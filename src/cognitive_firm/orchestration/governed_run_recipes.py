"""Thin composition helpers for governed run recipes.

This module does not create authority, approve work, or write kernel state. It
only normalizes client-side request bodies and inspection artifacts for flows
that already use first-party kernel primitives and service routes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cognitive_firm.orchestration.command_surface import command_operator_path


@dataclass(frozen=True)
class BoundedRunControlInput:
    """Operator-visible bounds for a governed run recipe."""

    budget_units_consumed: int
    budget_units_total: int | None
    stop_file: str | Path | None
    stop_file_seen: bool
    termination_reason: str
    selected_steps: int
    steps_run: int
    live_snapshots_written: int | None = None
    clock_kind: str = "bounded_harness_iteration"
    tick_unit: str = "governed_iteration"


@dataclass(frozen=True)
class GovernedMutationRecipeInput:
    """References needed to ask the kernel service for a mutation proof."""

    step_id: str
    change_kind: str
    target_ref: str
    run_id: str
    work_id: str
    proposal_id: str
    approval_event_id: str
    mutation_ref: str
    attestation_id: str
    learning_event_id: str
    outcome_link_id: str
    routine_review_id: str
    bundle_id: str | None
    bundle_digest: str | None
    bundle_verdict: str | None
    commit_sha: str
    bundle_validation_errors: list[str]
    evidence_carrier_refs: list[str]


@dataclass(frozen=True)
class GovernedMutationEvidenceInput:
    """Common evidence refs for a governed mutation lifecycle."""

    proposal_id: str
    learning_event_id: str
    attestation_id: str
    run_id: str
    capability_signal_id: str
    learning_candidate_id: str
    phase_execution_plan_id: str
    a2a_refs: list[str] | None = None
    reviewer_evidence_refs: list[str] | None = None
    decision_case_ref: str | None = None
    planner_evidence_refs: list[str] | None = None
    trace_event_ids: list[str] | None = None


@dataclass(frozen=True)
class GovernedRunOperatorSummaryInput:
    """Human inspection projection for one governed run or bounded run."""

    run_label: str
    run_ref: str
    summary: dict[str, Any]
    operator_controls: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] | None = None
    commands: list[dict[str, Any]] | None = None
    inspection_order: list[str] | None = None
    bundle_summaries: list[dict[str, Any]] | None = None
    mutation_proofs: list[dict[str, Any]] | None = None
    execution_signals: list[dict[str, Any]] | None = None
    learning_candidates: list[dict[str, Any]] | None = None
    phase_plans: list[dict[str, Any]] | None = None
    learning_closure: list[dict[str, Any]] | None = None
    operator_burden: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class AdoptionReadinessPacketInput:
    """Adopter-facing review packet over existing runnable proof paths.

    This input carries observed JSON outputs from demos/smokes that have
    already run. The builder does not execute commands or approve release
    readiness; it only packages evidence and missing checks for review.
    """

    target_label: str = "local_adopter"
    observed_results: dict[str, dict[str, Any]] | None = None
    include_live_agent: bool = False
    include_release_gate: bool = False
    generated_at_utc: str | None = None
    evidence_refs: list[str] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class GovernedActionCompositionInput:
    """Read-only traceability check for one governed action proof chain.

    The input carries observed output from an already-run demo, adapter, or
    operator command. The builder checks required evidence classes and returns
    missing links; it does not execute the action, call service routes, approve
    governance, or verify that referenced rows exist.
    """

    action_label: str
    observed_result: dict[str, Any] | None = None
    evidence_refs: list[str] | None = None
    profile: str = "first_gated_action"
    generated_at_utc: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class PredictedMutationOutcomeInput:
    """Request context for opening an outcome link from a predicted proposal."""

    proposal: dict[str, Any]
    created_by: str
    learning_event_id: str | None = None
    owner_role: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    metadata: dict[str, Any] | None = None
    outcome_link_id: str | None = None


@dataclass(frozen=True)
class PredictedMutationReversalReviewInput:
    """Request context for scheduling review after a failed prediction."""

    outcome_link: dict[str, Any]
    review_due_utc: str
    scheduled_by: str
    review_id: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    metadata: dict[str, Any] | None = None
    require_failed_prediction: bool = True


@dataclass(frozen=True)
class ExecutionEvidenceRouteInput:
    """A runtime-observed issue that should enter governed review.

    This input describes evidence an adapter already observed: an abstention,
    capability gap, verifier block, tool failure, or similar execution signal.
    The recipe converts it into service-call shapes for existing kernel routes.
    It does not dispatch the calls or decide their outcome.
    """

    signal_kind: str
    source_ref: str
    summary: str
    owner_role: str
    severity: str = "warning"
    worker_ref: str | None = None
    run_id: str | None = None
    work_id: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    capability_ref: str | None = None
    threshold_ref: str | None = None
    recommended_route: str | None = "open_learning_candidate"
    route_kind: str | None = "open_learning_candidate"
    route_target_ref: str | None = None
    route_rationale: str | None = None
    routed_by: str | None = None
    counts_as_failure: bool = False
    evidence_refs: list[str] | None = None
    metadata: dict[str, Any] | None = None
    signal_id: str | None = None
    governance_change_target_ref: str | None = None
    governance_change_kind: str | None = None
    proposed_by: str | None = None


def build_bounded_run_controls(
    control_input: BoundedRunControlInput,
) -> dict[str, Any]:
    """Build a normalized operator-control snapshot for a bounded run.

    This is an inspection artifact for demos and adapters. It does not stop a
    process by itself; the caller remains responsible for enforcing the bounds
    before invoking another runtime step.
    """

    total = control_input.budget_units_total
    consumed = control_input.budget_units_consumed
    remaining = None if total is None else max(total - consumed, 0)
    controls: dict[str, Any] = {
        "schema": "bounded_run_controls.v1",
        "budget_units_total": total,
        "budget_units_consumed": consumed,
        "budget_units_remaining": remaining,
        "stop_file": str(control_input.stop_file) if control_input.stop_file else None,
        "stop_file_seen": control_input.stop_file_seen,
        "termination_reason": control_input.termination_reason,
        "selected_steps": control_input.selected_steps,
        "live_snapshots_written": control_input.live_snapshots_written,
        "simulation_clock": {
            "clock_kind": control_input.clock_kind,
            "tick_unit": control_input.tick_unit,
            "ticks_selected": control_input.selected_steps,
            "ticks_run": control_input.steps_run,
            "next_tick_index": control_input.steps_run + 1,
        },
    }
    stop_receipt = _bounded_run_stop_receipt(control_input, remaining=remaining)
    if stop_receipt is not None:
        controls["stop_receipt"] = stop_receipt
    return controls


def build_predicted_mutation_outcome_link_request(
    outcome_input: PredictedMutationOutcomeInput,
) -> dict[str, Any]:
    """Build `POST /kernel/outcome-links` for a predicted governance change.

    A proposal owns the reviewable prediction. The outcome link later owns the
    measurement lifecycle. This helper carries the typed prediction across the
    boundary without computing the metric or recording a verdict.
    """

    proposal = dict(outcome_input.proposal)
    proposal_id = _required(str(proposal.get("proposal_id") or ""), "proposal_id")
    predicted_effect = proposal.get("predicted_effect")
    if not isinstance(predicted_effect, dict):
        raise ValueError("proposal.predicted_effect is required")
    metric_name = _required(
        str(predicted_effect.get("metric_name") or ""),
        "predicted_effect.metric_name",
    )
    metric_unit = _required(
        str(predicted_effect.get("metric_unit") or ""),
        "predicted_effect.metric_unit",
    )
    direction = _required(
        str(predicted_effect.get("direction") or ""),
        "predicted_effect.direction",
    )
    proposal_metadata = dict(proposal.get("metadata") or {})
    metadata = {
        **proposal_metadata,
        **dict(outcome_input.metadata or {}),
        "source_proposal_id": proposal_id,
        "source_proposal_ref": f"governance_change:{proposal_id}",
        "source_recipe": "predicted_mutation_outcome_link_request.v1",
        "predicted_effect": dict(predicted_effect),
    }
    if proposal_metadata.get("source_recipe"):
        metadata["source_proposal_recipe"] = proposal_metadata.get("source_recipe")
    if proposal.get("target_ref"):
        metadata["target_ref"] = proposal.get("target_ref")
    if proposal.get("change_kind"):
        metadata["proposal_change_kind"] = proposal.get("change_kind")
    return _without_none(
        {
            "outcome_link_id": outcome_input.outcome_link_id,
            "change_ref": f"governance_change:{proposal_id}",
            "change_kind": "governance_change",
            "metric_name": metric_name,
            "metric_unit": metric_unit,
            "direction": direction,
            "created_by": _required(outcome_input.created_by, "created_by"),
            "learning_event_id": outcome_input.learning_event_id,
            "owner_role": outcome_input.owner_role or proposal.get("owner_role"),
            "tenant_id": outcome_input.tenant_id or proposal.get("tenant_id"),
            "project_id": outcome_input.project_id or proposal.get("project_id"),
            "metadata": metadata,
        }
    )


def build_predicted_mutation_reversal_review_request(
    review_input: PredictedMutationReversalReviewInput,
) -> dict[str, Any]:
    """Build `POST /kernel/routine-reviews` for a failed predicted mutation.

    This creates a review request, not a reversal. The review can later record
    `amend`, `retire`, or `escalate` under the routine-review lifecycle.
    """

    link = dict(review_input.outcome_link)
    outcome_link_id = _required(
        str(link.get("outcome_link_id") or ""),
        "outcome_link_id",
    )
    change_ref = _required(str(link.get("change_ref") or ""), "change_ref")
    metadata = dict(link.get("metadata") or {})
    prediction_review = dict(metadata.get("prediction_review") or {})
    status = str(prediction_review.get("status") or "").strip()
    if review_input.require_failed_prediction and status != "prediction_failed":
        raise ValueError("outcome_link prediction_review.status must be prediction_failed")
    evidence_refs = _dedupe_refs(
        [
            f"outcome_link:{outcome_link_id}",
            change_ref,
            *list(prediction_review.get("evidence_refs") or []),
        ]
    )
    review_metadata = {
        **dict(review_input.metadata or {}),
        "source_recipe": "predicted_mutation_reversal_review_request.v1",
        "source_outcome_link_id": outcome_link_id,
        "source_outcome_link_ref": f"outcome_link:{outcome_link_id}",
        "prediction_review": prediction_review,
        "evidence_refs": evidence_refs,
        "reversal_candidate": status == "prediction_failed",
    }
    return _without_none(
        {
            "review_id": review_input.review_id,
            "routine_ref": change_ref,
            "routine_kind": "other",
            "review_due_utc": _required(review_input.review_due_utc, "review_due_utc"),
            "scheduled_by": _required(review_input.scheduled_by, "scheduled_by"),
            "tenant_id": review_input.tenant_id or link.get("tenant_id"),
            "project_id": review_input.project_id or link.get("project_id"),
            "reason": (
                "Predicted structural mutation failed its outcome review; "
                "evaluate amend, retire, or escalation."
            ),
            "review_cadence": "prediction_failure",
            "metadata": review_metadata,
        }
    )


def build_execution_evidence_route_packet(
    route_input: ExecutionEvidenceRouteInput,
) -> dict[str, Any]:
    """Build service-call shapes for routing execution evidence.

    This is the standard adapter recipe for "an agent/runtime could not or
    should not continue." It composes existing routes:

    1. record a `CapabilitySignal`;
    2. optionally route that signal;
    3. list projected learning-transition candidates;
    4. optionally prepare a governance-change request template.

    The caller must still perform each service request, handle leases, and
    inspect/approve any resulting governance change.
    """

    signal_id = str(route_input.signal_id or "").strip()
    signal_ref = (
        f"capability_signal:{signal_id}"
        if signal_id
        else "capability_signal:{created_signal_id}"
    )
    object_ref = (
        route_input.work_id
        or route_input.run_id
        or _required(route_input.source_ref, "source_ref")
    )
    record_body = _without_none(
        {
            "signal_id": signal_id or None,
            "signal_kind": _required(route_input.signal_kind, "signal_kind"),
            "source_ref": _required(route_input.source_ref, "source_ref"),
            "summary": _required(route_input.summary, "summary"),
            "owner_role": _required(route_input.owner_role, "owner_role"),
            "severity": route_input.severity,
            "worker_ref": route_input.worker_ref,
            "run_id": route_input.run_id,
            "work_id": route_input.work_id,
            "tenant_id": route_input.tenant_id,
            "project_id": route_input.project_id,
            "capability_ref": route_input.capability_ref,
            "threshold_ref": route_input.threshold_ref,
            "recommended_route": route_input.recommended_route,
            "route_target_ref": route_input.route_target_ref,
            "counts_as_failure": route_input.counts_as_failure,
            "evidence_refs": list(route_input.evidence_refs or []),
            "metadata": dict(route_input.metadata or {}),
        }
    )
    calls: list[dict[str, Any]] = [
        {
            "label": "record_capability_signal",
            "method": "POST",
            "path": "/kernel/capability-signals",
            "body": record_body,
            "expected_ref": signal_ref,
        }
    ]

    if route_input.route_kind:
        route_body = _without_none(
            {
                "route_kind": route_input.route_kind,
                "routed_by": route_input.routed_by,
                "rationale": route_input.route_rationale or route_input.summary,
                "target_ref": route_input.route_target_ref,
            }
        )
        calls.append(
            {
                "label": "route_capability_signal",
                "method": "POST",
                "path": f"/kernel/capability-signals/{signal_id or '{created_signal_id}'}/route",
                "body": route_body,
                "requires": ["record_capability_signal"],
            }
        )

    candidate_lookup = {
        "source": "capability",
        "source_kind": "capability_signal",
        "object_ref": object_ref,
        "source_refs_contains": signal_ref,
    }
    calls.append(
        {
            "label": "list_learning_transition_candidates",
            "method": "GET",
            "path": "/kernel/learning-transition-candidates?source=capability",
            "match": candidate_lookup,
            "requires": ["record_capability_signal"],
        }
    )

    if route_input.governance_change_target_ref:
        proposal_body = _without_none(
            {
                "target_ref": route_input.governance_change_target_ref,
                "change_kind": route_input.governance_change_kind,
                "proposed_by": route_input.proposed_by,
                "expected_behavior_change": route_input.summary,
                "risk_summary": "Generated from routed execution evidence; requires review before mutation.",
                "metadata": {
                    "source_recipe": "execution_evidence_route_packet.v1",
                    "source_capability_signal_ref": signal_ref,
                    "candidate_lookup": candidate_lookup,
                },
            }
        )
        calls.append(
            {
                "label": "open_governance_change_from_candidate",
                "method": "POST",
                "path": "/kernel/learning-transition-candidates/{candidate_id}/governance-change",
                "body": proposal_body,
                "requires": ["list_learning_transition_candidates"],
            }
        )

    return {
        "schema": "execution_evidence_route_packet.v1",
        "signal_ref": signal_ref,
        "object_ref": object_ref,
        "evidence_carrier_refs": _dedupe_refs(
            [signal_ref] + list(route_input.evidence_refs or [])
        ),
        "candidate_lookup": candidate_lookup,
        "service_calls": calls,
        "boundary": {
            "does_not_execute_runtime": True,
            "does_not_approve_governance": True,
            "does_not_mutate_files": True,
        },
    }


def build_governed_run_operator_summary(
    summary_input: GovernedRunOperatorSummaryInput,
) -> dict[str, Any]:
    """Build a compact operator inspection projection for governed runs.

    This is a read model over run controls, bundles, proofs, artifacts, and
    commands. It does not create or validate authoritative kernel state; it
    gives demos and adapters one stable shape for "what should a human inspect
    first after this run?".
    """

    artifacts = _normalize_artifacts(summary_input.artifacts or [])
    commands = _normalize_commands(summary_input.commands or [])
    bundles = [
        _compact_bundle_summary(bundle)
        for bundle in summary_input.bundle_summaries or []
    ]
    proofs = [
        _compact_mutation_proof(proof)
        for proof in summary_input.mutation_proofs or []
    ]
    execution_signals = [
        _compact_execution_signal(signal)
        for signal in summary_input.execution_signals or []
    ]
    learning_candidates = [
        _compact_learning_candidate(candidate)
        for candidate in summary_input.learning_candidates or []
    ]
    phase_plans = [
        _compact_phase_plan(plan)
        for plan in summary_input.phase_plans or []
    ]
    learning_closure = [
        _compact_learning_closure(row)
        for row in summary_input.learning_closure or []
    ]
    summary = dict(summary_input.summary)
    operator_burden = (
        _normalize_operator_burden(
            summary_input.operator_burden,
            bundles=bundles,
            summary=summary,
        )
        if summary_input.operator_burden is not None
        else None
    )
    invalid_proofs = [
        proof for proof in proofs if proof.get("valid") is False
    ]
    open_signals = [
        signal for signal in execution_signals if signal.get("status") != "closed"
    ]
    blocking_signals = [
        signal
        for signal in open_signals
        if signal.get("severity") == "blocking"
    ]
    blocked_phase_plans = [
        plan for plan in phase_plans if plan.get("status") == "blocked"
    ]
    review_candidates = [
        candidate
        for candidate in learning_candidates
        if candidate.get("status") in {"open", "review_ready"}
    ]
    learning_closure_needs_review = [
        row
        for row in learning_closure
        if row.get("outcome_review_status") in {"prediction_failed", "unknown"}
        or row.get("routine_review_status") in {"due", "overdue", "unknown"}
    ]
    status = {
        "verdict": summary.get("verdict"),
        "termination_reason": summary.get("termination_reason"),
        "bundle_count": len(bundles),
        "mutation_proof_count": len(proofs),
        "invalid_mutation_proofs": len(invalid_proofs),
        "open_execution_signals": len(open_signals),
        "blocking_execution_signals": len(blocking_signals),
        "blocked_phase_plans": len(blocked_phase_plans),
        "review_candidates": len(review_candidates),
        "learning_closure_count": len(learning_closure),
        "learning_closure_needs_review": len(learning_closure_needs_review),
    }
    if operator_burden:
        burden_summary = operator_burden["summary"]
        status.update(
            {
                "operator_burden_level": burden_summary["burden_level"],
                "operator_burden_score": burden_summary["burden_score"],
                "estimated_human_touchpoints": burden_summary[
                    "estimated_human_touchpoints"
                ],
            }
        )
    return {
        "schema": "governed_run_operator_summary.v1",
        "run_label": _required(summary_input.run_label, "run_label"),
        "run_ref": _required(summary_input.run_ref, "run_ref"),
        "summary": summary,
        "operator_controls": dict(summary_input.operator_controls or {}),
        "status": status,
        "artifacts": artifacts,
        "commands": commands,
        "inspection_order": list(summary_input.inspection_order or []),
        "bundle_summaries": bundles,
        "mutation_proofs": proofs,
        "execution_signals": execution_signals,
        "learning_candidates": learning_candidates,
        "phase_plans": phase_plans,
        "learning_closure": learning_closure,
        **({"operator_burden": operator_burden} if operator_burden else {}),
        "metadata": dict(summary_input.metadata or {}),
    }


def summarize_operator_burden_field_pilot(
    rows: list[dict[str, Any]],
    *,
    min_baseline_runs: int = 1,
    min_pilot_runs: int = 1,
    max_touchpoint_increase_rate: float = 0.1,
    projection_tolerance: float = 1.0,
) -> dict[str, Any]:
    """Summarize measured operator burden in a bounded field pilot.

    This is a read model over pilot rows. It compares baseline and pilot human
    coordination burden, checks whether runbook projections undercounted actual
    touchpoints, and emits review reasons. It does not schedule, assign,
    optimize, approve, or mutate any work.
    """

    normalized = [
        _operator_burden_pilot_row(row, index=index)
        for index, row in enumerate(rows)
        if isinstance(row, dict)
    ]
    baseline = [row for row in normalized if row["phase"] == "baseline"]
    pilot = [row for row in normalized if row["phase"] == "pilot"]
    phases = {
        "baseline": _operator_burden_phase_summary(baseline),
        "pilot": _operator_burden_phase_summary(pilot),
    }
    deltas = _operator_burden_phase_deltas(phases["baseline"], phases["pilot"])
    projection_fit = _operator_burden_projection_fit(
        pilot,
        tolerance=projection_tolerance,
    )
    enough_records = (
        len(baseline) >= min_baseline_runs
        and len(pilot) >= min_pilot_runs
    )
    review_reasons = _operator_burden_review_reasons(
        phases=phases,
        deltas=deltas,
        projection_fit=projection_fit,
        enough_records=enough_records,
        min_baseline_runs=min_baseline_runs,
        min_pilot_runs=min_pilot_runs,
        max_touchpoint_increase_rate=max_touchpoint_increase_rate,
    )
    if not enough_records:
        measurement_status = "insufficient_evidence"
    elif review_reasons:
        measurement_status = "needs_review"
    else:
        measurement_status = "stable"
    return {
        "schema": "operator_burden_field_pilot_summary.v1",
        "n_total": len(normalized),
        "min_baseline_runs": min_baseline_runs,
        "min_pilot_runs": min_pilot_runs,
        "enough_records": enough_records,
        "measurement_status": measurement_status,
        "phases": phases,
        "deltas": deltas,
        "projection_fit": projection_fit,
        "review_reasons": review_reasons,
        "boundary": {
            "does_not_assign_work": True,
            "does_not_schedule_work": True,
            "does_not_approve_policy": True,
            "does_not_optimize_routing": True,
            "does_not_mutate_kernel_state": True,
        },
    }


def render_governed_run_operator_summary_markdown(summary: dict[str, Any]) -> str:
    """Render `governed_run_operator_summary.v1` for terminal/repo review."""

    if summary.get("schema") != "governed_run_operator_summary.v1":
        raise ValueError("summary schema must be governed_run_operator_summary.v1")
    run_summary = summary.get("summary") or {}
    status = summary.get("status") or {}
    lines = [
        "# Governed Run Operator Summary",
        "",
        "## Run Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Run | {_md(summary.get('run_label', ''))} |",
        f"| Run ref | {_md(summary.get('run_ref', ''))} |",
        f"| Verdict | {_md(status.get('verdict', run_summary.get('verdict', '')))} |",
        f"| Termination reason | {_md(status.get('termination_reason', run_summary.get('termination_reason', '')))} |",
        f"| Budget units consumed | {_md(run_summary.get('budget_units_consumed', ''))} |",
        f"| Budget units remaining | {_md(run_summary.get('budget_units_remaining', ''))} |",
        f"| Bundles | {_md(status.get('bundle_count', 0))} |",
        f"| Mutation proofs | {_md(status.get('mutation_proof_count', 0))} |",
        f"| Invalid mutation proofs | {_md(status.get('invalid_mutation_proofs', 0))} |",
        f"| Open execution signals | {_md(status.get('open_execution_signals', 0))} |",
        f"| Blocking execution signals | {_md(status.get('blocking_execution_signals', 0))} |",
        f"| Blocked phase plans | {_md(status.get('blocked_phase_plans', 0))} |",
        f"| Review candidates | {_md(status.get('review_candidates', 0))} |",
        f"| Learning closure rows | {_md(status.get('learning_closure_count', 0))} |",
        f"| Learning closure needs review | {_md(status.get('learning_closure_needs_review', 0))} |",
        f"| Operator burden level | {_md(status.get('operator_burden_level', ''))} |",
        f"| Estimated human touchpoints | {_md(status.get('estimated_human_touchpoints', ''))} |",
        "",
        "## Inspect First",
        "",
        "| Artifact | Ref | Purpose |",
        "| --- | --- | --- |",
    ]
    for artifact in summary.get("artifacts") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(artifact.get("label", "")),
                    _md(artifact.get("ref", "")),
                    _md(artifact.get("purpose", "")),
                ]
            )
                + " |"
            )
    if summary.get("execution_signals") or summary.get("phase_plans") or summary.get("learning_candidates"):
        lines.extend(
            [
                "",
                "## Execution Health",
                "",
                "| Kind | Ref | Status | Route / Next Review |",
                "| --- | --- | --- | --- |",
            ]
        )
        for signal in summary.get("execution_signals") or []:
            route_or_source = str(signal.get("recommended_route") or "")
            if signal.get("source_ref"):
                route_or_source = (
                    f"{route_or_source} via {signal['source_ref']}"
                    if route_or_source
                    else str(signal["source_ref"])
                )
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(signal.get("signal_kind", "capability_signal")),
                        _md(signal.get("signal_ref", "")),
                        _md(signal.get("status", "")),
                        _md(route_or_source),
                    ]
                )
                + " |"
            )
        for plan in summary.get("phase_plans") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        "phase_execution_plan",
                        _md(plan.get("plan_ref", "")),
                        _md(plan.get("status", "")),
                        _md(plan.get("current_phase", "")),
                    ]
                )
                + " |"
            )
        for candidate in summary.get("learning_candidates") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(candidate.get("transition_kind", "learning_candidate")),
                        _md(candidate.get("candidate_ref", "")),
                        _md(candidate.get("status", "")),
                        _md(candidate.get("suggested_owner_role", "")),
                    ]
                )
                + " |"
            )
    if summary.get("learning_closure"):
        lines.extend(
            [
                "",
                "## Learning Closure",
                "",
                "| Step | Learned | Changed context | Future work sees | Context packet | Outcome | Review | Evidence |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in summary["learning_closure"]:
            evidence_refs = row.get("evidence_refs") or []
            evidence = f"{len(evidence_refs)} refs"
            if evidence_refs:
                evidence = f"{evidence}; first: {evidence_refs[0]}"
            outcome = str(row.get("outcome_link_ref") or "")
            if row.get("outcome_review_status"):
                outcome = f"{row['outcome_review_status']} ({outcome})" if outcome else str(
                    row["outcome_review_status"]
                )
            review = str(row.get("routine_review_ref") or "")
            if row.get("routine_review_status"):
                review = f"{row['routine_review_status']} ({review})" if review else str(
                    row["routine_review_status"]
                )
            context_packets = ", ".join(row.get("context_packet_refs") or [])
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(row.get("step_id", "")),
                        _md(row.get("learning_event_ref", "")),
                        _md(row.get("changed_context_ref", "")),
                        _md(row.get("future_work_context", "")),
                        _md(context_packets),
                        _md(outcome),
                        _md(review),
                        _md(evidence),
                    ]
                )
                + " |"
            )
    if summary.get("operator_burden"):
        burden = summary["operator_burden"]
        burden_summary = burden.get("summary") or {}
        lines.extend(
            [
                "",
                "## Operator Burden",
                "",
                "| Field | Value |",
                "| --- | --- |",
                f"| Burden level | {_md(burden_summary.get('burden_level', ''))} |",
                f"| Burden score | {_md(burden_summary.get('burden_score', 0))} |",
                f"| Estimated human touchpoints | {_md(burden_summary.get('estimated_human_touchpoints', 0))} |",
                f"| Human-work sessions in bundles | {_md(burden_summary.get('bundle_human_work_sessions', 0))} |",
                f"| A2H pressure groups | {_md(burden_summary.get('pressure_groups', 0))} |",
                f"| Missing receipts | {_md(burden_summary.get('missing_receipts', 0))} |",
                f"| Stale sessions | {_md(burden_summary.get('stale_sessions', 0))} |",
                f"| Action-impact rows requiring review | {_md(burden_summary.get('action_impact_review_required', 0))} |",
                f"| Action-impact review rate | {_md(burden_summary.get('action_impact_review_rate', 0.0))} |",
                f"| Accountability cases in bundles | {_md(burden_summary.get('bundle_accountability_cases', 0))} |",
                "",
                "| Pressure group | Active | Waiting | Missing receipts | Stale | Recommendation |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for group in burden.get("pressure_groups") or []:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(
                            f"{group.get('agent_counterparty_role', '')}/"
                            f"{group.get('bottleneck_class', '')}"
                        ),
                        _md(group.get("active_count", 0)),
                        _md(group.get("waiting_count", 0)),
                        _md(group.get("missing_receipt_count", 0)),
                        _md(group.get("stale_count", 0)),
                        _md(group.get("recommendation", "")),
                    ]
                )
                + " |"
            )
        if burden.get("review_questions"):
            lines.extend(["", "Review questions:"])
            for question in burden["review_questions"]:
                lines.append(f"- {_md(question)}")
    if summary.get("bundle_summaries"):
        lines.extend(["", "## Bundles", "", "| Bundle | Verdict | Digest |", "| --- | --- | --- |"])
        for bundle in summary["bundle_summaries"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(bundle.get("bundle_id", "")),
                        _md(bundle.get("verdict", "")),
                        _md(bundle.get("bundle_digest", "")),
                    ]
                )
                + " |"
            )
    if summary.get("mutation_proofs"):
        lines.extend(
            [
                "",
                "## Mutation Proofs",
                "",
                "| Step | Target | Valid | Commit |",
                "| --- | --- | --- | --- |",
            ]
        )
        for proof in summary["mutation_proofs"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(proof.get("step_id", "")),
                        _md(proof.get("target_ref", "")),
                        _md(proof.get("valid", "")),
                        _md(proof.get("commit", "")),
                    ]
                )
                + " |"
            )
    lines.extend(["", "## Commands", "", "```bash"])
    for command in summary.get("commands") or []:
        lines.append(f"# {command.get('label', '')}")
        lines.append(str(command.get("command", "")))
        lines.append("")
    lines.extend(["```", ""])
    return "\n".join(lines)


def build_governed_action_composition_packet(
    composition_input: GovernedActionCompositionInput,
) -> dict[str, Any]:
    """Build a read-only evidence-chain coverage packet for one governed action.

    This is a typed traceability matrix over observed outputs and canonical
    refs. It is intentionally not a workflow engine: it does not execute
    service calls, schedule missing work, approve changes, or mutate state.
    """

    observed = dict(composition_input.observed_result or {})
    supplied_refs = _dedupe_refs(list(composition_input.evidence_refs or []))
    profile = _governed_action_composition_profile(composition_input.profile)
    links = [
        _governed_action_composition_link(row, observed, supplied_refs)
        for row in profile["requirements"]
    ]
    required = [row for row in links if row["required"]]
    missing = [row for row in links if row["status"] == "missing"]
    failed = [row for row in links if row["status"] == "failed"]
    required_blockers = [
        row for row in required if row["status"] in {"missing", "failed"}
    ]
    if any(row["status"] == "failed" for row in required):
        status = "failed_evidence"
    elif required_blockers:
        status = "missing_required_evidence"
    else:
        status = "ready_for_review"
    return {
        "schema": "governed_action_composition_packet.v1",
        "packet_kind": "governed_action_traceability_matrix",
        "profile": profile["profile"],
        "action_label": _required(composition_input.action_label, "action_label"),
        "generated_at_utc": composition_input.generated_at_utc,
        "read_only": True,
        "projection_only": True,
        "status": status,
        "summary": {
            "links": len(links),
            "required_links": len(required),
            "passed_links": sum(1 for row in links if row["status"] == "passed"),
            "missing_links": len(missing),
            "failed_links": len(failed),
            "required_blockers": len(required_blockers),
        },
        "links": links,
        "review_questions": _governed_action_composition_review_questions(
            links,
            profile_label=profile["label"],
        ),
        "evidence_refs": supplied_refs,
        "boundary": {
            "does_not_execute_commands": True,
            "does_not_call_service_routes": True,
            "does_not_approve_governance": True,
            "does_not_schedule_work": True,
            "does_not_mutate_kernel_state": True,
            "does_not_verify_row_existence": True,
        },
        "metadata": dict(composition_input.metadata or {}),
    }


def build_adoption_readiness_packet(
    packet_input: AdoptionReadinessPacketInput,
) -> dict[str, Any]:
    """Build a read-only adoption readiness packet.

    The packet is a reviewer handoff over existing command outputs and routes.
    It is intentionally not a runner, scheduler, release approval, or state
    store. Missing checks remain visible so an adopter can run only the commands
    that matter for their next decision.
    """

    observed_results = {
        key: dict(value)
        for key, value in (packet_input.observed_results or {}).items()
        if isinstance(value, dict)
    }
    checks = _adoption_readiness_checks(
        include_live_agent=packet_input.include_live_agent,
        include_release_gate=packet_input.include_release_gate,
    )
    rows = [
        _adoption_check_row(check, observed_results.get(check["check_id"]))
        for check in checks
    ]
    composition_packets = _adoption_composition_packets(
        rows=rows,
        checks=checks,
        observed_results=observed_results,
    )
    composition_blockers = sum(
        packet["summary"]["required_blockers"] for packet in composition_packets
    )
    required = [row for row in rows if row["required"]]
    missing = [row for row in rows if row["status"] == "missing"]
    failed = [row for row in rows if row["status"] == "failed"]
    warning = [row for row in rows if row["status"] == "warning"]
    observed = [row for row in rows if row["status"] in {"passed", "warning"}]
    release_blockers = [
        row
        for row in required
        if row["status"] in {"missing", "failed"}
    ]
    evidence_quality_blockers = [
        row
        for row in required
        if row["status"] in {"passed", "warning"}
        and row.get("evidence_quality") == "partial"
    ]
    optional_evidence_blockers = [
        row
        for row in rows
        if not row["required"] and row["status"] == "failed"
    ]
    packet: dict[str, Any] = {
        "schema": "adoption_readiness_packet.v1",
        "packet_kind": "adoption_readiness_handoff",
        "target_label": _required(packet_input.target_label, "target_label"),
        "generated_at_utc": packet_input.generated_at_utc,
        "read_only": True,
        "projection_only": True,
        "reviewer_path": _adoption_reviewer_path(packet_input.metadata or {}),
        "summary": {
            "checks": len(rows),
            "required_checks": len(required),
            "observed_checks": len(observed),
            "missing_checks": len(missing),
            "failed_checks": len(failed),
            "warning_checks": len(warning),
            "required_blockers": len(release_blockers),
            "evidence_quality_blockers": len(evidence_quality_blockers),
            "optional_evidence_blockers": len(optional_evidence_blockers),
            "composition_packets": len(composition_packets),
            "composition_blockers": composition_blockers,
            "ready_for_human_adoption_review": (
                not release_blockers
                and not evidence_quality_blockers
                and not optional_evidence_blockers
                and composition_blockers == 0
            ),
        },
        "checks": rows,
        "composition_packets": composition_packets,
        "review_questions": _adoption_review_questions(rows),
        "evidence_refs": _dedupe_refs(list(packet_input.evidence_refs or [])),
        "boundary": {
            "does_not_execute_commands": True,
            "does_not_approve_release": True,
            "does_not_mutate_kernel_state": True,
            "does_not_replace_human_diff_review": True,
        },
        "metadata": dict(packet_input.metadata or {}),
    }
    packet["markdown"] = render_adoption_readiness_packet_markdown(packet)
    return packet


def render_adoption_readiness_packet_markdown(packet: dict[str, Any]) -> str:
    """Render `adoption_readiness_packet.v1` as a review handoff."""

    if packet.get("schema") != "adoption_readiness_packet.v1":
        raise ValueError("packet schema must be adoption_readiness_packet.v1")
    summary = packet.get("summary") or {}
    lines = [
        "# Adoption Readiness Packet",
        "",
        "## Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Target | {_md(packet.get('target_label', ''))} |",
        f"| Required checks | {_md(summary.get('required_checks', 0))} |",
        f"| Observed checks | {_md(summary.get('observed_checks', 0))} |",
        f"| Missing checks | {_md(summary.get('missing_checks', 0))} |",
        f"| Failed checks | {_md(summary.get('failed_checks', 0))} |",
        f"| Warning checks | {_md(summary.get('warning_checks', 0))} |",
        f"| Required blockers | {_md(summary.get('required_blockers', 0))} |",
        f"| Evidence quality blockers | {_md(summary.get('evidence_quality_blockers', 0))} |",
        f"| Optional evidence blockers | {_md(summary.get('optional_evidence_blockers', 0))} |",
        f"| Ready for human review | {_md(summary.get('ready_for_human_adoption_review', False))} |",
        "",
        "## Reviewer Path",
        "",
    ]
    reviewer_path = packet.get("reviewer_path") or {}
    if reviewer_path.get("purpose"):
        lines.extend(
            [
                f"Purpose: {_md(reviewer_path.get('purpose', ''))}",
                "",
            ]
        )
    if reviewer_path.get("use_when"):
        lines.extend(
            [
                f"Use when: {_md(reviewer_path.get('use_when', ''))}",
                "",
            ]
        )
    if reviewer_path.get("not_a"):
        lines.extend(
            [
                "Not a: "
                + _md(", ".join(str(item) for item in reviewer_path["not_a"])),
                "",
            ]
        )
    lines.extend(
        [
            "| Step | Command | Status | Description |",
            "| --- | --- | --- | --- |",
        ]
    )
    for step in reviewer_path.get("steps") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(
                        f"{step.get('step', '')}/{step.get('total_steps', '')}"
                    ),
                    _md(step.get("command", "")),
                    _md(step.get("packet_status", "")),
                    _md(step.get("description", "")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| Check | Status | Required | Evidence quality | Command | Evidence | Missing expected fields |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in packet.get("checks") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(row.get("label", "")),
                    _md(row.get("status", "")),
                    _md(row.get("required", "")),
                    _md(row.get("evidence_quality", "")),
                    _md(row.get("command", "")),
                    _md(", ".join(row.get("evidence_refs") or [])),
                    _md(", ".join(row.get("missing_evidence_fields") or [])),
                ]
            )
            + " |"
        )
    if packet.get("review_questions"):
        lines.extend(["", "## Review Questions", ""])
        for question in packet["review_questions"]:
            lines.append(f"- {_md(question)}")
    if packet.get("composition_packets"):
        lines.extend(["", "## Composition Coverage", ""])
        for composition in packet["composition_packets"]:
            summary = composition.get("summary") or {}
            lines.extend(
                [
                    f"### {_md(composition.get('action_label', ''))}",
                    "",
                    "| Field | Value |",
                    "| --- | --- |",
                    f"| Profile | {_md(composition.get('profile', ''))} |",
                    f"| Status | {_md(composition.get('status', ''))} |",
                    f"| Required blockers | {_md(summary.get('required_blockers', 0))} |",
                    "",
                    "| Link | Status | Required | Evidence |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for link in composition.get("links") or []:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _md(link.get("label", "")),
                            _md(link.get("status", "")),
                            _md(link.get("required", "")),
                            _md(", ".join(link.get("evidence_refs") or [])),
                        ]
                    )
                    + " |"
                )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- This packet does not execute commands.",
            "- This packet does not approve a release or replace human diff review.",
            "- This packet does not write kernel state.",
            "",
        ]
    )
    return "\n".join(lines)


def refresh_adoption_readiness_packet_projection(
    packet: dict[str, Any],
) -> dict[str, Any]:
    """Refresh projection-only fields on a stored adoption readiness packet."""

    if packet.get("schema") != "adoption_readiness_packet.v1":
        raise ValueError("packet schema must be adoption_readiness_packet.v1")
    refreshed = dict(packet)
    metadata = dict(refreshed.get("metadata") or {})
    refreshed["metadata"] = metadata
    refreshed["reviewer_path"] = _adoption_reviewer_path(metadata)
    refreshed["markdown"] = render_adoption_readiness_packet_markdown(refreshed)
    return refreshed


def build_governed_mutation_evidence_pack(
    evidence_input: GovernedMutationEvidenceInput,
) -> dict[str, Any]:
    """Build shared evidence projections for governed mutation clients.

    This is a client-side composition helper. It does not create, approve, or
    validate any kernel state. It keeps work-completion artifact refs and
    mutation-proof evidence refs aligned so demos/adapters do not hand-roll the
    same reference lists twice.
    """

    artifact_refs = governed_work_completion_artifact_refs(
        proposal_id=evidence_input.proposal_id,
        learning_event_id=evidence_input.learning_event_id,
        attestation_id=evidence_input.attestation_id,
        run_id=evidence_input.run_id,
        phase_execution_plan_id=evidence_input.phase_execution_plan_id,
        a2a_refs=evidence_input.a2a_refs,
        reviewer_evidence_refs=evidence_input.reviewer_evidence_refs,
        decision_case_ref=evidence_input.decision_case_ref,
        planner_evidence_refs=evidence_input.planner_evidence_refs,
        trace_event_ids=evidence_input.trace_event_ids,
    )
    evidence_carrier_refs = governed_mutation_evidence_refs(
        capability_signal_id=evidence_input.capability_signal_id,
        learning_candidate_id=evidence_input.learning_candidate_id,
        phase_execution_plan_id=evidence_input.phase_execution_plan_id,
        a2a_refs=evidence_input.a2a_refs,
        reviewer_evidence_refs=evidence_input.reviewer_evidence_refs,
        decision_case_ref=evidence_input.decision_case_ref,
        planner_evidence_refs=evidence_input.planner_evidence_refs,
        trace_event_ids=evidence_input.trace_event_ids,
    )
    return {
        "schema": "governed_mutation_evidence_pack.v1",
        "artifact_refs": artifact_refs,
        "evidence_carrier_refs": evidence_carrier_refs,
        "summary": {
            "artifact_refs": len(artifact_refs),
            "evidence_carrier_refs": len(evidence_carrier_refs),
            "a2a_refs": len(evidence_input.a2a_refs or []),
            "reviewer_evidence_refs": len(evidence_input.reviewer_evidence_refs or []),
            "planner_evidence_refs": len(evidence_input.planner_evidence_refs or []),
            "trace_event_ids": len(evidence_input.trace_event_ids or []),
        },
    }


def validate_governed_mutation_evidence_pack(
    pack: dict[str, Any],
    *,
    required_evidence_prefixes: list[str] | None = None,
    required_artifact_kinds: list[str] | None = None,
) -> dict[str, Any]:
    """Validate the shape of a governed mutation evidence pack.

    This is an adopter-side preflight before work completion or proof-build
    calls. It does not validate that the referenced kernel rows exist; service
    routes remain responsible for authoritative state checks. Callers can also
    require artifact kinds so work-completion receipts stay aligned with the
    proof evidence carried forward.
    """

    errors: list[str] = []
    if pack.get("schema") != "governed_mutation_evidence_pack.v1":
        errors.append("schema must be governed_mutation_evidence_pack.v1")

    artifact_refs = pack.get("artifact_refs")
    if not isinstance(artifact_refs, list) or not artifact_refs:
        errors.append("artifact_refs must be a non-empty list")
        artifact_refs = []

    evidence_refs = pack.get("evidence_carrier_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        errors.append("evidence_carrier_refs must be a non-empty list")
        evidence_refs = []

    malformed_artifact_refs = [
        index
        for index, ref in enumerate(artifact_refs)
        if not isinstance(ref, dict)
        or not str(ref.get("kind") or "").strip()
        or not str(ref.get("ref") or "").strip()
    ]
    if malformed_artifact_refs:
        errors.append(
            "artifact_refs contain malformed entries at indexes "
            + ", ".join(str(index) for index in malformed_artifact_refs)
        )

    malformed_evidence_refs = [
        index
        for index, ref in enumerate(evidence_refs)
        if not isinstance(ref, str) or not ref.strip()
    ]
    if malformed_evidence_refs:
        errors.append(
            "evidence_carrier_refs contain malformed entries at indexes "
            + ", ".join(str(index) for index in malformed_evidence_refs)
        )

    refs = [str(ref).strip() for ref in evidence_refs if isinstance(ref, str)]
    for prefix in required_evidence_prefixes or []:
        if not any(ref.startswith(prefix) for ref in refs):
            errors.append(f"missing evidence ref with prefix {prefix}")

    artifact_kinds = [
        str(ref.get("kind") or "").strip()
        for ref in artifact_refs
        if isinstance(ref, dict)
    ]
    for kind in required_artifact_kinds or []:
        if kind not in artifact_kinds:
            errors.append(f"missing artifact ref with kind {kind}")

    return {
        "schema": "governed_mutation_evidence_pack_validation.v1",
        "valid": not errors,
        "errors": errors,
        "summary": {
            "artifact_refs": len(artifact_refs),
            "evidence_carrier_refs": len(evidence_refs),
            "required_evidence_prefixes": len(required_evidence_prefixes or []),
            "required_artifact_kinds": len(required_artifact_kinds or []),
        },
    }


def governed_mutation_evidence_requirements(
    *,
    require_planner: bool = True,
    require_a2a: bool = True,
    require_decision: bool = True,
    require_phase_plan: bool = True,
    require_trace: bool = True,
    require_reviewer_evidence: bool = False,
) -> dict[str, list[str]]:
    """Return the standard evidence requirements for mutation clients.

    The result is intentionally just two lists for
    `validate_governed_mutation_evidence_pack`. It encodes the generic kernel
    lifecycle shape without introducing a second workflow engine.
    """

    evidence_prefixes = [
        "capability_signal:",
        "learning_transition_candidate:",
    ]
    artifact_kinds = [
        "governance_change",
        "learning_event",
        "attestation",
        "run",
    ]
    if require_phase_plan:
        evidence_prefixes.append("phase_execution_plan:")
        artifact_kinds.append("phase_execution_plan")
    if require_a2a:
        evidence_prefixes.append("a2a_message:")
        artifact_kinds.append("a2a_message")
    if require_decision:
        evidence_prefixes.append("decision_aggregation_case:")
        artifact_kinds.append("decision_aggregation_case")
    if require_planner:
        evidence_prefixes.append("planner_receipt:")
        artifact_kinds.append("planner_receipt")
    if require_trace:
        evidence_prefixes.append("multi_agent_trace_event:")
        artifact_kinds.append("multi_agent_trace_event")
    if require_reviewer_evidence:
        evidence_prefixes.append("attestation:")
        artifact_kinds.append("action_attestation")
    return {
        "required_evidence_prefixes": evidence_prefixes,
        "required_artifact_kinds": artifact_kinds,
    }


def build_mutation_proof_request(
    recipe_input: GovernedMutationRecipeInput,
) -> dict[str, Any]:
    """Return the POST body for `/kernel/mutation-proofs/build`.

    The kernel service remains the proof builder and validator. This helper is
    intentionally a request shaper so demos and adapters do not each hand-roll
    the same proof request.
    """

    return asdict(recipe_input)


def governed_work_completion_artifact_refs(
    *,
    proposal_id: str,
    learning_event_id: str,
    attestation_id: str,
    run_id: str,
    phase_execution_plan_id: str | None = None,
    a2a_refs: list[str] | None = None,
    reviewer_evidence_refs: list[str] | None = None,
    decision_case_ref: str | None = None,
    planner_evidence_refs: list[str] | None = None,
    trace_event_ids: list[str] | None = None,
) -> list[dict[str, str]]:
    """Build common artifact refs for completing governed work items.

    The result is a projection convenience for clients. The work-item lifecycle
    still lives in `work_items` and the service route that consumes these refs.
    """

    refs = [
        {"kind": "governance_change", "ref": f"governance_change:{proposal_id}"},
        {"kind": "learning_event", "ref": f"learning_event:{learning_event_id}"},
        {"kind": "attestation", "ref": f"attestation:{attestation_id}"},
        {"kind": "run", "ref": f"run:{run_id}"},
    ]
    if phase_execution_plan_id:
        refs.append(
            {
                "kind": "phase_execution_plan",
                "ref": f"phase_execution_plan:{phase_execution_plan_id}",
            }
        )
    refs.extend({"kind": "a2a_message", "ref": ref} for ref in a2a_refs or [])
    refs.extend(
        {
            "kind": (
                "action_attestation"
                if ref.startswith("attestation:")
                else "reviewer_evidence"
            ),
            "ref": ref,
        }
        for ref in reviewer_evidence_refs or []
    )
    if decision_case_ref:
        refs.append({"kind": "decision_aggregation_case", "ref": decision_case_ref})
    refs.extend(
        {"kind": "planner_receipt", "ref": ref}
        for ref in planner_evidence_refs or []
        if ref.startswith("planner_receipt:")
    )
    refs.extend(
        {"kind": "multi_agent_trace_event", "ref": f"multi_agent_trace_event:{trace_id}"}
        for trace_id in trace_event_ids or []
    )
    return refs


def governed_mutation_evidence_refs(
    *,
    capability_signal_id: str,
    learning_candidate_id: str,
    phase_execution_plan_id: str,
    a2a_refs: list[str] | None = None,
    reviewer_evidence_refs: list[str] | None = None,
    decision_case_ref: str | None = None,
    planner_evidence_refs: list[str] | None = None,
    trace_event_ids: list[str] | None = None,
) -> list[str]:
    """Return canonical evidence refs for a governed structural mutation."""

    refs = [
        f"capability_signal:{capability_signal_id}",
        f"learning_transition_candidate:{learning_candidate_id}",
        f"phase_execution_plan:{phase_execution_plan_id}",
    ]
    refs.extend(a2a_refs or [])
    refs.extend(reviewer_evidence_refs or [])
    if decision_case_ref:
        refs.append(decision_case_ref)
    refs.extend(planner_evidence_refs or [])
    refs.extend(
        f"multi_agent_trace_event:{trace_id}" for trace_id in trace_event_ids or []
    )
    return _dedupe_refs(refs)


def _adoption_readiness_checks(
    *,
    include_live_agent: bool,
    include_release_gate: bool,
) -> list[dict[str, Any]]:
    checks = [
        {
            "check_id": "first_gated_action",
            "label": "First gated action",
            "command": "make first-gated-action",
            "required": True,
            "why": "Shortest no-cost proof of authority, work, receipt, attestation, outcome, and bundle.",
            "expectations": [
                ("bundle_validation.ok", True),
                ("summary.verdict", "passed"),
                ("work_item.status", "done"),
            ],
            "evidence_fields": [
                "summary.run_id",
                "summary.bundle_id",
                "summary.bundle_digest",
                "work_item.work_id",
            ],
        },
        {
            "check_id": "kernel_service_smoke",
            "label": "Kernel service smoke",
            "command": "make kernel-service-smoke",
            "required": True,
            "why": "Service-level proof for fenced mutation, governance, provenance, bundles, mutation proof, pressure, and policy-promotion routes.",
            "expectations": [
                ("ok", True),
                ("governed_run_bundle_verdict", "passed"),
                ("mutation_proof_validated", True),
                ("stale_rejected", True),
                (
                    "provenance_report_counts.provenance_follow_through",
                    "closed_loop_observed",
                ),
            ],
            "minimums": [
                ("provenance_report_counts.provenance_outcome_links", 1),
                ("provenance_report_counts.provenance_routine_reviews", 1),
                ("provenance_report_counts.provenance_learning_events", 1),
                ("provenance_report_counts.provenance_learning_use_receipts", 1),
            ],
            "evidence_fields": [
                "provenance_report_counts.provenance_report_coverage",
                "provenance_report_counts.provenance_follow_through",
                "provenance_report_counts.provenance_outcome_links",
                "provenance_report_counts.provenance_routine_reviews",
                "provenance_report_counts.provenance_learning_events",
                "provenance_report_counts.provenance_learning_use_receipts",
                "governance_proposal_status",
                "governance_decision",
            ],
        },
        {
            "check_id": "agent_fleet_audit_demo",
            "label": "Agent-fleet audit demo",
            "command": "make agent-fleet-audit-demo",
            "required": False,
            "why": "Adoption wedge for one local/subscription agent invocation receipt, action attestation, and bundle.",
            "expectations": [
                ("bundle_validation.ok", True),
                ("summary.verdict", "passed"),
            ],
            "evidence_fields": [
                "agent_invocation.receipt_ref",
                "summary.run_id",
                "summary.bundle_id",
                "summary.bundle_digest",
            ],
        },
        {
            "check_id": "learning_loop_walkthrough",
            "label": "Learning loop walkthrough",
            "command": "make learning-loop-walkthrough",
            "required": True,
            "why": "Proof that approved learning can become a pre-work context packet and later learning-use receipt.",
            "expectations": [
                ("ok", True),
                ("replayed_for_future_work", True),
            ],
            "evidence_fields": [
                "learning_event",
                "context_packet",
                "verified_context_packet",
                "learning_use_receipt",
                "learning_loop_state",
            ],
        },
        {
            "check_id": "adoption_demo",
            "label": "No-cost adoption suite",
            "command": "make adoption-demo",
            "required": False,
            "why": "Broader deterministic suite over native, adapter, failure, field-pilot, formal-provider, and governed self-evolution paths.",
            "expectations": [("ok", True)],
            "evidence_fields": ["summary.verdict", "verdict"],
            "allow_unstructured_pass": True,
        },
        {
            "check_id": "field_pilot_action_impact_demo",
            "label": "Field-pilot action-impact demo",
            "command": "make field-pilot-action-impact-demo",
            "required": False,
            "why": "Adoption-facing proof that measured pilot rows emit a review packet, not an automatic route write.",
            "expectations": [
                ("summary.verdict", "passed"),
                ("promotion_packet.status", "review_ready"),
            ],
            "evidence_fields": [
                "summary.action_impact_records",
                "promotion_packet.candidate_policy_id",
                "policy_evaluation.status",
            ],
        },
        {
            "check_id": "formal_provider_proof_pack",
            "label": "Formal-provider proof pack",
            "command": "make formal-provider-proof-pack",
            "required": False,
            "why": "Adoption proof that optional prover evidence enters as signed payloads with missing-evidence caveats, not as kernel-owned proof execution.",
            "expectations": [
                ("schema", "formal_provider_proof_pack.v1"),
                ("summary.ok", True),
                ("summary.trusted_bundle_verdict", "passed"),
                ("summary.missing_evidence_bundle_verdict", "incomplete"),
            ],
            "evidence_fields": [
                "summary.trusted_run_id",
                "summary.trusted_verification_id",
                "summary.missing_evidence_run_id",
                "summary.missing_evidence_verification_id",
            ],
        },
        {
            "check_id": "adapter_policy_preview",
            "label": "Adapter-policy preview",
            "command": "make langgraph-adapter-policy-preview",
            "required": False,
            "why": "Adoption proof that a bundled runtime adapter policy overlay previews as authority-neutral before any governed install.",
            "expectations": [
                ("schema", "adapter_policy_preview.v1"),
                ("ok", True),
                ("preview.status", "review_ready"),
                ("preview.can_proceed", True),
                ("preview.expands_authority", False),
                ("validation.expected_files_present", True),
                ("validation.authority_neutral", True),
            ],
            "evidence_fields": [
                "package",
                "package_version",
                "adapter_manifest.adapter_id",
                "adapter_manifest.protocol",
                "preview.status",
            ],
        },
        {
            "check_id": "runtime_adapter_proof_pack",
            "label": "Runtime-adapter proof pack",
            "command": "make runtime-adapter-proof-pack",
            "required": False,
            "why": "Adoption proof that external-runtime projections satisfy the same governed-run contract without importing runtime execution semantics.",
            "expectations": [
                ("schema", "runtime_adapter_proof_pack.v1"),
                ("summary.ok", True),
            ],
            "evidence_fields": [
                "summary.native_run_id",
                "summary.native_bundle_id",
                "summary.runtime_run_id",
                "summary.runtime_bundle_id",
            ],
        },
    ]
    if include_live_agent:
        checks.append(
            {
                "check_id": "bounded_live_agent_run",
                "label": "Bounded live agent run",
                "command": (
                    "make self-evolving-agent-preflight AGENT_RUNTIME=codex "
                    "AGENT_ADAPTER=codex_exec && make self-evolving-org-agent-demo "
                    "AGENT_RUNTIME=codex AGENT_ADAPTER=codex_exec "
                    "SELF_EVOLVING_DEMO_ITERATIONS=1 SELF_EVOLVING_DEMO_BUDGET_UNITS=1"
                ),
                "required": False,
                "why": "Optional proof that a local/subscription agent can operate inside bounded controls.",
                "expectations": [
                    ("summary.verdict", "passed"),
                    ("summary.budget_units_remaining", 0),
                    ("summary.mutation_proofs_valid", True),
                    ("summary.mutation_proof_replay_valid", True),
                ],
                "minimums": [
                    ("summary.budget_units_consumed", 1),
                    ("summary.learning_events", 1),
                    ("summary.learning_use_receipts", 1),
                    ("summary.context_packets", 1),
                    ("summary.verified_context_packets", 1),
                    ("summary.provenance_reports", 1),
                    ("summary.proposal_review_packets", 1),
                    ("summary.proposal_review_follow_through_closed_loop", 1),
                ],
                "evidence_fields": [
                    ("planner_transport", "summary.planner_transport"),
                    "summary.budget_units_consumed",
                    "summary.learning_events",
                    "summary.learning_use_receipts",
                    "summary.context_packets",
                    "summary.verified_context_packets",
                    "summary.provenance_reports",
                    "summary.proposal_review_packets",
                    "summary.proposal_review_follow_through_closed_loop",
                    "summary.mutation_proofs_valid",
                    "summary.mutation_proof_replay_valid",
                    "summary.termination_reason",
                ],
            }
        )
    if include_release_gate:
        checks.append(
            {
                "check_id": "release_candidate_check",
                "label": "Release candidate gate",
                "command": "make release-candidate-check",
                "required": True,
                "why": "Tag-candidate gate over public smoke, clean-container smoke, and release diff audit.",
                "expectations": [("ok", True)],
                "evidence_fields": [
                    "pytest",
                    "smoke_docker",
                    "release_diff_audit.unclassified",
                ],
                "allow_unstructured_pass": True,
            }
        )
    return checks


def _adoption_reviewer_path(metadata: dict[str, Any]) -> dict[str, Any]:
    path = command_operator_path("first_review")
    collector = str(metadata.get("collector") or "")
    steps: list[dict[str, Any]] = []
    for step in path.get("steps") or []:
        command = step.get("command")
        packet_status = "recommended"
        if command == "make smoke-public":
            packet_status = "external_gate"
        elif command == "make adoption-onramp-packet":
            packet_status = (
                "source_collector"
                if collector.endswith("adoption_onramp_packet.py")
                else "recommended_collector"
            )
        elif command == "make adoption-readiness-packet":
            packet_status = "this_packet"
        steps.append({**step, "packet_status": packet_status})
    return {
        **path,
        "steps": steps,
        "reviewer_note": (
            "Recommended first-review sequence only; this packet does not run "
            "or approve any step."
        ),
    }


def _adoption_check_row(
    check: dict[str, Any],
    observed: dict[str, Any] | None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    evidence_refs: list[str] = []
    result_summary: dict[str, Any] = {}
    present_evidence_fields: list[str] = []
    missing_evidence_fields: list[str] = []
    evidence_specs = list(check.get("evidence_fields") or [])
    expected_evidence_fields = [
        _evidence_field_label(spec) for spec in evidence_specs
    ]
    if observed is None:
        status = "missing"
        evidence_quality = "not_observed" if expected_evidence_fields else "not_expected"
    else:
        for field, expected in check.get("expectations") or []:
            actual = _deep_get(observed, field)
            if actual != expected:
                errors.append(f"{field} expected {expected!r}, observed {actual!r}")
        for field, minimum in check.get("minimums") or []:
            actual = _deep_get(observed, field)
            if actual in (None, "", [], {}):
                continue
            try:
                numeric = float(actual)
            except (TypeError, ValueError):
                errors.append(
                    f"{field} expected at least {minimum!r}, observed {actual!r}"
                )
                continue
            if numeric < float(minimum):
                errors.append(
                    f"{field} expected at least {minimum!r}, observed {actual!r}"
                )
        if errors and check.get("allow_unstructured_pass") and observed.get("ok") is True:
            warnings.extend(errors)
            errors = []
        for spec in evidence_specs:
            field = _evidence_field_label(spec)
            value = None
            matched_field = ""
            for candidate in _evidence_field_candidates(spec):
                candidate_value = _deep_get(observed, candidate)
                if candidate_value not in (None, "", [], {}):
                    value = candidate_value
                    matched_field = candidate
                    break
            if value not in (None, "", [], {}):
                present_evidence_fields.append(matched_field or field)
                result_summary[field] = value
                if isinstance(value, str):
                    evidence_refs.append(value)
            else:
                missing_evidence_fields.append(field)
        status = "failed" if errors else "warning" if warnings else "passed"
        evidence_quality = "complete"
        if missing_evidence_fields:
            evidence_quality = "partial"
            if status == "passed":
                status = "warning"
            warnings.append(
                "missing expected evidence field(s): "
                + ", ".join(missing_evidence_fields)
            )
    return {
        "check_id": check["check_id"],
        "label": check["label"],
        "command": check["command"],
        "required": bool(check.get("required")),
        "status": status,
        "why": check.get("why"),
        "errors": errors,
        "warnings": warnings,
        "evidence_refs": _dedupe_refs(evidence_refs),
        "result_summary": result_summary,
        "expected_evidence_fields": expected_evidence_fields,
        "present_evidence_fields": present_evidence_fields,
        "missing_evidence_fields": missing_evidence_fields,
        "evidence_quality": evidence_quality,
    }


def _evidence_field_candidates(spec: Any) -> list[str]:
    if isinstance(spec, (list, tuple)):
        return [str(item) for item in spec if str(item)]
    return [str(spec)] if str(spec) else []


def _evidence_field_label(spec: Any) -> str:
    candidates = _evidence_field_candidates(spec)
    return candidates[0] if candidates else ""


def _adoption_review_questions(rows: list[dict[str, Any]]) -> list[str]:
    questions = [
        "Did the shortest no-cost path show authority, bounded human work, action provenance, outcome evidence, and a bundle?",
        "Can a reviewer answer why a proposed change exists and what evidence supports it without reading raw JSONL?",
        "Are any missing checks intentionally deferred for this adoption decision?",
    ]
    if any(row["status"] == "failed" for row in rows):
        questions.append("Which failed check blocks adoption, and what source ref should repair it?")
    if any(row.get("evidence_quality") == "partial" and row["required"] for row in rows):
        questions.append("Which required check passed without its expected evidence fields, and should that output be regenerated before review?")
    if any(row["check_id"] == "bounded_live_agent_run" and row["status"] == "missing" for row in rows):
        questions.append("Is live-agent proof required now, or is deterministic fixture proof sufficient for this stage?")
    return questions


def _adoption_composition_packets(
    *,
    rows: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    observed_results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    check_labels = {check["check_id"]: check["label"] for check in checks}
    row_by_id = {row["check_id"]: row for row in rows}
    profiles = {
        "first_gated_action": "first_gated_action",
        "learning_loop_walkthrough": "learning_loop",
    }
    packets: list[dict[str, Any]] = []
    for check_id, profile in profiles.items():
        observed = observed_results.get(check_id)
        if observed is None:
            continue
        row = row_by_id.get(check_id) or {}
        packets.append(
            build_governed_action_composition_packet(
                GovernedActionCompositionInput(
                    action_label=check_labels.get(check_id, check_id),
                    observed_result=observed,
                    evidence_refs=list(row.get("evidence_refs") or []),
                    profile=profile,
                    metadata={"source_check_id": check_id},
                )
            )
        )
    return packets


def _governed_action_composition_profile(profile: str) -> dict[str, Any]:
    profile = profile.strip() or "first_gated_action"
    profiles: dict[str, dict[str, Any]] = {
        "first_gated_action": {
            "profile": "first_gated_action",
            "label": "First gated action",
            "requirements": [
                {
                    "link_id": "run_verdict",
                    "label": "Run passed",
                    "required": True,
                    "why": "The shortest adoption proof must finish with a passing governed-run verdict.",
                    "expectations": [("summary.verdict", "passed"), ("bundle_validation.ok", True)],
                    "min_evidence_refs": 0,
                },
                {
                    "link_id": "authority",
                    "label": "Authority resolved",
                    "required": True,
                    "why": "A governed action needs a role/mandate authority snapshot.",
                    "expectations": [("summary.authority_snapshot.status", "resolved")],
                    "fields": [
                        {"path": "summary.authority_snapshot.role_ref"},
                        {"path": "summary.authority_snapshot.mandate_ref"},
                        {"path": "summary.authority_snapshot.mandate_hash", "ref_prefix": "authority_hash:"},
                    ],
                    "min_evidence_refs": 1,
                },
                {
                    "link_id": "run",
                    "label": "Run checkpoint",
                    "required": True,
                    "why": "The action needs a run id that later bundles and timelines can join.",
                    "fields": [{"path": "summary.run_id", "ref_prefix": "run:"}],
                    "min_evidence_refs": 1,
                },
                {
                    "link_id": "work_item",
                    "label": "Completed work item",
                    "required": True,
                    "why": "The product wedge should prove a claimable unit of work reached closure.",
                    "expectations": [("work_item.status", "done")],
                    "fields": [
                        {"path": "work_item.work_id", "ref_prefix": "work_item:"},
                        {"path": "summary.ids.work_items", "ref_prefix": "work_item:"},
                    ],
                    "min_evidence_refs": 1,
                },
                {
                    "link_id": "human_work",
                    "label": "Bounded human work",
                    "required": True,
                    "why": "The action should demonstrate a bounded human review/receipt boundary.",
                    "fields": [
                        {"path": "summary.ids.human_work_sessions", "ref_prefix": "human_work:"}
                    ],
                    "min_evidence_refs": 1,
                },
                {
                    "link_id": "action_attestation",
                    "label": "Action attestation",
                    "required": True,
                    "why": "The machine-side action needs durable provenance.",
                    "fields": [
                        {
                            "path": "summary.ids.action_attestations",
                            "ref_prefix": "action_attestation:",
                        }
                    ],
                    "min_evidence_refs": 1,
                },
                {
                    "link_id": "outcome_link",
                    "label": "Outcome evidence",
                    "required": True,
                    "why": "The action should connect to measured outcome state, not just a log.",
                    "fields": [
                        {"path": "summary.ids.outcome_links", "ref_prefix": "outcome_link:"}
                    ],
                    "min_evidence_refs": 1,
                },
                {
                    "link_id": "governed_bundle",
                    "label": "Governed-run bundle",
                    "required": True,
                    "why": "The reviewer needs a portable bundle digest for audit.",
                    "fields": [
                        {"path": "summary.bundle_id", "ref_prefix": "governed_run_bundle:"},
                        {"path": "summary.bundle_digest"},
                    ],
                    "min_evidence_refs": 2,
                },
            ],
        },
        "learning_loop": {
            "profile": "learning_loop",
            "label": "Learning loop",
            "requirements": [
                {
                    "link_id": "future_replay",
                    "label": "Future replay observed",
                    "required": True,
                    "why": "Approved learning must reappear before matching future work.",
                    "expectations": [("ok", True), ("replayed_for_future_work", True)],
                    "min_evidence_refs": 0,
                },
                {
                    "link_id": "learning_event",
                    "label": "Approved learning event",
                    "required": True,
                    "why": "The loop needs an approved future-behavior unit.",
                    "fields": [{"path": "learning_event", "ref_prefix": "learning_event:"}],
                    "min_evidence_refs": 1,
                },
                {
                    "link_id": "context_packet",
                    "label": "Verified context packet",
                    "required": True,
                    "why": "The future-work context must be citeable and digest-checked.",
                    "fields": [
                        {"path": "context_packet", "ref_prefix": "context_packet:"},
                        {"path": "verified_context_packet", "ref_prefix": "context_packet:"},
                    ],
                    "min_evidence_refs": 1,
                },
                {
                    "link_id": "learning_use_receipt",
                    "label": "Learning-use receipt",
                    "required": True,
                    "why": "Later work should record whether the learning was applied, ignored, or deferred.",
                    "fields": [
                        {
                            "path": "learning_use_receipt",
                            "ref_prefix": "learning_event_encounter:",
                        }
                    ],
                    "min_evidence_refs": 1,
                },
                {
                    "link_id": "outcome_and_review",
                    "label": "Outcome/review follow-through",
                    "required": True,
                    "why": "The learning loop should carry outcome and routine-review follow-through.",
                    "fields": [
                        {"path": "learning_loop_outcome_links", "ref_prefix": "outcome_links:"},
                        {"path": "learning_loop_routine_reviews", "ref_prefix": "routine_reviews:"},
                    ],
                    "min_evidence_refs": 2,
                },
            ],
        },
    }
    if profile not in profiles:
        raise ValueError(f"unknown governed action composition profile: {profile}")
    return profiles[profile]


def _governed_action_composition_link(
    requirement: dict[str, Any],
    observed: dict[str, Any],
    supplied_refs: list[str],
) -> dict[str, Any]:
    errors: list[str] = []
    missing: list[str] = []
    result_summary: dict[str, Any] = {}
    evidence_refs = _matching_evidence_refs(
        supplied_refs,
        prefixes=list(requirement.get("evidence_prefixes") or []),
    )

    for field in requirement.get("fields") or []:
        path = str(field.get("path") or "")
        values = _deep_values(observed, path)
        if not values:
            missing.append(f"{path} is missing")
            continue
        result_summary[path] = values[0] if len(values) == 1 else values
        prefix = field.get("ref_prefix")
        evidence_refs.extend(_field_refs(values, ref_prefix=prefix))

    for field, expected in requirement.get("expectations") or []:
        actual = _deep_get(observed, field)
        result_summary[field] = actual
        if actual != expected:
            errors.append(f"{field} expected {expected!r}, observed {actual!r}")

    evidence_refs = _dedupe_refs(evidence_refs)
    min_refs = int(requirement.get("min_evidence_refs", 1))
    if len(evidence_refs) < min_refs:
        missing.append(
            f"expected at least {min_refs} evidence ref(s), observed {len(evidence_refs)}"
        )
    if errors:
        status = "failed"
    elif missing:
        status = "missing"
    else:
        status = "passed"
    return {
        "link_id": requirement["link_id"],
        "label": requirement["label"],
        "required": bool(requirement.get("required", True)),
        "status": status,
        "why": requirement.get("why"),
        "errors": errors,
        "missing": missing,
        "evidence_refs": evidence_refs,
        "result_summary": result_summary,
    }


def _governed_action_composition_review_questions(
    links: list[dict[str, Any]],
    *,
    profile_label: str,
) -> list[str]:
    blockers = [row for row in links if row["required"] and row["status"] != "passed"]
    questions = [
        f"Does the {profile_label} proof chain explain authority, action, evidence, outcome, and future learning without reading raw JSONL?",
        "Are missing links absent because the work did not happen, or because the adapter failed to carry refs?",
    ]
    if blockers:
        questions.append(
            "Which required composition blocker should be repaired before adoption review: "
            + ", ".join(row["link_id"] for row in blockers)
            + "?"
        )
    return questions


def _matching_evidence_refs(refs: list[str], *, prefixes: list[str]) -> list[str]:
    if not prefixes:
        return []
    return [
        ref
        for ref in refs
        if any(str(ref).startswith(prefix) for prefix in prefixes)
    ]


def _deep_values(payload: dict[str, Any], dotted_path: str) -> list[Any]:
    value = _deep_get(payload, dotted_path)
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "", [], {})]
    return [value]


def _field_refs(values: list[Any], *, ref_prefix: Any = None) -> list[str]:
    refs: list[str] = []
    for value in values:
        if isinstance(value, dict):
            continue
        text = str(value).strip()
        if not text:
            continue
        prefix = str(ref_prefix or "")
        if prefix and not text.startswith(prefix):
            refs.append(f"{prefix}{text}")
        else:
            refs.append(text)
    return refs


def _deep_get(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _dedupe_refs(refs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for ref in refs:
        cleaned = ref.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def _normalize_artifacts(artifacts: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        label = str(artifact.get("label") or "").strip()
        ref = str(artifact.get("ref") or "").strip()
        purpose = str(artifact.get("purpose") or "").strip()
        if not label or not ref:
            continue
        normalized.append({"label": label, "ref": ref, "purpose": purpose})
    return normalized


def _normalize_operator_burden(
    burden: dict[str, Any],
    *,
    bundles: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Build a read-only burden projection from existing run evidence."""

    payload = dict(burden or {})
    pressure_groups = [
        _compact_pressure_group(group)
        for group in (
            payload.get("human_work_pressure")
            or payload.get("pressure_groups")
            or []
        )
        if isinstance(group, dict)
    ]
    action_impact = dict(payload.get("action_impact_summary") or {})
    action_total = _int_or(
        action_impact.get("n_total"),
        len(action_impact.get("records") or []),
    )
    action_review_required = _int_or(
        action_impact.get("n_review_required"),
        len(action_impact.get("review_required") or []),
    )
    action_negative_externalities = _int_or(
        action_impact.get("n_local_with_negative_externalities"),
        len(action_impact.get("local_with_negative_externalities") or []),
    )
    action_review_rate = (
        round(action_review_required / action_total, 4)
        if action_total > 0
        else 0.0
    )
    bundle_counts: dict[str, int] = {}
    for bundle in bundles:
        for key, value in dict(bundle.get("counts") or {}).items():
            bundle_counts[key] = bundle_counts.get(key, 0) + _int_or(value, 0)

    missing_receipts = sum(
        _int_or(group.get("missing_receipt_count"), 0)
        for group in pressure_groups
    )
    stale_sessions = sum(
        _int_or(group.get("stale_count"), 0)
        for group in pressure_groups
    )
    bundle_human_work_sessions = bundle_counts.get("human_work_sessions", 0)
    bundle_accountability_cases = bundle_counts.get("accountability_cases", 0)
    bundle_approval_events = bundle_counts.get("approval_events", 0)
    estimated_human_touchpoints = (
        bundle_human_work_sessions
        + action_review_required
        + missing_receipts
        + bundle_accountability_cases
        + bundle_approval_events
    )
    burden_score = _operator_burden_score(
        pressure_groups=pressure_groups,
        missing_receipts=missing_receipts,
        stale_sessions=stale_sessions,
        action_review_required=action_review_required,
        action_review_rate=action_review_rate,
        bundle_human_work_sessions=bundle_human_work_sessions,
        bundle_accountability_cases=bundle_accountability_cases,
        review_candidates=_int_or(
            payload.get("review_candidates"),
            _int_or(summary.get("review_candidates"), 0),
        ),
    )
    review_questions = _clean_text_list(payload.get("review_questions"))
    if not review_questions:
        review_questions = [
            "Which human touchpoints were necessary for authority, safety, or relationship judgment?",
            "Which touchpoints were compensating for missing context, tooling, or receipts?",
            "Did review-required action-impact rows reduce enough risk to justify the human burden?",
        ]

    return {
        "schema": "operator_burden_projection.v1",
        "projection_only": True,
        "summary": {
            "burden_level": _operator_burden_level(burden_score),
            "burden_score": burden_score,
            "estimated_human_touchpoints": estimated_human_touchpoints,
            "pressure_groups": len(pressure_groups),
            "missing_receipts": missing_receipts,
            "stale_sessions": stale_sessions,
            "action_impact_total": action_total,
            "action_impact_review_required": action_review_required,
            "action_impact_review_rate": action_review_rate,
            "action_impact_negative_externalities": action_negative_externalities,
            "bundle_human_work_sessions": bundle_human_work_sessions,
            "bundle_accountability_cases": bundle_accountability_cases,
            "bundle_approval_events": bundle_approval_events,
        },
        "pressure_groups": pressure_groups,
        "review_questions": review_questions[:6],
        "boundary": {
            "does_not_assign_work": True,
            "does_not_schedule_work": True,
            "does_not_approve_policy": True,
            "does_not_optimize_routing": True,
        },
    }


def _operator_burden_pilot_row(row: dict[str, Any], *, index: int) -> dict[str, Any]:
    phase = str(row.get("phase") or row.get("period") or "").strip().lower()
    if phase in {"before", "pre", "pre_pilot", "control"}:
        phase = "baseline"
    if phase in {"after", "post", "post_pilot", "treatment"}:
        phase = "pilot"
    if phase not in {"baseline", "pilot"}:
        phase = "pilot"
    projection = dict(
        row.get("operator_burden_projection")
        or row.get("operator_burden")
        or {}
    )
    projection_summary = dict(projection.get("summary") or {})
    projected_touchpoints = _float_or_none(
        row.get("projected_human_touchpoints"),
        row.get("projected_operator_touchpoints"),
        projection_summary.get("estimated_human_touchpoints"),
    )
    actual_touchpoints = _float_or_none(
        row.get("actual_human_touchpoints"),
        row.get("human_touchpoints"),
        row.get("operator_touchpoints"),
        row.get("manual_touchpoints"),
    )
    coordination_minutes = _float_or_none(
        row.get("coordination_minutes"),
        row.get("human_coordination_minutes"),
        row.get("review_minutes"),
    )
    return {
        "row_index": index,
        "run_ref": str(row.get("run_ref") or row.get("run_id") or "").strip(),
        "phase": phase,
        "actual_human_touchpoints": actual_touchpoints,
        "projected_human_touchpoints": projected_touchpoints,
        "coordination_minutes": coordination_minutes,
        "rework_count": _int_or(row.get("rework_count"), 0),
        "missing_receipts": _int_or(row.get("missing_receipts"), 0),
        "stale_sessions": _int_or(row.get("stale_sessions"), 0),
        "review_required_count": _int_or(
            row.get("review_required_count"),
            _int_or(row.get("review_required"), 0),
        ),
        "hidden_burden_reported": _boolish(row.get("hidden_burden_reported")),
        "burden_shift_reported": _boolish(row.get("burden_shift_reported")),
    }


def _operator_burden_phase_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    actual_touchpoints = [
        row["actual_human_touchpoints"]
        for row in rows
        if row["actual_human_touchpoints"] is not None
    ]
    projected_touchpoints = [
        row["projected_human_touchpoints"]
        for row in rows
        if row["projected_human_touchpoints"] is not None
    ]
    coordination_minutes = [
        row["coordination_minutes"]
        for row in rows
        if row["coordination_minutes"] is not None
    ]
    return {
        "n_runs": len(rows),
        "runs_with_actual_touchpoints": len(actual_touchpoints),
        "mean_actual_human_touchpoints": _mean_or_none(actual_touchpoints),
        "mean_projected_human_touchpoints": _mean_or_none(projected_touchpoints),
        "mean_coordination_minutes": _mean_or_none(coordination_minutes),
        "total_rework_count": sum(row["rework_count"] for row in rows),
        "total_missing_receipts": sum(row["missing_receipts"] for row in rows),
        "total_stale_sessions": sum(row["stale_sessions"] for row in rows),
        "total_review_required": sum(row["review_required_count"] for row in rows),
        "hidden_burden_reports": sum(
            1 for row in rows if row["hidden_burden_reported"]
        ),
        "burden_shift_reports": sum(
            1 for row in rows if row["burden_shift_reported"]
        ),
        "missing_receipt_rate": _rate(
            sum(1 for row in rows if row["missing_receipts"] > 0),
            len(rows),
        ),
        "hidden_burden_rate": _rate(
            sum(1 for row in rows if row["hidden_burden_reported"]),
            len(rows),
        ),
    }


def _operator_burden_phase_deltas(
    baseline: dict[str, Any],
    pilot: dict[str, Any],
) -> dict[str, Any]:
    return {
        "mean_actual_human_touchpoints": _delta(
            baseline.get("mean_actual_human_touchpoints"),
            pilot.get("mean_actual_human_touchpoints"),
        ),
        "mean_coordination_minutes": _delta(
            baseline.get("mean_coordination_minutes"),
            pilot.get("mean_coordination_minutes"),
        ),
        "total_rework_count": pilot["total_rework_count"] - baseline["total_rework_count"],
        "total_missing_receipts": (
            pilot["total_missing_receipts"] - baseline["total_missing_receipts"]
        ),
        "hidden_burden_rate": _delta(
            baseline.get("hidden_burden_rate"),
            pilot.get("hidden_burden_rate"),
        ),
    }


def _operator_burden_projection_fit(
    pilot_rows: list[dict[str, Any]],
    *,
    tolerance: float,
) -> dict[str, Any]:
    comparable = [
        row
        for row in pilot_rows
        if row["actual_human_touchpoints"] is not None
        and row["projected_human_touchpoints"] is not None
    ]
    differences = [
        round(row["actual_human_touchpoints"] - row["projected_human_touchpoints"], 4)
        for row in comparable
    ]
    overrun_rows = [
        {
            "row_index": row["row_index"],
            "run_ref": row["run_ref"],
            "actual_human_touchpoints": row["actual_human_touchpoints"],
            "projected_human_touchpoints": row["projected_human_touchpoints"],
            "delta": round(
                row["actual_human_touchpoints"] - row["projected_human_touchpoints"],
                4,
            ),
        }
        for row in comparable
        if row["actual_human_touchpoints"] - row["projected_human_touchpoints"]
        > tolerance
    ]
    return {
        "rows_with_projection": len(comparable),
        "projection_tolerance": tolerance,
        "mean_actual_minus_projected": _mean_or_none(differences),
        "undercounted_rows": overrun_rows,
        "undercounted_rate": _rate(len(overrun_rows), len(comparable)),
    }


def _operator_burden_review_reasons(
    *,
    phases: dict[str, dict[str, Any]],
    deltas: dict[str, Any],
    projection_fit: dict[str, Any],
    enough_records: bool,
    min_baseline_runs: int,
    min_pilot_runs: int,
    max_touchpoint_increase_rate: float,
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    baseline = phases["baseline"]
    pilot = phases["pilot"]
    if baseline["n_runs"] < min_baseline_runs:
        reasons.append(
            {
                "reason": "missing_baseline_records",
                "observed": baseline["n_runs"],
                "required": min_baseline_runs,
            }
        )
    if pilot["n_runs"] < min_pilot_runs:
        reasons.append(
            {
                "reason": "missing_pilot_records",
                "observed": pilot["n_runs"],
                "required": min_pilot_runs,
            }
        )
    baseline_touchpoints = baseline.get("mean_actual_human_touchpoints")
    pilot_touchpoints = pilot.get("mean_actual_human_touchpoints")
    if (
        enough_records
        and baseline_touchpoints is not None
        and pilot_touchpoints is not None
        and baseline_touchpoints > 0
        and pilot_touchpoints
        > baseline_touchpoints * (1.0 + max_touchpoint_increase_rate)
    ):
        reasons.append(
            {
                "reason": "pilot_human_touchpoints_increased",
                "baseline_mean": baseline_touchpoints,
                "pilot_mean": pilot_touchpoints,
                "max_increase_rate": max_touchpoint_increase_rate,
            }
        )
    if enough_records and pilot["hidden_burden_reports"] > 0:
        reasons.append(
            {
                "reason": "hidden_burden_reported",
                "count": pilot["hidden_burden_reports"],
                "rate": pilot["hidden_burden_rate"],
            }
        )
    if enough_records and pilot["burden_shift_reports"] > 0:
        reasons.append(
            {
                "reason": "burden_shift_reported",
                "count": pilot["burden_shift_reports"],
            }
        )
    if enough_records and pilot["total_missing_receipts"] > 0:
        reasons.append(
            {
                "reason": "pilot_missing_receipts",
                "count": pilot["total_missing_receipts"],
            }
        )
    if enough_records and pilot["total_stale_sessions"] > 0:
        reasons.append(
            {
                "reason": "pilot_stale_sessions",
                "count": pilot["total_stale_sessions"],
            }
        )
    if enough_records and projection_fit["undercounted_rows"]:
        reasons.append(
            {
                "reason": "projection_undercounted_human_touchpoints",
                "count": len(projection_fit["undercounted_rows"]),
                "rate": projection_fit["undercounted_rate"],
            }
        )
    return reasons


def _compact_pressure_group(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_counterparty_role": str(
            group.get("agent_counterparty_role") or group.get("role") or ""
        ).strip(),
        "bottleneck_class": str(group.get("bottleneck_class") or "").strip(),
        "active_count": _int_or(group.get("active_count"), 0),
        "waiting_count": _int_or(group.get("waiting_count"), 0),
        "missing_receipt_count": _int_or(group.get("missing_receipt_count"), 0),
        "stale_count": _int_or(group.get("stale_count"), 0),
        "session_ids": _clean_text_list(group.get("session_ids"))[:20],
        "recommendation": str(group.get("recommendation") or "").strip(),
    }


def _operator_burden_score(
    *,
    pressure_groups: list[dict[str, Any]],
    missing_receipts: int,
    stale_sessions: int,
    action_review_required: int,
    action_review_rate: float,
    bundle_human_work_sessions: int,
    bundle_accountability_cases: int,
    review_candidates: int,
) -> int:
    score = 0
    if pressure_groups:
        score += 1
    if missing_receipts:
        score += 2
    if stale_sessions:
        score += 1
    if action_review_required and action_review_rate >= 0.25:
        score += 1
    if bundle_human_work_sessions >= 3:
        score += 1
    if bundle_accountability_cases:
        score += 1
    if review_candidates >= 3:
        score += 1
    return score


def _operator_burden_level(score: int) -> str:
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _normalize_commands(commands: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for command in commands:
        if not isinstance(command, dict):
            continue
        label = str(command.get("label") or "").strip()
        command_text = str(command.get("command") or "").strip()
        if not label or not command_text:
            continue
        normalized.append({"label": label, "command": command_text})
    return normalized


def _compact_bundle_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "bundle_id": bundle.get("bundle_id"),
        "run_id": bundle.get("run_id"),
        "verdict": bundle.get("verdict"),
        "counts": dict(bundle.get("counts") or {}),
        "authority_snapshot": dict(bundle.get("authority_snapshot") or {}),
        "bundle_digest": bundle.get("bundle_digest"),
    }


def _compact_mutation_proof(proof: dict[str, Any]) -> dict[str, Any]:
    return {
        "proof_kind": proof.get("proof_kind"),
        "step_id": proof.get("step_id"),
        "change_kind": proof.get("change_kind"),
        "target_ref": proof.get("target_ref"),
        "valid": proof.get("valid"),
        "proof_digest": proof.get("proof_digest"),
        "bundle_digest": proof.get("bundle_digest"),
        "bundle_verdict": proof.get("bundle_verdict"),
        "commit": proof.get("commit"),
        "evidence_carrier_refs": list(proof.get("evidence_carrier_refs") or []),
    }


def _compact_execution_signal(signal: dict[str, Any]) -> dict[str, Any]:
    signal_id = str(signal.get("signal_id") or "").strip()
    return _without_none(
        {
            "signal_id": signal_id or None,
            "signal_ref": f"capability_signal:{signal_id}" if signal_id else None,
            "signal_kind": signal.get("signal_kind"),
            "severity": signal.get("severity"),
            "status": signal.get("status"),
            "source_ref": signal.get("source_ref"),
            "owner_role": signal.get("owner_role"),
            "worker_ref": signal.get("worker_ref"),
            "run_id": signal.get("run_id"),
            "work_id": signal.get("work_id"),
            "recommended_route": signal.get("recommended_route"),
            "route_target_ref": signal.get("route_target_ref"),
            "counts_as_failure": signal.get("counts_as_failure"),
            "evidence_refs": list(signal.get("evidence_refs") or []),
        }
    )


def _compact_learning_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate_id = str(candidate.get("candidate_id") or "").strip()
    return _without_none(
        {
            "candidate_id": candidate_id or None,
            "candidate_ref": (
                f"learning_transition_candidate:{candidate_id}"
                if candidate_id
                else None
            ),
            "source_kind": candidate.get("source_kind"),
            "transition_kind": candidate.get("transition_kind"),
            "status": candidate.get("status"),
            "severity": candidate.get("severity"),
            "object_ref": candidate.get("object_ref"),
            "suggested_owner_role": candidate.get("suggested_owner_role"),
            "source_refs": list(candidate.get("source_refs") or []),
        }
    )


def _compact_learning_closure(row: dict[str, Any]) -> dict[str, Any]:
    learning_event_id = str(row.get("learning_event_id") or "").strip()
    outcome_link_id = str(row.get("outcome_link_id") or "").strip()
    routine_review_id = str(row.get("routine_review_id") or "").strip()
    learning_use_receipt_id = str(
        row.get("learning_use_receipt_id")
        or row.get("learning_encounter_id")
        or ""
    ).strip()
    evidence_refs = _dedupe_refs(
        [
            str(ref)
            for ref in row.get("evidence_refs") or []
            if str(ref or "").strip()
        ]
    )
    context_packet_refs = _dedupe_refs(
        [
            str(ref)
            for ref in row.get("context_packet_refs") or []
            if str(ref or "").strip()
        ]
    )
    return _without_none(
        {
            "step_id": row.get("step_id"),
            "title": row.get("title"),
            "learning_event_id": learning_event_id or None,
            "learning_event_ref": (
                f"learning_event:{learning_event_id}" if learning_event_id else None
            ),
            "learning_use_receipt_id": learning_use_receipt_id or None,
            "learning_use_receipt_ref": (
                f"learning_event_encounter:{learning_use_receipt_id}"
                if learning_use_receipt_id
                else None
            ),
            "changed_context_ref": row.get("changed_context_ref")
            or row.get("target_ref"),
            "future_work_context": row.get("future_work_context")
            or row.get("future_replay_intent"),
            "future_replay_source": row.get("future_replay_source")
            or row.get("future_replay_candidate_source"),
            "context_packet_refs": context_packet_refs or None,
            "outcome_link_id": outcome_link_id or None,
            "outcome_link_ref": (
                f"outcome_link:{outcome_link_id}" if outcome_link_id else None
            ),
            "outcome_review_status": row.get("outcome_review_status"),
            "outcome_recommended_action": row.get("outcome_recommended_action"),
            "routine_review_id": routine_review_id or None,
            "routine_review_ref": (
                f"routine_review:{routine_review_id}" if routine_review_id else None
            ),
            "routine_review_status": row.get("routine_review_status"),
            "evidence_refs": evidence_refs,
        }
    )


def _compact_phase_plan(plan: dict[str, Any]) -> dict[str, Any]:
    plan_id = str(plan.get("plan_id") or "").strip()
    return _without_none(
        {
            "plan_id": plan_id or None,
            "plan_ref": f"phase_execution_plan:{plan_id}" if plan_id else None,
            "objective": plan.get("objective"),
            "owner_role": plan.get("owner_role"),
            "status": plan.get("status"),
            "current_phase": plan.get("current_phase"),
            "remaining_budget_units": plan.get("remaining_budget_units"),
            "attempts": plan.get("attempts"),
            "run_id": plan.get("run_id"),
            "work_id": plan.get("work_id"),
        }
    )


def _float_or_none(*values: Any) -> float | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _rate(count: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(count / denominator, 4)


def _delta(baseline: Any, pilot: Any) -> float | None:
    if baseline is None or pilot is None:
        return None
    return round(float(pilot) - float(baseline), 4)


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _int_or(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _required(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _without_none(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _md(value: Any) -> str:
    text = str(value).replace("\n", " ").strip()
    return text.replace("|", "\\|")


def _bounded_run_stop_receipt(
    control_input: BoundedRunControlInput,
    *,
    remaining: int | None,
) -> dict[str, Any] | None:
    reason = control_input.termination_reason
    if reason == "stop_file" and control_input.stop_file_seen:
        return {
            "receipt_kind": "bounded_run_stop_receipt",
            "source": "stop_file",
            "stop_file": str(control_input.stop_file) if control_input.stop_file else None,
            "observed_at_tick_boundary": control_input.steps_run,
            "termination_reason": reason,
        }
    if reason == "budget_exhausted":
        return {
            "receipt_kind": "bounded_run_stop_receipt",
            "source": "budget",
            "budget_units_total": control_input.budget_units_total,
            "budget_units_consumed": control_input.budget_units_consumed,
            "budget_units_remaining": remaining,
            "observed_at_tick_boundary": control_input.steps_run,
            "termination_reason": reason,
        }
    return None
