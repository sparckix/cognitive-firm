"""Small local HTTP boundary over cognitive-firm kernel commands.

This module is intentionally stdlib-only. It is a deployment adapter over the
Python kernel functions, not a second implementation of the primitives.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from cognitive_firm.identity_providers import (
    AuthenticatedSubject,
    IdentityProviderAdapter,
    StaticBearerTokenIdentityProvider,
)
from cognitive_firm.common.paths import ORG_ROOT_DIR, REPO_ROOT, WORKSPACE_DIR
from cognitive_firm.orchestration.accountability import build_accountability_summary
from cognitive_firm.orchestration.accountability_cases import (
    DEFAULT_ACCOUNTABILITY_CASES_LOG,
    build_damage_signal_accountability_case_request,
    create_accountability_case,
    update_accountability_case_status,
)
from cognitive_firm.orchestration.action_impact import (
    DEFAULT_ACTION_IMPACT_SUMMARY,
    DEFAULT_POLICY_EVALUATIONS_LOG,
    DEFAULT_POLICY_PROMOTION_PACKETS_LOG,
    append_policy_evaluation,
    append_policy_promotion_packet,
    build_policy_promotion_governance_change_request,
    build_policy_promotion_packet,
    evaluate_offline_policy_candidate,
    get_policy_evaluation,
    get_policy_promotion_packet,
    list_policy_evaluations,
    list_policy_promotion_packets,
    summary_from_optional_path,
)
from cognitive_firm.orchestration.action_attestation import (
    DEFAULT_ACTION_ATTESTATION_LOG,
    action_attestation_resource,
    create_action_attestation,
    list_agent_invocation_audits,
    list_action_attestations,
)
from cognitive_firm.orchestration.actor_identity import (
    DEFAULT_ACTOR_IDENTITY_LOG,
    ActorContext,
    actor_context_from_payload,
    get_actor_identity,
    register_actor_identity,
)
from cognitive_firm.orchestration.actor_membership import (
    DEFAULT_ACTOR_MEMBERSHIP_LOG,
    grant_actor_membership,
    revoke_actor_membership,
)
from cognitive_firm.orchestration.app_intents import (
    issue_control,
    issue_directive,
    resolve_gate,
    send_chat_message,
    update_role_agent_utilization,
)
from cognitive_firm.orchestration.agent_channels import (
    send_agent_message,
    update_agent_message_status,
    update_obligation_state,
)
from cognitive_firm.orchestration.capability_signals import (
    DEFAULT_CAPABILITY_SIGNALS_LOG,
    capability_signal_resource,
    close_capability_signal,
    learning_candidate_from_capability_signal,
    list_capability_signals,
    record_capability_signal,
    route_capability_signal,
    summarize_capability_signals,
)
from cognitive_firm.orchestration.evidence_gaps import DEFAULT_EVIDENCE_GAPS_LOG
from cognitive_firm.orchestration.forecast_market import DEFAULT_FORECAST_MARKET_ROOT
from cognitive_firm.orchestration.formal_verification import (
    DEFAULT_FORMAL_VERIFICATION_LOG,
    create_formal_verification_from_provider_payload,
    list_formal_verifications,
)
from cognitive_firm.orchestration.governed_run_recipes import (
    ExecutionEvidenceRouteInput,
    PredictedMutationOutcomeInput,
    PredictedMutationReversalReviewInput,
    build_execution_evidence_route_packet,
    build_predicted_mutation_outcome_link_request,
    build_predicted_mutation_reversal_review_request,
)
from cognitive_firm.orchestration.human_work import (
    DEFAULT_HUMAN_WORK_LOG,
    append_human_work_interaction,
    create_agent_requested_human_work_session,
    create_human_work_session,
    update_human_work_state,
)
from cognitive_firm.orchestration.leases import DEFAULT_LEASES_LOG, acquire_lease, release_lease, verify_lease
from cognitive_firm.orchestration.learning_events import (
    DEFAULT_LEARNING_ENCOUNTERS_LOG,
    DEFAULT_LEARNING_EVENTS_LOG,
    create_learning_event,
    learning_event_resource,
    list_learning_events,
    record_learning_event_encounter,
    replay_learning_events,
    summarize_learning_events,
)
from cognitive_firm.orchestration.learning_transition_compiler import (
    compile_learning_transitions,
)
from cognitive_firm.orchestration.multi_agent_trace_attribution import (
    DEFAULT_ATTRIBUTION_PACKETS_LOG,
    DEFAULT_TRACE_EVENTS_LOG,
    attribution_packet_resource,
    build_delegation_graph,
    create_failure_attribution_packet,
    delegation_graph_resource,
    list_failure_attribution_packets,
    list_trace_events,
    learning_candidate_from_attribution_packet,
    record_trace_event,
    trace_event_resource,
)
from cognitive_firm.orchestration.operating_units import (
    DEFAULT_OPERATING_UNITS_LOG,
    define_operating_unit,
    get_operating_unit,
    list_operating_units,
    operating_unit_resource,
)
from cognitive_firm.orchestration.operating_unit_surface import build_operating_unit_dashboard
from cognitive_firm.orchestration.outcome_links import (
    DEFAULT_OUTCOME_LINKS_LOG,
    create_outcome_link,
    get_outcome_link,
    list_outcome_links,
    outcome_link_resource,
    record_metric_snapshot,
    record_verdict,
    summarize_outcome_links,
    void_outcome_link,
)
from cognitive_firm.orchestration.phase_execution import (
    DEFAULT_PHASE_EXECUTION_LOG,
    learning_candidate_from_phase_execution_plan,
    list_phase_execution_plans,
    phase_execution_plan_resource,
    record_phase_directive,
    record_verification_feedback,
    start_phase_execution_plan,
)
from cognitive_firm.orchestration.policy_decisions import (
    DEFAULT_POLICY_DECISIONS_LOG,
    PolicyDecisionRequest,
    evaluate_policy,
    list_policy_decisions,
    policy_decision_resource,
)
from cognitive_firm.orchestration.protocol_experiments import (
    DEFAULT_PROTOCOL_EXPERIMENTS_LOG,
    build_protocol_experiment_report,
    learning_candidate_from_protocol_experiment_report,
    list_protocol_experiments,
    protocol_experiment_resource,
    record_protocol_observation,
    start_protocol_experiment,
)
from cognitive_firm.orchestration.routine_reviews import (
    DEFAULT_ROUTINE_REVIEWS_LOG,
    list_due_reviews,
    list_routine_reviews,
    record_review_outcome,
    retire_routine,
    routine_review_resource,
    schedule_routine_review,
    start_routine_review,
    summarize_routine_reviews,
)
from cognitive_firm.orchestration.run_checkpoints import (
    append_checkpoint,
    get_run,
    list_runs,
    resume_summary,
    set_run_state,
    start_run,
)
from cognitive_firm.orchestration.resource_allocation import (
    DEFAULT_RESOURCE_ALLOCATION_LOG,
    allocation_summary,
    apply_allocation_decision,
    current_allocation,
    list_allocation_decisions,
    record_allocation_decision,
    revert_allocation_decision,
)
from cognitive_firm.orchestration.decision_rights import (
    DEFAULT_RESIDUAL_DECISIONS_LOG,
    DEFAULT_RESIDUAL_RIGHTS_LOG,
    assign_residual_right,
    get_residual_right_holder,
    record_residual_decision,
    review_residual_decision,
    summarize_decision_rights,
)
from cognitive_firm.orchestration.decision_aggregation import (
    DEFAULT_DECISION_AGGREGATION_LOG,
    compute_decision_aggregation_case,
    decision_aggregation_case_resource,
    get_decision_aggregation_case,
    list_decision_aggregation_cases,
    list_decision_procedure_profiles,
    open_decision_aggregation_case,
    open_decision_aggregation_case_from_profile,
    record_decision_position,
)
from cognitive_firm.orchestration.state_backends import SqliteMutationBackend, TransactionalMutationBackend
from cognitive_firm.orchestration.org_surface import build_org_surface
from cognitive_firm.orchestration.work_items import (
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_WORK_ITEMS_LOG,
    claim_next_work_item,
    claim_work_item,
    complete_work_item,
    enqueue_work_item,
    fail_work_item,
    get_work_item,
    heartbeat_work_item,
    list_work_items,
    requeue_dead_letter,
    retire_work_item,
    start_work_item,
    work_item_resource,
)
from cognitive_firm.orchestration.work_discovery import build_role_learning_context


@dataclass(frozen=True)
class KernelServiceConfig:
    """Path config for the local service adapter.

    The default paths match the filesystem kernel. Tests and tenant overlays can
    provide temporary paths without changing primitive implementations.
    """

    human_work_log: Path = DEFAULT_HUMAN_WORK_LOG
    accountability_cases_log: Path = DEFAULT_ACCOUNTABILITY_CASES_LOG
    actor_identity_log: Path = DEFAULT_ACTOR_IDENTITY_LOG
    actor_membership_log: Path = DEFAULT_ACTOR_MEMBERSHIP_LOG
    leases_log: Path = DEFAULT_LEASES_LOG
    evidence_gaps_log: Path = DEFAULT_EVIDENCE_GAPS_LOG
    forecast_market_summary: Path = DEFAULT_FORECAST_MARKET_ROOT / "global_health.json"
    action_impact_summary: Path = DEFAULT_ACTION_IMPACT_SUMMARY
    policy_evaluations_log: Path = DEFAULT_POLICY_EVALUATIONS_LOG
    policy_promotion_packets_log: Path = DEFAULT_POLICY_PROMOTION_PACKETS_LOG
    policy_decisions_log: Path = DEFAULT_POLICY_DECISIONS_LOG
    work_items_log: Path = DEFAULT_WORK_ITEMS_LOG
    operating_units_log: Path = DEFAULT_OPERATING_UNITS_LOG
    outcome_links_log: Path = DEFAULT_OUTCOME_LINKS_LOG
    routine_reviews_log: Path = DEFAULT_ROUTINE_REVIEWS_LOG
    learning_events_log: Path = DEFAULT_LEARNING_EVENTS_LOG
    learning_encounters_log: Path = DEFAULT_LEARNING_ENCOUNTERS_LOG
    action_attestation_log: Path = DEFAULT_ACTION_ATTESTATION_LOG
    formal_verification_log: Path = DEFAULT_FORMAL_VERIFICATION_LOG
    trace_events_log: Path = DEFAULT_TRACE_EVENTS_LOG
    attribution_packets_log: Path = DEFAULT_ATTRIBUTION_PACKETS_LOG
    phase_execution_log: Path = DEFAULT_PHASE_EXECUTION_LOG
    protocol_experiments_log: Path = DEFAULT_PROTOCOL_EXPERIMENTS_LOG
    capability_signals_log: Path = DEFAULT_CAPABILITY_SIGNALS_LOG
    resource_allocation_log: Path = DEFAULT_RESOURCE_ALLOCATION_LOG
    residual_rights_log: Path = DEFAULT_RESIDUAL_RIGHTS_LOG
    residual_decisions_log: Path = DEFAULT_RESIDUAL_DECISIONS_LOG
    decision_aggregation_log: Path = DEFAULT_DECISION_AGGREGATION_LOG
    project_root: Path = REPO_ROOT
    kernel_events_log: Path | None = None
    org_dir: Path = Path(os.environ.get("ORG_ROOT") or ORG_ROOT_DIR)
    gates_dir: Path = Path(os.environ.get("GATES_DIR") or WORKSPACE_DIR / "gates" / "pending")
    gates_resolved_dir: Path = Path(
        os.environ.get("GATES_RESOLVED_DIR") or WORKSPACE_DIR / "gates" / "resolved"
    )
    transition_log: Path = Path(os.environ.get("TRANSITIONS_LOG") or WORKSPACE_DIR / "transitions.jsonl")
    enforce_registered_actors: bool = False
    enforce_actor_membership: bool = False
    enforce_subject_scope: bool = False
    require_leases: bool = False
    a2a_max_thread_messages: int = 25
    a2a_max_parent_depth: int = 8
    identity_admin_roles: tuple[str, ...] = ("role.identity_admin", "role.owner", "role.principal")
    identity_provider: IdentityProviderAdapter | None = None
    mutation_backend: TransactionalMutationBackend | None = None
    # Per-surface write policy (L3 / O-Q4). Maps an ActorContext.surface tag to
    # "projection_only" or "read_write". A surface absent here may write —
    # the kernel denies only what a deployment explicitly restricts.
    surface_write_modes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KernelServiceResponse:
    status: int
    payload: dict[str, Any]


def _vocabulary_payload() -> dict[str, Any]:
    """The L4 userland vocabulary, served so every surface speaks one dialect."""
    from cognitive_firm.userland import vocabulary

    return {
        "schema_version": vocabulary.schema_version(),
        "terms": [term.as_dict() for term in vocabulary.all_terms()],
    }


def _governance_changes_log(config: KernelServiceConfig) -> Path:
    """The firm's governance-change proposal log, anchored to its org dir."""
    return config.org_dir / "governance_changes" / "governance_changes.jsonl"


def _configured_org_surface(config: KernelServiceConfig):
    """Build the service projection from the service's configured logs."""
    return build_org_surface(
        project_root=config.project_root,
        evidence_gaps_log=config.evidence_gaps_log,
        human_work_log=config.human_work_log,
        forecast_market_summary=config.forecast_market_summary,
        action_impact_summary=config.action_impact_summary,
        governance_changes_log=_governance_changes_log(config),
        accountability_cases_log=config.accountability_cases_log,
        learning_events_log=config.learning_events_log,
        learning_encounters_log=config.learning_encounters_log,
        outcome_links_log=config.outcome_links_log,
        routine_reviews_log=config.routine_reviews_log,
        transitions_log=config.transition_log,
    )


def _learning_transition_candidates_payload(
    config: KernelServiceConfig,
    *,
    source: str = "all",
    include_closed: bool = False,
) -> dict[str, Any]:
    """Build the service read model for reviewable learning candidates."""
    valid_sources = {
        "all",
        "org_surface",
        "execution",
        "attribution",
        "capability",
        "phase_execution",
        "protocol_experiment",
    }
    if source not in valid_sources:
        raise ValueError(f"source must be one of: {', '.join(sorted(valid_sources))}")

    candidates: list[dict[str, Any]] = []
    source_counts = {
        "org_surface": 0,
        "attribution": 0,
        "capability": 0,
        "phase_execution": 0,
        "protocol_experiment": 0,
    }
    if source in {"all", "org_surface"}:
        plan = compile_learning_transitions(_configured_org_surface(config))
        rows = [candidate.as_dict() for candidate in plan.candidates]
        candidates.extend(rows)
        source_counts["org_surface"] = len(rows)

    if source in {"all", "execution", "attribution"}:
        packets = list_failure_attribution_packets(
            status="review_ready",
            log_path=config.attribution_packets_log,
        )
        rows = [
            learning_candidate_from_attribution_packet(packet).as_dict()
            for packet in packets
        ]
        candidates.extend(rows)
        source_counts["attribution"] = len(rows)

    if source in {"all", "execution", "capability"}:
        signals = list_capability_signals(log_path=config.capability_signals_log)
        if not include_closed:
            signals = [signal for signal in signals if signal.status != "closed"]
        rows = [
            learning_candidate_from_capability_signal(signal).as_dict()
            for signal in signals
        ]
        candidates.extend(rows)
        source_counts["capability"] = len(rows)

    if source in {"all", "execution", "phase_execution"}:
        phase_plans = [
            plan
            for plan in list_phase_execution_plans(log_path=config.phase_execution_log)
            if plan.status in {"blocked", "failed"}
        ]
        rows = [
            learning_candidate_from_phase_execution_plan(plan).as_dict()
            for plan in phase_plans
        ]
        candidates.extend(rows)
        source_counts["phase_execution"] = len(rows)

    if source in {"all", "execution", "protocol_experiment"}:
        rows = []
        for experiment in list_protocol_experiments(log_path=config.protocol_experiments_log):
            for report in experiment.reports:
                if report.get("status") != "review_ready":
                    continue
                rows.append(
                    learning_candidate_from_protocol_experiment_report(
                        experiment,
                        report,
                    ).as_dict()
                )
        candidates.extend(rows)
        source_counts["protocol_experiment"] = len(rows)

    deduped: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        deduped.setdefault(str(candidate.get("candidate_id")), candidate)
    ordered = sorted(
        deduped.values(),
        key=lambda candidate: (
            {"blocking": 0, "warning": 1, "info": 2}.get(
                str(candidate.get("severity") or ""), 3
            ),
            str(candidate.get("transition_kind") or ""),
            str(candidate.get("candidate_id") or ""),
        ),
    )
    return {
        "source": source,
        "include_closed": include_closed,
        "n_candidates": len(ordered),
        "source_counts": source_counts,
        "candidates": ordered,
    }


def _find_learning_transition_candidate(
    config: KernelServiceConfig,
    *,
    candidate_id: str,
    source: str = "all",
    include_closed: bool = False,
) -> dict[str, Any] | None:
    payload = _learning_transition_candidates_payload(
        config,
        source=source,
        include_closed=include_closed,
    )
    for candidate in payload["candidates"]:
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    return None


def _decided_governance_ids(config: KernelServiceConfig) -> set[str]:
    """Proposal ids that already carry an attested approve/decline event.

    ``governance_changes`` has no status-transition function — a decided
    proposal keeps ``status: review_ready`` in its log. The durable decision
    is the kernel event; this reads those events so a decided proposal stops
    nagging in the attention feed and cannot be decided twice.
    """
    from cognitive_firm.orchestration.kernel_events import list_kernel_events

    decided: set[str] = set()
    for verb in ("governance_change.approved", "governance_change.declined"):
        for event in list_kernel_events(
            verb=verb, log_path=config.transition_log
        ):
            if event.object_ref.startswith("governance_change:"):
                decided.add(event.object_ref.split(":", 1)[1])
    return decided


def _approved_governance_ids(config: KernelServiceConfig) -> set[str]:
    """Proposal ids with an explicit approval event."""
    from cognitive_firm.orchestration.kernel_events import list_kernel_events

    approved: set[str] = set()
    for event in list_kernel_events(
        verb="governance_change.approved", log_path=config.transition_log
    ):
        if event.object_ref.startswith("governance_change:"):
            approved.add(event.object_ref.split(":", 1)[1])
    return approved


def _attention_feed(config: KernelServiceConfig) -> list[dict[str, Any]]:
    """Gather the firm's pending signals and route them to participants (L1).

    Pending gates, A2H work requests, and governance-change proposals awaiting
    an accountable actor decision are normalized, then the userland attention router
    classifies each and resolves its target participant.
    """
    from cognitive_firm.orchestration.authority_domains import (
        resolve_authority_assignment_from_org,
    )
    from cognitive_firm.orchestration.governance_changes import (
        list_governance_changes,
    )
    from cognitive_firm.orchestration.human_work import (
        list_a2h_waiting_on_human_sessions,
    )
    from cognitive_firm.userland.attention_router import (
        AttentionSignal,
        pending_gate_signals,
        route_signals,
    )

    signals = list(pending_gate_signals(config.gates_dir))
    decided = _decided_governance_ids(config)
    for proposal in list_governance_changes(
        status="review_ready", log_path=_governance_changes_log(config)
    ):
        if proposal.proposal_id in decided:
            continue  # already approved/declined — stop nagging the operator
        # Governance signals leave the target empty — the router fills it with
        # the authority. This closes the governed-install review loop: an
        # overlay's authority-diff proposal surfaces in an accountable actor's queue.
        signals.append(
            AttentionSignal(
                signal_id=proposal.proposal_id,
                kind="governance_change",
                headline=f"Governance change awaiting review: {proposal.title}",
                source_ref=proposal.proposal_id,
                created_at_utc=proposal.created_at_utc,
                tenant_id=proposal.tenant_id,
                project_id=proposal.project_id,
                decision_class=proposal.change_kind,
            )
        )
    for session in list_a2h_waiting_on_human_sessions(
        log_path=config.human_work_log
    ):
        signals.append(
            AttentionSignal(
                signal_id=session.session_id,
                kind="a2h_waiting",
                headline=f"Work request: {session.objective}",
                source_ref=session.session_id,
                created_at_utc=session.created_at_utc,
                target_role_id=session.agent_counterparty_role,
                target_actor_id=session.human_actor,
            )
        )

    def _authority_for_signal(signal: AttentionSignal) -> tuple[str | None, str | None]:
        resolution = resolve_authority_assignment_from_org(
            config.org_dir,
            tenant_id=signal.tenant_id,
            project_id=signal.project_id,
            operating_unit_id=signal.operating_unit_id,
            resource_class=signal.resource_class,
            decision_class=signal.decision_class,
            actor_membership_log=config.actor_membership_log,
        )
        if not resolution.authority_role_id:
            return None, None
        authority_actor = resolution.actor_ids[0] if resolution.actor_ids else None
        return resolution.authority_role_id, authority_actor

    routed = route_signals(
        signals,
        authority_resolver=_authority_for_signal,
    )
    return [signal.as_dict() for signal in routed]


def _query_bool(query: dict[str, list[str]], key: str) -> bool:
    return (query.get(key, ["false"])[0] or "").lower() in {"1", "true", "yes"}


def _query_optional_int(
    query: dict[str, list[str]],
    key: str,
    *,
    default: int | None = None,
) -> int | None:
    raw = query.get(key, [None])[0]
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{key} must be non-negative")
    return value


READ_ONLY_POST_ROUTES = {
    "/kernel/governed-run-bundles/build",
    "/kernel/governed-run-bundles/validate",
    "/kernel/mutation-proofs/build",
    "/kernel/mutation-proofs/validate",
}


def _is_mutating_request(method: str, route: str) -> bool:
    if method == "GET":
        return False
    return not (method == "POST" and route in READ_ONLY_POST_ROUTES)


def dispatch_kernel_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    config: KernelServiceConfig | None = None,
    headers: dict[str, str] | None = None,
) -> KernelServiceResponse:
    """Dispatch one local API request to kernel primitives."""
    config = config or KernelServiceConfig()
    body = body or {}
    parsed_path = urlparse(path)
    route = parsed_path.path.rstrip("/") or "/"
    parts = [part for part in route.split("/") if part]
    query = parse_qs(parsed_path.query)

    try:
        subject = _authenticate(headers or {}, config=config)
        actor = _actor_context(body, config=config, subject=subject)
        # Surface-write gating is keyed on whether the request mutates, not on
        # the literal verb. Some read-only validation/projection routes use
        # POST because their request bodies are structured artifacts.
        if _is_mutating_request(method, route):
            from cognitive_firm.userland.surface_policy import (
                surface_write_allowed,
            )

            _surface_decision = surface_write_allowed(
                surface=actor.surface,
                is_mutation=True,
                modes=config.surface_write_modes,
            )
            if not _surface_decision.allowed:
                return _error(403, _surface_decision.reason)
        if method == "GET" and route == "/health":
            return _ok({"ok": True, "service": "cognitive-firm-kernel"})

        if method == "GET" and route == "/kernel/org-surface":
            surface = _configured_org_surface(config)
            return _ok({"surface": surface.as_dict()})

        if method == "GET" and route == "/kernel/accountability-summary":
            surface = _configured_org_surface(config)
            summary = build_accountability_summary(surface)
            return _ok({"summary": summary.as_dict()})

        if method == "GET" and route == "/kernel/vocabulary":
            return _ok(_vocabulary_payload())

        if method == "GET" and route == "/kernel/governance-changes":
            from cognitive_firm.orchestration.governance_changes import (
                governance_change_resource,
                list_governance_changes,
            )

            status_filter = query.get("status", [None])[0]
            change_kind_filter = query.get("change_kind", [None])[0]
            tenant_filter = query.get("tenant_id", [None])[0]
            project_filter = query.get("project_id", [None])[0]
            proposals = list_governance_changes(
                status=status_filter,
                change_kind=change_kind_filter,
                tenant_id=tenant_filter,
                project_id=project_filter,
                log_path=_governance_changes_log(config),
            )
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "proposals": [
                            governance_change_resource(proposal).as_dict()
                            for proposal in proposals
                        ]
                    }
                )
            decided = _decided_governance_ids(config)
            payload = []
            for proposal in proposals:
                row = proposal.as_dict()
                row["decided"] = proposal.proposal_id in decided
                payload.append(row)
            return _ok({"proposals": payload})

        if (
            method == "GET"
            and len(parts) == 3
            and parts[:2] == ["kernel", "governance-changes"]
        ):
            from cognitive_firm.orchestration.governance_changes import (
                governance_change_resource,
                list_governance_changes,
            )

            proposal_id = parts[2]
            proposals = {
                proposal.proposal_id: proposal
                for proposal in list_governance_changes(
                    log_path=_governance_changes_log(config)
                )
            }
            proposal = proposals.get(proposal_id)
            if proposal is None:
                return _error(404, f"no governance change {proposal_id!r}")
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "proposal": governance_change_resource(
                            proposal
                        ).as_dict()
                    }
                )
            row = proposal.as_dict()
            row["decided"] = proposal_id in _decided_governance_ids(config)
            return _ok({"proposal": row})

        if method == "POST" and route == "/kernel/governance-changes":
            from cognitive_firm.orchestration.governance_changes import (
                propose_governance_change,
            )

            _verify_mutation_lease(
                "governance_changes:propose", body, actor=actor, config=config
            )
            proposal = propose_governance_change(
                change_kind=_required_str(body, "change_kind"),
                title=_required_str(body, "title"),
                proposed_by=(
                    actor.actor_id
                    if subject is not None
                    else str(body.get("proposed_by") or actor.actor_id)
                ),
                target_ref=_required_str(body, "target_ref"),
                rationale=_required_str(body, "rationale"),
                source_refs=_list_str(body.get("source_refs")),
                expected_behavior_change=_optional_str(
                    body, "expected_behavior_change"
                ),
                predicted_effect=(
                    dict(body.get("predicted_effect"))
                    if isinstance(body.get("predicted_effect"), dict)
                    else None
                ),
                risk_summary=_optional_str(body, "risk_summary"),
                rollback_plan=_optional_str(body, "rollback_plan"),
                owner_role=_optional_str(body, "owner_role"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                invariant_checks=_governance_invariant_checks_from_body(body),
                metadata=dict(body.get("metadata") or {}),
                proposal_id=_optional_str(body, "proposal_id"),
                log_path=_governance_changes_log(config),
            )
            return _ok({"proposal": proposal.as_dict()}, status=201)

        if (
            method == "GET"
            and len(parts) == 3
            and parts[:2] == ["kernel", "attention"]
        ):
            actor_id = parts[2]
            routed = _attention_feed(config)
            mine = [s for s in routed if s.get("target_actor_id") == actor_id]
            return _ok({"actor_id": actor_id, "signals": mine})

        if (
            method == "GET"
            and len(parts) == 3
            and parts[:2] == ["kernel", "work-inbox"]
        ):
            from cognitive_firm.userland.work_inbox import list_inbox

            actor_id = parts[2]
            items = list_inbox(
                actor_id=actor_id, log_path=config.human_work_log
            )
            return _ok(
                {
                    "actor_id": actor_id,
                    "items": [item.as_dict() for item in items],
                }
            )

        if method == "POST" and route == "/kernel/human-work":
            _verify_mutation_lease("human_work:create", body, actor=actor, config=config)
            return _ok(
                {
                    "session": asdict(
                        _create_human_work_from_payload(body, config=config)
                    )
                },
                status=201,
            )

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "human-work"]
            and parts[3] == "state"
        ):
            _verify_mutation_lease(f"human_work:{parts[2]}", body, actor=actor, config=config)
            session = update_human_work_state(
                parts[2],
                _required_str(body, "state"),
                completion_summary=_optional_str(body, "completion_summary"),
                integration_ref=_optional_str(body, "integration_ref"),
                receipt=_optional_str(body, "receipt"),
                confidence=_optional_str(body, "confidence"),
                agent_followup_required=body.get("agent_followup_required"),
                agent_followup_ref=_optional_str(body, "agent_followup_ref"),
                log_path=config.human_work_log,
            )
            return _ok({"session": asdict(session)})

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "human-work"]
            and parts[3] == "interaction"
        ):
            _verify_mutation_lease(f"human_work:{parts[2]}", body, actor=actor, config=config)
            session = append_human_work_interaction(
                parts[2],
                actor=_required_str(body, "actor"),
                event_type=_required_str(body, "event_type"),
                summary=_required_str(body, "summary"),
                surface=str(body.get("surface") or "mixed"),
                artifact_refs=_list_str(body.get("artifact_refs")),
                blocker=_optional_str(body, "blocker"),
                agent_followup_required=body.get("agent_followup_required"),
                log_path=config.human_work_log,
            )
            return _ok({"session": asdict(session)})

        if method == "POST" and route == "/kernel/accountability-cases/from-damage-signal":
            _verify_mutation_lease("accountability_cases:create_from_damage_signal", body, actor=actor, config=config)
            signal = body.get("signal")
            if not isinstance(signal, dict):
                raise ValueError("signal must be an object")
            request = build_damage_signal_accountability_case_request(
                signal,
                accountable_role=_required_str(body, "accountable_role"),
                authority_envelope_ref=_required_str(body, "authority_envelope_ref"),
                responsible_actor=_optional_str(body, "responsible_actor"),
                decision_right_basis=str(body.get("decision_right_basis") or "tenant_rule"),
                recourse_path=_optional_str(body, "recourse_path"),
                risk_tier=_optional_str(body, "risk_tier"),
                review_sla=_optional_str(body, "review_sla"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                due_at_utc=_optional_str(body, "due_at_utc"),
                operator_burden=_optional_str(body, "operator_burden"),
                case_id=_optional_str(body, "case_id"),
                trigger_ref=_optional_str(body, "trigger_ref"),
                metadata=dict(body.get("metadata") or {}),
            )
            case = create_accountability_case(
                **request,
                log_path=config.accountability_cases_log,
            )
            return _ok({"case": asdict(case), "request": request}, status=201)

        if method == "POST" and route == "/kernel/accountability-cases":
            _verify_mutation_lease("accountability_cases:create", body, actor=actor, config=config)
            case = create_accountability_case(
                trigger_ref=_required_str(body, "trigger_ref"),
                accountable_role=_required_str(body, "accountable_role"),
                responsible_actor=_required_str(body, "responsible_actor"),
                decision_right_basis=_required_str(body, "decision_right_basis"),
                authority_envelope_ref=_required_str(body, "authority_envelope_ref"),
                risk_tier=_required_str(body, "risk_tier"),
                recourse_path=_required_str(body, "recourse_path"),
                residual_risk_accepted_by=_optional_str(body, "residual_risk_accepted_by"),
                review_sla=_optional_str(body, "review_sla"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                due_at_utc=_optional_str(body, "due_at_utc"),
                externality_tags=_list_str(body.get("externality_tags")),
                operator_burden=str(body.get("operator_burden") or "medium"),
                rationale=str(body.get("rationale") or ""),
                metadata=dict(body.get("metadata") or {}),
                case_id=_optional_str(body, "case_id"),
                log_path=config.accountability_cases_log,
            )
            return _ok({"case": asdict(case)}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "accountability-cases"]
            and parts[3] == "status"
        ):
            case_id = parts[2]
            _verify_mutation_lease(
                f"accountability_case:{case_id}:status",
                body,
                actor=actor,
                config=config,
            )
            case = update_accountability_case_status(
                case_id,
                _required_str(body, "status"),
                closure_evidence_refs=_list_str(body.get("closure_evidence_refs")),
                residual_risk_accepted_by=_optional_str(body, "residual_risk_accepted_by"),
                log_path=config.accountability_cases_log,
            )
            return _ok({"case": asdict(case)})

        if method == "POST" and route == "/kernel/a2a/messages":
            _verify_mutation_lease("a2a:messages", body, actor=actor, config=config)
            msg = send_agent_message(
                from_role=_required_str(body, "from_role"),
                to_role=_required_str(body, "to_role"),
                kind=_required_str(body, "kind"),
                subject=_required_str(body, "subject"),
                body=_required_str(body, "body"),
                expects_response=bool(body.get("expects_response")),
                thread_id=_optional_str(body, "thread_id"),
                causality_id=_optional_str(body, "causality_id"),
                expires_utc=_optional_str(body, "expires_utc"),
                references=_list_str(body.get("references")),
                artifacts=_list_str(body.get("artifacts")),
                metadata=dict(body.get("metadata") or {}),
                enforce_policy=bool(body.get("enforce_policy", True)),
                parent_obligation_id=_optional_str(body, "parent_obligation_id"),
                channels_dir=config.org_dir / "channels",
                roles_dir=config.org_dir / "roles",
                transition_log_path=config.transition_log,
                max_thread_messages=config.a2a_max_thread_messages,
                max_parent_depth=config.a2a_max_parent_depth,
            )
            return _ok({"message": asdict(msg)}, status=201)

        if (
            method == "POST"
            and len(parts) == 5
            and parts[:3] == ["kernel", "a2a", "messages"]
            and parts[4] == "status"
        ):
            message_id = parts[3]
            _verify_mutation_lease(f"a2a:message:{message_id}:status", body, actor=actor, config=config)
            msg = update_agent_message_status(
                role_id=_required_str(body, "role_id"),
                message_id=message_id,
                status=_required_str(body, "status"),
                actor=str(body.get("actor") or actor.actor_id),
                note=str(body.get("note") or ""),
                channels_dir=config.org_dir / "channels",
                transition_log_path=config.transition_log,
            )
            return _ok({"message": asdict(msg)})

        if (
            method == "POST"
            and len(parts) == 5
            and parts[:3] == ["kernel", "a2a", "messages"]
            and parts[4] == "obligation"
        ):
            message_id = parts[3]
            _verify_mutation_lease(f"a2a:message:{message_id}:obligation", body, actor=actor, config=config)
            msg = update_obligation_state(
                role_id=_required_str(body, "role_id"),
                message_id=message_id,
                new_state=_required_str(body, "state"),
                actor=str(body.get("actor") or actor.actor_id),
                note=str(body.get("note") or ""),
                channels_dir=config.org_dir / "channels",
                transition_log_path=config.transition_log,
            )
            return _ok({"message": asdict(msg)})

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "gates"]
            and parts[3] == "resolve"
        ):
            _verify_mutation_lease(f"gate:{parts[2]}", body, actor=actor, config=config)
            result = resolve_gate(
                gate_id=parts[2],
                chosen_option=_required_str(body, "chosen_option"),
                reason=str(body.get("reason") or ""),
                gates_dir=config.gates_dir,
                resolved_dir=config.gates_resolved_dir,
                transition_log=config.transition_log,
                actor=str(body.get("resolved_by") or actor.actor_id),
            )
            return _ok({"result": result.as_dict()})

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "governance-changes"]
            and parts[3] == "decision"
        ):
            from cognitive_firm.orchestration.governance_changes import (
                list_governance_changes,
            )
            from cognitive_firm.orchestration.kernel_events import (
                record_kernel_event,
            )

            proposal_id = parts[2]
            decision = _required_str(body, "decision")
            if decision not in ("approve", "decline"):
                return _error(
                    400, "decision must be 'approve' or 'decline'"
                )
            proposals = {
                p.proposal_id: p
                for p in list_governance_changes(
                    log_path=_governance_changes_log(config)
                )
            }
            proposal = proposals.get(proposal_id)
            if proposal is None:
                return _error(
                    404, f"no governance change {proposal_id!r}"
                )
            if proposal.status != "review_ready":
                return _error(
                    409,
                    f"governance change {proposal_id!r} is not awaiting "
                    f"review (status: {proposal.status})",
                )
            if proposal_id in _decided_governance_ids(config):
                return _error(
                    409,
                    f"governance change {proposal_id!r} has already been "
                    f"decided",
                )
            verb = (
                "governance_change.approved"
                if decision == "approve"
                else "governance_change.declined"
            )
            # The recorded decider is the request's actor context — when auth
            # is on, _actor_context has already pinned this to the
            # authenticated subject. A body field cannot forge the attribution
            # on a governance decision (the accountability record).
            event = record_kernel_event(
                actor=actor.actor_id,
                verb=verb,
                object_ref=f"governance_change:{proposal_id}",
                payload={
                    "title": proposal.title,
                    "change_kind": proposal.change_kind,
                    "reason": str(body.get("reason") or ""),
                },
                log_path=config.transition_log,
            )
            return _ok(
                {
                    "result": {
                        "proposal_id": proposal_id,
                        "decision": decision,
                        "decided_by": event.actor,
                        "event_id": event.event_id,
                    }
                }
            )

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "governance-changes"]
            and parts[3] == "outcome-link"
        ):
            from cognitive_firm.orchestration.governance_changes import (
                list_governance_changes,
            )

            proposal_id = parts[2]
            _verify_mutation_lease("outcome_links:create", body, actor=actor, config=config)
            proposals = {
                p.proposal_id: p
                for p in list_governance_changes(
                    log_path=_governance_changes_log(config)
                )
            }
            proposal = proposals.get(proposal_id)
            if proposal is None:
                return _error(404, f"no governance change {proposal_id!r}")
            if proposal_id not in _approved_governance_ids(config):
                return _error(
                    409,
                    "predicted mutation outcome links require an approved "
                    "governance change; use /kernel/outcome-links directly "
                    "for planning-only measurements",
                )
            request = build_predicted_mutation_outcome_link_request(
                PredictedMutationOutcomeInput(
                    proposal=proposal.as_dict(),
                    created_by=str(body.get("created_by") or actor.actor_id),
                    learning_event_id=_optional_str(body, "learning_event_id"),
                    owner_role=_optional_str(body, "owner_role"),
                    tenant_id=_optional_str(body, "tenant_id"),
                    project_id=_optional_str(body, "project_id"),
                    metadata=dict(body.get("metadata") or {}),
                    outcome_link_id=_optional_str(body, "outcome_link_id"),
                )
            )
            link = create_outcome_link(
                change_ref=_required_str(request, "change_ref"),
                change_kind=_required_str(request, "change_kind"),
                metric_name=_required_str(request, "metric_name"),
                metric_unit=_required_str(request, "metric_unit"),
                created_by=_required_str(request, "created_by"),
                learning_event_id=_optional_str(request, "learning_event_id"),
                tenant_id=_optional_str(request, "tenant_id"),
                project_id=_optional_str(request, "project_id"),
                owner_role=_optional_str(request, "owner_role"),
                direction=_optional_str(request, "direction"),
                metadata=dict(request.get("metadata") or {}),
                outcome_link_id=_optional_str(request, "outcome_link_id"),
                actor=str(body.get("actor") or actor.actor_id),
                log_path=config.outcome_links_log,
                kernel_events_log=config.kernel_events_log,
            )
            return _ok(
                {
                    "outcome_link": link.as_dict(),
                    "source_proposal": proposal.as_dict(),
                    "request": request,
                },
                status=201,
            )

        if method == "POST" and route == "/kernel/directives":
            target_role = _required_str(body, "target_role")
            _verify_mutation_lease(f"directive:{target_role}", body, actor=actor, config=config)
            result = issue_directive(
                target_role=target_role,
                message=_required_str(body, "message"),
                org_dir=config.org_dir,
                transition_log=config.transition_log,
                actor=str(body.get("from") or actor.actor_id),
            )
            return _ok({"result": result.as_dict()}, status=201)

        if method == "POST" and route == "/kernel/controls":
            target_role = _required_str(body, "target_role")
            _verify_mutation_lease(f"control:{target_role}", body, actor=actor, config=config)
            result = issue_control(
                target_role=target_role,
                action=_required_str(body, "action"),
                org_dir=config.org_dir,
                transition_log=config.transition_log,
                actor=str(body.get("issued_by") or actor.actor_id),
            )
            return _ok({"result": result.as_dict()}, status=201)

        if method == "POST" and route == "/kernel/chat/messages":
            role_id = _required_str(body, "role_id")
            _verify_mutation_lease(f"chat:{role_id}", body, actor=actor, config=config)
            result = send_chat_message(
                role_id=role_id,
                text=_required_str(body, "text"),
                org_dir=config.org_dir,
                transition_log=config.transition_log,
                sender=str(body.get("sender") or actor.actor_id),
            )
            return _ok({"result": result.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "roles"]
            and parts[3] == "agent-utilization"
        ):
            _verify_mutation_lease(
                f"role_agent_utilization:{parts[2]}", body, actor=actor, config=config
            )
            result = update_role_agent_utilization(
                role_id=parts[2],
                caps=dict(body.get("agent_utilization") or {}),
                org_dir=config.org_dir,
                transition_log=config.transition_log,
                actor=str(body.get("updated_by") or actor.actor_id),
            )
            return _ok({"result": result.as_dict()})

        if method == "POST" and route == "/kernel/actors":
            _require_identity_admin(actor, config=config)
            identity = register_actor_identity(
                actor_id=_required_str(body, "actor_id"),
                actor_kind=_required_str(body, "actor_kind"),
                display_name=_required_str(body, "display_name"),
                auth_subject=_optional_str(body, "auth_subject"),
                identity_provider=_optional_str(body, "identity_provider"),
                roles_allowed=_list_str(body.get("roles_allowed")),
                tenant_ids=_list_str(body.get("tenant_ids")),
                status=str(body.get("status") or "active"),
                metadata=dict(body.get("metadata") or {}),
                log_path=config.actor_identity_log,
            )
            return _ok({"actor": asdict(identity)}, status=201)

        if method == "POST" and route == "/kernel/memberships":
            _require_identity_admin(actor, config=config)
            membership = grant_actor_membership(
                actor_id=_required_str(body, "actor_id"),
                role_id=_required_str(body, "role_id"),
                granted_by=str(body.get("granted_by") or actor.actor_id),
                decision_right_basis=_required_str(body, "decision_right_basis"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                starts_at_utc=_optional_str(body, "starts_at_utc"),
                expires_at_utc=_optional_str(body, "expires_at_utc"),
                metadata=dict(body.get("metadata") or {}),
                log_path=config.actor_membership_log,
            )
            return _ok({"membership": membership.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "memberships"]
            and parts[3] == "revoke"
        ):
            _require_identity_admin(actor, config=config)
            membership = revoke_actor_membership(
                parts[2],
                revoked_by=str(body.get("revoked_by") or actor.actor_id),
                reason=_required_str(body, "reason"),
                log_path=config.actor_membership_log,
            )
            return _ok({"membership": membership.as_dict()})

        if method == "POST" and route == "/kernel/leases":
            if config.mutation_backend is not None:
                lease_record = config.mutation_backend.acquire_lease(
                    resource_ref=_required_str(body, "resource_ref"),
                    actor_id=actor.actor_id,
                    role_id=actor.role_id,
                    ttl_seconds=int(body.get("ttl_seconds") or 300),
                    purpose=str(body.get("purpose") or ""),
                    metadata=dict(body.get("metadata") or {}),
                )
                return _ok({"lease": lease_record}, status=201)
            lease = acquire_lease(
                resource_ref=_required_str(body, "resource_ref"),
                actor=actor,
                ttl_seconds=int(body.get("ttl_seconds") or 300),
                purpose=str(body.get("purpose") or ""),
                metadata=dict(body.get("metadata") or {}),
                log_path=config.leases_log,
            )
            return _ok({"lease": asdict(lease)}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "leases"]
            and parts[3] == "release"
        ):
            if config.mutation_backend is not None:
                lease_record = config.mutation_backend.release_lease(
                    lease_id=parts[2],
                    actor_id=actor.actor_id,
                )
                return _ok({"lease": lease_record})
            lease = release_lease(parts[2], actor=actor, log_path=config.leases_log)
            return _ok({"lease": asdict(lease)})

        if method == "POST" and route == "/kernel/mutation-events":
            if config.mutation_backend is None:
                raise ValueError("mutation backend is not configured")
            event = body.get("event")
            if not isinstance(event, dict):
                raise ValueError("event must be a JSON object")
            result = config.mutation_backend.guarded_append_event(
                stream=_required_str(body, "stream"),
                event=event,
                resource_ref=_required_str(body, "resource_ref"),
                lease_id=_required_str(body, "lease_id"),
                actor_id=actor.actor_id,
                fencing_token=_required_int(body, "fencing_token"),
            )
            return _ok({"mutation": result}, status=201)

        if method == "GET" and route == "/kernel/action-attestations":
            attestations = list_action_attestations(
                subject_ref=query.get("subject_ref", [None])[0],
                producer=query.get("producer", [None])[0],
                tenant_id=query.get("tenant_id", [None])[0],
                project_id=query.get("project_id", [None])[0],
                run_id=query.get("run_id", [None])[0],
                verification_status=query.get("verification_status", [None])[0],
                log_path=config.action_attestation_log,
            )
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "action_attestations": [
                            action_attestation_resource(attestation).as_dict()
                            for attestation in attestations
                        ]
                    }
                )
            return _ok(
                {
                    "action_attestations": [
                        asdict(attestation) for attestation in attestations
                    ]
                }
            )

        if method == "GET" and route == "/kernel/agent-invocations":
            limit = _query_optional_int(query, "limit", default=20)
            invocations = list_agent_invocation_audits(
                producer=query.get("producer", [None])[0],
                tenant_id=query.get("tenant_id", [None])[0],
                project_id=query.get("project_id", [None])[0],
                run_id=query.get("run_id", [None])[0],
                verification_status=query.get("verification_status", [None])[0],
                limit=limit,
                log_path=config.action_attestation_log,
            )
            return _ok(
                {
                    "agent_invocations": [
                        invocation.as_dict() for invocation in invocations
                    ],
                    "limit": limit,
                }
            )

        if method == "POST" and route == "/kernel/action-attestations":
            subject_ref = _required_str(body, "subject_ref")
            _verify_mutation_lease(
                f"action_attestation:{subject_ref}",
                body,
                actor=actor,
                config=config,
            )
            attestation = create_action_attestation(
                subject_kind=_required_str(body, "subject_kind"),
                subject_ref=subject_ref,
                subject_digest=_required_str(body, "subject_digest"),
                producer=str(body.get("producer") or actor.role_id or actor.actor_id),
                action_type=_required_str(body, "action_type"),
                runtime_ref=_optional_str(body, "runtime_ref"),
                tool_ref=_optional_str(body, "tool_ref"),
                policy_ref=_optional_str(body, "policy_ref"),
                input_refs=_list_str(body.get("input_refs")),
                output_refs=_list_str(body.get("output_refs")),
                signature_ref=_optional_str(body, "signature_ref"),
                transparency_ref=_optional_str(body, "transparency_ref"),
                verification_status=str(body.get("verification_status") or "unverified"),
                verification_summary=_optional_str(body, "verification_summary"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                run_id=_optional_str(body, "run_id"),
                metadata=dict(body.get("metadata") or {}),
                attestation_id=_optional_str(body, "attestation_id"),
                log_path=config.action_attestation_log,
            )
            return _ok({"action_attestation": asdict(attestation)}, status=201)

        if method == "GET" and route == "/kernel/formal-verifications":
            records = list_formal_verifications(
                formal_system=query.get("formal_system", [None])[0],
                verdict=query.get("verdict", [None])[0],
                property_class=query.get("property_class", [None])[0],
                subject_ref=query.get("subject_ref", [None])[0],
                tenant_id=query.get("tenant_id", [None])[0],
                project_id=query.get("project_id", [None])[0],
                run_id=query.get("run_id", [None])[0],
                log_path=config.formal_verification_log,
            )
            return _ok({"formal_verifications": [asdict(record) for record in records]})

        if method == "POST" and route == "/kernel/formal-verifications/provider-payload":
            _verify_mutation_lease(
                "formal_verifications:create_from_provider_payload",
                body,
                actor=actor,
                config=config,
            )
            payload = body.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("payload must be an object")
            record = create_formal_verification_from_provider_payload(
                payload,
                log_path=config.formal_verification_log,
                action_attestation_log_path=config.action_attestation_log,
                create_attestation=bool(body.get("create_attestation", True)),
                authority_root=config.org_dir,
            )
            return _ok({"formal_verification": asdict(record)}, status=201)

        if method == "POST" and route == "/kernel/mutation-proofs/build":
            from cognitive_firm.orchestration.mutation_proofs import (
                build_governed_mutation_proof,
                governed_mutation_proof_to_dict,
            )

            proof = build_governed_mutation_proof(
                step_id=_required_str(body, "step_id"),
                change_kind=_required_str(body, "change_kind"),
                target_ref=_required_str(body, "target_ref"),
                run_id=_required_str(body, "run_id"),
                work_id=_required_str(body, "work_id"),
                proposal_id=_required_str(body, "proposal_id"),
                approval_event_id=_required_str(body, "approval_event_id"),
                mutation_ref=_required_str(body, "mutation_ref"),
                attestation_id=_required_str(body, "attestation_id"),
                learning_event_id=_required_str(body, "learning_event_id"),
                outcome_link_id=_required_str(body, "outcome_link_id"),
                routine_review_id=_required_str(body, "routine_review_id"),
                bundle_id=_optional_str(body, "bundle_id"),
                bundle_digest=_optional_str(body, "bundle_digest"),
                bundle_verdict=_optional_str(body, "bundle_verdict"),
                commit_sha=_required_str(body, "commit_sha"),
                bundle_validation_errors=_list_str(body.get("bundle_validation_errors")),
                evidence_carrier_refs=_list_str(body.get("evidence_carrier_refs")),
            )
            return _ok({"proof": governed_mutation_proof_to_dict(proof)})

        if method == "POST" and route == "/kernel/mutation-proofs/validate":
            from cognitive_firm.orchestration.mutation_proofs import (
                validate_governed_mutation_proof_payload,
            )

            proof_payload = body.get("proof", body)
            if not isinstance(proof_payload, dict):
                raise ValueError("proof must be a JSON object")
            errors = validate_governed_mutation_proof_payload(proof_payload)
            return _ok(
                {
                    "valid": not errors,
                    "errors": errors,
                    "proof_kind": proof_payload.get("proof_kind"),
                    "proof_digest": proof_payload.get("proof_digest"),
                }
            )

        if method == "POST" and route == "/kernel/governed-run-bundles/build":
            from cognitive_firm.orchestration.artifact_bundle import (
                build_governed_run_attestation_bundle,
                governed_run_bundle_summary,
                governed_run_bundle_to_dict,
                validate_governed_run_bundle_payload,
            )

            bundle = build_governed_run_attestation_bundle(
                _required_str(body, "run_id"),
                transition_log_path=config.transition_log,
                action_attestation_log_path=config.action_attestation_log,
                human_work_log_path=config.human_work_log,
                outcome_links_log_path=config.outcome_links_log,
                accountability_cases_log_path=config.accountability_cases_log,
                work_items_log_path=config.work_items_log,
                formal_verification_log_path=config.formal_verification_log,
                leases_log_path=config.leases_log,
                authority_root=config.project_root,
                trusted_formal_verification_providers=set(
                    _list_str(body.get("trusted_formal_verification_providers"))
                )
                or None,
            )
            payload = governed_run_bundle_to_dict(bundle)
            validation_errors = validate_governed_run_bundle_payload(payload)
            response = {
                "summary": governed_run_bundle_summary(bundle),
                "validation": {"ok": not validation_errors, "errors": validation_errors},
            }
            if _query_bool(query, "summary") or bool(body.get("summary")):
                return _ok(response)
            return _ok({"bundle": payload, **response})

        if method == "POST" and route == "/kernel/governed-run-bundles/validate":
            from cognitive_firm.orchestration.artifact_bundle import (
                validate_governed_run_bundle_payload,
            )

            bundle_payload = body.get("bundle", body)
            if not isinstance(bundle_payload, dict):
                raise ValueError("bundle must be a JSON object")
            errors = validate_governed_run_bundle_payload(bundle_payload)
            return _ok(
                {
                    "valid": not errors,
                    "errors": errors,
                    "bundle_id": bundle_payload.get("bundle_id"),
                    "bundle_digest": bundle_payload.get("bundle_digest"),
                    "verdict": bundle_payload.get("verdict"),
                }
            )

        if method == "POST" and route == "/kernel/multi-agent-trace-events":
            _verify_mutation_lease("multi_agent_trace_events:record", body, actor=actor, config=config)
            rows = body.get("events")
            if rows is not None:
                if not isinstance(rows, list):
                    raise ValueError("events must be a list")
                events = [
                    record_trace_event(
                        runtime_name=str(row.get("runtime_name") or body.get("runtime_name") or ""),
                        external_run_id=str(row.get("external_run_id") or body.get("external_run_id") or ""),
                        event_kind=str(row.get("event_kind") or "custom"),
                        agent_id=str(row.get("agent_id") or ""),
                        status=str(row.get("status") or "observed"),
                        cognitive_run_id=row.get("cognitive_run_id") or body.get("cognitive_run_id"),
                        parent_agent_id=row.get("parent_agent_id"),
                        target_agent_id=row.get("target_agent_id"),
                        owner_role=row.get("owner_role") or body.get("owner_role"),
                        step_id=row.get("step_id"),
                        summary=row.get("summary"),
                        payload_ref=row.get("payload_ref"),
                        token_count=row.get("token_count"),
                        cost_units=row.get("cost_units"),
                        source_refs=_list_str(row.get("source_refs")),
                        metadata=dict(row.get("metadata") or {}),
                        event_id=row.get("event_id"),
                        log_path=config.trace_events_log,
                    )
                    for row in rows
                ]
            else:
                event = record_trace_event(
                    runtime_name=_required_str(body, "runtime_name"),
                    external_run_id=_required_str(body, "external_run_id"),
                    event_kind=str(body.get("event_kind") or "custom"),
                    agent_id=_required_str(body, "agent_id"),
                    status=str(body.get("status") or "observed"),
                    cognitive_run_id=_optional_str(body, "cognitive_run_id"),
                    parent_agent_id=_optional_str(body, "parent_agent_id"),
                    target_agent_id=_optional_str(body, "target_agent_id"),
                    owner_role=_optional_str(body, "owner_role"),
                    step_id=_optional_str(body, "step_id"),
                    summary=_optional_str(body, "summary"),
                    payload_ref=_optional_str(body, "payload_ref"),
                    token_count=body.get("token_count"),
                    cost_units=body.get("cost_units"),
                    source_refs=_list_str(body.get("source_refs")),
                    metadata=dict(body.get("metadata") or {}),
                    event_id=_optional_str(body, "event_id"),
                    log_path=config.trace_events_log,
                )
                events = [event]
            return _ok({"trace_events": [event.as_dict() for event in events]}, status=201)

        if method == "GET" and route == "/kernel/multi-agent-trace-events":
            events = list_trace_events(
                runtime_name=query.get("runtime_name", [None])[0],
                external_run_id=query.get("external_run_id", [None])[0],
                cognitive_run_id=query.get("cognitive_run_id", [None])[0],
                log_path=config.trace_events_log,
            )
            if _query_bool(query, "resource"):
                return _ok(
                    {"trace_events": [trace_event_resource(event).as_dict() for event in events]}
                )
            return _ok({"trace_events": [event.as_dict() for event in events]})

        if method == "POST" and route == "/kernel/failure-attribution-packets":
            _verify_mutation_lease("failure_attribution_packets:create", body, actor=actor, config=config)
            packet_events = _trace_events_for_packet(body, config=config)
            packet = create_failure_attribution_packet(
                events=packet_events,
                failure_summary=_required_str(body, "failure_summary"),
                proposed_carrier_kind=_required_str(body, "proposed_carrier_kind"),
                owner_role=_required_str(body, "owner_role"),
                attribution_scope=str(body.get("attribution_scope") or "interaction"),
                runtime_name=_optional_str(body, "runtime_name"),
                external_run_id=_optional_str(body, "external_run_id"),
                cognitive_run_id=_optional_str(body, "cognitive_run_id"),
                target_ref=_optional_str(body, "target_ref"),
                proposed_transition_kind=_optional_str(body, "proposed_transition_kind") or "role_review",
                local_findings=(
                    list(body["local_findings"])
                    if "local_findings" in body
                    else None
                ),
                cross_agent_evidence=(
                    list(body["cross_agent_evidence"])
                    if "cross_agent_evidence" in body
                    else None
                ),
                disagreement_summary=_optional_str(body, "disagreement_summary"),
                risk_summary=_optional_str(body, "risk_summary"),
                rollback_plan=_optional_str(body, "rollback_plan"),
                invariant_evidence_refs=_list_str(body.get("invariant_evidence_refs")),
                metadata=dict(body.get("metadata") or {}),
                packet_id=_optional_str(body, "packet_id"),
                log_path=config.attribution_packets_log,
            )
            return _ok({"packet": packet.as_dict()}, status=201)

        if method == "GET" and route == "/kernel/failure-attribution-packets":
            packets = list_failure_attribution_packets(
                status=query.get("status", [None])[0],
                log_path=config.attribution_packets_log,
            )
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "packets": [
                            attribution_packet_resource(packet).as_dict() for packet in packets
                        ]
                    }
                )
            return _ok({"packets": [packet.as_dict() for packet in packets]})

        if method == "GET" and route == "/kernel/delegation-graph":
            events = list_trace_events(
                runtime_name=query.get("runtime_name", [None])[0],
                external_run_id=query.get("external_run_id", [None])[0],
                cognitive_run_id=query.get("cognitive_run_id", [None])[0],
                log_path=config.trace_events_log,
            )
            graph = build_delegation_graph(
                events,
                runtime_name=query.get("runtime_name", [None])[0],
                external_run_id=query.get("external_run_id", [None])[0],
                cognitive_run_id=query.get("cognitive_run_id", [None])[0],
            )
            if _query_bool(query, "resource"):
                return _ok({"graph": delegation_graph_resource(graph).as_dict()})
            return _ok({"graph": graph.as_dict()})

        if method == "GET" and route == "/kernel/phase-execution-plans":
            plans = list_phase_execution_plans(log_path=config.phase_execution_log)
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "plans": [
                            phase_execution_plan_resource(plan).as_dict() for plan in plans
                        ]
                    }
                )
            return _ok({"plans": [plan.as_dict() for plan in plans]})

        if method == "POST" and route == "/kernel/phase-execution-plans":
            _verify_mutation_lease("phase_execution:start", body, actor=actor, config=config)
            plan = start_phase_execution_plan(
                objective=_required_str(body, "objective"),
                owner_role=str(body.get("owner_role") or actor.role_id or actor.actor_id),
                total_budget_units=float(body.get("total_budget_units") or 1.0),
                max_attempts=int(body.get("max_attempts") or 3),
                run_id=_optional_str(body, "run_id"),
                work_id=_optional_str(body, "work_id"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                metadata=dict(body.get("metadata") or {}),
                plan_id=_optional_str(body, "plan_id"),
                log_path=config.phase_execution_log,
            )
            return _ok({"plan": plan.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "phase-execution-plans"]
            and parts[3] == "directives"
        ):
            plan_id = parts[2]
            _verify_mutation_lease(f"phase_execution:{plan_id}:directive", body, actor=actor, config=config)
            plan = record_phase_directive(
                plan_id=plan_id,
                phase=_required_str(body, "phase"),
                issued_by=str(body.get("issued_by") or actor.actor_id),
                directive=_required_str(body, "directive"),
                run_id=_optional_str(body, "run_id"),
                work_id=_optional_str(body, "work_id"),
                budget_units=body.get("budget_units"),
                evidence_refs=_list_str(body.get("evidence_refs")),
                output_refs=_list_str(body.get("output_refs")),
                metadata=dict(body.get("metadata") or {}),
                directive_id=_optional_str(body, "directive_id"),
                log_path=config.phase_execution_log,
            )
            return _ok({"plan": plan.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "phase-execution-plans"]
            and parts[3] == "verification-feedback"
        ):
            plan_id = parts[2]
            _verify_mutation_lease(f"phase_execution:{plan_id}:feedback", body, actor=actor, config=config)
            plan = record_verification_feedback(
                plan_id=plan_id,
                verifier_role=str(body.get("verifier_role") or actor.role_id or actor.actor_id),
                verdict=_required_str(body, "verdict"),
                rationale=_required_str(body, "rationale"),
                evidence_refs=_list_str(body.get("evidence_refs")),
                failed_phase=str(body.get("failed_phase") or "execution"),
                budget_decay=float(body.get("budget_decay") or 0.5),
                min_remaining_budget_units=float(body.get("min_remaining_budget_units") or 0.01),
                metadata=dict(body.get("metadata") or {}),
                feedback_id=_optional_str(body, "feedback_id"),
                log_path=config.phase_execution_log,
            )
            return _ok({"plan": plan.as_dict()}, status=201)

        if method == "GET" and route == "/kernel/protocol-experiments":
            experiments = list_protocol_experiments(log_path=config.protocol_experiments_log)
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "experiments": [
                            protocol_experiment_resource(experiment).as_dict()
                            for experiment in experiments
                        ]
                    }
                )
            return _ok({"experiments": [experiment.as_dict() for experiment in experiments]})

        if method == "POST" and route == "/kernel/protocol-experiments":
            _verify_mutation_lease("protocol_experiments:start", body, actor=actor, config=config)
            experiment = start_protocol_experiment(
                objective=_required_str(body, "objective"),
                owner_role=str(body.get("owner_role") or actor.role_id or actor.actor_id),
                candidate_protocols=_list_str(body.get("candidate_protocols")),
                baseline_protocol=_required_str(body, "baseline_protocol"),
                objective_metric=str(body.get("objective_metric") or "quality_score"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                metadata=dict(body.get("metadata") or {}),
                experiment_id=_optional_str(body, "experiment_id"),
                log_path=config.protocol_experiments_log,
            )
            return _ok({"experiment": experiment.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "protocol-experiments"]
            and parts[3] == "observations"
        ):
            experiment_id = parts[2]
            _verify_mutation_lease(
                f"protocol_experiment:{experiment_id}:observation",
                body,
                actor=actor,
                config=config,
            )
            experiment = record_protocol_observation(
                experiment_id=experiment_id,
                protocol=_required_str(body, "protocol"),
                task_ref=_required_str(body, "task_ref"),
                quality_score=float(_required_number(body, "quality_score")),
                latency_units=float(body.get("latency_units") or 0.0),
                cost_units=float(body.get("cost_units") or 0.0),
                abstentions=int(body.get("abstentions") or 0),
                failures=int(body.get("failures") or 0),
                guardrail_violations=int(body.get("guardrail_violations") or 0),
                evidence_refs=_list_str(body.get("evidence_refs")),
                metadata=dict(body.get("metadata") or {}),
                observation_id=_optional_str(body, "observation_id"),
                log_path=config.protocol_experiments_log,
            )
            return _ok({"experiment": experiment.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "protocol-experiments"]
            and parts[3] == "reports"
        ):
            experiment_id = parts[2]
            _verify_mutation_lease(f"protocol_experiment:{experiment_id}:report", body, actor=actor, config=config)
            experiment = build_protocol_experiment_report(
                experiment_id=experiment_id,
                proposed_by=str(body.get("proposed_by") or actor.actor_id),
                target_ref=_required_str(body, "target_ref"),
                min_observations_per_protocol=int(body.get("min_observations_per_protocol") or 2),
                min_quality_delta=float(body.get("min_quality_delta") or 0.05),
                max_guardrail_violations=int(body.get("max_guardrail_violations") or 0),
                log_path=config.protocol_experiments_log,
            )
            return _ok({"experiment": experiment.as_dict()}, status=201)

        if method == "GET" and route == "/kernel/policy-decisions":
            decisions = list_policy_decisions(
                effect=query.get("effect", [None])[0],
                actor_id=query.get("actor_id", [None])[0],
                resource_ref=query.get("resource_ref", [None])[0],
                tenant_id=query.get("tenant_id", [None])[0],
                log_path=config.policy_decisions_log,
            )
            payload = (
                [policy_decision_resource(decision).as_dict() for decision in decisions]
                if _query_bool(query, "resource")
                else [decision.as_dict() for decision in decisions]
            )
            return _ok({"policy_decisions": payload})

        if method == "POST" and route == "/kernel/policy-decisions/evaluate":
            _verify_mutation_lease("policy_decisions:evaluate", body, actor=actor, config=config)
            request_payload = body.get("request")
            if not isinstance(request_payload, dict):
                raise ValueError("request must be an object")
            rules = body.get("rules") or []
            if not isinstance(rules, list):
                raise ValueError("rules must be a list")
            decision = evaluate_policy(
                PolicyDecisionRequest(
                    action=_required_str(request_payload, "action"),
                    actor_id=_required_str(request_payload, "actor_id"),
                    resource_ref=_required_str(request_payload, "resource_ref"),
                    tenant_id=_optional_str(request_payload, "tenant_id"),
                    role_id=_optional_str(request_payload, "role_id"),
                    project_id=_optional_str(request_payload, "project_id"),
                    context=dict(request_payload.get("context") or {}),
                ),
                rules=[dict(rule) for rule in rules],
                default_effect=str(body.get("default_effect") or "deny"),
                default_reason=str(body.get("default_reason") or "no policy rule matched"),
                policy_ref=_optional_str(body, "policy_ref"),
                source_surface=_optional_str(body, "source_surface"),
                source_decision_ref=_optional_str(body, "source_decision_ref"),
                required_approval=_optional_str(body, "required_approval"),
                terminal=body.get("terminal"),
                matched_paths=_list_str(body.get("matched_paths")),
                evidence_refs=_list_str(body.get("evidence_refs")),
                metadata=dict(body.get("metadata") or {}),
                log_path=config.policy_decisions_log,
            )
            payload = (
                policy_decision_resource(decision).as_dict()
                if bool(body.get("resource"))
                else decision.as_dict()
            )
            return _ok({"policy_decision": payload}, status=201)

        # --- action impact: offline evaluation and review packet, not live optimizer ---
        if method == "GET" and route == "/kernel/action-impact/policy-evaluations":
            reports = list_policy_evaluations(
                log_path=config.policy_evaluations_log,
                candidate_policy_id=query.get("candidate_policy_id", [None])[0],
                status=query.get("status", [None])[0],
            )
            return _ok({"policy_evaluations": [report.as_dict() for report in reports]})

        if method == "POST" and route == "/kernel/action-impact/policy-evaluations/evaluate":
            _verify_mutation_lease("action_impact:evaluate_policy", body, actor=actor, config=config)
            candidate_action_by_context = body.get("candidate_action_by_context")
            if not isinstance(candidate_action_by_context, dict):
                raise ValueError("candidate_action_by_context must be an object")
            summary_path = (
                Path(str(body.get("summary_path")))
                if body.get("summary_path")
                else config.action_impact_summary
            )
            summary = summary_from_optional_path(summary_path)
            report = evaluate_offline_policy_candidate(
                summary.records,
                candidate_policy_id=_required_str(body, "candidate_policy_id"),
                candidate_policy_ref=_optional_str(body, "candidate_policy_ref"),
                candidate_action_by_context={
                    str(key): str(value)
                    for key, value in candidate_action_by_context.items()
                },
                context_keys=_list_str(body.get("context_keys")),
                objective_metric=_optional_str(body, "objective_metric"),
                min_matched=int(body.get("min_matched") or 20),
                min_support_coverage=float(body.get("min_support_coverage") or 0.25),
                max_negative_externality_rate=float(body.get("max_negative_externality_rate") or 0.0),
                max_human_review_rate=float(body.get("max_human_review_rate") or 0.25),
                evidence_refs=_list_str(body.get("evidence_refs")),
                metadata=dict(body.get("metadata") or {}),
            )
            append_policy_evaluation(report, log_path=config.policy_evaluations_log)
            return _ok({"policy_evaluation": report.as_dict()}, status=201)

        if method == "GET" and route == "/kernel/action-impact/policy-promotion-packets":
            packets = list_policy_promotion_packets(
                log_path=config.policy_promotion_packets_log,
                candidate_policy_id=query.get("candidate_policy_id", [None])[0],
                status=query.get("status", [None])[0],
            )
            return _ok({"policy_promotion_packets": [packet.as_dict() for packet in packets]})

        if method == "POST" and route == "/kernel/action-impact/policy-promotion-packets":
            _verify_mutation_lease("action_impact:build_promotion_packet", body, actor=actor, config=config)
            report = get_policy_evaluation(
                _required_str(body, "evaluation_id"),
                log_path=config.policy_evaluations_log,
            )
            packet = build_policy_promotion_packet(
                report,
                proposed_by=_required_str(body, "proposed_by"),
                target_ref=_optional_str(body, "target_ref"),
                title=_optional_str(body, "title"),
                rationale=_optional_str(body, "rationale"),
                expected_behavior_change=_optional_str(body, "expected_behavior_change"),
                rollback_plan=_optional_str(body, "rollback_plan"),
                predicted_effect=body.get("predicted_effect"),
                authority_diff_ref=_optional_str(body, "authority_diff_ref"),
                formal_verification_refs=_list_str(body.get("formal_verification_refs")),
                learning_event_refs=_list_str(body.get("learning_event_refs")),
                evidence_refs=_list_str(body.get("evidence_refs")),
                metadata=dict(body.get("metadata") or {}),
            )
            append_policy_promotion_packet(packet, log_path=config.policy_promotion_packets_log)
            return _ok({"policy_promotion_packet": packet.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 5
            and parts[:3] == ["kernel", "action-impact", "policy-promotion-packets"]
            and parts[4] == "governance-change"
        ):
            packet_id = parts[3]
            _verify_mutation_lease(
                f"action_impact:policy_promotion_packet:{packet_id}:governance_change",
                body,
                actor=actor,
                config=config,
            )
            packet = get_policy_promotion_packet(
                packet_id,
                log_path=config.policy_promotion_packets_log,
            )
            request = build_policy_promotion_governance_change_request(
                packet,
                proposal_id=_optional_str(body, "proposal_id"),
                owner_role=_optional_str(body, "owner_role"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                metadata=dict(body.get("metadata") or {}),
                require_review_ready=not _payload_bool(body, "allow_non_review_ready"),
            )
            request["invariant_checks"] = _governance_invariant_checks_from_body(
                {**body, **request}
            )
            from cognitive_firm.orchestration.governance_changes import (
                propose_governance_change,
            )

            proposal = propose_governance_change(
                change_kind=_required_str(request, "change_kind"),
                title=_required_str(request, "title"),
                proposed_by=_required_str(request, "proposed_by"),
                target_ref=_required_str(request, "target_ref"),
                rationale=_required_str(request, "rationale"),
                source_refs=_list_str(request.get("source_refs")),
                expected_behavior_change=_optional_str(request, "expected_behavior_change"),
                predicted_effect=(
                    dict(request.get("predicted_effect"))
                    if isinstance(request.get("predicted_effect"), dict)
                    else None
                ),
                risk_summary=_optional_str(request, "risk_summary"),
                rollback_plan=_optional_str(request, "rollback_plan"),
                owner_role=_optional_str(request, "owner_role"),
                tenant_id=_optional_str(request, "tenant_id"),
                project_id=_optional_str(request, "project_id"),
                invariant_checks=list(request.get("invariant_checks") or []),
                metadata=dict(request.get("metadata") or {}),
                proposal_id=_optional_str(request, "proposal_id"),
                log_path=_governance_changes_log(config),
            )
            return _ok(
                {
                    "policy_promotion_packet": packet.as_dict(),
                    "governance_change_request": request,
                    "proposal": proposal.as_dict(),
                    "boundary": {
                        "approved_governance": False,
                        "applied_policy": False,
                        "executed_runtime": False,
                    },
                },
                status=201,
            )

        if method == "GET" and route == "/kernel/capability-signals":
            signals = list_capability_signals(log_path=config.capability_signals_log)
            summary = summarize_capability_signals(signals)
            if _query_bool(query, "summary"):
                return _ok({"summary": summary.as_dict()})
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "signals": [
                            capability_signal_resource(signal).as_dict() for signal in signals
                        ],
                        "summary": summary.as_dict(),
                    }
                )
            return _ok(
                {
                    "signals": [signal.as_dict() for signal in signals],
                    "summary": summary.as_dict(),
                }
            )

        if method == "POST" and route == "/kernel/capability-signals":
            _verify_mutation_lease("capability_signals:record", body, actor=actor, config=config)
            signal = record_capability_signal(
                signal_kind=_required_str(body, "signal_kind"),
                source_ref=_required_str(body, "source_ref"),
                summary=_required_str(body, "summary"),
                owner_role=str(body.get("owner_role") or actor.role_id or actor.actor_id),
                severity=str(body.get("severity") or "warning"),
                worker_ref=_optional_str(body, "worker_ref"),
                run_id=_optional_str(body, "run_id"),
                work_id=_optional_str(body, "work_id"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                capability_ref=_optional_str(body, "capability_ref"),
                threshold_ref=_optional_str(body, "threshold_ref"),
                recommended_route=_optional_str(body, "recommended_route"),
                route_target_ref=_optional_str(body, "route_target_ref"),
                counts_as_failure=bool(body.get("counts_as_failure", False)),
                evidence_refs=_list_str(body.get("evidence_refs")),
                metadata=dict(body.get("metadata") or {}),
                signal_id=_optional_str(body, "signal_id"),
                log_path=config.capability_signals_log,
            )
            return _ok({"signal": signal.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "capability-signals"]
            and parts[3] == "route"
        ):
            signal_id = parts[2]
            _verify_mutation_lease(f"capability_signal:{signal_id}:route", body, actor=actor, config=config)
            signal = route_capability_signal(
                signal_id,
                route_kind=_required_str(body, "route_kind"),
                routed_by=str(body.get("routed_by") or actor.actor_id),
                rationale=_required_str(body, "rationale"),
                target_ref=_optional_str(body, "target_ref"),
                log_path=config.capability_signals_log,
            )
            return _ok({"signal": signal.as_dict()})

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "capability-signals"]
            and parts[3] == "close"
        ):
            signal_id = parts[2]
            _verify_mutation_lease(f"capability_signal:{signal_id}:close", body, actor=actor, config=config)
            signal = close_capability_signal(
                signal_id,
                closed_by=str(body.get("closed_by") or actor.actor_id),
                closure_ref=_required_str(body, "closure_ref"),
                rationale=_required_str(body, "rationale"),
                log_path=config.capability_signals_log,
            )
            return _ok({"signal": signal.as_dict()})

        if method == "POST" and route == "/kernel/execution-evidence/route":
            _verify_mutation_lease(
                "execution_evidence:route",
                body,
                actor=actor,
                config=config,
            )
            return _ok(
                _route_execution_evidence_payload(
                    body,
                    actor=actor,
                    config=config,
                ),
                status=201,
            )

        if method == "GET" and route == "/kernel/operating-units":
            units = list_operating_units(
                status=query.get("status", [None])[0],
                tenant_id=query.get("tenant_id", [None])[0],
                project_id=query.get("project_id", [None])[0],
                log_path=config.operating_units_log,
            )
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "operating_units": [
                            operating_unit_resource(unit).as_dict() for unit in units
                        ]
                    }
                )
            return _ok({"operating_units": [unit.as_dict() for unit in units]})

        if (
            method == "GET"
            and len(parts) == 3
            and parts[:2] == ["kernel", "operating-units"]
        ):
            unit = get_operating_unit(parts[2], log_path=config.operating_units_log)
            if unit is None:
                return _error(404, f"operating unit not found: {parts[2]}")
            payload = (
                operating_unit_resource(unit).as_dict()
                if _query_bool(query, "resource")
                else unit.as_dict()
            )
            return _ok({"operating_unit": payload})

        if method == "GET" and route == "/kernel/operating-unit-dashboard":
            dashboard = build_operating_unit_dashboard(
                operating_units_log=config.operating_units_log,
                work_items_log=config.work_items_log,
            )
            return _ok({"dashboard": dashboard.as_dict()})

        if method == "GET" and route == "/kernel/runs":
            runs = list_runs(log_path=config.transition_log)
            state_filter = query.get("state", [None])[0]
            owner_role_filter = query.get("owner_role", [None])[0]
            tenant_filter = query.get("tenant_id", [None])[0]
            project_filter = query.get("project_id", [None])[0]
            if state_filter is not None:
                runs = [run for run in runs if run.state == state_filter]
            if owner_role_filter is not None:
                runs = [run for run in runs if run.owner_role == owner_role_filter]
            if tenant_filter is not None:
                runs = [run for run in runs if run.tenant_id == tenant_filter]
            if project_filter is not None:
                runs = [run for run in runs if run.project_id == project_filter]
            return _ok({"runs": [run.as_dict() for run in runs]})

        if method == "POST" and route == "/kernel/runs":
            _verify_mutation_lease("run_checkpoints:start", body, actor=actor, config=config)
            run = start_run(
                owner_role=str(body.get("owner_role") or actor.role_id or actor.actor_id),
                objective=_required_str(body, "objective"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                idempotency_key=_optional_str(body, "idempotency_key"),
                run_id=_optional_str(body, "run_id"),
                log_path=config.transition_log,
            )
            return _ok({"run": run.as_dict()}, status=201)

        if method == "GET" and len(parts) == 3 and parts[:2] == ["kernel", "runs"]:
            try:
                run = get_run(parts[2], log_path=config.transition_log)
            except KeyError:
                return _error(404, f"run not found: {parts[2]}")
            return _ok({"run": run.as_dict()})

        if (
            method == "GET"
            and len(parts) == 4
            and parts[:2] == ["kernel", "runs"]
            and parts[3] == "resume"
        ):
            try:
                summary = resume_summary(parts[2], log_path=config.transition_log)
            except KeyError:
                return _error(404, f"run not found: {parts[2]}")
            return _ok({"summary": summary})

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "runs"]
            and parts[3] == "checkpoints"
        ):
            run_id = parts[2]
            _verify_mutation_lease(f"run:{run_id}", body, actor=actor, config=config)
            event = append_checkpoint(
                run_id,
                actor=str(body.get("actor") or actor.actor_id),
                step_id=_required_str(body, "step_id"),
                status=_required_str(body, "status"),
                summary=_required_str(body, "summary"),
                payload_ref=_optional_str(body, "payload_ref"),
                side_effect_key=_optional_str(body, "side_effect_key"),
                log_path=config.transition_log,
            )
            return _ok({"event": event}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "runs"]
            and parts[3] == "state"
        ):
            run_id = parts[2]
            _verify_mutation_lease(f"run:{run_id}", body, actor=actor, config=config)
            event = set_run_state(
                run_id,
                actor=str(body.get("actor") or actor.actor_id),
                state=_required_str(body, "state"),
                failure_reason=_optional_str(body, "failure_reason"),
                log_path=config.transition_log,
            )
            return _ok({"event": event})

        if method == "POST" and route == "/kernel/operating-units":
            _verify_mutation_lease("operating_units:define", body, actor=actor, config=config)
            unit = define_operating_unit(
                unit_id=_required_str(body, "unit_id"),
                unit_kind=_required_str(body, "unit_kind"),
                display_name=_required_str(body, "display_name"),
                owner_role=_required_str(body, "owner_role"),
                input_kinds=_list_str(body.get("input_kinds")),
                allowed_work_kinds=_list_str(body.get("allowed_work_kinds")),
                allowed_exits=_list_str(body.get("allowed_exits")),
                worker_roles=_list_str(body.get("worker_roles")),
                worker_role_classes=dict(body.get("worker_role_classes") or {}),
                worker_role_archetypes=dict(body.get("worker_role_archetypes") or {}),
                sla=dict(body.get("sla") or {}),
                operator_required_when=_list_str(body.get("operator_required_when")),
                governance_required_for=_list_str(body.get("governance_required_for")),
                status=str(body.get("status") or "active"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                metadata=dict(body.get("metadata") or {}),
                log_path=config.operating_units_log,
            )
            return _ok({"operating_unit": unit.as_dict()}, status=201)

        if method == "POST" and route == "/kernel/work-items":
            _verify_mutation_lease("work_items:enqueue", body, actor=actor, config=config)
            item = enqueue_work_item(
                unit_id=_required_str(body, "unit_id"),
                kind=_required_str(body, "kind"),
                payload=dict(body.get("payload") or {}),
                priority=int(body.get("priority") or 0),
                max_attempts=int(body.get("max_attempts") or DEFAULT_MAX_ATTEMPTS),
                owner_role=_optional_str(body, "owner_role"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                idempotency_key=_optional_str(body, "idempotency_key"),
                metadata=dict(body.get("metadata") or {}),
                actor=str(body.get("actor") or actor.actor_id),
                log_path=config.work_items_log,
                operating_units_log=config.operating_units_log,
                kernel_events_log=config.kernel_events_log,
            )
            return _ok({"work_item": item.as_dict()}, status=201)

        if method == "POST" and route == "/kernel/work-items/claim-next":
            _verify_mutation_lease("work_items:claim", body, actor=actor, config=config)
            item = claim_next_work_item(
                unit_id=_required_str(body, "unit_id"),
                actor=str(body.get("actor") or actor.actor_id),
                role_id=actor.role_id or _optional_str(body, "role_id"),
                kind=_optional_str(body, "kind"),
                lease_seconds=int(body.get("lease_seconds") or DEFAULT_LEASE_SECONDS),
                log_path=config.work_items_log,
                operating_units_log=config.operating_units_log,
                kernel_events_log=config.kernel_events_log,
            )
            return _ok({"work_item": item.as_dict() if item else None})

        if method == "GET" and route == "/kernel/work-items":
            items = list_work_items(
                unit_id=query.get("unit_id", [None])[0],
                status=query.get("status", [None])[0],
                kind=query.get("kind", [None])[0],
                tenant_id=query.get("tenant_id", [None])[0],
                project_id=query.get("project_id", [None])[0],
                log_path=config.work_items_log,
            )
            if _query_bool(query, "resource"):
                return _ok(
                    {"work_items": [work_item_resource(item).as_dict() for item in items]}
                )
            return _ok({"work_items": [item.as_dict() for item in items]})

        if method == "GET" and len(parts) == 3 and parts[:2] == ["kernel", "work-items"]:
            item = get_work_item(parts[2], log_path=config.work_items_log)
            if item is None:
                return _error(404, f"work item not found: {parts[2]}")
            payload = work_item_resource(item).as_dict() if _query_bool(query, "resource") else item.as_dict()
            return _ok({"work_item": payload})

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "work-items"]
        ):
            work_id = parts[2]
            action = parts[3]
            _verify_mutation_lease(f"work_item:{work_id}", body, actor=actor, config=config)
            worker = str(body.get("actor") or actor.actor_id)
            if action == "claim":
                item = claim_work_item(
                    work_id,
                    actor=worker,
                    role_id=actor.role_id or _optional_str(body, "role_id"),
                    lease_seconds=int(body.get("lease_seconds") or DEFAULT_LEASE_SECONDS),
                    log_path=config.work_items_log,
                    operating_units_log=config.operating_units_log,
                    kernel_events_log=config.kernel_events_log,
                )
            elif action == "start":
                item = start_work_item(
                    work_id,
                    actor=worker,
                    claim_token=_required_int(body, "claim_token"),
                    log_path=config.work_items_log,
                    kernel_events_log=config.kernel_events_log,
                )
            elif action == "heartbeat":
                item = heartbeat_work_item(
                    work_id,
                    actor=worker,
                    claim_token=_required_int(body, "claim_token"),
                    lease_seconds=int(body.get("lease_seconds") or DEFAULT_LEASE_SECONDS),
                    log_path=config.work_items_log,
                    kernel_events_log=config.kernel_events_log,
                )
            elif action == "complete":
                item = complete_work_item(
                    work_id,
                    actor=worker,
                    claim_token=_required_int(body, "claim_token"),
                    exit_kind=_required_str(body, "exit_kind"),
                    result=str(body.get("result") or "pass"),
                    producer=_optional_str(body, "producer"),
                    verifier=_optional_str(body, "verifier"),
                    artifact_refs=body.get("artifact_refs"),
                    log_path=config.work_items_log,
                    operating_units_log=config.operating_units_log,
                    kernel_events_log=config.kernel_events_log,
                )
            elif action == "fail":
                item = fail_work_item(
                    work_id,
                    actor=worker,
                    claim_token=_required_int(body, "claim_token"),
                    reason=_required_str(body, "reason"),
                    retryable=bool(body.get("retryable", True)),
                    log_path=config.work_items_log,
                    kernel_events_log=config.kernel_events_log,
                )
            elif action == "retire":
                item = retire_work_item(
                    work_id,
                    actor=worker,
                    reason=_required_str(body, "reason"),
                    log_path=config.work_items_log,
                    kernel_events_log=config.kernel_events_log,
                )
            elif action == "requeue":
                item = requeue_dead_letter(
                    work_id,
                    actor=worker,
                    reset_attempts=bool(body.get("reset_attempts", True)),
                    log_path=config.work_items_log,
                    kernel_events_log=config.kernel_events_log,
                )
            else:
                return _error(404, f"unknown work-item action: {action}")
            return _ok({"work_item": item.as_dict()})

        # --- learning events: approved learning replay and encounter telemetry ---
        if method == "GET" and route == "/kernel/learning-events/summary":
            summary = summarize_learning_events(
                tenant_id=query.get("tenant_id", [None])[0],
                project_id=query.get("project_id", [None])[0],
                log_path=config.learning_events_log,
                encounters_log_path=config.learning_encounters_log,
                outcome_links_log_path=config.outcome_links_log,
                routine_reviews_log_path=config.routine_reviews_log,
            )
            return _ok({"summary": summary.as_dict()})

        if method == "GET" and route == "/kernel/learning-transition-candidates":
            payload = _learning_transition_candidates_payload(
                config,
                source=str(query.get("source", ["all"])[0] or "all"),
                include_closed=_query_bool(query, "include_closed"),
            )
            return _ok(payload)

        if method == "POST" and route == "/kernel/learning-events":
            learning_unit_kind = _required_str(body, "learning_unit_kind")
            approval_ref = _required_str(body, "approval_ref")
            _verify_mutation_lease(
                f"learning_event:{learning_unit_kind}:{approval_ref}",
                body,
                actor=actor,
                config=config,
            )
            event = create_learning_event(
                learning_unit_kind=learning_unit_kind,
                decision_use=_required_str(body, "decision_use"),
                future_application_cue=_required_str(body, "future_application_cue"),
                approved_by=str(body.get("approved_by") or actor.role_id or actor.actor_id),
                approval_ref=approval_ref,
                source_carrier_refs=_list_str(body.get("source_carrier_refs")),
                derived_from_learning_event_ids=_list_str(
                    body.get("derived_from_learning_event_ids")
                ),
                candidate_ref=_optional_str(body, "candidate_ref"),
                before_state=_optional_str(body, "before_state"),
                after_state=_optional_str(body, "after_state"),
                owner_role=_optional_str(body, "owner_role"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                externality_review_ref=_optional_str(body, "externality_review_ref"),
                review_after_utc=_optional_str(body, "review_after_utc"),
                metadata=dict(body.get("metadata") or {}),
                learning_event_id=_optional_str(body, "learning_event_id"),
                log_path=config.learning_events_log,
            )
            return _ok({"learning_event": event.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "learning-transition-candidates"]
            and parts[3] == "governance-change"
        ):
            from cognitive_firm.orchestration.governance_changes import (
                governance_change_from_candidate,
            )

            candidate_id = parts[2]
            _verify_mutation_lease(
                f"learning_transition_candidate:{candidate_id}:governance_change",
                body,
                actor=actor,
                config=config,
            )
            candidate = _find_learning_transition_candidate(
                config,
                candidate_id=candidate_id,
                source=str(body.get("source") or "all"),
                include_closed=bool(body.get("include_closed", False)),
            )
            if candidate is None:
                return _error(404, f"learning transition candidate not found: {candidate_id}")
            proposal = governance_change_from_candidate(
                candidate,
                target_ref=_required_str(body, "target_ref"),
                proposed_by=str(body.get("proposed_by") or actor.actor_id),
                change_kind=_optional_str(body, "change_kind"),
                title=_optional_str(body, "title"),
                expected_behavior_change=_optional_str(body, "expected_behavior_change"),
                predicted_effect=(
                    dict(body.get("predicted_effect"))
                    if isinstance(body.get("predicted_effect"), dict)
                    else None
                ),
                risk_summary=_optional_str(body, "risk_summary"),
                rollback_plan=_optional_str(body, "rollback_plan"),
                owner_role=_optional_str(body, "owner_role"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                invariant_checks=_governance_invariant_checks_from_body(body),
                metadata=dict(body.get("metadata") or {}),
                proposal_id=_optional_str(body, "proposal_id"),
                log_path=_governance_changes_log(config),
            )
            return _ok({"proposal": proposal.as_dict()}, status=201)

        if method == "GET" and route == "/kernel/learning-events/replay":
            events = replay_learning_events(
                role=query.get("role", [None])[0],
                tenant_id=query.get("tenant_id", [None])[0],
                project_id=query.get("project_id", [None])[0],
                cue=query.get("cue", [None])[0],
                source_ref=query.get("source_ref", [None])[0],
                tag=query.get("tag", [None])[0],
                log_path=config.learning_events_log,
            )
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "learning_events": [
                            learning_event_resource(event).as_dict() for event in events
                        ]
                    }
                )
            return _ok({"learning_events": [event.as_dict() for event in events]})

        if method == "GET" and route == "/kernel/work-discovery":
            try:
                max_per_source = _query_optional_int(query, "max_per_source", default=5)
            except ValueError as exc:
                return _error(400, str(exc))
            assigned_to = (
                query.get("assigned_to", [None])[0]
                or query.get("role", [None])[0]
            )
            return _ok(
                build_role_learning_context(
                    assigned_to=assigned_to,
                    tenant_id=query.get("tenant_id", [None])[0],
                    project_id=query.get("project_id", [None])[0],
                    cue=query.get("cue", [None])[0],
                    max_per_source=max_per_source or 5,
                    include_work_candidates=not _query_bool(query, "learning_only"),
                    learning_events_log_path=config.learning_events_log,
                    outcome_links_log_path=config.outcome_links_log,
                    routine_reviews_log_path=config.routine_reviews_log,
                )
            )

        if method == "GET" and route == "/kernel/learning-events":
            events = list_learning_events(
                status=query.get("status", [None])[0],
                learning_unit_kind=query.get("learning_unit_kind", [None])[0],
                tenant_id=query.get("tenant_id", [None])[0],
                project_id=query.get("project_id", [None])[0],
                log_path=config.learning_events_log,
            )
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "learning_events": [
                            learning_event_resource(event).as_dict() for event in events
                        ]
                    }
                )
            return _ok({"learning_events": [event.as_dict() for event in events]})

        if method == "POST" and route == "/kernel/learning-event-encounters":
            learning_event_id = _required_str(body, "learning_event_id")
            if not any(
                event.learning_event_id == learning_event_id
                for event in list_learning_events(log_path=config.learning_events_log)
            ):
                return _error(404, f"learning event not found: {learning_event_id}")
            _verify_mutation_lease(
                f"learning_event:{learning_event_id}:encounter",
                body,
                actor=actor,
                config=config,
            )
            encounter = record_learning_event_encounter(
                learning_event_id=learning_event_id,
                role=str(body.get("role") or actor.role_id or actor.actor_id),
                cue=_required_str(body, "cue"),
                outcome=str(body.get("outcome") or "encountered"),
                work_ref=_optional_str(body, "work_ref"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                reason=_optional_str(body, "reason"),
                evidence_refs=_list_str(body.get("evidence_refs")),
                metadata=dict(body.get("metadata") or {}),
                idempotency_key=_optional_str(body, "idempotency_key"),
                log_path=config.learning_encounters_log,
            )
            return _ok({"encounter": encounter.as_dict()}, status=201)

        # --- outcome links: did an approved change improve a measured outcome? ---
        if method == "GET" and route == "/kernel/outcome-links/summary":
            summary = summarize_outcome_links(
                tenant_id=query.get("tenant_id", [None])[0],
                project_id=query.get("project_id", [None])[0],
                log_path=config.outcome_links_log,
            )
            return _ok({"summary": summary.as_dict()})

        if method == "GET" and route == "/kernel/outcome-links":
            links = list_outcome_links(
                status=query.get("status", [None])[0],
                verdict=query.get("verdict", [None])[0],
                learning_event_id=query.get("learning_event_id", [None])[0],
                log_path=config.outcome_links_log,
            )
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "outcome_links": [
                            outcome_link_resource(link).as_dict() for link in links
                        ]
                    }
                )
            return _ok({"outcome_links": [link.as_dict() for link in links]})

        if method == "POST" and route == "/kernel/outcome-links":
            _verify_mutation_lease("outcome_links:create", body, actor=actor, config=config)
            link = create_outcome_link(
                change_ref=_required_str(body, "change_ref"),
                change_kind=_required_str(body, "change_kind"),
                metric_name=_required_str(body, "metric_name"),
                metric_unit=_required_str(body, "metric_unit"),
                created_by=str(body.get("created_by") or actor.actor_id),
                learning_event_id=_optional_str(body, "learning_event_id"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                owner_role=_optional_str(body, "owner_role"),
                direction=_optional_str(body, "direction"),
                metadata=dict(body.get("metadata") or {}),
                actor=str(body.get("actor") or actor.actor_id),
                log_path=config.outcome_links_log,
                kernel_events_log=config.kernel_events_log,
            )
            return _ok({"outcome_link": link.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "outcome-links"]
        ):
            link_id = parts[2]
            action = parts[3]
            lease_resource = (
                "routine_reviews:schedule"
                if action == "reversal-review"
                else f"outcome_link:{link_id}"
            )
            _verify_mutation_lease(lease_resource, body, actor=actor, config=config)
            if action == "snapshots":
                link = record_metric_snapshot(
                    link_id,
                    kind=_required_str(body, "kind"),
                    value=_required_number(body, "value"),
                    captured_by=str(body.get("captured_by") or actor.actor_id),
                    captured_at_utc=_optional_str(body, "captured_at_utc"),
                    sample_size=body.get("sample_size"),
                    measurement_ref=_optional_str(body, "measurement_ref"),
                    note=_optional_str(body, "note"),
                    actor=str(body.get("actor") or actor.actor_id),
                    log_path=config.outcome_links_log,
                    kernel_events_log=config.kernel_events_log,
                )
            elif action == "verdict":
                link = record_verdict(
                    link_id,
                    verdict=_required_str(body, "verdict"),
                    recorded_by=str(body.get("recorded_by") or actor.actor_id),
                    rationale=_required_str(body, "rationale"),
                    actor=str(body.get("actor") or actor.actor_id),
                    log_path=config.outcome_links_log,
                    kernel_events_log=config.kernel_events_log,
                )
            elif action == "void":
                link = void_outcome_link(
                    link_id,
                    reason=_required_str(body, "reason"),
                    actor=str(body.get("actor") or actor.actor_id),
                    log_path=config.outcome_links_log,
                    kernel_events_log=config.kernel_events_log,
                )
            elif action == "reversal-review":
                source_link = get_outcome_link(link_id, log_path=config.outcome_links_log)
                if source_link is None:
                    return _error(404, f"outcome link not found: {link_id}")
                require_failed_prediction = True
                if "require_failed_prediction" in body:
                    require_failed_prediction = _payload_bool(body, "require_failed_prediction")
                request = build_predicted_mutation_reversal_review_request(
                    PredictedMutationReversalReviewInput(
                        outcome_link=source_link.as_dict(),
                        review_due_utc=_required_str(body, "review_due_utc"),
                        scheduled_by=str(body.get("scheduled_by") or actor.actor_id),
                        review_id=_optional_str(body, "review_id"),
                        tenant_id=_optional_str(body, "tenant_id"),
                        project_id=_optional_str(body, "project_id"),
                        metadata=dict(body.get("metadata") or {}),
                        require_failed_prediction=require_failed_prediction,
                    )
                )
                review = schedule_routine_review(
                    routine_ref=_required_str(request, "routine_ref"),
                    routine_kind=_required_str(request, "routine_kind"),
                    review_due_utc=_required_str(request, "review_due_utc"),
                    scheduled_by=_required_str(request, "scheduled_by"),
                    learning_event_id=_optional_str(request, "learning_event_id"),
                    tenant_id=_optional_str(request, "tenant_id"),
                    project_id=_optional_str(request, "project_id"),
                    reason=_optional_str(request, "reason"),
                    review_cadence=_optional_str(request, "review_cadence"),
                    metadata=dict(request.get("metadata") or {}),
                    actor=str(body.get("actor") or actor.actor_id),
                    log_path=config.routine_reviews_log,
                    kernel_events_log=config.kernel_events_log,
                )
                return _ok(
                    {
                        "routine_review": review.as_dict(),
                        "source_outcome_link": source_link.as_dict(),
                    },
                    status=201,
                )
            else:
                return _error(404, f"unknown outcome-link action: {action}")
            return _ok({"outcome_link": link.as_dict()})

        # --- routine reviews: scheduled review and retirement of stale routines ---
        if method == "GET" and route == "/kernel/routine-reviews":
            reviews = list_routine_reviews(
                status=query.get("status", [None])[0],
                routine_kind=query.get("routine_kind", [None])[0],
                learning_event_id=query.get("learning_event_id", [None])[0],
                routine_ref=query.get("routine_ref", [None])[0],
                tenant_id=query.get("tenant_id", [None])[0],
                project_id=query.get("project_id", [None])[0],
                log_path=config.routine_reviews_log,
            )
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "routine_reviews": [
                            routine_review_resource(review).as_dict() for review in reviews
                        ]
                    }
                )
            return _ok({"routine_reviews": [review.as_dict() for review in reviews]})

        if method == "GET" and route == "/kernel/routine-reviews/due":
            due = list_due_reviews(log_path=config.routine_reviews_log)
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "due_reviews": [
                            routine_review_resource(review).as_dict() for review in due
                        ]
                    }
                )
            return _ok({"due_reviews": [review.as_dict() for review in due]})

        if method == "GET" and route == "/kernel/routine-reviews/summary":
            summary = summarize_routine_reviews(log_path=config.routine_reviews_log)
            return _ok({"summary": summary.as_dict()})

        if method == "POST" and route == "/kernel/routine-reviews":
            _verify_mutation_lease("routine_reviews:schedule", body, actor=actor, config=config)
            review = schedule_routine_review(
                routine_ref=_required_str(body, "routine_ref"),
                routine_kind=_required_str(body, "routine_kind"),
                review_due_utc=_required_str(body, "review_due_utc"),
                scheduled_by=str(body.get("scheduled_by") or actor.actor_id),
                learning_event_id=_optional_str(body, "learning_event_id"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                reason=_optional_str(body, "reason"),
                review_cadence=_optional_str(body, "review_cadence"),
                metadata=dict(body.get("metadata") or {}),
                actor=str(body.get("actor") or actor.actor_id),
                log_path=config.routine_reviews_log,
                kernel_events_log=config.kernel_events_log,
            )
            return _ok({"routine_review": review.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "routine-reviews"]
        ):
            review_id = parts[2]
            action = parts[3]
            _verify_mutation_lease(f"routine_review:{review_id}", body, actor=actor, config=config)
            if action == "start":
                review = start_routine_review(
                    review_id,
                    reviewer=str(body.get("reviewer") or actor.actor_id),
                    log_path=config.routine_reviews_log,
                    kernel_events_log=config.kernel_events_log,
                )
            elif action == "record-outcome":
                review = record_review_outcome(
                    review_id,
                    outcome=_required_str(body, "outcome"),
                    reviewer=str(body.get("reviewer") or actor.actor_id),
                    rationale=_required_str(body, "rationale"),
                    evidence_refs=_list_str(body.get("evidence_refs")),
                    next_review_due_utc=_optional_str(body, "next_review_due_utc"),
                    next_review_cadence=_optional_str(body, "next_review_cadence"),
                    log_path=config.routine_reviews_log,
                    kernel_events_log=config.kernel_events_log,
                )
            elif action == "retire":
                review = retire_routine(
                    review_id,
                    retired_by=str(body.get("retired_by") or actor.actor_id),
                    reason=_required_str(body, "reason"),
                    log_path=config.routine_reviews_log,
                    kernel_events_log=config.kernel_events_log,
                )
            else:
                return _error(404, f"unknown routine-review action: {action}")
            return _ok({"routine_review": review.as_dict()})

        # --- resource allocation: governed capacity moves across operating units ---
        if (
            method == "GET"
            and len(parts) == 3
            and parts[:2] == ["kernel", "allocation-ledger"]
        ):
            resource_kind = parts[2]
            return _ok(
                {
                    "ledger": current_allocation(
                        resource_kind, log_path=config.resource_allocation_log
                    ),
                    "summary": allocation_summary(
                        resource_kind, log_path=config.resource_allocation_log
                    ),
                }
            )

        if method == "GET" and route == "/kernel/allocation-decisions":
            decisions = list_allocation_decisions(
                resource_kind=query.get("resource_kind", [None])[0],
                unit_id=query.get("unit_id", [None])[0],
                status=query.get("status", [None])[0],
                log_path=config.resource_allocation_log,
            )
            return _ok({"allocation_decisions": [d.as_dict() for d in decisions]})

        if method == "POST" and route == "/kernel/allocation-decisions":
            _verify_mutation_lease("resource_allocation:record", body, actor=actor, config=config)
            decision = record_allocation_decision(
                resource_kind=_required_str(body, "resource_kind"),
                from_unit=_required_str(body, "from_unit"),
                to_unit=_required_str(body, "to_unit"),
                amount=_required_number(body, "amount"),
                deciding_role=_required_str(body, "deciding_role"),
                deciding_actor=str(body.get("deciding_actor") or actor.actor_id),
                authority_basis=_required_str(body, "authority_basis"),
                rationale=_required_str(body, "rationale"),
                effective_from_utc=_optional_str(body, "effective_from_utc"),
                effective_until_utc=_optional_str(body, "effective_until_utc"),
                outcome_link_ids=_list_str(body.get("outcome_link_ids")),
                change_refs=_list_str(body.get("change_refs")),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                metadata=dict(body.get("metadata") or {}),
                actor=str(body.get("actor") or actor.actor_id),
                log_path=config.resource_allocation_log,
                kernel_events_log=config.kernel_events_log,
            )
            return _ok({"allocation_decision": decision.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "allocation-decisions"]
        ):
            decision_id = parts[2]
            action = parts[3]
            _verify_mutation_lease(
                f"allocation_decision:{decision_id}", body, actor=actor, config=config
            )
            if action == "apply":
                decision = apply_allocation_decision(
                    decision_id,
                    actor=str(body.get("actor") or actor.actor_id),
                    log_path=config.resource_allocation_log,
                    kernel_events_log=config.kernel_events_log,
                )
            elif action == "revert":
                decision = revert_allocation_decision(
                    decision_id,
                    actor=str(body.get("actor") or actor.actor_id),
                    reason=_required_str(body, "reason"),
                    log_path=config.resource_allocation_log,
                    kernel_events_log=config.kernel_events_log,
                )
            else:
                return _error(404, f"unknown allocation-decision action: {action}")
            return _ok({"allocation_decision": decision.as_dict()})

        # --- decision aggregation: procedure evidence, not authority ---
        if method == "GET" and route == "/kernel/decision-procedure-profiles":
            return _ok(
                {
                    "decision_procedure_profiles": [
                        profile.as_dict()
                        for profile in list_decision_procedure_profiles()
                    ]
                }
            )

        if method == "GET" and route == "/kernel/decision-aggregation-cases":
            cases = list_decision_aggregation_cases(
                status=query.get("status", [None])[0],
                procedure_kind=query.get("procedure_kind", [None])[0],
                subject_ref=query.get("subject_ref", [None])[0],
                log_path=config.decision_aggregation_log,
            )
            if _query_bool(query, "resource"):
                return _ok(
                    {
                        "decision_aggregation_cases": [
                            decision_aggregation_case_resource(case).as_dict()
                            for case in cases
                        ]
                    }
                )
            return _ok({"decision_aggregation_cases": [case.as_dict() for case in cases]})

        if method == "POST" and route == "/kernel/decision-aggregation-cases":
            _verify_mutation_lease("decision_aggregation:open", body, actor=actor, config=config)
            common = {
                "subject_ref": _required_str(body, "subject_ref"),
                "decision_class": _required_str(body, "decision_class"),
                "scope_kind": _required_str(body, "scope_kind"),
                "scope_ref": _required_str(body, "scope_ref"),
                "opened_by": str(body.get("opened_by") or actor.actor_id),
                "eligibility_basis": _required_str(body, "eligibility_basis"),
                "eligible_roles": _list_str(body.get("eligible_roles")),
                "eligible_actors": _list_str(body.get("eligible_actors")),
                "tie_breaker_role": _optional_str(body, "tie_breaker_role"),
                "downstream_ref": _optional_str(body, "downstream_ref"),
                "tenant_id": _optional_str(body, "tenant_id"),
                "project_id": _optional_str(body, "project_id"),
                "evidence_refs": _list_str(body.get("evidence_refs")),
                "metadata": dict(body.get("metadata") or {}),
                "case_id": _optional_str(body, "case_id"),
                "log_path": config.decision_aggregation_log,
            }
            if body.get("procedure_profile"):
                case = open_decision_aggregation_case_from_profile(
                    procedure_profile=_required_str(body, "procedure_profile"),
                    quorum=int(body["quorum"]) if body.get("quorum") is not None else None,
                    **common,
                )
            else:
                case = open_decision_aggregation_case(
                    procedure_kind=_required_str(body, "procedure_kind"),
                    quorum=int(body.get("quorum") or 1),
                    **common,
                )
            return _ok({"decision_aggregation_case": case.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "decision-aggregation-cases"]
            and parts[3] == "positions"
        ):
            case_id = parts[2]
            _verify_mutation_lease(
                f"decision_aggregation_case:{case_id}", body, actor=actor, config=config
            )
            case = record_decision_position(
                case_id,
                actor_id=str(body.get("actor_id") or actor.actor_id),
                role_id=_required_str(body, "role_id"),
                position=_required_str(body, "position"),
                rationale=_required_str(body, "rationale"),
                evidence_refs=_list_str(body.get("evidence_refs")),
                metadata=dict(body.get("metadata") or {}),
                position_id=_optional_str(body, "position_id"),
                log_path=config.decision_aggregation_log,
            )
            return _ok({"decision_aggregation_case": case.as_dict()})

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "decision-aggregation-cases"]
            and parts[3] == "compute"
        ):
            case_id = parts[2]
            _verify_mutation_lease(
                f"decision_aggregation_case:{case_id}", body, actor=actor, config=config
            )
            case = compute_decision_aggregation_case(
                case_id,
                log_path=config.decision_aggregation_log,
            )
            return _ok({"decision_aggregation_case": case.as_dict()})

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "decision-aggregation-cases"]
            and parts[3] == "route-escalation"
        ):
            case_id = parts[2]
            _verify_mutation_lease(
                f"decision_aggregation_case:{case_id}:route_escalation",
                body,
                actor=actor,
                config=config,
            )
            case = get_decision_aggregation_case(
                case_id,
                log_path=config.decision_aggregation_log,
            )
            if case.status != "escalated" or not case.result:
                return _error(
                    400,
                    "decision aggregation case must be escalated before routing",
                )
            result = case.result.as_dict()
            source_ref = f"decision_aggregation_case:{case.case_id}"
            evidence_refs = _dedupe_strs(
                [
                    source_ref,
                    case.subject_ref,
                    *case.evidence_refs,
                    *result.get("evidence_refs", []),
                    *_list_str(body.get("evidence_refs")),
                ]
            )
            signal_kind = str(body.get("signal_kind") or "evidence_gap")
            summary = _optional_str(body, "summary") or (
                "Decision aggregation escalated for "
                f"{case.subject_ref}: {result.get('rationale', 'no rationale')}"
            )
            severity = str(body.get("severity") or "blocking")
            routed_payload = _route_execution_evidence_payload(
                {
                    "signal_kind": signal_kind,
                    "source_ref": source_ref,
                    "summary": summary,
                    "owner_role": str(
                        body.get("owner_role")
                        or case.opened_by
                        or actor.role_id
                        or actor.actor_id
                    ),
                    "severity": severity,
                    "worker_ref": _optional_str(body, "worker_ref"),
                    "run_id": _optional_str(body, "run_id"),
                    "work_id": _optional_str(body, "work_id"),
                    "tenant_id": _optional_str(body, "tenant_id") or case.tenant_id,
                    "project_id": _optional_str(body, "project_id") or case.project_id,
                    "capability_ref": _optional_str(body, "capability_ref"),
                    "threshold_ref": _optional_str(body, "threshold_ref"),
                    "recommended_route": _optional_str(body, "recommended_route")
                    or "open_learning_candidate",
                    "route_kind": _optional_str(body, "route_kind")
                    or "open_learning_candidate",
                    "route_target_ref": _optional_str(body, "route_target_ref"),
                    "route_rationale": _optional_str(body, "route_rationale")
                    or summary,
                    "routed_by": _optional_str(body, "routed_by")
                    or actor.role_id
                    or actor.actor_id,
                    "counts_as_failure": bool(body.get("counts_as_failure", True)),
                    "evidence_refs": evidence_refs,
                    "metadata": {
                        **dict(body.get("metadata") or {}),
                        "source_route": "decision_aggregation_escalation.v1",
                        "decision_case_id": case.case_id,
                        "decision_class": case.decision_class,
                        "procedure_kind": case.procedure_kind,
                        "recommendation": result.get("recommendation"),
                        "quorum_met": result.get("quorum_met"),
                        "approvals": result.get("approvals"),
                        "rejections": result.get("rejections"),
                        "abstentions": result.get("abstentions"),
                        "recusals": result.get("recusals"),
                        "vetoes": result.get("vetoes"),
                    },
                    "signal_id": _optional_str(body, "signal_id"),
                    "governance_change_target_ref": _optional_str(
                        body, "governance_change_target_ref"
                    ),
                    "governance_change_kind": _optional_str(
                        body, "governance_change_kind"
                    ),
                    "proposed_by": _optional_str(body, "proposed_by")
                    or actor.role_id
                    or actor.actor_id,
                },
                actor=actor,
                config=config,
            )
            return _ok(
                {
                    "decision_aggregation_case": case.as_dict(),
                    **routed_payload,
                    "boundary": {
                        **dict(routed_payload.get("boundary") or {}),
                        "resolved_decision": False,
                        "overrode_aggregation": False,
                    },
                },
                status=201,
            )

        # --- decision rights: residual control rights for incomplete mandates ---
        if method == "GET" and route == "/kernel/residual-rights/holder":
            holder = get_residual_right_holder(
                query.get("scope_kind", [""])[0],
                query.get("scope_ref", [""])[0],
                log_path=config.residual_rights_log,
            )
            return _ok({"holder": holder.as_dict() if holder else None})

        if method == "GET" and route == "/kernel/decision-rights-summary":
            summary = summarize_decision_rights(
                log_path=config.residual_decisions_log,
                assignments_log=config.residual_rights_log,
            )
            return _ok({"summary": summary})

        if method == "POST" and route == "/kernel/residual-rights":
            _verify_mutation_lease("residual_rights:assign", body, actor=actor, config=config)
            assignment = assign_residual_right(
                scope_kind=_required_str(body, "scope_kind"),
                scope_ref=_required_str(body, "scope_ref"),
                holder_role=_required_str(body, "holder_role"),
                basis=_required_str(body, "basis"),
                assigned_by=str(body.get("assigned_by") or actor.actor_id),
                holder_actor=_optional_str(body, "holder_actor"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                metadata=dict(body.get("metadata") or {}),
                log_path=config.residual_rights_log,
                kernel_events_log=config.kernel_events_log,
            )
            return _ok({"residual_right_assignment": assignment.as_dict()}, status=201)

        if method == "POST" and route == "/kernel/residual-decisions":
            _verify_mutation_lease("residual_decisions:record", body, actor=actor, config=config)
            decision = record_residual_decision(
                scope_kind=_required_str(body, "scope_kind"),
                scope_ref=_required_str(body, "scope_ref"),
                deciding_actor=str(body.get("deciding_actor") or actor.actor_id),
                deciding_role=_required_str(body, "deciding_role"),
                decision_summary=_required_str(body, "decision_summary"),
                rationale=_required_str(body, "rationale"),
                tenant_id=_optional_str(body, "tenant_id"),
                project_id=_optional_str(body, "project_id"),
                metadata=dict(body.get("metadata") or {}),
                log_path=config.residual_decisions_log,
                assignments_log=config.residual_rights_log,
                kernel_events_log=config.kernel_events_log,
            )
            return _ok({"residual_decision": decision.as_dict()}, status=201)

        if (
            method == "POST"
            and len(parts) == 4
            and parts[:2] == ["kernel", "residual-decisions"]
            and parts[3] == "review"
        ):
            _verify_mutation_lease(
                f"residual_decision:{parts[2]}", body, actor=actor, config=config
            )
            decision = review_residual_decision(
                parts[2],
                reviewed_by=str(body.get("reviewed_by") or actor.actor_id),
                review_outcome=_required_str(body, "review_outcome"),
                review_notes=_optional_str(body, "review_notes"),
                log_path=config.residual_decisions_log,
                kernel_events_log=config.kernel_events_log,
            )
            return _ok({"residual_decision": decision.as_dict()})

    except KeyError as exc:
        return _error(404, str(exc))
    except (TypeError, ValueError, PermissionError) as exc:
        return _error(400, str(exc))

    return _error(404, f"unknown route: {method} {route}")


def _route_execution_evidence_payload(
    body: dict[str, Any],
    *,
    actor: ActorContext,
    config: KernelServiceConfig,
) -> dict[str, Any]:
    """Compose execution evidence into signal, route, candidate, and proposal.

    Public routes perform their own lease/surface checks before calling this
    helper. Keeping the composition here avoids nested service dispatch and
    therefore avoids requiring two unrelated leases for one service command.
    """

    packet = build_execution_evidence_route_packet(
        ExecutionEvidenceRouteInput(
            signal_kind=_required_str(body, "signal_kind"),
            source_ref=_required_str(body, "source_ref"),
            summary=_required_str(body, "summary"),
            owner_role=str(body.get("owner_role") or actor.role_id or actor.actor_id),
            severity=str(body.get("severity") or "warning"),
            worker_ref=_optional_str(body, "worker_ref"),
            run_id=_optional_str(body, "run_id"),
            work_id=_optional_str(body, "work_id"),
            tenant_id=_optional_str(body, "tenant_id"),
            project_id=_optional_str(body, "project_id"),
            capability_ref=_optional_str(body, "capability_ref"),
            threshold_ref=_optional_str(body, "threshold_ref"),
            recommended_route=_optional_str(body, "recommended_route")
            or "open_learning_candidate",
            route_kind=_optional_str(body, "route_kind") or "open_learning_candidate",
            route_target_ref=_optional_str(body, "route_target_ref"),
            route_rationale=_optional_str(body, "route_rationale"),
            routed_by=_optional_str(body, "routed_by") or actor.role_id or actor.actor_id,
            counts_as_failure=bool(body.get("counts_as_failure", False)),
            evidence_refs=_list_str(body.get("evidence_refs")),
            metadata=dict(body.get("metadata") or {}),
            signal_id=_optional_str(body, "signal_id"),
            governance_change_target_ref=_optional_str(
                body, "governance_change_target_ref"
            ),
            governance_change_kind=_optional_str(body, "governance_change_kind"),
            proposed_by=_optional_str(body, "proposed_by")
            or actor.role_id
            or actor.actor_id,
        )
    )
    signal_body = packet["service_calls"][0]["body"]
    signal = record_capability_signal(
        signal_kind=_required_str(signal_body, "signal_kind"),
        source_ref=_required_str(signal_body, "source_ref"),
        summary=_required_str(signal_body, "summary"),
        owner_role=_required_str(signal_body, "owner_role"),
        severity=str(signal_body.get("severity") or "warning"),
        worker_ref=_optional_str(signal_body, "worker_ref"),
        run_id=_optional_str(signal_body, "run_id"),
        work_id=_optional_str(signal_body, "work_id"),
        tenant_id=_optional_str(signal_body, "tenant_id"),
        project_id=_optional_str(signal_body, "project_id"),
        capability_ref=_optional_str(signal_body, "capability_ref"),
        threshold_ref=_optional_str(signal_body, "threshold_ref"),
        recommended_route=_optional_str(signal_body, "recommended_route"),
        route_target_ref=_optional_str(signal_body, "route_target_ref"),
        counts_as_failure=bool(signal_body.get("counts_as_failure", False)),
        evidence_refs=_list_str(signal_body.get("evidence_refs")),
        metadata=dict(signal_body.get("metadata") or {}),
        signal_id=_optional_str(signal_body, "signal_id"),
        log_path=config.capability_signals_log,
    )
    signal_ref = f"capability_signal:{signal.signal_id}"
    routed_signal = signal
    route_call = next(
        (
            call
            for call in packet["service_calls"]
            if call["label"] == "route_capability_signal"
        ),
        None,
    )
    if route_call is not None:
        route_body = route_call["body"]
        routed_signal = route_capability_signal(
            signal.signal_id,
            route_kind=_required_str(route_body, "route_kind"),
            routed_by=str(route_body.get("routed_by") or actor.actor_id),
            rationale=_required_str(route_body, "rationale"),
            target_ref=_optional_str(route_body, "target_ref"),
            log_path=config.capability_signals_log,
        )

    candidates_payload = _learning_transition_candidates_payload(
        config,
        source="capability",
        include_closed=False,
    )
    matching_candidates = [
        candidate
        for candidate in candidates_payload["candidates"]
        if signal_ref in list(candidate.get("source_refs") or [])
    ]
    candidate = matching_candidates[0] if matching_candidates else None
    proposal = None
    if candidate is not None and _optional_str(body, "governance_change_target_ref"):
        from cognitive_firm.orchestration.governance_changes import (
            governance_change_from_candidate,
        )

        proposal_body = next(
            (
                call["body"]
                for call in packet["service_calls"]
                if call["label"] == "open_governance_change_from_candidate"
            ),
            {},
        )
        proposal = governance_change_from_candidate(
            candidate,
            target_ref=_required_str(proposal_body, "target_ref"),
            proposed_by=str(
                proposal_body.get("proposed_by")
                or body.get("proposed_by")
                or actor.actor_id
            ),
            change_kind=_optional_str(proposal_body, "change_kind"),
            expected_behavior_change=_optional_str(
                proposal_body, "expected_behavior_change"
            ),
            risk_summary=_optional_str(proposal_body, "risk_summary"),
            metadata=dict(proposal_body.get("metadata") or {}),
            tenant_id=_optional_str(body, "tenant_id"),
            project_id=_optional_str(body, "project_id"),
            log_path=_governance_changes_log(config),
        )

    return {
        "route_packet": packet,
        "signal": routed_signal.as_dict(),
        "learning_candidate": candidate,
        "proposal": proposal.as_dict() if proposal else None,
        "resolved_refs": {
            "signal_ref": signal_ref,
            "learning_candidate_ref": (
                f"learning_transition_candidate:{candidate['candidate_id']}"
                if candidate
                else None
            ),
            "proposal_ref": (
                f"governance_change:{proposal.proposal_id}" if proposal else None
            ),
        },
        "boundary": {
            "approved_governance": False,
            "mutated_files": False,
            "executed_runtime": False,
        },
    }


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    config: KernelServiceConfig | None = None,
) -> None:
    """Run the local kernel service until interrupted."""

    server = make_kernel_server(host=host, port=port, config=config)
    server.serve_forever()


def make_kernel_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    config: KernelServiceConfig | None = None,
) -> ThreadingHTTPServer:
    """Create a local kernel HTTP server without starting its event loop."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._send(
                dispatch_kernel_request(
                    "GET",
                    self.path,
                    config=config,
                    headers={key: value for key, value in self.headers.items()},
                )
            )

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("content-length") or "0")
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                payload = json.loads(raw or "{}")
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                response = dispatch_kernel_request(
                    "POST",
                    self.path,
                    payload,
                    config=config,
                    headers={key: value for key, value in self.headers.items()},
                )
            except Exception as exc:  # noqa: BLE001
                response = _error(400, str(exc))
            self._send(response)

        def _send(self, response: KernelServiceResponse) -> None:
            data = json.dumps(response.payload, sort_keys=True).encode("utf-8")
            self.send_response(response.status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    return ThreadingHTTPServer((host, port), Handler)


def _create_human_work_from_payload(
    payload: dict[str, Any],
    *,
    config: KernelServiceConfig,
):
    if payload.get("coordination_pattern") == "a2h_work_request":
        return create_agent_requested_human_work_session(
            requested_by_role=_required_str(payload, "requested_by"),
            human_actor=_required_str(payload, "human_actor"),
            objective=_required_str(payload, "objective"),
            work_mode=str(payload.get("work_mode") or "other"),
            bottleneck_class=str(payload.get("bottleneck_class") or "other"),
            human_deliverable=_required_str(payload, "human_deliverable"),
            tenant_id=_optional_str(payload, "tenant_id"),
            project_id=_optional_str(payload, "project_id"),
            collaborating_roles=_list_str(payload.get("collaborating_roles")),
            artifact_refs=_list_str(payload.get("artifact_refs")),
            observability=str(payload.get("observability") or "human_attested"),
            receipt_required=bool(payload.get("receipt_required", True)),
            receipt_type=str(payload.get("receipt_type") or "note"),
            confidence=str(payload.get("confidence") or "medium"),
            sample_for_review=bool(payload.get("sample_for_review")),
            obligation_id=_optional_str(payload, "obligation_id"),
            deadline_utc=_optional_str(payload, "deadline_utc"),
            interaction_surface=str(payload.get("interaction_surface") or "mixed"),
            agent_followup_ref=_optional_str(payload, "agent_followup_ref"),
            metadata=dict(payload.get("metadata") or {}),
            log_path=config.human_work_log,
        )
    return create_human_work_session(
        requested_by=_required_str(payload, "requested_by"),
        human_actor=_required_str(payload, "human_actor"),
        objective=_required_str(payload, "objective"),
        work_mode=str(payload.get("work_mode") or "other"),
        bottleneck_class=str(payload.get("bottleneck_class") or "other"),
        tenant_id=_optional_str(payload, "tenant_id"),
        project_id=_optional_str(payload, "project_id"),
        collaborating_roles=_list_str(payload.get("collaborating_roles")),
        artifact_refs=_list_str(payload.get("artifact_refs")),
        observability=str(payload.get("observability") or "human_attested"),
        receipt_required=bool(payload.get("receipt_required")),
        receipt_type=str(payload.get("receipt_type") or "none"),
        receipt=_optional_str(payload, "receipt"),
        confidence=str(payload.get("confidence") or "medium"),
        sample_for_review=bool(payload.get("sample_for_review")),
        obligation_id=_optional_str(payload, "obligation_id"),
        deadline_utc=_optional_str(payload, "deadline_utc"),
        interaction_surface=str(payload.get("interaction_surface") or "mixed"),
        agent_counterparty_role=_optional_str(payload, "agent_counterparty_role"),
        human_deliverable=_optional_str(payload, "human_deliverable"),
        agent_followup_required=bool(payload.get("agent_followup_required")),
        agent_followup_ref=_optional_str(payload, "agent_followup_ref"),
        metadata=dict(payload.get("metadata") or {}),
        log_path=config.human_work_log,
    )


def _actor_context(
    payload: dict[str, Any],
    *,
    config: KernelServiceConfig,
    subject: AuthenticatedSubject | None = None,
) -> ActorContext:
    actor_payload = dict(payload)
    if subject is not None:
        raw = payload.get("actor_context")
        data = dict(raw) if isinstance(raw, dict) else {}
        data["auth_subject"] = subject.auth_subject
        data["identity_provider"] = subject.identity_provider
        if subject.actor_id:
            data["actor_id"] = subject.actor_id
        if subject.actor_kind:
            data["actor_kind"] = subject.actor_kind
        actor_payload = {**payload, "actor_context": data}
    actor = actor_context_from_payload(
        actor_payload,
        identity_log=config.actor_identity_log,
        membership_log=config.actor_membership_log,
        enforce_registered=config.enforce_registered_actors,
        enforce_membership=config.enforce_actor_membership,
    )
    if subject is not None and config.enforce_subject_scope:
        _verify_subject_scope(actor, subject)
    return actor


def _require_identity_admin(actor: ActorContext, *, config: KernelServiceConfig) -> None:
    strict = (
        config.enforce_registered_actors
        or config.enforce_actor_membership
        or config.enforce_subject_scope
        or config.identity_provider is not None
    )
    if not strict:
        return
    if not actor.role_id:
        raise PermissionError("identity admin role required")
    if actor.role_id not in config.identity_admin_roles:
        raise PermissionError(f"identity admin role required; got {actor.role_id}")
    if config.enforce_registered_actors or config.identity_provider is not None:
        identity = get_actor_identity(actor.actor_id, log_path=config.actor_identity_log)
        if identity is None:
            raise PermissionError(f"registered identity admin actor required: {actor.actor_id}")
        if actor.role_id not in identity.roles_allowed:
            raise PermissionError(
                f"actor {actor.actor_id} is not explicitly allowed to act as {actor.role_id}"
            )


def _authenticate(
    headers: dict[str, str],
    *,
    config: KernelServiceConfig,
) -> AuthenticatedSubject | None:
    if config.identity_provider is None:
        return None
    subject = config.identity_provider.authenticate(headers)
    if subject is None:
        raise PermissionError("authentication failed")
    return subject


def _verify_subject_scope(actor: ActorContext, subject: AuthenticatedSubject) -> None:
    if subject.roles_allowed and (not actor.role_id or actor.role_id not in subject.roles_allowed):
        raise PermissionError(f"authenticated subject is not allowed to act as {actor.role_id}")
    if subject.tenant_ids and (not actor.tenant_id or actor.tenant_id not in subject.tenant_ids):
        raise PermissionError(f"authenticated subject is not allowed in tenant {actor.tenant_id}")


def _verify_mutation_lease(
    resource_ref: str,
    payload: dict[str, Any],
    *,
    actor: ActorContext,
    config: KernelServiceConfig,
) -> None:
    if config.mutation_backend is not None:
        _verify_backend_lease(
            config.mutation_backend,
            resource_ref=resource_ref,
            lease_id=_optional_str(payload, "lease_id"),
            actor=actor,
            required=config.require_leases,
            fencing_token=_optional_int(payload, "fencing_token"),
        )
        return
    verify_lease(
        resource_ref=resource_ref,
        lease_id=_optional_str(payload, "lease_id"),
        actor=actor,
        required=config.require_leases,
        fencing_token=_optional_int(payload, "fencing_token"),
        log_path=config.leases_log,
    )


def _verify_backend_lease(
    backend: TransactionalMutationBackend,
    *,
    resource_ref: str,
    lease_id: str | None,
    actor: ActorContext,
    required: bool,
    fencing_token: int | None,
) -> None:
    if not required:
        return
    if not lease_id:
        raise PermissionError(f"active lease is required for {resource_ref}")
    if fencing_token is None:
        raise PermissionError(f"fencing_token is required for {resource_ref}")
    matching = [
        lease
        for lease in backend.list_leases(resource_ref=resource_ref)
        if lease.get("lease_id") == lease_id
    ]
    if not matching:
        raise PermissionError(f"active lease not found for {resource_ref}: {lease_id}")
    lease = matching[-1]
    if lease.get("state") != "active":
        raise PermissionError(f"lease is not active: {lease_id}")
    if lease.get("held_by_actor_id") != actor.actor_id:
        raise PermissionError("lease holder does not match actor")
    if int(lease.get("fencing_token") or -1) != int(fencing_token):
        raise PermissionError("lease fencing token does not match")
    expires_at = str(lease.get("expires_at_utc") or "")
    try:
        expires = datetime.fromisoformat(expires_at)
    except ValueError as exc:
        raise PermissionError(f"lease has invalid expiry: {lease_id}") from exc
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        raise PermissionError(f"lease expired for {resource_ref}: {lease_id}")


def _ok(payload: dict[str, Any], *, status: int = 200) -> KernelServiceResponse:
    return KernelServiceResponse(status=status, payload={"ok": True, **payload})


def _error(status: int, message: str) -> KernelServiceResponse:
    return KernelServiceResponse(status=status, payload={"ok": False, "error": message})


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _list_str(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list")
    return [str(item) for item in value if str(item).strip()]


def _dedupe_strs(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _payload_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes"}


def _infer_governance_change_kind_for_target(
    target_ref: str,
    explicit_change_kind: str | None,
) -> str:
    if explicit_change_kind:
        return explicit_change_kind
    if target_ref.startswith("org/roles/"):
        return "role_change"
    if target_ref.startswith("org/charters/"):
        return "project_charter_change"
    if target_ref.startswith("org/policies/"):
        return "learning_policy_change"
    return "mandate_change"


def _governance_invariant_checks_from_body(body: dict[str, Any]) -> list[Any]:
    checks = list(body.get("invariant_checks") or [])
    if not _payload_bool(body, "require_deletion_duty"):
        return checks
    from cognitive_firm.orchestration.governance_changes import (
        deletion_duty_invariant_check,
    )

    target_ref = _required_str(body, "target_ref")
    change_kind = _infer_governance_change_kind_for_target(
        target_ref,
        _optional_str(body, "change_kind"),
    )
    checks.append(
        deletion_duty_invariant_check(
            target_ref=target_ref,
            change_kind=change_kind,
            retirement_candidate_ref=_optional_str(body, "retirement_candidate_ref"),
            net_growth_justification=_optional_str(body, "net_growth_justification"),
            evidence_refs=_list_str(body.get("deletion_duty_evidence_refs")),
        ).as_dict()
    )
    return checks


def _trace_events_for_packet(body: dict[str, Any], *, config: KernelServiceConfig) -> list[Any]:
    """Resolve or import trace events referenced by an attribution-packet request."""
    inline_rows = body.get("events")
    if inline_rows is not None:
        if not isinstance(inline_rows, list):
            raise ValueError("events must be a list")
        return [
            record_trace_event(
                runtime_name=str(row.get("runtime_name") or body.get("runtime_name") or ""),
                external_run_id=str(row.get("external_run_id") or body.get("external_run_id") or ""),
                event_kind=str(row.get("event_kind") or "custom"),
                agent_id=str(row.get("agent_id") or ""),
                status=str(row.get("status") or "observed"),
                cognitive_run_id=row.get("cognitive_run_id") or body.get("cognitive_run_id"),
                parent_agent_id=row.get("parent_agent_id"),
                target_agent_id=row.get("target_agent_id"),
                owner_role=row.get("owner_role") or body.get("owner_role"),
                step_id=row.get("step_id"),
                summary=row.get("summary"),
                payload_ref=row.get("payload_ref"),
                token_count=row.get("token_count"),
                cost_units=row.get("cost_units"),
                source_refs=_list_str(row.get("source_refs")),
                metadata=dict(row.get("metadata") or {}),
                event_id=row.get("event_id"),
                log_path=config.trace_events_log,
            )
            for row in inline_rows
        ]

    source_event_ids = set(_list_str(body.get("source_event_ids")))
    events = list_trace_events(
        runtime_name=_optional_str(body, "runtime_name"),
        external_run_id=_optional_str(body, "external_run_id"),
        cognitive_run_id=_optional_str(body, "cognitive_run_id"),
        log_path=config.trace_events_log,
    )
    if source_event_ids:
        events = [event for event in events if event.event_id in source_event_ids]
    if not events:
        raise ValueError("events or matching source_event_ids are required")
    if source_event_ids and len(events) != len(source_event_ids):
        found = {event.event_id for event in events}
        missing = sorted(source_event_ids - found)
        raise ValueError(f"source trace events not found: {', '.join(missing)}")
    return events


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None or value == "":
        return None
    return int(value)


def _required_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if value is None or value == "":
        raise ValueError(f"{key} is required")
    return int(value)


def _required_number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if value is None or value == "":
        raise ValueError(f"{key} is required")
    return float(value)


def _csv_env(name: str) -> list[str]:
    return [part.strip() for part in os.environ.get(name, "").split(",") if part.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local cognitive-firm kernel service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--human-work-log", type=Path, default=DEFAULT_HUMAN_WORK_LOG)
    parser.add_argument("--accountability-cases-log", type=Path, default=DEFAULT_ACCOUNTABILITY_CASES_LOG)
    parser.add_argument("--actor-identity-log", type=Path, default=DEFAULT_ACTOR_IDENTITY_LOG)
    parser.add_argument("--actor-membership-log", type=Path, default=DEFAULT_ACTOR_MEMBERSHIP_LOG)
    parser.add_argument("--leases-log", type=Path, default=DEFAULT_LEASES_LOG)
    parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--evidence-gaps-log", type=Path, default=DEFAULT_EVIDENCE_GAPS_LOG)
    parser.add_argument(
        "--forecast-market-summary",
        type=Path,
        default=DEFAULT_FORECAST_MARKET_ROOT / "global_health.json",
    )
    parser.add_argument("--action-impact-summary", type=Path, default=DEFAULT_ACTION_IMPACT_SUMMARY)
    parser.add_argument(
        "--policy-evaluations-log", type=Path, default=DEFAULT_POLICY_EVALUATIONS_LOG
    )
    parser.add_argument(
        "--policy-promotion-packets-log",
        type=Path,
        default=DEFAULT_POLICY_PROMOTION_PACKETS_LOG,
    )
    parser.add_argument("--policy-decisions-log", type=Path, default=DEFAULT_POLICY_DECISIONS_LOG)
    parser.add_argument("--work-items-log", type=Path, default=DEFAULT_WORK_ITEMS_LOG)
    parser.add_argument("--operating-units-log", type=Path, default=DEFAULT_OPERATING_UNITS_LOG)
    parser.add_argument("--outcome-links-log", type=Path, default=DEFAULT_OUTCOME_LINKS_LOG)
    parser.add_argument("--routine-reviews-log", type=Path, default=DEFAULT_ROUTINE_REVIEWS_LOG)
    parser.add_argument("--learning-events-log", type=Path, default=DEFAULT_LEARNING_EVENTS_LOG)
    parser.add_argument(
        "--learning-encounters-log", type=Path, default=DEFAULT_LEARNING_ENCOUNTERS_LOG
    )
    parser.add_argument("--action-attestation-log", type=Path, default=DEFAULT_ACTION_ATTESTATION_LOG)
    parser.add_argument("--formal-verification-log", type=Path, default=DEFAULT_FORMAL_VERIFICATION_LOG)
    parser.add_argument("--trace-events-log", type=Path, default=DEFAULT_TRACE_EVENTS_LOG)
    parser.add_argument("--attribution-packets-log", type=Path, default=DEFAULT_ATTRIBUTION_PACKETS_LOG)
    parser.add_argument("--phase-execution-log", type=Path, default=DEFAULT_PHASE_EXECUTION_LOG)
    parser.add_argument("--protocol-experiments-log", type=Path, default=DEFAULT_PROTOCOL_EXPERIMENTS_LOG)
    parser.add_argument("--capability-signals-log", type=Path, default=DEFAULT_CAPABILITY_SIGNALS_LOG)
    parser.add_argument(
        "--resource-allocation-log", type=Path, default=DEFAULT_RESOURCE_ALLOCATION_LOG
    )
    parser.add_argument("--residual-rights-log", type=Path, default=DEFAULT_RESIDUAL_RIGHTS_LOG)
    parser.add_argument(
        "--residual-decisions-log", type=Path, default=DEFAULT_RESIDUAL_DECISIONS_LOG
    )
    parser.add_argument(
        "--decision-aggregation-log", type=Path, default=DEFAULT_DECISION_AGGREGATION_LOG
    )
    parser.add_argument("--org-dir", type=Path, default=Path(os.environ.get("ORG_ROOT") or ORG_ROOT_DIR))
    parser.add_argument(
        "--gates-dir",
        type=Path,
        default=Path(os.environ.get("GATES_DIR") or WORKSPACE_DIR / "gates" / "pending"),
    )
    parser.add_argument(
        "--gates-resolved-dir",
        type=Path,
        default=Path(
            os.environ.get("GATES_RESOLVED_DIR") or WORKSPACE_DIR / "gates" / "resolved"
        ),
    )
    parser.add_argument(
        "--transition-log",
        type=Path,
        default=Path(os.environ.get("TRANSITIONS_LOG") or WORKSPACE_DIR / "transitions.jsonl"),
    )
    parser.add_argument("--enforce-registered-actors", action="store_true")
    parser.add_argument("--enforce-actor-membership", action="store_true")
    parser.add_argument(
        "--enforce-subject-scope",
        action="store_true",
        help="Require authenticated subject role/tenant scopes to match actor_context.",
    )
    parser.add_argument("--require-leases", action="store_true")
    parser.add_argument(
        "--mutation-backend",
        choices=("jsonl", "sqlite"),
        default=os.environ.get("COGNITIVE_FIRM_MUTATION_BACKEND", "jsonl"),
        help="Mutation lease backend. jsonl preserves T1 files; sqlite enables transactional fencing.",
    )
    parser.add_argument(
        "--mutation-db",
        type=Path,
        default=Path(
            os.environ.get("COGNITIVE_FIRM_MUTATION_DB") or WORKSPACE_DIR / "kernel_mutations.sqlite3"
        ),
    )
    parser.add_argument(
        "--require-token",
        action="store_true",
        help="Require Authorization: Bearer <token>; token is read from COGNITIVE_FIRM_KERNEL_TOKEN.",
    )
    args = parser.parse_args(argv)
    identity_provider = None
    if args.require_token:
        token = os.environ.get("COGNITIVE_FIRM_KERNEL_TOKEN")
        if not token:
            raise SystemExit("COGNITIVE_FIRM_KERNEL_TOKEN is required with --require-token")
        identity_provider = StaticBearerTokenIdentityProvider(
            subjects_by_token={
                token: AuthenticatedSubject(
                    auth_subject="static_bearer:kernel",
                    identity_provider="static_bearer",
                    actor_id=os.environ.get("COGNITIVE_FIRM_KERNEL_ACTOR_ID"),
                    actor_kind=os.environ.get("COGNITIVE_FIRM_KERNEL_ACTOR_KIND"),
                    roles_allowed=_csv_env("COGNITIVE_FIRM_KERNEL_ROLES_ALLOWED"),
                    tenant_ids=_csv_env("COGNITIVE_FIRM_KERNEL_TENANT_IDS"),
                )
            }
        )
    mutation_backend = None
    if args.mutation_backend == "sqlite":
        mutation_backend = SqliteMutationBackend(args.mutation_db)
    serve(
        host=args.host,
        port=args.port,
        config=KernelServiceConfig(
            human_work_log=args.human_work_log,
            accountability_cases_log=args.accountability_cases_log,
            actor_identity_log=args.actor_identity_log,
            actor_membership_log=args.actor_membership_log,
            leases_log=args.leases_log,
            evidence_gaps_log=args.evidence_gaps_log,
            forecast_market_summary=args.forecast_market_summary,
            action_impact_summary=args.action_impact_summary,
            policy_evaluations_log=args.policy_evaluations_log,
            policy_promotion_packets_log=args.policy_promotion_packets_log,
            policy_decisions_log=args.policy_decisions_log,
            work_items_log=args.work_items_log,
            operating_units_log=args.operating_units_log,
            outcome_links_log=args.outcome_links_log,
            routine_reviews_log=args.routine_reviews_log,
            learning_events_log=args.learning_events_log,
            learning_encounters_log=args.learning_encounters_log,
            action_attestation_log=args.action_attestation_log,
            formal_verification_log=args.formal_verification_log,
            trace_events_log=args.trace_events_log,
            attribution_packets_log=args.attribution_packets_log,
            phase_execution_log=args.phase_execution_log,
            protocol_experiments_log=args.protocol_experiments_log,
            capability_signals_log=args.capability_signals_log,
            resource_allocation_log=args.resource_allocation_log,
            residual_rights_log=args.residual_rights_log,
            residual_decisions_log=args.residual_decisions_log,
            decision_aggregation_log=args.decision_aggregation_log,
            project_root=args.project_root,
            org_dir=args.org_dir,
            gates_dir=args.gates_dir,
            gates_resolved_dir=args.gates_resolved_dir,
            transition_log=args.transition_log,
            enforce_registered_actors=args.enforce_registered_actors,
            enforce_actor_membership=args.enforce_actor_membership,
            enforce_subject_scope=args.enforce_subject_scope,
            require_leases=args.require_leases,
            identity_provider=identity_provider,
            mutation_backend=mutation_backend,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
