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
    metadata: dict[str, Any] = field(default_factory=dict)

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
        source_carrier_refs=source_carrier_refs or [],
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
    log_path: Path | None = None,
) -> list[ApprovedLearningEvent]:
    """Return active events relevant to a future work surface.

    This replay is deliberately lexical and metadata-bound. It does not use
    semantic similarity as authority.
    """
    events = list_learning_events(status="active", log_path=log_path)
    out: list[ApprovedLearningEvent] = []
    cue_text = cue.lower() if cue else None
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
        if cue_text:
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
    metadata: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    log_path: Path | None = None,
) -> LearningEventEncounter:
    """Record that future work encountered, applied, or ignored learning."""
    if not learning_event_id.strip():
        raise ValueError("learning_event_id is required")
    if not role.strip():
        raise ValueError("role is required")
    if not cue.strip():
        raise ValueError("cue is required")
    normalized = _validate_encounter_outcome(str(outcome))
    dedupe_key = idempotency_key or _encounter_idempotency_key(
        learning_event_id=learning_event_id,
        role=role,
        cue=cue,
        outcome=normalized,
        work_ref=work_ref,
        tenant_id=tenant_id,
        project_id=project_id,
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
        evidence_refs=evidence_refs or [],
        metadata={**(metadata or {}), "idempotency_key": dedupe_key},
    )
    _append_jsonl(path, encounter.as_dict())
    return encounter


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
) -> str:
    payload = "\x1f".join(
        [
            learning_event_id,
            role,
            outcome,
            work_ref or "",
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
        return [str(item) for item in payload if item]
    if payload:
        return [str(payload)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage approved organizational learning events.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--status")
    list_parser.add_argument("--learning-unit-kind")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--log-path", type=Path)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--learning-unit-kind", required=True)
    create_parser.add_argument("--decision-use", required=True)
    create_parser.add_argument("--future-application-cue", required=True)
    create_parser.add_argument("--approved-by", required=True)
    create_parser.add_argument("--approval-ref", required=True)
    create_parser.add_argument("--source-carrier-ref", action="append", default=[])
    create_parser.add_argument("--candidate-ref")
    create_parser.add_argument("--before-state")
    create_parser.add_argument("--after-state")
    create_parser.add_argument("--owner-role")
    create_parser.add_argument("--tenant-id")
    create_parser.add_argument("--project-id")
    create_parser.add_argument("--externality-review-ref")
    create_parser.add_argument("--review-after-utc")
    create_parser.add_argument("--log-path", type=Path)

    replay_parser = sub.add_parser("replay")
    replay_parser.add_argument("--role")
    replay_parser.add_argument("--tenant-id")
    replay_parser.add_argument("--project-id")
    replay_parser.add_argument("--cue")
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
        print(json.dumps([event.as_dict() for event in events], indent=2, sort_keys=True))
        return 0

    if args.cmd == "replay":
        events = replay_learning_events(
            role=args.role,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            cue=args.cue,
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

    event = create_learning_event(
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
        log_path=args.log_path,
    )
    print(json.dumps(event.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
