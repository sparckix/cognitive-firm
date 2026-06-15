from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import html
import argparse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.distribution.gitops import commit, stage_all  # noqa: E402
from cognitive_firm.distribution.installer import install  # noqa: E402
from cognitive_firm.distribution.manifest import load_manifest  # noqa: E402
from cognitive_firm.orchestration.run_checkpoints import list_runs  # noqa: E402
from demos.self_evolving_org.run import (  # noqa: E402
    PlannerRejectionError,
    ReviewerRuntimeConfig,
    _define_demo_unit,
    _demo_kernel_config,
    _parse_llm_evolution_steps,
    _planner_selection_with_receipt,
    _run_governed_evolution,
    _seed_genesis_workload,
    _write_planner_rejection_report,
)


def run_smoke(root: Path) -> dict[str, Any]:
    """Run a no-cost daemon-native starter-firm dispatch smoke.

    This is not the live self-evolving demo. It proves the native path that
    the live demo must use: installed starter firm, durable role office,
    mandate, task inbox, session, authorization, daemon dispatch, and task
    closure. The execution runtime is a local stub so public smoke remains
    deterministic and network-free.
    """

    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    demo_firm = root / "demo-firm"
    manifest = load_manifest(ROOT / "distro" / "starter-firm" / "package.yaml")
    receipt = install(manifest, ROOT / "distro" / "starter-firm", demo_firm)
    _seed_daemon_overlay(demo_firm)
    stub = _write_stub_agent(root)
    stage_all(demo_firm)
    commit(demo_firm, "seed daemon-native self-evolving smoke overlay")

    result = _run_daemon_once(demo_firm=demo_firm, agent_cli=str(stub))

    report = _build_report(
        demo_firm=demo_firm,
        receipt=receipt.as_dict(),
        command=result["command"],
        result=result["completed"],
    )
    _write_daemon_report_artifacts(demo_firm, report)
    stage_all(demo_firm)
    commit(demo_firm, "record daemon-native self-evolving smoke report")
    return report


def run_governed_smoke(
    root: Path,
    *,
    agent_cli: str | None = None,
    agent_adapter: str = "claude_print",
    daemon_timeout: int = 30,
    reviewer_runtime: str | None = None,
    reviewer_adapter: str = "auto",
    reviewer_timeout_seconds: int = 600,
) -> dict[str, Any]:
    """Run daemon dispatch, then govern its bounded planner output.

    The daemon still only dispatches a role-bearing runtime and records
    dispatch provenance. The structural mutation path is reused from
    `self_evolving_org_demo`; this function only bridges the daemon-produced
    planner artifact into that existing governed path.
    """

    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    demo_firm = root / "demo-firm"
    manifest = load_manifest(ROOT / "distro" / "starter-firm" / "package.yaml")
    receipt = install(manifest, ROOT / "distro" / "starter-firm", demo_firm)
    use_stub = agent_cli is None
    _seed_daemon_overlay(demo_firm, planner_task=True)
    resolved_agent_cli = str(_write_stub_agent(root, planner_output=True)) if use_stub else str(agent_cli)
    resolved_adapter = "claude_print" if use_stub else agent_adapter
    stage_all(demo_firm)
    commit(
        demo_firm,
        "seed daemon-native governed self-evolving smoke overlay",
    )

    result = _run_daemon_once(
        demo_firm=demo_firm,
        agent_cli=resolved_agent_cli,
        agent_adapter=resolved_adapter,
        member_id="stub_subscription_agent" if use_stub else "live_subscription_agent",
        timeout_s=daemon_timeout,
    )
    daemon_report = _build_report(
        demo_firm=demo_firm,
        receipt=receipt.as_dict(),
        command=result["command"],
        result=result["completed"],
        expect_prompt_capture=use_stub,
    )
    _write_daemon_report_artifacts(demo_firm, daemon_report)
    stage_all(demo_firm)
    commit(demo_firm, "record daemon-native dispatch proof")
    if daemon_report["summary"]["verdict"] != "passed":
        return {
            "demo": "self_evolving_daemon_governed_smoke",
            "no_external_calls": use_stub,
            "daemon_dispatch": daemon_report,
            "summary": {
                "verdict": "failed",
                "reason": "daemon dispatch failed",
                "demo_firm": str(demo_firm),
                "daemon_process_ok": daemon_report["summary"].get("daemon_process_ok"),
                "dispatch_chain_valid": daemon_report["summary"].get("dispatch_chain_valid"),
                "runtime_run_count": daemon_report["summary"].get("runtime_run_count"),
                "runtime_run_completed": daemon_report["summary"].get("runtime_run_completed"),
                "daemon_returncode": daemon_report["summary"].get("daemon_returncode"),
                "daemon_process_timed_out": daemon_report["summary"].get("daemon_process_timed_out"),
                "daemon_report_ref": "file://reports/self-evolving-daemon-smoke.json",
                "daemon_timeline_ref": "file://reports/self-evolving-daemon-timeline.html",
                "daemon_prompt_ref": (
                    f"file://{daemon_report['artifacts']['daemon_prompt']}"
                    if daemon_report.get("artifacts", {}).get("daemon_prompt")
                    else None
                ),
                "stdout_tail": daemon_report.get("stdout_tail", ""),
                "stderr_tail": daemon_report.get("stderr_tail", ""),
            },
        }

    planner_path = demo_firm / "workspace" / "daemon_planner_steps.json"
    if not planner_path.exists():
        rejection = _write_planner_rejection_report(
            demo_firm,
            transport="daemon_subscription_cli",
            prompt=None,
            response="",
            metadata={
                "daemon_run_id": daemon_report["dispatch_proof"]["run_id"],
                "daemon_report_ref": "file://reports/self-evolving-daemon-smoke.json",
                "expected_artifact_ref": "file://workspace/daemon_planner_steps.json",
                "agent_cli": Path(resolved_agent_cli).name,
                "agent_adapter": resolved_adapter,
                "stub_runtime": use_stub,
            },
            reason="daemon-dispatched planner did not write workspace/daemon_planner_steps.json",
            stderr=daemon_report.get("stderr_tail", ""),
        )
        stage_all(demo_firm)
        commit(demo_firm, "record rejected daemon planner output")
        raise PlannerRejectionError(rejection)
    planner_text = planner_path.read_text(encoding="utf-8")
    try:
        steps = _parse_llm_evolution_steps(planner_text, max_steps=1)
    except Exception as exc:
        rejection = _write_planner_rejection_report(
            demo_firm,
            transport="daemon_subscription_cli",
            prompt=None,
            response=planner_text,
            metadata={
                "daemon_run_id": daemon_report["dispatch_proof"]["run_id"],
                "daemon_report_ref": "file://reports/self-evolving-daemon-smoke.json",
                "planner_artifact_ref": "file://workspace/daemon_planner_steps.json",
                "agent_cli": Path(resolved_agent_cli).name,
                "agent_adapter": resolved_adapter,
                "stub_runtime": use_stub,
            },
            reason=str(exc),
            stderr=daemon_report.get("stderr_tail", ""),
        )
        stage_all(demo_firm)
        commit(demo_firm, "record rejected daemon planner output")
        raise PlannerRejectionError(rejection) from exc
    daemon_prompt_artifact = daemon_report.get("artifacts", {}).get("daemon_prompt")
    prompt_path = (
        demo_firm / daemon_prompt_artifact
        if isinstance(daemon_prompt_artifact, str)
        else demo_firm / "workspace" / "stub_agent_prompt.txt"
    )
    prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else None
    selection = _planner_selection_with_receipt(
        demo_firm,
        transport="daemon_subscription_cli",
        steps=steps,
        prompt=prompt,
        response=planner_text,
        metadata={
            "daemon_run_id": daemon_report["dispatch_proof"]["run_id"],
            "daemon_report_ref": "file://reports/self-evolving-daemon-smoke.json",
            "daemon_timeline_ref": "file://reports/self-evolving-daemon-timeline.json",
            "planner_artifact_ref": "file://workspace/daemon_planner_steps.json",
            "agent_cli": Path(resolved_agent_cli).name,
            "agent_adapter": resolved_adapter,
            "stub_runtime": use_stub,
        },
    )
    config = _demo_kernel_config(demo_firm)
    _define_demo_unit(config)
    governed = _run_governed_evolution(
        demo_firm=demo_firm,
        config=config,
        selection=selection,
        iterations_requested=1,
        max_budget_units=None,
        stop_file=None,
        planner_transport="daemon_subscription_cli",
        starter_install=receipt.as_dict(),
        no_external_calls=use_stub,
        reviewer_runtime=(
            ReviewerRuntimeConfig(
                runtime=reviewer_runtime,
                adapter=reviewer_adapter,
                timeout_seconds=reviewer_timeout_seconds,
                prompt_mode="compact",
            )
            if reviewer_runtime
            else None
        ),
        extra_report_fields={
            "daemon_dispatch": {
                "valid": daemon_report["dispatch_proof"]["valid"],
                "run_id": daemon_report["dispatch_proof"]["run_id"],
                "report_ref": "file://reports/self-evolving-daemon-smoke.json",
                "timeline_ref": "file://reports/self-evolving-daemon-timeline.json",
            }
        },
    )
    governed["demo"] = "self_evolving_daemon_governed_smoke"
    return governed


def _seed_daemon_overlay(demo_firm: Path, *, planner_task: bool = False) -> None:
    org = demo_firm / "org"
    for rel in (
        "roles",
        "mandates",
        "charters",
        "tasks/pending",
        "tasks/active",
        "tasks/done",
        "controls",
        "directives",
    ):
        (org / rel).mkdir(parents=True, exist_ok=True)
    (demo_firm / "workspace").mkdir(parents=True, exist_ok=True)
    (demo_firm / "cognitive_firm_workspace").mkdir(parents=True, exist_ok=True)
    _seed_genesis_workload(demo_firm)
    (org / "charters" / "self_evolving_firm.md").write_text(
        """
# Self-Evolving Firm Charter

## Purpose

This firm exists to perform its workload well and cheaply, and to improve its
own operating model only insofar as that improves workload performance. The
workload is the stream of task packets in `org/workload/inbox/`, scored by an
external rubric this firm cannot read or modify.

Capability is trailing workload score per unit dispatched budget, with error
and incident counts as guard metrics. Counts of offices, policies, proposals,
or documents are explicitly not measures of capability.

## Initial Objective

Raise trailing capability. Begin by executing the workload as constituted,
then propose one bounded structural change at a time where evidence from
executed work shows the current office structure, mandates, decision model,
protocol, or learning units are costing score or budget.

## Evolution Rules

- Every structural proposal must state a falsifiable predicted effect on
  capability or guard metrics and a review horizon.
- Outcome links are mandatory. A mutation whose prediction fails at review
  becomes a reversal candidate at the next routine review.
- At most 20% of dispatched budget per cycle may fund structural
  self-modification; the remainder funds workload execution.
- Any proposal that adds an office, policy, or protocol must name one existing
  structure to retire, or justify net growth to the principal. Every routine
  review tables at least one deletion candidate.

## Amendment Tiers

- Tier 0 immutable: typed authority, principal decision rights, attestation and
  audit duties, and the Non-Goals below.
- Tier 1 principal approval only: this charter, the capability definition, and
  the workload scoring interface.
- Tier 2 governed mutation path: offices, mandates, decision models, policies,
  protocols, and learning units.

## Non-Goals

- Do not choose an industry-specific business model for the kernel demo.
- Do not expand autonomy, tools, budget, or external commitments.
- Do not read, infer, or optimize against the workload scoring rubric itself.
- Do not apply structural changes outside governed proposal, review, approval,
  attestation, learning, proof, and git receipt.
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (org / "bootstrap_manifest.yaml").write_text(
        """
required_reads:
  - path: "AGENTS.md"
    purpose: "repository-level agent instructions"
  - path: "org/roles/{role_id}.yaml"
    purpose: "durable role office contract"
  - path: "org/mandates/{role_id}_mandate.md"
    purpose: "typed mandate and escalation boundary"
  - path: "org/charters/self_evolving_firm.md"
    purpose: "self-organizing firm objective and operating-model game"
  - path: "org/workload/README.md"
    purpose: "exogenous workload interface and scoring boundary"
  - path: "org/workload/inbox/"
    purpose: "visible workload packets the firm must improve against"
conditional_reads:
  - path: "docs/PROTOCOLS.md"
    purpose: "protocol reference when touching governance state"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (org / "roles" / "principal.yaml").write_text(
        """
schema_version: 1
role_id: principal
role_class: authority
description: >
  Durable office holding final decision rights for structural mutation in the
  demo firm.

authorized_paths:
  - "org/**"

delegates_to:
  - role.org_evolver
  - role.evaluator
  - role.risk_guardian
  - role.learning_steward

mandate_path: org/mandates/principal_mandate.md
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (org / "roles" / "org_evolver.yaml").write_text(
        """
schema_version: 1
role_id: org_evolver
role_class: governance_worker
description: >
  Durable office that proposes bounded improvements to organization structure,
  mandates, charters, decision paths, communication patterns, and learning
  mechanisms within explicit authority.

authorized_paths:
  - "org/"
  - "org/**"
  - "workspace/"
  - "cognitive_firm_workspace/"
forbidden_paths:
  - ".env"
  - "secrets/"
  - "~/.ssh/"

delegates_to:
  - role.evaluator
  - role.risk_guardian
  - role.learning_steward
  - role.principal
  - role.reviewer

escalates_to:
  - role.principal

budget:
  daily_cap_usd: 5.00
  session_cap_usd: 2.00
  single_action_cap_usd: 1.00
  warn_threshold_frac: 0.80
  absolute_ceiling_usd: 5.00

mandate_path: org/mandates/org_evolver_mandate.md
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (org / "roles" / "evaluator.yaml").write_text(
        """
schema_version: 1
role_id: evaluator
role_class: governance_reviewer
description: >
  Durable office that reviews evidence, authority boundaries, risk, and
  rollback plans before structural changes are promoted for approval.

authorized_paths:
  - "org/reviews/"
  - "org/reviews/**"
  - "org/policies/"
  - "org/policies/**"

delegates_to:
  - role.risk_guardian
  - role.learning_steward

escalates_to:
  - role.principal

mandate_path: org/mandates/evaluator_mandate.md
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (org / "roles" / "risk_guardian.yaml").write_text(
        """
schema_version: 1
role_id: risk_guardian
role_class: governance_reviewer
description: >
  Durable office that independently reviews authority expansion, recursion
  risk, rollback quality, resource expansion, and unsafe incentives.

authorized_paths:
  - "org/reviews/"
  - "org/reviews/**"
  - "org/risks/"
  - "org/risks/**"
  - "org/policies/"
  - "org/policies/**"

escalates_to:
  - role.principal

mandate_path: org/mandates/risk_guardian_mandate.md
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (org / "roles" / "learning_steward.yaml").write_text(
        """
schema_version: 1
role_id: learning_steward
role_class: governance_reviewer
description: >
  Durable office that owns approved learning-unit quality, replay cues, source
  traceability, review cadence, and retirement pressure.

authorized_paths:
  - "org/learning_events/"
  - "org/learning_events/**"
  - "org/reviews/"
  - "org/reviews/**"
  - "org/policies/"
  - "org/policies/**"

escalates_to:
  - role.principal

mandate_path: org/mandates/learning_steward_mandate.md
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (org / "mandates" / "principal_mandate.md").write_text(
        """
# Principal Mandate

Hold final approval rights for structural mutation in the demo firm. Advisory
review, quorum aggregation, and agent recommendations are evidence; they do not
apply organization state without explicit Principal approval.
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (org / "mandates" / "evaluator_mandate.md").write_text(
        """
# Evaluator Mandate

Review structural-change evidence before governance promotion. Check source
refs, authority boundaries, risk, rollback, and whether uncertainty should
escalate to the principal. Request Risk Guardian or Learning Steward review
when the proposal affects authority, recursion, incentives, or durable learning.
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (org / "mandates" / "org_evolver_mandate.md").write_text(
        """
# Org Evolver Mandate

## Objective

Improve the firm's ability to self-organize, learn, and adapt by proposing
bounded changes to roles, mandates, charters, decision paths, protocols, work
routing, and learning mechanisms. Use `org/charters/self_evolving_firm.md` as
the current objective frame.

## Autonomous Authority

- Inspect the organization surface and task inbox.
- Draft low-risk proposal artifacts under `org/`.
- Execute explicit principal tasks that carry `autonomous_scope_ok: true`,
  stay inside authorized paths, and stay within the action budget.

## Escalation Required

- Creating, deleting, or materially expanding role authority.
- Changing principal preferences or top-level invariants.
- Increasing autonomy, spend, network access, or external commitments.

## Discipline

- Preserve generation/evaluation/approval/execution separation.
- Treat learning as durable reviewed state, not chat history.
- Record evidence and route uncertain authority to the principal.
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (org / "mandates" / "risk_guardian_mandate.md").write_text(
        """
# Risk Guardian Mandate

Review proposed structural changes for authority expansion, recursive
instability, weak rollback plans, hidden resource increases, and incentives
that could distort future learning. Approve, abstain, or escalate as an
advisory control before Principal approval.
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (org / "mandates" / "learning_steward_mandate.md").write_text(
        """
# Learning Steward Mandate

Ensure approved learning units carry future-use cues, source carrier refs,
owner roles, review cadence, and retirement paths. Learning is valid only when
it can affect future dispatch through reviewed state rather than remaining a
transcript.
""".strip()
        + "\n",
        encoding="utf-8",
    )
    task_body = (
        """
Review `org/charters/self_evolving_firm.md` and
`org/mandates/org_evolver_mandate.md`, then write one bounded structural change
proposal as JSON to `workspace/daemon_planner_steps.json`. The JSON must use
the self-evolving organization demo planner schema. Prefer changes that improve
the firm's objective, office structure, decision model, or learning units. Do
not mutate governed org state directly.
""".strip()
        if planner_task
        else """
Review `org/charters/self_evolving_firm.md` and
`org/mandates/org_evolver_mandate.md`, then report one bounded next improvement
candidate for the self-evolving organization demo. This smoke task is
intentionally no-op for state mutation; it exists to prove daemon-native
dispatch against an installed starter firm.
""".strip()
    )
    (org / "tasks" / "pending" / "daemon-native-org-evolver.md").write_text(
        """
---
goal_id: daemon-native-org-evolver
priority: high
assigned_to: role.org_evolver
autonomous_scope_ok: true
estimated_cost_usd: 0.0
created_by: principal
created_utc: "2026-06-11T00:00:00+00:00"
declared_paths:
  - org/charters/self_evolving_firm.md
  - org/mandates/org_evolver_mandate.md
---

""".lstrip()
        + task_body
        + "\n",
        encoding="utf-8",
    )


def _write_stub_agent(root: Path, *, planner_output: bool = False) -> Path:
    stub = root / "stub_subscription_agent.py"
    planner_block = ""
    if planner_output:
        planner_payload = {
            "steps": [
                {
                    "step_id": "daemon_planned_evidence_route",
                    "title": "Daemon planned evidence route",
                    "change_kind": "mandate_change",
                    "target_ref": "org/mandates/daemon_planned_evidence_route.md",
                    "rationale": "The daemon-dispatched role identified that evidence routing needs a durable note.",
                    "expected_behavior_change": "Future structural proposals cite evidence routes before review.",
                    "risk_summary": "Narrows review input requirements; grants no new authority.",
                    "rollback_plan": "Remove org/mandates/daemon_planned_evidence_route.md.",
                    "applied_relpath": "org/mandates/daemon_planned_evidence_route.md",
                    "applied_text": (
                        "# Daemon Planned Evidence Route\n\n"
                        "Structural proposals should identify their evidence route before review. "
                        "The route should include source refs, unresolved gaps, and the reviewer role.\n"
                    ),
                }
            ]
        }
        planner_json = json.dumps(planner_payload, sort_keys=True)
        planner_block = (
            "\n"
            f"Path('workspace/daemon_planner_steps.json').write_text({planner_json!r}, encoding='utf-8')\n"
        )
    planner_artifact_expr = (
        "'workspace/daemon_planner_steps.json'" if planner_output else "None"
    )
    stub.write_text(
        f"""#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

args = sys.argv[1:]
prompt = ""
if "-p" in args:
    idx = args.index("-p")
    if idx + 1 < len(args):
        prompt = args[idx + 1]
elif args:
    prompt = args[-1]
Path("workspace").mkdir(exist_ok=True)
Path("workspace/stub_agent_prompt.txt").write_text(prompt, encoding="utf-8")
{planner_block}
print(json.dumps({{
    "stub_runtime": "subscription_cli_shape",
    "received_prompt_chars": len(prompt),
    "planner_artifact": {planner_artifact_expr},
    "status": "completed"
}}))
""",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def _run_daemon_once(
    *,
    demo_firm: Path,
    agent_cli: str,
    agent_adapter: str = "claude_print",
    member_id: str = "stub_subscription_agent",
    timeout_s: int = 30,
) -> dict[str, Any]:
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "COGNITIVE_FIRM_PROJECT_ROOT": str(demo_firm),
        "ORG_ROOT": str(demo_firm / "org"),
        "COGNITIVE_FIRM_WORKSPACE": str(demo_firm / "cognitive_firm_workspace"),
        "COGNITIVE_FIRM_CLAUDE_PERMISSION_MODE": "acceptEdits",
    }
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "agent_daemon.py"),
        "--role",
        "org_evolver",
        "--tick-once",
        "--unattended",
        "--member-id",
        member_id,
        "--agent-cli",
        str(agent_cli),
        "--agent-adapter",
        agent_adapter,
    ]
    try:
        completed = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        completed = subprocess.CompletedProcess(
            cmd,
            returncode=124,
            stdout=(exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""),
            stderr=(exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr or "")
            + f"\ndaemon subprocess timed out after {timeout_s} seconds\n",
        )
    return {"command": cmd, "completed": completed}


def _write_daemon_report_artifacts(demo_firm: Path, report: dict[str, Any]) -> None:
    reports_dir = demo_firm / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "self-evolving-daemon-smoke.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports_dir / "self-evolving-daemon-smoke.md").write_text(
        _render_markdown_report(report),
        encoding="utf-8",
    )
    timeline_graph = _build_timeline_graph(report)
    (reports_dir / "self-evolving-daemon-timeline.json").write_text(
        json.dumps(timeline_graph, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports_dir / "self-evolving-daemon-timeline.html").write_text(
        _render_timeline_html(timeline_graph),
        encoding="utf-8",
    )


def _build_report(
    *,
    demo_firm: Path,
    receipt: dict[str, Any],
    command: list[str],
    result: subprocess.CompletedProcess[str],
    expect_prompt_capture: bool = True,
) -> dict[str, Any]:
    org = demo_firm / "org"
    workspace = demo_firm / "cognitive_firm_workspace"
    done_task = org / "tasks" / "done" / "daemon-native-org-evolver.md"
    active_task = org / "tasks" / "active" / "daemon-native-org-evolver.md"
    pending_task = org / "tasks" / "pending" / "daemon-native-org-evolver.md"
    session_dirs = sorted((org / "sessions").glob("sess_org_evolver_*"))
    daemon_session = org / "sessions" / "daemon" / "org_evolver.json"
    task_checkpoints = [
        session_dir / "state.json"
        for session_dir in session_dirs
        if (session_dir / "state.json").exists()
    ]
    continuity_written = daemon_session.exists() or bool(task_checkpoints)
    transitions = workspace / "transitions.jsonl"
    daemon_log = demo_firm / "workspace" / "agent_daemon_log.jsonl"
    prompt_capture = demo_firm / "workspace" / "stub_agent_prompt.txt"
    attestation_log = org / "attestations" / "action_attestations.jsonl"
    transition_rows = _read_jsonl(transitions)
    daemon_rows = _read_jsonl(daemon_log)
    daemon_prompt_ref = next(
        (
            row.get("prompt_ref")
            for row in reversed(daemon_rows)
            if row.get("prompt_ref")
        ),
        None,
    )
    daemon_prompt_capture = (
        demo_firm / str(daemon_prompt_ref)
        if isinstance(daemon_prompt_ref, str)
        else None
    )
    if daemon_prompt_capture is None or not daemon_prompt_capture.exists():
        prompt_dir = demo_firm / "workspace" / "agent_prompts"
        prompt_candidates = (
            sorted(
                (path for path in prompt_dir.glob("*.md") if path.is_file()),
                key=lambda path: (path.stat().st_mtime_ns, path.name),
            )
            if prompt_dir.exists()
            else []
        )
        daemon_prompt_capture = prompt_candidates[-1] if prompt_candidates else None
    attestation_rows = _read_jsonl(attestation_log)
    runs = list_runs(log_path=transitions)
    daemon_runs = [
        run
        for run in runs
        if run.owner_role == "role.org_evolver"
        and (run.idempotency_key or "").startswith("runtime:cognitive_firm_daemon:")
    ]
    latest_run = daemon_runs[-1] if daemon_runs else None
    expected_events = [
        "daemon.work.discovered",
        "daemon.dispatch.auto_approved",
        "daemon.task.claimed",
        "run.started",
        "run.checkpointed",
        "run.state_changed",
        "daemon.task.completed",
        "daemon.action.attested",
    ]
    transition_events = [str(row.get("event") or "") for row in transition_rows]
    expected_checkpoints = {
        "dispatch_agent_cli": "started",
        "dispatch_agent_cli_result": "completed",
    }
    checkpoint_statuses = {
        str(checkpoint.get("step_id")): str(checkpoint.get("status"))
        for checkpoint in (latest_run.checkpoints if latest_run else [])
    }
    dispatch_chain_valid = (
        all(event in transition_events for event in expected_events)
        and latest_run is not None
        and latest_run.state == "completed"
        and all(
            checkpoint_statuses.get(step_id) == status
            for step_id, status in expected_checkpoints.items()
        )
        and any(row.get("success") is True for row in daemon_rows)
        and any(
            row.get("action_type") == "agent_cli_dispatch"
            and row.get("verification_status") == "verified"
            and row.get("run_id") == latest_run.run_id
            for row in attestation_rows
        )
    )
    ok = (
        result.returncode == 0
        and done_task.exists()
        and not active_task.exists()
        and not pending_task.exists()
        and bool(session_dirs)
        and continuity_written
        and daemon_log.exists()
        and daemon_prompt_capture is not None
        and daemon_prompt_capture.exists()
        and (prompt_capture.exists() if expect_prompt_capture else True)
        and dispatch_chain_valid
    )
    return {
        "demo": "self_evolving_daemon_native_smoke",
        "no_external_calls": True,
        "starter_install": receipt,
        "demo_firm": str(demo_firm),
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
        "dispatch_proof": {
            "valid": dispatch_chain_valid,
            "expected_events": expected_events,
            "observed_events": transition_events,
            "run_id": latest_run.run_id if latest_run else None,
            "run_state": latest_run.state if latest_run else None,
            "run_owner_role": latest_run.owner_role if latest_run else None,
            "run_idempotency_key": latest_run.idempotency_key if latest_run else None,
            "checkpoint_statuses": checkpoint_statuses,
            "process_returncode": result.returncode,
            "process_timed_out": result.returncode == 124,
            "daemon_log_success": any(row.get("success") is True for row in daemon_rows),
            "attestation_count": len(attestation_rows),
            "verified_dispatch_attestation": any(
                row.get("action_type") == "agent_cli_dispatch"
                and row.get("verification_status") == "verified"
                and row.get("run_id") == latest_run.run_id
                for row in attestation_rows
            ) if latest_run else False,
        },
        "artifacts": {
            "done_task": str(done_task.relative_to(demo_firm)) if done_task.exists() else None,
            "transitions_log": str(transitions.relative_to(demo_firm)) if transitions.exists() else None,
            "daemon_log": str(daemon_log.relative_to(demo_firm)) if daemon_log.exists() else None,
            "daemon_prompt": (
                str(daemon_prompt_capture.relative_to(demo_firm))
                if daemon_prompt_capture is not None and daemon_prompt_capture.exists()
                else None
            ),
            "prompt_capture": str(prompt_capture.relative_to(demo_firm)) if prompt_capture.exists() else None,
            "session_checkpoint": (
                str(task_checkpoints[-1].relative_to(demo_firm))
                if task_checkpoints
                else None
            ),
            "daemon_session": (
                str(daemon_session.relative_to(demo_firm))
                if daemon_session.exists()
                else None
            ),
            "attestation_log": str(attestation_log.relative_to(demo_firm)) if attestation_log.exists() else None,
        },
        "summary": {
            "verdict": "passed" if ok else "failed",
            "daemon_returncode": result.returncode,
            "daemon_process_ok": result.returncode == 0,
            "daemon_process_timed_out": result.returncode == 124,
            "task_closed_done": done_task.exists(),
            "task_not_left_active": not active_task.exists(),
            "task_not_left_pending": not pending_task.exists(),
            "role_session_count": len(session_dirs),
            "daemon_continuity_written": continuity_written,
            "daemon_resume_session_written": daemon_session.exists(),
            "task_checkpoint_written": bool(task_checkpoints),
            "transition_log_written": transitions.exists(),
            "daemon_log_written": daemon_log.exists(),
            "daemon_prompt_written": (
                daemon_prompt_capture is not None and daemon_prompt_capture.exists()
            ),
            "action_attestation_written": attestation_log.exists(),
            "prompt_capture_expected": expect_prompt_capture,
            "stub_runtime_invoked": prompt_capture.exists(),
            "runtime_run_count": len(daemon_runs),
            "runtime_run_completed": latest_run.state == "completed" if latest_run else False,
            "dispatch_chain_valid": dispatch_chain_valid,
        },
    }


def _render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    proof = report["dispatch_proof"]
    lines = [
        "# Self-Evolving Daemon Dispatch Smoke",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Verdict | {_md(summary['verdict'])} |",
        f"| Daemon returncode | {_md(summary.get('daemon_returncode'))} |",
        f"| Daemon process ok | {str(summary['daemon_process_ok']).lower()} |",
        f"| Daemon timed out | {str(summary.get('daemon_process_timed_out', False)).lower()} |",
        f"| Task closed done | {str(summary['task_closed_done']).lower()} |",
        f"| Runtime runs | {summary['runtime_run_count']} |",
        f"| Runtime run completed | {str(summary['runtime_run_completed']).lower()} |",
        f"| Dispatch chain valid | {str(summary['dispatch_chain_valid']).lower()} |",
        f"| Action attestations | {proof['attestation_count']} |",
        "",
        "## Dispatch Proof",
        "",
        "| Stage | Ref |",
        "| --- | --- |",
        "| role office | org/roles/org_evolver.yaml |",
        "| mandate | org/mandates/org_evolver_mandate.md |",
        "| pending task | org/tasks/pending/daemon-native-org-evolver.md |",
        f"| runtime run | {_md(proof.get('run_id'))} |",
        "| completed task | org/tasks/done/daemon-native-org-evolver.md |",
        "| action attestation | org/attestations/action_attestations.jsonl |",
        f"| daemon prompt | {_md(report.get('artifacts', {}).get('daemon_prompt'))} |",
        "| daemon log | workspace/agent_daemon_log.jsonl |",
        "",
        "## Checkpoints",
        "",
        "| Checkpoint | Status |",
        "| --- | --- |",
    ]
    for step_id, status in proof.get("checkpoint_statuses", {}).items():
        lines.append(f"| {_md(step_id)} | {_md(status)} |")
    lines.extend(["", "## Observed Events", "", "| Event |", "| --- |"])
    for event in proof.get("observed_events", []):
        lines.append(f"| {_md(event)} |")
    lines.extend(["", "## Artifacts", "", "| Artifact | Path |", "| --- | --- |"])
    for key, value in report.get("artifacts", {}).items():
        lines.append(f"| {_md(key)} | {_md(value)} |")
    return "\n".join(lines) + "\n"


def _build_timeline_graph(report: dict[str, Any]) -> dict[str, Any]:
    proof = report["dispatch_proof"]
    summary = report["summary"]
    nodes = [
        {"id": "daemon:self_evolving_dispatch", "kind": "demo", "label": "Daemon Dispatch Smoke"},
        {"id": "role:org_evolver", "kind": "role_office", "label": "org_evolver"},
        {
            "id": "mandate:org_evolver",
            "kind": "mandate",
            "label": "org/mandates/org_evolver_mandate.md",
        },
        {
            "id": "task:daemon-native-org-evolver",
            "kind": "task",
            "label": "daemon-native-org-evolver",
        },
    ]
    run_id = proof.get("run_id")
    if run_id:
        nodes.append({"id": f"run:{run_id}", "kind": "runtime_run", "label": run_id})
    for step_id, status in proof.get("checkpoint_statuses", {}).items():
        nodes.append(
            {
                "id": f"checkpoint:{step_id}",
                "kind": "checkpoint",
                "label": step_id,
                "metadata": {"status": status},
            }
        )
    nodes.extend(
        [
            {
                "id": "attestation:agent_cli_dispatch",
                "kind": "action_attestation",
                "label": "agent_cli_dispatch",
                "metadata": {"verified": proof.get("verified_dispatch_attestation")},
            },
            {
                "id": "task_done:daemon-native-org-evolver",
                "kind": "completed_task",
                "label": "org/tasks/done/daemon-native-org-evolver.md",
            },
        ]
    )
    edges = [
        {"source": "daemon:self_evolving_dispatch", "target": "role:org_evolver", "label": "uses"},
        {"source": "role:org_evolver", "target": "mandate:org_evolver", "label": "bounded_by"},
        {"source": "mandate:org_evolver", "target": "task:daemon-native-org-evolver", "label": "authorizes"},
    ]
    if run_id:
        edges.append({"source": "task:daemon-native-org-evolver", "target": f"run:{run_id}", "label": "dispatches"})
        previous = f"run:{run_id}"
    else:
        previous = "task:daemon-native-org-evolver"
    for step_id in proof.get("checkpoint_statuses", {}):
        node_id = f"checkpoint:{step_id}"
        edges.append({"source": previous, "target": node_id, "label": "checkpoint"})
        previous = node_id
    edges.append({"source": previous, "target": "attestation:agent_cli_dispatch", "label": "attests"})
    edges.append(
        {
            "source": "attestation:agent_cli_dispatch",
            "target": "task_done:daemon-native-org-evolver",
            "label": "closes",
        }
    )
    return {
        "graph_kind": "self_evolving_daemon_dispatch_timeline",
        "demo": report["demo"],
        "summary": {
            "verdict": summary["verdict"],
            "dispatch_chain_valid": summary["dispatch_chain_valid"],
            "runtime_run_count": summary["runtime_run_count"],
            "nodes": len(nodes),
            "edges": len(edges),
        },
        "nodes": nodes,
        "edges": edges,
    }


def _render_timeline_html(graph: dict[str, Any]) -> str:
    graph_json = _json_for_script(graph)
    summary = graph["summary"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Self-Evolving Daemon Dispatch Timeline</title>
  <style>
    body {{ margin: 0; background: #f7f8fa; color: #18202b; font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    header {{ padding: 24px; background: #fff; border-bottom: 1px solid #d9dee7; }}
    h1 {{ margin: 0 0 12px; font-size: 24px; letter-spacing: 0; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; max-width: 900px; }}
    .metric {{ border: 1px solid #d9dee7; border-radius: 8px; background: #fbfcfe; padding: 10px 12px; min-height: 68px; }}
    .metric b {{ display: block; font-size: 22px; }}
    .metric span {{ color: #596575; font-size: 12px; }}
    main {{ padding: 16px 24px 32px; }}
    .node {{ border: 1px solid #d9dee7; border-left: 4px solid #176b87; border-radius: 8px; background: #fff; padding: 10px; margin-bottom: 8px; max-width: 760px; }}
    .kind {{ color: #596575; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }}
    .label {{ margin-top: 4px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; overflow-wrap: anywhere; }}
    .edge {{ color: #596575; margin: 0 0 8px 20px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <header>
    <h1>Self-Evolving Daemon Dispatch Timeline</h1>
    <div class="summary">
      <div class="metric"><b>{html.escape(str(summary.get("verdict", "")))}</b><span>verdict</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("dispatch_chain_valid", False)).lower())}</b><span>dispatch chain</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("runtime_run_count", 0)))}</b><span>runtime runs</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("nodes", 0)))}</b><span>timeline nodes</span></div>
    </div>
  </header>
  <main id="timeline"></main>
  <script id="graph-data" type="application/json">{graph_json}</script>
  <script>
    const graph = JSON.parse(document.getElementById('graph-data').textContent);
    const root = document.getElementById('timeline');
    const byId = new Map(graph.nodes.map((node) => [node.id, node]));
    function text(value) {{ return String(value == null ? '' : value); }}
    for (const node of graph.nodes) {{
      const element = document.createElement('section');
      element.className = 'node';
      const kind = document.createElement('div');
      kind.className = 'kind';
      kind.textContent = text(node.kind);
      const label = document.createElement('div');
      label.className = 'label';
      label.textContent = text(node.label);
      element.append(kind, label);
      root.appendChild(element);
      for (const edge of graph.edges.filter((edge) => edge.source === node.id)) {{
        const target = byId.get(edge.target);
        const row = document.createElement('div');
        row.className = 'edge';
        row.textContent = `${{text(edge.label)}} -> ${{text(target ? target.label : edge.target)}}`;
        root.appendChild(row);
      }}
    }}
  </script>
</body>
</html>
"""


def _json_for_script(value: Any) -> str:
    return (
        json.dumps(value, sort_keys=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run self-evolving daemon smokes.")
    parser.add_argument(
        "--governed",
        action="store_true",
        help="After daemon dispatch, route the daemon-produced planner artifact through the governed mutation demo path.",
    )
    parser.add_argument(
        "--agent-cli",
        help="Live role-bearing agent CLI for --governed mode. Omit to use the no-cost stub runtime.",
    )
    parser.add_argument(
        "--agent-adapter",
        default="auto",
        help="Agent adapter for --agent-cli in --governed mode: auto, claude_print, or codex_exec.",
    )
    parser.add_argument(
        "--agent-reviewer-runtime",
        help=(
            "Optional subscription/local agent CLI used to back evaluator, "
            "risk_guardian, and learning_steward during the governed mutation path."
        ),
    )
    parser.add_argument(
        "--agent-reviewer-adapter",
        default="auto",
        help="Agent adapter for --agent-reviewer-runtime: auto, claude_print, or codex_exec.",
    )
    parser.add_argument(
        "--reviewer-timeout",
        type=int,
        default=600,
        help="Seconds to allow each live reviewer subprocess to run.",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        help="Persist demo artifacts under this directory instead of a temporary directory.",
    )
    parser.add_argument(
        "--daemon-timeout",
        type=int,
        default=30,
        help="Seconds to allow the daemon subprocess to run.",
    )
    args = parser.parse_args(argv)
    if args.reviewer_timeout <= 0:
        parser.error("--reviewer-timeout must be positive")
    temp_context = (
        tempfile.TemporaryDirectory(prefix="cf-self-evolving-daemon-")
        if args.workdir is None
        else None
    )
    tmp = args.workdir if args.workdir is not None else Path(temp_context.name)  # type: ignore[union-attr]
    try:
        try:
            report = (
                run_governed_smoke(
                    Path(tmp),
                    agent_cli=args.agent_cli,
                    agent_adapter=args.agent_adapter,
                    daemon_timeout=args.daemon_timeout,
                    reviewer_runtime=args.agent_reviewer_runtime,
                    reviewer_adapter=args.agent_reviewer_adapter,
                    reviewer_timeout_seconds=args.reviewer_timeout,
                )
                if args.governed
                else run_smoke(Path(tmp))
            )
        except PlannerRejectionError as exc:
            print(json.dumps(exc.report, indent=2, sort_keys=True))
            raise SystemExit(2) from exc
        print(
            json.dumps(
                {
                    "demo": report["demo"],
                    "no_external_calls": report["no_external_calls"],
                    "summary": report["summary"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        if report["summary"]["verdict"] != "passed":
            raise SystemExit(1)
    finally:
        if temp_context is not None:
            temp_context.cleanup()


if __name__ == "__main__":
    main()
