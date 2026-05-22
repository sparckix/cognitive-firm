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
from cognitive_firm.common.paths import ORG_ROOT_DIR, WORKSPACE_DIR
from cognitive_firm.orchestration.accountability import build_accountability_summary
from cognitive_firm.orchestration.accountability_cases import (
    DEFAULT_ACCOUNTABILITY_CASES_LOG,
    create_accountability_case,
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
from cognitive_firm.orchestration.agent_channels import send_agent_message
from cognitive_firm.orchestration.human_work import (
    DEFAULT_HUMAN_WORK_LOG,
    append_human_work_interaction,
    create_agent_requested_human_work_session,
    create_human_work_session,
    update_human_work_state,
)
from cognitive_firm.orchestration.leases import DEFAULT_LEASES_LOG, acquire_lease, release_lease, verify_lease
from cognitive_firm.orchestration.operating_units import (
    DEFAULT_OPERATING_UNITS_LOG,
    define_operating_unit,
    list_operating_units,
)
from cognitive_firm.orchestration.operating_unit_surface import build_operating_unit_dashboard
from cognitive_firm.orchestration.outcome_links import (
    DEFAULT_OUTCOME_LINKS_LOG,
    create_outcome_link,
    list_outcome_links,
    record_metric_snapshot,
    record_verdict,
    summarize_outcome_links,
    void_outcome_link,
)
from cognitive_firm.orchestration.routine_reviews import (
    DEFAULT_ROUTINE_REVIEWS_LOG,
    list_due_reviews,
    record_review_outcome,
    retire_routine,
    schedule_routine_review,
    start_routine_review,
    summarize_routine_reviews,
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
    heartbeat_work_item,
    requeue_dead_letter,
    retire_work_item,
    start_work_item,
)


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
    work_items_log: Path = DEFAULT_WORK_ITEMS_LOG
    operating_units_log: Path = DEFAULT_OPERATING_UNITS_LOG
    outcome_links_log: Path = DEFAULT_OUTCOME_LINKS_LOG
    routine_reviews_log: Path = DEFAULT_ROUTINE_REVIEWS_LOG
    resource_allocation_log: Path = DEFAULT_RESOURCE_ALLOCATION_LOG
    residual_rights_log: Path = DEFAULT_RESIDUAL_RIGHTS_LOG
    residual_decisions_log: Path = DEFAULT_RESIDUAL_DECISIONS_LOG
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


def _attention_feed(config: KernelServiceConfig) -> list[dict[str, Any]]:
    """Gather the firm's pending signals and route them to participants (L1).

    Pending gates, A2H work requests, and governance-change proposals awaiting
    a human decision are normalized, then the userland attention router
    classifies each and resolves its target participant.
    """
    from cognitive_firm.orchestration.actor_membership import (
        list_actor_memberships,
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
        resolve_authority_role,
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
        # the authority. This closes the governed-install human loop: an
        # overlay's authority-diff proposal surfaces in the operator's queue.
        signals.append(
            AttentionSignal(
                signal_id=proposal.proposal_id,
                kind="governance_change",
                headline=f"Governance change awaiting review: {proposal.title}",
                source_ref=proposal.proposal_id,
                created_at_utc=proposal.created_at_utc,
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

    authority_role = resolve_authority_role(config.org_dir)
    authority_actor: str | None = None
    if authority_role:
        memberships = list_actor_memberships(
            role_id=authority_role,
            status="active",
            log_path=config.actor_membership_log,
        )
        if memberships:
            # The authority role may have more than one active holder; pick
            # deterministically (lowest actor_id) so a given firm state always
            # routes governance interrupts to the same holder, not to whichever
            # membership the log happened to return first.
            authority_actor = min(m.actor_id for m in memberships)

    routed = route_signals(
        signals,
        authority_actor_id=authority_actor,
        authority_role_id=authority_role,
    )
    return [signal.as_dict() for signal in routed]


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
        # the literal verb: every non-GET request is a mutation here, so a
        # PUT/PATCH/DELETE added later is gated by construction, not by being
        # remembered. A denied mutation is an authorization failure -> 403.
        if method != "GET":
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
            surface = build_org_surface(
                human_work_log=config.human_work_log,
                accountability_cases_log=config.accountability_cases_log,
            )
            return _ok({"surface": surface.as_dict()})

        if method == "GET" and route == "/kernel/accountability-summary":
            surface = build_org_surface(
                human_work_log=config.human_work_log,
                accountability_cases_log=config.accountability_cases_log,
            )
            summary = build_accountability_summary(surface)
            return _ok({"summary": summary.as_dict()})

        if method == "GET" and route == "/kernel/vocabulary":
            return _ok(_vocabulary_payload())

        if method == "GET" and route == "/kernel/governance-changes":
            from cognitive_firm.orchestration.governance_changes import (
                list_governance_changes,
            )

            status_filter = query.get("status", [None])[0]
            proposals = list_governance_changes(
                status=status_filter,
                log_path=_governance_changes_log(config),
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
                log_path=config.accountability_cases_log,
            )
            return _ok({"case": asdict(case)}, status=201)

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
            )
            return _ok({"message": asdict(msg)}, status=201)

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

        if method == "GET" and route == "/kernel/operating-units":
            units = list_operating_units(log_path=config.operating_units_log)
            return _ok({"operating_units": [unit.as_dict() for unit in units]})

        if method == "GET" and route == "/kernel/operating-unit-dashboard":
            dashboard = build_operating_unit_dashboard(
                operating_units_log=config.operating_units_log,
                work_items_log=config.work_items_log,
            )
            return _ok({"dashboard": dashboard.as_dict()})

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
            _verify_mutation_lease(f"outcome_link:{link_id}", body, actor=actor, config=config)
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
            else:
                return _error(404, f"unknown outcome-link action: {action}")
            return _ok({"outcome_link": link.as_dict()})

        # --- routine reviews: scheduled review and retirement of stale routines ---
        if method == "GET" and route == "/kernel/routine-reviews/due":
            due = list_due_reviews(log_path=config.routine_reviews_log)
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
    parser.add_argument("--work-items-log", type=Path, default=DEFAULT_WORK_ITEMS_LOG)
    parser.add_argument("--operating-units-log", type=Path, default=DEFAULT_OPERATING_UNITS_LOG)
    parser.add_argument("--outcome-links-log", type=Path, default=DEFAULT_OUTCOME_LINKS_LOG)
    parser.add_argument("--routine-reviews-log", type=Path, default=DEFAULT_ROUTINE_REVIEWS_LOG)
    parser.add_argument(
        "--resource-allocation-log", type=Path, default=DEFAULT_RESOURCE_ALLOCATION_LOG
    )
    parser.add_argument("--residual-rights-log", type=Path, default=DEFAULT_RESIDUAL_RIGHTS_LOG)
    parser.add_argument(
        "--residual-decisions-log", type=Path, default=DEFAULT_RESIDUAL_DECISIONS_LOG
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
            work_items_log=args.work_items_log,
            operating_units_log=args.operating_units_log,
            outcome_links_log=args.outcome_links_log,
            routine_reviews_log=args.routine_reviews_log,
            resource_allocation_log=args.resource_allocation_log,
            residual_rights_log=args.residual_rights_log,
            residual_decisions_log=args.residual_decisions_log,
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
