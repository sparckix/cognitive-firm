"""Tests for ``cognitive-firm-userland`` — the userland's terminal carrier."""

from __future__ import annotations

import pytest

from cognitive_firm.orchestration.human_work import create_human_work_session
from cognitive_firm.userland.cli import main


def test_vocabulary_prints_the_shared_glossary(capsys):
    rc = main(["vocabulary"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "userland vocabulary" in out
    assert "term(s):" in out
    # The L4 glossary is non-empty and renders label + definition lines.
    assert len(out.strip().splitlines()) > 1


def test_needs_me_for_an_actor_with_no_signals(capsys):
    rc = main(["needs-me", "human_nobody_home"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Nothing needs you right now." in out


def test_inbox_lists_a_member_humans_open_work(tmp_path, capsys):
    log = tmp_path / "human_work.jsonl"
    create_human_work_session(
        requested_by="research_office",
        human_actor="alice",
        objective="review the draft",
        work_mode="edit",
        bottleneck_class="taste",
        human_deliverable="annotated draft",
        deadline_utc="2026-06-01T00:00:00+00:00",
        log_path=log,
    )
    create_human_work_session(
        requested_by="research_office",
        human_actor="bob",
        objective="bob's unrelated task",
        work_mode="edit",
        bottleneck_class="taste",
        log_path=log,
    )

    rc = main(["inbox", "alice", "--human-work-log", str(log)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "alice — 1 open task(s):" in out
    assert "review the draft" in out
    assert "annotated draft" in out
    assert "2026-06-01T00:00:00+00:00" in out
    assert "bob's unrelated task" not in out


def test_inbox_for_an_actor_with_no_work(tmp_path, capsys):
    log = tmp_path / "human_work.jsonl"
    rc = main(["inbox", "ghost", "--human-work-log", str(log)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ghost has no open work." in out


def test_unknown_verb_exits_nonzero(capsys):
    with pytest.raises(SystemExit):
        main(["not-a-verb"])
