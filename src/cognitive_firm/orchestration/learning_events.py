"""Approved organizational learning events.

Learning-transition candidates are proposals. Approved learning events are the
durable record that a role or tenant policy accepted a behavior change that
should affect future work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.resource_envelope import KernelResource, make_resource


LearningEventKind = Literal[
    "route_change",
    "mandate_change",
    "charter_change",
    "evidence_standard_change",
    "review_threshold_change",
    "routine_change",
    "policy_adapter_change",
]
LearningEventStatus = Literal["active", "superseded", "retired"]
LearningEncounterOutcome = Literal["encountered", "applied", "ignored", "deferred"]

DEFAULT_LEARNING_EVENTS_LOG = ORG_ROOT_DIR / "learning_events" / "learning_events.jsonl"
DEFAULT_LEARNING_ENCOUNTERS_LOG = ORG_ROOT_DIR / "learning_events" / "learning_encounters.jsonl"
VALID_EVENT_KINDS = {
    "route_change",
    "mandate_change",
    "charter_change",
    "evidence_standard_change",
    "review_threshold_change",
    "routine_change",
    "policy_adapter_change",
}
VALID_STATUSES = {"active", "superseded", "retired"}
VALID_ENCOUNTER_OUTCOMES = {"encountered", "applied", "ignored", "deferred"}


@dataclass(frozen=True)
class ApprovedLearningEvent:
    """A reviewed durable change to future organizational behavior."""

    learning_event_id: str
    created_at_utc: str
    learning_unit_kind: LearningEventKind
    decision_use: str
    future_application_cue: str
    approved_by: str
    approval_ref: str
    source_carrier_refs: list[str] = field(default_factory=list)
    derived_from_learning_event_ids: list[str] = field(default_factory=list)
    candidate_ref: str | None = None
    before_state: str | None = None
    after_state: str | None = None
    owner_role: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    externality_review_ref: str | None = None
    review_after_utc: str | None = None
    superseded_by: str | None = None
    retirement_reason: str | None = None
    status: LearningEventStatus = "active"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningEventEncounter:
    """A future work surface encountered an approved learning event."""

    encounter_id: str
    encountered_at_utc: str
    learning_event_id: str
    role: str
    cue: str
    outcome: LearningEncounterOutcome
    work_ref: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    reason: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    context_packet_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningEventSummary:
    """Read-side health summary for approved learning units.

    Derived from learning-event rows plus optional encounter, outcome-link, and
    routine-review logs. It owns no facts and can be rebuilt.
    """

    total: int
    active: int
    superseded: int
    retired: int
    compounded: int
    root_units: int
    with_source_carriers: int
    with_review_after: int
    encounter_counts: dict[str, int]
    events_with_encounters: int
    outcome_link_count: int
    outcome_verdict_coverage: float
    routine_review_count: int
    overdue_routine_review_count: int
    overdue_learning_event_ids: list[str]
    recommendation: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_learning_event(
    *,
    learning_unit_kind: LearningEventKind | str,
    decision_use: str,
    future_application_cue: str,
    approved_by: str,
    approval_ref: str,
    source_carrier_refs: list[str] | None = None,
    derived_from_learning_event_ids: list[str] | None = None,
    candidate_ref: str | None = None,
    before_state: str | None = None,
    after_state: str | None = None,
    owner_role: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    externality_review_ref: str | None = None,
    review_after_utc: str | None = None,
    metadata: dict[str, Any] | None = None,
    learning_event_id: str | None = None,
    log_path: Path | None = None,
) -> ApprovedLearningEvent:
    """Create and append an approved learning event."""
    if not decision_use.strip():
        raise ValueError("decision_use is required")
    if not future_application_cue.strip():
        raise ValueError("future_application_cue is required")
    if not approved_by.strip():
        raise ValueError("approved_by is required")
    if not approval_ref.strip():
        raise ValueError("approval_ref is required")

    event = ApprovedLearningEvent(
        learning_event_id=learning_event_id or f"learn_{uuid.uuid4().hex[:12]}",
        created_at_utc=_now_iso(),
        learning_unit_kind=_validate_kind(str(learning_unit_kind)),
        decision_use=decision_use,
        future_application_cue=future_application_cue,
        approved_by=approved_by,
        approval_ref=approval_ref,
        source_carrier_refs=_clean_unique_strings(source_carrier_refs or [], label="source_carrier_refs"),
        derived_from_learning_event_ids=_clean_unique_strings(
            derived_from_learning_event_ids or [],
            label="derived_from_learning_event_ids",
        ),
        candidate_ref=candidate_ref,
        before_state=before_state,
        after_state=after_state,
        owner_role=owner_role,
        tenant_id=tenant_id,
        project_id=project_id,
        externality_review_ref=externality_review_ref,
        review_after_utc=review_after_utc,
        metadata=metadata or {},
    )
    _append_jsonl(log_path or DEFAULT_LEARNING_EVENTS_LOG, event.as_dict())
    return event


def create_compounded_learning_event(
    *,
    source_learning_event_ids: list[str],
    learning_unit_kind: LearningEventKind | str,
    decision_use: str,
    future_application_cue: str,
    approved_by: str,
    approval_ref: str,
    source_carrier_refs: list[str] | None = None,
    candidate_ref: str | None = None,
    before_state: str | None = None,
    after_state: str | None = None,
    owner_role: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    externality_review_ref: str | None = None,
    review_after_utc: str | None = None,
    metadata: dict[str, Any] | None = None,
    learning_event_id: str | None = None,
    require_active_sources: bool = True,
    log_path: Path | None = None,
) -> ApprovedLearningEvent:
    """Create an approved event whose basis is prior learning events.

    This records lineage only. It does not apply the referenced behavior
    change, merge routines, or decide whether the parent events should retire.
    """
    source_ids = _clean_unique_strings(
        source_learning_event_ids,
        label="source_learning_event_ids",
    )
    if not source_ids:
        raise ValueError("source_learning_event_ids must list at least one learning event")

    path = log_path or DEFAULT_LEARNING_EVENTS_LOG
    known = {event.learning_event_id: event for event in list_learning_events(log_path=path)}
    missing = [event_id for event_id in source_ids if event_id not in known]
    if missing:
        raise KeyError(f"source learning events not found: {', '.join(missing)}")
    if require_active_sources:
        inactive = [
            event_id
            for event_id in source_ids
            if known[event_id].status != "active"
        ]
        if inactive:
            raise ValueError(
                "source learning events must be active when compounding: "
                + ", ".join(inactive)
            )

    carrier_refs = _clean_unique_strings(
        [
            *(source_carrier_refs or []),
            *(f"learning_event:{event_id}" for event_id in source_ids),
        ],
        label="source_carrier_refs",
    )
    return create_learning_event(
        learning_unit_kind=learning_unit_kind,
        decision_use=decision_use,
        future_application_cue=future_application_cue,
        approved_by=approved_by,
        approval_ref=approval_ref,
        source_carrier_refs=carrier_refs,
        derived_from_learning_event_ids=source_ids,
        candidate_ref=candidate_ref,
        before_state=before_state,
        after_state=after_state,
        owner_role=owner_role,
        tenant_id=tenant_id,
        project_id=project_id,
        externality_review_ref=externality_review_ref,
        review_after_utc=review_after_utc,
        metadata=metadata,
        learning_event_id=learning_event_id,
        log_path=path,
    )


def list_learning_events(
    *,
    status: LearningEventStatus | str | None = None,
    learning_unit_kind: LearningEventKind | str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> list[ApprovedLearningEvent]:
    """Read approved learning events, optionally filtered."""
    if status is not None:
        status = _validate_status(str(status))
    if learning_unit_kind is not None:
        learning_unit_kind = _validate_kind(str(learning_unit_kind))

    events: list[ApprovedLearningEvent] = []
    for row in _read_jsonl(log_path or DEFAULT_LEARNING_EVENTS_LOG):
        event = ApprovedLearningEvent(**row)
        if status is not None and event.status != status:
            continue
        if learning_unit_kind is not None and event.learning_unit_kind != learning_unit_kind:
            continue
        if tenant_id is not None and event.tenant_id != tenant_id:
            continue
        if project_id is not None and event.project_id != project_id:
            continue
        events.append(event)
    return events


def update_learning_event_status(
    learning_event_id: str,
    status: LearningEventStatus | str,
    *,
    superseded_by: str | None = None,
    retirement_reason: str | None = None,
    log_path: Path | None = None,
) -> ApprovedLearningEvent:
    """Update one learning-event lifecycle state.

    This rewrites the T1 JSONL projection. Event-sourced deployments should
    replace this adapter with append-only lifecycle events.
    """
    path = log_path or DEFAULT_LEARNING_EVENTS_LOG
    next_status = _validate_status(str(status))
    if next_status == "superseded" and not superseded_by:
        raise ValueError("superseded_by is required when status is superseded")
    if next_status == "retired" and not retirement_reason:
        raise ValueError("retirement_reason is required when status is retired")
    rows = _read_jsonl(path)
    updated: ApprovedLearningEvent | None = None
    next_rows: list[dict[str, Any]] = []

    for row in rows:
        row = dict(row)
        if row.get("learning_event_id") == learning_event_id:
            row["status"] = next_status
            row["superseded_by"] = superseded_by
            row["retirement_reason"] = retirement_reason
            updated = ApprovedLearningEvent(**row)
        next_rows.append(row)

    if updated is None:
        raise KeyError(f"learning event not found: {learning_event_id}")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in next_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return updated


def replay_learning_events(
    *,
    role: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    cue: str | None = None,
    cue_signature: str | None = None,
    resource_refs: list[str] | None = None,
    topology_refs: list[str] | None = None,
    source_ref: str | None = None,
    tag: str | None = None,
    log_path: Path | None = None,
) -> list[ApprovedLearningEvent]:
    """Return active events relevant to a future work surface.

    This replay is deliberately lexical and metadata-bound. It does not use
    semantic similarity as authority.
    """
    events = list_learning_events(status="active", log_path=log_path)
    out: list[ApprovedLearningEvent] = []
    cue_text = cue.strip().lower() if cue and cue.strip() else None
    cue_signature_values = _clean_optional_strings(
        [cue_signature] if cue_signature is not None else []
    )
    cue_signature = cue_signature_values[0] if cue_signature_values else None
    resource_ref_set = set(_clean_optional_strings(resource_refs or []))
    topology_ref_set = set(_clean_optional_strings(topology_refs or []))
    for event in events:
        if tenant_id is None and event.tenant_id is not None:
            continue
        if tenant_id is not None and event.tenant_id not in {None, tenant_id}:
            continue
        if project_id is None and event.project_id is not None:
            continue
        if project_id is not None and event.project_id not in {None, project_id}:
            continue
        if role and event.owner_role and event.owner_role != role:
            continue
        if source_ref is not None and source_ref not in _learning_event_exact_refs(event):
            continue
        if tag is not None and tag not in _learning_event_tags(event):
            continue
        if cue_signature is not None:
            if cue_signature not in _learning_event_cue_signatures(event):
                continue
        if resource_ref_set:
            if not resource_ref_set.intersection(_learning_event_resource_refs(event)):
                continue
        if topology_ref_set:
            if not topology_ref_set.intersection(_learning_event_topology_refs(event)):
                continue
        negative_cues = _learning_event_negative_cues(event)
        if cue_signature and cue_signature in negative_cues:
            continue
        if cue_text:
            if any(negative.lower() in cue_text for negative in negative_cues):
                continue
            haystack = " ".join(
                [
                    event.future_application_cue,
                    event.decision_use,
                    event.learning_unit_kind,
                    " ".join(event.source_carrier_refs),
                ]
            ).lower()
            future_cue = event.future_application_cue.lower()
            decision_use = event.decision_use.lower()
            if (
                cue_text not in haystack
                and future_cue not in cue_text
                and decision_use not in cue_text
            ):
                continue
        out.append(event)
    return out


def _learning_event_exact_refs(event: ApprovedLearningEvent) -> set[str]:
    refs = {
        event.learning_event_id,
        f"learning_event:{event.learning_event_id}",
        event.approval_ref,
    }
    refs.update(event.source_carrier_refs)
    refs.update(f"learning_event:{event_id}" for event_id in event.derived_from_learning_event_ids)
    if event.candidate_ref:
        refs.add(event.candidate_ref)
    if event.externality_review_ref:
        refs.add(event.externality_review_ref)
    return {ref for ref in refs if ref}


def _learning_event_tags(event: ApprovedLearningEvent) -> set[str]:
    tags: set[str] = set()
    for key in ("tag", "tags", "labels", "capability_tags"):
        tags.update(_string_list(event.metadata.get(key)))
    return tags


def _learning_event_cue_signatures(event: ApprovedLearningEvent) -> set[str]:
    signatures: set[str] = set()
    for key in ("cue_signature", "cue_signatures"):
        signatures.update(_string_list(event.metadata.get(key)))
    return signatures


def _learning_event_resource_refs(event: ApprovedLearningEvent) -> set[str]:
    refs: set[str] = set()
    for key in ("resource_ref", "resource_refs"):
        refs.update(_string_list(event.metadata.get(key)))
    return refs


def _learning_event_topology_refs(event: ApprovedLearningEvent) -> set[str]:
    refs: set[str] = set()
    for key in ("topology_ref", "topology_refs"):
        refs.update(_string_list(event.metadata.get(key)))
    return refs


def _learning_event_negative_cues(event: ApprovedLearningEvent) -> set[str]:
    cues: set[str] = set()
    for key in ("negative_cue", "negative_cues"):
        cues.update(_string_list(event.metadata.get(key)))
    return cues


def record_learning_event_encounter(
    *,
    learning_event_id: str,
    role: str,
    cue: str,
    outcome: LearningEncounterOutcome | str = "encountered",
    work_ref: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    reason: str | None = None,
    evidence_refs: list[str] | None = None,
    context_packet_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    log_path: Path | None = None,
) -> LearningEventEncounter:
    """Record that future work encountered, applied, or ignored learning.

    Stronger outcomes are learning-use receipts. They need enough evidence to
    support later audit without turning replay into automatic application.
    """
    if not learning_event_id.strip():
        raise ValueError("learning_event_id is required")
    if not role.strip():
        raise ValueError("role is required")
    if not cue.strip():
        raise ValueError("cue is required")
    normalized = _validate_encounter_outcome(str(outcome))
    normalized_evidence_refs = evidence_refs or []
    if normalized in {"ignored", "deferred"} and not (reason or "").strip():
        raise ValueError(f"{normalized} learning encounters require a reason")
    if (
        normalized == "applied"
        and not work_ref
        and not normalized_evidence_refs
        and not context_packet_ref
    ):
        raise ValueError(
            "applied learning encounters require work_ref, evidence_refs, "
            "or context_packet_ref"
        )
    dedupe_key = idempotency_key or _encounter_idempotency_key(
        learning_event_id=learning_event_id,
        role=role,
        cue=cue,
        outcome=normalized,
        work_ref=work_ref,
        tenant_id=tenant_id,
        project_id=project_id,
        context_packet_ref=context_packet_ref,
    )
    path = log_path or DEFAULT_LEARNING_ENCOUNTERS_LOG
    for existing in list_learning_event_encounters(log_path=path):
        if existing.metadata.get("idempotency_key") == dedupe_key:
            return existing
    encounter = LearningEventEncounter(
        encounter_id=f"lenc_{dedupe_key[:12]}",
        encountered_at_utc=_now_iso(),
        learning_event_id=learning_event_id,
        role=role,
        cue=cue,
        outcome=normalized,
        work_ref=work_ref,
        tenant_id=tenant_id,
        project_id=project_id,
        reason=reason,
        evidence_refs=normalized_evidence_refs,
        context_packet_ref=context_packet_ref,
        metadata={**(metadata or {}), "idempotency_key": dedupe_key},
    )
    _append_jsonl(path, encounter.as_dict())
    return encounter


def verify_learning_event_context_packet_use(
    *,
    learning_event_id: str,
    context_packet: dict[str, Any],
    context_packet_ref: str | None = None,
) -> dict[str, Any]:
    """Verify a context packet can support a learning-use receipt.

    This is a read-only receipt-integrity check. It verifies the packet digest
    and confirms the packet basis names the learning event being encountered;
    it does not replay current logs, apply learning, or authorize work.
    """
    from cognitive_firm.orchestration.work_discovery import verify_context_packet

    if not isinstance(context_packet, dict):
        return {
            "ok": False,
            "issues": ["context_packet must be an object"],
            "packet_ok": False,
            "read_only": True,
            "verification_policy": "context_packet_digest_basis_includes_learning_event",
        }

    packet_verification = verify_context_packet(context_packet)
    issues = list(packet_verification.get("issues") or [])
    packet_ref = packet_verification.get("context_packet_id")
    basis = packet_verification.get("basis") or {}
    learning_event_ids = basis.get("learning_event_ids")

    if packet_verification.get("ok"):
        if not isinstance(learning_event_ids, list) or learning_event_id not in {
            str(item) for item in learning_event_ids
        }:
            issues.append(
                "context_packet does not include learning_event_id "
                f"{learning_event_id}"
            )
        if context_packet_ref and context_packet_ref != packet_ref:
            issues.append("context_packet_ref does not match context_packet id")

    ok = not issues
    return {
        "ok": ok,
        "issues": issues,
        "packet_ok": bool(packet_verification.get("ok")),
        "context_packet_ref": packet_ref,
        "digest": packet_verification.get("digest"),
        "basis_learning_event_ids": [
            str(item) for item in learning_event_ids
        ]
        if isinstance(learning_event_ids, list)
        else [],
        "receipt_metadata": {
            "context_packet_verification": "digest_basis_includes_learning_event",
            "context_packet_digest": packet_verification.get("digest"),
            "context_packet_verification_policy": packet_verification.get(
                "verification_policy"
            ),
        }
        if ok
        else {},
        "read_only": True,
        "verification_policy": "context_packet_digest_basis_includes_learning_event",
    }


def list_learning_event_encounters(
    *,
    learning_event_id: str | None = None,
    role: str | None = None,
    outcome: LearningEncounterOutcome | str | None = None,
    log_path: Path | None = None,
) -> list[LearningEventEncounter]:
    """Read recorded learning-event encounters."""
    if outcome is not None:
        outcome = _validate_encounter_outcome(str(outcome))
    out: list[LearningEventEncounter] = []
    for row in _read_jsonl(log_path or DEFAULT_LEARNING_ENCOUNTERS_LOG):
        encounter = LearningEventEncounter(**row)
        if learning_event_id is not None and encounter.learning_event_id != learning_event_id:
            continue
        if role is not None and encounter.role != role:
            continue
        if outcome is not None and encounter.outcome != outcome:
            continue
        out.append(encounter)
    return out


def summarize_learning_events(
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    events: list[ApprovedLearningEvent] | None = None,
    encounters: list[LearningEventEncounter] | None = None,
    log_path: Path | None = None,
    encounters_log_path: Path | None = None,
    outcome_links_log_path: Path | None = None,
    routine_reviews_log_path: Path | None = None,
) -> LearningEventSummary:
    """Summarize approved learning units and whether they are closing loops.

    The summary treats ``ApprovedLearningEvent`` as the unit. Action-impact
    rows, forecasts, human receipts, and strategy findings remain carriers
    unless they were promoted into approved events.
    """
    rows = events if events is not None else list_learning_events(
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=log_path,
    )
    event_ids = {event.learning_event_id for event in rows}
    by_status = {state: 0 for state in VALID_STATUSES}
    compounded = 0
    with_source_carriers = 0
    with_review_after = 0
    for event in rows:
        by_status[event.status] = by_status.get(event.status, 0) + 1
        if event.derived_from_learning_event_ids:
            compounded += 1
        if event.source_carrier_refs:
            with_source_carriers += 1
        if event.review_after_utc:
            with_review_after += 1

    encounter_rows = encounters if encounters is not None else list_learning_event_encounters(
        log_path=encounters_log_path,
    )
    encounter_counts = {outcome: 0 for outcome in sorted(VALID_ENCOUNTER_OUTCOMES)}
    events_with_encounters: set[str] = set()
    for encounter in encounter_rows:
        if encounter.learning_event_id not in event_ids:
            continue
        if tenant_id is not None and encounter.tenant_id not in {None, tenant_id}:
            continue
        if project_id is not None and encounter.project_id not in {None, project_id}:
            continue
        encounter_counts[encounter.outcome] = encounter_counts.get(encounter.outcome, 0) + 1
        events_with_encounters.add(encounter.learning_event_id)

    outcome_link_count, outcome_verdict_coverage = _learning_event_outcome_summary(
        event_ids=event_ids,
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=outcome_links_log_path,
    )
    routine_review_count, overdue_count, overdue_learning_event_ids = _learning_event_review_summary(
        event_ids=event_ids,
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=routine_reviews_log_path,
    )
    return LearningEventSummary(
        total=len(rows),
        active=by_status.get("active", 0),
        superseded=by_status.get("superseded", 0),
        retired=by_status.get("retired", 0),
        compounded=compounded,
        root_units=len(rows) - compounded,
        with_source_carriers=with_source_carriers,
        with_review_after=with_review_after,
        encounter_counts=encounter_counts,
        events_with_encounters=len(events_with_encounters),
        outcome_link_count=outcome_link_count,
        outcome_verdict_coverage=outcome_verdict_coverage,
        routine_review_count=routine_review_count,
        overdue_routine_review_count=overdue_count,
        overdue_learning_event_ids=overdue_learning_event_ids,
        recommendation=_learning_summary_recommendation(
            active=by_status.get("active", 0),
            overdue_count=overdue_count,
            outcome_link_count=outcome_link_count,
            outcome_verdict_coverage=outcome_verdict_coverage,
            events_with_encounters=len(events_with_encounters),
        ),
    )


def learning_event_loop_projection(
    learning_event_id: str,
    *,
    log_path: Path | None = None,
    encounters_log_path: Path | None = None,
    outcome_links_log_path: Path | None = None,
    routine_reviews_log_path: Path | None = None,
) -> dict[str, Any]:
    """Return one approved learning unit's read-only compounding loop.

    This is the operator-facing join for v0.4: what was learned, what evidence
    justified it, what future context will see it, how it has been used, what
    outcomes measured it, and when the routine is due for review. It owns no
    facts and does not promote, apply, rank, or dispatch learning.
    """

    event = next(
        (
            row
            for row in list_learning_events(log_path=log_path)
            if row.learning_event_id == learning_event_id
        ),
        None,
    )
    if event is None:
        raise KeyError(f"learning event not found: {learning_event_id}")

    encounters = list_learning_event_encounters(
        learning_event_id=learning_event_id,
        log_path=encounters_log_path,
    )
    from cognitive_firm.orchestration.outcome_links import list_outcome_links
    from cognitive_firm.orchestration.routine_reviews import list_routine_reviews

    outcome_links = list_outcome_links(
        learning_event_id=learning_event_id,
        log_path=outcome_links_log_path,
    )
    routine_reviews = list_routine_reviews(
        learning_event_id=learning_event_id,
        log_path=routine_reviews_log_path,
    )

    encounter_counts = {
        outcome: 0 for outcome in sorted(VALID_ENCOUNTER_OUTCOMES)
    }
    for encounter in encounters:
        encounter_counts[encounter.outcome] = encounter_counts.get(
            encounter.outcome,
            0,
        ) + 1
    verdict_counts: dict[str, int] = {}
    for link in outcome_links:
        verdict = link.verdict or "awaiting_verdict"
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    non_voided_links = [link for link in outcome_links if link.status != "voided"]
    verdict_coverage = (
        len([link for link in non_voided_links if link.verdict is not None])
        / len(non_voided_links)
        if non_voided_links
        else 0.0
    )
    overdue_review_ids = [
        review.review_id for review in routine_reviews if review.is_overdue()
    ]
    context_packet_refs = sorted(
        {
            ref
            for ref in (encounter.context_packet_ref for encounter in encounters)
            if ref
        }
    )
    verified_context_packet_refs = sorted(
        {
            encounter.context_packet_ref
            for encounter in encounters
            if encounter.context_packet_ref
            and encounter.metadata.get("context_packet_verification")
            == "digest_basis_includes_learning_event"
        }
    )
    evidence_refs = list(
        dict.fromkeys(
            [
                event.approval_ref,
                *event.source_carrier_refs,
                *(link.outcome_link_id for link in outcome_links),
                *(review.review_id for review in routine_reviews),
                *[
                    ref
                    for encounter in encounters
                    for ref in encounter.evidence_refs
                ],
            ]
        )
    )

    if event.status != "active":
        loop_state = event.status
        recommendation = "learning unit is no longer active"
    elif not outcome_links:
        loop_state = "needs_outcome_link"
        recommendation = "attach an outcome link to measure this learning unit"
    elif verdict_coverage < 1.0:
        loop_state = "awaiting_outcome_verdict"
        recommendation = "record verdicts for open outcome links"
    elif overdue_review_ids:
        loop_state = "review_overdue"
        recommendation = "review or retire overdue learning routine"
    elif not encounters:
        loop_state = "not_yet_used"
        recommendation = "watch future work for an encounter/use receipt"
    else:
        loop_state = "closed_loop_active"
        recommendation = "learning unit has evidence, future-use receipts, outcomes, and review coverage"

    return {
        "learning_event_id": learning_event_id,
        "read_only": True,
        "loop_state": loop_state,
        "recommendation": recommendation,
        "learned": {
            "decision_use": event.decision_use,
            "future_application_cue": event.future_application_cue,
            "learning_unit_kind": event.learning_unit_kind,
            "status": event.status,
            "approved_by": event.approved_by,
            "approval_ref": event.approval_ref,
            "owner_role": event.owner_role,
            "tenant_id": event.tenant_id,
            "project_id": event.project_id,
            "review_after_utc": event.review_after_utc,
        },
        "future_context": {
            "owner_role": event.owner_role,
            "cue": event.future_application_cue,
            "cue_signatures": sorted(_learning_event_cue_signatures(event)),
            "resource_refs": sorted(_learning_event_resource_refs(event)),
            "topology_refs": sorted(_learning_event_topology_refs(event)),
            "negative_cues": sorted(_learning_event_negative_cues(event)),
            "context_packet_refs": context_packet_refs,
            "verified_context_packet_refs": verified_context_packet_refs,
        },
        "evidence_refs": evidence_refs,
        "source_carrier_refs": event.source_carrier_refs,
        "derived_from_learning_event_ids": event.derived_from_learning_event_ids,
        "encounter_counts": encounter_counts,
        "encounters": [encounter.as_dict() for encounter in encounters],
        "outcome_link_count": len(outcome_links),
        "outcome_verdict_coverage": verdict_coverage,
        "outcome_verdict_counts": verdict_counts,
        "outcome_links": [link.as_dict() for link in outcome_links],
        "routine_review_count": len(routine_reviews),
        "overdue_review_ids": overdue_review_ids,
        "routine_reviews": [review.as_dict() for review in routine_reviews],
    }


def learning_event_from_candidate(
    candidate: Any,
    *,
    learning_unit_kind: LearningEventKind | str,
    decision_use: str,
    future_application_cue: str,
    approved_by: str,
    approval_ref: str,
    before_state: str | None = None,
    after_state: str | None = None,
    externality_review_ref: str | None = None,
    review_after_utc: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> ApprovedLearningEvent:
    """Promote a reviewed transition candidate into an approved event.

    This helper records the promotion. It does not apply the referenced mandate,
    route, charter, threshold, or policy-adapter change.
    """
    payload = candidate.as_dict() if hasattr(candidate, "as_dict") else dict(candidate)
    source_refs = _string_list(payload.get("source_refs") or [])
    object_ref = payload.get("object_ref")
    if object_ref:
        source_refs.append(str(object_ref))
    source_refs = list(dict.fromkeys(source_refs))
    return create_learning_event(
        learning_unit_kind=learning_unit_kind,
        decision_use=decision_use,
        future_application_cue=future_application_cue,
        approved_by=approved_by,
        approval_ref=approval_ref,
        source_carrier_refs=source_refs,
        candidate_ref=str(payload.get("candidate_id") or ""),
        before_state=before_state,
        after_state=after_state,
        owner_role=payload.get("suggested_owner_role"),
        tenant_id=tenant_id,
        project_id=project_id,
        externality_review_ref=externality_review_ref,
        review_after_utc=review_after_utc,
        metadata={
            "candidate_transition_kind": payload.get("transition_kind"),
            "candidate_source_kind": payload.get("source_kind"),
            "candidate_rationale": payload.get("rationale"),
            "candidate_proposed_payload": payload.get("proposed_payload") or {},
        },
        log_path=log_path,
    )


def learning_event_resource(event: ApprovedLearningEvent) -> KernelResource:
    """Project an approved learning event into the resource envelope.

    The JSONL row remains canonical. The resource shape is for adapters,
    dashboards, migrations, and conformance tests that need a portable view of
    one approved learning unit.
    """
    labels = {
        "learning_unit_kind": event.learning_unit_kind,
        "status": event.status,
        "approved_by": event.approved_by,
    }
    if event.owner_role:
        labels["owner_role"] = event.owner_role
    links: list[dict[str, str]] = [
        {"rel": "approval", "href": event.approval_ref},
    ]
    if event.candidate_ref:
        links.append({"rel": "candidate", "href": event.candidate_ref})
    if event.externality_review_ref:
        links.append({"rel": "externality_review", "href": event.externality_review_ref})
    for event_id in event.derived_from_learning_event_ids:
        links.append({"rel": "derived_from", "href": f"learning_event:{event_id}"})
    for ref in event.source_carrier_refs:
        links.append({"rel": "source_carrier", "href": ref})
    return make_resource(
        kind="LearningEvent",
        name=event.learning_event_id,
        resource_id=event.learning_event_id,
        tenant_id=event.tenant_id,
        project_id=event.project_id,
        stability="alpha",
        labels=labels,
        annotations={
            key: str(value)
            for key, value in event.metadata.items()
            if isinstance(key, str) and value is not None
        },
        spec={
            "learning_unit_kind": event.learning_unit_kind,
            "decision_use": event.decision_use,
            "future_application_cue": event.future_application_cue,
            "source_carrier_refs": event.source_carrier_refs,
            "derived_from_learning_event_ids": event.derived_from_learning_event_ids,
            "candidate_ref": event.candidate_ref,
            "before_state": event.before_state,
            "after_state": event.after_state,
            "owner_role": event.owner_role,
            "approval_ref": event.approval_ref,
            "externality_review_ref": event.externality_review_ref,
            "review_after_utc": event.review_after_utc,
        },
        status={
            "status": event.status,
            "created_at_utc": event.created_at_utc,
            "superseded_by": event.superseded_by,
            "retirement_reason": event.retirement_reason,
        },
        links=links,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_kind(kind: str) -> LearningEventKind:
    if kind not in VALID_EVENT_KINDS:
        raise ValueError(f"invalid learning_unit_kind {kind!r}; expected one of {sorted(VALID_EVENT_KINDS)}")
    return kind  # type: ignore[return-value]


def _validate_status(status: str) -> LearningEventStatus:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}; expected one of {sorted(VALID_STATUSES)}")
    return status  # type: ignore[return-value]


def _validate_encounter_outcome(outcome: str) -> LearningEncounterOutcome:
    if outcome not in VALID_ENCOUNTER_OUTCOMES:
        raise ValueError(
            f"invalid outcome {outcome!r}; expected one of {sorted(VALID_ENCOUNTER_OUTCOMES)}"
        )
    return outcome  # type: ignore[return-value]


def _encounter_idempotency_key(
    *,
    learning_event_id: str,
    role: str,
    cue: str,
    outcome: str,
    work_ref: str | None,
    tenant_id: str | None,
    project_id: str | None,
    context_packet_ref: str | None,
) -> str:
    payload = "\x1f".join(
        [
            learning_event_id,
            role,
            outcome,
            work_ref or "",
            context_packet_ref or "",
            tenant_id or "",
            project_id or "",
            cue.strip().lower(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _string_list(payload: Any) -> list[str]:
    if isinstance(payload, list):
        out: list[str] = []
        for item in payload:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    if payload:
        text = str(payload).strip()
        return [text] if text else []
    return []


def _clean_unique_strings(values: list[str], *, label: str) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            raise ValueError(f"{label} entries must be non-empty")
        if text not in out:
            out.append(text)
    return out


def _clean_optional_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in out:
            out.append(text)
    return out


def _learning_event_outcome_summary(
    *,
    event_ids: set[str],
    tenant_id: str | None,
    project_id: str | None,
    log_path: Path | None,
) -> tuple[int, float]:
    if not event_ids:
        return 0, 0.0
    from cognitive_firm.orchestration.outcome_links import (
        summarize_outcome_links,
        list_outcome_links,
    )

    links = [
        link
        for link in list_outcome_links(
            tenant_id=tenant_id,
            project_id=project_id,
            log_path=log_path,
        )
        if link.learning_event_id in event_ids
    ]
    summary = summarize_outcome_links(links=links)
    return len(links), summary.verdict_coverage


def _learning_event_review_summary(
    *,
    event_ids: set[str],
    tenant_id: str | None,
    project_id: str | None,
    log_path: Path | None,
) -> tuple[int, int, list[str]]:
    if not event_ids:
        return 0, 0, []
    from cognitive_firm.orchestration.routine_reviews import list_routine_reviews

    reviews = [
        review
        for review in list_routine_reviews(
            routine_kind="learning_event",
            tenant_id=tenant_id,
            project_id=project_id,
            log_path=log_path,
        )
        if review.learning_event_id in event_ids
    ]
    overdue = [review for review in reviews if review.is_overdue()]
    overdue_event_ids = sorted(
        {
            str(review.learning_event_id)
            for review in overdue
            if review.learning_event_id
        }
    )
    return len(reviews), len(overdue), overdue_event_ids


def _learning_summary_recommendation(
    *,
    active: int,
    overdue_count: int,
    outcome_link_count: int,
    outcome_verdict_coverage: float,
    events_with_encounters: int,
) -> str:
    if active == 0:
        return "review learning-transition candidates before claiming durable learning"
    if overdue_count:
        return "review or retire overdue learning routines"
    if outcome_link_count == 0:
        return "attach outcome links to approved learning units"
    if outcome_verdict_coverage < 1.0:
        return "record verdicts for open learning-unit outcome links"
    if events_with_encounters == 0:
        return "surface approved learning units in future work discovery"
    return "learning units are active, encountered, and outcome-linked"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage approved organizational learning events.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--status")
    list_parser.add_argument("--learning-unit-kind")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--log-path", type=Path)
    list_parser.add_argument("--resource", action="store_true", help="render resource envelopes")

    summary_parser = sub.add_parser("summary")
    summary_parser.add_argument("--tenant-id")
    summary_parser.add_argument("--project-id")
    summary_parser.add_argument("--log-path", type=Path)
    summary_parser.add_argument("--encounters-log-path", type=Path)
    summary_parser.add_argument("--outcome-links-log-path", type=Path)
    summary_parser.add_argument("--routine-reviews-log-path", type=Path)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--learning-unit-kind", required=True)
    create_parser.add_argument("--decision-use", required=True)
    create_parser.add_argument("--future-application-cue", required=True)
    create_parser.add_argument("--approved-by", required=True)
    create_parser.add_argument("--approval-ref", required=True)
    create_parser.add_argument("--source-carrier-ref", action="append", default=[])
    create_parser.add_argument("--derived-from-learning-event-id", action="append", default=[])
    create_parser.add_argument("--candidate-ref")
    create_parser.add_argument("--before-state")
    create_parser.add_argument("--after-state")
    create_parser.add_argument("--owner-role")
    create_parser.add_argument("--tenant-id")
    create_parser.add_argument("--project-id")
    create_parser.add_argument("--externality-review-ref")
    create_parser.add_argument("--review-after-utc")
    create_parser.add_argument("--log-path", type=Path)

    compound_parser = sub.add_parser("compound")
    compound_parser.add_argument("--source-learning-event-id", action="append", required=True)
    compound_parser.add_argument("--learning-unit-kind", required=True)
    compound_parser.add_argument("--decision-use", required=True)
    compound_parser.add_argument("--future-application-cue", required=True)
    compound_parser.add_argument("--approved-by", required=True)
    compound_parser.add_argument("--approval-ref", required=True)
    compound_parser.add_argument("--source-carrier-ref", action="append", default=[])
    compound_parser.add_argument("--candidate-ref")
    compound_parser.add_argument("--before-state")
    compound_parser.add_argument("--after-state")
    compound_parser.add_argument("--owner-role")
    compound_parser.add_argument("--tenant-id")
    compound_parser.add_argument("--project-id")
    compound_parser.add_argument("--externality-review-ref")
    compound_parser.add_argument("--review-after-utc")
    compound_parser.add_argument("--allow-inactive-source", action="store_true")
    compound_parser.add_argument("--log-path", type=Path)

    replay_parser = sub.add_parser("replay")
    replay_parser.add_argument("--role")
    replay_parser.add_argument("--tenant-id")
    replay_parser.add_argument("--project-id")
    replay_parser.add_argument("--cue")
    replay_parser.add_argument("--source-ref")
    replay_parser.add_argument("--tag")
    replay_parser.add_argument("--log-path", type=Path)

    retire_parser = sub.add_parser("retire")
    retire_parser.add_argument("learning_event_id")
    retire_parser.add_argument("--reason", required=True)
    retire_parser.add_argument("--log-path", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "list":
        events = list_learning_events(
            status=args.status,
            learning_unit_kind=args.learning_unit_kind,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
        )
        payload = [
            learning_event_resource(event).as_dict() if args.resource else event.as_dict()
            for event in events
        ]
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.cmd == "summary":
        summary = summarize_learning_events(
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
            encounters_log_path=args.encounters_log_path,
            outcome_links_log_path=args.outcome_links_log_path,
            routine_reviews_log_path=args.routine_reviews_log_path,
        )
        print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
        return 0

    if args.cmd == "replay":
        events = replay_learning_events(
            role=args.role,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            cue=args.cue,
            source_ref=args.source_ref,
            tag=args.tag,
            log_path=args.log_path,
        )
        print(json.dumps([event.as_dict() for event in events], indent=2, sort_keys=True))
        return 0

    if args.cmd == "retire":
        event = update_learning_event_status(
            args.learning_event_id,
            "retired",
            retirement_reason=args.reason,
            log_path=args.log_path,
        )
        print(json.dumps(event.as_dict(), indent=2, sort_keys=True))
        return 0

    if args.cmd == "compound":
        event = create_compounded_learning_event(
            source_learning_event_ids=args.source_learning_event_id,
            learning_unit_kind=args.learning_unit_kind,
            decision_use=args.decision_use,
            future_application_cue=args.future_application_cue,
            approved_by=args.approved_by,
            approval_ref=args.approval_ref,
            source_carrier_refs=args.source_carrier_ref,
            candidate_ref=args.candidate_ref,
            before_state=args.before_state,
            after_state=args.after_state,
            owner_role=args.owner_role,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            externality_review_ref=args.externality_review_ref,
            review_after_utc=args.review_after_utc,
            require_active_sources=not args.allow_inactive_source,
            log_path=args.log_path,
        )
        print(json.dumps(event.as_dict(), indent=2, sort_keys=True))
        return 0

    event = create_learning_event(
        learning_unit_kind=args.learning_unit_kind,
        decision_use=args.decision_use,
        future_application_cue=args.future_application_cue,
        approved_by=args.approved_by,
        approval_ref=args.approval_ref,
        source_carrier_refs=args.source_carrier_ref,
        derived_from_learning_event_ids=args.derived_from_learning_event_id,
        candidate_ref=args.candidate_ref,
        before_state=args.before_state,
        after_state=args.after_state,
        owner_role=args.owner_role,
        tenant_id=args.tenant_id,
        project_id=args.project_id,
        externality_review_ref=args.externality_review_ref,
        review_after_utc=args.review_after_utc,
        log_path=args.log_path,
    )
    print(json.dumps(event.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
