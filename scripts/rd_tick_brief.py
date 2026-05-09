#!/usr/bin/env python3
"""
rd_tick_brief.py — kernel-tick surfacing for Research Director discipline.

Operator catch (NS-tenant session 2026-05-09 ~20:15 UTC, ported here
2026-05-09 ~21:00 UTC): RD agents drift to free-recall dispatch, ignoring
the orchestration menu / pattern-deployment ledger / monoculture diagnostics
that already exist on disk. The mandate that was supposed to enforce
discipline doesn't have a kernel-tick hook.

This script is the kernel-tick brief. Every research-director-role
agent (this session, VPS agents on Hetzner) MUST run this at session
start (or daemon-tick start) and read the output before any dispatch
decision. The brief is deterministic, short, and pulls from on-disk
state — no agent invention.

This module lives in cognitive-firm (the org-OS kernel). It reads from
a tenant overlay path (default: $TENANT_ROOT or repo root) so VPS
deployments can point it at any tenant's analytics/* and org/* trees.

Wire-up:
  1. `org/bootstrap_manifest.yaml` declares `pre_tick_scripts:` with
     `only_for_roles: [research_director]` and `output_to:
     analytics/RD_TICK_BRIEF.md`.
  2. `scripts/agent_daemon.py` runs pre_tick_scripts before formatting
     `required_reads`. If exit != 0 and `failure_action: block`, abort.

Usage:
  python scripts/rd_tick_brief.py
  python scripts/rd_tick_brief.py --tenant-root /path/to/tenant
  python scripts/rd_tick_brief.py --short

Exit codes:
  0 — gate passed (or no monoculture data available; fail-open).
  1 — monoculture flag firing on the deployment ledger; tick blocked.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def section(title: str) -> None:
    print()
    print(f"## §{title}")
    print()


def resolve_tenant_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser()
    env = os.environ.get("TENANT_ROOT")
    if env:
        return Path(env).expanduser()
    # Default: repo root (works for in-repo dev)
    return Path(__file__).resolve().parent.parent


def safe_read(path: Path, max_lines: int = 80) -> list[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()[:max_lines]
    except Exception:
        return []


def safe_jsonl_tail(path: Path, n: int) -> list[dict]:
    if not path.exists():
        return []
    try:
        rows: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows[-n:]
    except Exception:
        return []


def run_scorer(tenant: Path) -> dict:
    """Run the tenant's diversity scorer if it exists. Return parsed summary."""
    scorer = tenant / "scripts/score_pattern_deployment_diversity.py"
    summary = tenant / "analytics/pattern_deployment_diversity.json"
    if not scorer.exists():
        return {}
    try:
        subprocess.run(
            ["python", str(scorer), "--window", "15"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return {}
    if summary.exists():
        try:
            return json.loads(summary.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def render_mandate(tenant: Path, short: bool) -> None:
    p = tenant / "org/mandates/research_director_mandate.md"
    if not p.exists():
        print(f"  (no {p.name} in tenant)")
        return
    cap = 30 if short else 80
    for line in safe_read(p, cap):
        print(f"  {line}")
    total = len(p.read_text(encoding="utf-8").splitlines())
    if total > cap:
        print(f"  ... ({total - cap} more lines)")


def render_pattern_state(tenant: Path) -> None:
    pat_idx = tenant / "org/patterns/INDEX.md"
    ap_idx = tenant / "org/anti-patterns/INDEX.md"
    if not pat_idx.exists():
        print("  (no patterns/INDEX.md in tenant)")
        return
    text = pat_idx.read_text(encoding="utf-8")
    pat = sum(1 for ln in text.splitlines() if ln.strip().startswith("| PATTERN-"))
    meta = sum(1 for ln in text.splitlines() if ln.strip().startswith("| META-PATTERN-"))
    print(f"  Patterns: {pat} regular + {meta} meta")
    if ap_idx.exists():
        ap_text = ap_idx.read_text(encoding="utf-8")
        ap = sum(1 for ln in ap_text.splitlines() if ln.strip().startswith("| ANTI-PATTERN-"))
        print(f"  Anti-patterns: {ap}")


def render_diversity(summary: dict) -> int:
    """Returns 1 if monoculture flag firing, else 0."""
    if not summary:
        print("  (no scorer summary; tenant may not run pattern_deployment_ledger)")
        return 0
    metrics = summary.get("metrics", {})
    flag = metrics.get("monoculture_flag", False)
    print(f"  monoculture_flag = {flag}")
    print(f"    max share: {metrics.get('monoculture_max_share', 0):.3f} on {metrics.get('monoculture_max_pattern', 'NA')}")
    print(f"  audit_share: {metrics.get('audit_share', 0):.3f}")
    print(f"  external_share: {metrics.get('external_share', 0):.3f}")
    print(f"  eigenquestion_share: {metrics.get('eigenquestion_share', 0):.3f}")
    blind = [p for p, _ in summary.get("blind_spots", [])]
    if blind:
        head = ", ".join(blind[:6])
        more = f" + {len(blind) - 6} more" if len(blind) > 6 else ""
        print(f"  blind spots: {head}{more}")
    if flag:
        print()
        print(f"  !!! MONOCULTURE FLAG FIRING — DEPLOY DIVERSE PATTERN NEXT !!!")
        return 1
    return 0


def render_recent_catches(tenant: Path, n: int) -> None:
    rows = safe_jsonl_tail(tenant / "analytics/catch_ledger.jsonl", n)
    if not rows:
        print("  (no catch_ledger.jsonl in tenant)")
        return
    print(f"  Last {n}:")
    for r in rows:
        cid = r.get("catch_id", "NA")
        title = (r.get("title", "") or "")[:140]
        status = r.get("status", "NA")
        print(f"    {cid} [{status}] {title}")


def render_open_pls(tenant: Path, n: int) -> None:
    path = tenant / "analytics/prediction_ledger.jsonl"
    if not path.exists():
        print("  (no prediction_ledger.jsonl in tenant)")
        return
    pl_seen: dict[str, dict] = {}
    pl_resolved: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            pid = row.get("prediction_id")
            if not pid:
                continue
            if "resolved_at" in row:
                pl_resolved.add(pid)
            elif pid not in pl_seen:
                pl_seen[pid] = row
    except Exception:
        return
    open_pls = [(pid, row) for pid, row in pl_seen.items() if pid not in pl_resolved]
    open_pls.sort(key=lambda kv: kv[1].get("predicted_at", ""), reverse=True)
    print(f"  Open PLs: {len(open_pls)}")
    for pid, row in open_pls[:n]:
        substrate = (row.get("substrate", "") or "")[:60]
        question = (row.get("question", "") or "")[:120]
        print(f"    {pid} [{substrate}]")
        print(f"      Q: {question}")


def render_calibration(tenant: Path) -> None:
    """Surface PL calibration state. Added 2026-05-10 per operator catch
    'I haven't seen u update the predictions in terms of estimation etc.'
    VPS agents must SEE calibration drift every tick, not on-demand.
    """
    scorer = tenant / "scripts/score_prediction_ledger_calibration.py"
    summary_path = tenant / "analytics/prediction_ledger_calibration_summary.json"
    if not scorer.exists():
        print("  (no calibration scorer in tenant)")
        return
    try:
        subprocess.run(
            ["python", str(scorer)],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        pass
    if not summary_path.exists():
        print("  (calibration summary unavailable)")
        return
    try:
        s = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        print("  (calibration summary parse failed)")
        return
    cross = s.get("cross_predictor", {})
    effort = s.get("effort_ratio", {})
    cost = s.get("cost_ratio", {})
    demo = s.get("demotion_check", {})
    n_scored = s.get("n_rows_brier_scored", 0)
    print(f"  N resolved scored: {n_scored} (gate: 20)")
    if cross:
        best = cross.get("best_predictor", "NA")
        worst = cross.get("worst_predictor", "NA")
        bbrier = cross.get("best_brier_mean", 0)
        wbrier = cross.get("worst_brier_mean", 0)
        print(f"  Cross-predictor Brier: best {best}={bbrier:.3f}, worst {worst}={wbrier:.3f}")
    print(f"  Effort-ratio (predicted_min/actual_min) mean={effort.get('mean', 0):.2f} median={effort.get('median', 0):.2f} (in-band [0.5, 2.0])")
    pred_effort = effort.get('per_predictor', {})
    out_of_band = [p for p, d in pred_effort.items()
                   if isinstance(d, dict) and d.get('out_of_band')]
    if out_of_band:
        print(f"  Predictors OUT-OF-BAND on effort: {', '.join(out_of_band[:3])}")
    print(f"  Cost-ratio mean={cost.get('mean', 0):.2f} (in-band [0.5, 2.0])")
    if s.get('demote_now'):
        print(f"  !!! DEMOTION RULE TRIGGERED — review before more PL forecasts !!!")


def render_predispatch_checklist() -> None:
    print("  Before any dispatch (cold-shot or internal-Claude agent):")
    print("    1. Run: python scripts/predispatch_check.py \\")
    print("              --pattern-id PATTERN-XXX --mode <m> --internal-or-external <e> \\")
    print("              --substrate <substrate>")
    print("    2. Refuse if monoculture flag firing without --override.")
    print("    3. Pre-register PL row with conditional odds in analytics/prediction_ledger.jsonl.")
    print("    4. Dispatch.")
    print("    5. Log to analytics/pattern_deployment_ledger.jsonl with task_id.")
    print("    6. Resolve PL row when result lands.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-root", default=None,
                        help="Tenant repo root (default: $TENANT_ROOT or repo root)")
    parser.add_argument("--short", action="store_true",
                        help="One-screen scan (less mandate detail)")
    parser.add_argument("--last-n-catches", type=int, default=5)
    parser.add_argument("--last-n-pls", type=int, default=5)
    args = parser.parse_args()

    tenant = resolve_tenant_root(args.tenant_root)
    now = datetime.now(timezone.utc).isoformat()
    print(f"# RD-Tick Brief — {now}")
    print(f"_Tenant root: {tenant}_")
    print()
    print("**This brief is auto-generated by `scripts/rd_tick_brief.py`.**")
    print("Every Research-Director-role agent (this session, VPS agent on")
    print("Hetzner) MUST read this at session-start AND before any dispatch")
    print("decision. Bootstrap manifest hook: `pre_tick_scripts` with")
    print("`only_for_roles: [research_director]`.")

    section("1. Active mandates")
    render_mandate(tenant, args.short)

    section("2. Pattern catalog state")
    render_pattern_state(tenant)

    summary = run_scorer(tenant)
    section("3. Diversity scorer state")
    monoculture = render_diversity(summary)

    section(f"4. Last {args.last_n_catches} catches")
    render_recent_catches(tenant, args.last_n_catches)

    section(f"5. Last {args.last_n_pls} unresolved PLs")
    render_open_pls(tenant, args.last_n_pls)

    section("6. PL calibration state")
    render_calibration(tenant)

    section("7. Pre-dispatch checklist")
    render_predispatch_checklist()

    print()
    print("---")
    print(f"_Brief end. Generated by rd_tick_brief.py at {now}._")
    return 1 if monoculture else 0


if __name__ == "__main__":
    raise SystemExit(main())
