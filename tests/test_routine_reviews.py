from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration import routine_reviews as routine_reviews_module  # noqa: E402
from cognitive_firm.orchestration.kernel_events import list_kernel_events  # noqa: E402
from cognitive_firm.orchestration.routine_reviews import (  # noqa: E402
    get_routine_review,
    list_due_reviews,
    list_routine_reviews,
    record_review_outcome,
    retire_routine,
    schedule_routine_review,
    start_routine_review,
    summarize_routine_reviews,
)


class _Logs:
    """Bundle of temp log paths for one isolated routine-review world."""

    def __init__(self, tmp_path: Path):
        self.reviews = tmp_path / "routine_reviews.jsonl"
        self.events = tmp_path / "kernel_events.jsonl"


@pytest.fixture()
def logs(tmp_path: Path) -> _Logs:
    return _Logs(tmp_path)


def _future(days: int = 30) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _past(days: int = 30) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _schedule(logs: _Logs, **overrides):
    base = dict(
        routine_ref="routine.evidence_standard_v3",
        routine_kind="learning_event",
        review_due_utc=_future(),
        scheduled_by="role.strategy_office",
        learning_event_id="learn_abc123",
        review_cadence="P90D",
        log_path=logs.reviews,
        kernel_events_log=logs.events,
    )
    base.update(overrides)
    return schedule_routine_review(**base)


def test_schedule_creates_a_scheduled_review(logs: _Logs):
    review = _schedule(logs)
    assert review.status == "scheduled"
    assert review.routine_kind == "learning_event"
    assert review.learning_event_id == "learn_abc123"
    assert [r.review_id for r in list_routine_reviews(log_path=logs.reviews)] == [review.review_id]


def test_schedule_requires_learning_event_id_for_learning_event_kind(logs: _Logs):
    with pytest.raises(ValueError, match="learning_event_id is required"):
        _schedule(logs, learning_event_id=None)


def test_schedule_rejects_unparseable_due_date(logs: _Logs):
    with pytest.raises(ValueError, match="ISO-8601"):
        _schedule(logs, review_due_utc="not-a-date")


def test_schedule_rejects_unknown_routine_kind(logs: _Logs):
    with pytest.raises(ValueError, match="routine_kind"):
        _schedule(logs, routine_kind="not_a_kind", learning_event_id=None)


def test_overdue_review_is_surfaced_by_list_due_reviews(logs: _Logs):
    fresh = _schedule(logs, review_due_utc=_future())
    stale = _schedule(logs, review_due_utc=_past(), learning_event_id="learn_stale")

    due = list_due_reviews(log_path=logs.reviews)
    assert [r.review_id for r in due] == [stale.review_id]
    assert fresh.review_id not in {r.review_id for r in due}


def test_overdue_query_is_deterministic_with_monkeypatched_clock(logs: _Logs, monkeypatch):
    base = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(routine_reviews_module, "_now", lambda: base)
    due_soon = (base + timedelta(days=1)).isoformat()
    review = _schedule(logs, review_due_utc=due_soon)
    assert list_due_reviews(log_path=logs.reviews) == []

    # Advance the clock past the due date: the review is now overdue.
    monkeypatch.setattr(routine_reviews_module, "_now", lambda: base + timedelta(days=2))
    due = list_due_reviews(log_path=logs.reviews)
    assert [r.review_id for r in due] == [review.review_id]


def test_reaffirm_outcome_moves_review_to_reviewed(logs: _Logs):
    review = _schedule(logs)
    started = start_routine_review(review.review_id, reviewer="role.reviewer", log_path=logs.reviews,
                                   kernel_events_log=logs.events)
    assert started.status == "in_review"
    reviewed = record_review_outcome(
        review.review_id,
        outcome="reaffirm",
        reviewer="role.reviewer",
        rationale="still fits current conditions",
        log_path=logs.reviews,
        kernel_events_log=logs.events,
    )
    assert reviewed.status == "reviewed"
    assert reviewed.outcome == "reaffirm"


def test_each_review_outcome_is_accepted(logs: _Logs):
    for outcome in ("reaffirm", "amend", "retire", "escalate"):
        review = _schedule(logs, learning_event_id=f"learn_{outcome}")
        start_routine_review(review.review_id, reviewer="role.reviewer", log_path=logs.reviews,
                             kernel_events_log=logs.events)
        reviewed = record_review_outcome(
            review.review_id,
            outcome=outcome,
            reviewer="role.reviewer",
            rationale=f"{outcome} decision",
            log_path=logs.reviews,
            kernel_events_log=logs.events,
        )
        assert reviewed.outcome == outcome
        assert reviewed.status == "reviewed"


def test_record_outcome_rejects_unknown_outcome(logs: _Logs):
    review = _schedule(logs)
    start_routine_review(review.review_id, reviewer="role.reviewer", log_path=logs.reviews,
                         kernel_events_log=logs.events)
    with pytest.raises(ValueError, match="outcome"):
        record_review_outcome(
            review.review_id,
            outcome="maybe",
            reviewer="role.reviewer",
            rationale="x",
            log_path=logs.reviews,
            kernel_events_log=logs.events,
        )


def test_illegal_transition_from_scheduled_to_reviewed_is_rejected(logs: _Logs):
    review = _schedule(logs)
    with pytest.raises(ValueError, match="illegal transition"):
        record_review_outcome(
            review.review_id,
            outcome="reaffirm",
            reviewer="role.reviewer",
            rationale="skipped in_review",
            log_path=logs.reviews,
            kernel_events_log=logs.events,
        )


def test_reviewed_is_terminal_for_further_outcomes(logs: _Logs):
    review = _schedule(logs)
    start_routine_review(review.review_id, reviewer="role.reviewer", log_path=logs.reviews,
                         kernel_events_log=logs.events)
    record_review_outcome(
        review.review_id, outcome="amend", reviewer="role.reviewer", rationale="amend",
        log_path=logs.reviews, kernel_events_log=logs.events,
    )
    with pytest.raises(ValueError, match="illegal transition"):
        start_routine_review(review.review_id, reviewer="role.reviewer", log_path=logs.reviews,
                             kernel_events_log=logs.events)


def test_retire_records_accountable_actor_and_reason(logs: _Logs):
    review = _schedule(logs)
    retired = retire_routine(
        review.review_id,
        retired_by="role.accountable_owner",
        reason="superseded by new evidence standard",
        log_path=logs.reviews,
        kernel_events_log=logs.events,
    )
    assert retired.status == "retired"
    assert retired.retired_by == "role.accountable_owner"
    assert retired.retirement_reason == "superseded by new evidence standard"
    assert retired.retired_at_utc is not None
    assert retired.outcome == "retire"


def test_retire_is_terminal(logs: _Logs):
    review = _schedule(logs)
    retire_routine(review.review_id, retired_by="role.owner", reason="stale",
                   log_path=logs.reviews, kernel_events_log=logs.events)
    with pytest.raises(ValueError, match="terminal"):
        retire_routine(review.review_id, retired_by="role.owner", reason="again",
                       log_path=logs.reviews, kernel_events_log=logs.events)


def test_retire_requires_a_reason(logs: _Logs):
    review = _schedule(logs)
    with pytest.raises(ValueError, match="reason is required"):
        retire_routine(review.review_id, retired_by="role.owner", reason="  ",
                       log_path=logs.reviews, kernel_events_log=logs.events)


def test_recording_outcome_schedules_the_next_cadence_review(logs: _Logs):
    review = _schedule(logs)
    start_routine_review(review.review_id, reviewer="role.reviewer", log_path=logs.reviews,
                         kernel_events_log=logs.events)
    next_due = _future(120)
    reviewed = record_review_outcome(
        review.review_id,
        outcome="reaffirm",
        reviewer="role.reviewer",
        rationale="still fits; re-review in a quarter",
        next_review_due_utc=next_due,
        log_path=logs.reviews,
        kernel_events_log=logs.events,
    )
    assert reviewed.next_review_id is not None
    next_review = get_routine_review(reviewed.next_review_id, log_path=logs.reviews)
    assert next_review is not None
    assert next_review.status == "scheduled"
    assert next_review.routine_ref == review.routine_ref
    assert next_review.learning_event_id == review.learning_event_id
    assert next_review.review_due_utc == next_due


def test_list_routine_reviews_filters_by_status_and_learning_event(logs: _Logs):
    a = _schedule(logs, learning_event_id="learn_a")
    _schedule(logs, learning_event_id="learn_b")
    retire_routine(a.review_id, retired_by="role.owner", reason="stale",
                   log_path=logs.reviews, kernel_events_log=logs.events)

    retired = list_routine_reviews(status="retired", log_path=logs.reviews)
    assert [r.review_id for r in retired] == [a.review_id]
    by_event = list_routine_reviews(learning_event_id="learn_b", log_path=logs.reviews)
    assert {r.learning_event_id for r in by_event} == {"learn_b"}
    by_kind = list_routine_reviews(routine_kind="learning_event", log_path=logs.reviews)
    assert len(by_kind) == 2


def test_summary_counts_scheduled_overdue_and_retired(logs: _Logs):
    _schedule(logs, review_due_utc=_future(), learning_event_id="learn_fresh")
    overdue = _schedule(logs, review_due_utc=_past(), learning_event_id="learn_overdue")
    gone = _schedule(logs, review_due_utc=_future(), learning_event_id="learn_gone")
    retire_routine(gone.review_id, retired_by="role.owner", reason="stale",
                   log_path=logs.reviews, kernel_events_log=logs.events)

    summary = summarize_routine_reviews(log_path=logs.reviews)
    assert summary.total == 3
    assert summary.scheduled_count == 2
    assert summary.retired_count == 1
    assert summary.overdue_count == 1
    assert summary.overdue_review_ids == [overdue.review_id]
    assert "overdue" in summary.recommendation


def test_every_transition_emits_a_kernel_event(logs: _Logs):
    review = _schedule(logs)
    start_routine_review(review.review_id, reviewer="role.reviewer", log_path=logs.reviews,
                         kernel_events_log=logs.events)
    record_review_outcome(
        review.review_id, outcome="reaffirm", reviewer="role.reviewer", rationale="fits",
        log_path=logs.reviews, kernel_events_log=logs.events,
    )

    verbs = [
        event.verb
        for event in list_kernel_events(
            object_ref=f"routine_review:{review.review_id}", log_path=logs.events
        )
    ]
    assert verbs == [
        "routine_review.scheduled",
        "routine_review.started",
        "routine_review.outcome_recorded",
    ]


def test_retire_emits_a_kernel_event(logs: _Logs):
    review = _schedule(logs)
    retire_routine(review.review_id, retired_by="role.owner", reason="stale",
                   log_path=logs.reviews, kernel_events_log=logs.events)
    verbs = [
        event.verb
        for event in list_kernel_events(
            object_ref=f"routine_review:{review.review_id}", log_path=logs.events
        )
    ]
    assert verbs == ["routine_review.scheduled", "routine_review.retired"]
