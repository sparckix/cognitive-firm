"""Tests for L2 (member-human face) — the work inbox."""

from __future__ import annotations

import pytest

from cognitive_firm.orchestration.human_work import create_human_work_session
from cognitive_firm.userland.work_inbox import claim, list_inbox, submit


def _new_session(log, *, human_actor="alice", objective="review the draft",
                 deadline=None):
    return create_human_work_session(
        requested_by="research_office",
        human_actor=human_actor,
        objective=objective,
        work_mode="edit",
        bottleneck_class="taste",
        deadline_utc=deadline,
        log_path=log,
    )


def test_list_inbox_shows_only_my_open_work(tmp_path):
    log = tmp_path / "human_work.jsonl"
    _new_session(log, human_actor="alice", objective="alice task")
    _new_session(log, human_actor="bob", objective="bob task")
    items = list_inbox(actor_id="alice", log_path=log)
    assert [i.objective for i in items] == ["alice task"]


def test_claim_moves_work_to_in_progress(tmp_path):
    log = tmp_path / "human_work.jsonl"
    session = _new_session(log)
    item = claim(session_id=session.session_id, actor_id="alice", log_path=log)
    assert item.state == "in_progress"


def test_claim_rejects_someone_elses_work(tmp_path):
    log = tmp_path / "human_work.jsonl"
    session = _new_session(log, human_actor="alice")
    with pytest.raises(ValueError):
        claim(session_id=session.session_id, actor_id="bob", log_path=log)


def test_claim_then_submit_completes_the_work(tmp_path):
    log = tmp_path / "human_work.jsonl"
    session = _new_session(log)
    claim(session_id=session.session_id, actor_id="alice", log_path=log)
    item = submit(
        session_id=session.session_id,
        actor_id="alice",
        receipt="edited draft attached",
        completion_summary="addressed the review notes",
        log_path=log,
    )
    assert item.state == "completed"


def test_submit_before_claim_is_an_illegal_transition(tmp_path):
    log = tmp_path / "human_work.jsonl"
    session = _new_session(log)  # state = requested
    with pytest.raises(ValueError):
        submit(
            session_id=session.session_id,
            actor_id="alice",
            receipt="x",
            completion_summary="y",
            log_path=log,
        )


def test_inbox_drops_completed_work(tmp_path):
    log = tmp_path / "human_work.jsonl"
    session = _new_session(log)
    claim(session_id=session.session_id, actor_id="alice", log_path=log)
    submit(
        session_id=session.session_id,
        actor_id="alice",
        receipt="r",
        completion_summary="c",
        log_path=log,
    )
    assert list_inbox(actor_id="alice", log_path=log) == []


def test_inbox_orders_by_deadline(tmp_path):
    log = tmp_path / "human_work.jsonl"
    _new_session(log, objective="late", deadline="2026-12-01T00:00:00+00:00")
    _new_session(log, objective="soon", deadline="2026-06-01T00:00:00+00:00")
    items = list_inbox(actor_id="alice", log_path=log)
    assert [i.objective for i in items] == ["soon", "late"]
