from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.human_work import (  # noqa: E402
    append_human_work_receipt,
    append_human_work_interaction,
    append_human_work_note,
    create_agent_requested_human_work_session,
    create_human_work_session,
    human_work_resource,
    list_a2h_waiting_on_human_sessions,
    list_human_work_sessions,
    list_agent_followup_human_work_sessions,
    list_missing_receipt_human_work_sessions,
    main as human_work_main,
    summarize_a2h_work_pressure,
    update_human_work_state,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402
from cognitive_firm.orchestration.agent_channels import send_agent_message  # noqa: E402
from cognitive_firm.orchestration.execution_routing import infer_execution_route  # noqa: E402


def test_create_and_list_human_work_session(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    session = create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="verify source and attach citation",
        work_mode="source_check",
        bottleneck_class="access",
        observability="human_attested",
        receipt_required=True,
        receipt_type="note",
        tenant_id="tenant_a",
        project_id="project_a",
        collaborating_roles=["role.reviewer"],
        log_path=log,
    )

    sessions = list_human_work_sessions(log_path=log)
    assert sessions == [session]
    assert session.session_id.startswith("hws_")
    assert session.state == "requested"
    assert session.observability == "human_attested"
    assert session.receipt_required is True


def test_human_work_projects_to_resource_envelope(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    session = create_agent_requested_human_work_session(
        requested_by_role="role.researcher",
        human_actor="principal",
        objective="Inspect private partner note and report whether it changes the recommendation.",
        work_mode="judgment",
        bottleneck_class="access",
        human_deliverable="bounded yes/no plus short rationale",
        tenant_id="tenant-a",
        project_id="project-a",
        collaborating_roles=["role.reviewer"],
        artifact_refs=["artifact://partner-note-redacted"],
        obligation_id="msg_partner_check",
        interaction_surface="offline",
        agent_followup_ref="work:followup",
        metadata={"risk_tier": "medium"},
        log_path=log,
    )

    payload = human_work_resource(session).as_dict()

    assert validate_resource(payload) == []
    assert payload["kind"] == "HumanWorkSession"
    assert payload["metadata"]["name"] == session.session_id
    assert payload["metadata"]["tenant_id"] == "tenant-a"
    assert payload["metadata"]["project_id"] == "project-a"
    assert payload["metadata"]["labels"]["state"] == "requested"
    assert payload["metadata"]["labels"]["work_mode"] == "judgment"
    assert payload["metadata"]["labels"]["bottleneck_class"] == "access"
    assert payload["metadata"]["labels"]["agent_counterparty_role"] == "role.researcher"
    assert payload["metadata"]["labels"]["receipt_required"] == "true"
    assert payload["metadata"]["annotations"]["risk_tier"] == "medium"
    assert payload["spec"]["human_deliverable"] == "bounded yes/no plus short rationale"
    assert payload["spec"]["obligation_id"] == "msg_partner_check"
    assert payload["status"]["receipt_present"] is False
    assert payload["status"]["interaction_event_count"] == 1
    assert {"rel": "requested_by", "href": "role.researcher"} in payload["links"]
    assert {"rel": "human_actor", "href": "principal"} in payload["links"]
    assert {"rel": "collaborating_role", "href": "role.reviewer"} in payload["links"]
    assert {"rel": "artifact", "href": "artifact://partner-note-redacted"} in payload["links"]
    assert {"rel": "obligation", "href": "msg_partner_check"} in payload["links"]


def test_filter_human_work_sessions(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="edit draft",
        work_mode="edit",
        bottleneck_class="taste",
        tenant_id="tenant_a",
        project_id="project_a",
        log_path=log,
    )
    create_human_work_session(
        requested_by="role.manager",
        human_actor="operator",
        objective="copy restricted data",
        work_mode="data_entry",
        bottleneck_class="access",
        tenant_id="tenant_b",
        project_id="project_b",
        log_path=log,
    )

    assert len(list_human_work_sessions(human_actor="operator", log_path=log)) == 1
    assert len(list_human_work_sessions(tenant_id="tenant_a", log_path=log)) == 1
    assert len(list_human_work_sessions(project_id="project_b", log_path=log)) == 1


def test_human_work_state_lifecycle(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    session = create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="call customer",
        work_mode="relationship",
        bottleneck_class="relationship",
        log_path=log,
    )

    claimed = update_human_work_state(session.session_id, "claimed", log_path=log)
    assert claimed.state == "claimed"
    started = update_human_work_state(session.session_id, "in_progress", log_path=log)
    assert started.state == "in_progress"
    completed = update_human_work_state(
        session.session_id,
        "completed",
        completion_summary="Customer confirmed requirement.",
        receipt="Call completed; notes in CRM.",
        confidence="high",
        log_path=log,
    )
    assert completed.state == "completed"
    assert completed.completion_summary == "Customer confirmed requirement."
    assert completed.receipt == "Call completed; notes in CRM."
    assert completed.confidence == "high"
    integrated = update_human_work_state(
        session.session_id,
        "integrated",
        integration_ref="org/tasks/done/customer_call.md",
        log_path=log,
    )
    assert integrated.state == "integrated"
    assert integrated.integration_ref == "org/tasks/done/customer_call.md"


def test_human_work_resource_reflects_receipt_and_integration(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    session = create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="call customer",
        work_mode="relationship",
        bottleneck_class="relationship",
        receipt_required=True,
        receipt_type="note",
        log_path=log,
    )
    update_human_work_state(session.session_id, "claimed", log_path=log)
    update_human_work_state(session.session_id, "in_progress", log_path=log)
    update_human_work_state(
        session.session_id,
        "completed",
        completion_summary="Customer confirmed requirement.",
        receipt="Call completed; notes in CRM.",
        confidence="high",
        log_path=log,
    )
    integrated = update_human_work_state(
        session.session_id,
        "integrated",
        integration_ref="org/tasks/done/customer_call.md",
        log_path=log,
    )

    payload = human_work_resource(integrated).as_dict()

    assert payload["metadata"]["labels"]["state"] == "integrated"
    assert payload["status"]["state"] == "integrated"
    assert payload["status"]["receipt_present"] is True
    assert payload["status"]["completion_summary"] == "Customer confirmed requirement."
    assert payload["status"]["integration_ref"] == "org/tasks/done/customer_call.md"
    assert {"rel": "integration", "href": "org/tasks/done/customer_call.md"} in payload["links"]


def test_human_work_rejects_illegal_transition(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    session = create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="edit draft",
        work_mode="edit",
        bottleneck_class="taste",
        log_path=log,
    )

    with pytest.raises(ValueError, match="illegal transition"):
        update_human_work_state(session.session_id, "integrated", log_path=log)


def test_append_human_work_note_tracks_artifact_refs(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    session = create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="verify source",
        work_mode="source_check",
        bottleneck_class="access",
        log_path=log,
    )

    updated = append_human_work_note(
        session.session_id,
        actor="principal",
        note="Found primary source.",
        artifact_refs=["docs/source.md"],
        log_path=log,
    )
    assert updated.notes[0]["actor"] == "principal"
    assert updated.artifact_refs == ["docs/source.md"]


def test_append_human_work_interaction_tracks_surface_and_followup(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    session = create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="call source owner and hand result back to agent",
        work_mode="relationship",
        bottleneck_class="relationship",
        interaction_surface="offline",
        agent_counterparty_role="role.reviewer",
        human_deliverable="source owner yes/no",
        log_path=log,
    )

    updated = append_human_work_interaction(
        session.session_id,
        actor="principal",
        event_type="offline_call",
        surface="offline",
        summary="Source owner confirmed the document is current.",
        artifact_refs=["crm/source-owner-note"],
        agent_followup_required=True,
        log_path=log,
    )
    assert updated.interaction_surface == "offline"
    assert updated.agent_counterparty_role == "role.reviewer"
    assert updated.interaction_events[0]["event_type"] == "offline_call"
    assert updated.interaction_events[0]["surface"] == "offline"
    assert updated.agent_followup_required is True
    assert updated.artifact_refs == ["crm/source-owner-note"]


def test_world_contact_attestation_uses_human_work_session(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    session = create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="Check restricted billing system and report whether invoice INV-17 is paid.",
        work_mode="external_action",
        bottleneck_class="access",
        observability="external_system",
        receipt_required=True,
        receipt_type="external_ref",
        interaction_surface="external_system",
        agent_counterparty_role="role.manager",
        human_deliverable="bounded payment-status claim",
        agent_followup_required=True,
        metadata={"world_contact_kind": "external_system"},
        log_path=log,
    )

    update_human_work_state(session.session_id, "claimed", log_path=log)
    update_human_work_state(session.session_id, "in_progress", log_path=log)
    completed = update_human_work_state(
        session.session_id,
        "completed",
        completion_summary="Invoice INV-17 is marked paid.",
        receipt="billing://invoice/INV-17",
        confidence="high",
        log_path=log,
    )

    assert completed.metadata["world_contact_kind"] == "external_system"
    assert completed.receipt_required is True
    assert completed.receipt_type == "external_ref"
    assert completed.agent_followup_required is True
    assert completed.receipt == "billing://invoice/INV-17"


def test_world_contact_relationship_event_is_bounded_not_full_transcript(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    session = create_human_work_session(
        requested_by="role.researcher",
        human_actor="principal",
        objective="Call partner and confirm whether Friday review is realistic.",
        work_mode="relationship",
        bottleneck_class="relationship",
        observability="human_attested",
        receipt_required=True,
        receipt_type="note",
        interaction_surface="offline",
        agent_counterparty_role="role.researcher",
        human_deliverable="partner timeline claim",
        metadata={"world_contact_kind": "human_relationship"},
        log_path=log,
    )

    updated = append_human_work_interaction(
        session.session_id,
        actor="principal",
        event_type="world_contact_attested",
        surface="offline",
        summary="Partner said Friday review is realistic if draft is sent by Wednesday.",
        agent_followup_required=True,
        log_path=log,
    )

    assert updated.interaction_events[0]["event_type"] == "world_contact_attested"
    assert "Friday review is realistic" in updated.interaction_events[0]["summary"]
    assert updated.interaction_events[0]["artifact_refs"] == []
    assert updated.agent_followup_required is True


def test_human_work_can_be_queried_by_a2a_obligation_and_followup(tmp_path: Path, monkeypatch):
    channels = tmp_path / "channels"
    roles = tmp_path / "roles"
    log = tmp_path / "human_work.jsonl"
    roles.mkdir()
    (roles / "manager.yaml").write_text("role_id: manager\n", encoding="utf-8")
    (roles / "reviewer.yaml").write_text("role_id: reviewer\n", encoding="utf-8")
    monkeypatch.setattr("cognitive_firm.orchestration.agent_channels.CHANNELS_DIR", channels)
    monkeypatch.setattr("cognitive_firm.orchestration.agent_channels.ROLES_DIR", roles)
    monkeypatch.setattr(
        "cognitive_firm.orchestration.transition_log.TRANSITIONS_LOG",
        tmp_path / "transitions.jsonl",
    )

    message = send_agent_message(
        from_role="manager",
        to_role="reviewer",
        kind="request",
        subject="Verify restricted source",
        body="Requires human access to a non-public source.",
    )
    session = create_human_work_session(
        requested_by="role.reviewer",
        human_actor="principal",
        objective="Check the restricted source and report whether it supports the claim.",
        work_mode="source_check",
        bottleneck_class="access",
        observability="human_attested",
        obligation_id=message.message_id,
        interaction_surface="mixed",
        agent_counterparty_role="role.reviewer",
        agent_followup_required=True,
        log_path=log,
    )

    by_obligation = list_human_work_sessions(obligation_id=message.message_id, log_path=log)
    needs_followup = list_human_work_sessions(agent_followup_required=True, log_path=log)
    by_surface = list_human_work_sessions(interaction_surface="mixed", log_path=log)

    assert by_obligation == [session]
    assert needs_followup == [session]
    assert by_surface == [session]


def test_agent_requested_human_work_session_encodes_a2h_pattern(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"

    session = create_agent_requested_human_work_session(
        requested_by_role="role.researcher",
        human_actor="principal",
        objective="Inspect private partner note and report whether it changes the recommendation.",
        work_mode="judgment",
        bottleneck_class="access",
        human_deliverable="bounded yes/no plus short rationale",
        obligation_id="msg_partner_check",
        interaction_surface="offline",
        metadata={"risk_tier": "medium"},
        log_path=log,
    )

    assert session.requested_by == "role.researcher"
    assert session.agent_counterparty_role == "role.researcher"
    assert session.agent_followup_required is True
    assert session.receipt_required is True
    assert session.receipt_type == "note"
    assert session.metadata["coordination_pattern"] == "a2h_work_request"
    assert session.metadata["risk_tier"] == "medium"
    assert session.interaction_events[0]["actor"] == "role.researcher"
    assert session.interaction_events[0]["event_type"] == "agent_requested_human_work"


def test_a2h_read_models_surface_followup_receipts_and_pressure(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    sessions = [
        create_agent_requested_human_work_session(
            requested_by_role="role.researcher",
            human_actor="principal",
            objective=f"Check private source {index}.",
            work_mode="source_check",
            bottleneck_class="access",
            human_deliverable="source support claim",
            receipt_required=True,
            receipt_type="note",
            log_path=log,
        )
        for index in range(3)
    ]

    update_human_work_state(sessions[0].session_id, "claimed", log_path=log)
    update_human_work_state(sessions[0].session_id, "in_progress", log_path=log)
    update_human_work_state(
        sessions[0].session_id,
        "completed",
        completion_summary="Source supports the claim.",
        receipt="source note",
        log_path=log,
    )

    followup = list_agent_followup_human_work_sessions(
        agent_counterparty_role="role.researcher",
        log_path=log,
    )
    waiting = list_a2h_waiting_on_human_sessions(
        agent_counterparty_role="role.researcher",
        log_path=log,
    )
    missing_receipts = list_missing_receipt_human_work_sessions(log_path=log)
    pressure = summarize_a2h_work_pressure(log_path=log, concentration_threshold=3)

    assert len(followup) == 1
    assert len(waiting) == 2
    assert len(missing_receipts) == 2
    assert len(pressure) == 1
    assert pressure[0].agent_counterparty_role == "role.researcher"
    assert pressure[0].bottleneck_class == "access"
    assert "source connector" in pressure[0].recommendation


def test_receipt_required_human_work_cannot_integrate_without_receipt(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    session = create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="Verify restricted source.",
        work_mode="source_check",
        bottleneck_class="access",
        receipt_required=True,
        receipt_type="note",
        log_path=log,
    )

    update_human_work_state(session.session_id, "claimed", log_path=log)
    update_human_work_state(session.session_id, "in_progress", log_path=log)
    update_human_work_state(
        session.session_id,
        "completed",
        completion_summary="Source was checked.",
        log_path=log,
    )

    with pytest.raises(ValueError, match="requires receipt"):
        update_human_work_state(
            session.session_id,
            "integrated",
            integration_ref="workspace/integration.md",
            log_path=log,
        )

    integrated = update_human_work_state(
        session.session_id,
        "integrated",
        integration_ref="workspace/integration.md",
        receipt="checked source note",
        log_path=log,
    )
    assert integrated.state == "integrated"
    assert integrated.receipt == "checked source note"


def test_human_work_receipt_records_non_digitized_work_and_unblocks_integration(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    session = create_agent_requested_human_work_session(
        requested_by_role="role.researcher",
        human_actor="principal",
        objective="Check restricted source and report whether it supports the claim.",
        work_mode="source_check",
        bottleneck_class="access",
        human_deliverable="bounded source-support claim plus evidence refs",
        receipt_required=True,
        receipt_type="note",
        interaction_surface="offline",
        sample_for_review=True,
        log_path=log,
    )

    update_human_work_state(session.session_id, "claimed", log_path=log)
    update_human_work_state(session.session_id, "in_progress", log_path=log)
    updated = append_human_work_receipt(
        session.session_id,
        actor="principal",
        summary="Restricted source supports the claim within the requested scope.",
        receipt_type="artifact_ref",
        subject_refs=["source://restricted/source-a"],
        artifact_refs=["artifact://redacted-source-note"],
        confidence="high",
        log_path=log,
    )
    completed = update_human_work_state(
        session.session_id,
        "completed",
        completion_summary="Restricted source supports the claim.",
        log_path=log,
    )
    integrated = update_human_work_state(
        session.session_id,
        "integrated",
        integration_ref="workspace/recommendation.md",
        log_path=log,
    )

    assert updated.receipt_required is True
    assert updated.receipt_type == "artifact_ref"
    assert updated.receipt is not None
    assert updated.confidence == "high"
    assert updated.work_receipts[0]["subject_refs"] == ["source://restricted/source-a"]
    assert updated.artifact_refs == ["artifact://redacted-source-note"]
    assert updated.interaction_events[-1]["event_type"] == "human_work_receipt_attested"
    assert completed.receipt is not None
    assert integrated.state == "integrated"


def test_human_work_resource_links_structured_receipt_refs(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    session = create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="Confirm external system status.",
        work_mode="external_action",
        bottleneck_class="access",
        receipt_required=True,
        receipt_type="none",
        interaction_surface="external_system",
        log_path=log,
    )
    updated = append_human_work_receipt(
        session.session_id,
        actor="principal",
        summary="External system status is complete.",
        receipt_type="external_ref",
        receipt_ref="external://system/record-44",
        subject_refs=["customer://account-44"],
        metadata={"world_contact_kind": "external_system"},
        log_path=log,
    )

    payload = human_work_resource(updated).as_dict()

    assert validate_resource(payload) == []
    assert payload["metadata"]["labels"]["work_receipt_present"] == "true"
    assert payload["metadata"]["labels"]["receipt_type"] == "external_ref"
    assert payload["status"]["work_receipt_count"] == 1
    assert payload["status"]["work_receipts"][0]["receipt_ref"] == "external://system/record-44"
    assert {"rel": "receipt_ref", "href": "external://system/record-44"} in payload["links"]
    assert {"rel": "subject", "href": "customer://account-44"} in payload["links"]


def test_human_work_cli_can_append_structured_receipt(tmp_path: Path, capsys):
    log = tmp_path / "human_work.jsonl"
    session = create_human_work_session(
        requested_by="role.reviewer",
        human_actor="principal",
        objective="Check private note.",
        work_mode="source_check",
        bottleneck_class="access",
        receipt_required=True,
        receipt_type="note",
        interaction_surface="offline",
        log_path=log,
    )

    rc = human_work_main(
        [
            "receipt",
            session.session_id,
            "--actor",
            "principal",
            "--summary",
            "Private note supports the claim.",
            "--receipt-type",
            "witness",
            "--receipt-ref",
            "principal",
            "--subject-ref",
            "source://private-note",
            "--log-path",
            str(log),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["work_receipts"][0]["subject_refs"] == ["source://private-note"]
    assert payload["receipt_type"] == "witness"
    assert payload["receipt"]


def test_human_work_cli_can_render_resource_envelopes(tmp_path: Path, capsys):
    log = tmp_path / "human_work.jsonl"
    session = create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="verify source",
        work_mode="source_check",
        bottleneck_class="access",
        log_path=log,
    )

    rc = human_work_main(["list", "--log-path", str(log), "--resource"])

    assert rc == 0
    payloads = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [payload["kind"] for payload in payloads] == ["HumanWorkSession"]
    assert payloads[0]["metadata"]["name"] == session.session_id
    assert payloads[0]["spec"]["objective"] == "verify source"


def test_invalid_human_work_fields_fail(tmp_path: Path):
    log = tmp_path / "human_work.jsonl"
    with pytest.raises(ValueError):
        create_human_work_session(
            requested_by="role.manager",
            human_actor="principal",
            objective="do work",
            work_mode="magic",
            bottleneck_class="access",
            log_path=log,
        )


def test_execution_route_detects_joint_work():
    route = infer_execution_route(body="This needs human work to verify a restricted source.")
    assert route.route == "joint_work"
    assert route.required_first_artifact == "workspace/human_work_session.md"
