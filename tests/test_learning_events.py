from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.learning_events import (  # noqa: E402
    create_learning_event,
    learning_event_from_candidate,
    list_learning_event_encounters,
    list_learning_events,
    record_learning_event_encounter,
    replay_learning_events,
    update_learning_event_status,
)
from cognitive_firm.orchestration.learning_transition_compiler import LearningTransitionCandidate  # noqa: E402


def test_learning_event_records_approved_behavior_change(tmp_path: Path):
    log_path = tmp_path / "learning_events.jsonl"

    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Stop rerunning a stale reduction route after repeated null evidence.",
        future_application_cue="When a branch repeats the same failure mode across three reviews.",
        approved_by="role.principal",
        approval_ref="review/1",
        source_carrier_refs=["forecast/c1", "action/a1"],
        before_state="route retries by default",
        after_state="route requires independent evidence before retry",
        owner_role="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        externality_review_ref="review/externalities/1",
        log_path=log_path,
    )

    assert event.learning_event_id.startswith("learn_")
    assert event.learning_unit_kind == "routine_change"
    assert event.status == "active"

    events = list_learning_events(tenant_id="tenant-a", log_path=log_path)
    assert [item.learning_event_id for item in events] == [event.learning_event_id]
    assert events[0].future_application_cue.startswith("When a branch repeats")


def test_learning_event_can_promote_reviewed_candidate(tmp_path: Path):
    log_path = tmp_path / "learning_events.jsonl"
    candidate = LearningTransitionCandidate(
        candidate_id="ltc_1",
        transition_kind="role_review",
        severity="warning",
        rationale="Forecast allocation recommends killing this branch.",
        source_kind="forecast_allocation_recommendation",
        object_ref="forecast/c1",
        suggested_owner_role="role.manager",
        source_refs=["forecast/c1"],
        proposed_payload={"allocation_action": "kill_branch"},
    )

    event = learning_event_from_candidate(
        candidate,
        learning_unit_kind="route_change",
        decision_use="Route future matching branches to independent review before execution.",
        future_application_cue="Forecast recommends kill_branch with high confidence.",
        approved_by="role.principal",
        approval_ref="review/approved/1",
        before_state="branch enters execution queue",
        after_state="branch enters independent review queue",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=log_path,
    )

    assert event.candidate_ref == "ltc_1"
    assert event.owner_role == "role.manager"
    assert event.source_carrier_refs == ["forecast/c1"]
    assert event.metadata["candidate_transition_kind"] == "role_review"


def test_learning_event_rejects_missing_promotion_authority(tmp_path: Path):
    try:
        create_learning_event(
            learning_unit_kind="route_change",
            decision_use="Change route.",
            future_application_cue="Cue.",
            approved_by="",
            approval_ref="review/1",
            log_path=tmp_path / "events.jsonl",
        )
    except ValueError as exc:
        assert "approved_by is required" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_learning_event_replay_and_retirement_are_explicit(tmp_path: Path):
    log_path = tmp_path / "learning_events.jsonl"
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Require independent review before retry.",
        future_application_cue="same failure mode repeats",
        approved_by="role.principal",
        approval_ref="review/1",
        owner_role="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=log_path,
    )

    replayed = replay_learning_events(
        role="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        cue="same failure",
        log_path=log_path,
    )
    assert [item.learning_event_id for item in replayed] == [event.learning_event_id]

    retired = update_learning_event_status(
        event.learning_event_id,
        "retired",
        retirement_reason="Superseded by a narrower route policy.",
        log_path=log_path,
    )
    assert retired.status == "retired"
    assert replay_learning_events(cue="same failure", log_path=log_path) == []


def test_learning_event_replay_includes_global_events_for_tenant_context(tmp_path: Path):
    log_path = tmp_path / "learning_events.jsonl"
    create_learning_event(
        learning_event_id="learn_global",
        learning_unit_kind="routine_change",
        decision_use="Use for all similar project handoffs.",
        future_application_cue="project handoff",
        approved_by="role.manager",
        approval_ref="review/global",
        owner_role="role.research_director",
        log_path=log_path,
    )
    create_learning_event(
        learning_event_id="learn_other_tenant",
        learning_unit_kind="routine_change",
        decision_use="Use only for another tenant.",
        future_application_cue="project handoff",
        approved_by="role.manager",
        approval_ref="review/other",
        owner_role="role.research_director",
        tenant_id="tenant-b",
        log_path=log_path,
    )

    rows = replay_learning_events(
        tenant_id="tenant-a",
        role="role.research_director",
        cue="project handoff",
        log_path=log_path,
    )

    assert [event.learning_event_id for event in rows] == ["learn_global"]


def test_learning_event_lifecycle_requires_reason_or_replacement(tmp_path: Path):
    log_path = tmp_path / "learning_events.jsonl"
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Require narrower review.",
        future_application_cue="handoff repeats",
        approved_by="role.manager",
        approval_ref="review/1",
        log_path=log_path,
    )

    try:
        update_learning_event_status(event.learning_event_id, "retired", log_path=log_path)
    except ValueError as exc:
        assert "retirement_reason is required" in str(exc)
    else:
        raise AssertionError("expected retired lifecycle reason rejection")

    try:
        update_learning_event_status(event.learning_event_id, "superseded", log_path=log_path)
    except ValueError as exc:
        assert "superseded_by is required" in str(exc)
    else:
        raise AssertionError("expected superseded lifecycle replacement rejection")


def test_learning_event_encounter_records_future_use(tmp_path: Path):
    log_path = tmp_path / "learning_events.jsonl"
    encounter_log = tmp_path / "learning_encounters.jsonl"
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Require source note before comparator claims.",
        future_application_cue="comparator claim",
        approved_by="role.manager",
        approval_ref="review/1",
        owner_role="role.researcher",
        log_path=log_path,
    )

    encounter = record_learning_event_encounter(
        learning_event_id=event.learning_event_id,
        role="role.researcher",
        cue="comparator claim",
        outcome="applied",
        work_ref="project/demo/artifact-1",
        evidence_refs=["artifact/source-note"],
        log_path=encounter_log,
    )
    duplicate = record_learning_event_encounter(
        learning_event_id=event.learning_event_id,
        role="role.researcher",
        cue="comparator claim",
        outcome="applied",
        work_ref="project/demo/artifact-1",
        evidence_refs=["artifact/source-note"],
        log_path=encounter_log,
    )

    rows = list_learning_event_encounters(
        learning_event_id=event.learning_event_id,
        outcome="applied",
        log_path=encounter_log,
    )

    assert [row.encounter_id for row in rows] == [encounter.encounter_id]
    assert duplicate.encounter_id == encounter.encounter_id
    assert len(rows) == 1
    assert rows[0].work_ref == "project/demo/artifact-1"
