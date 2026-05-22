from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.kernel_events import list_kernel_events  # noqa: E402
from cognitive_firm.orchestration.outcome_links import (  # noqa: E402
    create_outcome_link,
    get_outcome_link,
    list_outcome_links,
    record_metric_snapshot,
    record_verdict,
    summarize_outcome_links,
    void_outcome_link,
)


class _Logs:
    """Bundle of temp log paths for one isolated outcome-link world."""

    def __init__(self, tmp_path: Path):
        self.links = tmp_path / "outcome_links.jsonl"
        self.events = tmp_path / "kernel_events.jsonl"


@pytest.fixture()
def logs(tmp_path: Path) -> _Logs:
    return _Logs(tmp_path)


def _create(logs: _Logs, **overrides):
    base = dict(
        change_ref="learning_event:learn_abc",
        change_kind="learning_event",
        metric_name="rework_rate",
        metric_unit="ratio",
        created_by="role.quality_office",
        learning_event_id="learn_abc",
        tenant_id="tenant_x",
        project_id="proj_1",
        log_path=logs.links,
        kernel_events_log=logs.events,
    )
    base.update(overrides)
    return create_outcome_link(**base)


def _baseline(logs: _Logs, link, value: float = 0.40):
    return record_metric_snapshot(
        link.outcome_link_id,
        kind="baseline",
        value=value,
        captured_by="role.quality_office",
        log_path=logs.links,
        kernel_events_log=logs.events,
    )


def _post(logs: _Logs, link, value: float = 0.22):
    return record_metric_snapshot(
        link.outcome_link_id,
        kind="post",
        value=value,
        captured_by="role.quality_office",
        log_path=logs.links,
        kernel_events_log=logs.events,
    )


def test_create_opens_an_outcome_link(logs: _Logs):
    link = _create(logs)
    assert link.status == "open"
    assert link.baseline is None
    assert link.post_snapshots == []
    assert link.verdict is None
    assert get_outcome_link(link.outcome_link_id, log_path=logs.links) is not None


def test_create_validates_required_fields(logs: _Logs):
    with pytest.raises(ValueError, match="metric_name"):
        _create(logs, metric_name="  ")
    with pytest.raises(ValueError, match="change_ref"):
        _create(logs, change_ref="")


def test_baseline_snapshot_moves_link_to_measuring(logs: _Logs):
    link = _create(logs)
    measured = _baseline(logs, link)
    assert measured.status == "measuring"
    assert measured.baseline is not None
    assert measured.baseline["value"] == 0.40
    assert measured.baseline["kind"] == "baseline"


def test_post_snapshot_requires_a_baseline_first(logs: _Logs):
    link = _create(logs)
    with pytest.raises(ValueError, match="baseline snapshot before"):
        _post(logs, link)


def test_second_baseline_is_rejected(logs: _Logs):
    link = _create(logs)
    _baseline(logs, link)
    with pytest.raises(ValueError, match="already has a baseline"):
        _baseline(logs, link, value=0.50)


def test_post_snapshots_accumulate(logs: _Logs):
    link = _create(logs)
    _baseline(logs, link)
    _post(logs, link, value=0.30)
    after = _post(logs, link, value=0.22)
    assert len(after.post_snapshots) == 2
    assert [s["value"] for s in after.post_snapshots] == [0.30, 0.22]


def test_verdict_lifecycle_terminates_the_link(logs: _Logs):
    link = _create(logs)
    _baseline(logs, link)
    _post(logs, link)
    final = record_verdict(
        link.outcome_link_id,
        verdict="improved",
        recorded_by="role.quality_office",
        rationale="rework rate fell from 0.40 to 0.22 after the routine change",
        log_path=logs.links,
        kernel_events_log=logs.events,
    )
    assert final.status == "verdict_recorded"
    assert final.verdict == "improved"
    assert final.verdict_recorded_by == "role.quality_office"
    assert final.verdict_recorded_at_utc is not None


def test_verdict_requires_a_baseline_and_post_snapshot(logs: _Logs):
    link = _create(logs)
    # No measurement at all.
    with pytest.raises(ValueError, match="measuring link"):
        record_verdict(
            link.outcome_link_id,
            verdict="improved",
            recorded_by="role.quality_office",
            rationale="too early",
            log_path=logs.links,
            kernel_events_log=logs.events,
        )
    # Baseline only, no post snapshot.
    _baseline(logs, link)
    with pytest.raises(ValueError, match="post-change snapshot"):
        record_verdict(
            link.outcome_link_id,
            verdict="improved",
            recorded_by="role.quality_office",
            rationale="still too early",
            log_path=logs.links,
            kernel_events_log=logs.events,
        )


def test_illegal_transitions_on_terminal_links(logs: _Logs):
    link = _create(logs)
    _baseline(logs, link)
    _post(logs, link)
    record_verdict(
        link.outcome_link_id,
        verdict="no_change",
        recorded_by="role.quality_office",
        rationale="no measurable movement",
        log_path=logs.links,
        kernel_events_log=logs.events,
    )
    # A verdict-recorded link is terminal.
    with pytest.raises(ValueError, match="verdict_recorded"):
        _post(logs, link, value=0.10)
    with pytest.raises(ValueError, match="verdict_recorded"):
        record_verdict(
            link.outcome_link_id,
            verdict="improved",
            recorded_by="role.quality_office",
            rationale="changed my mind",
            log_path=logs.links,
            kernel_events_log=logs.events,
        )
    with pytest.raises(ValueError, match="verdict_recorded"):
        void_outcome_link(
            link.outcome_link_id,
            reason="too late",
            log_path=logs.links,
            kernel_events_log=logs.events,
        )


def test_void_terminates_an_open_link(logs: _Logs):
    link = _create(logs)
    voided = void_outcome_link(
        link.outcome_link_id,
        reason="change was reverted before measurement",
        log_path=logs.links,
        kernel_events_log=logs.events,
    )
    assert voided.status == "voided"
    assert voided.void_reason == "change was reverted before measurement"
    with pytest.raises(ValueError, match="voided"):
        void_outcome_link(
            link.outcome_link_id,
            reason="again",
            log_path=logs.links,
            kernel_events_log=logs.events,
        )


def test_list_filters_by_status_verdict_and_learning_event(logs: _Logs):
    open_link = _create(logs, change_ref="learning_event:l1", learning_event_id="l1")
    done = _create(logs, change_ref="learning_event:l2", learning_event_id="l2")
    _baseline(logs, done)
    _post(logs, done)
    record_verdict(
        done.outcome_link_id,
        verdict="regressed",
        recorded_by="role.quality_office",
        rationale="metric got worse",
        log_path=logs.links,
        kernel_events_log=logs.events,
    )

    assert {l.outcome_link_id for l in list_outcome_links(status="open", log_path=logs.links)} == {
        open_link.outcome_link_id
    }
    regressed = list_outcome_links(verdict="regressed", log_path=logs.links)
    assert [l.outcome_link_id for l in regressed] == [done.outcome_link_id]
    by_event = list_outcome_links(learning_event_id="l1", log_path=logs.links)
    assert [l.outcome_link_id for l in by_event] == [open_link.outcome_link_id]
    with pytest.raises(ValueError, match="invalid status"):
        list_outcome_links(status="not_a_status", log_path=logs.links)


def test_summary_read_model_counts(logs: _Logs):
    # improved
    a = _create(logs, change_ref="c:a")
    _baseline(logs, a)
    _post(logs, a)
    record_verdict(
        a.outcome_link_id,
        verdict="improved",
        recorded_by="role.q",
        rationale="better",
        log_path=logs.links,
        kernel_events_log=logs.events,
    )
    # regressed
    b = _create(logs, change_ref="c:b")
    _baseline(logs, b)
    _post(logs, b)
    record_verdict(
        b.outcome_link_id,
        verdict="regressed",
        recorded_by="role.q",
        rationale="worse",
        log_path=logs.links,
        kernel_events_log=logs.events,
    )
    # still measuring
    c = _create(logs, change_ref="c:c")
    _baseline(logs, c)
    # still open
    _create(logs, change_ref="c:d")
    # voided
    e = _create(logs, change_ref="c:e")
    void_outcome_link(
        e.outcome_link_id,
        reason="reverted",
        log_path=logs.links,
        kernel_events_log=logs.events,
    )

    summary = summarize_outcome_links(log_path=logs.links)
    assert summary.total == 5
    assert summary.improved == 1
    assert summary.regressed == 1
    assert summary.measuring == 1
    assert summary.open == 1
    assert summary.voided == 1
    assert summary.verdict_recorded == 2
    assert summary.awaiting_verdict == 2
    # 2 verdicts of 4 non-voided links.
    assert summary.verdict_coverage == 0.5


def test_summary_empty_world_has_zero_coverage(logs: _Logs):
    summary = summarize_outcome_links(log_path=logs.links)
    assert summary.total == 0
    assert summary.verdict_coverage == 0.0


def test_every_transition_emits_a_kernel_event(logs: _Logs):
    link = _create(logs)
    _baseline(logs, link)
    _post(logs, link)
    record_verdict(
        link.outcome_link_id,
        verdict="improved",
        recorded_by="role.quality_office",
        rationale="rework rate dropped",
        log_path=logs.links,
        kernel_events_log=logs.events,
    )
    verbs = [
        event.verb
        for event in list_kernel_events(
            object_ref=f"outcome_link:{link.outcome_link_id}", log_path=logs.events
        )
    ]
    assert verbs == [
        "outcome_link.created",
        "outcome_link.snapshot_recorded",
        "outcome_link.snapshot_recorded",
        "outcome_link.verdict_recorded",
    ]


def test_void_emits_a_kernel_event(logs: _Logs):
    link = _create(logs)
    void_outcome_link(
        link.outcome_link_id,
        reason="opened in error",
        log_path=logs.links,
        kernel_events_log=logs.events,
    )
    verbs = [
        event.verb
        for event in list_kernel_events(
            object_ref=f"outcome_link:{link.outcome_link_id}", log_path=logs.events
        )
    ]
    assert verbs == ["outcome_link.created", "outcome_link.voided"]
