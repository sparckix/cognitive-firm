#!/usr/bin/env python3
"""Generate a generic pre-tick brief for a research-director role.

This is a kernel-level surface, not a tenant research policy. It reads generic
state if present and stays quiet when optional tenant adapters are absent.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WORKSPACE = REPO_ROOT / "cognitive_firm_workspace"


def resolve_root(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    env = os.environ.get("COGNITIVE_FIRM_ROOT") or os.environ.get("TENANT_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return REPO_ROOT


def resolve_workspace(root: Path, value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    env = os.environ.get("COGNITIVE_FIRM_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    return root / "cognitive_firm_workspace"


def section(title: str) -> None:
    print()
    print(f"## {title}")
    print()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def jsonl_tail(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows[-limit:]


def render_role_scope(root: Path, role_id: str, short: bool) -> None:
    role_path = root / "org" / "roles" / f"{role_id}.yaml"
    mandate_path = root / "org" / "mandates" / f"{role_id}_mandate.md"
    print(f"- Role contract: `{role_path.relative_to(root)}`" if role_path.exists() else "- Role contract: missing")
    print(
        f"- Mandate: `{mandate_path.relative_to(root)}`"
        if mandate_path.exists()
        else "- Mandate: missing or supplied by overlay"
    )
    if mandate_path.exists() and not short:
        lines = mandate_path.read_text(encoding="utf-8").splitlines()[:18]
        print()
        for line in lines:
            print(f"  {line}")


def render_workspace(workspace: Path, limit: int) -> None:
    transitions = jsonl_tail(workspace / "transitions.jsonl", limit)
    gates = jsonl_tail(workspace / "gates.jsonl", limit)
    print(f"- Workspace: `{workspace}`")
    print(f"- Recent transitions: {len(transitions)} shown")
    for row in transitions:
        event = row.get("event_type") or row.get("transition_type") or row.get("kind") or "transition"
        actor = row.get("actor") or row.get("by") or "unknown"
        ref = row.get("object_ref") or row.get("target") or row.get("transition_id") or ""
        print(f"  - {event} by {actor}: {ref}")
    print(f"- Recent gates: {len(gates)} shown")
    for row in gates:
        status = row.get("status") or row.get("decision") or "unknown"
        ref = row.get("gate_id") or row.get("object_ref") or row.get("target") or ""
        print(f"  - {status}: {ref}")


def render_forecast_market(root: Path) -> None:
    summary_path = root / "org" / "forecast_market" / "global_health.json"
    summary = read_json(summary_path)
    if summary is None:
        print("- Forecast market: no generic summary found")
        return
    print(f"- Forecast market summary: `{summary_path.relative_to(root)}`")
    for key in [
        "n_contracts",
        "n_awaiting_forecasts",
        "n_aggregate_debt",
        "n_score_debt",
        "n_high_confidence_misses",
    ]:
        if key in summary:
            print(f"  - {key}: {summary[key]}")


def render_action_impact(root: Path) -> None:
    candidates = [
        root / "org" / "action_impact" / "summary.json",
        root / "cognitive_firm_workspace" / "action_impact_summary.json",
    ]
    summary_path = next((path for path in candidates if path.exists()), None)
    if summary_path is None:
        print("- Action-impact summary: no generic summary found")
        return
    summary = read_json(summary_path)
    if summary is None:
        print(f"- Action-impact summary: `{summary_path.relative_to(root)}` could not be parsed")
        return
    print(f"- Action-impact summary: `{summary_path.relative_to(root)}`")
    for key in ["n_actions", "n_resolved_actions", "n_unresolved_actions", "n_learning_candidates"]:
        if key in summary:
            print(f"  - {key}: {summary[key]}")


def render_next_actions() -> None:
    print("- Read the role contract and mandate before changing project direction.")
    print("- Check open gates and recent transitions before starting new work.")
    print("- If forecast or action-impact summaries are present, use them as routing evidence.")
    print("- Record new durable state through kernel-service or typed primitive CLIs.")
    print("- Keep tenant-specific policy in the overlay, not in the kernel.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=None, help="Kernel or overlay root. Defaults to this checkout.")
    parser.add_argument("--workspace", default=None, help="Workspace state directory.")
    parser.add_argument("--role-id", default="research_director")
    parser.add_argument("--short", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    root = resolve_root(args.root)
    workspace = resolve_workspace(root, args.workspace)
    now = datetime.now(timezone.utc).isoformat()

    print(f"# Research-Director Tick Brief — {now}")
    print()
    print("Generic kernel surface. Optional tenant adapters may add richer summaries.")

    section("Role Scope")
    render_role_scope(root, args.role_id, args.short)

    section("Workspace State")
    render_workspace(workspace, args.limit)

    section("Forecast Market")
    render_forecast_market(root)

    section("Action Impact")
    render_action_impact(root)

    section("Next Actions")
    render_next_actions()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
