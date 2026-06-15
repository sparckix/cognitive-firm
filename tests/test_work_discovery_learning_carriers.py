from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration import evidence_gaps, goals_inbox, human_work, learning_events, work_discovery  # noqa: E402
from cognitive_firm.orchestration.evidence_gaps import create_evidence_gap  # noqa: E402
from cognitive_firm.orchestration.human_work import (  # noqa: E402
    create_agent_requested_human_work_session,
    create_human_work_session,
    update_human_work_state,
)
from cognitive_firm.orchestration.learning_events import create_learning_event  # noqa: E402
from cognitive_firm.orchestration.learning_events import list_learning_event_encounters  # noqa: E402
from cognitive_firm.orchestration.outcome_links import create_outcome_link  # noqa: E402
from cognitive_firm.orchestration.routine_reviews import schedule_routine_review  # noqa: E402
from cognitive_firm.orchestration.work_discovery import (  # noqa: E402
    build_role_learning_context,
    discover_all,
    discover_evidence_gaps,
    discover_human_work_sessions,
    discover_open_debates,
    discover_principal_goals,
    discover_relevant_learning_events,
)


def test_work_discovery_surfaces_blocking_evidence_gaps(tmp_path: Path, monkeypatch):
    log = tmp_path / "evidence_gaps.jsonl"
    monkeypatch.setattr(evidence_gaps, "DEFAULT_EVIDENCE_GAPS_LOG", log)
    gap = create_evidence_gap(
        gap_type="missing_source",
        target="main claim",
        description="Need a source before work continues.",
        severity="blocking",
        producer="reviewer",
        log_path=log,
    )

    candidates = discover_evidence_gaps(max_per_source=5)

    assert len(candidates) == 1
    assert candidates[0].source == "evidence-gap"
    assert candidates[0].severity == "critical"
    assert candidates[0].metadata["gap_id"] == gap.gap_id


def test_work_discovery_surfaces_completed_human_work_for_integration(tmp_path: Path, monkeypatch):
    log = tmp_path / "human_work.jsonl"
    monkeypatch.setattr(human_work, "DEFAULT_HUMAN_WORK_LOG", log)
    session = create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="check restricted source",
        work_mode="source_check",
        bottleneck_class="access",
        collaborating_roles=["role.manager"],
        log_path=log,
    )
    update_human_work_state(session.session_id, "claimed", log_path=log)
    update_human_work_state(session.session_id, "in_progress", log_path=log)
    update_human_work_state(
        session.session_id,
        "completed",
        completion_summary="Source confirms the claim.",
        receipt="private-source-note",
        log_path=log,
    )

    candidates = discover_human_work_sessions(assigned_to="role.manager", max_per_source=5)

    assert len(candidates) == 1
    assert candidates[0].source == "human-work"
    assert "integrate completed human work" in candidates[0].intent
    assert candidates[0].metadata["session_id"] == session.session_id


def test_principal_goal_discovery_preserves_declared_paths(tmp_path: Path, monkeypatch):
    goals_root = tmp_path / "tasks"
    pending = goals_root / "pending"
    pending.mkdir(parents=True)
    monkeypatch.setattr(goals_inbox, "GOALS_ROOT", goals_root)
    (pending / "adjust-mandate.md").write_text(
        """
---
goal_id: adjust-mandate
priority: high
assigned_to: role.org_evolver
autonomous_scope_ok: true
estimated_cost_usd: 0.0
declared_paths:
  - org/mandates/org_evolver_mandate.md
---

Review the mandate and report the next bounded improvement candidate.
""".lstrip(),
        encoding="utf-8",
    )

    candidates = discover_principal_goals(assigned_to="role.org_evolver")

    assert len(candidates) == 1
    assert candidates[0].source == "principal-goal"
    assert candidates[0].metadata["declared_paths"] == [
        "org/mandates/org_evolver_mandate.md"
    ]


def test_work_discovery_routes_a2h_followup_to_agent_counterparty(tmp_path: Path, monkeypatch):
    log = tmp_path / "human_work.jsonl"
    monkeypatch.setattr(human_work, "DEFAULT_HUMAN_WORK_LOG", log)
    session = create_agent_requested_human_work_session(
        requested_by_role="role.researcher",
        human_actor="principal",
        objective="Check private source and report whether it supports claim C.",
        work_mode="source_check",
        bottleneck_class="access",
        human_deliverable="source support claim",
        receipt_required=True,
        receipt_type="note",
        log_path=log,
    )

    assert discover_human_work_sessions(assigned_to="role.researcher", max_per_source=5) == []

    update_human_work_state(session.session_id, "claimed", log_path=log)
    update_human_work_state(session.session_id, "in_progress", log_path=log)
    update_human_work_state(
        session.session_id,
        "completed",
        completion_summary="Source supports claim C.",
        receipt="source note",
        log_path=log,
    )

    candidates = discover_human_work_sessions(assigned_to="role.researcher", max_per_source=5)

    assert len(candidates) == 1
    assert candidates[0].metadata["session_id"] == session.session_id
    assert candidates[0].metadata["coordination_pattern"] == "a2h_work_request"
    assert candidates[0].metadata["agent_counterparty_role"] == "role.researcher"
    assert "A2H follow-up" in candidates[0].intent


def test_discover_all_includes_learning_carriers(tmp_path: Path, monkeypatch):
    gaps_log = tmp_path / "evidence_gaps.jsonl"
    human_log = tmp_path / "human_work.jsonl"
    learning_log = tmp_path / "learning_events.jsonl"
    encounter_log = tmp_path / "learning_encounters.jsonl"
    monkeypatch.setattr(evidence_gaps, "DEFAULT_EVIDENCE_GAPS_LOG", gaps_log)
    monkeypatch.setattr(human_work, "DEFAULT_HUMAN_WORK_LOG", human_log)
    monkeypatch.setattr(learning_events, "DEFAULT_LEARNING_EVENTS_LOG", learning_log)
    monkeypatch.setattr(learning_events, "DEFAULT_LEARNING_ENCOUNTERS_LOG", encounter_log)
    create_evidence_gap(
        gap_type="missing_source",
        target="unsupported comparator claim",
        description="Need a source before this comparator claim continues.",
        severity="blocking",
        producer="reviewer",
        log_path=gaps_log,
    )
    create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="verify restricted source",
        work_mode="source_check",
        bottleneck_class="access",
        collaborating_roles=["role.manager"],
        log_path=human_log,
    )
    create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Require a source note before repeating this pattern.",
        future_application_cue="unsupported comparator claim",
        approved_by="role.manager",
        approval_ref="review/1",
        owner_role="role.manager",
        log_path=learning_log,
    )

    candidates = discover_all(assigned_to="role.manager", record_learning_encounters=True)
    sources = [candidate.source for candidate in candidates]

    assert "evidence-gap" in sources
    assert "human-work" in sources
    evidence_candidate = next(candidate for candidate in candidates if candidate.source == "evidence-gap")
    assert evidence_candidate.metadata["learning_event_refs"]
    encounters = list_learning_event_encounters(log_path=encounter_log)
    assert encounters
    assert encounters[0].outcome == "encountered"


def test_discover_all_does_not_attach_other_tenant_learning(tmp_path: Path, monkeypatch):
    gaps_log = tmp_path / "evidence_gaps.jsonl"
    learning_log = tmp_path / "learning_events.jsonl"
    encounter_log = tmp_path / "learning_encounters.jsonl"
    monkeypatch.setattr(evidence_gaps, "DEFAULT_EVIDENCE_GAPS_LOG", gaps_log)
    monkeypatch.setattr(learning_events, "DEFAULT_LEARNING_EVENTS_LOG", learning_log)
    monkeypatch.setattr(learning_events, "DEFAULT_LEARNING_ENCOUNTERS_LOG", encounter_log)
    create_evidence_gap(
        gap_type="missing_source",
        target="unsupported comparator claim",
        description="Need a source before this comparator claim continues.",
        severity="blocking",
        producer="reviewer",
        owner_role="role.manager",
        tenant_id="tenant-b",
        log_path=gaps_log,
    )
    create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Require a source note before repeating this pattern.",
        future_application_cue="unsupported comparator claim",
        approved_by="role.manager",
        approval_ref="review/1",
        owner_role="role.manager",
        tenant_id="tenant-a",
        log_path=learning_log,
    )

    candidates = discover_all(assigned_to="role.manager", record_learning_encounters=True)

    assert candidates
    assert all(not candidate.metadata.get("learning_event_refs") for candidate in candidates)
    assert list_learning_event_encounters(log_path=encounter_log) == []


def test_learning_encounter_work_refs_are_candidate_specific(tmp_path: Path, monkeypatch):
    gaps_log = tmp_path / "evidence_gaps.jsonl"
    learning_log = tmp_path / "learning_events.jsonl"
    encounter_log = tmp_path / "learning_encounters.jsonl"
    monkeypatch.setattr(evidence_gaps, "DEFAULT_EVIDENCE_GAPS_LOG", gaps_log)
    monkeypatch.setattr(learning_events, "DEFAULT_LEARNING_EVENTS_LOG", learning_log)
    monkeypatch.setattr(learning_events, "DEFAULT_LEARNING_ENCOUNTERS_LOG", encounter_log)
    for target in ["claim one", "claim two"]:
        create_evidence_gap(
            gap_type="missing_source",
            target=target,
            description="Need a source before this comparator claim continues.",
            severity="blocking",
            producer="reviewer",
            owner_role="role.manager",
            tenant_id="tenant-a",
            log_path=gaps_log,
        )
    create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Require a source note before comparator claims.",
        future_application_cue="comparator claim",
        approved_by="role.manager",
        approval_ref="review/1",
        owner_role="role.manager",
        tenant_id="tenant-a",
        log_path=learning_log,
    )

    discover_all(
        assigned_to="role.manager",
        tenant_id="tenant-a",
        record_learning_encounters=True,
    )

    encounters = list_learning_event_encounters(log_path=encounter_log)
    assert len(encounters) == 2
    assert {row.work_ref for row in encounters} == {
        f"evidence-gap:{candidate.metadata['gap_id']}"
        for candidate in discover_evidence_gaps(assigned_to="role.manager", max_per_source=5)
    }


def test_discover_relevant_learning_events_surfaces_active_role_context(tmp_path: Path, monkeypatch):
    learning_log = tmp_path / "learning_events.jsonl"
    monkeypatch.setattr(learning_events, "DEFAULT_LEARNING_EVENTS_LOG", learning_log)
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Require source note or explicit uncertainty before comparator claims.",
        future_application_cue="new comparator claim",
        approved_by="role.manager",
        approval_ref="review/learning/1",
        owner_role="role.researcher",
        tenant_id="tenant-a",
        project_id="project-a",
        source_carrier_refs=["evidence_gap/gap_1"],
        log_path=learning_log,
    )

    candidates = discover_relevant_learning_events(
        assigned_to="role.researcher",
        tenant_id="tenant-a",
        project_id="project-a",
        cue="comparator claim",
    )

    assert len(candidates) == 1
    assert candidates[0].source == "learning-event-replay"
    assert candidates[0].metadata["learning_event_id"] == event.learning_event_id
    assert candidates[0].raw_text.startswith("Require source note")


def test_discover_relevant_learning_events_accepts_explicit_log_path(tmp_path: Path):
    learning_log = tmp_path / "tenant_firm" / "learning_events.jsonl"
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Replay this approved routine before repeating the queue repair.",
        future_application_cue="queue repair repeats",
        approved_by="role.manager",
        approval_ref="review/learning/explicit",
        owner_role="role.org_evolver",
        log_path=learning_log,
    )

    candidates = discover_relevant_learning_events(
        assigned_to="role.org_evolver",
        cue="queue repair",
        log_path=learning_log,
    )

    assert [candidate.metadata["learning_event_id"] for candidate in candidates] == [
        event.learning_event_id
    ]


def test_role_learning_context_joins_outcomes_reviews_without_recording_encounters(
    tmp_path: Path,
):
    learning_log = tmp_path / "learning_events.jsonl"
    outcome_log = tmp_path / "outcome_links.jsonl"
    review_log = tmp_path / "routine_reviews.jsonl"
    encounter_log = tmp_path / "learning_encounters.jsonl"
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Route queue stalls through reviewer handoff before escalation.",
        future_application_cue="queue stalls",
        approved_by="role.owner",
        approval_ref="decision:learning-queue",
        owner_role="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        source_carrier_refs=["attribution:packet-queue"],
        log_path=learning_log,
    )
    link = create_outcome_link(
        change_ref=f"learning_event:{event.learning_event_id}",
        change_kind="learning_event",
        learning_event_id=event.learning_event_id,
        metric_name="queue_cycle_time",
        metric_unit="hours",
        created_by="actor.analyst",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=outcome_log,
    )
    due = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    review = schedule_routine_review(
        routine_ref=f"learning_event:{event.learning_event_id}",
        routine_kind="learning_event",
        learning_event_id=event.learning_event_id,
        review_due_utc=due,
        scheduled_by="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        reason="Check whether the queue-stall routine still fits.",
        log_path=review_log,
    )

    context = build_role_learning_context(
        assigned_to="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        cue="queue stalls during handoff",
        learning_events_log_path=learning_log,
        outcome_links_log_path=outcome_log,
        routine_reviews_log_path=review_log,
    )

    assert context["read_only"] is True
    assert context["context_packet"]["context_packet_id"].startswith("ctx_")
    assert context["context_packet"]["basis"]["learning_event_ids"] == [
        event.learning_event_id
    ]
    assert context["context_packet"]["basis"]["outcome_link_ids"] == [
        link.outcome_link_id
    ]
    assert context["context_packet"]["basis"]["overdue_review_ids"] == [
        review.review_id
    ]
    assert context["context_packet"]["write_policy"] == "projection_only"
    assert context["consumer_contract"]["encounter_route"] == (
        "POST /kernel/learning-event-encounters"
    )
    assert encounter_log.exists() is False
    assert [row["learning_event"]["learning_event_id"] for row in context["learning_context"]] == [
        event.learning_event_id
    ]
    assert context["learning_context"][0]["outcome_links"][0]["outcome_link_id"] == (
        link.outcome_link_id
    )
    assert context["learning_context"][0]["overdue_review_ids"] == [review.review_id]
    assert [
        candidate["metadata"]["learning_event_id"]
        for candidate in context["work_candidates"]
        if candidate["source"] == "learning-event-replay"
    ] == [event.learning_event_id]


def test_discover_open_debates_returns_valid_candidate(tmp_path: Path, monkeypatch):
    seams = tmp_path / "seams"
    seams.mkdir()
    seam = seams / "gp-001-test.md"
    seam.write_text("debate_state: OPEN\n## Turn 1\n", encoding="utf-8")
    os.utime(seam, (1, 1))

    monkeypatch.setattr(work_discovery, "SEAMS_ROOT", seams)

    candidates = discover_open_debates(idle_threshold_hours=0, max_per_source=5)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source == "open_debate"
    assert "Append turn to stagnant debate" in candidate.intent
    assert candidate.origin_path == seam
    assert candidate.metadata["kind"] == "debate_turn"
