"""Thin composition helpers for governed run recipes.

This module does not create authority, approve work, or write kernel state. It
only normalizes client-side request bodies and inspection artifacts for flows
that already use first-party kernel primitives and service routes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


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
    summary = dict(summary_input.summary)
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
    return {
        "schema": "governed_run_operator_summary.v1",
        "run_label": _required(summary_input.run_label, "run_label"),
        "run_ref": _required(summary_input.run_ref, "run_ref"),
        "summary": summary,
        "operator_controls": dict(summary_input.operator_controls or {}),
        "status": {
            "verdict": summary.get("verdict"),
            "termination_reason": summary.get("termination_reason"),
            "bundle_count": len(bundles),
            "mutation_proof_count": len(proofs),
            "invalid_mutation_proofs": len(invalid_proofs),
            "open_execution_signals": len(open_signals),
            "blocking_execution_signals": len(blocking_signals),
            "blocked_phase_plans": len(blocked_phase_plans),
            "review_candidates": len(review_candidates),
        },
        "artifacts": artifacts,
        "commands": commands,
        "inspection_order": list(summary_input.inspection_order or []),
        "bundle_summaries": bundles,
        "mutation_proofs": proofs,
        "execution_signals": execution_signals,
        "learning_candidates": learning_candidates,
        "phase_plans": phase_plans,
        "metadata": dict(summary_input.metadata or {}),
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
