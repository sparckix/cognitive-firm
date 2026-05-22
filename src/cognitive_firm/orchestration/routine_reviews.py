"""Durable review-and-retirement lifecycle for organizational routines.

The kernel records *approved learning events* — durable changes to future
organizational behavior — but it only ever *adds* them. An approved routine
keeps firing as guidance long after the conditions that justified it have
changed. Nelson & Winter's account of organizational routines makes the same
point: routines persist because they are cheap to keep running, not because
they are continuously re-justified. Without an explicit forgetting step, a
kernel that only learns accumulates stale routines.

A :class:`RoutineReview` is the missing primitive. It lays a review schedule
*over* a durable routine (an approved learning event, or generically any
``routine_ref``) and gives the kernel three things it did not have:

- a ``review_due_utc`` deadline after which a routine is *overdue* for
  re-justification — the forgetting pressure, surfaced as a queryable failure;
- a typed review outcome — ``reaffirm``, ``amend``, ``retire``, ``escalate`` —
  so a review is a recorded decision, not a note;
- an explicit accountable ``retire`` transition that records who retired the
  routine and why.

Recording an outcome may schedule the *next* review, so a routine that should
survive stays continuously re-justified on a tenant-defined cadence.

CRITICAL BOUNDARY: the kernel owns the review schedule, the overdue surface,
and the typed transition. The tenant owns the review cadence policy and the
judgment of whether a routine still fits. This module references a learning
event by id; it does not edit ``learning_events.py`` and does not apply the
referenced routine change.

Every transition emits a canonical :class:`KernelEvent`, so the review
lifecycle is auditable through the same envelope as the rest of the kernel.
T1 uses the JSONL log; a T2 deployment puts the same rows behind the
transactional state backend with an identical function contract.
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.kernel_events import record_kernel_event


RoutineReviewStatus = Literal["scheduled", "in_review", "reviewed", "retired"]
RoutineReviewOutcome = Literal["reaffirm", "amend", "retire", "escalate"]
RoutineKind = Literal[
    "learning_event",
    "route_rule",
    "mandate_rule",
    "charter_rule",
    "evidence_standard",
    "review_threshold",
    "policy_adapter",
    "other",
]

DEFAULT_ROUTINE_REVIEWS_LOG = ORG_ROOT_DIR / "routine_reviews" / "routine_reviews.jsonl"

VALID_STATUSES = {"scheduled", "in_review", "reviewed", "retired"}
VALID_OUTCOMES = {"reaffirm", "amend", "retire", "escalate"}
VALID_ROUTINE_KINDS = {
    "learning_event",
    "route_rule",
    "mandate_rule",
    "charter_rule",
    "evidence_standard",
    "review_threshold",
    "policy_adapter",
    "other",
}
# ``retired`` is the accountable terminal state. ``reviewed`` is non-terminal:
# a reviewed routine can re-enter the schedule via the next cadence review.
TERMINAL_STATES = {"retired"}
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "scheduled": {"in_review", "retired"},
    "in_review": {"reviewed", "retired"},
    "reviewed": set(),
    "retired": set(),
}


@dataclass(frozen=True)
class RoutineReview:
    """A scheduled review of one durable routine.

    Canonical state. The overdue surface and the summary are read models
    derived from these rows and can always be rebuilt.
    """

    review_id: str
    routine_ref: str
    routine_kind: RoutineKind
    review_due_utc: str
    scheduled_by: str
    created_at_utc: str
    updated_at_utc: str
    status: RoutineReviewStatus = "scheduled"
    learning_event_id: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    reason: str | None = None
    review_cadence: str | None = None
    reviewer: str | None = None
    review_started_at_utc: str | None = None
    reviewed_at_utc: str | None = None
    outcome: RoutineReviewOutcome | None = None
    outcome_rationale: str | None = None
    outcome_evidence_refs: list[str] = field(default_factory=list)
    next_review_id: str | None = None
    retired_at_utc: str | None = None
    retired_by: str | None = None
    retirement_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    def is_overdue(self, *, now: datetime | None = None) -> bool:
        """Return whether this review is past its due date and still open.

        A retired or already-reviewed routine is not overdue: the forgetting
        pressure only applies to a routine still awaiting re-justification.
        """
        if self.status not in {"scheduled", "in_review"}:
            return False
        return _parse_iso(self.review_due_utc) <= (now or _now())


@dataclass(frozen=True)
class RoutineReviewSummary:
    """Read-side summary of routine forgetting pressure.

    Derived from routine-review rows; owns no facts and can be rebuilt.
    """

    total: int
    scheduled_count: int
    in_review_count: int
    reviewed_count: int
    retired_count: int
    overdue_count: int
    overdue_review_ids: list[str]
    recommendation: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# time + io helpers (kept module-local, matching the kernel's primitive style)
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _validate(value: str, allowed: set[str], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"invalid {label} {value!r}; expected one of {sorted(allowed)}")
    return value


def _emit(
    review: RoutineReview,
    *,
    verb: str,
    actor: str,
    extra: dict[str, Any] | None = None,
    kernel_events_log: Path | None = None,
) -> None:
    """Record a routine-review transition on the canonical kernel-event stream."""
    payload: dict[str, Any] = {
        "review_id": review.review_id,
        "routine_ref": review.routine_ref,
        "routine_kind": review.routine_kind,
        "status": review.status,
        "review_due_utc": review.review_due_utc,
    }
    for key in ("learning_event_id", "outcome", "next_review_id", "retirement_reason"):
        value = getattr(review, key)
        if value is not None:
            payload[key] = value
    if extra:
        payload.update(extra)
    record_kernel_event(
        actor=actor,
        verb=verb,
        object_ref=f"routine_review:{review.review_id}",
        subject_ref=f"routine:{review.routine_ref}",
        tenant_id=review.tenant_id,
        project_id=review.project_id,
        idempotency_key=f"{verb}:{review.review_id}:{review.updated_at_utc}",
        payload=payload,
        log_path=kernel_events_log,
    )


def _mutate(
    path: Path,
    review_id: str,
    mutate: Callable[[dict[str, Any]], dict[str, Any]],
) -> RoutineReview:
    """Apply ``mutate`` to one routine-review row in the JSONL projection."""
    rows = _read_jsonl(path)
    updated: RoutineReview | None = None
    next_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("review_id") == review_id:
            row = mutate(dict(row))
            updated = RoutineReview(**row)
        next_rows.append(row)
    if updated is None:
        raise KeyError(f"routine review not found: {review_id}")
    _write_jsonl(path, next_rows)
    return updated


def _require_transition(row: dict[str, Any], next_state: str) -> None:
    """Fail closed unless the row may move to ``next_state``."""
    current = str(row.get("status"))
    if current in TERMINAL_STATES:
        raise ValueError(f"{current} is terminal; no transitions allowed")
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if next_state not in allowed:
        raise ValueError(
            f"illegal transition {current} -> {next_state}; allowed: {sorted(allowed)}"
        )


# ---------------------------------------------------------------------------
# lifecycle operations
# ---------------------------------------------------------------------------


def schedule_routine_review(
    *,
    routine_ref: str,
    routine_kind: RoutineKind | str,
    review_due_utc: str,
    scheduled_by: str,
    learning_event_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    reason: str | None = None,
    review_cadence: str | None = None,
    metadata: dict[str, Any] | None = None,
    review_id: str | None = None,
    actor: str = "service.kernel",
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> RoutineReview:
    """Schedule a review of a durable routine by ``review_due_utc``.

    ``routine_ref`` is the generic, opaque reference to whatever routine is
    being reviewed. When the routine is an approved learning event, pass its id
    as ``learning_event_id`` as well so the review is joinable to that surface;
    the kernel does not read or mutate the learning event itself.
    """
    if not routine_ref.strip():
        raise ValueError("routine_ref is required")
    if not scheduled_by.strip():
        raise ValueError("scheduled_by is required")
    if not str(review_due_utc).strip():
        raise ValueError("review_due_utc is required")
    kind = _validate(str(routine_kind), VALID_ROUTINE_KINDS, "routine_kind")
    # Reject an unparseable due date now so overdue queries stay deterministic.
    try:
        datetime.fromisoformat(str(review_due_utc))
    except ValueError as exc:
        raise ValueError(f"review_due_utc is not an ISO-8601 timestamp: {review_due_utc!r}") from exc
    if kind == "learning_event" and not (learning_event_id or "").strip():
        raise ValueError("learning_event_id is required when routine_kind is learning_event")

    now = _now_iso()
    review = RoutineReview(
        review_id=review_id or f"rrev_{uuid.uuid4().hex[:12]}",
        routine_ref=routine_ref,
        routine_kind=kind,  # type: ignore[arg-type]
        review_due_utc=str(review_due_utc),
        scheduled_by=scheduled_by,
        created_at_utc=now,
        updated_at_utc=now,
        status="scheduled",
        learning_event_id=learning_event_id,
        tenant_id=tenant_id,
        project_id=project_id,
        reason=reason,
        review_cadence=review_cadence,
        metadata=dict(metadata or {}),
    )
    _append_jsonl(log_path or DEFAULT_ROUTINE_REVIEWS_LOG, review.as_dict())
    _emit(review, verb="routine_review.scheduled", actor=actor, kernel_events_log=kernel_events_log)
    return review


def start_routine_review(
    review_id: str,
    *,
    reviewer: str,
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> RoutineReview:
    """Move a scheduled review to ``in_review`` under a named reviewer."""
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    path = log_path or DEFAULT_ROUTINE_REVIEWS_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        _require_transition(row, "in_review")
        row["status"] = "in_review"
        row["reviewer"] = reviewer
        row["review_started_at_utc"] = _now_iso()
        row["updated_at_utc"] = _now_iso()
        return row

    review = _mutate(path, review_id, mutate)
    _emit(review, verb="routine_review.started", actor=reviewer, kernel_events_log=kernel_events_log)
    return review


def record_review_outcome(
    review_id: str,
    *,
    outcome: RoutineReviewOutcome | str,
    reviewer: str,
    rationale: str,
    evidence_refs: list[str] | None = None,
    next_review_due_utc: str | None = None,
    next_review_cadence: str | None = None,
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> RoutineReview:
    """Record a typed review outcome and optionally schedule the next review.

    Outcomes are ``reaffirm``, ``amend``, ``retire``, or ``escalate``. Recording
    an outcome moves the review to ``reviewed``; it does NOT itself retire the
    routine — an ``outcome="retire"`` is a recommendation, and the accountable
    terminal transition is :func:`retire_routine`. When ``next_review_due_utc``
    is given, a fresh ``scheduled`` review is created so a routine that should
    survive stays continuously re-justified on a cadence.

    A reviewer who starts a review and a reviewer who records its outcome
    should be the same person; the call validates the recording reviewer.
    """
    normalized = _validate(str(outcome), VALID_OUTCOMES, "outcome")
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    if not rationale.strip():
        raise ValueError("rationale is required")
    if next_review_due_utc is not None:
        try:
            datetime.fromisoformat(str(next_review_due_utc))
        except ValueError as exc:
            raise ValueError(
                f"next_review_due_utc is not an ISO-8601 timestamp: {next_review_due_utc!r}"
            ) from exc
    path = log_path or DEFAULT_ROUTINE_REVIEWS_LOG

    # The next cadence review is scheduled first so its id can be linked back
    # onto the reviewed row in the same mutation.
    next_review: RoutineReview | None = None
    captured: dict[str, Any] = {}

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        _require_transition(row, "reviewed")
        row["status"] = "reviewed"
        row["reviewer"] = reviewer
        row["outcome"] = normalized
        row["outcome_rationale"] = rationale
        if evidence_refs:
            existing = list(row.get("outcome_evidence_refs") or [])
            row["outcome_evidence_refs"] = list(dict.fromkeys(existing + evidence_refs))
        row["reviewed_at_utc"] = _now_iso()
        row["updated_at_utc"] = _now_iso()
        captured["routine_ref"] = row.get("routine_ref")
        captured["routine_kind"] = row.get("routine_kind")
        captured["learning_event_id"] = row.get("learning_event_id")
        captured["tenant_id"] = row.get("tenant_id")
        captured["project_id"] = row.get("project_id")
        captured["review_cadence"] = next_review_cadence or row.get("review_cadence")
        return row

    if next_review_due_utc is not None:
        # Read the source row to copy routine identity onto the next review.
        for row in _read_jsonl(path):
            if row.get("review_id") == review_id:
                next_review = schedule_routine_review(
                    routine_ref=str(row.get("routine_ref")),
                    routine_kind=str(row.get("routine_kind")),
                    review_due_utc=str(next_review_due_utc),
                    scheduled_by=reviewer,
                    learning_event_id=row.get("learning_event_id"),
                    tenant_id=row.get("tenant_id"),
                    project_id=row.get("project_id"),
                    reason=f"cadence review following {review_id}",
                    review_cadence=next_review_cadence or row.get("review_cadence"),
                    actor=reviewer,
                    log_path=path,
                    kernel_events_log=kernel_events_log,
                )
                break
        else:
            raise KeyError(f"routine review not found: {review_id}")

    def mutate_with_next(row: dict[str, Any]) -> dict[str, Any]:
        row = mutate(row)
        if next_review is not None:
            row["next_review_id"] = next_review.review_id
        return row

    review = _mutate(path, review_id, mutate_with_next)
    extra: dict[str, Any] = {"recommends_retirement": normalized == "retire"}
    if next_review is not None:
        extra["next_review_id"] = next_review.review_id
        extra["next_review_due_utc"] = next_review.review_due_utc
    _emit(
        review,
        verb="routine_review.outcome_recorded",
        actor=reviewer,
        extra=extra,
        kernel_events_log=kernel_events_log,
    )
    return review


def retire_routine(
    review_id: str,
    *,
    retired_by: str,
    reason: str,
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> RoutineReview:
    """Retire a routine: the accountable terminal transition.

    Retirement is the kernel's explicit forgetting step. It records the
    accountable actor and a reason, and it is reachable from ``scheduled`` or
    ``in_review`` — a routine can be retired without a full review when the
    accountable role decides it no longer fits. The kernel records the
    retirement of the *review*; it does not mutate the referenced learning
    event or apply the routine change.
    """
    if not retired_by.strip():
        raise ValueError("retired_by is required")
    if not reason.strip():
        raise ValueError("reason is required")
    path = log_path or DEFAULT_ROUTINE_REVIEWS_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        _require_transition(row, "retired")
        now = _now_iso()
        row["status"] = "retired"
        row["retired_at_utc"] = now
        row["retired_by"] = retired_by
        row["retirement_reason"] = reason
        if not row.get("outcome"):
            row["outcome"] = "retire"
        row["updated_at_utc"] = now
        return row

    review = _mutate(path, review_id, mutate)
    _emit(review, verb="routine_review.retired", actor=retired_by, kernel_events_log=kernel_events_log)
    return review


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------


def list_routine_reviews(
    *,
    status: RoutineReviewStatus | str | None = None,
    routine_kind: RoutineKind | str | None = None,
    learning_event_id: str | None = None,
    routine_ref: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> list[RoutineReview]:
    """Read routine reviews, optionally filtered."""
    if status is not None:
        status = _validate(str(status), VALID_STATUSES, "status")
    if routine_kind is not None:
        routine_kind = _validate(str(routine_kind), VALID_ROUTINE_KINDS, "routine_kind")
    out: list[RoutineReview] = []
    for row in _read_jsonl(log_path or DEFAULT_ROUTINE_REVIEWS_LOG):
        review = RoutineReview(**row)
        if status is not None and review.status != status:
            continue
        if routine_kind is not None and review.routine_kind != routine_kind:
            continue
        if learning_event_id is not None and review.learning_event_id != learning_event_id:
            continue
        if routine_ref is not None and review.routine_ref != routine_ref:
            continue
        if tenant_id is not None and review.tenant_id != tenant_id:
            continue
        if project_id is not None and review.project_id != project_id:
            continue
        out.append(review)
    return out


def get_routine_review(
    review_id: str,
    *,
    log_path: Path | None = None,
) -> RoutineReview | None:
    """Return one routine review by id, or ``None``."""
    for review in list_routine_reviews(log_path=log_path):
        if review.review_id == review_id:
            return review
    return None


def list_due_reviews(
    *,
    routine_kind: RoutineKind | str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    now: datetime | None = None,
    log_path: Path | None = None,
) -> list[RoutineReview]:
    """Return reviews that are overdue as of ``now``.

    This is the forgetting-pressure surface: every overdue review is a routine
    still firing as guidance that has not been re-justified by its deadline.
    Results are ordered most-overdue first.
    """
    moment = now or _now()
    overdue = [
        review
        for review in list_routine_reviews(
            routine_kind=routine_kind,
            tenant_id=tenant_id,
            project_id=project_id,
            log_path=log_path,
        )
        if review.is_overdue(now=moment)
    ]
    overdue.sort(key=lambda review: _parse_iso(review.review_due_utc))
    return overdue


def summarize_routine_reviews(
    *,
    reviews: list[RoutineReview] | None = None,
    now: datetime | None = None,
    log_path: Path | None = None,
) -> RoutineReviewSummary:
    """Summarize the routine-review population and its forgetting pressure."""
    moment = now or _now()
    rows = reviews if reviews is not None else list_routine_reviews(log_path=log_path)
    by_status = {state: 0 for state in VALID_STATUSES}
    overdue_ids: list[str] = []
    for review in rows:
        by_status[review.status] = by_status.get(review.status, 0) + 1
        if review.is_overdue(now=moment):
            overdue_ids.append(review.review_id)
    if overdue_ids:
        recommendation = (
            f"{len(overdue_ids)} routine(s) overdue for re-justification; "
            "review or retire before they keep firing as stale guidance"
        )
    elif by_status["scheduled"] or by_status["in_review"]:
        recommendation = "routine reviews on schedule; no overdue forgetting pressure"
    else:
        recommendation = "no open routine reviews"
    return RoutineReviewSummary(
        total=len(rows),
        scheduled_count=by_status["scheduled"],
        in_review_count=by_status["in_review"],
        reviewed_count=by_status["reviewed"],
        retired_count=by_status["retired"],
        overdue_count=len(overdue_ids),
        overdue_review_ids=overdue_ids,
        recommendation=recommendation,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage routine review-and-retirement lifecycle records."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    schedule = sub.add_parser("schedule")
    schedule.add_argument("--routine-ref", required=True)
    schedule.add_argument("--routine-kind", required=True)
    schedule.add_argument("--review-due-utc", required=True)
    schedule.add_argument("--scheduled-by", required=True)
    schedule.add_argument("--learning-event-id")
    schedule.add_argument("--tenant-id")
    schedule.add_argument("--project-id")
    schedule.add_argument("--reason")
    schedule.add_argument("--review-cadence")
    schedule.add_argument("--actor", default="service.kernel")
    schedule.add_argument("--log-path", type=Path)

    start = sub.add_parser("start")
    start.add_argument("review_id")
    start.add_argument("--reviewer", required=True)
    start.add_argument("--log-path", type=Path)

    outcome = sub.add_parser("record-outcome")
    outcome.add_argument("review_id")
    outcome.add_argument("--outcome", required=True)
    outcome.add_argument("--reviewer", required=True)
    outcome.add_argument("--rationale", required=True)
    outcome.add_argument("--evidence-ref", action="append", default=[])
    outcome.add_argument("--next-review-due-utc")
    outcome.add_argument("--next-review-cadence")
    outcome.add_argument("--log-path", type=Path)

    retire = sub.add_parser("retire")
    retire.add_argument("review_id")
    retire.add_argument("--retired-by", required=True)
    retire.add_argument("--reason", required=True)
    retire.add_argument("--log-path", type=Path)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--status")
    list_parser.add_argument("--routine-kind")
    list_parser.add_argument("--learning-event-id")
    list_parser.add_argument("--routine-ref")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--log-path", type=Path)

    due = sub.add_parser("list-due")
    due.add_argument("--routine-kind")
    due.add_argument("--tenant-id")
    due.add_argument("--project-id")
    due.add_argument("--log-path", type=Path)

    summary = sub.add_parser("summary")
    summary.add_argument("--log-path", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "schedule":
        review = schedule_routine_review(
            routine_ref=args.routine_ref,
            routine_kind=args.routine_kind,
            review_due_utc=args.review_due_utc,
            scheduled_by=args.scheduled_by,
            learning_event_id=args.learning_event_id,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            reason=args.reason,
            review_cadence=args.review_cadence,
            actor=args.actor,
            log_path=args.log_path,
        )
        print(json.dumps(review.as_dict(), indent=2, sort_keys=True))
        return 0
    if args.cmd == "start":
        review = start_routine_review(
            args.review_id, reviewer=args.reviewer, log_path=args.log_path
        )
        print(json.dumps(review.as_dict(), indent=2, sort_keys=True))
        return 0
    if args.cmd == "record-outcome":
        review = record_review_outcome(
            args.review_id,
            outcome=args.outcome,
            reviewer=args.reviewer,
            rationale=args.rationale,
            evidence_refs=args.evidence_ref or None,
            next_review_due_utc=args.next_review_due_utc,
            next_review_cadence=args.next_review_cadence,
            log_path=args.log_path,
        )
        print(json.dumps(review.as_dict(), indent=2, sort_keys=True))
        return 0
    if args.cmd == "retire":
        review = retire_routine(
            args.review_id,
            retired_by=args.retired_by,
            reason=args.reason,
            log_path=args.log_path,
        )
        print(json.dumps(review.as_dict(), indent=2, sort_keys=True))
        return 0
    if args.cmd == "list":
        reviews = list_routine_reviews(
            status=args.status,
            routine_kind=args.routine_kind,
            learning_event_id=args.learning_event_id,
            routine_ref=args.routine_ref,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
        )
        print(json.dumps([review.as_dict() for review in reviews], indent=2, sort_keys=True))
        return 0
    if args.cmd == "list-due":
        reviews = list_due_reviews(
            routine_kind=args.routine_kind,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
        )
        print(json.dumps([review.as_dict() for review in reviews], indent=2, sort_keys=True))
        return 0
    if args.cmd == "summary":
        summary_obj = summarize_routine_reviews(log_path=args.log_path)
        print(json.dumps(summary_obj.as_dict(), indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
