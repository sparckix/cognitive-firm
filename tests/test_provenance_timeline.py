from __future__ import annotations

import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request  # noqa: E402
from cognitive_firm.orchestration.action_attestation import (  # noqa: E402
    create_action_attestation,
    digest_text,
)
from cognitive_firm.orchestration.governance_changes import (  # noqa: E402
    REQUIRED_INVARIANTS,
    propose_governance_change,
)
from cognitive_firm.orchestration.human_work import (  # noqa: E402
    append_human_work_receipt,
    create_human_work_session,
)
from cognitive_firm.orchestration.kernel_events import record_kernel_event  # noqa: E402
from cognitive_firm.orchestration.learning_events import (  # noqa: E402
    create_learning_event,
    record_learning_event_encounter,
)
from cognitive_firm.orchestration.outcome_links import create_outcome_link  # noqa: E402
from cognitive_firm.orchestration.routine_reviews import schedule_routine_review  # noqa: E402
from cognitive_firm.orchestration.run_checkpoints import append_checkpoint, start_run  # noqa: E402


def test_kernel_service_builds_read_only_provenance_timeline(tmp_path: Path):
    config = KernelServiceConfig(
        transition_log=tmp_path / "transitions.jsonl",
        action_attestation_log=tmp_path / "action_attestations.jsonl",
        human_work_log=tmp_path / "human_work.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
        org_dir=tmp_path / "org",
    )
    run = start_run(
        owner_role="role.manager",
        objective="decide whether to change the queue routine",
        tenant_id="tenant-a",
        project_id="project-a",
        run_id="run_timeline_1",
        log_path=config.transition_log,
    )
    append_checkpoint(
        run.run_id,
        actor="role.manager",
        step_id="inspect",
        status="completed",
        summary="Inspected queue evidence.",
        payload_ref="artifact://queue-evidence",
        log_path=config.transition_log,
    )
    create_action_attestation(
        subject_kind="artifact",
        subject_ref="artifact://queue-evidence",
        subject_digest=digest_text("queue evidence"),
        producer="role.manager",
        action_type="inspect_queue",
        run_id=run.run_id,
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=config.action_attestation_log,
    )
    create_human_work_session(
        requested_by="role.manager",
        human_actor="human.reviewer",
        objective="Review queue evidence before policy change.",
        work_mode="judgment",
        bottleneck_class="authority",
        tenant_id="tenant-a",
        project_id="project-a",
        metadata={"cognitive_run_id": run.run_id},
        log_path=config.human_work_log,
    )
    proposal = propose_governance_change(
        change_kind="route_policy_change",
        title="Require reviewer handoff for stalled queues",
        proposed_by="role.manager",
        target_ref="policy:queue-routing",
        rationale="Repeated queue stalls need human review before escalation.",
        source_refs=[run.run_id, "artifact://queue-evidence"],
        expected_behavior_change="Queue stalls route to reviewer handoff first.",
        risk_summary="May slow routine queues.",
        rollback_plan="Revert to previous route policy.",
        tenant_id="tenant-a",
        project_id="project-a",
        invariant_checks=[
            {
                "invariant": invariant,
                "status": "pass",
                "rationale": "checked in fixture",
                "evidence_refs": [run.run_id],
            }
            for invariant in sorted(REQUIRED_INVARIANTS)
        ],
        log_path=config.org_dir / "governance_changes" / "governance_changes.jsonl",
    )
    record_kernel_event(
        actor="role.owner",
        verb="governance_change.approved",
        object_ref=f"governance_change:{proposal.proposal_id}",
        subject_ref=proposal.target_ref,
        tenant_id="tenant-a",
        project_id="project-a",
        payload={"run_id": run.run_id, "proposal_id": proposal.proposal_id},
        log_path=config.transition_log,
    )
    learning = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Route stalled queues through reviewer handoff.",
        future_application_cue="queue stalls",
        approved_by="role.owner",
        approval_ref=f"governance_change:{proposal.proposal_id}",
        owner_role="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        source_carrier_refs=[run.run_id],
        log_path=config.learning_events_log,
    )
    create_outcome_link(
        change_ref=f"run:{run.run_id}",
        change_kind="governed_run",
        metric_name="queue_stall_count",
        metric_unit="count",
        created_by="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        metadata={"run_id": run.run_id},
        log_path=config.outcome_links_log,
    )
    schedule_routine_review(
        routine_ref=f"learning_event:{learning.learning_event_id}",
        routine_kind="learning_event",
        review_due_utc="2030-01-01T00:00:00+00:00",
        scheduled_by="role.manager",
        learning_event_id=learning.learning_event_id,
        tenant_id="tenant-a",
        project_id="project-a",
        metadata={"run_id": run.run_id},
        log_path=config.routine_reviews_log,
    )
    encounter = record_learning_event_encounter(
        learning_event_id=learning.learning_event_id,
        role="role.manager",
        cue="queue stalls",
        outcome="applied",
        work_ref=f"run:{run.run_id}",
        tenant_id="tenant-a",
        project_id="project-a",
        context_packet_ref="ctx_queue",
        log_path=config.learning_encounters_log,
    )

    response = dispatch_kernel_request(
        "GET",
        f"/kernel/provenance-timeline?run_id={run.run_id}",
        config=config,
    )

    assert response.status == 200
    timeline = response.payload["timeline"]
    assert timeline["read_only"] is True
    assert timeline["caveats"] == []
    assert timeline["query"]["tenant_id"] == "tenant-a"
    assert timeline["query"]["project_id"] == "project-a"
    assert timeline["counts"]["kernel_events"] >= 2
    for source in [
        "action_attestations",
        "human_work",
        "governance_changes",
        "learning_events",
        "learning_encounters",
        "outcome_links",
        "routine_reviews",
    ]:
        assert timeline["counts"][source] == 1
    assert [
        event["occurred_at_utc"] for event in timeline["events"]
    ] == sorted(event["occurred_at_utc"] for event in timeline["events"])
    assert any(
        event["object_ref"] == f"governance_change:{proposal.proposal_id}"
        for event in timeline["events"]
    )
    assert any(
        event["object_ref"] == f"learning_encounter:{encounter.encounter_id}"
        and event["summary"].startswith("applied:")
        for event in timeline["events"]
    )

    for source in [
        "action_attestations",
        "human_work",
        "governance_changes",
        "learning_events",
        "learning_encounters",
        "outcome_links",
        "routine_reviews",
    ]:
        object_ref = next(
            event["object_ref"]
            for event in timeline["events"]
            if event["source"] == source
        )
        by_ref = dispatch_kernel_request(
            "GET",
            f"/kernel/provenance-timeline?ref={object_ref}",
            config=config,
        )
        assert by_ref.status == 200
        assert any(
            event["source"] == source and event["object_ref"] == object_ref
            for event in by_ref.payload["timeline"]["events"]
        )

    graph_response = dispatch_kernel_request(
        "GET",
        f"/kernel/provenance-graph?run_id={run.run_id}",
        config=config,
    )
    assert graph_response.status == 200
    graph = graph_response.payload["graph"]
    assert graph["read_only"] is True
    assert graph["projection_only"] is True
    assert graph["counts"]["events"] == len(timeline["events"])
    assert graph["counts"]["nodes"] >= graph["counts"]["events"]
    assert graph["counts"]["edges"] > 0
    assert any(
        "not workflow state" in caveat
        for caveat in graph["caveats"]
    )
    node_ids = {node["node_id"] for node in graph["nodes"]}
    edge_pairs = {
        (edge["from_ref"], edge["to_ref"], edge["relation"])
        for edge in graph["edges"]
    }
    assert f"governance_change:{proposal.proposal_id}" in node_ids
    assert "artifact://queue-evidence" in node_ids
    assert any(
        source == f"governance_change:{proposal.proposal_id}"
        and target == "artifact://queue-evidence"
        and relation == "mentions_ref"
        for source, target, relation in edge_pairs
    )

    report_response = dispatch_kernel_request(
        "GET",
        f"/kernel/provenance-report?run_id={run.run_id}&event_limit=4",
        config=config,
    )
    assert report_response.status == 200
    report = report_response.payload["report"]
    assert report["read_only"] is True
    assert report["projection_only"] is True
    assert report["report_kind"] == "provenance_handoff"
    assert report["generated_from"] == [
        "provenance_timeline",
        "provenance_graph",
    ]
    assert report["summary"]["event_count"] == len(timeline["events"])
    assert report["summary"]["source_counts"]["governance_changes"] == 1
    assert report["coverage"]["status"] == "complete_enough_for_review"
    assert report["coverage"]["gaps"] == []
    assert report["follow_through"]["status"] == "closed_loop_observed"
    assert report["follow_through"]["outcome_links"] == 1
    assert report["follow_through"]["routine_reviews"] == 1
    assert report["follow_through"]["learning_use_receipts"] == 1
    assert f"learning_encounter:{encounter.encounter_id}" in report[
        "follow_through"
    ]["latest_refs"]
    assert report["event_excerpt_limit"] == 4
    assert len(report["event_excerpt"]) == 4
    assert any(
        row["ref"] == "artifact://queue-evidence"
        and row["ref_kind"] == "artifact"
        for row in report["evidence_refs"]
    )
    assert "# Provenance Report" in report["markdown"]
    assert "## Follow-Through" in report["markdown"]
    assert "Read-only projection over canonical kernel logs." in report["markdown"]


def test_provenance_routes_require_explicit_selector(tmp_path: Path):
    config = KernelServiceConfig(
        transition_log=tmp_path / "transitions.jsonl",
        action_attestation_log=tmp_path / "action_attestations.jsonl",
        human_work_log=tmp_path / "human_work.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
    )

    timeline = dispatch_kernel_request(
        "GET",
        "/kernel/provenance-timeline",
        config=config,
    )
    graph = dispatch_kernel_request(
        "GET",
        "/kernel/provenance-graph",
        config=config,
    )
    report = dispatch_kernel_request(
        "GET",
        "/kernel/provenance-report",
        config=config,
    )

    assert timeline.status == 400
    assert (
        "requires run_id, ref, tenant_id, or tenant_id with project_id"
        in timeline.payload["error"]
    )
    assert graph.status == 400
    assert (
        "requires run_id, ref, tenant_id, or tenant_id with project_id"
        in graph.payload["error"]
    )
    assert report.status == 400
    assert (
        "requires run_id, ref, tenant_id, or tenant_id with project_id"
        in report.payload["error"]
    )


def test_provenance_routes_require_tenant_for_project_selector(tmp_path: Path):
    config = KernelServiceConfig(
        action_attestation_log=tmp_path / "action_attestations.jsonl",
    )

    timeline = dispatch_kernel_request(
        "GET",
        "/kernel/provenance-timeline?project_id=shared-project",
        config=config,
    )
    graph = dispatch_kernel_request(
        "GET",
        "/kernel/provenance-graph?project_id=shared-project",
        config=config,
    )
    report = dispatch_kernel_request(
        "GET",
        "/kernel/provenance-report?project_id=shared-project",
        config=config,
    )

    assert timeline.status == 400
    assert "project_id provenance queries require tenant_id" in timeline.payload["error"]
    assert graph.status == 400
    assert "project_id provenance queries require tenant_id" in graph.payload["error"]
    assert report.status == 400
    assert "project_id provenance queries require tenant_id" in report.payload["error"]


def test_provenance_timeline_matches_human_work_receipt_subject_refs(
    tmp_path: Path,
):
    config = KernelServiceConfig(
        action_attestation_log=tmp_path / "action_attestations.jsonl",
        human_work_log=tmp_path / "human_work.jsonl",
    )
    attestation = create_action_attestation(
        subject_kind="artifact",
        subject_ref="artifact://agent-output/release-note",
        subject_digest=digest_text("release note"),
        producer="role.writer",
        action_type="draft_release_note",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=config.action_attestation_log,
    )
    session = create_human_work_session(
        requested_by="role.reviewer",
        human_actor="principal",
        objective="Review the agent-generated release note.",
        work_mode="judgment",
        bottleneck_class="cognition",
        tenant_id="tenant-a",
        project_id="project-a",
        receipt_required=True,
        receipt_type="artifact_ref",
        log_path=config.human_work_log,
    )
    updated = append_human_work_receipt(
        session.session_id,
        actor="principal",
        summary="Accepted after checking the cited diff.",
        receipt_type="artifact_ref",
        subject_refs=[
            "artifact://agent-output/release-note",
            f"action_attestation:{attestation.attestation_id}",
        ],
        artifact_refs=["artifact://human-review/release-note-accepted"],
        confidence="high",
        observability="digital_artifact",
        metadata={"review_decision": "accepted"},
        log_path=config.human_work_log,
    )

    response = dispatch_kernel_request(
        "GET",
        f"/kernel/provenance-timeline?ref=action_attestation:{attestation.attestation_id}",
        config=config,
    )

    assert response.status == 200
    timeline = response.payload["timeline"]
    assert timeline["counts"] == {
        "action_attestations": 1,
        "human_work": 1,
    }
    human_event = next(
        event for event in timeline["events"] if event["source"] == "human_work"
    )
    receipt = updated.work_receipts[0]
    assert f"human_work_receipt:{receipt['receipt_id']}" in human_event["related_refs"]
    assert f"action_attestation:{attestation.attestation_id}" in human_event["related_refs"]
    assert "artifact://human-review/release-note-accepted" in human_event["related_refs"]


def test_ref_only_provenance_timeline_surfaces_scope_caveat(tmp_path: Path):
    config = KernelServiceConfig(
        action_attestation_log=tmp_path / "action_attestations.jsonl",
    )
    attestation = create_action_attestation(
        subject_kind="artifact",
        subject_ref="artifact://shared/ref",
        subject_digest=digest_text("shared ref"),
        producer="role.writer",
        action_type="draft_shared_ref",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=config.action_attestation_log,
    )

    ref_only = dispatch_kernel_request(
        "GET",
        f"/kernel/provenance-timeline?ref=action_attestation:{attestation.attestation_id}",
        config=config,
    )
    scoped = dispatch_kernel_request(
        "GET",
        (
            "/kernel/provenance-timeline"
            f"?ref=action_attestation:{attestation.attestation_id}"
            "&tenant_id=tenant-a"
        ),
        config=config,
    )

    assert ref_only.status == 200
    assert any(
        "pass tenant_id/project_id to narrow scope" in caveat
        for caveat in ref_only.payload["timeline"]["caveats"]
    )
    assert scoped.status == 200
    assert not any(
        "pass tenant_id/project_id to narrow scope" in caveat
        for caveat in scoped.payload["timeline"]["caveats"]
    )


def test_typed_ref_timeline_does_not_match_unrelated_raw_id_collision(
    tmp_path: Path,
):
    config = KernelServiceConfig(
        org_dir=tmp_path / "org",
        learning_events_log=tmp_path / "learning_events.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
    )
    proposal = propose_governance_change(
        change_kind="route_policy_change",
        title="Shared id governance proposal",
        proposed_by="role.manager",
        target_ref="policy:queue-routing",
        rationale="Fixture for typed ref collision.",
        source_refs=["artifact://proposal-evidence"],
        expected_behavior_change="No runtime effect.",
        risk_summary="Fixture risk.",
        rollback_plan="Fixture rollback.",
        invariant_checks=[
            {
                "invariant": invariant,
                "status": "pass",
                "rationale": "checked in fixture",
                "evidence_refs": ["artifact://proposal-evidence"],
            }
            for invariant in sorted(REQUIRED_INVARIANTS)
        ],
        proposal_id="same_id",
        log_path=config.org_dir / "governance_changes" / "governance_changes.jsonl",
    )
    learning = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Unrelated learning event with colliding raw id.",
        future_application_cue="queue stalls",
        approved_by="role.owner",
        approval_ref="governance_change:other",
        owner_role="role.manager",
        learning_event_id="same_id",
        log_path=config.learning_events_log,
    )
    outcome = create_outcome_link(
        change_ref="policy:queue-routing",
        change_kind="learning_event",
        learning_event_id=learning.learning_event_id,
        metric_name="queue_stall_count",
        metric_unit="count",
        created_by="role.manager",
        log_path=config.outcome_links_log,
    )
    review = schedule_routine_review(
        routine_ref="routine:queue-review",
        routine_kind="learning_event",
        review_due_utc="2030-01-01T00:00:00+00:00",
        scheduled_by="role.manager",
        learning_event_id=learning.learning_event_id,
        log_path=config.routine_reviews_log,
    )
    encounter = record_learning_event_encounter(
        learning_event_id=learning.learning_event_id,
        role="role.manager",
        cue="queue stalls",
        outcome="applied",
        context_packet_ref="ctx_same",
        log_path=config.learning_encounters_log,
    )

    governance_ref = dispatch_kernel_request(
        "GET",
        "/kernel/provenance-timeline?ref=governance_change:same_id",
        config=config,
    )
    learning_ref = dispatch_kernel_request(
        "GET",
        "/kernel/provenance-timeline?ref=learning_event:same_id",
        config=config,
    )

    assert governance_ref.status == 200
    governance_object_refs = {
        event["object_ref"]
        for event in governance_ref.payload["timeline"]["events"]
    }
    assert governance_object_refs == {f"governance_change:{proposal.proposal_id}"}

    assert learning_ref.status == 200
    learning_object_refs = {
        event["object_ref"]
        for event in learning_ref.payload["timeline"]["events"]
    }
    assert f"learning_event:{learning.learning_event_id}" in learning_object_refs
    assert f"outcome_link:{outcome.outcome_link_id}" in learning_object_refs
    assert f"routine_review:{review.review_id}" in learning_object_refs
    assert f"learning_encounter:{encounter.encounter_id}" in learning_object_refs
    assert f"governance_change:{proposal.proposal_id}" not in learning_object_refs


def test_learning_event_ref_timeline_includes_downstream_loop_records(
    tmp_path: Path,
):
    config = KernelServiceConfig(
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
    )
    learning = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Route stalled queues through reviewer handoff.",
        future_application_cue="queue stalls",
        approved_by="role.owner",
        approval_ref="governance_change:gcp_queue",
        owner_role="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=config.learning_events_log,
    )
    outcome = create_outcome_link(
        change_ref="policy:queue-routing",
        change_kind="learning_event",
        learning_event_id=learning.learning_event_id,
        metric_name="queue_stall_count",
        metric_unit="count",
        created_by="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=config.outcome_links_log,
    )
    review = schedule_routine_review(
        routine_ref="routine:queue-review",
        routine_kind="learning_event",
        review_due_utc="2030-01-01T00:00:00+00:00",
        scheduled_by="role.manager",
        learning_event_id=learning.learning_event_id,
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=config.routine_reviews_log,
    )
    encounter = record_learning_event_encounter(
        learning_event_id=learning.learning_event_id,
        role="role.manager",
        cue="queue stalls",
        outcome="applied",
        context_packet_ref="ctx_queue",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=config.learning_encounters_log,
    )

    response = dispatch_kernel_request(
        "GET",
        f"/kernel/provenance-timeline?ref=learning_event:{learning.learning_event_id}",
        config=config,
    )

    assert response.status == 200
    timeline = response.payload["timeline"]
    assert timeline["counts"]["learning_events"] == 1
    assert timeline["counts"]["learning_encounters"] == 1
    assert timeline["counts"]["outcome_links"] == 1
    assert timeline["counts"]["routine_reviews"] == 1
    object_refs = {event["object_ref"] for event in timeline["events"]}
    assert f"learning_event:{learning.learning_event_id}" in object_refs
    assert f"outcome_link:{outcome.outcome_link_id}" in object_refs
    assert f"routine_review:{review.review_id}" in object_refs
    assert f"learning_encounter:{encounter.encounter_id}" in object_refs

    graph_response = dispatch_kernel_request(
        "GET",
        f"/kernel/provenance-graph?ref=learning_event:{learning.learning_event_id}",
        config=config,
    )

    assert graph_response.status == 200
    graph_edges = {
        (edge["from_ref"], edge["to_ref"], edge["relation"])
        for edge in graph_response.payload["graph"]["edges"]
    }
    assert (
        f"outcome_link:{outcome.outcome_link_id}",
        f"learning_event:{learning.learning_event_id}",
        "mentions_event",
    ) in graph_edges


def test_provenance_timeline_reads_configured_kernel_events_log(
    tmp_path: Path,
):
    config = KernelServiceConfig(
        transition_log=tmp_path / "transitions.jsonl",
        kernel_events_log=tmp_path / "kernel_events.jsonl",
    )
    run = start_run(
        owner_role="role.manager",
        objective="inspect a separately configured kernel event stream",
        tenant_id="tenant-a",
        project_id="project-a",
        run_id="run_kernel_events_sidecar",
        log_path=config.transition_log,
    )
    record_kernel_event(
        actor="role.manager",
        verb="artifact.inspected",
        object_ref="artifact://kernel-sidecar",
        tenant_id="tenant-a",
        project_id="project-a",
        payload={"run_id": run.run_id, "summary": "Inspected sidecar event."},
        log_path=config.kernel_events_log,
    )

    response = dispatch_kernel_request(
        "GET",
        f"/kernel/provenance-timeline?run_id={run.run_id}",
        config=config,
    )

    assert response.status == 200
    timeline = response.payload["timeline"]
    assert timeline["counts"]["kernel_events"] == 1
    assert [
        event["object_ref"]
        for event in timeline["events"]
        if event["source"] == "kernel_events"
    ] == ["artifact://kernel-sidecar"]


def test_run_timeline_includes_global_ref_records_but_not_other_tenants(
    tmp_path: Path,
):
    config = KernelServiceConfig(
        transition_log=tmp_path / "transitions.jsonl",
        action_attestation_log=tmp_path / "action_attestations.jsonl",
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
    )
    run = start_run(
        owner_role="role.manager",
        objective="inspect globally scoped carriers for a tenant run",
        tenant_id="tenant-a",
        project_id="project-a",
        run_id="run_global_refs",
        log_path=config.transition_log,
    )
    global_attestation = create_action_attestation(
        subject_kind="artifact",
        subject_ref="artifact://global-ref",
        subject_digest=digest_text("global ref"),
        producer="role.manager",
        action_type="inspect_global_ref",
        run_id=run.run_id,
        log_path=config.action_attestation_log,
    )
    other_tenant_attestation = create_action_attestation(
        subject_kind="artifact",
        subject_ref="artifact://other-tenant-ref",
        subject_digest=digest_text("other tenant ref"),
        producer="role.manager",
        action_type="inspect_other_tenant_ref",
        run_id=run.run_id,
        tenant_id="tenant-b",
        project_id="project-b",
        log_path=config.action_attestation_log,
    )
    global_learning = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Globally approved routine cited by a tenant run.",
        future_application_cue="global routine",
        approved_by="role.owner",
        approval_ref="decision:global-learning",
        source_carrier_refs=[f"run:{run.run_id}"],
        log_path=config.learning_events_log,
    )
    other_tenant_learning = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Other tenant routine should stay out.",
        future_application_cue="global routine",
        approved_by="role.owner",
        approval_ref="decision:other-tenant-learning",
        tenant_id="tenant-b",
        project_id="project-b",
        source_carrier_refs=[f"run:{run.run_id}"],
        log_path=config.learning_events_log,
    )
    global_encounter = record_learning_event_encounter(
        learning_event_id=global_learning.learning_event_id,
        role="role.manager",
        cue="global routine",
        outcome="applied",
        work_ref=f"run:{run.run_id}",
        log_path=config.learning_encounters_log,
    )
    other_tenant_encounter = record_learning_event_encounter(
        learning_event_id=other_tenant_learning.learning_event_id,
        role="role.manager",
        cue="global routine",
        outcome="applied",
        work_ref=f"run:{run.run_id}",
        tenant_id="tenant-b",
        project_id="project-b",
        log_path=config.learning_encounters_log,
    )

    by_run = dispatch_kernel_request(
        "GET",
        f"/kernel/provenance-timeline?run_id={run.run_id}",
        config=config,
    )

    assert by_run.status == 200
    object_refs = {
        event["object_ref"] for event in by_run.payload["timeline"]["events"]
    }
    assert f"action_attestation:{global_attestation.attestation_id}" in object_refs
    assert f"learning_event:{global_learning.learning_event_id}" in object_refs
    assert f"learning_encounter:{global_encounter.encounter_id}" in object_refs
    assert f"action_attestation:{other_tenant_attestation.attestation_id}" not in object_refs
    assert f"learning_event:{other_tenant_learning.learning_event_id}" not in object_refs
    assert f"learning_encounter:{other_tenant_encounter.encounter_id}" not in object_refs

    by_scope = dispatch_kernel_request(
        "GET",
        "/kernel/provenance-timeline?tenant_id=tenant-a&project_id=project-a",
        config=config,
    )

    assert by_scope.status == 200
    scope_refs = {
        event["object_ref"] for event in by_scope.payload["timeline"]["events"]
    }
    assert f"action_attestation:{global_attestation.attestation_id}" not in scope_refs
    assert f"learning_event:{global_learning.learning_event_id}" not in scope_refs
    assert f"learning_encounter:{global_encounter.encounter_id}" not in scope_refs


def test_provenance_timeline_tolerates_scalar_human_work_receipt_refs(
    tmp_path: Path,
):
    config = KernelServiceConfig(human_work_log=tmp_path / "human_work.jsonl")
    session = create_human_work_session(
        requested_by="role.reviewer",
        human_actor="principal",
        objective="Review scalar receipt refs from an imported record.",
        work_mode="judgment",
        bottleneck_class="cognition",
        tenant_id="tenant-a",
        project_id="project-a",
        log_path=config.human_work_log,
    )
    append_human_work_receipt(
        session.session_id,
        actor="principal",
        summary="Accepted imported scalar refs.",
        receipt_type="artifact_ref",
        subject_refs=["artifact://agent-output/scalar"],
        artifact_refs=["artifact://human-review/scalar"],
        confidence="high",
        observability="digital_artifact",
        log_path=config.human_work_log,
    )
    rows = [
        json.loads(line)
        for line in config.human_work_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows[-1]["work_receipts"][0]["subject_refs"] = "artifact://agent-output/scalar"
    rows[-1]["work_receipts"][0]["artifact_refs"] = "artifact://human-review/scalar"
    config.human_work_log.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )

    response = dispatch_kernel_request(
        "GET",
        "/kernel/provenance-timeline?ref=artifact://agent-output/scalar",
        config=config,
    )

    assert response.status == 200
    timeline = response.payload["timeline"]
    assert timeline["counts"] == {"human_work": 1}
    event = timeline["events"][0]
    assert "artifact://agent-output/scalar" in event["related_refs"]
    assert "artifact://human-review/scalar" in event["related_refs"]
    assert "a" not in event["related_refs"]
