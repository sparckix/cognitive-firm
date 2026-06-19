from __future__ import annotations

import argparse
import html
import json
import os
import re
import shlex
import shutil
import sys
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.distribution.gitops import commit, stage_all  # noqa: E402
from cognitive_firm.distribution.installer import install  # noqa: E402
from cognitive_firm.distribution.manifest import load_manifest  # noqa: E402
from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request  # noqa: E402
from cognitive_firm.common.llm_runtime import (  # noqa: E402
    LLMRuntime,
    pick_model_for_tier,
)
from cognitive_firm.orchestration.agent_runtime_invocation import (  # noqa: E402
    agent_subprocess_env,
    build_agent_invocation_receipt,
    build_agent_invocation,
    infer_agent_adapter,
    infer_subscription_runtime_from_adapter,
    safe_command_for_receipt,
)
from cognitive_firm.orchestration.action_attestation import (  # noqa: E402
    create_action_attestation,
    digest_text,
    list_agent_invocation_audits,
)
from cognitive_firm.orchestration.governance_changes import (  # noqa: E402
    REQUIRED_INVARIANTS,
    tier_classification_invariant_check,
)
from cognitive_firm.orchestration.governed_run_recipes import (  # noqa: E402
    BoundedRunControlInput,
    GovernedMutationEvidenceInput,
    GovernedMutationRecipeInput,
    GovernedRunOperatorSummaryInput,
    PredictedMutationOutcomeInput,
    build_bounded_run_controls,
    build_governed_mutation_evidence_pack,
    build_governed_run_operator_summary,
    build_mutation_proof_request,
    build_predicted_mutation_outcome_link_request,
    governed_mutation_evidence_requirements,
    render_governed_run_operator_summary_markdown,
    validate_governed_mutation_evidence_pack,
)
from cognitive_firm.orchestration.work_discovery import discover_relevant_learning_events  # noqa: E402


@dataclass(frozen=True)
class EvolutionStep:
    step_id: str
    title: str
    change_kind: str
    target_ref: str
    rationale: str
    expected_behavior_change: str
    risk_summary: str
    rollback_plan: str
    work_kind: str
    work_payload: dict[str, Any]
    applied_relpath: str
    applied_text: str
    metric_baseline: float
    metric_post: float


@dataclass(frozen=True)
class PlannerSelection:
    steps: list[EvolutionStep]
    receipts: list[dict[str, Any]]
    evidence_refs: list[str]


@dataclass(frozen=True)
class ReviewerRuntimeConfig:
    runtime: str
    adapter: str = "auto"
    timeout_seconds: int = 600
    prompt_mode: str = "compact"


@dataclass(frozen=True)
class ReviewPosition:
    actor_id: str
    role_id: str
    position: str
    rationale: str
    evidence_refs: list[str]
    invocation: dict[str, Any] | None = None


class PlannerRejectionError(RuntimeError):
    def __init__(self, report: dict[str, Any]):
        super().__init__(str(report["summary"]["reason"]))
        self.report = report


class StepBlockedError(RuntimeError):
    def __init__(self, blocked_proposal: dict[str, Any], reason: str):
        super().__init__(reason)
        self.blocked_proposal = blocked_proposal
        self.reason = reason


STEPS = (
    EvolutionStep(
        step_id="evaluator_handoff",
        title="Clarify evaluator escalation handoff",
        change_kind="mandate_change",
        target_ref="org/mandates/evaluator.md",
        rationale="The org has recurring review work but no durable evaluator handoff rule.",
        expected_behavior_change="Ambiguous authority cases are routed to evaluation before execution.",
        risk_summary="Narrows execution authority; does not add capabilities.",
        rollback_plan="Revert the generated evaluator mandate note.",
        work_kind="org_diagnosis",
        work_payload={"symptom": "ambiguous authority handoff"},
        applied_relpath="org/mandates/evaluator.md",
        applied_text=(
            "# Evaluator Mandate\n\n"
            "When authority is ambiguous, evaluate the proposed action before execution. "
            "Record the evidence refs and escalation basis.\n"
        ),
        metric_baseline=3,
        metric_post=2,
    ),
    EvolutionStep(
        step_id="risk_guardian_role",
        title="Create risk guardian review role",
        change_kind="role_change",
        target_ref="org/roles/risk_guardian.yaml",
        rationale="Repeated structural proposals need an independent risk reviewer.",
        expected_behavior_change="High-risk proposals cite an independent risk review before approval.",
        risk_summary="Adds review burden but does not expand execution authority.",
        rollback_plan="Remove the generated risk guardian role file.",
        work_kind="role_design",
        work_payload={"missing_role": "independent risk review"},
        applied_relpath="org/roles/risk_guardian.yaml",
        applied_text=(
            "role_id: role.risk_guardian\n"
            "display_name: Risk Guardian\n"
            "purpose: Review proposed structural changes for authority, evidence, and rollback risk.\n"
            "authorized_paths:\n"
            "  - org/reviews/**\n"
        ),
        metric_baseline=2,
        metric_post=1,
    ),
    EvolutionStep(
        step_id="learning_review_cadence",
        title="Schedule learning review cadence",
        change_kind="learning_policy_change",
        target_ref="org/policies/learning-review.md",
        rationale="Accepted learning should be revisited instead of remaining permanently active.",
        expected_behavior_change="Each approved structural learning event gets a routine review.",
        risk_summary="Adds a review checkpoint; does not activate any learned policy automatically.",
        rollback_plan="Remove the generated learning-review policy note.",
        work_kind="learning_cadence",
        work_payload={"gap": "no routine review for accepted learning"},
        applied_relpath="org/policies/learning-review.md",
        applied_text=(
            "# Learning Review Policy\n\n"
            "Approved structural learning events should carry a routine review. "
            "A stale learning event can be retired after review.\n"
        ),
        metric_baseline=1,
        metric_post=0,
    ),
)


GENERATED_FIXTURE_TOPICS = (
    {
        "slug": "evidence_ref_handoff",
        "title": "Require evidence refs on handoff",
        "change_kind": "mandate_change",
        "target_prefix": "org/mandates/generated_evidence_ref_handoff",
        "work_kind": "org_diagnosis",
        "work_payload": {"gap": "handoff without source references"},
        "rationale": "Longer-running org evolution needs handoffs that preserve source refs.",
        "expected": "Future handoffs cite evidence before downstream review starts.",
        "risk": "Narrows handoff completion criteria; grants no new authority.",
        "rollback": "Remove the generated evidence-ref handoff mandate note.",
        "body": (
            "# Evidence Ref Handoff\n\n"
            "When a role hands off work, include the source refs that justify the "
            "handoff and the unresolved evidence gaps that remain.\n"
        ),
    },
    {
        "slug": "proposal_batch_review",
        "title": "Add proposal batch review routine",
        "change_kind": "learning_policy_change",
        "target_prefix": "org/policies/generated_proposal_batch_review",
        "work_kind": "learning_cadence",
        "work_payload": {"gap": "no batch review for repeated proposals"},
        "rationale": "Repeated proposal patterns should be reviewed as a group, not only one by one.",
        "expected": "Recurring proposal patterns create a batch review note before policy promotion.",
        "risk": "Adds review grouping; does not approve any policy automatically.",
        "rollback": "Remove the generated proposal batch review policy note.",
        "body": (
            "# Proposal Batch Review\n\n"
            "When similar governance proposals repeat, group them for review before "
            "promoting a route or mandate pattern.\n"
        ),
    },
    {
        "slug": "source_gap_triage",
        "title": "Create source gap triage role",
        "change_kind": "role_change",
        "target_prefix": "org/roles/generated_source_gap_triage",
        "work_kind": "role_design",
        "work_payload": {"missing_role": "source gap triage"},
        "rationale": "Evidence gaps need a bounded reviewer before they become blockers.",
        "expected": "Source gaps are triaged into repair, escalation, or deferral before execution.",
        "risk": "Adds a narrow review role; does not add external tools or execution authority.",
        "rollback": "Remove the generated source gap triage role file.",
        "body": (
            "role_id: role.generated_source_gap_triage_{index}\n"
            "display_name: Source Gap Triage {index}\n"
            "purpose: Triage evidence gaps before they block or distort future work.\n"
            "authorized_paths:\n"
            "  - org/reviews/**\n"
            "  - org/policies/**\n"
        ),
    },
    {
        "slug": "outcome_window",
        "title": "Add outcome measurement window",
        "change_kind": "learning_policy_change",
        "target_prefix": "org/policies/generated_outcome_window",
        "work_kind": "learning_cadence",
        "work_payload": {"gap": "no explicit outcome window"},
        "rationale": "Approved changes need a bounded window for outcome interpretation.",
        "expected": "Outcome links record the review window before a verdict is reused.",
        "risk": "Adds measurement discipline; does not make metrics authoritative by themselves.",
        "rollback": "Remove the generated outcome window policy note.",
        "body": (
            "# Outcome Measurement Window\n\n"
            "When an approved change creates an outcome link, record the review "
            "window before reusing the verdict as evidence.\n"
        ),
    },
    {
        "slug": "abstention_routing",
        "title": "Clarify abstention routing",
        "change_kind": "mandate_change",
        "target_prefix": "org/mandates/generated_abstention_routing",
        "work_kind": "org_diagnosis",
        "work_payload": {"gap": "unclear abstention route"},
        "rationale": "Capability gaps should route cleanly instead of being treated as ordinary failure.",
        "expected": "Roles can abstain with a typed reason and route target for reassignment or review.",
        "risk": "Clarifies non-execution; does not expand autonomy.",
        "rollback": "Remove the generated abstention routing mandate note.",
        "body": (
            "# Abstention Routing\n\n"
            "When a role lacks authority, evidence, tools, budget, or safety context, "
            "record a typed abstention and route it before retrying execution.\n"
        ),
    },
    {
        "slug": "routine_retirement",
        "title": "Add routine retirement check",
        "change_kind": "learning_policy_change",
        "target_prefix": "org/policies/generated_routine_retirement",
        "work_kind": "learning_cadence",
        "work_payload": {"gap": "stale routines remain active"},
        "rationale": "Longer-running organizations need explicit retirement pressure for stale routines.",
        "expected": "Stale approved routines create retirement review before future dispatch depends on them.",
        "risk": "Adds a review gate; does not retire learning without approval.",
        "rollback": "Remove the generated routine retirement policy note.",
        "body": (
            "# Routine Retirement Check\n\n"
            "Before stale guidance keeps affecting dispatch, schedule a review to "
            "reaffirm, amend, or retire the routine.\n"
        ),
    },
    {
        "slug": "delegation_depth_note",
        "title": "Clarify delegation depth note",
        "change_kind": "mandate_change",
        "target_prefix": "org/mandates/generated_delegation_depth_note",
        "work_kind": "org_diagnosis",
        "work_payload": {"gap": "delegation depth not recorded"},
        "rationale": "Recursive delegation should preserve depth and budget context for review.",
        "expected": "Delegated work records depth and budget before another delegation layer starts.",
        "risk": "Adds observability; does not authorize deeper recursion.",
        "rollback": "Remove the generated delegation depth mandate note.",
        "body": (
            "# Delegation Depth Note\n\n"
            "When work is delegated recursively, record the delegation depth, budget "
            "remaining, and reason another layer is warranted.\n"
        ),
    },
)


def _fixture_evolution_steps(iterations: int) -> list[EvolutionStep]:
    count = max(0, iterations)
    steps = list(STEPS[: min(count, len(STEPS))])
    for index in range(len(steps) + 1, count + 1):
        topic = GENERATED_FIXTURE_TOPICS[(index - len(STEPS) - 1) % len(GENERATED_FIXTURE_TOPICS)]
        step_id = f"generated_{index:02d}_{topic['slug']}"
        suffix = ".yaml" if topic["change_kind"] == "role_change" else ".md"
        body = str(topic["body"]).format(index=index)
        steps.append(
            EvolutionStep(
                step_id=step_id,
                title=f"{topic['title']} {index}",
                change_kind=str(topic["change_kind"]),
                target_ref=f"{topic['target_prefix']}_{index:02d}{suffix}",
                rationale=str(topic["rationale"]),
                expected_behavior_change=str(topic["expected"]),
                risk_summary=str(topic["risk"]),
                rollback_plan=str(topic["rollback"]),
                work_kind=str(topic["work_kind"]),
                work_payload={**dict(topic["work_payload"]), "generated_iteration": index},
                applied_relpath=f"{topic['target_prefix']}_{index:02d}{suffix}",
                applied_text=body,
                metric_baseline=float(max(1, count - index + 1)),
                metric_post=float(max(0, count - index)),
            )
        )
    return steps


def run_demo(
    root: Path,
    *,
    iterations: int = 3,
    max_budget_units: int | None = None,
    stop_file: Path | None = None,
    planner_transport: str = "fixture",
    model_id: str | None = None,
    planner_command: str | None = None,
    planner_runtime: str | None = None,
    planner_adapter: str = "auto",
    planner_prompt_mode: str = "full",
    planner_timeout_seconds: int = 600,
    reviewer_runtime: str | None = None,
    reviewer_adapter: str = "auto",
    reviewer_timeout_seconds: int | None = None,
    reviewer_prompt_mode: str = "compact",
    workload_feedback: str = "score_totals",
    workload_executor_runtime: str | None = None,
    workload_executor_adapter: str = "auto",
    workload_executor_limit: int = 0,
    workload_executor_timeout_seconds: int = 180,
    replace_existing: bool = False,
) -> dict[str, Any]:
    if iterations < 0:
        raise ValueError("iterations must be non-negative")
    if max_budget_units is not None and max_budget_units < 0:
        raise ValueError("max_budget_units must be non-negative")
    if workload_feedback not in {"score_totals", "withheld"}:
        raise ValueError("workload_feedback must be score_totals or withheld")
    if workload_executor_limit < 0:
        raise ValueError("workload_executor_limit must be non-negative")
    if workload_executor_timeout_seconds <= 0:
        raise ValueError("workload_executor_timeout_seconds must be positive")
    _validate_workload_scoring_isolation(
        planner_transport=planner_transport,
        planner_runtime=planner_runtime,
        planner_command=planner_command,
        reviewer_runtime=reviewer_runtime,
        workload_executor_runtime=workload_executor_runtime,
    )
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    demo_firm = root / "demo-firm"
    if demo_firm.exists():
        if replace_existing:
            shutil.rmtree(demo_firm)
        else:
            raise RuntimeError(
                f"{demo_firm} already exists. Choose a fresh --workdir or pass "
                "--replace-existing to delete and recreate that generated demo firm."
            )
    manifest = load_manifest(ROOT / "distro" / "starter-firm" / "package.yaml")
    receipt = install(manifest, ROOT / "distro" / "starter-firm", demo_firm)
    _seed_demo_overlay(demo_firm)
    stage_all(demo_firm)
    commit(demo_firm, "seed self-evolving organization demo overlay")

    config = _demo_kernel_config(demo_firm)
    _define_demo_unit(config)
    workload_probe = _run_workload_probe_harness(
        demo_firm,
        config=config,
        feedback_visibility=workload_feedback,
        workload_executor_runtime=workload_executor_runtime,
        workload_executor_adapter=workload_executor_adapter,
        workload_executor_limit=workload_executor_limit,
        workload_executor_timeout_seconds=workload_executor_timeout_seconds,
    )
    stage_all(demo_firm)
    commit(demo_firm, "record workload probe receipts")
    selection = _select_evolution_plan(
        demo_firm,
        iterations=iterations,
        planner_transport=planner_transport,
        model_id=model_id,
        planner_command=planner_command,
        planner_runtime=planner_runtime,
        planner_adapter=planner_adapter,
        planner_prompt_mode=planner_prompt_mode,
        planner_timeout_seconds=planner_timeout_seconds,
    )
    selection = _selection_with_workload_probe_evidence(selection, workload_probe)
    return _run_governed_evolution(
        demo_firm=demo_firm,
        config=config,
        selection=selection,
        iterations_requested=iterations,
        max_budget_units=max_budget_units,
        stop_file=stop_file,
        planner_transport=planner_transport,
        starter_install=receipt.as_dict(),
        extra_report_fields={"workload_probe": workload_probe},
        reviewer_runtime=(
            ReviewerRuntimeConfig(
                runtime=reviewer_runtime,
                adapter=reviewer_adapter,
                timeout_seconds=reviewer_timeout_seconds or planner_timeout_seconds,
                prompt_mode=reviewer_prompt_mode,
            )
            if reviewer_runtime
            else None
        ),
    )


def run_feedback_comparison(
    root: Path,
    *,
    iterations: int = 3,
    max_budget_units: int | None = None,
    planner_transport: str = "fixture",
    model_id: str | None = None,
    planner_command: str | None = None,
    planner_runtime: str | None = None,
    planner_adapter: str = "auto",
    planner_prompt_mode: str = "full",
    planner_timeout_seconds: int = 600,
    reviewer_runtime: str | None = None,
    reviewer_adapter: str = "auto",
    reviewer_timeout_seconds: int | None = None,
    reviewer_prompt_mode: str = "compact",
    workload_executor_runtime: str | None = None,
    workload_executor_adapter: str = "auto",
    workload_executor_limit: int = 0,
    workload_executor_timeout_seconds: int = 180,
    replace_existing: bool = False,
) -> dict[str, Any]:
    """Run score-feedback and no-feedback demo arms through the same harness.

    This is intentionally a comparison wrapper over `run_demo`, not a new
    simulation path. Operator-side scores exist in both arms; only firm-visible
    feedback changes.
    """

    root = Path(root)
    if root.exists() and replace_existing:
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    score_root = root / "score-feedback"
    withheld_root = root / "no-feedback"
    if not replace_existing and (score_root.exists() or withheld_root.exists()):
        raise RuntimeError(
            f"{root} already contains comparison arms. Choose a fresh --workdir "
            "or pass --replace-existing."
        )
    score_report = run_demo(
        score_root,
        iterations=iterations,
        max_budget_units=max_budget_units,
        planner_transport=planner_transport,
        model_id=model_id,
        planner_command=planner_command,
        planner_runtime=planner_runtime,
        planner_adapter=planner_adapter,
        planner_prompt_mode=planner_prompt_mode,
        planner_timeout_seconds=planner_timeout_seconds,
        reviewer_runtime=reviewer_runtime,
        reviewer_adapter=reviewer_adapter,
        reviewer_timeout_seconds=reviewer_timeout_seconds,
        reviewer_prompt_mode=reviewer_prompt_mode,
        workload_feedback="score_totals",
        workload_executor_runtime=workload_executor_runtime,
        workload_executor_adapter=workload_executor_adapter,
        workload_executor_limit=workload_executor_limit,
        workload_executor_timeout_seconds=workload_executor_timeout_seconds,
    )
    withheld_report = run_demo(
        withheld_root,
        iterations=iterations,
        max_budget_units=max_budget_units,
        planner_transport=planner_transport,
        model_id=model_id,
        planner_command=planner_command,
        planner_runtime=planner_runtime,
        planner_adapter=planner_adapter,
        planner_prompt_mode=planner_prompt_mode,
        planner_timeout_seconds=planner_timeout_seconds,
        reviewer_runtime=reviewer_runtime,
        reviewer_adapter=reviewer_adapter,
        reviewer_timeout_seconds=reviewer_timeout_seconds,
        reviewer_prompt_mode=reviewer_prompt_mode,
        workload_feedback="withheld",
        workload_executor_runtime=workload_executor_runtime,
        workload_executor_adapter=workload_executor_adapter,
        workload_executor_limit=workload_executor_limit,
        workload_executor_timeout_seconds=workload_executor_timeout_seconds,
    )
    comparison = _build_feedback_comparison_report(
        root=root,
        score_root=score_root,
        withheld_root=withheld_root,
        score_report=score_report,
        withheld_report=withheld_report,
        iterations=iterations,
        max_budget_units=max_budget_units,
    )
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "self-evolving-feedback-comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports_dir / "self-evolving-feedback-comparison.md").write_text(
        _render_feedback_comparison_markdown(comparison),
        encoding="utf-8",
    )
    comparison_html = _render_feedback_comparison_html(comparison)
    (reports_dir / "self-evolving-feedback-comparison.html").write_text(
        comparison_html,
        encoding="utf-8",
    )
    (root / "index.html").write_text(comparison_html, encoding="utf-8")
    return comparison


def _build_feedback_comparison_report(
    *,
    root: Path,
    score_root: Path,
    withheld_root: Path,
    score_report: dict[str, Any],
    withheld_report: dict[str, Any],
    iterations: int,
    max_budget_units: int | None,
) -> dict[str, Any]:
    score_summary = score_report["summary"]
    withheld_summary = withheld_report["summary"]
    score_hidden = _operator_hidden_score_summary(score_root)
    withheld_hidden = _operator_hidden_score_summary(withheld_root)
    return {
        "schema": "self_evolving_feedback_comparison.v1",
        "demo": "self_evolving_org_feedback_comparison",
        "no_external_calls": bool(
            score_report.get("no_external_calls")
            and withheld_report.get("no_external_calls")
        ),
        "planner_transport": score_report.get("planner_transport"),
        "workdir": str(root),
        "arms": {
            "score_feedback": _feedback_arm_summary(
                score_report,
                arm_label="score_feedback",
                hidden_score_summary=score_hidden,
            ),
            "no_feedback": _feedback_arm_summary(
                withheld_report,
                arm_label="no_feedback",
                hidden_score_summary=withheld_hidden,
            ),
        },
        "comparison": {
            "iterations_requested": iterations,
            "budget_units_total": max_budget_units,
            "score_feedback_firm_received_scores": score_summary[
                "workload_firm_received_scores"
            ],
            "no_feedback_firm_received_scores": withheld_summary[
                "workload_firm_received_scores"
            ],
            "operator_hidden_total_scores_equal": (
                score_hidden["total_score"] == withheld_hidden["total_score"]
            ),
            "score_feedback_visible_capability": score_summary[
                "workload_capability_score_per_budget_unit"
            ],
            "no_feedback_visible_capability": withheld_summary[
                "workload_capability_score_per_budget_unit"
            ],
            "score_feedback_operator_score_per_budget": score_hidden[
                "score_per_budget_unit"
            ],
            "no_feedback_operator_score_per_budget": withheld_hidden[
                "score_per_budget_unit"
            ],
            "score_feedback_hidden_score_per_budget": score_hidden[
                "score_per_budget_unit"
            ],
            "no_feedback_hidden_score_per_budget": withheld_hidden[
                "score_per_budget_unit"
            ],
            "score_feedback_mutations": score_summary["approved"],
            "no_feedback_mutations": withheld_summary["approved"],
            "score_feedback_blocked_proposals": score_summary["blocked_proposals"],
            "no_feedback_blocked_proposals": withheld_summary["blocked_proposals"],
        },
        "interpretation": [
            "Both arms run the same kernel-native governed evolution harness.",
            "The operator scores both arms on the same hidden workload axis.",
            "Only the score-feedback arm writes score totals into firm-visible state.",
            "Use this comparison to inspect whether self-organization stays anchored to workload evidence or drifts toward self-referential process.",
        ],
        "artifacts": [
            {
                "label": "score_feedback_viewer",
                "path": "score-feedback/demo-firm/reports/self-evolving-org-company-state.html",
            },
            {
                "label": "score_feedback_report",
                "path": "score-feedback/demo-firm/reports/self-evolving-org-demo.json",
            },
            {
                "label": "no_feedback_viewer",
                "path": "no-feedback/demo-firm/reports/self-evolving-org-company-state.html",
            },
            {
                "label": "no_feedback_report",
                "path": "no-feedback/demo-firm/reports/self-evolving-org-demo.json",
            },
            {
                "label": "comparison_markdown",
                "path": "reports/self-evolving-feedback-comparison.md",
            },
            {
                "label": "comparison_html",
                "path": "reports/self-evolving-feedback-comparison.html",
            },
            {
                "label": "comparison_json",
                "path": "reports/self-evolving-feedback-comparison.json",
            },
        ],
    }


def _feedback_arm_summary(
    report: dict[str, Any],
    *,
    arm_label: str,
    hidden_score_summary: dict[str, Any],
) -> dict[str, Any]:
    summary = report["summary"]
    probe_summary = report["workload_probe"]["summary"]
    return {
        "arm": arm_label,
        "firm_visible_feedback": summary["workload_feedback_visibility"],
        "firm_received_scores": summary["workload_firm_received_scores"],
        "visible_capability_score_per_budget_unit": summary[
            "workload_capability_score_per_budget_unit"
        ],
        "operator_hidden_total_score": hidden_score_summary["total_score"],
        "operator_score_per_budget_unit": hidden_score_summary[
            "score_per_budget_unit"
        ],
        "operator_hidden_score_per_budget_unit": hidden_score_summary[
            "score_per_budget_unit"
        ],
        "packets": summary["workload_probe_packets"],
        "budget_units": probe_summary["total_budget_units"],
        "iterations_run": report["iterations_run"],
        "approved_mutations": summary["approved"],
        "blocked_proposals": summary["blocked_proposals"],
        "mutation_proofs_valid": summary["mutation_proofs_valid"],
        "mutation_proof_replay_valid": summary["mutation_proof_replay_valid"],
        "viewer_path": (
            f"{arm_label.replace('_', '-')}/demo-firm/reports/"
            "self-evolving-org-company-state.html"
        ),
    }


def _operator_hidden_score_summary(run_root: Path) -> dict[str, Any]:
    scorecard_dir = run_root / "operator-only" / "workload-probes"
    scorecards = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(scorecard_dir.glob("*.scorecard.json"))
    ]
    total_score = sum(float(row.get("score") or 0) for row in scorecards)
    total_budget = sum(float(row.get("budget_units") or 0) for row in scorecards)
    total_max = sum(float(row.get("max_score") or 0) for row in scorecards)
    score_per_budget = round(total_score / total_budget, 4) if total_budget else None
    average_percent = round(total_score / total_max, 4) if total_max else None
    normalized_total = int(total_score) if total_score.is_integer() else round(total_score, 4)
    return {
        "scorecards": len(scorecards),
        "total_score": normalized_total,
        "total_budget_units": int(total_budget) if total_budget.is_integer() else total_budget,
        "total_max_score": int(total_max) if total_max.is_integer() else round(total_max, 4),
        "score_per_budget_unit": score_per_budget,
        "average_percent": average_percent,
        "scorecard_dir": str(scorecard_dir),
    }


def _render_feedback_comparison_markdown(comparison: dict[str, Any]) -> str:
    arms = comparison["arms"]
    rows = []
    for label in ("score_feedback", "no_feedback"):
        arm = arms[label]
        rows.append(
            " | ".join(
                [
                    _md(label),
                    _md(arm["firm_visible_feedback"]),
                    _md(str(arm["firm_received_scores"]).lower()),
                    _md(str(arm["visible_capability_score_per_budget_unit"])),
                    _md(str(arm["operator_score_per_budget_unit"])),
                    _md(str(arm["approved_mutations"])),
                    _md(str(arm["blocked_proposals"])),
                ]
            )
        )
    artifact_lines = [
        f"- `{artifact['label']}`: `{artifact['path']}`"
        for artifact in comparison["artifacts"]
    ]
    interpretation = "\n".join(f"- {line}" for line in comparison["interpretation"])
    return "\n".join(
        [
            "# Self-Evolving Organization Feedback Comparison",
            "",
            "This report runs the same kernel-native self-evolving organization demo twice.",
            "The operator scores both arms; only one arm exposes score totals to the firm.",
            "",
            "## Arms",
            "",
            "| Arm | Firm-visible feedback | Firm received scores | Visible capability | Operator score/budget | Approved mutations | Blocked proposals |",
            "| --- | --- | --- | --- | --- | --- | --- |",
            *[f"| {row} |" for row in rows],
            "",
            "## Comparison",
            "",
            f"- Operator hidden totals equal: `{str(comparison['comparison']['operator_hidden_total_scores_equal']).lower()}`",
            f"- Score-feedback visible capability: `{comparison['comparison']['score_feedback_visible_capability']}`",
            f"- No-feedback visible capability: `{comparison['comparison']['no_feedback_visible_capability']}`",
            "",
            "## Interpretation",
            "",
            interpretation,
            "",
            "## Artifacts",
            "",
            *artifact_lines,
            "",
        ]
    )


def _render_feedback_comparison_html(comparison: dict[str, Any]) -> str:
    arms = comparison["arms"]
    score_arm = arms["score_feedback"]
    no_feedback_arm = arms["no_feedback"]

    def _fmt(value: Any) -> str:
        if value is None:
            return "hidden"
        if value is True:
            return "yes"
        if value is False:
            return "no"
        return str(value)

    if comparison.get("no_external_calls"):
        agent_mode_sentence = (
            "Deterministic fixture workers executed the same kernel-native path "
            "without external model calls."
        )
    elif str(comparison.get("planner_transport") or "").endswith("subscription_cli"):
        agent_mode_sentence = (
            "Live subscription/local agent CLIs planned or executed work while "
            "separate evaluator, risk, and learning offices recorded review evidence."
        )
    else:
        agent_mode_sentence = (
            "Live model/runtime calls planned or executed work while the kernel "
            "kept the governance and proof path unchanged."
        )

    score_story = (
        f"The score-feedback firm saw workload score totals, completed "
        f"{score_arm.get('iterations_run', 0)} governed tick(s), and approved "
        f"{score_arm.get('approved_mutations', 0)} structural mutation(s)."
    )
    no_feedback_story = (
        f"The no-feedback firm did not see score totals. In this reconstructed run, "
        f"it completed {no_feedback_arm.get('iterations_run', 0)} governed tick(s), "
        f"approved {no_feedback_arm.get('approved_mutations', 0)} mutation(s), and "
        f"blocked {no_feedback_arm.get('blocked_proposals', 0)} proposal(s)."
    )
    if not comparison.get("ex_post_reconstruction"):
        no_feedback_story = (
            f"The no-feedback firm did not see score totals. It completed "
            f"{no_feedback_arm.get('iterations_run', 0)} governed tick(s), approved "
            f"{no_feedback_arm.get('approved_mutations', 0)} mutation(s), and blocked "
            f"{no_feedback_arm.get('blocked_proposals', 0)} proposal(s)."
        )
    score_anchor_sentence = (
        "It saw workload score totals, so its structural proposals could be "
        f"judged against visible workload "
        f"performance. In this run it approved "
        f"{score_arm.get('approved_mutations', 0)} mutation(s) and blocked "
        f"{score_arm.get('blocked_proposals', 0)} proposal(s)."
    )
    no_feedback_anchor_sentence = (
        "It had to self-organize without seeing score totals. "
        f"The operator still scored it on the same hidden axis for comparison. "
        f"In this run it approved {no_feedback_arm.get('approved_mutations', 0)} "
        f"mutation(s) and blocked {no_feedback_arm.get('blocked_proposals', 0)} "
        f"proposal(s)."
    )

    rows = []
    for label in ("score_feedback", "no_feedback"):
        arm = arms[label]
        arm_name = "Score feedback" if label == "score_feedback" else "No feedback"
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(arm_name)}</strong></td>"
            f"<td>{html.escape(_fmt(arm['firm_visible_feedback']))}</td>"
            f"<td>{html.escape(_fmt(arm['firm_received_scores']))}</td>"
            f"<td>{html.escape(_fmt(arm['visible_capability_score_per_budget_unit']))}</td>"
            f"<td>{html.escape(_fmt(arm['operator_score_per_budget_unit']))}</td>"
            f"<td>{html.escape(_fmt(arm['approved_mutations']))}</td>"
            f"<td>{html.escape(_fmt(arm['blocked_proposals']))}</td>"
            "</tr>"
        )
    interpretation_items = "\n".join(
        f"<li>{html.escape(line)}</li>" for line in comparison["interpretation"]
    )
    score_href = "../score-feedback/demo-firm/reports/self-evolving-org-company-state.html"
    withheld_href = "../no-feedback/demo-firm/reports/self-evolving-org-company-state.html"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Self-Evolving Organization Feedback Comparison</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0e1013;
      --panel: #171a1f;
      --panel-2: #20242b;
      --text: #f5f1e8;
      --muted: #b8b1a3;
      --line: #3a3f48;
      --accent: #d7b46a;
      --good: #8ed7a5;
      --warn: #efb071;
      --bad: #e48484;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      background: radial-gradient(circle at 50% -20%, #30333a 0, #121418 42%, var(--bg) 100%);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      min-height: 42vh;
      display: grid;
      align-content: end;
      padding: 48px clamp(24px, 6vw, 80px);
      border-bottom: 1px solid var(--line);
      background:
        linear-gradient(90deg, rgba(14,16,19,.96), rgba(14,16,19,.72)),
        repeating-linear-gradient(90deg, transparent 0 38px, rgba(255,255,255,.035) 38px 39px);
    }}
    h1 {{
      max-width: 980px;
      margin: 0;
      font-size: clamp(2.25rem, 6vw, 5.25rem);
      line-height: .95;
      letter-spacing: 0;
    }}
    .sub {{
      max-width: 820px;
      margin: 24px 0 0;
      color: var(--muted);
      font-size: 1.08rem;
      line-height: 1.65;
    }}
    main {{
      padding: 34px clamp(18px, 4vw, 56px) 56px;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 1.25rem;
      letter-spacing: 0;
    }}
    p {{
      line-height: 1.58;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 18px;
      margin-bottom: 24px;
    }}
    .panel {{
      background: color-mix(in srgb, var(--panel) 92%, black);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
    .plain {{
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(280px, .95fr);
      gap: 18px;
      margin-bottom: 24px;
    }}
    .story {{
      background: #f5f1e8;
      color: #15130f;
      border-radius: 8px;
      padding: 20px;
      border: 1px solid rgba(215, 180, 106, .45);
    }}
    .story p {{
      color: #4c473d;
      margin: 0 0 12px;
    }}
    .story strong {{
      color: #15130f;
    }}
    .compare-cards {{
      display: grid;
      gap: 12px;
    }}
    .compare-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: var(--panel);
    }}
    .compare-card[data-state="applied"] {{
      border-left: 5px solid var(--good);
    }}
    .compare-card[data-state="blocked"] {{
      border-left: 5px solid var(--warn);
    }}
    .value {{
      display: block;
      margin-top: 8px;
      font-size: 1.8rem;
      line-height: 1;
      color: var(--text);
      font-weight: 750;
    }}
    .kicker {{
      color: var(--accent);
      font-size: .78rem;
      text-transform: uppercase;
      letter-spacing: .12em;
      margin-bottom: 10px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 8px;
      background: var(--panel);
      border: 1px solid var(--line);
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: .94rem;
    }}
    th {{
      color: var(--muted);
      background: var(--panel-2);
      font-weight: 650;
    }}
    tr:last-child td {{
      border-bottom: 0;
    }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin: 20px 0 28px;
    }}
    a.button {{
      color: #15130f;
      background: var(--accent);
      padding: 11px 14px;
      border-radius: 6px;
      text-decoration: none;
      font-weight: 700;
    }}
    .frames {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 18px;
      margin-top: 20px;
    }}
    iframe {{
      width: 100%;
      height: 680px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    code {{
      color: var(--good);
    }}
    .note {{
      color: var(--muted);
      font-size: .94rem;
    }}
    @media (max-width: 900px) {{
      .plain {{
        grid-template-columns: 1fr;
      }}
      iframe {{
        height: 560px;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="kicker">Cognitive-firm demo comparison</div>
    <h1>Does feedback anchor self-organization?</h1>
    <p class="sub">Two identical firms run through the same kernel-native governed evolution path. The operator scores both on the hidden coordination workload. Only one firm sees score totals; the other must self-organize without feedback.</p>
  </header>
  <main>
    <section class="plain">
      <div class="story">
        <h2>What happened in simple terms</h2>
        <p><strong>The setup is Severance-inspired, but fictional and generic.</strong> The agents work inside a sealed coordination floor: they see concrete packets, receipts, roles, and local feedback, but not the operator-only scoring rubric.</p>
        <p><strong>The firm is not choosing an industry.</strong> It runs a neutral Coordination Desk with twenty concrete packets: route requests, resolve conflicts, classify records, reuse prior learning, and retire stale routines.</p>
        <p><strong>The score-feedback arm had an anchor.</strong> {html.escape(score_anchor_sentence)}</p>
        <p><strong>The no-feedback arm had less feedback.</strong> {html.escape(no_feedback_anchor_sentence)}</p>
        <p class="note">The packets are fixed in this version. More iterations mean more governed mutation attempts against the same benchmark, not randomly generated new work. Use 1-3 iterations for the v1 demo; longer runs should add held-out or operator-generated packets to avoid overfitting to the visible packet set.</p>
      </div>
      <div class="compare-cards">
        <div class="compare-card" data-state="applied">
          <div class="kicker">Score-feedback result</div>
          <p>{html.escape(score_story)}</p>
          <span class="value">{html.escape(_fmt(score_arm.get("visible_capability_score_per_budget_unit")))}</span>
          <div class="note">visible score per budget</div>
        </div>
        <div class="compare-card" data-state="blocked">
          <div class="kicker">No-feedback result</div>
          <p>{html.escape(no_feedback_story)}</p>
          <span class="value">{html.escape(_fmt(no_feedback_arm.get("operator_score_per_budget_unit")))}</span>
          <div class="note">operator-only hidden score per budget</div>
        </div>
      </div>
    </section>
    <section class="grid">
      <div class="panel">
        <div class="kicker">What the agents did</div>
        <p>{html.escape(agent_mode_sentence)}</p>
      </div>
      <div class="panel">
        <div class="kicker">What the operator hid</div>
        <p>Like a sealed-floor work game, the hidden rubric and score detail stay outside firm-visible state. The firm sees packets and, depending on the arm, either score totals or no scores.</p>
      </div>
      <div class="panel">
        <div class="kicker">What counts as improvement</div>
        <p>Only reviewed state changes that can affect future work count: policies, mandates, learning units, outcome links, routine reviews, and git receipts.</p>
      </div>
    </section>
    <table>
      <thead>
        <tr>
          <th>Arm</th>
          <th>Firm-visible feedback</th>
          <th>Received scores</th>
          <th>Visible capability</th>
          <th>Operator score/budget</th>
          <th>Approved mutations</th>
          <th>Blocked proposals</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    <section class="panel" style="margin-top: 20px;">
      <div class="kicker">Raw interpretation</div>
      <ul>{interpretation_items}</ul>
      <p>Comparison JSON: <code>reports/self-evolving-feedback-comparison.json</code></p>
    </section>
    <div class="links">
      <a class="button" href="{score_href}">Open score-feedback firm</a>
      <a class="button" href="{withheld_href}">Open no-feedback firm</a>
      <a class="button" href="self-evolving-feedback-comparison.md">Open markdown report</a>
    </div>
    <section class="frames">
      <div>
        <div class="kicker">Score-feedback firm</div>
        <iframe src="{score_href}" title="Score-feedback firm"></iframe>
      </div>
      <div>
        <div class="kicker">No-feedback firm</div>
        <iframe src="{withheld_href}" title="No-feedback firm"></iframe>
      </div>
    </section>
  </main>
</body>
</html>
"""


def _demo_kernel_config(demo_firm: Path) -> KernelServiceConfig:
    return KernelServiceConfig(
        org_dir=demo_firm / "org",
        project_root=demo_firm,
        transition_log=demo_firm / "cognitive_firm_workspace" / "transitions.jsonl",
        kernel_events_log=demo_firm / "cognitive_firm_workspace" / "transitions.jsonl",
        work_items_log=demo_firm / "org" / "work_items" / "work_items.jsonl",
        operating_units_log=demo_firm / "org" / "operating_units" / "operating_units.jsonl",
        learning_events_log=demo_firm / "org" / "learning_events" / "learning_events.jsonl",
        learning_encounters_log=demo_firm / "org" / "learning_events" / "learning_encounters.jsonl",
        outcome_links_log=demo_firm / "org" / "outcome_links" / "outcome_links.jsonl",
        routine_reviews_log=demo_firm / "org" / "routine_reviews" / "routine_reviews.jsonl",
        accountability_cases_log=demo_firm / "org" / "accountability" / "accountability_cases.jsonl",
        human_work_log=demo_firm / "org" / "human_work" / "human_work.jsonl",
        leases_log=demo_firm / "org" / "leases" / "leases.jsonl",
        action_attestation_log=demo_firm
        / "org"
        / "action_attestations"
        / "action_attestations.jsonl",
        formal_verification_log=demo_firm
        / "org"
        / "action_attestations"
        / "formal_verifications.jsonl",
        actor_identity_log=demo_firm / "org" / "actors" / "actors.jsonl",
        actor_membership_log=demo_firm / "org" / "actors" / "memberships.jsonl",
        trace_events_log=demo_firm / "org" / "multi_agent_traces" / "trace_events.jsonl",
        attribution_packets_log=demo_firm
        / "org"
        / "multi_agent_traces"
        / "attribution_packets.jsonl",
        phase_execution_log=demo_firm / "org" / "phase_execution" / "phase_execution.jsonl",
        capability_signals_log=demo_firm
        / "org"
        / "capability_signals"
        / "capability_signals.jsonl",
        decision_aggregation_log=demo_firm
        / "org"
        / "decision_aggregation"
        / "decision_aggregation_cases.jsonl",
    )


def _validate_workload_scoring_isolation(
    *,
    planner_transport: str,
    planner_runtime: str | None,
    planner_command: str | None,
    reviewer_runtime: str | None,
    workload_executor_runtime: str | None = None,
) -> None:
    """Fail closed when live agents could read operator-only scoring state."""

    if planner_transport != "subscription_cli" and not workload_executor_runtime:
        return
    if os.environ.get("COGNITIVE_FIRM_CODEX_BYPASS_SANDBOX"):
        raise ValueError(
            "COGNITIVE_FIRM_CODEX_BYPASS_SANDBOX disables the isolation needed "
            "for hidden workload scoring"
        )
    if os.environ.get("COGNITIVE_FIRM_CLAUDE_ADD_DIRS"):
        raise ValueError(
            "COGNITIVE_FIRM_CLAUDE_ADD_DIRS grants extra read roots and is not "
            "allowed for the hidden-score workload demo"
        )
    checked_runtimes = [
        item
        for item in [planner_runtime, reviewer_runtime, workload_executor_runtime]
        if item
    ]
    unknown_runtimes = [
        item
        for item in checked_runtimes
        if Path(item).name.lower() not in {"codex", "claude"} and not Path(item).exists()
    ]
    if unknown_runtimes:
        raise ValueError(
            "live workload demo subscription runtimes must be known isolated "
            f"runtimes (codex or claude), got: {', '.join(unknown_runtimes)}"
        )


def _run_governed_evolution(
    *,
    demo_firm: Path,
    config: KernelServiceConfig,
    selection: PlannerSelection,
    iterations_requested: int,
    max_budget_units: int | None,
    stop_file: Path | None,
    planner_transport: str,
    starter_install: dict[str, Any],
    no_external_calls: bool | None = None,
    extra_report_fields: dict[str, Any] | None = None,
    reviewer_runtime: ReviewerRuntimeConfig | None = None,
) -> dict[str, Any]:
    selected_steps = selection.steps
    if selection.receipts:
        stage_all(demo_firm)
        commit(demo_firm, "record self-evolving planner receipts")
    applied_steps: list[dict[str, Any]] = []
    budget_units_consumed = 0
    live_snapshots_written = 0
    stop_file = Path(stop_file) if stop_file is not None else None
    stop_file_seen = False
    termination_reason = "completed_selected_steps"
    _write_company_state_live_snapshot(
        demo_firm=demo_firm,
        selection=selection,
        iterations_requested=iterations_requested,
        selected_steps=selected_steps,
        applied_steps=applied_steps,
        blocked_proposals=[],
        budget_units_consumed=budget_units_consumed,
        max_budget_units=max_budget_units,
        stop_file=stop_file,
        stop_file_seen=stop_file_seen,
        termination_reason="running_before_first_tick",
        planner_transport=planner_transport,
        starter_install=starter_install,
        no_external_calls=no_external_calls,
        extra_report_fields=extra_report_fields,
    )
    live_snapshots_written += 1
    blocked_proposals: list[dict[str, Any]] = []
    for tick_index, step in enumerate(selected_steps, start=1):
        if stop_file is not None and stop_file.exists():
            stop_file_seen = True
            termination_reason = "stop_file"
            break
        if max_budget_units is not None and budget_units_consumed >= max_budget_units:
            termination_reason = "budget_exhausted"
            break
        try:
            applied_steps.append(
                _run_step(
                    step,
                    config=config,
                    demo_firm=demo_firm,
                    action_attestation_log=config.action_attestation_log,
                    planner_evidence_refs=selection.evidence_refs,
                    simulation_tick=_simulation_tick(tick_index, step),
                    reviewer_runtime=reviewer_runtime,
                )
            )
            budget_units_consumed += 1
        except StepBlockedError as exc:
            blocked_proposals.append(exc.blocked_proposal)
            budget_units_consumed += 1
            termination_reason = "blocked_by_reviewer_quorum"
            _write_company_state_live_snapshot(
                demo_firm=demo_firm,
                selection=selection,
                iterations_requested=iterations_requested,
                selected_steps=selected_steps,
                applied_steps=applied_steps,
                blocked_proposals=blocked_proposals,
                budget_units_consumed=budget_units_consumed,
                max_budget_units=max_budget_units,
                stop_file=stop_file,
                stop_file_seen=stop_file_seen,
                termination_reason=termination_reason,
                planner_transport=planner_transport,
                starter_install=starter_install,
                no_external_calls=no_external_calls,
                extra_report_fields=extra_report_fields,
            )
            live_snapshots_written += 1
            break
        _write_company_state_live_snapshot(
            demo_firm=demo_firm,
            selection=selection,
            iterations_requested=iterations_requested,
            selected_steps=selected_steps,
            applied_steps=applied_steps,
            blocked_proposals=blocked_proposals,
            budget_units_consumed=budget_units_consumed,
            max_budget_units=max_budget_units,
            stop_file=stop_file,
            stop_file_seen=stop_file_seen,
            termination_reason="running",
            planner_transport=planner_transport,
            starter_install=starter_install,
            no_external_calls=no_external_calls,
            extra_report_fields=extra_report_fields,
        )
        live_snapshots_written += 1
    if not blocked_proposals and (applied_steps or not stop_file_seen):
        blocked_proposals.append(_run_blocked_candidate_fixture(config))
    operator_controls = build_bounded_run_controls(
        BoundedRunControlInput(
            budget_units_consumed=budget_units_consumed,
            budget_units_total=max_budget_units,
            stop_file=stop_file,
            stop_file_seen=stop_file_seen,
            termination_reason=termination_reason,
            selected_steps=len(selected_steps),
            steps_run=len(applied_steps),
            live_snapshots_written=live_snapshots_written,
        )
    )

    genesis_workload = _collect_workload_summary(demo_firm)
    report = {
        "demo": "self_evolving_org",
        "no_external_calls": (
            planner_transport == "fixture" if no_external_calls is None else no_external_calls
        ),
        "planner_transport": planner_transport,
        "starter_install": starter_install,
        "demo_firm": str(demo_firm),
        "planner_receipts": selection.receipts,
        "iterations_requested": iterations_requested,
        "iterations_run": len(applied_steps),
        "operator_controls": operator_controls,
        "genesis_workload": genesis_workload,
        "steps": applied_steps,
        "blocked_proposals": blocked_proposals,
        "mutation_proofs": [step["mutation_proof"] for step in applied_steps],
        "summary": {
            "proposals": len(applied_steps),
            "genesis_workload_packets": genesis_workload["packet_count"],
            "blocked_proposals": len(blocked_proposals),
            "approved": sum(1 for step in applied_steps if step["decision"] == "approve"),
            "learning_events": len(applied_steps),
            "future_replay_proofs": sum(
                1 for step in applied_steps if step.get("future_replay")
            ),
            "mutation_proofs": len(applied_steps),
            "phase_execution_plans": sum(
                1 for step in applied_steps if step.get("phase_execution_plan_id")
            ),
            "a2a_messages": sum(
                len(step.get("a2a_messages") or [])
                or (1 if step.get("a2a_message_id") else 0)
                for step in applied_steps
            ),
            "a2a_obligations_fulfilled": sum(
                len(
                    [
                        message
                        for message in (step.get("a2a_messages") or [])
                        if message.get("obligation_state") == "fulfilled"
                    ]
                )
                or (1 if step.get("a2a_obligation_state") == "fulfilled" else 0)
                for step in applied_steps
            ),
            "decision_aggregation_cases": sum(
                1 for step in applied_steps if step.get("decision_aggregation_case_id")
            ),
            "trace_events": sum(len(step.get("trace_event_ids", [])) for step in applied_steps),
            "delegation_graphs": sum(
                1 for step in applied_steps if step.get("delegation_graph")
            ),
            "planner_receipts": len(selection.receipts),
            "simulation_ticks": len(applied_steps),
            "simulation_clock_kind": "bounded_harness_iteration",
            "budget_units_consumed": budget_units_consumed,
            "budget_units_total": max_budget_units,
            "budget_units_remaining": operator_controls["budget_units_remaining"],
            "stop_file_seen": stop_file_seen,
            "stop_receipt": operator_controls.get("stop_receipt"),
            "termination_reason": termination_reason,
            "live_snapshots_written": live_snapshots_written,
            "mutation_proofs_valid": all(
                step["mutation_proof"]["valid"] for step in applied_steps
            ),
            "git_commits": _git_log(demo_firm),
            "verdict": (
                "passed"
                if applied_steps and all(step["mutation_proof"]["valid"] for step in applied_steps)
                else "blocked" if blocked_proposals else "empty" if not applied_steps else "failed"
            ),
        },
    }
    if extra_report_fields:
        report.update(extra_report_fields)
    _attach_workload_probe_summary(report)
    mutation_proof_replay = _reconstruct_mutation_proofs_from_report(
        report,
        config=config,
    )
    report["mutation_proof_replay"] = mutation_proof_replay
    report["summary"]["mutation_proofs_reconstructed"] = len(mutation_proof_replay)
    report["summary"]["mutation_proof_replay_valid"] = all(
        row["valid"] and row["matches_saved"] for row in mutation_proof_replay
    )
    reports_dir = demo_firm / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report["provenance_reports"] = _write_step_provenance_reports(
        config=config,
        reports_dir=reports_dir,
        steps=applied_steps,
    )
    report["proposal_review_packets"] = _write_proposal_review_packets(
        config=config,
        reports_dir=reports_dir,
        steps=applied_steps,
        blocked_proposals=blocked_proposals,
    )
    _attach_v04_evidence_summary(report)
    report["company_state"] = _build_company_state_projection(
        demo_firm,
        report,
    )
    report["operator_runbook"] = _build_operator_runbook(report)
    (reports_dir / "self-evolving-org-demo.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports_dir / "self-evolving-org-demo.md").write_text(
        _render_demo_markdown_report(report),
        encoding="utf-8",
    )
    (reports_dir / "self-evolving-org-runbook.json").write_text(
        json.dumps(report["operator_runbook"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports_dir / "self-evolving-org-runbook.md").write_text(
        _render_operator_runbook_markdown(report["operator_runbook"]),
        encoding="utf-8",
    )
    timeline_graph = _build_timeline_graph(report)
    (reports_dir / "self-evolving-org-timeline.json").write_text(
        json.dumps(timeline_graph, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports_dir / "self-evolving-org-mutation-proofs.json").write_text(
        json.dumps(report["mutation_proofs"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports_dir / "self-evolving-org-company-state.json").write_text(
        json.dumps(report["company_state"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports_dir / "self-evolving-org-company-state.html").write_text(
        _render_company_state_html(report["company_state"]),
        encoding="utf-8",
    )
    stage_all(demo_firm)
    commit(demo_firm, "record self-evolving organization demo report")
    return report


def _write_company_state_live_snapshot(
    *,
    demo_firm: Path,
    selection: PlannerSelection,
    iterations_requested: int,
    selected_steps: list[EvolutionStep],
    applied_steps: list[dict[str, Any]],
    blocked_proposals: list[dict[str, Any]],
    budget_units_consumed: int,
    max_budget_units: int | None,
    stop_file: Path | None,
    stop_file_seen: bool,
    termination_reason: str,
    planner_transport: str,
    starter_install: dict[str, Any],
    no_external_calls: bool | None,
    extra_report_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the live-polled company-state projection during a long run."""
    report = _build_company_state_report(
        demo_firm=demo_firm,
        selection=selection,
        iterations_requested=iterations_requested,
        selected_steps=selected_steps,
        applied_steps=applied_steps,
        blocked_proposals=blocked_proposals,
        budget_units_consumed=budget_units_consumed,
        max_budget_units=max_budget_units,
        stop_file=stop_file,
        stop_file_seen=stop_file_seen,
        termination_reason=termination_reason,
        planner_transport=planner_transport,
        starter_install=starter_install,
        no_external_calls=no_external_calls,
        extra_report_fields=extra_report_fields,
        verdict="running" if termination_reason.startswith("running") else None,
    )
    company_state = _build_company_state_projection(demo_firm, report)
    reports_dir = demo_firm / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "self-evolving-org-company-state.json").write_text(
        json.dumps(company_state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports_dir / "self-evolving-org-company-state.html").write_text(
        _render_company_state_html(company_state),
        encoding="utf-8",
    )
    return company_state


def _write_step_provenance_reports(
    *,
    config: KernelServiceConfig,
    reports_dir: Path,
    steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Write reusable provenance handoff reports for accepted governed steps."""
    if not steps:
        return []
    provenance_dir = reports_dir / "provenance"
    provenance_dir.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, Any]] = []
    for step in steps:
        step_id = str(step.get("step_id") or "step").strip() or "step"
        run_id = str(step.get("run_id") or "").strip()
        if not run_id:
            continue
        response = dispatch_kernel_request(
            "GET",
            f"/kernel/provenance-report?run_id={run_id}&event_limit=10",
            config=config,
        )
        _assert_status(response.status, 200, f"provenance report {step_id}")
        provenance_report = response.payload["report"]
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", step_id).strip("_") or "step"
        json_name = f"{slug}-provenance-report.json"
        markdown_name = f"{slug}-provenance-report.md"
        (provenance_dir / json_name).write_text(
            json.dumps(provenance_report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (provenance_dir / markdown_name).write_text(
            str(provenance_report.get("markdown") or ""),
            encoding="utf-8",
        )
        manifests.append(
            {
                "step_id": step_id,
                "run_id": run_id,
                "report_ref": f"file://reports/provenance/{json_name}",
                "markdown_ref": f"file://reports/provenance/{markdown_name}",
                "report_kind": provenance_report.get("report_kind"),
                "read_only": provenance_report.get("read_only"),
                "projection_only": provenance_report.get("projection_only"),
                "coverage": dict(provenance_report.get("coverage") or {}),
                "follow_through": dict(
                    provenance_report.get("follow_through") or {}
                ),
                "summary": dict(provenance_report.get("summary") or {}),
                "evidence_ref_count": len(
                    provenance_report.get("evidence_refs") or []
                ),
            }
        )
    return manifests


def _write_proposal_review_packets(
    *,
    config: KernelServiceConfig,
    reports_dir: Path,
    steps: list[dict[str, Any]],
    blocked_proposals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Write reusable proposal review packets for accepted and blocked changes."""
    proposal_rows: list[dict[str, Any]] = []
    for step in steps:
        proposal_id = str(step.get("proposal_id") or "").strip()
        if proposal_id:
            proposal_rows.append(
                {
                    "proposal_id": proposal_id,
                    "step_id": step.get("step_id"),
                    "target_ref": step.get("target_ref"),
                    "proposal_outcome": "accepted",
                }
            )
    for blocked in blocked_proposals:
        proposal_id = str(blocked.get("proposal_id") or "").strip()
        if proposal_id:
            proposal_rows.append(
                {
                    "proposal_id": proposal_id,
                    "step_id": blocked.get("step_id"),
                    "target_ref": blocked.get("target_ref"),
                    "proposal_outcome": "blocked",
                    "blocked_by": blocked.get("blocked_by"),
                }
            )
    if not proposal_rows:
        return []
    proposal_dir = reports_dir / "proposals"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, Any]] = []
    for row in proposal_rows:
        proposal_id = row["proposal_id"]
        response = dispatch_kernel_request(
            "GET",
            f"/kernel/governance-changes/{proposal_id}/review-packet?event_limit=8",
            config=config,
        )
        _assert_status(response.status, 200, f"proposal review packet {proposal_id}")
        packet = response.payload["packet"]
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", proposal_id).strip("_") or "proposal"
        json_name = f"{slug}-proposal-review-packet.json"
        markdown_name = f"{slug}-proposal-review-packet.md"
        (proposal_dir / json_name).write_text(
            json.dumps(packet, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (proposal_dir / markdown_name).write_text(
            str(packet.get("markdown") or ""),
            encoding="utf-8",
        )
        review = packet.get("review") or {}
        provenance = packet.get("provenance_report") or {}
        follow_through = packet.get("follow_through") or {}
        manifests.append(
            {
                **row,
                "packet_kind": packet.get("packet_kind"),
                "read_only": packet.get("read_only"),
                "projection_only": packet.get("projection_only"),
                "review_state": review.get("review_state"),
                "status": review.get("status"),
                "decision_route": packet.get("decision_route"),
                "proof_obligations": list(packet.get("proof_obligations") or []),
                "follow_through": dict(follow_through),
                "evidence_ref_count": len(packet.get("evidence_refs") or []),
                "provenance_event_count": (
                    provenance.get("summary") or {}
                ).get("event_count", 0),
                "report_ref": f"file://reports/proposals/{json_name}",
                "markdown_ref": f"file://reports/proposals/{markdown_name}",
            }
        )
    return manifests


def _build_company_state_report(
    *,
    demo_firm: Path,
    selection: PlannerSelection,
    iterations_requested: int,
    selected_steps: list[EvolutionStep],
    applied_steps: list[dict[str, Any]],
    blocked_proposals: list[dict[str, Any]],
    budget_units_consumed: int,
    max_budget_units: int | None,
    stop_file: Path | None,
    stop_file_seen: bool,
    termination_reason: str,
    planner_transport: str,
    starter_install: dict[str, Any],
    no_external_calls: bool | None,
    extra_report_fields: dict[str, Any] | None = None,
    verdict: str | None = None,
) -> dict[str, Any]:
    operator_controls = build_bounded_run_controls(
        BoundedRunControlInput(
            budget_units_consumed=budget_units_consumed,
            budget_units_total=max_budget_units,
            stop_file=stop_file,
            stop_file_seen=stop_file_seen,
            termination_reason=termination_reason,
            selected_steps=len(selected_steps),
            steps_run=len(applied_steps),
        )
    )
    mutation_proofs_valid = all(
        step["mutation_proof"]["valid"] for step in applied_steps
    )
    summary_verdict = (
        verdict
        if verdict is not None
        else (
            "passed"
            if applied_steps and mutation_proofs_valid
            else "empty" if not applied_steps else "failed"
        )
    )
    report = {
        "demo": "self_evolving_org",
        "no_external_calls": (
            planner_transport == "fixture" if no_external_calls is None else no_external_calls
        ),
        "planner_transport": planner_transport,
        "starter_install": starter_install,
        "demo_firm": str(demo_firm),
        "planner_receipts": selection.receipts,
        "iterations_requested": iterations_requested,
        "iterations_run": len(applied_steps),
        "operator_controls": operator_controls,
        "steps": applied_steps,
        "blocked_proposals": blocked_proposals,
        "mutation_proofs": [step["mutation_proof"] for step in applied_steps],
        "summary": {
            "proposals": len(applied_steps),
            "blocked_proposals": len(blocked_proposals),
            "approved": sum(1 for step in applied_steps if step["decision"] == "approve"),
            "learning_events": len(applied_steps),
            "future_replay_proofs": sum(
                1 for step in applied_steps if step.get("future_replay")
            ),
            "mutation_proofs": len(applied_steps),
            "phase_execution_plans": sum(
                1 for step in applied_steps if step.get("phase_execution_plan_id")
            ),
            "a2a_messages": sum(
                len(step.get("a2a_messages") or [])
                or (1 if step.get("a2a_message_id") else 0)
                for step in applied_steps
            ),
            "a2a_obligations_fulfilled": sum(
                len(
                    [
                        message
                        for message in (step.get("a2a_messages") or [])
                        if message.get("obligation_state") == "fulfilled"
                    ]
                )
                or (1 if step.get("a2a_obligation_state") == "fulfilled" else 0)
                for step in applied_steps
            ),
            "decision_aggregation_cases": sum(
                1 for step in applied_steps if step.get("decision_aggregation_case_id")
            ),
            "trace_events": sum(len(step.get("trace_event_ids", [])) for step in applied_steps),
            "delegation_graphs": sum(
                1 for step in applied_steps if step.get("delegation_graph")
            ),
            "planner_receipts": len(selection.receipts),
            "simulation_ticks": len(applied_steps),
            "simulation_clock_kind": "bounded_harness_iteration",
            "budget_units_consumed": budget_units_consumed,
            "budget_units_total": max_budget_units,
            "budget_units_remaining": operator_controls["budget_units_remaining"],
            "stop_file_seen": stop_file_seen,
            "stop_receipt": operator_controls.get("stop_receipt"),
            "termination_reason": termination_reason,
            "mutation_proofs_valid": mutation_proofs_valid,
            "git_commits": _git_log(demo_firm),
            "verdict": summary_verdict,
        },
    }
    if extra_report_fields:
        report.update(extra_report_fields)
    _attach_workload_probe_summary(report)
    return report


def _attach_workload_probe_summary(report: dict[str, Any]) -> None:
    workload_probe = report.get("workload_probe") or {}
    workload_summary = workload_probe.get("summary") or {}
    if not workload_summary:
        return
    summary = report.setdefault("summary", {})
    summary["workload_probe_packets"] = workload_summary.get("packet_count", 0)
    summary["workload_feedback_visibility"] = workload_summary.get("feedback_visibility")
    summary["workload_firm_received_scores"] = workload_summary.get("firm_received_scores")
    summary["workload_capability_score_per_budget_unit"] = workload_summary.get(
        "capability_score_per_budget_unit"
    )


def _attach_v04_evidence_summary(report: dict[str, Any]) -> None:
    summary = report.setdefault("summary", {})
    steps = list(report.get("steps") or [])
    summary["learning_use_receipts"] = sum(
        1 for step in steps if step.get("learning_use_receipt")
    )
    summary["context_packets"] = sum(
        1 for step in steps if step.get("context_packet_id")
    )
    summary["verified_context_packets"] = sum(
        1
        for step in steps
        if (step.get("context_packet_verification") or {}).get("ok") is True
    )
    summary["provenance_reports"] = len(report.get("provenance_reports") or [])
    summary["proposal_review_packets"] = len(
        report.get("proposal_review_packets") or []
    )
    proposal_follow_through = _follow_through_status_counts(
        report.get("proposal_review_packets") or []
    )
    summary["proposal_review_follow_through_closed_loop"] = (
        proposal_follow_through.get("closed_loop_observed", 0)
    )
    summary["proposal_review_follow_through_decision_observed"] = (
        proposal_follow_through.get("decision_observed", 0)
    )
    summary["proposal_review_follow_through_proposal_only"] = (
        proposal_follow_through.get("proposal_only", 0)
    )


def _follow_through_status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str((row.get("follow_through") or {}).get("status") or "")
        if not status:
            continue
        counts[status] = counts.get(status, 0) + 1
    return counts


def _render_demo_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Self-Evolving Organization Demo Report",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Iterations run | {report['iterations_run']} |",
        f"| Termination reason | {summary['termination_reason']} |",
        f"| Budget units consumed | {summary['budget_units_consumed']} |",
        f"| Budget units total | {summary['budget_units_total']} |",
        f"| Budget units remaining | {summary['budget_units_remaining']} |",
        f"| Stop file seen | {str(summary['stop_file_seen']).lower()} |",
        f"| Stop receipt | {_md((summary.get('stop_receipt') or {}).get('source', ''))} |",
        f"| Approved proposals | {summary['approved']} |",
        f"| Blocked proposals | {summary['blocked_proposals']} |",
        f"| Learning events | {summary['learning_events']} |",
        f"| Simulation ticks | {summary['simulation_ticks']} |",
        f"| Future replay proofs | {summary['future_replay_proofs']} |",
        f"| Mutation proofs | {summary['mutation_proofs']} |",
        f"| Mutation proofs valid | {str(summary['mutation_proofs_valid']).lower()} |",
        f"| Mutation proofs reconstructed | {summary['mutation_proofs_reconstructed']} |",
        f"| Mutation proof replay valid | {str(summary['mutation_proof_replay_valid']).lower()} |",
        f"| Phase execution plans | {summary['phase_execution_plans']} |",
        f"| A2A messages | {summary['a2a_messages']} |",
        f"| A2A obligations fulfilled | {summary['a2a_obligations_fulfilled']} |",
        f"| Decision aggregation cases | {summary['decision_aggregation_cases']} |",
        f"| Trace events | {summary['trace_events']} |",
        f"| Delegation graphs | {summary['delegation_graphs']} |",
        f"| Planner receipts | {summary['planner_receipts']} |",
        f"| Verdict | {summary['verdict']} |",
        f"| Workload probe packets | {summary.get('workload_probe_packets', 0)} |",
        f"| Workload feedback | {_md(summary.get('workload_feedback_visibility', ''))} |",
        f"| Firm received workload scores | {str(summary.get('workload_firm_received_scores')).lower()} |",
        f"| Workload score per budget | {_md(summary.get('workload_capability_score_per_budget_unit', ''))} |",
        f"| Proposal review closed-loop packets | {summary.get('proposal_review_follow_through_closed_loop', 0)} |",
        f"| Proposal review decision-observed packets | {summary.get('proposal_review_follow_through_decision_observed', 0)} |",
        f"| Proposal review proposal-only packets | {summary.get('proposal_review_follow_through_proposal_only', 0)} |",
        "",
        "## Planner Receipts",
        "",
        "| Receipt | Transport | Steps | Response Digest |",
        "| --- | --- | --- | --- |",
    ]
    for receipt in report.get("planner_receipts", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(receipt["receipt_id"]),
                    _md(receipt["transport"]),
                    _md(", ".join(receipt["step_ids"])),
                    _md(receipt["response_digest"]),
                ]
            )
            + " |"
        )
    if report.get("provenance_reports"):
        lines.extend(
            [
                "",
                "## Provenance Reports",
                "",
                "| Step | Coverage | Follow-Through | Events | Report | Markdown |",
                "| --- | --- | --- | ---: | --- | --- |",
            ]
        )
        for provenance in report["provenance_reports"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(provenance.get("step_id", "")),
                        _md((provenance.get("coverage") or {}).get("status", "")),
                        _md(
                            (provenance.get("follow_through") or {}).get(
                                "status", ""
                            )
                        ),
                        _md((provenance.get("summary") or {}).get("event_count", 0)),
                        _md(provenance.get("report_ref", "")),
                        _md(provenance.get("markdown_ref", "")),
                    ]
                )
                + " |"
            )
    if report.get("proposal_review_packets"):
        lines.extend(
            [
                "",
                "## Proposal Review Packets",
                "",
                "| Proposal | Outcome | Review State | Follow-Through | Evidence Refs | Report | Markdown |",
                "| --- | --- | --- | --- | ---: | --- | --- |",
            ]
        )
        for packet in report["proposal_review_packets"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(packet.get("proposal_id", "")),
                        _md(packet.get("proposal_outcome", "")),
                        _md(packet.get("review_state", "")),
                        _md(
                            (packet.get("follow_through") or {}).get(
                                "status", ""
                            )
                        ),
                        _md(packet.get("evidence_ref_count", 0)),
                        _md(packet.get("report_ref", "")),
                        _md(packet.get("markdown_ref", "")),
                    ]
                )
                + " |"
            )
    daemon_dispatch = report.get("daemon_dispatch")
    if daemon_dispatch:
        lines.extend(
            [
                "",
                "## Daemon Dispatch",
                "",
                "| Field | Value |",
                "| --- | --- |",
                f"| Dispatch valid | {_md(daemon_dispatch.get('valid'))} |",
                f"| Runtime run | {_md(daemon_dispatch.get('run_id'))} |",
                f"| Report | {_md(daemon_dispatch.get('report_ref'))} |",
                f"| Timeline | {_md(daemon_dispatch.get('timeline_ref'))} |",
            ]
        )
    lines.extend(
        [
            "",
            "## Approved Mutations",
            "",
            "| Tick | Step | Proposal | Decision Procedure | Recommendation | Candidate | Signal | Replay | Proof | Commit |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for step in report["steps"]:
        proof = step["mutation_proof"]
        decision_result = step.get("decision_aggregation_result") or {}
        tick = step.get("simulation_tick") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(tick.get("tick_label", "")),
                    _md(step["step_id"]),
                    _md(step["proposal_id"]),
                    _md(decision_result.get("procedure_kind", "")),
                    _md(decision_result.get("recommendation", "")),
                    _md(step["learning_candidate_id"]),
                    _md(step["capability_signal_id"]),
                    _md(step["future_replay"]["learning_event_id"]),
                    _md(proof["proof_digest"]),
                    _md(step["commit"]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Proof Chains", ""])
    for step in report["steps"]:
        proof = step["mutation_proof"]
        lines.extend(
            [
                f"### {_md(step['step_id'])}",
                "",
                "| Stage | Ref |",
                "| --- | --- |",
            ]
        )
        for item in proof["chain"]:
            lines.append(f"| {_md(item['stage'])} | {_md(item['ref'])} |")
        lines.extend(
            [
                "",
                "| Evidence Carrier Ref |",
                "| --- |",
            ]
        )
        for ref in proof.get("evidence_carrier_refs", []):
            lines.append(f"| {_md(ref)} |")
        if step.get("planner_evidence_refs"):
            lines.extend(["", "| Planner Evidence Ref |", "| --- |"])
            for ref in step["planner_evidence_refs"]:
                lines.append(f"| {_md(ref)} |")
        graph = step["delegation_graph"]
        diagnostics = graph.get("diagnostics", {})
        node_count = diagnostics.get("n_agents", len(graph.get("nodes", [])))
        lines.extend(
            [
                "",
                "| Delegation Diagnostic | Value |",
                "| --- | ---: |",
                f"| Nodes | {node_count} |",
                f"| Edges | {diagnostics.get('n_edges', 0)} |",
                f"| Events | {diagnostics.get('n_events', 0)} |",
                "",
            ]
        )
    lines.extend(["## Blocked Proposals", "", "| Proposal | Candidate | Signal | Target | Status | Evidence Gate |", "| --- | --- | --- | --- | --- | --- |"])
    for blocked in report["blocked_proposals"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(blocked["proposal_id"]),
                    _md(blocked["learning_candidate_id"]),
                    _md(blocked["capability_signal_id"]),
                    _md(blocked["target_ref"]),
                    _md(blocked["status"]),
                    _md(blocked["evidence_sufficiency"]["status"]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Git Receipts", "", "| Commit | Subject |", "| --- | --- |"])
    for row in summary["git_commits"]:
        lines.append(f"| {_md(row['sha'])} | {_md(row['subject'])} |")
    return "\n".join(lines) + "\n"


def _operator_execution_health(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Project demo step/block records into the standard runbook health rows."""

    execution_signals: list[dict[str, Any]] = []
    learning_candidates: list[dict[str, Any]] = []
    phase_plans: list[dict[str, Any]] = []
    for step in report.get("steps", []):
        signal_id = step.get("capability_signal_id")
        candidate_id = step.get("learning_candidate_id")
        phase_plan_id = step.get("phase_execution_plan_id")
        evidence_refs = list(
            step.get("proof_evidence_carrier_refs")
            or (step.get("governed_mutation_evidence_pack") or {}).get(
                "evidence_carrier_refs"
            )
            or []
        )
        if signal_id:
            execution_signals.append(
                {
                    "signal_id": signal_id,
                    "signal_kind": "custom",
                    "severity": "warning",
                    "status": "closed",
                    "source_ref": f"work_item:{step.get('work_id', '')}",
                    "owner_role": "role.org_evolver",
                    "worker_ref": "agent.org_evolver",
                    "run_id": step.get("run_id"),
                    "work_id": step.get("work_id"),
                    "recommended_route": "open_governance_change",
                    "route_target_ref": step.get("target_ref"),
                    "counts_as_failure": False,
                    "evidence_refs": evidence_refs,
                }
            )
        if candidate_id:
            learning_candidates.append(
                {
                    "candidate_id": candidate_id,
                    "source_kind": "capability",
                    "transition_kind": step.get("change_kind"),
                    "status": "promoted",
                    "severity": "warning",
                    "object_ref": step.get("target_ref"),
                    "suggested_owner_role": "role.principal",
                    "source_refs": [
                        ref
                        for ref in [
                            f"capability_signal:{signal_id}" if signal_id else None,
                            f"phase_execution_plan:{phase_plan_id}"
                            if phase_plan_id
                            else None,
                            f"work:{step.get('work_id')}" if step.get("work_id") else None,
                        ]
                        if ref
                    ],
                }
            )
        if phase_plan_id:
            phase_plans.append(
                {
                    "plan_id": phase_plan_id,
                    "objective": step.get("title"),
                    "owner_role": "role.org_evolver",
                    "status": "passed",
                    "current_phase": "verification",
                    "remaining_budget_units": None,
                    "attempts": 1,
                    "run_id": step.get("run_id"),
                    "work_id": step.get("work_id"),
                }
            )
    for blocked in report.get("blocked_proposals", []):
        signal_id = blocked.get("capability_signal_id")
        candidate_id = blocked.get("learning_candidate_id")
        route_packet = blocked.get("route_packet") or {}
        evidence_refs = list(
            route_packet.get("evidence_refs")
            or route_packet.get("source_refs")
            or route_packet.get("evidence_carrier_refs")
            or []
        )
        if not evidence_refs and blocked.get("decision_aggregation_case_ref"):
            evidence_refs.append(blocked["decision_aggregation_case_ref"])
        signal_kind = (
            "evidence_gap"
            if blocked.get("blocked_by") == "reviewer_quorum"
            else "unsafe_request"
        )
        if signal_id:
            execution_signals.append(
                {
                    "signal_id": signal_id,
                    "signal_kind": signal_kind,
                    "severity": "blocking",
                    "status": "routed",
                    "source_ref": blocked.get(
                        "decision_aggregation_case_ref",
                        "demo:self_evolving_org:blocked_fixture",
                    ),
                    "owner_role": "role.evaluator",
                    "worker_ref": "agent.org_evolver",
                    "recommended_route": "open_governance_change",
                    "route_target_ref": blocked.get("target_ref"),
                    "counts_as_failure": blocked.get("blocked_by") == "reviewer_quorum",
                    "evidence_refs": evidence_refs,
                }
            )
        if candidate_id:
            learning_candidates.append(
                {
                    "candidate_id": candidate_id,
                    "source_kind": "capability",
                    "transition_kind": "governance_change",
                    "status": blocked.get("status"),
                    "severity": "blocking",
                    "object_ref": blocked.get("target_ref"),
                    "suggested_owner_role": "role.principal",
                    "source_refs": [
                        ref
                        for ref in [
                            f"capability_signal:{signal_id}" if signal_id else None,
                            blocked.get("decision_aggregation_case_ref"),
                        ]
                        if ref
                    ],
                }
            )
    return {
        "execution_signals": execution_signals,
        "learning_candidates": learning_candidates,
        "phase_plans": phase_plans,
    }


def _build_operator_runbook(report: dict[str, Any]) -> dict[str, Any]:
    """Build a human inspection guide for a completed demo run."""

    controls = report.get("operator_controls", {})
    demo_firm = report.get("demo_firm", "")
    planner_transport = report.get("planner_transport", "")
    timeout = None
    for receipt in report.get("planner_receipts", []):
        metadata = receipt.get("metadata") or {}
        if metadata.get("timeout_seconds"):
            timeout = metadata["timeout_seconds"]
            break
    suggested_env = {
        "SELF_EVOLVING_DEMO_WORKDIR": str(Path(demo_firm).parent) if demo_firm else "",
        "SELF_EVOLVING_DEMO_ITERATIONS": str(report.get("iterations_requested", "")),
        "SELF_EVOLVING_DEMO_BUDGET_UNITS": (
            "" if controls.get("budget_units_total") is None else str(controls["budget_units_total"])
        ),
        "SELF_EVOLVING_PLANNER_PROMPT_MODE": (
            (report.get("planner_receipts") or [{}])[0]
            .get("metadata", {})
            .get("prompt_mode", "")
        ),
        "SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS": "" if timeout is None else str(timeout),
    }
    def _make_command(target: str, env: dict[str, Any]) -> str:
        prefix = " ".join(
            f"{key}={shlex.quote(str(value))}"
            for key, value in env.items()
            if value not in (None, "")
        )
        return f"{prefix} make {target}".strip()

    commands = [
        {
            "label": "serve_viewer",
            "command": _make_command(
                "self-evolving-org-serve",
                {"SELF_EVOLVING_DEMO_WORKDIR": suggested_env["SELF_EVOLVING_DEMO_WORKDIR"]},
            ),
        },
        {
            "label": "fixture_rerun",
            "command": _make_command(
                "self-evolving-org-view",
                {"SELF_EVOLVING_DEMO_ITERATIONS": suggested_env["SELF_EVOLVING_DEMO_ITERATIONS"]},
            ),
        },
    ]
    if planner_transport == "subscription_cli":
        planner_metadata = (report.get("planner_receipts") or [{}])[0].get("metadata", {})
        runtime = planner_metadata.get("runtime", "")
        adapter = planner_metadata.get("adapter", "")
        reviewer_invocation = next(
            (
                invocation
                for step in report.get("steps", [])
                for invocation in step.get("reviewer_invocations", [])
                if invocation
            ),
            {},
        )
        reviewer_runtime = reviewer_invocation.get("runtime", "")
        reviewer_adapter = reviewer_invocation.get("adapter", "")
        reviewer_timeout = reviewer_invocation.get("timeout_seconds", "")
        commands.append(
            {
                "label": "live_agent_preflight",
                "command": _make_command(
                    "self-evolving-agent-preflight",
                    {
                        "AGENT_RUNTIME": runtime,
                        "AGENT_ADAPTER": adapter,
                    },
                ),
            }
        )
        commands.append(
            {
                "label": "bounded_live_rerun",
                "command": _make_command(
                    "self-evolving-org-agent-demo",
                    {
                        "AGENT_RUNTIME": runtime,
                        "AGENT_ADAPTER": adapter,
                        "SELF_EVOLVING_DEMO_ITERATIONS": suggested_env[
                            "SELF_EVOLVING_DEMO_ITERATIONS"
                        ],
                        "SELF_EVOLVING_DEMO_BUDGET_UNITS": suggested_env[
                            "SELF_EVOLVING_DEMO_BUDGET_UNITS"
                        ],
                        "SELF_EVOLVING_PLANNER_PROMPT_MODE": suggested_env[
                            "SELF_EVOLVING_PLANNER_PROMPT_MODE"
                        ],
                        "SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS": suggested_env[
                            "SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS"
                        ],
                        "AGENT_REVIEWER_RUNTIME": reviewer_runtime,
                        "AGENT_REVIEWER_ADAPTER": reviewer_adapter,
                        "SELF_EVOLVING_REVIEWER_TIMEOUT_SECONDS": reviewer_timeout,
                    },
                ),
            }
        )
    elif planner_transport == "daemon_subscription_cli":
        planner_metadata = (report.get("planner_receipts") or [{}])[0].get("metadata", {})
        agent_cli = planner_metadata.get("agent_cli", "")
        agent_adapter = planner_metadata.get("agent_adapter", "")
        commands.append(
            {
                "label": "daemon_live_rerun",
                "command": _make_command(
                    "self-evolving-daemon-live-governed-demo",
                    {
                        "AGENT_CLI": agent_cli,
                        "AGENT_ADAPTER": agent_adapter,
                    },
                ),
            }
        )
    artifacts = [
        {
            "label": "company_state_viewer",
            "ref": "file://reports/self-evolving-org-company-state.html",
            "purpose": "Primary human inspection surface for offices, ticks, A2A messages, planner transcript, and kernel trace.",
        },
        {
            "label": "report_json",
            "ref": "file://reports/self-evolving-org-demo.json",
            "purpose": "Machine-readable report with ids and proof summaries.",
        },
        {
            "label": "mutation_proofs",
            "ref": "file://reports/self-evolving-org-mutation-proofs.json",
            "purpose": "Saved proof rows for proposal to evidence to approval to mutation to replay.",
        },
        {
            "label": "git_history",
            "ref": "git:generated-demo-firm",
            "purpose": "System of record for structural and report commits inside the generated demo firm.",
        },
    ]
    for receipt in report.get("planner_receipts", []):
        artifacts.append(
            {
                "label": f"planner_receipt:{receipt['receipt_id']}",
                "ref": f"file://reports/planner/{receipt['receipt_id']}/receipt.json",
                "purpose": "Planner command metadata, prompt/response digests, and parsed step refs.",
            }
        )
    for provenance in report.get("provenance_reports", []):
        step_id = provenance.get("step_id", "step")
        artifacts.append(
            {
                "label": f"provenance_report:{step_id}",
                "ref": provenance.get("report_ref", ""),
                "purpose": "Reusable v0.4 provenance handoff over the accepted mutation run.",
            }
        )
    for packet in report.get("proposal_review_packets", []):
        proposal_id = packet.get("proposal_id", "proposal")
        artifacts.append(
            {
                "label": f"proposal_review_packet:{proposal_id}",
                "ref": packet.get("report_ref", ""),
                "purpose": "Reusable governance-change review handoff for accepted or blocked proposal state.",
            }
        )
    execution_health = _operator_execution_health(report)
    bundle_summaries = [
        step.get("bundle", {})
        for step in report.get("steps", [])
        if step.get("bundle")
    ]
    learning_closure = [
        {
            "step_id": step.get("step_id"),
            "title": step.get("title"),
            "learning_event_id": step.get("learning_event_id"),
            "learning_use_receipt_id": step.get("learning_encounter_id"),
            "changed_context_ref": step.get("target_ref"),
            "future_work_context": (step.get("future_replay") or {}).get("intent"),
            "future_replay_source": (step.get("future_replay") or {}).get(
                "candidate_source"
            ),
            "context_packet_refs": [step.get("context_packet_id")]
            if step.get("context_packet_id")
            else [],
            "outcome_link_id": step.get("outcome_link_id"),
            "outcome_review_status": (
                step.get("outcome_prediction_review") or {}
            ).get("status"),
            "outcome_recommended_action": (
                step.get("outcome_prediction_review") or {}
            ).get("recommended_action"),
            "routine_review_id": step.get("routine_review_id"),
            "routine_review_status": "scheduled",
            "evidence_refs": [
                *list(step.get("proof_evidence_carrier_refs") or []),
                *list(step.get("planner_evidence_refs") or []),
            ],
        }
        for step in report.get("steps", [])
        if step.get("learning_event_id")
    ]
    review_candidates = sum(
        1
        for candidate in execution_health["learning_candidates"]
        if candidate.get("status") in {"open", "review_ready"}
    )
    runbook = build_governed_run_operator_summary(
        GovernedRunOperatorSummaryInput(
            run_label="self_evolving_org",
            run_ref=f"file://{demo_firm}" if demo_firm else "demo:self_evolving_org",
            summary=report.get("summary", {}),
            operator_controls=controls,
            artifacts=artifacts,
            commands=commands,
            inspection_order=[
                "company_state_viewer",
                "planner_receipt",
                "mutation_proofs",
                "git_history",
            ],
            bundle_summaries=bundle_summaries,
            mutation_proofs=report.get("mutation_proofs", []),
            execution_signals=execution_health["execution_signals"],
            learning_candidates=execution_health["learning_candidates"],
            phase_plans=execution_health["phase_plans"],
            learning_closure=learning_closure,
            operator_burden={
                "review_candidates": review_candidates,
                "review_questions": [
                    "Did the run reduce coordination/rework enough to justify the operator review surface?",
                    "Which repeated review signals should become source repair instead of more human checking?",
                ],
            },
            metadata={
                "demo": report.get("demo"),
                "demo_firm": demo_firm,
                "planner_transport": planner_transport,
                "suggested_env": suggested_env,
            },
        )
    )
    return runbook


def _render_operator_runbook_markdown(runbook: dict[str, Any]) -> str:
    markdown = render_governed_run_operator_summary_markdown(runbook)
    return markdown.replace(
        "# Governed Run Operator Summary",
        "# Self-Evolving Organization Operator Runbook",
        1,
    )


def _build_company_state_projection(
    demo_firm: Path,
    report: dict[str, Any],
) -> dict[str, Any]:
    """Build an observer projection of the generated company's current state."""
    roles = _collect_role_offices(demo_firm)
    workload = _collect_workload_packets(demo_firm)
    planner_transcripts = _collect_planner_transcripts(
        demo_firm,
        report.get("planner_receipts", []),
    )
    agent_invocations = _collect_agent_invocation_audits(demo_firm)
    runtime_slots = _build_runtime_slots(roles, agent_invocations)
    a2a_messages = _collect_a2a_messages(demo_firm)
    demo_brief = _collect_demo_brief(demo_firm)
    accepted_mutations = [
        {
            "step_id": step["step_id"],
            "simulation_tick": step.get("simulation_tick"),
            "title": step.get("title", step["step_id"]),
            "change_kind": step["change_kind"],
            "target_ref": step["target_ref"],
            "applied_path": step["applied_path"],
            "decision": step["decision"],
            "decision_procedure": (step.get("decision_aggregation_result") or {}).get(
                "procedure_kind"
            ),
            "decision_recommendation": (step.get("decision_aggregation_result") or {}).get(
                "recommendation"
            ),
            "proposal_id": step["proposal_id"],
            "learning_event_id": step["learning_event_id"],
            "outcome_link_id": step["outcome_link_id"],
            "bundle_id": step["bundle"].get("bundle_id"),
            "commit": step["commit"],
            "rationale": step.get("rationale"),
            "expected_behavior_change": step.get("expected_behavior_change"),
            "predicted_effect": step.get("proposal_predicted_effect"),
            "risk_summary": step.get("risk_summary"),
            "rollback_plan": step.get("rollback_plan"),
            "outcome_prediction_review": step.get("outcome_prediction_review"),
            "decision_positions": step.get("decision_positions", []),
        }
        for step in report.get("steps", [])
    ]
    learning_units = [
        {
            "learning_event_id": step["learning_event_id"],
            "step_id": step["step_id"],
            "simulation_tick": step.get("simulation_tick"),
            "target_ref": step["target_ref"],
            "future_replay_intent": step.get("future_replay", {}).get("intent"),
            "future_replay_candidate_source": step.get("future_replay", {}).get(
                "candidate_source"
            ),
            "context_packet_ref": step.get("context_packet_ref"),
            "context_packet_verified": (
                step.get("context_packet_verification") or {}
            ).get("ok"),
            "learning_steward_review_ref": step.get("learning_steward_review_ref"),
            "evidence_refs": step.get("proof_evidence_carrier_refs", []),
        }
        for step in report.get("steps", [])
    ]
    decision_cases = [
        {
            "case_id": step["decision_aggregation_case_id"],
            "step_id": step["step_id"],
            **(step.get("decision_aggregation_result") or {}),
        }
        for step in report.get("steps", [])
        if step.get("decision_aggregation_case_id")
    ]
    source_refs = [
        "file://reports/self-evolving-org-demo.json",
        "file://reports/self-evolving-org-runbook.md",
        "file://reports/self-evolving-org-timeline.json",
        "file://reports/self-evolving-org-mutation-proofs.json",
        "git:generated-demo-firm",
    ]
    timeline_graph = _build_timeline_graph(report)
    workload_probe = report.get("workload_probe") or {}
    workload_probe_summary = workload_probe.get("summary") or {}
    live_executor_packets = int(workload_probe_summary.get("live_executor_packets") or 0)
    return {
        "projection_kind": "self_evolving_org_company_state",
        "demo": report["demo"],
        "demo_firm": str(demo_firm),
        "planner_transport": report.get("planner_transport"),
        "no_external_calls": report.get("no_external_calls"),
        "operator_controls": report.get("operator_controls", {}),
        "source_refs": source_refs,
        "demo_brief": demo_brief,
        "summary": {
            "offices": len(roles),
            "workload_packets": len(workload),
            "workload_probe_packets": workload_probe_summary.get("packet_count", 0),
            "workload_feedback_visibility": workload_probe_summary.get(
                "feedback_visibility"
            ),
            "workload_firm_received_scores": workload_probe_summary.get(
                "firm_received_scores"
            ),
            "workload_capability_score_per_budget_unit": workload_probe_summary.get(
                "capability_score_per_budget_unit"
            ),
            "accepted_mutations": len(accepted_mutations),
            "blocked_proposals": len(report.get("blocked_proposals", [])),
            "learning_units": len(learning_units),
            "a2a_messages": len(a2a_messages),
            "decision_cases": len(decision_cases),
            "planner_transcripts": len(planner_transcripts),
            "agent_invocations": len(agent_invocations),
            "workload_executor_mode": workload_probe_summary.get("executor_mode", "fixture"),
            "live_workload_executor_packets": live_executor_packets,
            "live_runtime_offices": sum(
                1 for slot in runtime_slots if slot["binding"] == "live_agent_cli"
            ),
            "timeline_nodes": len(timeline_graph.get("nodes", [])),
            "timeline_edges": len(timeline_graph.get("edges", [])),
            "simulation_ticks": len(report.get("steps", [])),
            "termination_reason": report["summary"].get("termination_reason"),
            "verdict": report["summary"].get("verdict"),
        },
        "offices": roles,
        "workload": workload,
        "workload_probe": workload_probe,
        "runtime_slots": runtime_slots,
        "accepted_mutations": accepted_mutations,
        "blocked_proposals": report.get("blocked_proposals", []),
        "learning_units": learning_units,
        "decision_cases": decision_cases,
        "agent_transcripts": {
            "planner_receipts": planner_transcripts,
            "agent_invocations": agent_invocations,
            "a2a_messages": a2a_messages,
        },
        "timeline_graph": timeline_graph,
        "git_commits": report["summary"].get("git_commits", []),
    }


def _collect_demo_brief(demo_firm: Path) -> dict[str, Any]:
    charter = demo_firm / "org" / "charters" / "self_evolving_firm.md"
    workload_readme = demo_firm / "org" / "workload" / "README.md"
    return {
        "charter_ref": "file://org/charters/self_evolving_firm.md",
        "workload_ref": "file://org/workload/README.md",
        "purpose": _markdown_section_excerpt(charter, "Purpose", limit=720),
        "objective": _markdown_section_excerpt(charter, "Initial Objective", limit=520),
        "workload": _first_paragraph_excerpt(workload_readme, limit=640),
    }


def _markdown_section_excerpt(path: Path, heading: str, *, limit: int) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    marker = f"## {heading}"
    capture = False
    out: list[str] = []
    for line in lines:
        if line.strip() == marker:
            capture = True
            continue
        if capture and line.startswith("## "):
            break
        if capture:
            out.append(line.strip())
    return _compact_excerpt("\n".join(out), limit=limit)


def _first_paragraph_excerpt(path: Path, *, limit: int) -> str:
    if not path.exists():
        return ""
    paragraphs = [
        paragraph.strip()
        for paragraph in path.read_text(encoding="utf-8").split("\n\n")
        if paragraph.strip() and not paragraph.lstrip().startswith("#")
    ]
    return _compact_excerpt(paragraphs[0] if paragraphs else "", limit=limit)


def _compact_excerpt(text: str, *, limit: int) -> str:
    raw = re.sub(r"\s+", " ", text).strip()
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)].rstrip() + "..."


def _collect_workload_packets(demo_firm: Path) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    inbox = demo_firm / "org" / "workload" / "inbox"
    jsonl_path = inbox / "packets.jsonl"
    if jsonl_path.exists():
        for line_number, line in enumerate(jsonl_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            packet_id = str(payload.get("packet_id") or f"line-{line_number}").strip()
            title = str(payload.get("title") or packet_id).strip()
            body = str(payload.get("body") or "")
            deliverable = str(payload.get("deliverable_spec") or "")
            packets.append(
                {
                    "packet_id": packet_id,
                    "class": str(payload.get("class") or "unknown"),
                    "title": title,
                    "budget_units": int(payload.get("budget_units") or 1),
                    "source_ref": f"file://{jsonl_path.relative_to(demo_firm)}#{packet_id}",
                    "preview": body[:320],
                    "body": body,
                    "deliverable_spec": deliverable,
                    "records": payload.get("records") or [],
                    "raw": payload,
                }
            )
        return packets
    for path in sorted(inbox.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = path.stem
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        packets.append(
            {
                "packet_id": path.stem,
                "class": "legacy_markdown",
                "title": title,
                "budget_units": 1,
                "source_ref": f"file://{path.relative_to(demo_firm)}",
                "preview": text[:320],
                "body": text,
                "deliverable_spec": "",
                "records": [],
                "raw": {},
            }
        )
    return packets


def _build_runtime_slots(
    roles: list[dict[str, Any]],
    agent_invocations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    invocations_by_producer: dict[str, list[dict[str, Any]]] = {}
    for invocation in agent_invocations:
        producer = _canonical_role_ref(str(invocation.get("producer") or ""))
        if producer:
            invocations_by_producer.setdefault(producer, []).append(invocation)

    slots: list[dict[str, Any]] = []
    for role in roles:
        role_id = _canonical_role_ref(str(role.get("role_id") or ""))
        invocations = invocations_by_producer.get(role_id, [])
        if invocations:
            latest = invocations[-1]
            slots.append(
                {
                    "role_id": role_id,
                    "display_name": role.get("display_name") or role_id,
                    "binding": "live_agent_cli",
                    "runtime": latest.get("runtime"),
                    "adapter": latest.get("adapter"),
                    "invocation_count": len(invocations),
                    "evidence_refs": [
                        row.get("subject_ref") or row.get("attestation_id")
                        for row in invocations
                        if row.get("subject_ref") or row.get("attestation_id")
                    ],
                    "note": (
                        "This office was backed by a spawned role-bearing "
                        "runtime in this run."
                    ),
                }
            )
            continue
        if role_id == "role.principal":
            binding = "governance_authority"
            note = "Approval authority is represented as governed state."
        elif role_id in {
            "role.evaluator",
            "role.risk_guardian",
            "role.learning_steward",
        }:
            binding = "kernel_protocol_office"
            note = (
                "V1 records this office through A2A obligations, decision "
                "positions, and review evidence; it is not a separate spawned "
                "model process yet."
            )
        else:
            binding = "durable_office"
            note = "Durable role office present in org state."
        slots.append(
            {
                "role_id": role_id,
                "display_name": role.get("display_name") or role_id,
                "binding": binding,
                "runtime": None,
                "adapter": None,
                "invocation_count": 0,
                "evidence_refs": [],
                "note": note,
            }
        )
    return slots


def _collect_role_offices(demo_firm: Path) -> list[dict[str, Any]]:
    offices: list[dict[str, Any]] = []
    role_dir = demo_firm / "org" / "roles"
    for path in sorted(role_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            data = {"parse_error": str(exc)}
        raw_role_id = str(data.get("role_id") or path.stem)
        role_id = _canonical_role_ref(raw_role_id)
        offices.append(
            {
                "role_id": role_id,
                "source_role_id": raw_role_id,
                "display_name": data.get("display_name") or path.stem,
                "purpose": data.get("purpose"),
                "mandate_path": data.get("mandate_path"),
                "delegates_to": data.get("delegates_to", []),
                "escalates_to": data.get("escalates_to", []),
                "authorized_paths": data.get("authorized_paths", []),
                "source_ref": f"file://{path.relative_to(demo_firm)}",
            }
        )
    return offices


def _canonical_role_ref(value: str) -> str:
    text = value.strip()
    if not text:
        return text
    return text if text.startswith("role.") else f"role.{text}"


def _collect_planner_transcripts(
    demo_firm: Path,
    receipts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    transcripts: list[dict[str, Any]] = []
    for receipt in receipts:
        receipt_id = receipt.get("receipt_id")
        if not receipt_id:
            continue
        receipt_dir = demo_firm / "reports" / "planner" / receipt_id
        transcripts.append(
            {
                "receipt_id": receipt_id,
                "transport": receipt.get("transport"),
                "step_ids": receipt.get("step_ids", []),
                "prompt_digest": receipt.get("prompt_digest"),
                "response_digest": receipt.get("response_digest"),
                "steps_digest": receipt.get("steps_digest"),
                "metadata": receipt.get("metadata", {}),
                "prompt_ref": _relative_file_ref(demo_firm, receipt_dir / "prompt.md"),
                "response_ref": _relative_file_ref(demo_firm, receipt_dir / "response.txt"),
                "steps_ref": _relative_file_ref(demo_firm, receipt_dir / "steps.json"),
                "prompt_text": _read_report_text(receipt_dir / "prompt.md"),
                "response_text": _read_report_text(receipt_dir / "response.txt"),
                "steps_text": _read_report_text(receipt_dir / "steps.json"),
                "prompt_excerpt": _read_report_excerpt(receipt_dir / "prompt.md"),
                "response_excerpt": _read_report_excerpt(receipt_dir / "response.txt"),
                "steps_excerpt": _read_report_excerpt(receipt_dir / "steps.json"),
            }
        )
    return transcripts


def _collect_agent_invocation_audits(demo_firm: Path) -> list[dict[str, Any]]:
    """Read agent invocation audit rows from generated-firm attestation logs."""
    logs = [
        demo_firm / "org" / "attestations" / "action_attestations.jsonl",
        demo_firm
        / "org"
        / "attestations"
        / "action_attestations"
        / "action_attestations.jsonl",
    ]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for log_path in logs:
        if not log_path.exists():
            continue
        for row in list_agent_invocation_audits(log_path=log_path):
            if row.attestation_id in seen:
                continue
            seen.add(row.attestation_id)
            payload = row.as_dict()
            payload["source_ref"] = f"file://{log_path.relative_to(demo_firm)}"
            rows.append(payload)
    return sorted(rows, key=lambda row: str(row.get("created_at_utc") or ""), reverse=True)


def _collect_a2a_messages(demo_firm: Path) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    seen: set[str] = set()
    channels_dir = demo_firm / "org" / "channels"
    if not channels_dir.exists():
        return messages
    for path in sorted(channels_dir.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        message_id = data.get("message_id") or str(path)
        if message_id in seen:
            continue
        seen.add(message_id)
        messages.append(
            {
                "message_id": message_id,
                "thread_id": data.get("thread_id"),
                "from_role": data.get("from_role"),
                "to_role": data.get("to_role"),
                "kind": data.get("kind"),
                "subject": data.get("subject"),
                "body": data.get("body"),
                "status": data.get("status"),
                "obligation_state": data.get("obligation_state"),
                "references": data.get("references", []),
                "artifacts": data.get("artifacts", []),
                "metadata": data.get("metadata", {}),
                "source_ref": f"file://{path.relative_to(demo_firm)}",
            }
        )
    return messages


def _relative_file_ref(root: Path, path: Path) -> str | None:
    if not path.exists():
        return None
    return f"file://{path.relative_to(root)}"


def _read_report_text(path: Path, *, limit: int = 20000) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated at {limit} characters]\n"


def _read_report_excerpt(path: Path, *, limit: int = 1800) -> str | None:
    if not path.exists():
        return None
    return _compact_excerpt(path.read_text(encoding="utf-8"), limit=limit)


def _render_company_state_html(state: dict[str, Any]) -> str:
    summary = state["summary"]
    state_json = _json_for_script(state)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Self-Evolving Organization Demo Viewer</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --ink: #18202b;
      --muted: #596575;
      --line: #d9dee7;
      --panel: #ffffff;
      --accent: #176b87;
      --ok: #187044;
      --warn: #9a5b00;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      padding: 0;
      background: #101820;
      border-bottom: 1px solid #263342;
      color: #f4f1e8;
      overflow: hidden;
    }}
    h1 {{ margin: 0 0 12px; font-size: 36px; letter-spacing: 0; line-height: 1.05; }}
    h2 {{ margin: 0 0 10px; font-size: 17px; letter-spacing: 0; }}
    .lede {{
      max-width: 920px;
      margin: 0 0 16px;
      color: #d8d0bd;
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(320px, 0.92fr) minmax(360px, 1.08fr);
      gap: 24px;
      padding: 28px 28px 20px;
      min-height: 460px;
      background:
        linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px),
        linear-gradient(0deg, rgba(255,255,255,0.04) 1px, transparent 1px),
        radial-gradient(circle at 70% 22%, rgba(227, 218, 184, 0.13), transparent 28%),
        linear-gradient(135deg, #101820 0%, #172330 52%, #1e2d38 100%);
      background-size: 42px 42px, 42px 42px, auto, auto;
    }}
    .hero-copy {{
      display: flex;
      flex-direction: column;
      justify-content: center;
      min-width: 0;
    }}
    .eyebrow {{
      width: fit-content;
      border: 1px solid rgba(236, 225, 193, 0.35);
      border-radius: 999px;
      padding: 5px 10px;
      margin-bottom: 12px;
      color: #e7ddc5;
      background: rgba(255,255,255,0.06);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .hero-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 18px 0 0;
    }}
    .hero-action {{
      appearance: none;
      border: 1px solid rgba(236, 225, 193, 0.42);
      border-radius: 8px;
      background: #f4f1e8;
      color: #101820;
      padding: 10px 13px;
      font: inherit;
      cursor: pointer;
    }}
    .hero-action.secondary {{
      background: rgba(255,255,255,0.08);
      color: #f4f1e8;
    }}
    .hero-note {{
      margin-top: 14px;
      color: #b7c5c6;
      max-width: 720px;
    }}
    .control-room {{
      position: relative;
      min-height: 400px;
      border: 1px solid rgba(236, 225, 193, 0.22);
      border-radius: 8px;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.01)),
        #0d141b;
      box-shadow: 0 24px 80px rgba(0,0,0,0.28);
      overflow: hidden;
    }}
    .control-room::before {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px),
        linear-gradient(0deg, rgba(255,255,255,0.035) 1px, transparent 1px);
      background-size: 34px 34px;
      pointer-events: none;
    }}
    .control-title {{
      position: relative;
      padding: 14px 16px;
      border-bottom: 1px solid rgba(236, 225, 193, 0.18);
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      z-index: 1;
    }}
    .control-title strong {{ font-size: 14px; }}
    .indicator {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: #d8d0bd;
      font-size: 12px;
    }}
    .indicator::before {{
      content: "";
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: #66d19e;
      box-shadow: 0 0 14px rgba(102, 209, 158, 0.8);
    }}
    .desk-grid {{
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      padding: 14px;
    }}
    .desk-card {{
      min-height: 118px;
      border: 1px solid rgba(236, 225, 193, 0.18);
      border-radius: 8px;
      background: rgba(244, 241, 232, 0.08);
      padding: 11px;
      color: #f4f1e8;
    }}
    .desk-card.wide {{ grid-column: 1 / -1; }}
    .desk-card small {{
      display: block;
      color: #aebbc0;
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      font-size: 11px;
    }}
    .desk-card b {{
      display: block;
      font-size: 24px;
      margin-bottom: 4px;
    }}
    .signal-row {{
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 5px;
      margin-top: 10px;
    }}
    .signal-cell {{
      aspect-ratio: 1;
      border-radius: 3px;
      background: #243441;
      border: 1px solid rgba(236, 225, 193, 0.12);
    }}
    .signal-cell.active {{ background: #c8b36a; box-shadow: 0 0 12px rgba(200, 179, 106, 0.55); }}
    .signal-cell.ok {{ background: #66d19e; box-shadow: 0 0 12px rgba(102, 209, 158, 0.45); }}
    .route-line {{
      height: 8px;
      border-radius: 999px;
      background: linear-gradient(90deg, #66d19e 0 32%, #c8b36a 32% 68%, #8db3c7 68%);
      margin: 12px 0 8px;
    }}
    .process-strip {{
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 6px;
      padding: 0 14px 16px;
    }}
    .process-step {{
      border: 1px solid rgba(236, 225, 193, 0.18);
      border-radius: 8px;
      padding: 8px;
      min-height: 70px;
      background: rgba(16, 24, 32, 0.7);
      color: #d8d0bd;
      font-size: 12px;
    }}
    .process-step strong {{
      display: block;
      color: #f4f1e8;
      margin-bottom: 4px;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 8px;
      max-width: 1180px;
      padding: 0 28px 24px;
    }}
    .metric {{
      border: 1px solid rgba(236, 225, 193, 0.25);
      border-radius: 8px;
      padding: 10px 12px;
      background: rgba(255,255,255,0.07);
      min-height: 68px;
    }}
    .metric b {{ display: block; font-size: 22px; }}
    .metric span {{ color: #c9d0d0; font-size: 12px; }}
    main {{
      padding: 16px 24px 32px;
    }}
    .tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }}
    .tab-button {{
      appearance: none;
      border: 1px solid var(--line);
      border-bottom: 0;
      border-radius: 8px 8px 0 0;
      background: #edf2f7;
      color: var(--muted);
      padding: 9px 13px;
      font: inherit;
      cursor: pointer;
    }}
    .tab-button[aria-selected="true"] {{
      background: var(--panel);
      color: var(--ink);
      box-shadow: inset 0 3px 0 var(--accent);
    }}
    .tab-panel {{
      min-width: 0;
    }}
    .tab-panel[hidden] {{
      display: none;
    }}
    .company-grid, .communications-grid, .proof-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
      gap: 16px;
    }}
    section {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
      margin-bottom: 14px;
      min-width: 0;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 10px;
    }}
    .item {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fff;
      min-width: 0;
    }}
    .item strong {{ display: block; margin-bottom: 4px; overflow-wrap: anywhere; }}
    .muted {{ color: var(--muted); }}
    .mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    pre {{
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfcfe;
      max-height: 340px;
      overflow: auto;
      font-size: 12px;
    }}
    .badge {{
      display: inline-block;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      margin: 2px 4px 2px 0;
      color: var(--muted);
      background: #fff;
      font-size: 12px;
    }}
    .status-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-top: 12px;
    }}
    .chip {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 10px;
      background: #fff;
      color: var(--muted);
      font-size: 12px;
    }}
    .chip.live {{ color: var(--ok); border-color: #9ed7b7; background: #f3fbf6; }}
    .tick-strip {{
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding-bottom: 4px;
    }}
    .tick-card {{
      min-width: 180px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 10px;
    }}
    .tick-card.current {{ border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }}
    .tick-label {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      color: var(--accent);
      font-size: 12px;
      margin-bottom: 4px;
    }}
    .board {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
    }}
    .lane {{
      border-top: 4px solid var(--accent);
      border-radius: 8px;
      background: #fff;
      padding: 10px;
      min-height: 118px;
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      border-left: 1px solid var(--line);
    }}
    .lane[data-role*="risk"] {{ border-top-color: var(--warn); }}
    .lane[data-role*="learning"] {{ border-top-color: var(--ok); }}
    .feed {{
      display: grid;
      gap: 8px;
    }}
    .feed-row {{
      border-left: 4px solid var(--line);
      background: #fff;
      border-radius: 8px;
      padding: 9px 10px;
      border-top: 1px solid var(--line);
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
    }}
    .feed-row[data-kind="mutation"] {{ border-left-color: var(--accent); }}
    .feed-row[data-kind="learning"] {{ border-left-color: var(--ok); }}
    .feed-row[data-kind="message"] {{ border-left-color: var(--warn); }}
    .feed-row[data-kind="trace"] {{ border-left-color: #596575; }}
    .story-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 10px;
    }}
    .story-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 12px;
      min-width: 0;
    }}
    .story-card h3 {{
      margin: 0 0 6px;
      font-size: 14px;
      letter-spacing: 0;
    }}
    .story-card p {{
      margin: 0;
      color: var(--muted);
    }}
    .story-card strong {{
      color: var(--ink);
    }}
    .guide {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: linear-gradient(180deg, #ffffff 0%, #f8fafb 100%);
      margin-bottom: 12px;
    }}
    .guide ol {{
      margin: 8px 0 0 20px;
      padding: 0;
    }}
    .guide li {{ margin: 5px 0; }}
    .decoder {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 8px;
      margin-top: 10px;
    }}
    .decoder-item {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fff;
    }}
    .decoder-item strong {{
      display: block;
      margin-bottom: 4px;
    }}
    .decoder-item span {{
      color: var(--muted);
    }}
    .agent-step {{
      display: grid;
      grid-template-columns: 150px minmax(0, 1fr);
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fff;
      margin-bottom: 8px;
    }}
    .agent-step .who {{
      font-weight: 700;
      color: var(--accent);
    }}
    details {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      background: #fbfcfe;
      margin-top: 8px;
    }}
    summary {{
      cursor: pointer;
      color: var(--accent);
      font-weight: 600;
    }}
    .artifact-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      margin-top: 8px;
    }}
    .artifact-list span {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 7px;
      font-size: 12px;
      color: var(--muted);
      background: #fff;
      max-width: 100%;
      overflow-wrap: anywhere;
    }}
    .role-note {{
      border-left: 4px solid var(--accent);
      background: #fff;
      border-radius: 8px;
      padding: 10px;
      border-top: 1px solid var(--line);
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      margin-bottom: 8px;
    }}
    .role-note[data-position="reject"] {{ border-left-color: #a33131; }}
    .role-note[data-position="abstain"] {{ border-left-color: var(--warn); }}
    @media (max-width: 920px) {{
      main {{ padding: 12px; }}
      .hero {{ grid-template-columns: 1fr; padding: 20px 12px; }}
      h1 {{ font-size: 30px; }}
      .process-strip {{ grid-template-columns: 1fr; }}
      .desk-grid {{ grid-template-columns: 1fr; }}
      .company-grid, .communications-grid, .proof-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="hero">
      <div class="hero-copy">
        <div class="eyebrow">Governed Emergence Demo</div>
        <h1>Self-Evolving Organization Demo Viewer</h1>
        <p class="lede">
          A sealed coordination floor receives concrete work packets whose
          full scoring logic is hidden from the firm. Agents can execute work,
          talk through A2A obligations, propose structural changes, and improve
          the company only through the cognitive-firm governance path.
          The v1 packet set is fixed for reproducible comparison; long runs
          should use held-out or operator-generated packets.
        </p>
        <div class="hero-actions">
          <button class="hero-action" type="button" data-jump-tab="company-tab">Inspect the company</button>
          <button class="hero-action secondary" type="button" data-jump-tab="communications-tab">Read agent work</button>
          <button class="hero-action secondary" type="button" data-jump-tab="proof-tab">Audit proof chain</button>
        </div>
        <p class="hero-note">
          The public page shows the firm-visible universe. Operator-only score
          detail stays outside `demo-firm`, so live agents cannot inspect the
          hidden rubric through normal project files. This is the coordination desk home for the run.
          Fixed packets are a benchmark, not an infinite game board.
        </p>
      </div>
      <div class="control-room" aria-label="Coordination desk visual summary">
        <div class="control-title">
          <strong>Halloway Coordination Desk</strong>
          <span class="indicator">run bounded</span>
        </div>
        <div class="desk-grid">
          <div class="desk-card">
            <small>Visible work packets</small>
            <b>{html.escape(str(summary.get("workload_packets", 0)))}</b>
            intake, refinement, conflict, memory, prune
            <div class="signal-row" aria-hidden="true">
              <span class="signal-cell active"></span><span class="signal-cell active"></span><span class="signal-cell active"></span><span class="signal-cell"></span><span class="signal-cell"></span><span class="signal-cell ok"></span><span class="signal-cell ok"></span><span class="signal-cell"></span><span class="signal-cell active"></span><span class="signal-cell"></span><span class="signal-cell ok"></span><span class="signal-cell"></span>
            </div>
          </div>
          <div class="desk-card">
            <small>Feedback arm</small>
            <b>{html.escape(str(summary.get("workload_feedback_visibility", "") or "n/a"))}</b>
            score totals may be visible or withheld
            <div class="route-line"></div>
          </div>
          <div class="desk-card">
            <small>Agent offices</small>
            <b>{html.escape(str(summary.get("offices", 0)))}</b>
            durable roles, mandates, decision rights
          </div>
          <div class="desk-card">
            <small>Accepted mutations</small>
            <b>{html.escape(str(summary.get("accepted_mutations", 0)))}</b>
            proposed, reviewed, approved, committed
          </div>
          <div class="desk-card wide">
            <small>What this proves</small>
            The demo is not a new agent framework. It is a thin client forcing
            live or fixture agents through kernel work items, A2A messages,
            decision aggregation, attestations, learning events, outcome links,
            mutation proofs, and git receipts.
          </div>
        </div>
        <div class="process-strip">
          <div class="process-step"><strong>1. Work</strong>Packets enter the desk.</div>
          <div class="process-step"><strong>2. Discuss</strong>Offices exchange A2A obligations.</div>
          <div class="process-step"><strong>3. Propose</strong>Org Evolver drafts one bounded mutation.</div>
          <div class="process-step"><strong>4. Govern</strong>Reviewers and Principal decide.</div>
          <div class="process-step"><strong>5. Learn</strong>Approved state changes become future behavior.</div>
        </div>
      </div>
    </div>
    <div class="summary">
      <div class="metric"><b>{html.escape(str(summary.get("offices", 0)))}</b><span>role offices</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("workload_packets", 0)))}</b><span>workload packets</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("workload_feedback_visibility", "") or "n/a"))}</b><span>workload feedback</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("workload_capability_score_per_budget_unit", "") or "hidden"))}</b><span>score / budget</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("accepted_mutations", 0)))}</b><span>accepted mutations</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("learning_units", 0)))}</b><span>learning units</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("simulation_ticks", 0)))}</b><span>simulation ticks</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("a2a_messages", 0)))}</b><span>A2A messages</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("agent_invocations", 0)))}</b><span>agent invocations</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("live_workload_executor_packets", 0)))}</b><span>live work packets</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("live_runtime_offices", 0)))}</b><span>live runtime offices</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("decision_cases", 0)))}</b><span>decision cases</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("timeline_nodes", 0)))}</b><span>trace nodes</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("termination_reason", "")))}</b><span>termination</span></div>
    </div>
    <div class="status-row">
      <span id="live-status" class="chip">static snapshot</span>
      <span id="last-updated" class="chip">loaded from embedded state</span>
    </div>
  </header>
  <main>
    <nav class="tabs" aria-label="Demo inspection tabs">
      <button class="tab-button" type="button" data-tab-target="company-tab" aria-selected="true">Home / Company</button>
      <button class="tab-button" type="button" data-tab-target="communications-tab" aria-selected="false">Agent Work</button>
      <button class="tab-button" type="button" data-tab-target="proof-tab" aria-selected="false">Proof Chain</button>
    </nav>
    <div id="company-tab" class="tab-panel company-grid">
      <div>
        <section>
          <h2>What To Look At First</h2>
          <div class="guide">
            <strong>This page is the entry point.</strong>
            <ol>
              <li>Read <span class="mono">What Happened</span> to see the company-level story.</li>
              <li>Open <span class="mono">Agent Work</span> to inspect prompts, responses, reviewer positions, and A2A messages.</li>
              <li>Open <span class="mono">Proof Chain</span> to verify the mutation path and git-backed receipts.</li>
            </ol>
            <div class="decoder" aria-label="Plain-English Decoder">
              <div class="decoder-item"><strong>Work packet</strong><span>A concrete desk case the firm must handle before it earns the right to improve itself.</span></div>
              <div class="decoder-item"><strong>Office</strong><span>A durable role with a mandate. The role continues across ticks even when a specific agent process ends.</span></div>
              <div class="decoder-item"><strong>A2A message</strong><span>A visible obligation between offices, not an invisible chat transcript.</span></div>
              <div class="decoder-item"><strong>Decision aggregation</strong><span>How reviewer positions were collected. It is evidence for authority, not authority by itself.</span></div>
              <div class="decoder-item"><strong>Mutation proof</strong><span>The receipt chain from proposal to approval, file change, learning event, outcome check, bundle, and git commit.</span></div>
              <div class="decoder-item"><strong>Learning unit</strong><span>A reviewed state change that can affect future dispatch. It is not a chat summary.</span></div>
            </div>
          </div>
        </section>
        <section>
          <h2>Demo Brief</h2>
          <div id="demo-brief" class="story-grid"></div>
        </section>
        <section>
          <h2>What Happened</h2>
          <div id="run-story" class="story-grid"></div>
        </section>
        <section>
          <h2>What Improved</h2>
          <div id="improvement-story" class="story-grid"></div>
        </section>
        <section>
          <h2>Simulation Timeline</h2>
          <div id="ticks" class="tick-strip"></div>
        </section>
        <section>
          <h2>Office Map</h2>
          <div id="office-map" class="board"></div>
        </section>
        <section>
          <h2>Accepted Mutations</h2>
          <div id="mutations" class="grid"></div>
        </section>
      </div>
      <aside>
        <section>
          <h2>Genesis Workload</h2>
          <div id="workload" class="grid"></div>
        </section>
        <section>
          <h2>Workload Probe</h2>
          <div id="workload-probe" class="grid"></div>
        </section>
        <section>
          <h2>Offices</h2>
          <div id="offices" class="grid"></div>
        </section>
        <section>
          <h2>Learning Units</h2>
          <div id="learning" class="grid"></div>
        </section>
      </aside>
    </div>
    <div id="communications-tab" class="tab-panel communications-grid" hidden>
      <div>
        <section>
          <h2>Agent Discussion</h2>
          <div id="agent-discussion"></div>
        </section>
        <section>
          <h2>Planner Transcript</h2>
          <div id="planner"></div>
        </section>
        <section>
          <h2>A2A Messages</h2>
          <div id="messages"></div>
        </section>
      </div>
      <aside>
        <section>
          <h2>Runtime Slots</h2>
          <div id="runtime-slots"></div>
        </section>
        <section>
          <h2>Agent Invocation Audit</h2>
          <div id="agent-invocations"></div>
        </section>
      </aside>
    </div>
    <div id="proof-tab" class="tab-panel proof-grid" hidden>
      <div>
        <section>
          <h2>Event Feed</h2>
          <div id="feed" class="feed"></div>
        </section>
      </div>
      <aside>
        <section>
          <h2>Kernel Trace</h2>
          <div id="trace" class="feed"></div>
        </section>
        <section>
          <h2>Artifacts</h2>
          <div class="feed">
            <div class="feed-row" data-kind="trace"><strong>Timeline JSON</strong><div class="mono">reports/self-evolving-org-timeline.json</div></div>
            <div class="feed-row" data-kind="trace"><strong>Mutation Proofs</strong><div class="mono">reports/self-evolving-org-mutation-proofs.json</div></div>
            <div class="feed-row" data-kind="trace"><strong>Run Report</strong><div class="mono">reports/self-evolving-org-demo.json</div></div>
            <div class="feed-row" data-kind="trace"><strong>Git History</strong><div class="mono">git -C demo-firm log --oneline</div></div>
          </div>
        </section>
      </aside>
    </div>
  </main>
  <script id="state-data" type="application/json">{state_json}</script>
  <script>
    let state = JSON.parse(document.getElementById('state-data').textContent);
    const text = (value) => String(value == null ? '' : value);
    const shortText = (value, limit = 420) => {{
      const raw = text(value).replace(/\\s+/g, ' ').trim();
      return raw.length > limit ? `${{raw.slice(0, limit - 1)}}...` : raw;
    }};
    const roleName = (value) => text(value).replace(/^role\\./, '').replace(/_/g, ' ');
    const ticks = document.getElementById('ticks');
    const runStory = document.getElementById('run-story');
    const improvementStory = document.getElementById('improvement-story');
    const officeMap = document.getElementById('office-map');
    const workload = document.getElementById('workload');
    const workloadProbe = document.getElementById('workload-probe');
    const offices = document.getElementById('offices');
    const mutations = document.getElementById('mutations');
    const learning = document.getElementById('learning');
    const feed = document.getElementById('feed');
    const trace = document.getElementById('trace');
    const agentDiscussion = document.getElementById('agent-discussion');
    const planner = document.getElementById('planner');
    const runtimeSlots = document.getElementById('runtime-slots');
    const agentInvocations = document.getElementById('agent-invocations');
    const messages = document.getElementById('messages');
    const liveStatus = document.getElementById('live-status');
    const lastUpdated = document.getElementById('last-updated');
    const tabButtons = Array.from(document.querySelectorAll('.tab-button'));
    const tabPanels = Array.from(document.querySelectorAll('.tab-panel'));
    const demoBrief = document.getElementById('demo-brief');

    for (const button of tabButtons) {{
      button.addEventListener('click', () => {{
        selectTab(button.dataset.tabTarget);
      }});
    }}
    for (const button of Array.from(document.querySelectorAll('[data-jump-tab]'))) {{
      button.addEventListener('click', () => {{
        selectTab(button.dataset.jumpTab);
        document.querySelector('main').scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }});
    }}

    function selectTab(target) {{
      for (const other of tabButtons) {{
        other.setAttribute('aria-selected', String(other.dataset.tabTarget === target));
      }}
      for (const panel of tabPanels) {{
        panel.hidden = panel.id !== target;
      }}
    }}

    function item(title, parts) {{
      const el = document.createElement('div');
      el.className = 'item';
      const strong = document.createElement('strong');
      strong.textContent = text(title);
      el.appendChild(strong);
      for (const part of parts) {{
        const div = document.createElement('div');
        div.className = part.mono ? 'mono' : part.muted ? 'muted' : '';
        div.textContent = text(part.value);
        el.appendChild(div);
      }}
      return el;
    }}

    function storyCard(title, body, meta = '') {{
      const el = document.createElement('div');
      el.className = 'story-card';
      const h = document.createElement('h3');
      h.textContent = text(title);
      const p = document.createElement('p');
      p.textContent = text(body);
      el.append(h, p);
      if (meta) {{
        const div = document.createElement('div');
        div.className = 'mono';
        div.textContent = text(meta);
        el.appendChild(div);
      }}
      return el;
    }}

    function agentStep(who, title, body, meta = '') {{
      const el = document.createElement('div');
      el.className = 'agent-step';
      const left = document.createElement('div');
      left.className = 'who';
      left.textContent = text(who);
      const right = document.createElement('div');
      const strong = document.createElement('strong');
      strong.textContent = text(title);
      const p = document.createElement('div');
      p.className = 'muted';
      p.textContent = text(body);
      right.append(strong, p);
      if (meta) {{
        const m = document.createElement('div');
        m.className = 'mono';
        m.textContent = text(meta);
        right.appendChild(m);
      }}
      el.append(left, right);
      return el;
    }}

    function detailsBlock(label, value) {{
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      summary.textContent = label;
      const pre = document.createElement('pre');
      pre.textContent = text(value);
      details.append(summary, pre);
      return details;
    }}

    function artifactList(refs) {{
      const wrap = document.createElement('div');
      wrap.className = 'artifact-list';
      for (const ref of refs.filter(Boolean)) {{
        const span = document.createElement('span');
        span.textContent = text(ref);
        wrap.appendChild(span);
      }}
      return wrap;
    }}

    function clearAll() {{
      for (const node of [demoBrief, runStory, improvementStory, ticks, officeMap, workload, workloadProbe, offices, mutations, learning, feed, trace, agentDiscussion, planner, runtimeSlots, agentInvocations, messages]) {{
        node.textContent = '';
      }}
    }}

    function render(nextState) {{
      state = nextState;
      clearAll();
      const byStep = new Map(state.accepted_mutations.map((mutation) => [mutation.step_id, mutation]));
      const latestTick = Math.max(0, ...state.accepted_mutations.map((mutation) => (mutation.simulation_tick || {{}}).tick_index || 0));
      const accepted = state.accepted_mutations || [];
      const blocked = state.blocked_proposals || [];
      const latestMutation = accepted[accepted.length - 1];
      const brief = state.demo_brief || {{}};

      demoBrief.appendChild(storyCard(
        'Purpose',
        brief.purpose || 'The firm performs a neutral coordination workload and may only improve its own operating model when workload evidence justifies it.',
        brief.charter_ref || '',
      ));
      demoBrief.appendChild(storyCard(
        'Initial objective',
        brief.objective || 'Execute the workload first, then propose one bounded structural change at a time.',
        brief.charter_ref || '',
      ));
      demoBrief.appendChild(storyCard(
        'Workload game',
        brief.workload || 'Twenty Coordination Desk packets test triage, refinement, conflict handling, memory use, and routine pruning.',
        brief.workload_ref || '',
      ));

      if (latestMutation) {{
        const tick = latestMutation.simulation_tick || {{}};
        runStory.appendChild(storyCard(
          'The firm ran a bounded company game',
          `At ${{tick.tick_label || 'the latest tick'}}, Org Evolver proposed "${{latestMutation.title || latestMutation.step_id}}" after the Coordination Desk workload. The change went through A2A review, decision aggregation, approval, attestation, learning, outcome review, and a git receipt.`,
          latestMutation.proposal_id || latestMutation.step_id,
        ));
        runStory.appendChild(storyCard(
          'The approved change',
          `It changed ${{latestMutation.target_ref}}: ${{shortText(latestMutation.expected_behavior_change, 360)}}`,
          latestMutation.commit ? `commit ${{latestMutation.commit}}` : '',
        ));
        runStory.appendChild(storyCard(
          'The blocked path matters',
          blocked.length
            ? `The run also generated and blocked ${{blocked.length}} unsafe or under-evidenced proposal. The blocked target was ${{blocked[0].target_ref || blocked[0].proposal_id}}.`
            : 'No blocked proposal was recorded in this snapshot.',
          blocked.length ? (blocked[0].evidence_sufficiency || {{}}).status || blocked[0].status : '',
        ));
        runStory.appendChild(storyCard(
          'How the company was scored',
          state.summary.workload_firm_received_scores
            ? `The firm saw score totals, so it could connect structure changes to workload performance. Current score per budget is ${{state.summary.workload_capability_score_per_budget_unit}}.`
            : 'The operator scored the same workload silently, but score feedback was withheld from firm-visible state. This lets you compare self-direction against measured feedback.',
          `executor: ${{state.summary.workload_executor_mode || 'fixture'}}`,
        ));
      }} else {{
        runStory.appendChild(storyCard(
          'Waiting for first tick',
          'The firm has been seeded, but no governed mutation has completed yet.',
          state.operator_controls && state.operator_controls.termination_reason,
        ));
      }}

      if (latestMutation) {{
        const review = latestMutation.outcome_prediction_review || {{}};
        improvementStory.appendChild(storyCard(
          'Capability improvement claim',
          shortText(latestMutation.rationale, 520),
          latestMutation.target_ref,
        ));
        improvementStory.appendChild(storyCard(
          'Prediction review',
          review.status
            ? `Prediction status: ${{review.status}}. Recommended next action: ${{review.recommended_action || 'none'}}.`
            : 'No prediction review was present in this snapshot.',
          review.review_horizon || '',
        ));
        improvementStory.appendChild(storyCard(
          'Rollback pressure',
          shortText(latestMutation.rollback_plan, 420),
          'routine review required',
        ));
      }}

      for (const mutation of state.accepted_mutations) {{
        const tick = mutation.simulation_tick || {{}};
        const card = document.createElement('div');
        card.className = `tick-card ${{tick.tick_index === latestTick ? 'current' : ''}}`;
        card.appendChild(item(tick.tick_label || tick.tick_id || mutation.step_id, [
          {{ value: mutation.title || mutation.step_id }},
          {{ value: mutation.target_ref, mono: true }},
          {{ value: `decision: ${{mutation.decision_recommendation || ''}}` }},
        ]));
        ticks.appendChild(card);
      }}

      for (const office of state.offices) {{
        const lane = document.createElement('div');
        lane.className = 'lane';
        lane.dataset.role = office.role_id || '';
        lane.appendChild(item(office.display_name || office.role_id, [
          {{ value: office.role_id, mono: true }},
          {{ value: office.purpose || '', muted: true }},
        ]));
        officeMap.appendChild(lane);
        offices.appendChild(item(office.display_name || office.role_id, [
          {{ value: office.role_id, mono: true }},
          {{ value: office.purpose || '', muted: true }},
          {{ value: office.source_ref, mono: true }},
        ]));
      }}

      for (const packet of state.workload || []) {{
        workload.appendChild(item(packet.title || packet.packet_id, [
          {{ value: packet.packet_id, mono: true }},
          {{ value: `${{packet.class || 'unknown'}} · budget ${{packet.budget_units || 1}}` }},
          {{ value: packet.source_ref, mono: true }},
          {{ value: packet.preview || '', muted: true }},
        ]));
      }}

      const probe = state.workload_probe || {{}};
      const probeSummary = probe.summary || {{}};
      workloadProbe.appendChild(item('Probe run', [
        {{ value: `packets: ${{probeSummary.packet_count || 0}}` }},
        {{ value: `feedback: ${{probeSummary.feedback_visibility || 'n/a'}}` }},
        {{ value: `firm received scores: ${{probeSummary.firm_received_scores === true ? 'yes' : 'no'}}` }},
        {{ value: `score / budget: ${{probeSummary.capability_score_per_budget_unit == null ? 'hidden' : probeSummary.capability_score_per_budget_unit}}` }},
        {{ value: `operator detail: ${{probeSummary.operator_score_detail_ref || 'not written into firm state'}}`, mono: true }},
      ]));
      for (const row of (probe.packets || []).slice(0, 8)) {{
        workloadProbe.appendChild(item(row.title || row.packet_id, [
          {{ value: row.packet_id, mono: true }},
          {{ value: `${{row.class || 'unknown'}} · score ${{row.score == null ? 'withheld' : row.score}} / ${{row.max_score == null ? 'hidden' : row.max_score}}` }},
          {{ value: row.visible_receipt_ref, mono: true }},
        ]));
      }}

      for (const mutation of state.accepted_mutations) {{
        const tick = mutation.simulation_tick || {{}};
        mutations.appendChild(item(mutation.title || mutation.step_id, [
          {{ value: `${{tick.tick_label || ''}} ${{tick.tick_id || ''}}`, mono: true }},
          {{ value: `${{mutation.change_kind}} -> ${{mutation.target_ref}}`, mono: true }},
          {{ value: mutation.rationale || '', muted: true }},
          {{ value: `decision: ${{mutation.decision_procedure || ''}} / ${{mutation.decision_recommendation || ''}}` }},
          {{ value: `commit: ${{mutation.commit}}`, mono: true }},
        ]));
      }}

      for (const unit of state.learning_units) {{
        const tick = unit.simulation_tick || {{}};
        learning.appendChild(item(unit.learning_event_id, [
          {{ value: `${{tick.tick_label || ''}} ${{unit.step_id}}`, mono: true }},
          {{ value: unit.future_replay_intent || '', muted: true }},
          {{ value: `context packet: ${{unit.context_packet_ref || 'none'}}${{unit.context_packet_verified ? ' / verified' : ''}}`, mono: true }},
          {{ value: `learning steward: ${{unit.learning_steward_review_ref || 'n/a'}}`, mono: true }},
          {{ value: `evidence refs: ${{unit.evidence_refs.length}}` }},
        ]));
      }}

      const rows = [];
      for (const mutation of state.accepted_mutations) {{
        rows.push({{ kind: 'mutation', tick: (mutation.simulation_tick || {{}}).tick_label, title: mutation.title, detail: mutation.target_ref }});
      }}
      for (const unit of state.learning_units) {{
        rows.push({{ kind: 'learning', tick: (unit.simulation_tick || {{}}).tick_label, title: unit.learning_event_id, detail: unit.future_replay_intent }});
      }}
      for (const message of state.agent_transcripts.a2a_messages) {{
        const mutation = byStep.get(message.metadata && message.metadata.step_id);
        rows.push({{
          kind: 'message',
          tick: mutation ? (mutation.simulation_tick || {{}}).tick_label : '',
          title: `${{message.from_role}} -> ${{message.to_role}}`,
          detail: `${{message.subject || message.message_id}} / ${{message.obligation_state || message.status || ''}}`,
        }});
      }}
      for (const row of rows) {{
        const el = document.createElement('div');
        el.className = 'feed-row';
        el.dataset.kind = row.kind;
        el.appendChild(item(`${{row.tick || ''}} ${{row.title || ''}}`, [
          {{ value: row.kind }},
          {{ value: row.detail || '', muted: true }},
        ]));
        feed.appendChild(el);
      }}

      const graph = state.timeline_graph || {{ nodes: [], edges: [] }};
      const graphSummary = graph.summary || {{}};
      trace.appendChild(item('Trace projection', [
        {{ value: `${{graphSummary.timeline_nodes || graph.nodes.length || 0}} nodes / ${{graphSummary.timeline_edges || graph.edges.length || 0}} edges` }},
        {{ value: graph.graph_kind || 'self_evolving_org_timeline', mono: true }},
      ]));
      for (const edge of graph.edges.slice(-18)) {{
        const el = document.createElement('div');
        el.className = 'feed-row';
        el.dataset.kind = 'trace';
        el.appendChild(item(edge.label || edge.kind || 'edge', [
          {{ value: `${{edge.source || edge.from}} -> ${{edge.target || edge.to}}`, mono: true }},
        ]));
        trace.appendChild(el);
      }}

      for (const mutation of accepted) {{
        agentDiscussion.appendChild(agentStep(
          'Org Evolver',
          'Proposed one bounded structural mutation',
          shortText(mutation.rationale || mutation.expected_behavior_change || '', 620),
          mutation.proposal_id || mutation.step_id,
        ));
        const header = document.createElement('div');
        header.className = 'muted';
        header.textContent = `Reviewer positions for ${{mutation.title || mutation.step_id}}`;
        agentDiscussion.appendChild(header);
        for (const position of mutation.decision_positions || []) {{
          const el = document.createElement('div');
          el.className = 'role-note';
          el.dataset.position = position.position || '';
          const title = document.createElement('strong');
          title.textContent = `${{roleName(position.role_id)}}: ${{position.position || 'position'}}`;
          const rationale = document.createElement('div');
          rationale.className = 'muted';
          rationale.textContent = shortText(position.rationale || '', 520);
          el.append(title, rationale);
          if (position.evidence_summary) {{
            const evidence = document.createElement('div');
            evidence.className = 'mono';
            evidence.textContent = shortText(position.evidence_summary, 360);
            el.appendChild(evidence);
          }}
          if (position.invocation && position.invocation.artifact_refs) {{
            el.appendChild(artifactList(Object.values(position.invocation.artifact_refs)));
          }}
          if (position.invocation && position.invocation.input_refs) {{
            el.appendChild(detailsBlock('Reviewer input evidence', (position.invocation.input_refs || []).join('\\n')));
          }}
          agentDiscussion.appendChild(el);
        }}
        agentDiscussion.appendChild(agentStep(
          'Principal',
          `${{mutation.decision_recommendation || mutation.decision || 'decision'}} via ${{mutation.decision_procedure || 'governance'}}`,
          'The Principal remains the authority holder; reviewer votes are evidence for the decision, not a replacement for decision rights.',
          mutation.commit ? `git receipt: ${{mutation.commit}}` : '',
        ));
      }}
      for (const blockedProposal of blocked) {{
        const result = blockedProposal.decision_aggregation_result || {{}};
        agentDiscussion.appendChild(agentStep(
          'Governance',
          'Blocked proposal',
          shortText(blockedProposal.reason || 'Reviewer quorum did not approve this proposal.', 620),
          blockedProposal.decision_aggregation_case_ref || blockedProposal.proposal_id || '',
        ));
        const header = document.createElement('div');
        header.className = 'muted';
        header.textContent = `Blocked reviewer positions for ${{blockedProposal.target_ref || blockedProposal.proposal_id || 'proposal'}}`;
        agentDiscussion.appendChild(header);
        const positions = blockedProposal.decision_positions || [];
        if (positions.length) {{
          for (const position of positions) {{
            const el = document.createElement('div');
            el.className = 'role-note';
            el.dataset.position = position.position || '';
            const title = document.createElement('strong');
            title.textContent = `${{roleName(position.role_id)}}: ${{position.position || 'position'}}`;
            const rationale = document.createElement('div');
            rationale.className = 'muted';
            rationale.textContent = shortText(position.rationale || '', 520);
            el.append(title, rationale);
            if (position.invocation && position.invocation.artifact_refs) {{
              el.appendChild(artifactList(Object.values(position.invocation.artifact_refs)));
            }}
            if (position.invocation && position.invocation.input_refs) {{
              el.appendChild(detailsBlock('Reviewer input evidence', (position.invocation.input_refs || []).join('\\n')));
            }}
            agentDiscussion.appendChild(el);
          }}
        }} else {{
          agentDiscussion.appendChild(storyCard(
            `Decision aggregation: ${{result.recommendation || blockedProposal.status || 'blocked'}}`,
            shortText(blockedProposal.reason || result.rationale || '', 520),
            `approvals ${{result.approvals || 0}} / quorum ${{result.quorum || 'n/a'}}`,
          ));
          if (Array.isArray(result.evidence_refs) && result.evidence_refs.length) {{
            agentDiscussion.appendChild(detailsBlock('Blocked evidence refs', result.evidence_refs.join('\\n')));
          }}
        }}
      }}
      if (!agentDiscussion.textContent.trim()) {{
        agentDiscussion.appendChild(storyCard(
          'No role discussion yet',
          'Reviewer positions will appear here after the first governed mutation.',
        ));
      }}

      for (const receipt of state.agent_transcripts.planner_receipts) {{
        const block = item(receipt.receipt_id, [
          {{ value: `transport: ${{receipt.transport}}` }},
          {{ value: `steps proposed: ${{(receipt.step_ids || []).join(', ') || 'none'}}` }},
          {{ value: `response: ${{receipt.response_ref || ''}}`, mono: true }},
          {{ value: `prompt: ${{receipt.prompt_ref || 'none recorded'}}`, mono: true }},
        ]);
        block.appendChild(storyCard(
          'Planner response digest',
          shortText(receipt.response_excerpt || receipt.response_text || '', 760),
          receipt.response_digest || '',
        ));
        if (receipt.prompt_text) {{
          block.appendChild(detailsBlock('Show prompt excerpt', receipt.prompt_excerpt || receipt.prompt_text));
        }}
        if (receipt.response_text) {{
          block.appendChild(detailsBlock('Show full captured response excerpt', receipt.response_excerpt || receipt.response_text));
        }}
        if (receipt.steps_text) {{
          block.appendChild(detailsBlock('Show parsed proposal JSON excerpt', receipt.steps_excerpt || receipt.steps_text));
        }}
        planner.appendChild(block);
      }}

      for (const slot of state.runtime_slots || []) {{
        runtimeSlots.appendChild(item(slot.display_name || slot.role_id, [
          {{ value: slot.role_id, mono: true }},
          {{ value: `binding: ${{slot.binding || ''}}` }},
          {{ value: `runtime: ${{slot.runtime || 'n/a'}} / ${{slot.adapter || 'n/a'}}` }},
          {{ value: `invocations: ${{slot.invocation_count || 0}}` }},
          {{ value: slot.note || '', muted: true }},
          {{ value: `evidence: ${{(slot.evidence_refs || []).join(', ') || 'none'}}`, mono: true }},
        ]));
      }}

      for (const invocation of state.agent_transcripts.agent_invocations || []) {{
        const block = item(invocation.subject_ref || invocation.attestation_id, [
          {{ value: `${{invocation.runtime || 'unknown'}} / ${{invocation.adapter || 'unknown adapter'}}` }},
          {{ value: `producer: ${{invocation.producer || ''}}` }},
          {{ value: `returncode: ${{invocation.returncode == null ? 'n/a' : invocation.returncode}}` }},
          {{ value: `session: ${{invocation.agent_session_id || 'n/a'}}`, mono: true }},
          {{ value: `stdout: ${{invocation.stdout_digest || ''}}`, mono: true }},
          {{ value: `source: ${{invocation.source_ref || ''}}`, mono: true }},
        ]);
        const refs = invocation.output_refs || invocation.artifact_refs || [];
        if (Array.isArray(refs) && refs.length) {{
          block.appendChild(artifactList(refs.map((ref) => typeof ref === 'string' ? ref : ref.path || ref.ref || JSON.stringify(ref))));
        }}
        agentInvocations.appendChild(block);
      }}

      for (const message of state.agent_transcripts.a2a_messages) {{
        messages.appendChild(item(message.subject || message.message_id, [
          {{ value: `${{message.from_role}} -> ${{message.to_role}}` }},
          {{ value: message.body || '', muted: true }},
          {{ value: `status: ${{message.status}} / ${{message.obligation_state}}` }},
          {{ value: message.source_ref, mono: true }},
        ]));
      }}
      lastUpdated.textContent = `rendered ${{new Date().toLocaleTimeString()}}`;
    }}

    async function pollState() {{
      if (!location.protocol.startsWith('http')) {{
        liveStatus.textContent = 'static file';
        return;
      }}
      liveStatus.textContent = 'live polling';
      liveStatus.classList.add('live');
      try {{
        const response = await fetch(`self-evolving-org-company-state.json?ts=${{Date.now()}}`, {{ cache: 'no-store' }});
        if (response.ok) {{
          render(await response.json());
        }}
      }} catch (error) {{
        liveStatus.textContent = 'poll paused';
        liveStatus.classList.remove('live');
      }}
    }}

    render(state);
    pollState();
    setInterval(pollState, 2000);
  </script>
</body>
</html>
"""


def _reconstruct_mutation_proofs_from_report(
    report: dict[str, Any],
    *,
    config: KernelServiceConfig,
) -> list[dict[str, Any]]:
    """Rebuild saved proof rows from persisted step facts through service routes."""
    replay_rows: list[dict[str, Any]] = []
    saved_by_step = {
        proof["step_id"]: proof
        for proof in report.get("mutation_proofs", [])
        if isinstance(proof, dict) and proof.get("step_id")
    }
    for step in report.get("steps", []):
        response = dispatch_kernel_request(
            "POST",
            "/kernel/mutation-proofs/build",
            build_mutation_proof_request(
                GovernedMutationRecipeInput(
                    step_id=step["step_id"],
                    change_kind=step["change_kind"],
                    target_ref=step["target_ref"],
                    run_id=step["run_id"],
                    work_id=step["work_id"],
                    proposal_id=step["proposal_id"],
                    approval_event_id=step["decision_event_id"],
                    mutation_ref=f"file://{step['applied_path']}",
                    attestation_id=step["attestation_id"],
                    learning_event_id=step["learning_event_id"],
                    outcome_link_id=step["outcome_link_id"],
                    routine_review_id=step["routine_review_id"],
                    bundle_id=str(step["bundle"].get("bundle_id") or ""),
                    bundle_digest=step["bundle"].get("bundle_digest"),
                    bundle_verdict=step["bundle"].get("verdict"),
                    commit_sha=step["commit"],
                    bundle_validation_errors=step["bundle_validation"].get("errors")
                    or [],
                    evidence_carrier_refs=step.get("proof_evidence_carrier_refs", []),
                )
            ),
            config=config,
        )
        _assert_status(response.status, 200, f"rebuild mutation proof {step['step_id']}")
        rebuilt = response.payload["proof"]
        saved = saved_by_step.get(step["step_id"], {})
        replay_rows.append(
            {
                "step_id": step["step_id"],
                "proof_digest": rebuilt.get("proof_digest"),
                "saved_proof_digest": saved.get("proof_digest"),
                "matches_saved": rebuilt == saved,
                "valid": rebuilt.get("valid") is True,
            }
        )
    return replay_rows


def _build_timeline_graph(report: dict[str, Any]) -> dict[str, Any]:
    """Build a portable graph/timeline projection for visual demo surfaces."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_node(node_id: str, kind: str, label: str, **metadata: Any) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        nodes.append({
            "id": node_id,
            "kind": kind,
            "label": label,
            "metadata": {key: value for key, value in metadata.items() if value is not None},
        })

    def add_edge(source: str, target: str, label: str) -> None:
        edges.append({"source": source, "target": target, "label": label})

    root_id = "demo:self_evolving_org"
    add_node(root_id, "demo", "Self-Evolving Organization Demo", verdict=report["summary"]["verdict"])
    daemon_dispatch = report.get("daemon_dispatch")
    if daemon_dispatch:
        daemon_id = "daemon_dispatch:self_evolving_org"
        add_node(
            daemon_id,
            "daemon_dispatch",
            str(daemon_dispatch.get("run_id") or "daemon dispatch"),
            valid=daemon_dispatch.get("valid"),
            report_ref=daemon_dispatch.get("report_ref"),
            timeline_ref=daemon_dispatch.get("timeline_ref"),
        )
        add_edge(daemon_id, root_id, "plans")
    for receipt in report.get("planner_receipts", []):
        receipt_id = f"planner_receipt:{receipt['receipt_id']}"
        add_node(
            receipt_id,
            "planner_receipt",
            receipt["receipt_id"],
            transport=receipt.get("transport"),
            response_digest=receipt.get("response_digest"),
            step_ids=receipt.get("step_ids"),
        )
        add_edge(root_id, receipt_id, "planned_by")

    for index, step in enumerate(report.get("steps", []), start=1):
        tick = step.get("simulation_tick") or {
            "tick_index": index,
            "tick_id": f"tick_{index:04d}",
            "tick_label": f"T+{index:04d}",
        }
        tick_node = f"simulation_tick:{tick.get('tick_id')}"
        add_node(
            tick_node,
            "simulation_tick",
            str(tick.get("tick_label") or tick.get("tick_id") or index),
            tick_index=tick.get("tick_index"),
            tick_unit=tick.get("tick_unit"),
            step_id=step["step_id"],
        )
        add_edge(root_id, tick_node, "advances")
        step_node = f"step:{step['step_id']}"
        add_node(step_node, "approved_step", step["step_id"], order=index, decision=step["decision"])
        add_edge(tick_node, step_node, "iteration")
        for ref in step.get("planner_evidence_refs", []):
            if ref.startswith("planner_receipt:"):
                add_edge(ref, step_node, "proposed")

        chain_nodes = [
            ("run", f"run:{step['run_id']}", step["run_id"]),
            ("work_item", f"work_item:{step['work_id']}", step["work_id"]),
            ("phase_execution_plan", f"phase_execution_plan:{step['phase_execution_plan_id']}", step["phase_execution_plan_id"]),
            ("decision_aggregation_case", step["decision_aggregation_case_ref"], step["decision_aggregation_case_id"]),
            ("capability_signal", f"capability_signal:{step['capability_signal_id']}", step["capability_signal_id"]),
            ("learning_candidate", f"learning_transition_candidate:{step['learning_candidate_id']}", step["learning_candidate_id"]),
            ("governance_proposal", f"governance_change:{step['proposal_id']}", step["proposal_id"]),
            ("approval", f"kernel_event:{step['decision_event_id']}", step["decision_event_id"]),
            ("mutation", f"file://{step['applied_path']}", step["applied_path"]),
            ("attestation", f"attestation:{step['attestation_id']}", step["attestation_id"]),
            ("learning_event", f"learning_event:{step['learning_event_id']}", step["learning_event_id"]),
            ("future_replay", f"learning_replay:{step['future_replay']['learning_event_id']}", step["future_replay"]["learning_event_id"]),
            ("outcome_link", f"outcome_link:{step['outcome_link_id']}", step["outcome_link_id"]),
            ("routine_review", f"routine_review:{step['routine_review_id']}", step["routine_review_id"]),
            ("bundle", f"bundle:{step['bundle']['bundle_id']}", step["bundle"]["bundle_id"]),
            ("commit", f"git:{step['commit']}", step["commit"]),
        ]
        previous = step_node
        for kind, node_id, label in chain_nodes:
            metadata = {"step_id": step["step_id"]}
            if kind == "decision_aggregation_case":
                result = step.get("decision_aggregation_result") or {}
                metadata.update({
                    "procedure_kind": result.get("procedure_kind"),
                    "recommendation": result.get("recommendation"),
                    "quorum_met": result.get("quorum_met"),
                })
            add_node(node_id, kind, label, **metadata)
            add_edge(previous, node_id, "next")
            previous = node_id
            if kind == "phase_execution_plan":
                for message in step.get("a2a_messages", []):
                    add_node(
                        message["ref"],
                        "a2a_message",
                        message["message_id"],
                        step_id=step["step_id"],
                        from_role=message.get("from_role"),
                        to_role=message.get("to_role"),
                        obligation_state=message.get("obligation_state"),
                    )
                    add_edge(previous, message["ref"], "review")
                if step.get("a2a_messages"):
                    previous = step["a2a_messages"][-1]["ref"]
        for trace_id in step.get("trace_event_ids", []):
            node_id = f"multi_agent_trace_event:{trace_id}"
            add_node(node_id, "trace_event", trace_id, step_id=step["step_id"])
            add_edge(f"run:{step['run_id']}", node_id, "emits")
            add_edge(node_id, f"governance_change:{step['proposal_id']}", "evidence_for")

    for blocked in report.get("blocked_proposals", []):
        proposal_id = f"governance_change:{blocked['proposal_id']}"
        add_node(
            proposal_id,
            "blocked_proposal",
            blocked["proposal_id"],
            target_ref=blocked.get("target_ref"),
            evidence_gate=blocked.get("evidence_sufficiency", {}).get("status"),
        )
        add_node(
            f"capability_signal:{blocked['capability_signal_id']}",
            "capability_signal",
            blocked["capability_signal_id"],
        )
        add_node(
            f"learning_transition_candidate:{blocked['learning_candidate_id']}",
            "learning_candidate",
            blocked["learning_candidate_id"],
        )
        add_edge(root_id, f"capability_signal:{blocked['capability_signal_id']}", "blocked_fixture")
        add_edge(
            f"capability_signal:{blocked['capability_signal_id']}",
            f"learning_transition_candidate:{blocked['learning_candidate_id']}",
            "projects",
        )
        add_edge(f"learning_transition_candidate:{blocked['learning_candidate_id']}", proposal_id, "promotes")

    return {
        "graph_kind": "self_evolving_org_timeline",
        "demo": report["demo"],
        "summary": {
            **report["summary"],
            "timeline_nodes": len(nodes),
            "timeline_edges": len(edges),
        },
        "nodes": nodes,
        "edges": edges,
    }


def _render_timeline_html(graph: dict[str, Any]) -> str:
    """Render a static, dependency-free visual surface for the timeline graph."""
    summary = graph["summary"]
    node_count = len(graph["nodes"])
    edge_count = len(graph["edges"])
    graph_json = _json_for_script(graph)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Self-Evolving Organization Timeline</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --ink: #18202b;
      --muted: #596575;
      --line: #d9dee7;
      --panel: #ffffff;
      --accent: #176b87;
      --warn: #9a5b00;
      --ok: #187044;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      padding: 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }}
    h1 {{ margin: 0 0 12px; font-size: 24px; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 16px; letter-spacing: 0; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 8px;
      max-width: 1160px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      background: #fbfcfe;
      min-height: 68px;
    }}
    .metric b {{ display: block; font-size: 22px; }}
    .metric span {{ color: var(--muted); font-size: 12px; }}
    main {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 320px;
      gap: 16px;
      padding: 16px 24px 32px;
    }}
    .timeline, .side {{
      min-width: 0;
    }}
    .step {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      margin-bottom: 12px;
      overflow: hidden;
    }}
    .step-title {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }}
    .step-title strong {{ overflow-wrap: anywhere; }}
    .badge {{
      flex: 0 0 auto;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      color: var(--muted);
      font-size: 12px;
      background: white;
    }}
    .chain {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 8px;
      padding: 12px;
    }}
    .node {{
      border: 1px solid var(--line);
      border-left: 4px solid var(--accent);
      border-radius: 8px;
      padding: 8px;
      background: #fff;
      min-height: 74px;
    }}
    .node[data-kind="blocked_proposal"] {{ border-left-color: var(--warn); }}
    .node[data-kind="future_replay"], .node[data-kind="learning_event"] {{
      border-left-color: var(--ok);
    }}
    .node-kind {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .node-label {{
      margin-top: 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .side section {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
      margin-bottom: 12px;
    }}
    .edge {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 2px;
      padding: 8px 0;
      border-top: 1px solid var(--line);
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .edge:first-of-type {{ border-top: 0; }}
    .edge-label {{ color: var(--accent); font-family: inherit; }}
    @media (max-width: 880px) {{
      main {{ grid-template-columns: 1fr; padding: 12px; }}
      header {{ padding: 18px 12px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Self-Evolving Organization Timeline</h1>
    <div class="summary">
      <div class="metric"><b>{html.escape(str(summary.get("approved", 0)))}</b><span>approved mutations</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("blocked_proposals", 0)))}</b><span>blocked proposals</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("learning_events", 0)))}</b><span>learning events</span></div>
      <div class="metric"><b>{html.escape(str(summary.get("future_replay_proofs", 0)))}</b><span>future replay proofs</span></div>
      <div class="metric"><b>{html.escape(str(node_count))}</b><span>timeline nodes</span></div>
      <div class="metric"><b>{html.escape(str(edge_count))}</b><span>timeline edges</span></div>
    </div>
  </header>
  <main>
    <div class="timeline" id="timeline"></div>
    <aside class="side">
      <section>
        <h2>Projection</h2>
        <p>This view is generated from <code>self-evolving-org-timeline.json</code>. Kernel logs, bundles, mutation proofs, and git commits remain the source of record.</p>
      </section>
      <section>
        <h2>Evidence Edges</h2>
        <div id="edges"></div>
      </section>
    </aside>
  </main>
  <script id="graph-data" type="application/json">{graph_json}</script>
  <script>
    const graph = JSON.parse(document.getElementById('graph-data').textContent);
    const timeline = document.getElementById('timeline');
    const edges = document.getElementById('edges');
    const byId = new Map(graph.nodes.map((node) => [node.id, node]));
    const stepNodes = graph.nodes
      .filter((node) => node.kind === 'approved_step')
      .sort((a, b) => (a.metadata.order || 0) - (b.metadata.order || 0));

    function text(value) {{
      return String(value == null ? '' : value);
    }}

    function nodeCard(node) {{
      const element = document.createElement('div');
      element.className = 'node';
      element.dataset.kind = node.kind;
      const kind = document.createElement('div');
      kind.className = 'node-kind';
      kind.textContent = text(node.kind);
      const label = document.createElement('div');
      label.className = 'node-label';
      label.textContent = text(node.label);
      element.append(kind, label);
      return element;
    }}

    for (const step of stepNodes) {{
      const section = document.createElement('section');
      section.className = 'step';
      const title = document.createElement('div');
      title.className = 'step-title';
      const titleText = document.createElement('strong');
      titleText.textContent = text(step.label);
      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = text(step.metadata.decision);
      title.append(titleText, badge);
      section.appendChild(title);
      const chain = document.createElement('div');
      chain.className = 'chain';
      chain.appendChild(nodeCard(step));
      let cursor = step.id;
      const visited = new Set([cursor]);
      while (true) {{
        const next = graph.edges.find((edge) => edge.source === cursor && edge.label === 'next');
        if (!next || visited.has(next.target)) break;
        visited.add(next.target);
        const node = byId.get(next.target);
        if (!node) break;
        chain.appendChild(nodeCard(node));
        cursor = next.target;
      }}
      section.appendChild(chain);
      timeline.appendChild(section);
    }}

    const blocked = graph.nodes.filter((node) => node.kind === 'blocked_proposal');
    if (blocked.length) {{
      const section = document.createElement('section');
      section.className = 'step';
      const title = document.createElement('div');
      title.className = 'step-title';
      const titleText = document.createElement('strong');
      titleText.textContent = 'Blocked proposal path';
      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = 'blocked';
      title.append(titleText, badge);
      section.appendChild(title);
      const chain = document.createElement('div');
      chain.className = 'chain';
      for (const node of blocked) chain.appendChild(nodeCard(node));
      section.appendChild(chain);
      timeline.appendChild(section);
    }}

    for (const edge of graph.edges.filter((edge) => edge.label === 'evidence_for').slice(0, 12)) {{
      const item = document.createElement('div');
      item.className = 'edge';
      const label = document.createElement('span');
      label.className = 'edge-label';
      label.textContent = text(edge.label);
      const path = document.createElement('span');
      path.textContent = `${{text(edge.source)}} -> ${{text(edge.target)}}`;
      item.append(label, path);
      edges.appendChild(item);
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


def _define_demo_unit(config: KernelServiceConfig) -> None:
    response = dispatch_kernel_request(
        "POST",
        "/kernel/operating-units",
        {
            "unit_id": "org_evolution",
            "unit_kind": "governed_org_evolution",
            "display_name": "Organization Evolution",
            "owner_role": "role.principal",
            "allowed_work_kinds": [
                "org_diagnosis",
                "role_design",
                "charter_design",
                "learning_cadence",
            ],
            "allowed_exits": ["proposal_approved", "proposal_declined"],
            "worker_roles": [
                "role.org_evolver",
                "role.evaluator",
                "role.risk_guardian",
                "role.learning_steward",
            ],
            "worker_role_classes": {
                "role.org_evolver": "agent",
                "role.evaluator": "governance",
                "role.risk_guardian": "governance",
                "role.learning_steward": "governance",
            },
            "governance_required_for": ["proposal_approved"],
        },
        config=config,
    )
    _assert_status(response.status, 201, "define demo operating unit")
    workload_response = dispatch_kernel_request(
        "POST",
        "/kernel/operating-units",
        {
            "unit_id": "workload_probe_desk",
            "unit_kind": "coordination_workload_probe",
            "display_name": "Workload Probe Desk",
            "owner_role": "role.evaluator",
            "allowed_work_kinds": ["workload_packet_probe"],
            "allowed_exits": ["scored"],
            "worker_roles": ["role.org_evolver", "role.evaluator"],
            "worker_role_classes": {
                "role.org_evolver": "agent",
                "role.evaluator": "governance",
            },
            "governance_required_for": [],
        },
        config=config,
    )
    _assert_status(workload_response.status, 201, "define workload probe operating unit")


def _seed_demo_overlay(demo_firm: Path) -> None:
    """Add the minimal offices this demo needs without changing starter-firm."""
    role_dir = demo_firm / "org" / "roles"
    mandate_dir = demo_firm / "org" / "mandates"
    charter_dir = demo_firm / "org" / "charters"
    workload_dir = demo_firm / "org" / "workload"
    role_dir.mkdir(parents=True, exist_ok=True)
    mandate_dir.mkdir(parents=True, exist_ok=True)
    charter_dir.mkdir(parents=True, exist_ok=True)
    workload_dir.mkdir(parents=True, exist_ok=True)
    _seed_genesis_workload(demo_firm)
    (charter_dir / "self_evolving_firm.md").write_text(
        (
            "# Self-Evolving Firm Charter\n\n"
            "## Purpose\n\n"
            "This firm exists to perform its workload well and cheaply, and to "
            "improve its own operating model only insofar as that improves workload "
            "performance. The workload is the stream of task packets in "
            "`org/workload/inbox/`, scored by an external rubric this firm cannot "
            "read or modify.\n\n"
            "Capability is trailing workload score per unit dispatched budget, with "
            "error and incident counts as guard metrics. Counts of offices, "
            "policies, proposals, or documents are explicitly not measures of "
            "capability.\n\n"
            "## Initial Objective\n\n"
            "Raise trailing capability. Begin by executing the workload as "
            "constituted, then propose one bounded structural change at a time "
            "where evidence from executed work shows the current office structure, "
            "mandates, decision model, protocol, or learning units are costing "
            "score or budget.\n\n"
            "## Evolution Rules\n\n"
            "- Every structural proposal must state a falsifiable predicted effect "
            "on capability or guard metrics and a review horizon.\n"
            "- Outcome links are mandatory. A mutation whose prediction fails at "
            "review becomes a reversal candidate at the next routine review.\n"
            "- At most 20% of dispatched budget per cycle may fund structural "
            "self-modification; the remainder funds workload execution.\n"
            "- Any proposal that adds an office, policy, or protocol must name one "
            "existing structure to retire, or justify net growth to the principal. "
            "Every routine review tables at least one deletion candidate.\n\n"
            "## Amendment Tiers\n\n"
            "- Tier 0 immutable: typed authority, principal decision rights, "
            "attestation and audit duties, and the Non-Goals below.\n"
            "- Tier 1 principal approval only: this charter, the capability "
            "definition, and the workload scoring interface.\n"
            "- Tier 2 governed mutation path: offices, mandates, decision models, "
            "policies, protocols, and learning units.\n\n"
            "## Non-Goals\n\n"
            "- Do not choose an industry-specific business model for the kernel demo.\n"
            "- Do not expand autonomy, tools, budget, or external commitments.\n"
            "- Do not read, infer, or optimize against the workload scoring rubric "
            "itself.\n"
            "- Do not apply structural changes outside governed proposal, review, "
            "approval, attestation, learning, proof, and git receipt.\n\n"
            "## Simulation Game\n\n"
            "Each tick should connect a proposed structure change to workload "
            "evidence, a falsifiable prediction, an outcome link, and a future "
            "routine review. Mere discussion, transcript summaries, or unreviewed "
            "preferences do not count as learning.\n\n"
            "## Evaluation Questions\n\n"
            "- Does the change predict better workload score per budget?\n"
            "- Does it reduce error or incident risk without hiding work?\n"
            "- Does it improve how offices coordinate, review, decide, or learn from workload evidence?\n"
            "- Does it create durable state that future work can actually use?\n"
            "- Is the change reversible and bounded by existing authority?\n"
        ),
        encoding="utf-8",
    )
    (role_dir / "principal.yaml").write_text(
        (
            "role_id: role.principal\n"
            "display_name: Principal\n"
            "mandate_path: org/mandates/principal_mandate.md\n"
            "purpose: Hold final decision rights for structural mutation in the demo firm.\n"
            "authorized_paths:\n"
            "  - org/**\n"
            "delegates_to:\n"
            "  - role.org_evolver\n"
            "  - role.evaluator\n"
            "  - role.risk_guardian\n"
            "  - role.learning_steward\n"
        ),
        encoding="utf-8",
    )
    (role_dir / "org_evolver.yaml").write_text(
        (
            "role_id: role.org_evolver\n"
            "display_name: Org Evolver\n"
            "mandate_path: org/mandates/org_evolver_mandate.md\n"
            "purpose: Propose bounded improvements to roles, mandates, protocols, "
            "charters, decision paths, and learning routines.\n"
            "authorized_paths:\n"
            "  - org/charters/**\n"
            "  - org/mandates/**\n"
            "  - org/roles/**\n"
            "  - org/policies/**\n"
            "delegates_to:\n"
            "  - role.evaluator\n"
            "  - role.risk_guardian\n"
            "  - role.learning_steward\n"
            "escalates_to:\n"
            "  - role.principal\n"
        ),
        encoding="utf-8",
    )
    (role_dir / "evaluator.yaml").write_text(
        (
            "role_id: role.evaluator\n"
            "display_name: Evaluator\n"
            "mandate_path: org/mandates/evaluator_mandate.md\n"
            "purpose: Review structural-change evidence before governance promotion.\n"
            "authorized_paths:\n"
            "  - org/reviews/**\n"
            "  - org/policies/**\n"
            "delegates_to:\n"
            "  - role.risk_guardian\n"
            "  - role.learning_steward\n"
            "escalates_to:\n"
            "  - role.principal\n"
        ),
        encoding="utf-8",
    )
    (role_dir / "risk_guardian.yaml").write_text(
        (
            "role_id: role.risk_guardian\n"
            "display_name: Risk Guardian\n"
            "mandate_path: org/mandates/risk_guardian_mandate.md\n"
            "purpose: Independently review authority expansion, recursion risk, rollback quality, and unsafe incentives before structural changes reach approval.\n"
            "authorized_paths:\n"
            "  - org/reviews/**\n"
            "  - org/risks/**\n"
            "  - org/policies/**\n"
            "escalates_to:\n"
            "  - role.principal\n"
        ),
        encoding="utf-8",
    )
    (role_dir / "learning_steward.yaml").write_text(
        (
            "role_id: role.learning_steward\n"
            "display_name: Learning Steward\n"
            "mandate_path: org/mandates/learning_steward_mandate.md\n"
            "purpose: Own the quality of approved learning units, replay cues, retirement pressure, and evidence traceability.\n"
            "authorized_paths:\n"
            "  - org/learning_events/**\n"
            "  - org/policies/**\n"
            "  - org/reviews/**\n"
            "escalates_to:\n"
            "  - role.principal\n"
        ),
        encoding="utf-8",
    )
    (mandate_dir / "principal_mandate.md").write_text(
        (
            "# Principal Mandate\n\n"
            "The Principal holds the final approval right for structural mutation in "
            "this demo firm. Advisory review, quorum aggregation, and agent "
            "recommendations are evidence; they do not apply organization state "
            "without an explicit Principal decision.\n"
        ),
        encoding="utf-8",
    )
    (mandate_dir / "org_evolver_mandate.md").write_text(
        (
            "# Org Evolver Mandate\n\n"
            "The Org Evolver may diagnose the firm against "
            "`org/charters/self_evolving_firm.md` and propose bounded "
            "improvements to roles, mandates, communication paths, decision "
            "rights, charters, and learning routines. Structural mutation requires a "
            "governance proposal, explicit approval, action provenance, outcome "
            "measurement, routine review, and git-backed state transition.\n\n"
            "The role may not expand its authority, create unbounded recursion, "
            "or bypass evaluator and principal review.\n"
        ),
        encoding="utf-8",
    )
    (mandate_dir / "evaluator_mandate.md").write_text(
        (
            "# Evaluator Mandate\n\n"
            "The Evaluator checks evidence sufficiency, authority fit, and whether "
            "a proposed structural change has enough review context to be promoted. "
            "The Evaluator may request independent risk review and learning "
            "stewardship evidence, but does not approve final mutation.\n"
        ),
        encoding="utf-8",
    )
    (mandate_dir / "risk_guardian_mandate.md").write_text(
        (
            "# Risk Guardian Mandate\n\n"
            "The Risk Guardian reviews proposed structural changes for authority "
            "expansion, recursive instability, weak rollback plans, hidden resource "
            "increases, and incentives that could distort future learning. It may "
            "approve, abstain, or escalate as an advisory control before Principal "
            "approval.\n"
        ),
        encoding="utf-8",
    )
    (mandate_dir / "learning_steward_mandate.md").write_text(
        (
            "# Learning Steward Mandate\n\n"
            "The Learning Steward ensures that approved learning units have a "
            "future-use cue, source carrier refs, owner role, review cadence, and "
            "retirement path. Learning is valid only when it can affect future "
            "dispatch through reviewed state rather than remaining a transcript.\n"
        ),
        encoding="utf-8",
    )


def _seed_genesis_workload(demo_firm: Path) -> None:
    """Seed the exogenous workload interface for the self-organizing demo."""

    workload_dir = demo_firm / "org" / "workload"
    inbox = workload_dir / "inbox"
    scorecards = workload_dir / "scorecards"
    inbox.mkdir(parents=True, exist_ok=True)
    scorecards.mkdir(parents=True, exist_ok=True)
    packets = _genesis_workload_packets()
    (inbox / "packets.jsonl").write_text(
        "".join(json.dumps(packet, sort_keys=True) + "\n" for packet in packets),
        encoding="utf-8",
    )
    (workload_dir / "README.md").write_text(
        (
            "# Genesis Workload\n\n"
            "This directory is the exogenous task stream for the self-evolving firm "
            "demo. The v1 workload is the Coordination Desk for the fictional "
            "Halloway Institute, a three-site research-and-records organization. "
            "It has five packet classes: intake triage, refinement, conflict, "
            "memory, and prune. The packets are concrete and scoreable, but still "
            "industry-neutral enough that the kernel does not pick a business "
            "model.\n\n"
            "The firm may inspect `inbox/packets.jsonl`, execute packets, and use "
            "execution evidence to justify structure changes. Operator-only "
            "answer keys and scorer logic are intentionally not present in firm "
            "state; the firm receives totals and score receipts, not the hidden "
            "rubric.\n"
        ),
        encoding="utf-8",
    )
    (scorecards / "capability-contract.md").write_text(
        (
            "# Capability Scorecard Contract\n\n"
            "Capability is trailing workload score per unit dispatched budget. "
            "Guard metrics are error count, incident count, and unresolved "
            "authority gaps. Structural proposals should predict a measurable "
            "effect on at least one capability or guard metric and name a review "
            "horizon.\n\n"
            "The hidden rubric implementation, answer keys, and operator-only "
            "scorer are outside `org/` and must not be read, modified, inferred, "
            "or optimized directly by the firm.\n"
        ),
        encoding="utf-8",
    )


def _genesis_workload_packets() -> list[dict[str, Any]]:
    deliverables = {
        "intake": "Routing memo, max 200 words, naming exactly one primary destination office plus any required secondary action.",
        "refinement": "One disposition per record: EXPEDITE, STANDARD, ARCHIVE, or ESCALATE; optional rationale memo.",
        "conflict": "Allocation decision recorded through the decision-rights path, with written rationale.",
        "memory": "Class-specific artifact that cites the relevant approved learning event.",
        "prune": "Routine-review outcome (reaffirm / amend / retire / escalate) recorded through routine_reviews, with rationale.",
    }
    return [
        {
            "packet_id": "IN-01",
            "class": "intake",
            "title": "New-hire setup, Calder Point",
            "budget_units": 2,
            "body": "Priya Raman starts Monday at Calder Point. Her team lead asks for a desk assignment, building badge, and records-drive access. The onboarding sheet says Raman is a contractor through Meridian Staffing. The access policy says contractor records-drive access requires Security review and cannot be granted through standard Facilities.",
            "deliverable_spec": deliverables["intake"],
        },
        {
            "packet_id": "IN-02",
            "class": "intake",
            "title": "Courier window request, Thursday",
            "budget_units": 2,
            "body": "Sam Whitlock from Records requests the Thursday courier window for an urgent transfer of 14 archive boxes from Calder Point to Northfield. The ops handbook says one courier-window slot accepts a maximum of 10 boxes.",
            "deliverable_spec": deliverables["intake"],
        },
        {
            "packet_id": "IN-03",
            "class": "intake",
            "title": "Noise complaint, Annex floor 2",
            "budget_units": 2,
            "body": "Reception forwards an intermittent humming complaint on Annex floor 2, guessed to be HVAC. The floor warden log shows Tuesday and Thursday 06:40-06:55 occurrences. A Facilities notice says the backup generator self-test moved to Tuesday and Thursday early mornings.",
            "deliverable_spec": deliverables["intake"],
        },
        {
            "packet_id": "IN-04",
            "class": "intake",
            "title": "Bulk deletion before the audit",
            "budget_units": 2,
            "body": "Devon Okafor asks to authorize deletion of 11 obsolete duplicate folders before Friday's storage audit. The legal-hold register says line items 4, 7, and 9 cover three listed folders under matter HW-2025-031.",
            "deliverable_spec": deliverables["intake"],
        },
        {
            "packet_id": "RF-01",
            "class": "refinement",
            "title": "Record refinement, batch 1",
            "budget_units": 1,
            "body": "Assign each record a disposition. Batch total is returned; per-record results are not.",
            "deliverable_spec": deliverables["refinement"],
            "records": [
                {"record_id": "r01", "age_days": 400, "origin_site": "Northfield", "flag_count": 0, "requester_tier": "executive", "personal_data": False},
                {"record_id": "r02", "age_days": 210, "origin_site": "Annex", "flag_count": 1, "requester_tier": "standard", "personal_data": True},
                {"record_id": "r03", "age_days": 12, "origin_site": "Calder Point", "flag_count": 2, "requester_tier": "standard", "personal_data": False},
                {"record_id": "r04", "age_days": 90, "origin_site": "Northfield", "flag_count": 0, "requester_tier": "executive", "personal_data": False},
            ],
        },
        {
            "packet_id": "RF-02",
            "class": "refinement",
            "title": "Record refinement, batch 2",
            "budget_units": 1,
            "body": "Assign each record a disposition. Batch total is returned; per-record results are not.",
            "deliverable_spec": deliverables["refinement"],
            "records": [
                {"record_id": "r05", "age_days": 700, "origin_site": "Annex", "flag_count": 3, "requester_tier": "standard", "personal_data": False},
                {"record_id": "r06", "age_days": 200, "origin_site": "Calder Point", "flag_count": 0, "requester_tier": "executive", "personal_data": True},
                {"record_id": "r07", "age_days": 25, "origin_site": "Northfield", "flag_count": 0, "requester_tier": "standard", "personal_data": False},
                {"record_id": "r08", "age_days": 380, "origin_site": "Annex", "flag_count": 1, "requester_tier": "standard", "personal_data": False},
            ],
        },
        {
            "packet_id": "RF-03",
            "class": "refinement",
            "title": "Record refinement, batch 3",
            "budget_units": 1,
            "body": "Assign each record a disposition. Batch total is returned; per-record results are not.",
            "deliverable_spec": deliverables["refinement"],
            "records": [
                {"record_id": "r09", "age_days": 150, "origin_site": "Calder Point", "flag_count": 4, "requester_tier": "executive", "personal_data": True},
                {"record_id": "r10", "age_days": 181, "origin_site": "Northfield", "flag_count": 0, "requester_tier": "standard", "personal_data": True},
                {"record_id": "r11", "age_days": 18, "origin_site": "Annex", "flag_count": 0, "requester_tier": "executive", "personal_data": False},
                {"record_id": "r12", "age_days": 366, "origin_site": "Calder Point", "flag_count": 2, "requester_tier": "standard", "personal_data": False},
            ],
        },
        {
            "packet_id": "RF-04",
            "class": "refinement",
            "title": "Record refinement, batch 4",
            "budget_units": 1,
            "body": "Assign each record a disposition. Batch total is returned; per-record results are not.",
            "deliverable_spec": deliverables["refinement"],
            "records": [
                {"record_id": "r13", "age_days": 500, "origin_site": "Northfield", "flag_count": 0, "requester_tier": "standard", "personal_data": True},
                {"record_id": "r14", "age_days": 10, "origin_site": "Annex", "flag_count": 3, "requester_tier": "standard", "personal_data": False},
                {"record_id": "r15", "age_days": 100, "origin_site": "Calder Point", "flag_count": 2, "requester_tier": "executive", "personal_data": False},
                {"record_id": "r16", "age_days": 800, "origin_site": "Northfield", "flag_count": 0, "requester_tier": "executive", "personal_data": False},
            ],
        },
        {
            "packet_id": "CF-01",
            "class": "conflict",
            "title": "The calibration rig",
            "budget_units": 3,
            "body": "Marta Iglesias says the calibration rig was promised to her team for Thursday. Devon Okafor's office claims a standing Thursday reservation. The resource ledger shows Okafor standing entry L-2241. The maintenance log says the rig is flagged for inspection Wednesday and may be out of service 24-48 hours.",
            "deliverable_spec": deliverables["conflict"],
        },
        {
            "packet_id": "CF-02",
            "class": "conflict",
            "title": "Cold-storage bay, Q3",
            "budget_units": 3,
            "body": "Team Hargrove and team Osei both claim cold-storage bay 2. The ledger says Hargrove's allocation lapsed at Q2 end and Osei holds the current entry. Hargrove has a renewal email sent to a departed coordinator but never entered into the ledger.",
            "deliverable_spec": deliverables["conflict"],
        },
        {
            "packet_id": "CF-03",
            "class": "conflict",
            "title": "Courier window, Friday",
            "budget_units": 3,
            "body": "Vendor Liaison wants Friday's courier window for an inbound instrument delivery they describe as penalty-bearing. Records wants the same window for fixed-date audit prep. The vendor contract penalty applies only if delivery is refused at the dock; 24-hour rescheduling has no penalty.",
            "deliverable_spec": deliverables["conflict"],
        },
        {
            "packet_id": "CF-04",
            "class": "conflict",
            "title": "The scanner budget line",
            "budget_units": 3,
            "body": "Records and Facilities each claim budget line 7-310 to replace the archive scanner. The asset register says the scanner is leased, the lease ends next month, and renewal includes a replacement at no capital cost.",
            "deliverable_spec": deliverables["conflict"],
        },
        {
            "packet_id": "ME-01",
            "class": "memory",
            "title": "Confirm our reservation",
            "budget_units": 2,
            "body": "A team asks the desk to confirm a Northfield briefing room reservation for the 24th, arranged verbally with the previous coordinator. No ledger entry exists.",
            "deliverable_spec": deliverables["memory"],
        },
        {
            "packet_id": "ME-02",
            "class": "memory",
            "title": "Elevator escalation, Northfield",
            "budget_units": 2,
            "body": "The Northfield service elevator has faulted three times this month. The desk is asked to draft the escalation to Vertex Lifts.",
            "deliverable_spec": deliverables["memory"],
        },
        {
            "packet_id": "ME-03",
            "class": "memory",
            "title": "The 1,340-page digitization job",
            "budget_units": 2,
            "body": "Legal requests digitization of a 1,340-page case archive as a single job and asks to keep it together for pagination.",
            "deliverable_spec": deliverables["memory"],
        },
        {
            "packet_id": "ME-04",
            "class": "memory",
            "title": "Filing the excursion report",
            "budget_units": 2,
            "body": "Calder Point reports a cold-storage temperature excursion Saturday 02:10-03:40 and asks the desk to file the report today. The submission contains the incident narrative only.",
            "deliverable_spec": deliverables["memory"],
        },
        {
            "packet_id": "PR-01",
            "class": "prune",
            "title": "Routine review due: RR-007 fax-line check",
            "budget_units": 2,
            "body": "The weekly fax-line continuity check RR-007 comes due. A telecom decommission notice says all Institute fax lines were terminated eight months ago.",
            "deliverable_spec": deliverables["prune"],
        },
        {
            "packet_id": "PR-02",
            "class": "prune",
            "title": "Routine review due: RR-012 visitor-log mirror",
            "budget_units": 2,
            "body": "The daily manual visitor-log mirror RR-012 comes due. An IT bulletin says the badge system now auto-exports the visitor log nightly to the same location.",
            "deliverable_spec": deliverables["prune"],
        },
        {
            "packet_id": "PR-03",
            "class": "prune",
            "title": "Routine review due: RR-019 dual-signature cold-storage access",
            "budget_units": 2,
            "body": "The dual-signature cold-storage access routine RR-019 comes due. The second signer role was dissolved and requests stall. An incident summary says the single-signature period produced the LE-004 cold-storage excursion lineage.",
            "deliverable_spec": deliverables["prune"],
        },
        {
            "packet_id": "PR-04",
            "class": "prune",
            "title": "Routine review due: RR-023 printed org-chart binder",
            "budget_units": 2,
            "body": "The monthly printed org-chart binder RR-023 comes due. Distribution logs show zero pickups at any site for five months. An intranet notice says a live org-chart page is available.",
            "deliverable_spec": deliverables["prune"],
        },
    ]


def _collect_workload_summary(demo_firm: Path) -> dict[str, Any]:
    packets = _collect_workload_packets(demo_firm)
    return {
        "schema": "genesis_workload_summary.v1",
        "packet_count": len(packets),
        "packet_refs": [packet["source_ref"] for packet in packets],
        "scorecard_ref": "file://org/workload/scorecards/capability-contract.md",
        "rubric_visible_to_firm": False,
        "capability_metric": "trailing workload score per dispatched budget unit",
        "guard_metrics": ["error_count", "incident_count", "unresolved_authority_gaps"],
        "workload_game": "neutral_coordination_desk",
        "status": "seeded_concrete_desk_work_not_yet_executed",
    }


def _run_workload_probe_harness(
    demo_firm: Path,
    *,
    config: KernelServiceConfig,
    feedback_visibility: str,
    workload_executor_runtime: str | None = None,
    workload_executor_adapter: str = "auto",
    workload_executor_limit: int = 0,
    workload_executor_timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Run visible workload packets through normal work-item execution.

    The packet text and execution receipts are visible to the firm. The scoring
    routine stays in this demo harness and only emits scores/receipts, not the
    hidden rubric implementation, into the generated firm.
    """

    packets = _collect_workload_packets(demo_firm)
    if not packets:
        return {
            "schema": "workload_probe_execution.v1",
            "status": "empty",
            "packets": [],
            "summary": {"packet_count": 0, "average_score": 0.0},
        }
    if feedback_visibility not in {"score_totals", "withheld"}:
        raise ValueError("feedback_visibility must be score_totals or withheld")
    operator_dir = demo_firm.parent / "operator-only" / "workload-probes"
    reports_dir = demo_firm / "reports" / "workload-probes"
    visible_dir = demo_firm / "org" / "workload" / "executions"
    operator_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    visible_dir.mkdir(parents=True, exist_ok=True)
    for stale_scorecard in operator_dir.glob("*.scorecard.json"):
        stale_scorecard.unlink()
    rows: list[dict[str, Any]] = []
    live_executor_invocations = 0
    for packet_index, packet in enumerate(packets, start=1):
        packet_id = packet["packet_id"]
        packet_ref = packet["source_ref"]
        created = dispatch_kernel_request(
            "POST",
            "/kernel/work-items",
            {
                "unit_id": "workload_probe_desk",
                "kind": "workload_packet_probe",
                "payload": {
                    "packet_id": packet_id,
                    "packet_ref": packet_ref,
                    "packet_title": packet["title"],
                },
                "owner_role": "role.org_evolver",
                "idempotency_key": f"workload-probe:{packet_id}",
                "metadata": {
                    "demo": "self_evolving_org",
                    "workload_game": "neutral_coordination_desk",
                },
                "actor": "harness.workload_probe",
            },
            config=config,
        )
        _assert_status(created.status, 201, f"enqueue workload probe {packet_id}")
        work_id = created.payload["work_item"]["work_id"]
        claimed = dispatch_kernel_request(
            "POST",
            "/kernel/work-items/claim-next",
            {
                "unit_id": "workload_probe_desk",
                "kind": "workload_packet_probe",
                "actor": "agent.workload_probe_executor",
                "role_id": "role.org_evolver",
            },
            config=config,
        )
        _assert_status(claimed.status, 200, f"claim workload probe {packet_id}")
        claimed_item = claimed.payload["work_item"]
        if not claimed_item or claimed_item["work_id"] != work_id:
            raise AssertionError(f"claimed unexpected workload probe item for {packet_id}")
        claim_token = claimed_item["claim_token"]
        started = dispatch_kernel_request(
            "POST",
            f"/kernel/work-items/{work_id}/start",
            {
                "actor": "agent.workload_probe_executor",
                "claim_token": claim_token,
            },
            config=config,
        )
        _assert_status(started.status, 200, f"start workload probe {packet_id}")
        live_executor: dict[str, Any] | None = None
        if (
            workload_executor_runtime
            and workload_executor_limit > 0
            and packet_index <= workload_executor_limit
        ):
            artifact_text, live_executor = _run_live_workload_executor(
                demo_firm=demo_firm,
                packet=packet,
                work_id=work_id,
                runtime=workload_executor_runtime,
                adapter=workload_executor_adapter,
                timeout_seconds=workload_executor_timeout_seconds,
            )
            live_executor_invocations += 1
        else:
            artifact_text = _workload_probe_artifact(packet)
        score = _score_workload_probe(packet, artifact_text)
        artifact_rel = Path("org") / "workload" / "executions" / f"{packet_id}.artifact.md"
        visible_rel = Path("org") / "workload" / "executions" / f"{packet_id}.md"
        (demo_firm / artifact_rel).write_text(artifact_text, encoding="utf-8")
        operator_scorecard = {
            "schema": "workload_probe_scorecard.v1",
            "packet_id": packet_id,
            "packet_ref": packet_ref,
            "packet_class": packet.get("class"),
            "work_id": work_id,
            "score": score["score"],
            "max_score": score["max_score"],
            "budget_units": packet["budget_units"],
            "score_visible_to_firm": feedback_visibility == "score_totals",
            "rubric_visible_to_firm": False,
            "visible_feedback": score["visible_feedback"],
            "artifact_ref": f"file://{artifact_rel.as_posix()}",
            "executor_mode": "live_agent" if live_executor else "fixture",
            "live_executor": live_executor,
        }
        operator_scorecard_path = operator_dir / f"{packet_id}.scorecard.json"
        operator_scorecard_path.write_text(
            json.dumps(operator_scorecard, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        score_line = (
            f"- Score: `{score['score']:.2f}` out of `{score['max_score']:.2f}`\n"
            if feedback_visibility == "score_totals"
            else "- Score: `withheld from firm-visible state`\n"
        )
        feedback_line = (
            f"\nVisible feedback: {score['visible_feedback']}\n"
            if feedback_visibility == "score_totals"
            else "\nVisible feedback: score withheld for no-feedback baseline.\n"
        )
        (demo_firm / visible_rel).write_text(
            (
                f"# Workload Execution Receipt - {packet['title']}\n\n"
                f"- Packet: `{packet_id}`\n"
                f"- Class: `{packet.get('class', 'unknown')}`\n"
                f"- Budget units: `{packet['budget_units']}`\n"
                f"- Work item: `{work_id}`\n"
                f"- Feedback visibility: `{feedback_visibility}`\n"
                f"{score_line}"
                "- Rubric visible to firm: `false`\n"
                f"- Artifact: `file://{artifact_rel.as_posix()}`\n"
                f"{feedback_line}"
            ),
            encoding="utf-8",
        )
        attestation = create_action_attestation(
            subject_kind="artifact",
            subject_ref=f"file://{artifact_rel.as_posix()}",
            subject_digest=digest_text(artifact_text),
            producer="role.org_evolver",
            action_type="workload_packet_execution",
            runtime_ref="demo:workload_probe_harness",
            tool_ref="deterministic_external_scorer",
            input_refs=[packet_ref],
            output_refs=[
                f"file://{artifact_rel.as_posix()}",
                f"file://{visible_rel.as_posix()}",
            ],
            verification_status="verified",
            verification_summary=(
                "Workload packet was executed through the work-item queue and "
                "scored by the external demo harness."
            ),
            metadata={
                "demo": "self_evolving_org",
                "packet_id": packet_id,
                "executor_mode": "live_agent" if live_executor else "fixture",
                "score_visible_to_firm": feedback_visibility == "score_totals",
                "rubric_visible_to_firm": False,
            },
            log_path=config.action_attestation_log,
        )
        completed = dispatch_kernel_request(
            "POST",
            f"/kernel/work-items/{work_id}/complete",
            {
                "actor": "agent.workload_probe_executor",
                "claim_token": claim_token,
                "exit_kind": "scored",
                "result": f"score={score['score']:.2f}",
                "producer": "role.org_evolver",
                "verifier": "role.evaluator",
                "artifact_refs": [
                    {"kind": "workload_packet", "path": packet_ref},
                    {"kind": "workload_artifact", "path": f"file://{artifact_rel.as_posix()}"},
                    {"kind": "visible_receipt", "path": f"file://{visible_rel.as_posix()}"},
                    {"kind": "attestation", "path": f"attestation:{attestation.attestation_id}"},
                    *(
                        [
                            {
                                "kind": "live_executor_attestation",
                                "path": live_executor["attestation_ref"],
                            }
                        ]
                        if live_executor
                        else []
                    ),
                ],
            },
            config=config,
        )
        _assert_status(completed.status, 200, f"complete workload probe {packet_id}")
        rows.append(
            {
                "packet_id": packet_id,
                "class": packet.get("class"),
                "title": packet["title"],
                "budget_units": packet["budget_units"],
                "packet_ref": packet_ref,
                "work_id": work_id,
                "score": score["score"] if feedback_visibility == "score_totals" else None,
                "max_score": score["max_score"] if feedback_visibility == "score_totals" else None,
                "score_visible_to_firm": feedback_visibility == "score_totals",
                "executor_mode": "live_agent" if live_executor else "fixture",
                "live_executor": live_executor,
                "visible_feedback": (
                    score["visible_feedback"]
                    if feedback_visibility == "score_totals"
                    else "withheld for no-feedback baseline"
                ),
                "artifact_ref": f"file://{artifact_rel.as_posix()}",
                "visible_receipt_ref": f"file://{visible_rel.as_posix()}",
                "attestation_id": attestation.attestation_id,
                "attestation_ref": f"attestation:{attestation.attestation_id}",
            }
        )
    operator_rows = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(operator_dir.glob("*.scorecard.json"))
    ]
    total_score = round(sum(float(row["score"]) for row in operator_rows), 4)
    total_max_score = round(sum(float(row["max_score"]) for row in operator_rows), 4)
    total_budget_units = sum(int(row["budget_units"]) for row in operator_rows)
    average_percent = round(total_score / total_max_score, 4) if total_max_score else 0.0
    capability_score_per_budget_unit = (
        round(total_score / total_budget_units, 4) if total_budget_units else 0.0
    )
    summary = {
        "packet_count": len(rows),
        "feedback_visibility": feedback_visibility,
        "firm_received_scores": feedback_visibility == "score_totals",
        "operator_scored": True,
        "executor_mode": "mixed" if live_executor_invocations else "fixture",
        "live_executor_packets": live_executor_invocations,
        "total_budget_units": total_budget_units,
        "total_score": total_score if feedback_visibility == "score_totals" else None,
        "total_max_score": total_max_score if feedback_visibility == "score_totals" else None,
        "average_percent": average_percent if feedback_visibility == "score_totals" else None,
        "capability_score_per_budget_unit": (
            capability_score_per_budget_unit
            if feedback_visibility == "score_totals"
            else None
        ),
        "rubric_visible_to_firm": False,
        "operator_score_detail_ref": "operator-only/workload-probes/",
        "execution_evidence_refs": [
            ref
            for row in rows
            for ref in [
                f"work_item:{row['work_id']}",
                row["attestation_ref"],
                row["visible_receipt_ref"],
            ]
        ],
    }
    report = {
        "schema": "workload_probe_execution.v1",
        "status": "scored",
        "workload_game": "neutral_coordination_desk",
        "summary": summary,
        "packets": rows,
    }
    (reports_dir / "workload-probe-summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (visible_dir / "README.md").write_text(
        (
            "# Workload Execution Receipts\n\n"
            "These receipts are visible workload evidence. The hidden rubric "
            "implementation and operator score detail are not present in firm "
            "state.\n\n"
            f"- Packets scored: {summary['packet_count']}\n"
            f"- Feedback visibility: {feedback_visibility}\n"
            f"- Firm received scores: {str(summary['firm_received_scores']).lower()}\n"
            f"- Total budget units: {summary['total_budget_units']}\n"
            "- Rubric visible to firm: false\n"
        ),
        encoding="utf-8",
    )
    return report


def _run_live_workload_executor(
    *,
    demo_firm: Path,
    packet: dict[str, Any],
    work_id: str,
    runtime: str,
    adapter: str,
    timeout_seconds: int,
) -> tuple[str, dict[str, Any]]:
    """Execute one visible workload packet with a live role-bearing CLI."""

    resolved_adapter = infer_agent_adapter(runtime, requested=adapter)
    packet_id = packet["packet_id"]
    prompt = _workload_executor_prompt(packet, work_id=work_id)
    invocation = build_agent_invocation(
        agent_cli=runtime,
        adapter=resolved_adapter,
        prompt=prompt,
        project_root=demo_firm,
    )
    stdout = ""
    stderr = ""
    returncode: int | None = None
    error: str | None = None
    try:
        result = subprocess.run(
            invocation.argv,
            cwd=demo_firm,
            input=invocation.stdin,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=agent_subprocess_env(
                runtime=infer_subscription_runtime_from_adapter(resolved_adapter),
            ),
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        returncode = result.returncode
    except FileNotFoundError as exc:
        stderr = str(exc)
        error = f"workload executor command not found: {exc.filename}"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        error = f"workload executor timed out after {timeout_seconds} seconds"

    artifact_text = _extract_workload_executor_artifact(
        packet=packet,
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        error=error,
    )
    receipt = build_agent_invocation_receipt(
        command_argv=safe_command_for_receipt(invocation.argv, prompt=prompt),
        prompt=prompt,
        runtime=runtime,
        adapter=resolved_adapter,
        prompt_transport=invocation.prompt_transport,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timeout_seconds=timeout_seconds,
        prompt_mode="workload_packet",
        error=error,
    )
    artifact_refs = _write_workload_executor_artifacts(
        demo_firm=demo_firm,
        packet_id=packet_id,
        prompt=prompt,
        stdout=stdout,
        stderr=stderr,
        receipt=receipt,
        artifact_text=artifact_text,
    )
    verification_status = (
        "verified" if returncode == 0 and error is None and stdout.strip() else "failed"
    )
    attestation = create_action_attestation(
        subject_kind="runtime_event",
        subject_ref=f"work_item:{work_id}",
        subject_digest=digest_text(json.dumps(receipt, sort_keys=True)),
        producer="role.org_evolver",
        action_type="agent_cli_dispatch",
        runtime_ref=f"workload_executor:{runtime}",
        tool_ref=resolved_adapter,
        input_refs=[artifact_refs["prompt_ref"], packet["source_ref"]],
        output_refs=[artifact_refs["stdout_ref"], artifact_refs["artifact_ref"]],
        verification_status=verification_status,
        verification_summary=(
            "Live workload executor emitted a packet deliverable."
            if verification_status == "verified"
            else "Live workload executor did not emit a verified packet deliverable."
        ),
        metadata={
            "demo": "self_evolving_org",
            "packet_id": packet_id,
            "work_id": work_id,
            "agent_invocation_receipt": receipt,
        },
        log_path=demo_firm
        / "org"
        / "attestations"
        / "action_attestations"
        / "action_attestations.jsonl",
    )
    live_executor = {
        "runtime": runtime,
        "adapter": resolved_adapter,
        "packet_id": packet_id,
        "work_id": work_id,
        "returncode": returncode,
        "verification_status": verification_status,
        "attestation_id": attestation.attestation_id,
        "attestation_ref": f"attestation:{attestation.attestation_id}",
        **artifact_refs,
    }
    return artifact_text, live_executor


def _workload_executor_prompt(packet: dict[str, Any], *, work_id: str) -> str:
    packet_payload = {
        "packet_id": packet["packet_id"],
        "class": packet.get("class"),
        "title": packet["title"],
        "budget_units": packet["budget_units"],
        "body": packet.get("body"),
        "deliverable_spec": packet.get("deliverable_spec"),
        "records": packet.get("records") or [],
        "source_ref": packet["source_ref"],
        "work_id": work_id,
    }
    return (
        "You are acting as role.org_evolver inside the cognitive-firm "
        "Coordination Desk workload probe.\n\n"
        "Return only the packet deliverable as Markdown. Do not mention hidden "
        "rubrics, answer keys, scoring code, or operator-only files. Use only "
        "the visible packet data below and preserve existing authority "
        "boundaries. If the packet requires escalation, state the escalation "
        "rather than assuming authority.\n\n"
        "Visible packet JSON:\n"
        "```json\n"
        f"{json.dumps(packet_payload, indent=2, sort_keys=True)}\n"
        "```\n"
    )


def _extract_workload_executor_artifact(
    *,
    packet: dict[str, Any],
    stdout: str,
    stderr: str,
    returncode: int | None,
    error: str | None,
) -> str:
    if returncode == 0 and stdout.strip() and error is None:
        return stdout.strip()
    return (
        f"# Live Workload Executor Failure - {packet['title']}\n\n"
        f"Packet `{packet['packet_id']}` did not produce a verified live "
        "deliverable.\n\n"
        f"- Return code: `{returncode}`\n"
        f"- Error: `{error or ''}`\n"
        f"- Stderr preview: `{stderr[:400]}`\n"
    )


def _write_workload_executor_artifacts(
    *,
    demo_firm: Path,
    packet_id: str,
    prompt: str,
    stdout: str,
    stderr: str,
    receipt: dict[str, Any],
    artifact_text: str,
) -> dict[str, str]:
    out_dir = demo_firm / "reports" / "workload-probes" / "live" / packet_id
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "prompt.md": prompt,
        "stdout.txt": stdout,
        "stderr.txt": stderr,
        "receipt.json": json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        "artifact.md": artifact_text,
    }
    for filename, text in files.items():
        (out_dir / filename).write_text(text, encoding="utf-8")
    rel = out_dir.relative_to(demo_firm).as_posix()
    return {
        "prompt_ref": f"file://{rel}/prompt.md",
        "stdout_ref": f"file://{rel}/stdout.txt",
        "stderr_ref": f"file://{rel}/stderr.txt",
        "receipt_ref": f"file://{rel}/receipt.json",
        "artifact_ref": f"file://{rel}/artifact.md",
    }


def _workload_probe_artifact(packet: dict[str, Any]) -> str:
    packet_id = packet["packet_id"]
    title = packet["title"]
    payload = _fixture_workload_answer(packet)
    return (
        f"# Probe Artifact - {title}\n\n"
        f"Packet `{packet_id}` was handled by `role.org_evolver` for the "
        "coordination workload probe.\n\n"
        "## Deliverable\n\n"
        f"{payload}\n\n"
        "## Governance Note\n\n"
        "The packet is treated as external workload evidence. Any structural "
        "change justified by this packet must use normal governance proposal, "
        "review, approval, attestation, learning, outcome, and git receipt paths.\n"
    )


def _fixture_workload_answer(packet: dict[str, Any]) -> str:
    packet_id = packet["packet_id"]
    answers = {
        "IN-01": "Primary route: Facilities for desk and badge. Secondary action: Security review for records-drive access because Priya Raman is a contractor. Complete before Monday onboarding.",
        "IN-02": "Primary route: Facilities. The 14-box request exceeds the 10-box courier cap, so split across Thursday and Friday slots or book freight for the overflow.",
        "IN-03": "Primary route: Facilities. The Tuesday/Thursday 06:40-06:55 pattern correlates with the generator self-test schedule; confirm before vendor HVAC dispatch.",
        "IN-04": "Primary route: Records. Approve only the eight folders not under hold; exclude held folders 4, 7, and 9 under HW-2025-031 before Friday audit deletion.",
        "CF-01": "Decision: do not allocate Thursday until maintenance inspection clears the rig. Ledger entry L-2241 gives Okafor precedence for the next available slot; offer Marta Iglesias the following slot.",
        "CF-02": "Decision: allocate bay 2 to Osei. LE-001 says reservations require ledger entries as system of record; Hargrove should file a new entry.",
        "CF-03": "Decision: allocate Friday courier window to Records. Vendor Liaison should reschedule to Monday with 24-hour notice because penalty triggers only on refused dock delivery.",
        "CF-04": "Decision: deny both budget claims. The lease renewal includes the scanner replacement at no capital cost; route to Vendor Liaison for renewal.",
        "ME-01": "Citing LE-001, cannot confirm a verbal reservation with no ledger entry. Offer to file a ledger entry now, subject to availability.",
        "ME-02": "Citing LE-002, draft escalation to Vertex Lifts and cc the Northfield site manager.",
        "ME-03": "Citing LE-003, split the 1,340-page digitization job into 500-page batches with sequential job IDs and a pagination note.",
        "ME-04": "Citing LE-004, request the 24-hour sensor log before filing; do not file the incomplete excursion report.",
        "PR-01": '{"outcome":"retire","routine_ref":"RR-007","rationale":"Fax lines were decommissioned and terminated eight months ago."}',
        "PR-02": '{"outcome":"retire","routine_ref":"RR-012","rationale":"Badge system now auto-export nightly visitor logs to the same location."}',
        "PR-03": '{"outcome":"amend","routine_ref":"RR-019","rationale":"Do not retire; amend second signer to a current role because the incident and LE-004 excursion lineage show single-signature risk."}',
        "PR-04": '{"outcome":"retire","routine_ref":"RR-023","rationale":"Zero pickup logs and the intranet live org-chart make the printed binder stale."}',
    }
    if packet_id.startswith("RF-"):
        dispositions = _refinement_dispositions_for_packet(packet)
        lines = [f"{record_id}: {disposition}" for record_id, disposition in dispositions.items()]
        return "\n".join(
            [
                "Dispositions:",
                *lines,
                "Rationale: personal-data retention dominates when age is over 180 days; requester tier is not treated as decisive.",
            ]
        )
    return answers.get(packet_id, "Owner role: role.org_evolver. Route to role.evaluator with evidence refs and bounded closure.")


def _score_workload_probe(packet: dict[str, Any], artifact_text: str) -> dict[str, Any]:
    packet_id = packet["packet_id"]
    packet_class = packet.get("class")
    text = artifact_text.lower()
    if packet_class == "refinement":
        expected = _refinement_dispositions_for_packet(packet)
        score = 0
        for record_id, disposition in expected.items():
            if f"{record_id.lower()}: {disposition.lower()}" in text:
                score += 10
        max_score = len(expected) * 10
    elif packet_class == "memory":
        spec = _hidden_memory_key()[packet_id]
        cited = spec["required_citation"].lower() in text
        score = 0
        if cited:
            score += 10
            for keywords in spec["lines"].values():
                if any(keyword in text for keyword in keywords):
                    score += 5
        max_score = 20
    elif packet_class == "prune":
        spec = _hidden_prune_key()[packet_id]
        score = 0
        if f'"outcome":"{spec["outcome"]}"' in text.replace(" ", ""):
            score += 10
        for keywords in spec["lines"].values():
            if any(keyword in text for keyword in keywords):
                score += 5
        max_score = 20
    else:
        spec = _hidden_checklist_key().get(packet_id, {})
        score = 0
        for keywords in spec.values():
            if any(keyword in text for keyword in keywords):
                score += 5
        max_score = max(20, len(spec) * 5)
    return {
        "score": score,
        "max_score": max_score,
        "visible_feedback": (
            "Score total is returned without rubric lines or answer keys. "
            "Operator-only detail stays outside firm-visible state."
        ),
    }


def _refinement_dispositions_for_packet(packet: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for record in packet.get("records") or []:
        record_id = str(record["record_id"])
        age = int(record["age_days"])
        flags = int(record["flag_count"])
        personal = bool(record["personal_data"])
        if personal and age > 180:
            disposition = "ESCALATE"
        elif flags >= 3:
            disposition = "EXPEDITE"
        elif age > 365:
            disposition = "ARCHIVE"
        elif age <= 30 and flags >= 1:
            disposition = "EXPEDITE"
        else:
            disposition = "STANDARD"
        out[record_id] = disposition
    return out


def _hidden_checklist_key() -> dict[str, dict[str, list[str]]]:
    return {
        "IN-01": {"primary": ["facilities"], "complication": ["contractor"], "secondary": ["security"], "next": ["monday", "badge"]},
        "IN-02": {"primary": ["facilities"], "complication": ["10", "cap"], "secondary": ["split", "freight"], "next": ["friday"]},
        "IN-03": {"primary": ["facilities"], "complication": ["generator", "self-test"], "secondary": ["confirm", "correlat"], "next": ["vendor", "dispatch"]},
        "IN-04": {"primary": ["records"], "complication": ["legal", "hw-2025-031", "hold"], "secondary": ["exclude", "eight"], "next": ["friday", "audit"]},
        "CF-01": {"decision": ["decision"], "fact": ["maintenance", "inspection"], "claims": ["iglesias", "marta"], "ledger": ["l-2241", "ledger"]},
        "CF-02": {"decision": ["osei"], "fact": ["ledger"], "learning": ["le-001", "system of record"], "remedy": ["file", "entry"]},
        "CF-03": {"decision": ["records"], "fact": ["refused", "24"], "claim": ["vendor"], "remedy": ["monday", "reschedule"]},
        "CF-04": {"decision": ["deny"], "fact": ["lease"], "remedy": ["renewal", "vendor liaison"], "cost": ["no capital", "no cost"]},
    }


def _hidden_memory_key() -> dict[str, dict[str, Any]]:
    return {
        "ME-01": {"required_citation": "LE-001", "lines": {"decline": ["cannot confirm", "no ledger"], "remedy": ["file", "ledger entry"]}},
        "ME-02": {"required_citation": "LE-002", "lines": {"cc": ["site manager", "cc"], "recipient": ["vertex"]}},
        "ME-03": {"required_citation": "LE-003", "lines": {"split": ["500", "batch"], "pagination": ["pagination", "sequential"]}},
        "ME-04": {"required_citation": "LE-004", "lines": {"log": ["sensor log", "24"], "withhold": ["before filing", "do not file", "incomplete"]}},
    }


def _hidden_prune_key() -> dict[str, dict[str, Any]]:
    return {
        "PR-01": {"outcome": "retire", "lines": {"fact": ["decommission", "terminated"], "routine": ["rr-007"]}},
        "PR-02": {"outcome": "retire", "lines": {"fact": ["auto-export", "nightly", "badge system"], "routine": ["rr-012"]}},
        "PR-03": {"outcome": "amend", "lines": {"fact": ["incident", "excursion", "le-004"], "routine": ["rr-019"]}},
        "PR-04": {"outcome": "retire", "lines": {"fact": ["pickup", "zero", "intranet"], "routine": ["rr-023"]}},
    }


def _select_evolution_steps(
    demo_firm: Path,
    *,
    iterations: int,
    planner_transport: str,
    model_id: str | None,
    planner_command: str | None,
    planner_runtime: str | None = None,
    planner_adapter: str = "auto",
    planner_prompt_mode: str = "full",
    planner_timeout_seconds: int = 600,
) -> list[EvolutionStep]:
    return _select_evolution_plan(
        demo_firm,
        iterations=iterations,
        planner_transport=planner_transport,
        model_id=model_id,
        planner_command=planner_command,
        planner_runtime=planner_runtime,
        planner_adapter=planner_adapter,
        planner_prompt_mode=planner_prompt_mode,
        planner_timeout_seconds=planner_timeout_seconds,
    ).steps


def _selection_with_workload_probe_evidence(
    selection: PlannerSelection,
    workload_probe: dict[str, Any],
) -> PlannerSelection:
    if workload_probe.get("schema") != "workload_probe_execution.v1":
        return selection
    refs = [
        "file://reports/workload-probes/workload-probe-summary.json",
        "file://org/workload/executions/README.md",
    ]
    evidence_refs = _dedupe_preserve_order([*selection.evidence_refs, *refs])
    return PlannerSelection(
        steps=selection.steps,
        receipts=selection.receipts,
        evidence_refs=evidence_refs,
    )


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _select_evolution_plan(
    demo_firm: Path,
    *,
    iterations: int,
    planner_transport: str,
    model_id: str | None,
    planner_command: str | None,
    planner_runtime: str | None = None,
    planner_adapter: str = "auto",
    planner_prompt_mode: str = "full",
    planner_timeout_seconds: int = 600,
) -> PlannerSelection:
    if planner_transport == "fixture":
        steps = _fixture_evolution_steps(iterations)
        return _planner_selection_with_receipt(
            demo_firm,
            transport="fixture",
            steps=steps,
            prompt=None,
            response=json.dumps({"steps": [asdict(step) for step in steps]}, sort_keys=True),
            metadata={"source": "built_in_fixture"},
        )
    if planner_transport == "api":
        return _api_evolution_plan(
            demo_firm,
            iterations=iterations,
            model_id=model_id,
            prompt_mode=planner_prompt_mode,
        )
    if planner_transport == "subscription_cli":
        if not planner_command and not planner_runtime:
            raise RuntimeError(
                "--agent-planner-command or --agent-planner-runtime is required "
                "for subscription_cli planner transport"
            )
        return _agent_cli_evolution_plan(
            demo_firm,
            iterations=iterations,
            planner_command=planner_command,
            planner_runtime=planner_runtime,
            planner_adapter=planner_adapter,
            prompt_mode=planner_prompt_mode,
            timeout_seconds=planner_timeout_seconds,
        )
    raise ValueError(f"unknown planner_transport: {planner_transport}")


def _api_evolution_plan(
    demo_firm: Path,
    *,
    iterations: int,
    model_id: str | None,
    prompt_mode: str = "full",
) -> PlannerSelection:
    model = model_id or pick_model_for_tier("mid") or pick_model_for_tier("cheap")
    if not model:
        raise RuntimeError(
            "--llm mode requires ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY, "
            "or an explicit --model-id with matching credentials."
        )
    prompt = _llm_evolution_prompt(
        demo_firm,
        iterations=iterations,
        prompt_mode=prompt_mode,
    )
    response = LLMRuntime().call_text(
        prompt,
        model_id=model,
        max_tokens=5000,
        retries=1,
        timeout_seconds=180,
        request_label="self-evolving-org-demo-planner",
    )
    try:
        steps = _parse_llm_evolution_steps(response.text, max_steps=iterations)
    except Exception as exc:
        report = _write_planner_rejection_report(
            demo_firm,
            transport="api",
            prompt=prompt,
            response=response.text,
            metadata={"model_id": model, "request_label": "self-evolving-org-demo-planner"},
            reason=str(exc),
        )
        stage_all(demo_firm)
        commit(demo_firm, "record rejected api planner output")
        raise PlannerRejectionError(report) from exc
    return _planner_selection_with_receipt(
        demo_firm,
        transport="api",
        steps=steps,
        prompt=prompt,
        response=response.text,
        metadata={"model_id": model, "request_label": "self-evolving-org-demo-planner"},
    )


def _api_evolution_steps(
    demo_firm: Path,
    *,
    iterations: int,
    model_id: str | None,
    prompt_mode: str = "full",
) -> list[EvolutionStep]:
    return _api_evolution_plan(
        demo_firm,
        iterations=iterations,
        model_id=model_id,
        prompt_mode=prompt_mode,
    ).steps


def _agent_cli_evolution_plan(
    demo_firm: Path,
    *,
    iterations: int,
    planner_command: str | None,
    planner_runtime: str | None = None,
    planner_adapter: str = "auto",
    prompt_mode: str = "full",
    timeout_seconds: int = 600,
) -> PlannerSelection:
    prompt = _llm_evolution_prompt(
        demo_firm,
        iterations=iterations,
        prompt_mode=prompt_mode,
    )
    command: list[str]
    runtime_stdin: str | None = None
    runtime_prompt_transport: str | None = None
    uses_prompt_file = False
    planner_runtime_adapter = (
        infer_agent_adapter(planner_runtime, requested=planner_adapter)
        if planner_runtime
        else None
    )
    passes_prompt_in_command = False
    if planner_command:
        command = shlex.split(planner_command)
    elif planner_runtime:
        invocation = build_agent_invocation(
            agent_cli=planner_runtime,
            adapter=planner_runtime_adapter or "claude_print",
            prompt=prompt,
            project_root=demo_firm,
        )
        command = invocation.argv
        runtime_stdin = invocation.stdin
        runtime_prompt_transport = invocation.prompt_transport
        passes_prompt_in_command = True
    else:
        command = []
    if not command:
        raise ValueError("planner command is required")
    with tempfile.TemporaryDirectory(prefix="cf-agent-planner-") as raw:
        prompt_file = Path(raw) / "prompt.md"
        prompt_file.write_text(prompt, encoding="utf-8")
        if planner_command:
            command = [
                arg.replace("{prompt_file}", str(prompt_file))
                for arg in command
            ]
            uses_prompt_file = any(str(prompt_file) in arg for arg in command)
            safe_command = [
                "{prompt_file}" if arg == str(prompt_file) else arg
                for arg in command
            ]
        else:
            safe_command = safe_command_for_receipt(command, prompt=prompt)
        try:
            result = subprocess.run(
                command,
                cwd=demo_firm,
                input=(
                    None
                    if uses_prompt_file
                    else runtime_stdin
                    if planner_runtime
                    else None
                    if passes_prompt_in_command
                    else prompt
                ),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=agent_subprocess_env(
                    runtime=infer_subscription_runtime_from_adapter(
                        planner_runtime_adapter or ""
                    ),
                ),
            )
        except FileNotFoundError as exc:
            metadata = build_agent_invocation_receipt(
                command_argv=safe_command,
                prompt=prompt,
                runtime=planner_runtime,
                adapter=planner_runtime_adapter,
                prompt_transport=runtime_prompt_transport,
                returncode=None,
                stderr=str(exc),
                used_prompt_file=uses_prompt_file,
                prompt_mode=prompt_mode,
                error=f"planner command not found: {exc.filename}",
            )
            report = _write_planner_rejection_report(
                demo_firm,
                transport="subscription_cli",
                prompt=prompt,
                response="",
                metadata=metadata,
                reason=f"planner command not found: {exc.filename}",
                stderr=str(exc),
            )
            stage_all(demo_firm)
            commit(demo_firm, "record rejected subscription planner output")
            raise PlannerRejectionError(report) from exc
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            metadata = build_agent_invocation_receipt(
                command_argv=safe_command,
                prompt=prompt,
                runtime=planner_runtime,
                adapter=planner_runtime_adapter,
                prompt_transport=runtime_prompt_transport,
                returncode=None,
                stdout=stdout,
                stderr=stderr,
                used_prompt_file=uses_prompt_file,
                timeout_seconds=timeout_seconds,
                prompt_mode=prompt_mode,
                error="planner command timed out",
            )
            report = _write_planner_rejection_report(
                demo_firm,
                transport="subscription_cli",
                prompt=prompt,
                response=stdout,
                metadata=metadata,
                reason="planner command timed out",
                stderr=stderr,
            )
            stage_all(demo_firm)
            commit(demo_firm, "record rejected subscription planner output")
            raise PlannerRejectionError(report) from exc
    metadata = build_agent_invocation_receipt(
        command_argv=safe_command,
        prompt=prompt,
        runtime=planner_runtime,
        adapter=planner_runtime_adapter,
        prompt_transport=runtime_prompt_transport,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        used_prompt_file=uses_prompt_file,
        timeout_seconds=timeout_seconds,
        prompt_mode=prompt_mode,
    )
    if result.returncode != 0:
        reason = _planner_command_failure_reason(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        report = _write_planner_rejection_report(
            demo_firm,
            transport="subscription_cli",
            prompt=prompt,
            response=result.stdout,
            metadata=metadata,
            reason=reason,
            stderr=result.stderr,
        )
        stage_all(demo_firm)
        commit(demo_firm, "record rejected subscription planner output")
        raise PlannerRejectionError(report)
    try:
        steps = _parse_llm_evolution_steps(result.stdout, max_steps=iterations)
    except Exception as exc:
        report = _write_planner_rejection_report(
            demo_firm,
            transport="subscription_cli",
            prompt=prompt,
            response=result.stdout,
            metadata=metadata,
            reason=str(exc),
            stderr=result.stderr,
        )
        stage_all(demo_firm)
        commit(demo_firm, "record rejected subscription planner output")
        raise PlannerRejectionError(report) from exc
    return _planner_selection_with_receipt(
        demo_firm,
        transport="subscription_cli",
        steps=steps,
        prompt=prompt,
        response=result.stdout,
        metadata=metadata,
    )


def _agent_cli_evolution_steps(
    demo_firm: Path,
    *,
    iterations: int,
    planner_command: str | None,
    planner_runtime: str | None = None,
    planner_adapter: str = "auto",
    prompt_mode: str = "full",
    timeout_seconds: int = 600,
) -> list[EvolutionStep]:
    return _agent_cli_evolution_plan(
        demo_firm,
        iterations=iterations,
        planner_command=planner_command,
        planner_runtime=planner_runtime,
        planner_adapter=planner_adapter,
        prompt_mode=prompt_mode,
        timeout_seconds=timeout_seconds,
    ).steps


def _planner_command_failure_reason(
    *,
    returncode: int,
    stdout: str,
    stderr: str,
) -> str:
    combined = f"{stdout}\n{stderr}".lower()
    if "not logged in" in combined or "please run /login" in combined:
        return "planner command requires local agent login"
    if "failed to initialize" in combined and "app-server" in combined:
        return "planner command runtime initialization failed"
    return f"planner command exited {returncode}"


def _planner_selection_with_receipt(
    demo_firm: Path,
    *,
    transport: str,
    steps: list[EvolutionStep],
    prompt: str | None,
    response: str,
    metadata: dict[str, Any],
) -> PlannerSelection:
    receipt = _write_planner_receipt(
        demo_firm,
        transport=transport,
        steps=steps,
        prompt=prompt,
        response=response,
        metadata=metadata,
    )
    _attest_agent_planner_receipt(
        demo_firm,
        receipt=receipt,
        metadata=metadata,
    )
    return PlannerSelection(
        steps=steps,
        receipts=[receipt],
        evidence_refs=list(receipt["evidence_refs"]),
    )


def _attest_agent_planner_receipt(
    demo_firm: Path,
    *,
    receipt: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    """Record live agent planner receipts in the canonical attestation ledger."""
    if metadata.get("schema_version") != "agent_invocation_receipt.v1":
        return
    receipt_id = str(receipt.get("receipt_id") or "")
    if not receipt_id:
        return
    artifact_refs = [
        str(ref)
        for ref in receipt.get("artifact_refs", [])
        if isinstance(ref, str)
    ]
    prompt_ref = next(
        (ref for ref in artifact_refs if ref.endswith("/prompt.md")),
        None,
    )
    output_refs = [
        ref
        for ref in artifact_refs
        if ref.endswith("/response.txt") or ref.endswith("/steps.json")
    ]
    create_action_attestation(
        subject_kind="runtime_event",
        subject_ref=f"planner_receipt:{receipt_id}",
        subject_digest=digest_text(json.dumps(receipt, sort_keys=True)),
        producer="role.org_evolver",
        action_type="agent_cli_dispatch",
        runtime_ref=f"planner:{metadata.get('runtime') or 'subscription_cli'}",
        tool_ref=str(metadata.get("adapter") or "agent_cli"),
        input_refs=[prompt_ref] if prompt_ref else [],
        output_refs=output_refs,
        verification_status="verified",
        verification_summary=(
            "Live planner invocation receipt was captured and parsed into "
            "bounded evolution steps."
        ),
        metadata={
            "demo": "self_evolving_org",
            "planner_receipt_id": receipt_id,
            "agent_invocation_receipt": metadata,
        },
        log_path=demo_firm
        / "org"
        / "attestations"
        / "action_attestations"
        / "action_attestations.jsonl",
    )


def _run_live_reviewer(
    *,
    demo_firm: Path,
    step: EvolutionStep,
    reviewer: ReviewerRuntimeConfig,
    role_id: str,
    actor_id: str,
    a2a_ref: str,
    a2a_message_id: str,
    review_kind: str,
    default_rationale: str,
    run_id: str,
    phase_plan_id: str,
    evidence_refs: list[str],
) -> ReviewPosition:
    """Invoke a reviewer runtime and convert output into advisory evidence."""

    adapter = infer_agent_adapter(reviewer.runtime, requested=reviewer.adapter)
    prompt = _reviewer_prompt(
        step=step,
        role_id=role_id,
        review_kind=review_kind,
        prompt_mode=reviewer.prompt_mode,
        evidence_refs=evidence_refs,
    )
    invocation = build_agent_invocation(
        agent_cli=reviewer.runtime,
        adapter=adapter,
        prompt=prompt,
        project_root=demo_firm,
    )
    stdout = ""
    stderr = ""
    returncode: int | None = None
    error: str | None = None
    try:
        result = subprocess.run(
            invocation.argv,
            cwd=demo_firm,
            input=invocation.stdin,
            capture_output=True,
            text=True,
            timeout=reviewer.timeout_seconds,
            env=agent_subprocess_env(
                runtime=infer_subscription_runtime_from_adapter(adapter),
            ),
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        returncode = result.returncode
    except FileNotFoundError as exc:
        stderr = str(exc)
        error = f"reviewer command not found: {exc.filename}"
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        error = f"reviewer runtime timed out after {reviewer.timeout_seconds} seconds"

    parsed_position = "abstain"
    parsed_rationale = (
        f"{role_id} could not provide a valid live review; treating as abstention."
    )
    parsed_metadata: dict[str, Any] = {}
    if returncode == 0 and error is None:
        try:
            parsed = _parse_live_reviewer_output(stdout)
            parsed_position = parsed["position"]
            parsed_rationale = parsed["rationale"]
            parsed_metadata = parsed
        except Exception as exc:
            error = f"invalid reviewer output: {exc}"
    if parsed_position == "approve" and not parsed_rationale.strip():
        parsed_rationale = default_rationale

    receipt = build_agent_invocation_receipt(
        command_argv=safe_command_for_receipt(invocation.argv, prompt=prompt),
        prompt=prompt,
        runtime=reviewer.runtime,
        adapter=adapter,
        prompt_transport=invocation.prompt_transport,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timeout_seconds=reviewer.timeout_seconds,
        prompt_mode=reviewer.prompt_mode,
        error=error,
    )
    artifact_refs = _write_reviewer_artifacts(
        demo_firm,
        step_id=step.step_id,
        role_id=role_id,
        prompt=prompt,
        stdout=stdout,
        stderr=stderr,
        receipt=receipt,
        parsed={
            "position": parsed_position,
            "rationale": parsed_rationale,
            **parsed_metadata,
        },
    )
    verification_status = (
        "verified" if returncode == 0 and error is None and parsed_position in {"approve", "abstain", "reject"} else "failed"
    )
    attestation = create_action_attestation(
        subject_kind="runtime_event",
        subject_ref=a2a_ref,
        subject_digest=digest_text(json.dumps(receipt, sort_keys=True)),
        producer=role_id,
        action_type="agent_cli_dispatch",
        runtime_ref=f"reviewer:{reviewer.runtime}",
        tool_ref=adapter,
        input_refs=[artifact_refs["prompt_ref"], *evidence_refs],
        output_refs=[artifact_refs["stdout_ref"], artifact_refs["review_ref"]],
        verification_status=verification_status,
        verification_summary=(
            f"Live reviewer emitted advisory position {parsed_position}."
            if verification_status == "verified"
            else parsed_rationale
        ),
        run_id=run_id,
        metadata={
            "demo": "self_evolving_org",
            "step_id": step.step_id,
            "phase_execution_plan_id": phase_plan_id,
            "a2a_message_id": a2a_message_id,
            "review_kind": review_kind,
            "review_position": parsed_position,
            "review_rationale": parsed_rationale,
            "agent_invocation_receipt": receipt,
        },
        log_path=demo_firm
        / "org"
        / "attestations"
        / "action_attestations"
        / "action_attestations.jsonl",
    )
    attestation_ref = f"attestation:{attestation.attestation_id}"
    return ReviewPosition(
        actor_id=actor_id,
        role_id=role_id,
        position=parsed_position,
        rationale=parsed_rationale,
        evidence_refs=[
            a2a_ref,
            attestation_ref,
            artifact_refs["review_ref"],
            artifact_refs["stdout_ref"],
        ],
        invocation={
            "attestation_id": attestation.attestation_id,
            "attestation_ref": attestation_ref,
            "review_kind": review_kind,
            "runtime": reviewer.runtime,
            "adapter": adapter,
            "timeout_seconds": reviewer.timeout_seconds,
            "prompt_mode": reviewer.prompt_mode,
            "artifact_refs": artifact_refs,
            "input_refs": [artifact_refs["prompt_ref"], *evidence_refs],
            "output_refs": [artifact_refs["stdout_ref"], artifact_refs["review_ref"]],
            "verification_status": verification_status,
        },
    )


def _reviewer_prompt(
    *,
    step: EvolutionStep,
    role_id: str,
    review_kind: str,
    prompt_mode: str,
    evidence_refs: list[str],
) -> str:
    compact = prompt_mode == "compact"
    lines = [
        "You are acting as a cognitive-firm reviewer office.",
        f"Role: {role_id}",
        f"Review kind: {review_kind}",
        "",
        "Return only JSON with this schema:",
        '{"position":"approve|abstain|reject","rationale":"one concise sentence","evidence_summary":"optional concise note"}',
        "",
        "You are advisory. Do not request tools unless needed. Do not mutate files.",
        "Prefer abstain when evidence is insufficient or authority is unclear.",
        "",
        f"Step id: {step.step_id}",
        f"Title: {step.title}",
        f"Change kind: {step.change_kind}",
        f"Target ref: {step.target_ref}",
        f"Rationale: {step.rationale}",
        f"Expected behavior change: {step.expected_behavior_change}",
        f"Risk summary: {step.risk_summary}",
        f"Rollback plan: {step.rollback_plan}",
        f"Evidence refs: {', '.join(evidence_refs)}",
    ]
    if not compact:
        lines.extend(
            [
                "",
                "Decision guidance:",
                "- approve only if the change is bounded and evidence-carrying;",
                "- abstain if you lack enough evidence;",
                "- reject if it expands authority, weakens review, or lacks rollback.",
            ]
        )
    return "\n".join(lines) + "\n"


def _parse_live_reviewer_output(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise ValueError("empty stdout")
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("no JSON object found")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("reviewer output must be a JSON object")
    position = str(payload.get("position") or "").strip().lower()
    if position not in {"approve", "abstain", "reject"}:
        raise ValueError("position must be approve, abstain, or reject")
    rationale = str(payload.get("rationale") or "").strip()
    if not rationale:
        raise ValueError("rationale is required")
    return {
        "position": position,
        "rationale": rationale,
        "evidence_summary": str(payload.get("evidence_summary") or "").strip(),
    }


def _write_reviewer_artifacts(
    demo_firm: Path,
    *,
    step_id: str,
    role_id: str,
    prompt: str,
    stdout: str,
    stderr: str,
    receipt: dict[str, Any],
    parsed: dict[str, Any],
) -> dict[str, str]:
    slug = role_id.replace("role.", "").replace(".", "_")
    base = demo_firm / "reports" / "reviewers" / step_id / slug
    base.mkdir(parents=True, exist_ok=True)
    (base / "prompt.md").write_text(prompt, encoding="utf-8")
    (base / "stdout.txt").write_text(stdout, encoding="utf-8")
    (base / "stderr.txt").write_text(stderr, encoding="utf-8")
    (base / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (base / "review.json").write_text(
        json.dumps(parsed, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    prefix = f"file://reports/reviewers/{step_id}/{slug}"
    return {
        "prompt_ref": f"{prefix}/prompt.md",
        "stdout_ref": f"{prefix}/stdout.txt",
        "stderr_ref": f"{prefix}/stderr.txt",
        "receipt_ref": f"{prefix}/receipt.json",
        "review_ref": f"{prefix}/review.json",
    }


def _write_planner_receipt(
    demo_firm: Path,
    *,
    transport: str,
    steps: list[EvolutionStep],
    prompt: str | None,
    response: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "transport": transport,
        "step_ids": [step.step_id for step in steps],
        "prompt_digest": digest_text(prompt or ""),
        "response_digest": digest_text(response),
        "steps_digest": digest_text(json.dumps([asdict(step) for step in steps], sort_keys=True)),
        "metadata": metadata,
    }
    receipt_hex = digest_text(json.dumps(payload, sort_keys=True)).split(":", 1)[-1]
    receipt_id = f"planner_{transport}_{receipt_hex[:12]}"
    receipt_dir = demo_firm / "reports" / "planner" / receipt_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    if prompt is not None:
        (receipt_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    (receipt_dir / "response.txt").write_text(response, encoding="utf-8")
    (receipt_dir / "steps.json").write_text(
        json.dumps([asdict(step) for step in steps], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt = {
        "receipt_id": receipt_id,
        **payload,
        "artifact_refs": [
            f"file://reports/planner/{receipt_id}/response.txt",
            f"file://reports/planner/{receipt_id}/steps.json",
        ],
        "evidence_refs": [
            f"planner_receipt:{receipt_id}",
            f"file://reports/planner/{receipt_id}/response.txt",
            f"file://reports/planner/{receipt_id}/steps.json",
        ],
    }
    if prompt is not None:
        receipt["artifact_refs"].append(f"file://reports/planner/{receipt_id}/prompt.md")
        receipt["evidence_refs"].append(f"file://reports/planner/{receipt_id}/prompt.md")
    (receipt_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def _write_planner_rejection_report(
    demo_firm: Path,
    *,
    transport: str,
    prompt: str | None,
    response: str,
    metadata: dict[str, Any],
    reason: str,
    stderr: str = "",
) -> dict[str, Any]:
    payload = {
        "status": "rejected",
        "transport": transport,
        "prompt_digest": digest_text(prompt or ""),
        "response_digest": digest_text(response),
        "stderr_digest": digest_text(stderr),
        "metadata": metadata,
        "reason": reason,
    }
    receipt_hex = digest_text(json.dumps(payload, sort_keys=True)).split(":", 1)[-1]
    receipt_id = f"planner_{transport}_rejected_{receipt_hex[:12]}"
    receipt_dir = demo_firm / "reports" / "planner" / receipt_id
    receipt_dir.mkdir(parents=True, exist_ok=True)
    if prompt is not None:
        (receipt_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    (receipt_dir / "response.txt").write_text(response, encoding="utf-8")
    (receipt_dir / "stderr.txt").write_text(stderr, encoding="utf-8")
    (receipt_dir / "error.txt").write_text(reason + "\n", encoding="utf-8")
    receipt = {
        "receipt_id": receipt_id,
        **payload,
        "artifact_refs": [
            f"file://reports/planner/{receipt_id}/response.txt",
            f"file://reports/planner/{receipt_id}/stderr.txt",
            f"file://reports/planner/{receipt_id}/error.txt",
        ],
        "evidence_refs": [
            f"planner_receipt:{receipt_id}",
            f"file://reports/planner/{receipt_id}/response.txt",
            f"file://reports/planner/{receipt_id}/stderr.txt",
            f"file://reports/planner/{receipt_id}/error.txt",
        ],
    }
    if prompt is not None:
        receipt["artifact_refs"].append(f"file://reports/planner/{receipt_id}/prompt.md")
        receipt["evidence_refs"].append(f"file://reports/planner/{receipt_id}/prompt.md")
    (receipt_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = {
        "demo": "self_evolving_org",
        "status": "planner_rejected",
        "no_external_calls": transport == "fixture",
        "planner_transport": transport,
        "demo_firm": str(demo_firm),
        "planner_receipts": [receipt],
        "summary": {
            "verdict": "blocked",
            "reason": reason,
            "mutations_applied": 0,
            "planner_receipts": 1,
        },
    }
    reports_dir = demo_firm / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "self-evolving-org-planner-rejection.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports_dir / "self-evolving-org-planner-rejection.md").write_text(
        _render_planner_rejection_markdown(report),
        encoding="utf-8",
    )
    return report


def _render_planner_rejection_markdown(report: dict[str, Any]) -> str:
    receipt = report["planner_receipts"][0]
    return "\n".join(
        [
            "# Self-Evolving Organization Planner Rejection",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| Verdict | {_md(report['summary']['verdict'])} |",
            f"| Transport | {_md(report['planner_transport'])} |",
            f"| Reason | {_md(report['summary']['reason'])} |",
            f"| Receipt | {_md(receipt['receipt_id'])} |",
            f"| Response digest | {_md(receipt['response_digest'])} |",
            f"| Stderr digest | {_md(receipt['stderr_digest'])} |",
            "",
            "No governance proposal was opened and no organization mutation was applied.",
            "",
        ]
    )


def _llm_evolution_prompt(
    demo_firm: Path,
    *,
    iterations: int,
    prompt_mode: str = "full",
) -> str:
    if prompt_mode not in {"full", "compact"}:
        raise ValueError("planner prompt mode must be full or compact")
    org_files = []
    for path in sorted((demo_firm / "org").rglob("*"), key=_planner_context_sort_key):
        if path.is_file() and path.suffix in {".md", ".yaml", ".yml", ".json"}:
            rel = path.relative_to(demo_firm)
            text = path.read_text(encoding="utf-8")
            limit = 650 if prompt_mode == "compact" else 1800
            org_files.append(f"--- {rel} ---\n{text[:limit]}")
    context_limit = 10 if prompt_mode == "compact" else 24
    context = "\n\n".join(org_files[:context_limit])
    compact_note = ""
    if prompt_mode == "compact":
        compact_note = (
            "\nLive-smoke mode: choose one conservative charter, mandate, or policy "
            "clarification. Prefer a short markdown file under org/charters/, "
            "org/mandates/, or org/policies/. Do not create new roles unless "
            "necessary.\n"
        )
    workload_context = _planner_workload_evidence_context(demo_firm)
    workload_section = (
        f"\nCurrent workload evidence:\n{workload_context}\n"
        if workload_context
        else ""
    )
    return f"""You are proposing bounded organization-structure improvements for a cognitive-firm demo.

Return ONLY JSON. No markdown, no prose outside JSON.

Goal: propose up to {max(1, iterations)} structural changes that help this starter firm
improve workload capability: trailing workload score per dispatched budget unit, with
error, incident, and unresolved-authority-gap counts as guard metrics. Favor changes
that are justified by the genesis workload packets or current execution evidence, and
that sharpen office coordination, decision rights, evaluation, learning, or governance
while preserving authority boundaries.
{compact_note}

Constraints:
- Use only these change_kind values: mandate_change, role_change, project_charter_change,
  learning_policy_change.
- target_ref/applied_relpath must stay under one of:
  - org/charters/*.md
  - org/mandates/*.md
  - org/roles/*.yaml
  - org/policies/*.md
- Do not expand role authority or grant external capabilities.
- Do not read, infer, or optimize against any hidden scoring rubric. Use the visible
  workload packets and capability contract only.
- Every proposed change must state a falsifiable predicted effect on capability or
  guard metrics and name a review horizon in the rationale or expected behavior.
- If adding an office, policy, or protocol, name a retirement candidate or justify net
  growth to the principal.
- For role_change applied_text, YAML must declare a role.* role_id and may only use
  authorized_paths under org/charters/, org/mandates/, org/policies/, org/reviews/,
  or org/roles/. Do not declare tools, MCP capabilities, secrets, credentials, or
  environment fields.
- Every change must include rationale, expected_behavior_change, risk_summary, rollback_plan,
  and complete applied_text for the target file.
- Keep changes general-purpose, not tied to a single industry.
- The governance kernel will still require proposal, approval, attestation, learning,
  outcome link, routine review, bundle validation, and git commit before mutation is accepted.
{workload_section}

JSON schema:
{{
  "steps": [
    {{
      "step_id": "short_snake_case",
      "title": "short title",
      "change_kind": "mandate_change|role_change|project_charter_change|learning_policy_change",
      "target_ref": "org/...",
      "rationale": "...",
      "expected_behavior_change": "...",
      "risk_summary": "...",
      "rollback_plan": "...",
      "applied_relpath": "org/...",
      "applied_text": "full file content"
    }}
  ]
}}

Current starter firm context:
{context}
"""


def _planner_workload_evidence_context(demo_firm: Path) -> str:
    summary_path = demo_firm / "reports" / "workload-probes" / "workload-probe-summary.json"
    if not summary_path.exists():
        return ""
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    summary = payload.get("summary") or {}
    if not isinstance(summary, dict):
        return ""
    lines = [
        "- Evidence carrier: file://reports/workload-probes/workload-probe-summary.json",
        "- Visible receipt index: file://org/workload/executions/README.md",
        f"- Workload packets: {summary.get('packet_count', 0)}",
        f"- Total budget units: {summary.get('total_budget_units', 0)}",
        f"- Feedback visibility: {summary.get('feedback_visibility', 'unknown')}",
        f"- Firm received score totals: {str(summary.get('firm_received_scores', False)).lower()}",
        f"- Rubric visible to firm: {str(summary.get('rubric_visible_to_firm', False)).lower()}",
        f"- Live executor packets: {summary.get('live_executor_packets', 0)}",
    ]
    if summary.get("firm_received_scores"):
        lines.extend(
            [
                f"- Visible total score: {summary.get('total_score')}",
                f"- Visible max score: {summary.get('total_max_score')}",
                "- Visible capability score per budget unit: "
                f"{summary.get('capability_score_per_budget_unit')}",
            ]
        )
    else:
        lines.append(
            "- Numeric score totals are withheld from firm-visible state; do not "
            "cite operator-only score values as proposal evidence."
        )
    lines.append(
        "- Use these refs when making measurement claims; do not infer hidden "
        "rubric lines or operator-only scorecards."
    )
    return "\n".join(lines)


def _planner_context_sort_key(path: Path) -> tuple[int, str]:
    text = path.as_posix()
    if text.endswith("org/charters/self_evolving_firm.md"):
        return (0, text)
    if "/org/charters/" in text:
        return (1, text)
    if text.endswith("org/mandates/org_evolver_mandate.md"):
        return (2, text)
    if "/org/mandates/" in text:
        return (3, text)
    if "/org/roles/" in text:
        return (4, text)
    if "/org/policies/" in text:
        return (5, text)
    return (9, text)


def _parse_llm_evolution_steps(text: str, *, max_steps: int) -> list[EvolutionStep]:
    payload = _extract_json_object(text)
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("LLM response must contain a non-empty steps array")
    steps = []
    seen_step_ids: set[str] = set()
    for index, raw in enumerate(raw_steps[: max(1, max_steps)], start=1):
        if not isinstance(raw, dict):
            raise ValueError("each LLM step must be an object")
        step_id = _safe_step_id(str(raw.get("step_id") or f"llm_step_{index}"))
        if step_id in seen_step_ids:
            raise ValueError(f"duplicate LLM step_id: {step_id}")
        seen_step_ids.add(step_id)
        change_kind = _validate_llm_change_kind(str(raw.get("change_kind") or ""))
        relpath = _validate_llm_relpath(str(raw.get("applied_relpath") or raw.get("target_ref") or ""))
        target_ref = _validate_llm_relpath(str(raw.get("target_ref") or relpath))
        if relpath != target_ref:
            raise ValueError("target_ref and applied_relpath must match in --llm mode")
        _validate_llm_target_matches_change_kind(change_kind, relpath)
        applied_text = str(raw.get("applied_text") or "").strip()
        if not applied_text:
            raise ValueError(f"LLM step {step_id} missing applied_text")
        _validate_llm_applied_text(change_kind, relpath, applied_text)
        steps.append(
            EvolutionStep(
                step_id=step_id,
                title=_required_text(raw.get("title"), f"{step_id}.title"),
                change_kind=change_kind,
                target_ref=target_ref,
                rationale=_required_text(raw.get("rationale"), f"{step_id}.rationale"),
                expected_behavior_change=_required_text(
                    raw.get("expected_behavior_change"),
                    f"{step_id}.expected_behavior_change",
                ),
                risk_summary=_required_text(raw.get("risk_summary"), f"{step_id}.risk_summary"),
                rollback_plan=_required_text(raw.get("rollback_plan"), f"{step_id}.rollback_plan"),
                work_kind=_work_kind_for_change_kind(change_kind),
                work_payload={"llm_step_id": step_id, "target_ref": target_ref},
                applied_relpath=relpath,
                applied_text=applied_text + "\n",
                metric_baseline=float(len(raw_steps) - index + 1),
                metric_post=float(max(0, len(raw_steps) - index)),
            )
        )
    return steps


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM response JSON must be an object")
    return payload


def _validate_llm_change_kind(value: str) -> str:
    valid = {
        "mandate_change",
        "role_change",
        "project_charter_change",
        "learning_policy_change",
    }
    if value not in valid:
        raise ValueError(f"unsupported LLM change_kind: {value}")
    return value


def _validate_llm_relpath(value: str) -> str:
    path = value.strip()
    if path.startswith("/") or ".." in Path(path).parts:
        raise ValueError(f"unsafe LLM target path: {value}")
    allowed = (
        path.startswith("org/charters/") and path.endswith(".md"),
        path.startswith("org/mandates/") and path.endswith(".md"),
        path.startswith("org/roles/") and path.endswith(".yaml"),
        path.startswith("org/policies/") and path.endswith(".md"),
    )
    if not any(allowed):
        raise ValueError(f"LLM target path is outside the governed demo envelope: {value}")
    return path


def _validate_llm_target_matches_change_kind(change_kind: str, relpath: str) -> None:
    expected_prefix_suffix = {
        "mandate_change": ("org/mandates/", ".md"),
        "role_change": ("org/roles/", ".yaml"),
        "project_charter_change": ("org/charters/", ".md"),
        "learning_policy_change": ("org/policies/", ".md"),
    }
    prefix, suffix = expected_prefix_suffix[change_kind]
    if not (relpath.startswith(prefix) and relpath.endswith(suffix)):
        raise ValueError(
            f"{change_kind} must target {prefix}*{suffix}; got {relpath}"
        )


def _validate_llm_applied_text(change_kind: str, relpath: str, applied_text: str) -> None:
    if len(applied_text.encode("utf-8")) > 12_000:
        raise ValueError(f"LLM step {relpath} applied_text is too large")
    if change_kind == "role_change":
        _validate_llm_role_yaml(applied_text, relpath=relpath)


def _validate_llm_role_yaml(applied_text: str, *, relpath: str) -> None:
    try:
        parsed = yaml.safe_load(applied_text)
    except yaml.YAMLError as exc:
        raise ValueError(f"LLM role YAML is invalid for {relpath}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"LLM role YAML must be a mapping for {relpath}")
    forbidden_keys = {
        "authorized_mcp_capabilities",
        "authorized_mcp_servers",
        "capabilities",
        "credentials",
        "env",
        "external_tools",
        "mcp",
        "secrets",
        "tools",
    }
    present_forbidden = sorted(forbidden_keys & {str(key) for key in parsed})
    if present_forbidden:
        raise ValueError(
            "LLM role YAML cannot declare external capability or secret fields: "
            + ", ".join(present_forbidden)
        )
    role_id = str(parsed.get("role_id") or "").strip()
    if not role_id.startswith("role."):
        raise ValueError(f"LLM role YAML must declare a role.* role_id for {relpath}")
    authorized_paths = parsed.get("authorized_paths") or []
    if not isinstance(authorized_paths, list):
        raise ValueError(f"LLM role YAML authorized_paths must be a list for {relpath}")
    for item in authorized_paths:
        path = str(item or "").strip()
        if not path:
            raise ValueError(f"LLM role YAML has an empty authorized path for {relpath}")
        _validate_demo_authorized_path(path, relpath=relpath)


def _validate_demo_authorized_path(path: str, *, relpath: str) -> None:
    if path.startswith("/") or ".." in Path(path).parts:
        raise ValueError(f"unsafe authorized path in {relpath}: {path}")
    if path in {"*", "**"}:
        raise ValueError(f"wildcard authorized path is not allowed in {relpath}")
    allowed_prefixes = (
        "org/charters/",
        "org/mandates/",
        "org/policies/",
        "org/reviews/",
        "org/roles/",
    )
    if not path.startswith(allowed_prefixes):
        raise ValueError(
            f"authorized path in {relpath} must stay under demo org governance paths: {path}"
        )


def _safe_step_id(value: str) -> str:
    safe = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")
    if not safe:
        raise ValueError("step_id is required")
    return safe[:64]


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _work_kind_for_change_kind(change_kind: str) -> str:
    if change_kind == "role_change":
        return "role_design"
    if change_kind == "project_charter_change":
        return "charter_design"
    if change_kind == "learning_policy_change":
        return "learning_cadence"
    return "org_diagnosis"


def _simulation_tick(index: int, step: EvolutionStep) -> dict[str, Any]:
    return {
        "clock_kind": "bounded_harness_iteration",
        "tick_unit": "governed_iteration",
        "tick_index": index,
        "tick_id": f"tick_{index:04d}",
        "tick_label": f"T+{index:04d}",
        "step_id": step.step_id,
        "planner_step_title": step.title,
        "advances_when": "one proposed structural change finishes its governed path",
    }


def _run_step(
    step: EvolutionStep,
    *,
    config: KernelServiceConfig,
    demo_firm: Path,
    action_attestation_log: Path,
    planner_evidence_refs: list[str],
    simulation_tick: dict[str, Any],
    reviewer_runtime: ReviewerRuntimeConfig | None = None,
) -> dict[str, Any]:
    run = dispatch_kernel_request(
        "POST",
        "/kernel/runs",
        {
            "owner_role": "role.org_evolver",
            "objective": step.title,
            "idempotency_key": f"self-evolving-org:{step.step_id}",
        },
        config=config,
    )
    _assert_status(run.status, 201, f"start run {step.step_id}")
    run_id = run.payload["run"]["run_id"]

    work = dispatch_kernel_request(
        "POST",
        "/kernel/work-items",
        {
            "unit_id": "org_evolution",
            "kind": step.work_kind,
            "owner_role": "role.org_evolver",
            "payload": step.work_payload,
            "idempotency_key": f"work:{step.step_id}",
        },
        config=config,
    )
    _assert_status(work.status, 201, f"enqueue work {step.step_id}")
    work_id = work.payload["work_item"]["work_id"]

    phase_plan = dispatch_kernel_request(
        "POST",
        "/kernel/phase-execution-plans",
        {
            "plan_id": f"pex_{step.step_id}",
            "objective": step.title,
            "owner_role": "role.org_evolver",
            "run_id": run_id,
            "work_id": work_id,
            "metadata": {
                "demo": "self_evolving_org",
                "step_id": step.step_id,
                "simulation_tick": simulation_tick,
            },
            "actor_context": {
                "actor_id": "agent.org_evolver",
                "actor_kind": "agent",
                "role_id": "role.org_evolver",
            },
        },
        config=config,
    )
    _assert_status(phase_plan.status, 201, f"start phase execution {step.step_id}")
    phase_plan_id = phase_plan.payload["plan"]["plan_id"]
    for phase, directive_text in (
        (
            "strategy",
            "Identify the smallest governed structural change that addresses the observed gap.",
        ),
        (
            "execution",
            "Prepare the proposal and approved file mutation without widening authority.",
        ),
    ):
        directive = dispatch_kernel_request(
            "POST",
            f"/kernel/phase-execution-plans/{phase_plan_id}/directives",
            {
                "phase": phase,
                "issued_by": "role.org_evolver",
                "directive": directive_text,
                "run_id": run_id,
                "work_id": work_id,
                "evidence_refs": [
                    f"run:{run_id}",
                    f"work:{work_id}",
                    *planner_evidence_refs,
                ],
                "actor_context": {
                    "actor_id": "agent.org_evolver",
                    "actor_kind": "agent",
                    "role_id": "role.org_evolver",
                },
            },
            config=config,
        )
        _assert_status(directive.status, 201, f"record {phase} directive {step.step_id}")

    review_request = dispatch_kernel_request(
        "POST",
        "/kernel/a2a/messages",
        {
            "from_role": "org_evolver",
            "to_role": "evaluator",
            "kind": "request",
            "subject": f"Review governed structural change: {step.title}",
            "body": (
                "Evaluate the evidence, authority boundary, risk, and rollback "
                "before this structural change is promoted for approval."
            ),
            "expects_response": True,
            "thread_id": f"thread_{step.step_id}",
            "causality_id": run_id,
            "references": [
                f"run:{run_id}",
                f"work:{work_id}",
                f"phase_execution_plan:{phase_plan_id}",
                *planner_evidence_refs,
            ],
            "artifacts": [step.target_ref],
            "metadata": {
                "demo": "self_evolving_org",
                "step_id": step.step_id,
                "review_kind": "pre_promotion_evidence_review",
            },
            "actor_context": {
                "actor_id": "agent.org_evolver",
                "actor_kind": "agent",
                "role_id": "role.org_evolver",
            },
        },
        config=config,
    )
    _assert_status(review_request.status, 201, f"send A2A review request {step.step_id}")
    a2a_message_id = review_request.payload["message"]["message_id"]
    a2a_ref = f"a2a_message:{a2a_message_id}"
    acknowledged_message = dispatch_kernel_request(
        "POST",
        f"/kernel/a2a/messages/{a2a_message_id}/status",
        {
            "role_id": "evaluator",
            "status": "acknowledged",
            "actor": "agent.evaluator",
            "note": "Evaluator opened the structural-change review request.",
            "actor_context": {
                "actor_id": "agent.evaluator",
                "actor_kind": "agent",
                "role_id": "role.evaluator",
            },
        },
        config=config,
    )
    _assert_status(acknowledged_message.status, 200, f"acknowledge A2A review {step.step_id}")
    for state, note in (
        ("accepted", "Evaluator accepted the review obligation."),
        ("in_progress", "Evaluator started evidence and authority review."),
    ):
        lifecycle = dispatch_kernel_request(
            "POST",
            f"/kernel/a2a/messages/{a2a_message_id}/obligation",
            {
                "role_id": "evaluator",
                "state": state,
                "actor": "agent.evaluator",
                "note": note,
                "actor_context": {
                    "actor_id": "agent.evaluator",
                    "actor_kind": "agent",
                    "role_id": "role.evaluator",
                },
            },
            config=config,
        )
        _assert_status(lifecycle.status, 200, f"A2A obligation {state} {step.step_id}")
    risk_review_request = dispatch_kernel_request(
        "POST",
        "/kernel/a2a/messages",
        {
            "from_role": "evaluator",
            "to_role": "risk_guardian",
            "kind": "request",
            "subject": f"Independent risk review: {step.title}",
            "body": (
                "Review authority expansion, recursion risk, rollback quality, "
                "resource envelope, and incentive effects before principal approval."
            ),
            "expects_response": True,
            "thread_id": f"thread_{step.step_id}",
            "causality_id": run_id,
            "references": [
                f"run:{run_id}",
                f"work:{work_id}",
                f"phase_execution_plan:{phase_plan_id}",
                a2a_ref,
                *planner_evidence_refs,
            ],
            "artifacts": [step.target_ref],
            "metadata": {
                "demo": "self_evolving_org",
                "step_id": step.step_id,
                "review_kind": "independent_risk_review",
            },
            "actor_context": {
                "actor_id": "agent.evaluator",
                "actor_kind": "agent",
                "role_id": "role.evaluator",
            },
        },
        config=config,
    )
    _assert_status(
        risk_review_request.status,
        201,
        f"send A2A risk review request {step.step_id}",
    )
    risk_a2a_message_id = risk_review_request.payload["message"]["message_id"]
    risk_a2a_ref = f"a2a_message:{risk_a2a_message_id}"
    risk_acknowledged_message = dispatch_kernel_request(
        "POST",
        f"/kernel/a2a/messages/{risk_a2a_message_id}/status",
        {
            "role_id": "risk_guardian",
            "status": "acknowledged",
            "actor": "agent.risk_guardian",
            "note": "Risk Guardian opened the independent risk review request.",
            "actor_context": {
                "actor_id": "agent.risk_guardian",
                "actor_kind": "agent",
                "role_id": "role.risk_guardian",
            },
        },
        config=config,
    )
    _assert_status(
        risk_acknowledged_message.status,
        200,
        f"acknowledge A2A risk review {step.step_id}",
    )
    for state, note in (
        ("accepted", "Risk Guardian accepted the independent review obligation."),
        ("in_progress", "Risk Guardian started risk, rollback, and authority review."),
    ):
        lifecycle = dispatch_kernel_request(
            "POST",
            f"/kernel/a2a/messages/{risk_a2a_message_id}/obligation",
            {
                "role_id": "risk_guardian",
                "state": state,
                "actor": "agent.risk_guardian",
                "note": note,
                "actor_context": {
                    "actor_id": "agent.risk_guardian",
                    "actor_kind": "agent",
                    "role_id": "role.risk_guardian",
                },
            },
            config=config,
        )
        _assert_status(
            lifecycle.status,
            200,
            f"A2A risk obligation {state} {step.step_id}",
        )
    learning_review_request = dispatch_kernel_request(
        "POST",
        "/kernel/a2a/messages",
        {
            "from_role": "evaluator",
            "to_role": "learning_steward",
            "kind": "request",
            "subject": f"Learning-unit quality review: {step.title}",
            "body": (
                "Review whether the proposed change has a clear future-use cue, "
                "source carrier refs, outcome/review path, and retirement pressure "
                "before the learning unit is accepted."
            ),
            "expects_response": True,
            "thread_id": f"thread_{step.step_id}",
            "causality_id": run_id,
            "references": [
                f"run:{run_id}",
                f"work:{work_id}",
                f"phase_execution_plan:{phase_plan_id}",
                a2a_ref,
                risk_a2a_ref,
                *planner_evidence_refs,
            ],
            "artifacts": [step.target_ref],
            "metadata": {
                "demo": "self_evolving_org",
                "step_id": step.step_id,
                "review_kind": "learning_unit_quality_review",
            },
            "actor_context": {
                "actor_id": "agent.evaluator",
                "actor_kind": "agent",
                "role_id": "role.evaluator",
            },
        },
        config=config,
    )
    _assert_status(
        learning_review_request.status,
        201,
        f"send A2A learning review request {step.step_id}",
    )
    learning_a2a_message_id = learning_review_request.payload["message"]["message_id"]
    learning_a2a_ref = f"a2a_message:{learning_a2a_message_id}"
    learning_acknowledged_message = dispatch_kernel_request(
        "POST",
        f"/kernel/a2a/messages/{learning_a2a_message_id}/status",
        {
            "role_id": "learning_steward",
            "status": "acknowledged",
            "actor": "agent.learning_steward",
            "note": "Learning Steward opened the learning-unit quality review request.",
            "actor_context": {
                "actor_id": "agent.learning_steward",
                "actor_kind": "agent",
                "role_id": "role.learning_steward",
            },
        },
        config=config,
    )
    _assert_status(
        learning_acknowledged_message.status,
        200,
        f"acknowledge A2A learning review {step.step_id}",
    )
    for state, note in (
        ("accepted", "Learning Steward accepted the learning-quality review obligation."),
        ("in_progress", "Learning Steward started cue, source, review, and retirement review."),
    ):
        lifecycle = dispatch_kernel_request(
            "POST",
            f"/kernel/a2a/messages/{learning_a2a_message_id}/obligation",
            {
                "role_id": "learning_steward",
                "state": state,
                "actor": "agent.learning_steward",
                "note": note,
                "actor_context": {
                    "actor_id": "agent.learning_steward",
                    "actor_kind": "agent",
                    "role_id": "role.learning_steward",
                },
            },
            config=config,
        )
        _assert_status(
            lifecycle.status,
            200,
            f"A2A learning obligation {state} {step.step_id}",
        )
    a2a_messages = [
        {
            "message_id": a2a_message_id,
            "ref": a2a_ref,
            "from_role": "org_evolver",
            "to_role": "evaluator",
            "obligation_state": None,
        },
        {
            "message_id": risk_a2a_message_id,
            "ref": risk_a2a_ref,
            "from_role": "evaluator",
            "to_role": "risk_guardian",
            "obligation_state": None,
        },
        {
            "message_id": learning_a2a_message_id,
            "ref": learning_a2a_ref,
            "from_role": "evaluator",
            "to_role": "learning_steward",
            "obligation_state": None,
        },
    ]
    a2a_refs = [message["ref"] for message in a2a_messages]
    default_review_positions = [
        ReviewPosition(
            actor_id="agent.evaluator",
            role_id="role.evaluator",
            position="approve",
            rationale=(
                "Evaluator confirms the review obligation is accepted and no "
                "authority expansion is present."
            ),
            evidence_refs=[a2a_ref],
        ),
        ReviewPosition(
            actor_id="agent.risk_guardian",
            role_id="role.risk_guardian",
            position="approve",
            rationale=(
                "Risk Guardian confirms rollback, recursion, resource, and "
                "incentive risks are bounded."
            ),
            evidence_refs=[risk_a2a_ref],
        ),
        ReviewPosition(
            actor_id="agent.learning_steward",
            role_id="role.learning_steward",
            position="approve",
            rationale=(
                "Learning Steward confirms the future-use cue, source refs, "
                "review cadence, and retirement path are explicit."
            ),
            evidence_refs=[learning_a2a_ref],
        ),
    ]
    review_positions = default_review_positions
    if reviewer_runtime is not None:
        review_positions = [
            _run_live_reviewer(
                demo_firm=demo_firm,
                step=step,
                reviewer=reviewer_runtime,
                role_id=position.role_id,
                actor_id=position.actor_id,
                a2a_ref=position.evidence_refs[0],
                a2a_message_id={
                    "role.evaluator": a2a_message_id,
                    "role.risk_guardian": risk_a2a_message_id,
                    "role.learning_steward": learning_a2a_message_id,
                }[position.role_id],
                review_kind={
                    "role.evaluator": "pre_promotion_evidence_review",
                    "role.risk_guardian": "independent_risk_review",
                    "role.learning_steward": "learning_unit_quality_review",
                }[position.role_id],
                default_rationale=position.rationale,
                run_id=run_id,
                phase_plan_id=phase_plan_id,
                evidence_refs=[
                    f"run:{run_id}",
                    f"work:{work_id}",
                    f"phase_execution_plan:{phase_plan_id}",
                    *a2a_refs,
                    *planner_evidence_refs,
                ],
            )
            for position in default_review_positions
        ]
    reviewer_evidence_refs = [
        ref
        for position in review_positions
        for ref in position.evidence_refs
        if ref not in a2a_refs
    ]
    reviewer_invocations = [
        position.invocation
        for position in review_positions
        if position.invocation is not None
    ]

    decision_case_response = dispatch_kernel_request(
        "POST",
        "/kernel/decision-aggregation-cases",
        {
            "subject_ref": f"phase_execution_plan:{phase_plan_id}",
            "decision_class": "structural_change_review",
            "scope_kind": "project",
            "scope_ref": "self_evolving_org_demo",
            "procedure_kind": "quorum_majority",
            "opened_by": "role.org_evolver",
            "eligibility_basis": "demo review policy: proposer, evaluator, independent risk guardian, and learning steward advisory quorum before principal approval",
            "eligible_roles": [
                "role.org_evolver",
                "role.evaluator",
                "role.risk_guardian",
                "role.learning_steward",
            ],
            "quorum": 4,
            "downstream_ref": step.target_ref,
            "evidence_refs": [
                f"run:{run_id}",
                f"work:{work_id}",
                f"phase_execution_plan:{phase_plan_id}",
                *a2a_refs,
                *reviewer_evidence_refs,
                *planner_evidence_refs,
            ],
            "metadata": {
                "demo": "self_evolving_org",
                "step_id": step.step_id,
                "binding": "advisory",
            },
            "actor_context": {
                "actor_id": "agent.org_evolver",
                "actor_kind": "agent",
                "role_id": "role.org_evolver",
            },
        },
        config=config,
    )
    _assert_status(
        decision_case_response.status,
        201,
        f"open decision aggregation case {step.step_id}",
    )
    decision_case = decision_case_response.payload["decision_aggregation_case"]
    decision_case_id = decision_case["case_id"]
    decision_case_ref = f"decision_aggregation_case:{decision_case_id}"
    decision_positions = [
        ReviewPosition(
            actor_id="agent.org_evolver",
            role_id="role.org_evolver",
            position="approve",
            rationale=(
                "Proposer confirms the proposed mutation remains inside the "
                "bounded demo envelope."
            ),
            evidence_refs=[],
        ),
        *review_positions,
    ]
    for position in decision_positions:
        position_response = dispatch_kernel_request(
            "POST",
            f"/kernel/decision-aggregation-cases/{decision_case_id}/positions",
            {
                "actor_id": position.actor_id,
                "role_id": position.role_id,
                "position": position.position,
                "rationale": position.rationale,
                "evidence_refs": [
                    f"phase_execution_plan:{phase_plan_id}",
                    *a2a_refs,
                    *position.evidence_refs,
                    *planner_evidence_refs,
                ],
                "metadata": {"demo": "self_evolving_org", "step_id": step.step_id},
                "actor_context": {
                    "actor_id": position.actor_id,
                    "actor_kind": "agent",
                    "role_id": position.role_id,
                },
            },
            config=config,
        )
        _assert_status(
            position_response.status,
            200,
            f"record decision position {position.role_id} {step.step_id}",
        )
    computed_case_response = dispatch_kernel_request(
        "POST",
        f"/kernel/decision-aggregation-cases/{decision_case_id}/compute",
        {
            "actor_context": {
                "actor_id": "agent.evaluator",
                "actor_kind": "agent",
                "role_id": "role.evaluator",
            }
        },
        config=config,
    )
    _assert_status(
        computed_case_response.status,
        200,
        f"compute decision aggregation case {step.step_id}",
    )
    decision_case = computed_case_response.payload["decision_aggregation_case"]
    decision_case_result = decision_case["result"]
    if decision_case_result.get("recommendation") != "approve":
        blocked = _run_reviewer_blocked_candidate(
            config=config,
            step=step,
            decision_case_id=decision_case_id,
            decision_case_ref=decision_case_ref,
            decision_case_result=decision_case_result,
            decision_positions=decision_positions,
            reviewer_invocations=reviewer_invocations,
            reason=(
                "Live reviewer decision aggregation did not approve "
                f"{step.step_id}: {decision_case_result}"
            ),
            evidence_refs=[
                f"run:{run_id}",
                f"work:{work_id}",
                f"phase_execution_plan:{phase_plan_id}",
                decision_case_ref,
                *a2a_refs,
                *reviewer_evidence_refs,
                *planner_evidence_refs,
            ],
        )
        raise StepBlockedError(blocked, blocked["reason"])

    trace_response = dispatch_kernel_request(
        "POST",
        "/kernel/multi-agent-trace-events",
        {
            "runtime_name": "self_evolving_org_demo",
            "external_run_id": step.step_id,
            "cognitive_run_id": run_id,
            "events": [
                {
                    "event_id": f"mate_{step.step_id}_org_evolver",
                    "event_kind": "agent_spawned",
                    "agent_id": "agent.org_evolver",
                    "owner_role": "role.org_evolver",
                    "step_id": step.step_id,
                    "status": "succeeded",
                    "summary": "Org Evolver opened a bounded structural-change run.",
                    "source_refs": [
                        f"run:{run_id}",
                        f"work:{work_id}",
                        *a2a_refs,
                        decision_case_ref,
                        *planner_evidence_refs,
                    ],
                },
                {
                    "event_id": f"mate_{step.step_id}_evaluator",
                    "event_kind": "message",
                    "agent_id": "agent.org_evolver",
                    "target_agent_id": "agent.evaluator",
                    "owner_role": "role.evaluator",
                    "step_id": step.step_id,
                    "status": "succeeded",
                    "summary": "Evaluator receives proposal evidence for review.",
                    "source_refs": [
                        f"run:{run_id}",
                        f"work:{work_id}",
                        *a2a_refs,
                        decision_case_ref,
                        *planner_evidence_refs,
                    ],
                },
                {
                    "event_id": f"mate_{step.step_id}_risk_guardian",
                    "event_kind": "message",
                    "agent_id": "agent.evaluator",
                    "target_agent_id": "agent.risk_guardian",
                    "owner_role": "role.risk_guardian",
                    "step_id": step.step_id,
                    "status": "succeeded",
                    "summary": "Risk Guardian receives the independent structural-risk review.",
                    "source_refs": [
                        f"run:{run_id}",
                        f"work:{work_id}",
                        *a2a_refs,
                        decision_case_ref,
                        *planner_evidence_refs,
                    ],
                },
                {
                    "event_id": f"mate_{step.step_id}_learning_steward",
                    "event_kind": "message",
                    "agent_id": "agent.evaluator",
                    "target_agent_id": "agent.learning_steward",
                    "owner_role": "role.learning_steward",
                    "step_id": step.step_id,
                    "status": "succeeded",
                    "summary": "Learning Steward receives the learning-unit quality review.",
                    "source_refs": [
                        f"run:{run_id}",
                        f"work:{work_id}",
                        *a2a_refs,
                        decision_case_ref,
                        *planner_evidence_refs,
                    ],
                },
            ],
            "actor_context": {
                "actor_id": "agent.org_evolver",
                "actor_kind": "agent",
                "role_id": "role.org_evolver",
            },
        },
        config=config,
    )
    _assert_status(trace_response.status, 201, f"record trace events {step.step_id}")
    trace_event_ids = [event["event_id"] for event in trace_response.payload["trace_events"]]

    claimed = dispatch_kernel_request(
        "POST",
        "/kernel/work-items/claim-next",
        {
            "unit_id": "org_evolution",
            "actor": "agent.org_evolver",
            "role_id": "role.org_evolver",
        },
        config=config,
    )
    _assert_status(claimed.status, 200, f"claim work {step.step_id}")
    claim_token = claimed.payload["work_item"]["claim_token"]

    signal_refs = [
        f"run:{run_id}",
        f"work:{work_id}",
        f"phase_execution_plan:{phase_plan_id}",
        *a2a_refs,
        *reviewer_evidence_refs,
        decision_case_ref,
    ]
    signal_refs.extend(f"multi_agent_trace_event:{event_id}" for event_id in trace_event_ids)
    signal_refs.extend(planner_evidence_refs)
    promoted = _promote_step_candidate(
        step,
        config=config,
        run_id=run_id,
        work_id=work_id,
        phase_plan_id=phase_plan_id,
        evidence_refs=signal_refs,
    )
    signal_id = promoted["capability_signal_id"]
    candidate_id = promoted["learning_candidate_id"]
    proposal = promoted["proposal_response"]
    proposal_id = proposal.payload["proposal"]["proposal_id"]

    decision = dispatch_kernel_request(
        "POST",
        f"/kernel/governance-changes/{proposal_id}/decision",
        {
            "decision": "approve",
            "reason": "deterministic demo policy approves bounded, evidence-carrying steps",
            "actor_context": {
                "actor_id": "human.principal",
                "actor_kind": "human",
                "role_id": "role.principal",
            },
        },
        config=config,
    )
    _assert_status(decision.status, 200, f"approve governance change {step.step_id}")
    event_id = decision.payload["result"]["event_id"]
    closed_signal = dispatch_kernel_request(
        "POST",
        f"/kernel/capability-signals/{signal_id}/close",
        {
            "closed_by": "role.evaluator",
            "closure_ref": f"governance_change:{proposal_id}",
            "rationale": "Capability signal was promoted into an approved governance change.",
            "actor_context": {
                "actor_id": "agent.evaluator",
                "actor_kind": "agent",
                "role_id": "role.evaluator",
            },
        },
        config=config,
    )
    _assert_status(closed_signal.status, 200, f"close capability signal {step.step_id}")

    decision_trace = dispatch_kernel_request(
        "POST",
        "/kernel/multi-agent-trace-events",
        {
            "runtime_name": "self_evolving_org_demo",
            "external_run_id": step.step_id,
            "cognitive_run_id": run_id,
            "event_id": f"mate_{step.step_id}_verdict",
            "event_kind": "verifier_verdict",
            "agent_id": "agent.evaluator",
            "target_agent_id": "agent.org_evolver",
            "owner_role": "role.evaluator",
            "step_id": step.step_id,
            "status": "succeeded",
            "summary": "Evaluator observed approved bounded structural mutation.",
            "source_refs": [
                f"run:{run_id}",
                f"work:{work_id}",
                f"governance_change:{proposal_id}",
                f"kernel_event:{event_id}",
                decision_case_ref,
            ],
            "metadata": {"approval_event_id": event_id},
            "actor_context": {
                "actor_id": "agent.evaluator",
                "actor_kind": "agent",
                "role_id": "role.evaluator",
            },
        },
        config=config,
    )
    _assert_status(decision_trace.status, 201, f"record decision trace {step.step_id}")
    trace_event_ids += [
        event["event_id"] for event in decision_trace.payload["trace_events"]
    ]

    applied_path = demo_firm / step.applied_relpath
    before_state = applied_path.read_text(encoding="utf-8") if applied_path.exists() else ""
    applied_path.parent.mkdir(parents=True, exist_ok=True)
    applied_path.write_text(step.applied_text, encoding="utf-8")
    attestation_response = dispatch_kernel_request(
        "POST",
        "/kernel/action-attestations",
        {
            "subject_kind": "artifact",
            "subject_ref": f"file://{step.applied_relpath}",
            "subject_digest": digest_text(step.applied_text),
            "producer": "role.org_evolver",
            "action_type": "apply_governed_org_change",
            "runtime_ref": f"self_evolving_org_demo:{run_id}",
            "policy_ref": "org/mandates/org_evolver_mandate.md",
            "input_refs": [
                f"work_item:{work_id}",
                f"governance_change:{proposal_id}",
                f"approval_event:{event_id}",
                *a2a_refs,
                decision_case_ref,
                *planner_evidence_refs,
            ],
            "output_refs": [f"file://{step.applied_relpath}"],
            "verification_status": "verified",
            "verification_summary": "deterministic fixture wrote the approved file content",
            "run_id": run_id,
            "metadata": {
                "demo": "self_evolving_org",
                "step_id": step.step_id,
                "proposal_id": proposal_id,
                "approval_event_id": event_id,
                "approval_ref": f"governance_change:{proposal_id}",
                "work_id": work_id,
            },
            "actor_context": {
                "actor_id": "agent.org_evolver",
                "actor_kind": "agent",
                "role_id": "role.org_evolver",
            },
        },
        config=config,
    )
    _assert_status(attestation_response.status, 201, f"create attestation {step.step_id}")
    attestation = attestation_response.payload["action_attestation"]

    learning_response = dispatch_kernel_request(
        "POST",
        "/kernel/learning-events",
        {
            "learning_unit_kind": _learning_kind_for(step.change_kind),
            "decision_use": step.expected_behavior_change,
            "future_application_cue": step.rationale,
            "approved_by": "human.principal",
            "approval_ref": f"governance_change:{proposal_id}",
            "source_carrier_refs": [
                f"run:{run_id}",
                f"work:{work_id}",
                f"kernel_event:{event_id}",
                f"phase_execution_plan:{phase_plan_id}",
                *a2a_refs,
                *reviewer_evidence_refs,
                decision_case_ref,
                *planner_evidence_refs,
            ]
            + [f"multi_agent_trace_event:{event_id}" for event_id in trace_event_ids],
            "before_state": before_state,
            "after_state": step.applied_text,
            "owner_role": "role.org_evolver",
            "externality_review_ref": learning_a2a_ref,
            "metadata": {
                "demo": "self_evolving_org",
                "step_id": step.step_id,
                "learning_steward_review_ref": learning_a2a_ref,
            },
            "actor_context": {
                "actor_id": "human.principal",
                "actor_kind": "human",
                "role_id": "role.principal",
            },
        },
        config=config,
    )
    _assert_status(learning_response.status, 201, f"create learning event {step.step_id}")
    learning = learning_response.payload["learning_event"]
    learning_event_id = learning["learning_event_id"]
    attestation_id = attestation["attestation_id"]

    replay_candidates = discover_relevant_learning_events(
        assigned_to="role.org_evolver",
        cue=step.rationale,
        max_per_source=5,
        log_path=config.learning_events_log,
    )
    replay_matches = [
        candidate
        for candidate in replay_candidates
        if candidate.metadata.get("learning_event_id") == learning_event_id
    ]
    if not replay_matches:
        raise AssertionError(
            f"approved learning event did not replay for future work: {learning_event_id}"
        )
    future_replay = {
        "learning_event_id": learning_event_id,
        "candidate_source": replay_matches[0].source,
        "intent": replay_matches[0].intent,
        "scarcity_signal": replay_matches[0].scarcity_signal,
        "raw_text": replay_matches[0].raw_text,
    }

    outcome_response = dispatch_kernel_request(
        "POST",
        "/kernel/outcome-links",
        build_predicted_mutation_outcome_link_request(
            PredictedMutationOutcomeInput(
                proposal=proposal.payload["proposal"],
                created_by="role.evaluator",
                learning_event_id=learning_event_id,
                metadata={
                    "cognitive_run_id": run_id,
                    "work_id": work_id,
                    "demo": "self_evolving_org",
                    "step_id": step.step_id,
                },
            )
        ),
        config=config,
    )
    _assert_status(outcome_response.status, 201, f"create outcome link {step.step_id}")
    outcome_link_id = outcome_response.payload["outcome_link"]["outcome_link_id"]
    for kind, value in (("baseline", step.metric_baseline), ("post", step.metric_post)):
        snapshot = dispatch_kernel_request(
            "POST",
            f"/kernel/outcome-links/{outcome_link_id}/snapshots",
            {"kind": kind, "value": value, "captured_by": "role.evaluator"},
            config=config,
        )
        _assert_status(snapshot.status, 200, f"record {kind} outcome {step.step_id}")
    verdict = dispatch_kernel_request(
        "POST",
        f"/kernel/outcome-links/{outcome_link_id}/verdict",
        {
            "verdict": "improved",
            "recorded_by": "role.evaluator",
            "rationale": "Deterministic fixture reduced the tracked demo gap count.",
        },
        config=config,
    )
    _assert_status(verdict.status, 200, f"record outcome verdict {step.step_id}")
    outcome_link = verdict.payload["outcome_link"]
    verification_feedback = dispatch_kernel_request(
        "POST",
        f"/kernel/phase-execution-plans/{phase_plan_id}/verification-feedback",
        {
            "verifier_role": "role.evaluator",
            "verdict": "passed",
            "rationale": "Approved mutation has attestation, outcome link, and review schedule evidence.",
            "evidence_refs": [
                f"governance_change:{proposal_id}",
                f"attestation:{attestation_id}",
                f"outcome_link:{outcome_link_id}",
                *a2a_refs,
                decision_case_ref,
            ],
            "actor_context": {
                "actor_id": "agent.evaluator",
                "actor_kind": "agent",
                "role_id": "role.evaluator",
            },
        },
        config=config,
    )
    _assert_status(
        verification_feedback.status,
        201,
        f"record verification feedback {step.step_id}",
    )
    fulfilled_message = dispatch_kernel_request(
        "POST",
        f"/kernel/a2a/messages/{a2a_message_id}/obligation",
        {
            "role_id": "evaluator",
            "state": "fulfilled",
            "actor": "agent.evaluator",
            "note": "Evaluator completed review with passing verification feedback.",
            "actor_context": {
                "actor_id": "agent.evaluator",
                "actor_kind": "agent",
                "role_id": "role.evaluator",
            },
        },
        config=config,
    )
    _assert_status(fulfilled_message.status, 200, f"fulfill A2A review {step.step_id}")
    a2a_obligation_state = fulfilled_message.payload["message"]["obligation_state"]
    risk_fulfilled_message = dispatch_kernel_request(
        "POST",
        f"/kernel/a2a/messages/{risk_a2a_message_id}/obligation",
        {
            "role_id": "risk_guardian",
            "state": "fulfilled",
            "actor": "agent.risk_guardian",
            "note": "Risk Guardian completed independent review with no blocking risk.",
            "actor_context": {
                "actor_id": "agent.risk_guardian",
                "actor_kind": "agent",
                "role_id": "role.risk_guardian",
            },
        },
        config=config,
    )
    _assert_status(
        risk_fulfilled_message.status,
        200,
        f"fulfill A2A risk review {step.step_id}",
    )
    risk_a2a_obligation_state = risk_fulfilled_message.payload["message"][
        "obligation_state"
    ]
    a2a_messages[0]["obligation_state"] = a2a_obligation_state
    a2a_messages[1]["obligation_state"] = risk_a2a_obligation_state
    learning_fulfilled_message = dispatch_kernel_request(
        "POST",
        f"/kernel/a2a/messages/{learning_a2a_message_id}/obligation",
        {
            "role_id": "learning_steward",
            "state": "fulfilled",
            "actor": "agent.learning_steward",
            "note": "Learning Steward completed review of cue, sources, review cadence, and retirement path.",
            "actor_context": {
                "actor_id": "agent.learning_steward",
                "actor_kind": "agent",
                "role_id": "role.learning_steward",
            },
        },
        config=config,
    )
    _assert_status(
        learning_fulfilled_message.status,
        200,
        f"fulfill A2A learning review {step.step_id}",
    )
    learning_a2a_obligation_state = learning_fulfilled_message.payload["message"][
        "obligation_state"
    ]
    a2a_messages[2]["obligation_state"] = learning_a2a_obligation_state
    review_response = dispatch_kernel_request(
        "POST",
        "/kernel/routine-reviews",
        {
            "routine_ref": f"learning_event:{learning_event_id}",
            "routine_kind": "learning_event",
            "review_due_utc": "2030-01-01T00:00:00+00:00",
            "scheduled_by": "role.learning_steward",
            "learning_event_id": learning_event_id,
            "reason": "accepted structural learning should be revisited or retired",
            "metadata": {
                "cognitive_run_id": run_id,
                "work_id": work_id,
                "demo": "self_evolving_org",
                "step_id": step.step_id,
                "learning_steward_review_ref": learning_a2a_ref,
            },
        },
        config=config,
    )
    _assert_status(review_response.status, 201, f"schedule routine review {step.step_id}")
    routine_review_id = review_response.payload["routine_review"]["review_id"]
    context_query = urlencode(
        {
            "assigned_to": "role.org_evolver",
            "cue": step.rationale,
            "max_per_source": "5",
        }
    )
    future_context_response = dispatch_kernel_request(
        "GET",
        f"/kernel/work-discovery?{context_query}",
        config=config,
    )
    _assert_status(
        future_context_response.status,
        200,
        f"future context packet {step.step_id}",
    )
    future_context_packet = future_context_response.payload["context_packet"]
    future_context_verification = dispatch_kernel_request(
        "POST",
        "/kernel/work-discovery/context-packet/verify",
        {"context_packet": future_context_packet},
        config=config,
    )
    _assert_status(
        future_context_verification.status,
        200,
        f"verify future context packet {step.step_id}",
    )
    if not future_context_verification.payload["verification"]["ok"]:
        raise AssertionError(
            "invalid future context packet for "
            f"{step.step_id}: {future_context_verification.payload['verification']}"
        )
    encounter = dispatch_kernel_request(
        "POST",
        "/kernel/learning-event-encounters",
        {
            "learning_event_id": learning_event_id,
            "role": "role.org_evolver",
            "cue": step.rationale,
            "outcome": "applied",
            "work_ref": f"work:{work_id}",
            "context_packet": future_context_packet,
            "evidence_refs": [
                f"run:{run_id}",
                f"governance_change:{proposal_id}",
                f"outcome_link:{outcome_link_id}",
                f"routine_review:{routine_review_id}",
                f"context_packet:{future_context_packet['context_packet_id']}",
                *a2a_refs,
                decision_case_ref,
                *planner_evidence_refs,
            ],
            "metadata": {"demo": "self_evolving_org", "step_id": step.step_id},
        },
        config=config,
    )
    _assert_status(
        encounter.status,
        201,
        f"record verified learning-use encounter {step.step_id}",
    )
    evidence_pack = build_governed_mutation_evidence_pack(
        GovernedMutationEvidenceInput(
            proposal_id=proposal_id,
            learning_event_id=learning_event_id,
            attestation_id=attestation_id,
            run_id=run_id,
            capability_signal_id=signal_id,
            learning_candidate_id=candidate_id,
            phase_execution_plan_id=phase_plan_id,
            a2a_refs=a2a_refs,
            reviewer_evidence_refs=reviewer_evidence_refs,
            decision_case_ref=decision_case_ref,
            planner_evidence_refs=planner_evidence_refs,
            trace_event_ids=trace_event_ids,
        )
    )
    required_evidence = governed_mutation_evidence_requirements(
        require_planner=True,
        require_a2a=True,
        require_decision=True,
        require_phase_plan=True,
        require_trace=True,
        require_reviewer_evidence=bool(reviewer_evidence_refs),
    )
    evidence_pack_validation = validate_governed_mutation_evidence_pack(
        evidence_pack,
        required_evidence_prefixes=required_evidence["required_evidence_prefixes"],
        required_artifact_kinds=required_evidence["required_artifact_kinds"],
    )
    if not evidence_pack_validation["valid"]:
        raise AssertionError(
            "invalid governed mutation evidence pack for "
            f"{step.step_id}: {evidence_pack_validation['errors']}"
        )

    completed = dispatch_kernel_request(
        "POST",
        f"/kernel/work-items/{work_id}/complete",
        {
            "actor": "agent.org_evolver",
            "claim_token": claim_token,
            "exit_kind": "proposal_approved",
            "result": step.expected_behavior_change,
            "producer": "role.org_evolver",
            "verifier": "role.evaluator",
            "artifact_refs": evidence_pack["artifact_refs"],
        },
        config=config,
    )
    _assert_status(completed.status, 200, f"complete work {step.step_id}")

    checkpoint = dispatch_kernel_request(
        "POST",
        f"/kernel/runs/{run_id}/checkpoints",
        {
            "actor": "role.org_evolver",
            "step_id": step.step_id,
            "status": "completed",
            "summary": f"approved and applied {proposal_id}",
            "payload_ref": f"governance_change:{proposal_id}",
            "side_effect_key": f"apply:{step.applied_relpath}",
        },
        config=config,
    )
    _assert_status(checkpoint.status, 201, f"checkpoint {step.step_id}")
    run_done = dispatch_kernel_request(
        "POST",
        f"/kernel/runs/{run_id}/state",
        {"actor": "role.org_evolver", "state": "completed"},
        config=config,
    )
    _assert_status(run_done.status, 200, f"complete run {step.step_id}")

    bundle_response = dispatch_kernel_request(
        "POST",
        "/kernel/governed-run-bundles/build",
        {"run_id": run_id},
        config=config,
    )
    _assert_status(bundle_response.status, 200, f"build governed-run bundle {step.step_id}")
    bundle_summary = bundle_response.payload["summary"]
    bundle_validation = bundle_response.payload["validation"]
    bundle_validation_errors = list(bundle_validation.get("errors") or [])

    stage_all(demo_firm)
    commit_sha = commit(demo_firm, f"self-evolving org step: {step.step_id}")
    proof_evidence_carrier_refs = list(evidence_pack["evidence_carrier_refs"])
    proof_response = dispatch_kernel_request(
        "POST",
        "/kernel/mutation-proofs/build",
        build_mutation_proof_request(
            GovernedMutationRecipeInput(
                step_id=step.step_id,
                change_kind=step.change_kind,
                target_ref=step.target_ref,
                run_id=run_id,
                work_id=work_id,
                proposal_id=proposal_id,
                approval_event_id=event_id,
                mutation_ref=f"file://{step.applied_relpath}",
                attestation_id=attestation_id,
                learning_event_id=learning_event_id,
                outcome_link_id=outcome_link_id,
                routine_review_id=routine_review_id,
                bundle_id=str(bundle_summary.get("bundle_id") or ""),
                bundle_digest=bundle_summary.get("bundle_digest"),
                bundle_verdict=bundle_summary.get("verdict"),
                commit_sha=commit_sha,
                bundle_validation_errors=bundle_validation_errors,
                evidence_carrier_refs=proof_evidence_carrier_refs,
            )
        ),
        config=config,
    )
    _assert_status(proof_response.status, 200, f"build mutation proof {step.step_id}")
    mutation_proof = proof_response.payload["proof"]
    proof_validation = dispatch_kernel_request(
        "POST",
        "/kernel/mutation-proofs/validate",
        {"proof": mutation_proof},
        config=config,
    )
    _assert_status(proof_validation.status, 200, f"validate mutation proof {step.step_id}")

    graph_response = dispatch_kernel_request(
        "GET",
        (
            "/kernel/delegation-graph"
            f"?runtime_name=self_evolving_org_demo&external_run_id={step.step_id}"
        ),
        config=config,
    )
    _assert_status(graph_response.status, 200, f"build delegation graph {step.step_id}")
    delegation_graph = graph_response.payload["graph"]

    return {
        "step_id": step.step_id,
        "simulation_tick": simulation_tick,
        "title": step.title,
        "change_kind": step.change_kind,
        "target_ref": step.target_ref,
        "rationale": step.rationale,
        "expected_behavior_change": step.expected_behavior_change,
        "risk_summary": step.risk_summary,
        "rollback_plan": step.rollback_plan,
        "run_id": run_id,
        "work_id": work_id,
        "phase_execution_plan_id": phase_plan_id,
        "a2a_message_id": a2a_message_id,
        "a2a_message_ref": a2a_ref,
        "a2a_obligation_state": a2a_obligation_state,
        "a2a_messages": a2a_messages,
        "reviewer_invocations": reviewer_invocations,
        "decision_positions": [asdict(position) for position in decision_positions],
        "learning_steward_review_ref": learning_a2a_ref,
        "decision_aggregation_case_id": decision_case_id,
        "decision_aggregation_case_ref": decision_case_ref,
        "decision_aggregation_result": decision_case_result,
        "governed_mutation_evidence_pack": evidence_pack,
        "governed_mutation_evidence_pack_validation": evidence_pack_validation,
        "planner_evidence_refs": planner_evidence_refs,
        "trace_event_ids": trace_event_ids,
        "delegation_graph": delegation_graph,
        "capability_signal_id": signal_id,
        "learning_candidate_id": candidate_id,
        "proposal_source": "learning_candidate_promotion",
        "proposal_source_refs": proposal.payload["proposal"].get("source_refs", []),
        "proposal_id": proposal_id,
        "proposal_predicted_effect": proposal.payload["proposal"].get("predicted_effect"),
        "decision": "approve",
        "decision_event_id": event_id,
        "learning_event_id": learning_event_id,
        "learning_encounter_id": encounter.payload["encounter"]["encounter_id"],
        "learning_use_receipt": encounter.payload["encounter"],
        "context_packet_id": future_context_packet["context_packet_id"],
        "context_packet_ref": f"context_packet:{future_context_packet['context_packet_id']}",
        "context_packet_verification": future_context_verification.payload[
            "verification"
        ],
        "future_context_packet": {
            "context_packet_id": future_context_packet["context_packet_id"],
            "digest": future_context_packet["digest"],
            "basis": future_context_packet["basis"],
            "verification": future_context_verification.payload["verification"],
        },
        "future_replay": future_replay,
        "outcome_link_id": outcome_link_id,
        "outcome_prediction_review": outcome_link.get("metadata", {}).get(
            "prediction_review"
        ),
        "routine_review_id": routine_review_id,
        "attestation_id": attestation_id,
        "bundle": bundle_summary,
        "bundle_validation": bundle_validation,
        "applied_path": step.applied_relpath,
        "commit": commit_sha,
        "proof_evidence_carrier_refs": proof_evidence_carrier_refs,
        "mutation_proof": mutation_proof,
        "mutation_proof_validation": {
            "valid": proof_validation.payload["valid"],
            "errors": proof_validation.payload["errors"],
        },
    }


def _promote_step_candidate(
    step: EvolutionStep,
    *,
    config: KernelServiceConfig,
    run_id: str,
    work_id: str,
    phase_plan_id: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    signal = dispatch_kernel_request(
        "POST",
        "/kernel/capability-signals",
        {
            "signal_id": f"csig_{step.step_id}",
            "signal_kind": "custom",
            "severity": "warning",
            "source_ref": f"work_item:{work_id}",
            "summary": step.rationale,
            "owner_role": "role.org_evolver",
            "worker_ref": "agent.org_evolver",
            "run_id": run_id,
            "work_id": work_id,
            "recommended_route": "open_governance_change",
            "route_target_ref": step.target_ref,
            "counts_as_failure": False,
            "evidence_refs": evidence_refs,
            "metadata": {
                "demo": "self_evolving_org",
                "step_id": step.step_id,
                "change_kind": step.change_kind,
                "phase_plan_id": phase_plan_id,
                "target_ref": step.target_ref,
            },
            "actor_context": {
                "actor_id": "agent.org_evolver",
                "actor_kind": "agent",
                "role_id": "role.org_evolver",
            },
        },
        config=config,
    )
    _assert_status(signal.status, 201, f"record capability signal {step.step_id}")
    signal_id = signal.payload["signal"]["signal_id"]
    routed = dispatch_kernel_request(
        "POST",
        f"/kernel/capability-signals/{signal_id}/route",
        {
            "route_kind": "open_governance_change",
            "routed_by": "role.evaluator",
            "rationale": "Structural improvement evidence should enter governed proposal review.",
            "target_ref": step.target_ref,
            "actor_context": {
                "actor_id": "agent.evaluator",
                "actor_kind": "agent",
                "role_id": "role.evaluator",
            },
        },
        config=config,
    )
    _assert_status(routed.status, 200, f"route capability signal {step.step_id}")
    candidate = _candidate_for_signal(config, signal_id=signal_id)
    proposal = dispatch_kernel_request(
        "POST",
        f"/kernel/learning-transition-candidates/{candidate['candidate_id']}/governance-change",
        {
            "source": "capability",
            "change_kind": step.change_kind,
            "title": step.title,
            "target_ref": step.target_ref,
            "proposed_by": "agent.org_evolver",
            "expected_behavior_change": step.expected_behavior_change,
            "predicted_effect": _predicted_effect_for_step(step),
            "risk_summary": step.risk_summary,
            "rollback_plan": step.rollback_plan,
            "owner_role": "role.principal",
            "invariant_checks": _passing_invariant_checks(step),
            "metadata": {
                "demo": "self_evolving_org",
                "step_id": step.step_id,
                "capability_signal_id": signal_id,
                "amendment_tier": tier_classification_invariant_check(
                    target_ref=step.target_ref,
                    change_kind=step.change_kind,
                ).rationale,
            },
            "actor_context": {
                "actor_id": "agent.org_evolver",
                "actor_kind": "agent",
                "role_id": "role.org_evolver",
            },
        },
        config=config,
    )
    _assert_status(proposal.status, 201, f"promote candidate {step.step_id}")
    if proposal.payload["proposal"]["status"] != "review_ready":
        raise AssertionError(
            f"promoted demo proposal for {step.step_id} is not review_ready: "
            f"{proposal.payload['proposal']['status']}"
        )
    return {
        "capability_signal_id": signal_id,
        "learning_candidate_id": candidate["candidate_id"],
        "proposal_response": proposal,
    }


def _predicted_effect_for_step(step: EvolutionStep) -> dict[str, Any]:
    return {
        "metric_name": "open_org_design_gaps",
        "metric_unit": "count",
        "direction": "lower_is_better",
        "threshold": 1,
        "review_horizon": "same_governed_iteration",
        "expected_verdict": "improved",
        "rationale": step.expected_behavior_change,
    }


def _run_blocked_candidate_fixture(config: KernelServiceConfig) -> dict[str, Any]:
    signal = dispatch_kernel_request(
        "POST",
        "/kernel/capability-signals",
        {
            "signal_id": "csig_blocked_unsafe_self_modifier",
            "signal_kind": "unsafe_request",
            "severity": "blocking",
            "source_ref": "demo:self_evolving_org:blocked_fixture",
            "summary": (
                "A proposed self-modifying role has no rollback, invariant evidence, "
                "or bounded authority proof."
            ),
            "owner_role": "role.evaluator",
            "worker_ref": "agent.org_evolver",
            "recommended_route": "open_governance_change",
            "route_target_ref": "org/roles/unsafe_self_modifier.yaml",
            "counts_as_failure": False,
            "evidence_refs": ["demo:blocked_fixture:missing_invariant_evidence"],
            "metadata": {"demo": "self_evolving_org", "fixture": "blocked_candidate"},
            "actor_context": {
                "actor_id": "agent.evaluator",
                "actor_kind": "agent",
                "role_id": "role.evaluator",
            },
        },
        config=config,
    )
    _assert_status(signal.status, 201, "record blocked capability signal")
    signal_id = signal.payload["signal"]["signal_id"]
    routed = dispatch_kernel_request(
        "POST",
        f"/kernel/capability-signals/{signal_id}/route",
        {
            "route_kind": "open_governance_change",
            "routed_by": "role.evaluator",
            "rationale": "Unsafe structural request must be converted to a reviewable blocked proposal.",
            "target_ref": "org/roles/unsafe_self_modifier.yaml",
            "actor_context": {
                "actor_id": "agent.evaluator",
                "actor_kind": "agent",
                "role_id": "role.evaluator",
            },
        },
        config=config,
    )
    _assert_status(routed.status, 200, "route blocked capability signal")
    candidate = _candidate_for_signal(config, signal_id=signal_id)
    promoted = dispatch_kernel_request(
        "POST",
        f"/kernel/learning-transition-candidates/{candidate['candidate_id']}/governance-change",
        {
            "source": "capability",
            "change_kind": "role_change",
            "title": "Reject unsafe self-modifying role",
            "target_ref": "org/roles/unsafe_self_modifier.yaml",
            "proposed_by": "agent.org_evolver",
            "owner_role": "role.principal",
            "metadata": {
                "demo": "self_evolving_org",
                "fixture": "blocked_candidate",
                "capability_signal_id": signal_id,
            },
            "actor_context": {
                "actor_id": "agent.org_evolver",
                "actor_kind": "agent",
                "role_id": "role.org_evolver",
            },
        },
        config=config,
    )
    _assert_status(promoted.status, 201, "promote blocked candidate")
    proposal = promoted.payload["proposal"]
    if proposal["status"] != "blocked":
        raise AssertionError(f"blocked fixture unexpectedly produced {proposal['status']}")
    return {
        "capability_signal_id": signal_id,
        "learning_candidate_id": candidate["candidate_id"],
        "proposal_id": proposal["proposal_id"],
        "status": proposal["status"],
        "evidence_sufficiency": proposal["evidence_sufficiency"],
        "target_ref": proposal["target_ref"],
    }


def _run_reviewer_blocked_candidate(
    *,
    config: KernelServiceConfig,
    step: EvolutionStep,
    decision_case_id: str,
    decision_case_ref: str,
    decision_case_result: dict[str, Any],
    decision_positions: list[ReviewPosition],
    reviewer_invocations: list[dict[str, Any]],
    reason: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    signal_id = f"csig_reviewer_blocked_{step.step_id}"
    routed = dispatch_kernel_request(
        "POST",
        f"/kernel/decision-aggregation-cases/{decision_case_id}/route-escalation",
        {
            "signal_id": signal_id,
            "signal_kind": "evidence_gap",
            "severity": "blocking",
            "summary": reason,
            "owner_role": "role.evaluator",
            "worker_ref": "agent.org_evolver",
            "recommended_route": "open_governance_change",
            "route_kind": "open_governance_change",
            "route_target_ref": step.target_ref,
            "route_rationale": "Reviewer quorum did not approve; preserve as blocked governance evidence.",
            "routed_by": "role.evaluator",
            "counts_as_failure": True,
            "evidence_refs": evidence_refs,
            "metadata": {
                "demo": "self_evolving_org",
                "step_id": step.step_id,
                "blocked_by": "reviewer_quorum",
            },
            "governance_change_target_ref": step.target_ref,
            "governance_change_kind": step.change_kind,
            "proposed_by": "agent.org_evolver",
            "actor_context": {
                "actor_id": "agent.evaluator",
                "actor_kind": "agent",
                "role_id": "role.evaluator",
            },
        },
        config=config,
    )
    _assert_status(
        routed.status,
        201,
        f"route reviewer-blocked decision aggregation {step.step_id}",
    )
    candidate = routed.payload["learning_candidate"]
    proposal = routed.payload["proposal"]
    if candidate is None:
        raise AssertionError(f"reviewer-blocked route did not return a candidate: {routed.payload}")
    if proposal is None:
        raise AssertionError(f"reviewer-blocked route did not return a proposal: {routed.payload}")
    return {
        "capability_signal_id": signal_id,
        "learning_candidate_id": candidate["candidate_id"],
        "proposal_id": proposal["proposal_id"],
        "status": proposal["status"],
        "evidence_sufficiency": proposal["evidence_sufficiency"],
        "target_ref": proposal["target_ref"],
        "reason": reason,
        "blocked_by": "reviewer_quorum",
        "decision_aggregation_case_id": decision_case_id,
        "decision_aggregation_case_ref": decision_case_ref,
        "decision_aggregation_result": decision_case_result,
        "decision_positions": [asdict(position) for position in decision_positions],
        "reviewer_invocations": reviewer_invocations,
        "route_packet": routed.payload["route_packet"],
    }


def _candidate_for_signal(config: KernelServiceConfig, *, signal_id: str) -> dict[str, Any]:
    candidates = dispatch_kernel_request(
        "GET",
        "/kernel/learning-transition-candidates?source=capability",
        config=config,
    )
    _assert_status(candidates.status, 200, f"load candidate for {signal_id}")
    for candidate in candidates.payload["candidates"]:
        proposed = candidate.get("proposed_payload") or {}
        if proposed.get("signal_id") == signal_id:
            return candidate
    raise AssertionError(f"learning candidate not found for capability signal {signal_id}")


def _passing_invariant_checks(step: EvolutionStep) -> list[dict[str, Any]]:
    checks = [
        {
            "invariant": invariant,
            "status": "pass",
            "rationale": f"{invariant} preserved in deterministic step {step.step_id}.",
            "evidence_refs": [f"demo:{step.step_id}:{invariant}"],
        }
        for invariant in sorted(REQUIRED_INVARIANTS)
    ]
    checks.append(
        tier_classification_invariant_check(
            target_ref=step.target_ref,
            change_kind=step.change_kind,
            evidence_refs=[f"demo:{step.step_id}:amendment_tier"],
        ).as_dict()
    )
    return checks


def _learning_kind_for(change_kind: str) -> str:
    if change_kind == "role_change":
        return "route_change"
    if change_kind == "project_charter_change":
        return "charter_change"
    if change_kind == "learning_policy_change":
        return "review_threshold_change"
    return "mandate_change"


def _git_log(repo: Path) -> list[dict[str, str]]:
    import subprocess

    result = subprocess.run(
        ["git", "log", "--pretty=format:%H%x09%s"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    rows: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        sha, _, subject = line.partition("\t")
        rows.append({"sha": sha, "subject": subject})
    return rows


def _assert_status(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label} returned {actual}, expected {expected}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a deterministic self-evolving organization demo."
    )
    parser.add_argument("--workdir", type=Path, help="Directory to create demo-firm in.")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete an existing demo-firm under --workdir before running.",
    )
    parser.add_argument("--iterations", type=int, default=None)
    parser.add_argument(
        "--budget-units",
        type=int,
        help="Maximum governed mutation iterations to apply before stopping.",
    )
    parser.add_argument(
        "--planner-timeout-seconds",
        type=int,
        default=600,
        help="Timeout for subscription/local agent planner subprocesses.",
    )
    parser.add_argument(
        "--planner-prompt-mode",
        choices=["full", "compact"],
        default="full",
        help="Prompt detail level for API or subscription/local planners.",
    )
    parser.add_argument(
        "--stop-file",
        type=Path,
        help=(
            "Stop cleanly before the next iteration when this file exists. "
            "Reports are still written."
        ),
    )
    parser.add_argument(
        "--run-until-stopped",
        action="store_true",
        help=(
            "Use a long default iteration ceiling. Requires --budget-units or "
            "--stop-file as an operator stop condition."
        ),
    )
    parser.add_argument(
        "--api-planner",
        action="store_true",
        help="Use a configured API model call to propose structural changes.",
    )
    parser.add_argument("--llm", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--agent-planner-command",
        help=(
            "Subscription/local agent command that returns the planner JSON. "
            "Prompt is passed on stdin unless the command contains {prompt_file}."
        ),
    )
    parser.add_argument(
        "--agent-planner-runtime",
        help=(
            "Subscription/local agent CLI, such as claude or codex. Uses the "
            "same invocation policy as the Python daemon."
        ),
    )
    parser.add_argument(
        "--agent-planner-adapter",
        default="auto",
        choices=["auto", "claude_print", "codex_exec"],
        help="Runtime adapter for --agent-planner-runtime.",
    )
    parser.add_argument(
        "--agent-reviewer-runtime",
        help=(
            "Optional subscription/local agent CLI used to back evaluator, "
            "risk_guardian, and learning_steward review offices."
        ),
    )
    parser.add_argument(
        "--agent-reviewer-adapter",
        default="auto",
        choices=["auto", "claude_print", "codex_exec"],
        help="Runtime adapter for --agent-reviewer-runtime.",
    )
    parser.add_argument(
        "--reviewer-timeout-seconds",
        type=int,
        help="Timeout for each live reviewer subprocess. Defaults to planner timeout.",
    )
    parser.add_argument(
        "--workload-feedback",
        choices=["score_totals", "withheld"],
        default="score_totals",
        help=(
            "Whether workload score totals are written into firm-visible state. "
            "Operator-only scoring still runs in both modes."
        ),
    )
    parser.add_argument(
        "--compare-feedback",
        action="store_true",
        help=(
            "Run two arms, score_totals and withheld, then write a "
            "comparison report under --workdir/reports."
        ),
    )
    parser.add_argument(
        "--workload-executor-runtime",
        help=(
            "Optional subscription/local agent CLI used to execute the first N "
            "visible workload packets through kernel work items."
        ),
    )
    parser.add_argument(
        "--workload-executor-adapter",
        default="auto",
        choices=["auto", "claude_print", "codex_exec"],
        help="Runtime adapter for --workload-executor-runtime.",
    )
    parser.add_argument(
        "--workload-executor-limit",
        type=int,
        default=0,
        help=(
            "Number of workload packets to execute with the live workload "
            "executor. Remaining packets use fixture deliverables."
        ),
    )
    parser.add_argument(
        "--workload-executor-timeout-seconds",
        type=int,
        default=180,
        help="Timeout for each live workload packet executor subprocess.",
    )
    parser.add_argument("--model-id", help="Explicit model id for --api-planner mode.")
    parser.add_argument("--full-json", action="store_true")
    args = parser.parse_args(argv)
    if args.budget_units is not None and args.budget_units < 0:
        parser.error("--budget-units must be non-negative")
    if args.planner_timeout_seconds <= 0:
        parser.error("--planner-timeout-seconds must be positive")
    if args.reviewer_timeout_seconds is not None and args.reviewer_timeout_seconds <= 0:
        parser.error("--reviewer-timeout-seconds must be positive")
    if args.workload_executor_limit < 0:
        parser.error("--workload-executor-limit must be non-negative")
    if args.workload_executor_timeout_seconds <= 0:
        parser.error("--workload-executor-timeout-seconds must be positive")
    if args.run_until_stopped and args.budget_units is None and args.stop_file is None:
        parser.error("--run-until-stopped requires --budget-units or --stop-file")
    planner_transport = "fixture"
    if args.api_planner or args.llm:
        planner_transport = "api"
    if args.agent_planner_command or args.agent_planner_runtime:
        planner_transport = "subscription_cli"
    if args.compare_feedback:
        if not args.workdir:
            parser.error("--compare-feedback requires --workdir so artifacts persist")
    iterations = args.iterations
    if iterations is None:
        iterations = 1000 if args.run_until_stopped else 3
    if iterations < 0:
        parser.error("--iterations must be non-negative")

    if args.compare_feedback:
        try:
            report = run_feedback_comparison(
                args.workdir,
                iterations=iterations,
                max_budget_units=args.budget_units,
                planner_transport=planner_transport,
                model_id=args.model_id,
                planner_command=args.agent_planner_command,
                planner_runtime=args.agent_planner_runtime,
                planner_adapter=args.agent_planner_adapter,
                planner_prompt_mode=args.planner_prompt_mode,
                planner_timeout_seconds=args.planner_timeout_seconds,
                reviewer_runtime=args.agent_reviewer_runtime,
                reviewer_adapter=args.agent_reviewer_adapter,
                reviewer_timeout_seconds=args.reviewer_timeout_seconds,
                workload_executor_runtime=args.workload_executor_runtime,
                workload_executor_adapter=args.workload_executor_adapter,
                workload_executor_limit=args.workload_executor_limit,
                workload_executor_timeout_seconds=args.workload_executor_timeout_seconds,
                replace_existing=args.replace_existing,
            )
        except PlannerRejectionError as exc:
            print(json.dumps(exc.report, indent=2, sort_keys=True))
            return 2
    elif args.workdir:
        try:
            report = run_demo(
                args.workdir,
                iterations=iterations,
                max_budget_units=args.budget_units,
                stop_file=args.stop_file,
                planner_transport=planner_transport,
                model_id=args.model_id,
                planner_command=args.agent_planner_command,
                planner_runtime=args.agent_planner_runtime,
                planner_adapter=args.agent_planner_adapter,
                planner_prompt_mode=args.planner_prompt_mode,
                planner_timeout_seconds=args.planner_timeout_seconds,
                reviewer_runtime=args.agent_reviewer_runtime,
                reviewer_adapter=args.agent_reviewer_adapter,
                reviewer_timeout_seconds=args.reviewer_timeout_seconds,
                workload_feedback=args.workload_feedback,
                workload_executor_runtime=args.workload_executor_runtime,
                workload_executor_adapter=args.workload_executor_adapter,
                workload_executor_limit=args.workload_executor_limit,
                workload_executor_timeout_seconds=args.workload_executor_timeout_seconds,
                replace_existing=args.replace_existing,
            )
        except PlannerRejectionError as exc:
            print(json.dumps(exc.report, indent=2, sort_keys=True))
            return 2
    else:
        with tempfile.TemporaryDirectory(prefix="cognitive-firm-self-evolving-") as raw:
            try:
                report = run_demo(
                    Path(raw),
                    iterations=iterations,
                    max_budget_units=args.budget_units,
                    stop_file=args.stop_file,
                    planner_transport=planner_transport,
                    model_id=args.model_id,
                    planner_command=args.agent_planner_command,
                    planner_runtime=args.agent_planner_runtime,
                    planner_adapter=args.agent_planner_adapter,
                    planner_prompt_mode=args.planner_prompt_mode,
                    planner_timeout_seconds=args.planner_timeout_seconds,
                    reviewer_runtime=args.agent_reviewer_runtime,
                    reviewer_adapter=args.agent_reviewer_adapter,
                    reviewer_timeout_seconds=args.reviewer_timeout_seconds,
                    workload_feedback=args.workload_feedback,
                    workload_executor_runtime=args.workload_executor_runtime,
                    workload_executor_adapter=args.workload_executor_adapter,
                    workload_executor_limit=args.workload_executor_limit,
                    workload_executor_timeout_seconds=args.workload_executor_timeout_seconds,
                    replace_existing=args.replace_existing,
                )
            except PlannerRejectionError as exc:
                print(json.dumps(exc.report, indent=2, sort_keys=True))
                return 2

    if args.full_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif report.get("demo") == "self_evolving_org_feedback_comparison":
        print(
            json.dumps(
                {
                    "demo": report["demo"],
                    "no_external_calls": report["no_external_calls"],
                    "workdir": report["workdir"],
                    "comparison": report["comparison"],
                    "artifacts": report["artifacts"],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(
            json.dumps(
                {
                    "demo": report["demo"],
                    "no_external_calls": report["no_external_calls"],
                    "planner_transport": report["planner_transport"],
                    "iterations_run": report["iterations_run"],
                    "summary": report["summary"],
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
