from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.kernel_events import (  # noqa: E402
    create_kernel_event,
    event_from_legacy_transition,
    kernel_event_from_row,
    list_kernel_events,
    payload_hash,
    record_kernel_event,
    transition_row_from_kernel_event,
)
from cognitive_firm.orchestration.state_backends import FilesystemStateBackend  # noqa: E402
from cognitive_firm.orchestration.transition_log import append_transition  # noqa: E402


def test_kernel_event_envelope_hashes_payload_deterministically():
    payload = {"b": 2, "a": 1}
    event = create_kernel_event(
        actor="role.manager",
        verb="learning_event.created",
        object_ref="learning_events/learn_1",
        tenant_id="tenant-a",
        project_id="project-a",
        payload=payload,
    )
    payload["c"] = 3

    assert event.schema_version == 1
    assert event.payload_hash == payload_hash({"a": 1, "b": 2})
    assert event.payload == {"a": 1, "b": 2}
    assert event.event_id.startswith("kevt_")


def test_kernel_event_log_filters_by_tenant_and_verb(tmp_path: Path):
    log_path = tmp_path / "kernel_events.jsonl"
    record_kernel_event(
        actor="role.manager",
        verb="governance_change.proposed",
        object_ref="governance_changes/gcp_1",
        tenant_id="tenant-a",
        log_path=log_path,
    )
    record_kernel_event(
        actor="role.manager",
        verb="learning_event.created",
        object_ref="learning_events/learn_1",
        tenant_id="tenant-b",
        log_path=log_path,
    )

    rows = list_kernel_events(tenant_id="tenant-a", verb="governance_change.proposed", log_path=log_path)
    assert len(rows) == 1
    assert rows[0].object_ref == "governance_changes/gcp_1"


def test_default_kernel_event_storage_shape_is_transition_row():
    event = create_kernel_event(
        actor="role.manager",
        verb="learning_event.created",
        object_ref="learning_events/learn_1",
        payload={"status": "approved"},
    )

    row = transition_row_from_kernel_event(event)

    assert row["event"] == "learning_event.created"
    assert row["subject"] == "learning_events/learn_1"
    assert row["kernel_event"]["event_id"] == event.event_id
    assert kernel_event_from_row(row) == event


def test_legacy_transition_projects_to_kernel_event():
    row = {
        "event_id": "old-1",
        "event": "run.started",
        "actor": "role.manager",
        "subject": "run/run_1",
        "ts": "2026-05-20T00:00:00+00:00",
        "payload": {
            "run_id": "run_1",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "idempotency_key": "idem-1",
        },
    }
    event = event_from_legacy_transition(row)

    assert event.event_id == "old-1"
    assert event.verb == "run.started"
    assert event.object_ref == "run/run_1"
    assert event.tenant_id == "tenant-a"
    assert event.project_id == "project-a"
    assert event.idempotency_key == "idem-1"
    assert event.payload_hash == payload_hash(
        {
            "run_id": "run_1",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "idempotency_key": "idem-1",
        }
    )
    assert kernel_event_from_row(row) == event


def test_list_kernel_events_accepts_mixed_transition_stream(tmp_path: Path):
    log_path = tmp_path / "transitions.jsonl"
    legacy = {
        "event_id": "old-1",
        "event": "run.started",
        "actor": "role.manager",
        "subject": "run/run_1",
        "ts": "2026-05-20T00:00:00+00:00",
        "payload": {"tenant_id": "tenant-a"},
    }
    new_event = create_kernel_event(
        event_id="kevt_new",
        actor="role.manager",
        verb="run.completed",
        object_ref="run/run_1",
        tenant_id="tenant-a",
        payload={"status": "ok"},
    )
    log_path.write_text(
        "\n".join(
            [
                json.dumps(legacy),
                json.dumps(transition_row_from_kernel_event(new_event)),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    events = list_kernel_events(tenant_id="tenant-a", log_path=log_path)

    assert [event.verb for event in events] == ["run.started", "run.completed"]


def test_transition_log_embeds_kernel_event_envelope(tmp_path: Path):
    row = append_transition(
        event="run.started",
        actor="role.manager",
        role_id="role.manager",
        surface="run_checkpoints",
        subject="run_1",
        payload={"run_id": "run_1", "tenant_id": "tenant-a"},
        causality_id="cause-1",
        log_path=tmp_path / "transitions.jsonl",
    )

    kernel_event = row["kernel_event"]
    assert kernel_event["event_id"] == row["event_id"]
    assert kernel_event["verb"] == "run.started"
    assert kernel_event["object_ref"] == "run_1"
    assert kernel_event["tenant_id"] == "tenant-a"
    assert kernel_event["causation_id"] == "cause-1"


def test_transition_log_can_write_through_event_source(tmp_path: Path):
    backend = FilesystemStateBackend(tmp_path / "state")

    row = append_transition(
        event="governance_change.proposed",
        actor="role.manager",
        surface="governance_changes",
        subject="gcp_1",
        payload={"proposal_id": "gcp_1"},
        event_source=backend,
    )

    assert backend.read_events("transitions") == [row]
    assert row["kernel_event"]["verb"] == "governance_change.proposed"
