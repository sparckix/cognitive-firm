from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.learning_events import (  # noqa: E402
    create_compounded_learning_event,
    create_learning_event,
    learning_event_from_candidate,
    learning_event_resource,
    list_learning_event_encounters,
    list_learning_events,
    main as learning_events_main,
    record_learning_event_encounter,
    replay_learning_events,
    summarize_learning_events,
    update_learning_event_status,
)
from cognitive_firm.orchestration.learning_transition_compiler import LearningTransitionCandidate  # noqa: E402
from cognitive_firm.orchestration.outcome_links import (  # noqa: E402
    create_outcome_link,
    record_metric_snapshot,
    record_verdict,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402
from cognitive_firm.orchestration.routine_reviews import schedule_routine_review  # noqa: E402


def test_learning_event_records_approved_behavior_change(tmp_path: Path):
    log_path = tmp_path / "learning_events.jsonl"

    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Stop rerunning a stale reduction route after repeated null evidence.",
        future_application_cue="When a branch repeats the same failure mode across three reviews.",
        approved_by="role.principal",
        approval_ref="review/1",
        source_carrier_refs=["forecast/c1", "action/a1"],
        derived_from_learning_event_ids=["learn_prior"],
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
    assert event.derived_from_learning_event_ids == ["learn_prior"]
    assert event.status == "active"

    events = list_learning_events(tenant_id="tenant-a", log_path=log_path)
    assert [item.learning_event_id for item in events] == [event.learning_event_id]
    assert events[0].future_application_cue.startswith("When a branch repeats")


def test_learning_event_can_compound_prior_learning_units(tmp_path: Path):
    log_path = tmp_path / "learning_events.jsonl"
    first = create_learning_event(
        learning_event_id="learn_source_gate",
        learning_unit_kind="evidence_standard_change",
        decision_use="Require a source note for comparator claims.",
        future_application_cue="comparator claim",
        approved_by="role.manager",
        approval_ref="review/source-gate",
        log_path=log_path,
    )
    second = create_learning_event(
        learning_event_id="learn_review_gate",
        learning_unit_kind="review_threshold_change",
        decision_use="Escalate repeated comparator misses for independent review.",
        future_application_cue="repeated comparator miss",
        approved_by="role.manager",
        approval_ref="review/review-gate",
        log_path=log_path,
    )

    compounded = create_compounded_learning_event(
        source_learning_event_ids=[first.learning_event_id, second.learning_event_id],
        learning_unit_kind="routine_change",
        decision_use="Apply source-note and independent-review gates together.",
        future_application_cue="comparator claim after repeated misses",
        approved_by="role.principal",
        approval_ref="review/compound-1",
        source_carrier_refs=["outcome_link:olink_1"],
        before_state="two separate review cues",
        after_state="combined comparator-claim routine",
        log_path=log_path,
    )

    assert compounded.derived_from_learning_event_ids == [
        "learn_source_gate",
        "learn_review_gate",
    ]
    assert compounded.source_carrier_refs == [
        "outcome_link:olink_1",
        "learning_event:learn_source_gate",
        "learning_event:learn_review_gate",
    ]


def test_compounding_rejects_missing_or_inactive_sources(tmp_path: Path):
    log_path = tmp_path / "learning_events.jsonl"
    event = create_learning_event(
        learning_event_id="learn_parent",
        learning_unit_kind="routine_change",
        decision_use="Use parent.",
        future_application_cue="parent cue",
        approved_by="role.manager",
        approval_ref="review/parent",
        log_path=log_path,
    )

    update_learning_event_status(
        event.learning_event_id,
        "retired",
        retirement_reason="no longer applicable",
        log_path=log_path,
    )

    try:
        create_compounded_learning_event(
            source_learning_event_ids=["learn_parent"],
            learning_unit_kind="routine_change",
            decision_use="Use child.",
            future_application_cue="child cue",
            approved_by="role.manager",
            approval_ref="review/child",
            log_path=log_path,
        )
    except ValueError as exc:
        assert "must be active" in str(exc)
    else:
        raise AssertionError("expected inactive parent rejection")

    try:
        create_compounded_learning_event(
            source_learning_event_ids=["learn_missing"],
            learning_unit_kind="routine_change",
            decision_use="Use child.",
            future_application_cue="child cue",
            approved_by="role.manager",
            approval_ref="review/child",
            log_path=log_path,
        )
    except KeyError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("expected missing parent rejection")


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


def test_learning_event_resource_envelope_shape(tmp_path: Path):
    log_path = tmp_path / "learning_events.jsonl"
    event = create_learning_event(
        learning_unit_kind="route_change",
        decision_use="Route matching branches to independent review.",
        future_application_cue="forecast recommends branch kill",
        approved_by="role.principal",
        approval_ref="review/approved/1",
        source_carrier_refs=["forecast/c1"],
        derived_from_learning_event_ids=["learn_prior"],
        candidate_ref="ltc_1",
        before_state="execution queue",
        after_state="independent review queue",
        owner_role="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        metadata={"candidate_transition_kind": "role_review"},
        log_path=log_path,
    )

    resource = learning_event_resource(event).as_dict()

    assert validate_resource(resource) == []
    assert resource["kind"] == "LearningEvent"
    assert resource["metadata"]["name"] == event.learning_event_id
    assert resource["metadata"]["tenant_id"] == "tenant-a"
    assert resource["metadata"]["project_id"] == "project-a"
    assert resource["metadata"]["labels"]["learning_unit_kind"] == "route_change"
    assert resource["spec"]["derived_from_learning_event_ids"] == ["learn_prior"]
    assert resource["status"]["status"] == "active"
    assert {"rel": "derived_from", "href": "learning_event:learn_prior"} in resource["links"]
    assert {"rel": "source_carrier", "href": "forecast/c1"} in resource["links"]


def test_learning_events_cli_can_render_resource_envelopes(tmp_path: Path, capsys):
    log_path = tmp_path / "learning_events.jsonl"
    event = create_learning_event(
        learning_unit_kind="route_change",
        decision_use="Route matching branches to independent review.",
        future_application_cue="forecast recommends branch kill",
        approved_by="role.principal",
        approval_ref="review/approved/1",
        tenant_id="tenant-a",
        log_path=log_path,
    )

    rc = learning_events_main(["list", "--log-path", str(log_path), "--resource"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert len(payload) == 1
    assert payload[0]["kind"] == "LearningEvent"
    assert payload[0]["metadata"]["name"] == event.learning_event_id
    assert validate_resource(payload[0]) == []


def test_learning_event_summary_joins_units_encounters_outcomes_and_reviews(tmp_path: Path):
    learning_log = tmp_path / "learning_events.jsonl"
    encounter_log = tmp_path / "learning_encounters.jsonl"
    outcome_log = tmp_path / "outcome_links.jsonl"
    review_log = tmp_path / "routine_reviews.jsonl"
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    first = create_learning_event(
        learning_event_id="learn_source_gate",
        learning_unit_kind="evidence_standard_change",
        decision_use="Require source notes for comparator claims.",
        future_application_cue="comparator claim",
        approved_by="role.manager",
        approval_ref="review/source-gate",
        source_carrier_refs=["action_impact:row_1"],
        review_after_utc=past,
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=learning_log,
    )
    second = create_learning_event(
        learning_event_id="learn_review_gate",
        learning_unit_kind="review_threshold_change",
        decision_use="Escalate repeated comparator misses.",
        future_application_cue="repeated comparator miss",
        approved_by="role.manager",
        approval_ref="review/review-gate",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=learning_log,
    )
    compounded = create_compounded_learning_event(
        source_learning_event_ids=[first.learning_event_id, second.learning_event_id],
        learning_unit_kind="routine_change",
        decision_use="Apply source-note and escalation gates together.",
        future_application_cue="comparator claim after repeated misses",
        approved_by="role.principal",
        approval_ref="review/compound-1",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=learning_log,
    )
    record_learning_event_encounter(
        learning_event_id=compounded.learning_event_id,
        role="role.manager",
        cue="comparator claim after repeated misses",
        outcome="applied",
        work_ref="work:item-1",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=encounter_log,
    )
    link = create_outcome_link(
        change_ref=f"learning_event:{compounded.learning_event_id}",
        change_kind="learning_event",
        learning_event_id=compounded.learning_event_id,
        metric_name="review_burden",
        metric_unit="hours",
        created_by="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=outcome_log,
    )
    record_metric_snapshot(
        link.outcome_link_id,
        kind="baseline",
        value=4.0,
        captured_by="role.manager",
        log_path=outcome_log,
    )
    record_metric_snapshot(
        link.outcome_link_id,
        kind="post",
        value=2.5,
        captured_by="role.manager",
        log_path=outcome_log,
    )
    record_verdict(
        link.outcome_link_id,
        verdict="improved",
        recorded_by="role.manager",
        rationale="Review burden fell after the combined routine.",
        log_path=outcome_log,
    )
    schedule_routine_review(
        routine_ref=f"learning_event:{compounded.learning_event_id}",
        routine_kind="learning_event",
        learning_event_id=compounded.learning_event_id,
        review_due_utc=past,
        scheduled_by="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=review_log,
    )

    summary = summarize_learning_events(
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=learning_log,
        encounters_log_path=encounter_log,
        outcome_links_log_path=outcome_log,
        routine_reviews_log_path=review_log,
    )

    assert summary.total == 3
    assert summary.active == 3
    assert summary.compounded == 1
    assert summary.root_units == 2
    assert summary.with_source_carriers == 2
    assert summary.with_review_after == 1
    assert summary.encounter_counts["applied"] == 1
    assert summary.events_with_encounters == 1
    assert summary.outcome_link_count == 1
    assert summary.outcome_verdict_coverage == 1.0
    assert summary.routine_review_count == 1
    assert summary.overdue_routine_review_count == 1
    assert summary.overdue_learning_event_ids == [compounded.learning_event_id]
    assert summary.recommendation == "review or retire overdue learning routines"


def test_learning_events_cli_can_render_summary(tmp_path: Path, capsys):
    learning_log = tmp_path / "learning_events.jsonl"
    encounter_log = tmp_path / "learning_encounters.jsonl"
    outcome_log = tmp_path / "outcome_links.jsonl"
    review_log = tmp_path / "routine_reviews.jsonl"
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Require source notes.",
        future_application_cue="comparator claim",
        approved_by="role.manager",
        approval_ref="review/1",
        log_path=learning_log,
    )
    record_learning_event_encounter(
        learning_event_id=event.learning_event_id,
        role="role.manager",
        cue="comparator claim",
        outcome="encountered",
        log_path=encounter_log,
    )

    rc = learning_events_main(
        [
            "summary",
            "--log-path",
            str(learning_log),
            "--encounters-log-path",
            str(encounter_log),
            "--outcome-links-log-path",
            str(outcome_log),
            "--routine-reviews-log-path",
            str(review_log),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["total"] == 1
    assert payload["active"] == 1
    assert payload["encounter_counts"]["encountered"] == 1
    assert payload["recommendation"] == "attach outcome links to approved learning units"


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
