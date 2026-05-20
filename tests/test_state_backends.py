from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.state_backends import (  # noqa: E402
    FilesystemStateBackend,
    SqliteEventSource,
    SqliteMutationBackend,
    postgres_guarded_append_transaction_sql,
    postgres_transactional_mutation_schema_sql,
)


def test_filesystem_state_backend_appends_events_and_artifacts(tmp_path: Path):
    backend = FilesystemStateBackend(tmp_path / "state")

    assert backend.connector_family == "state_backend"
    assert backend.connector_id == "filesystem"
    backend.append_event("transitions", {"event": "run.started", "n": 1})
    backend.append_event("transitions", {"event": "run.completed", "n": 2})
    backend.put_artifact("org/surface", {"counts": {"blocked": 0}})

    assert backend.read_events("transitions") == [
        {"event": "run.started", "n": 1},
        {"event": "run.completed", "n": 2},
    ]
    assert backend.get_artifact("org/surface") == {"counts": {"blocked": 0}}
    assert backend.get_artifact("missing") is None


def test_sqlite_event_source_preserves_stream_order(tmp_path: Path):
    source = SqliteEventSource(tmp_path / "kernel_events.sqlite3")

    assert source.connector_family == "state_backend"
    assert source.connector_id == "sqlite"
    source.append_event("transitions", {"event": "a", "n": 1})
    source.append_event("other", {"event": "ignored"})
    source.append_event("transitions", {"event": "b", "n": 2})

    assert source.read_events("transitions") == [
        {"event": "a", "n": 1},
        {"event": "b", "n": 2},
    ]
    assert source.read_events("other") == [{"event": "ignored"}]


def test_filesystem_backend_rejects_unsafe_keys(tmp_path: Path):
    backend = FilesystemStateBackend(tmp_path / "state")

    with pytest.raises(ValueError):
        backend.put_artifact("../secret", {"bad": True})
    with pytest.raises(ValueError):
        backend.put_artifact("/absolute", {"bad": True})


def test_sqlite_mutation_backend_guards_event_append_with_lease(tmp_path: Path):
    backend = SqliteMutationBackend(tmp_path / "mutation.sqlite3")
    lease = backend.acquire_lease(
        resource_ref="human_work:hws_1",
        actor_id="human.alice",
        role_id="role.manager",
        ttl_seconds=60,
    )

    result = backend.guarded_append_event(
        stream="transitions",
        event={"event": "human_work.integrated", "subject": "hws_1"},
        resource_ref="human_work:hws_1",
        lease_id=lease["lease_id"],
        actor_id="human.alice",
        fencing_token=lease["fencing_token"],
    )

    assert result["event"]["lease_id"] == lease["lease_id"]
    assert backend.read_events("transitions") == [result["event"]]


def test_sqlite_mutation_backend_rejects_stale_fencing_without_append(tmp_path: Path):
    backend = SqliteMutationBackend(tmp_path / "mutation.sqlite3")
    lease = backend.acquire_lease(
        resource_ref="accountability_case:case_1",
        actor_id="human.alice",
        ttl_seconds=60,
    )

    with pytest.raises(PermissionError, match="fencing token"):
        backend.guarded_append_event(
            stream="transitions",
            event={"event": "accountability_case.closed"},
            resource_ref="accountability_case:case_1",
            lease_id=lease["lease_id"],
            actor_id="human.alice",
            fencing_token=lease["fencing_token"] + 1,
        )

    assert backend.read_events("transitions") == []


def test_sqlite_mutation_backend_increments_fencing_after_release(tmp_path: Path):
    backend = SqliteMutationBackend(tmp_path / "mutation.sqlite3")
    first = backend.acquire_lease(resource_ref="role:manager", actor_id="human.alice")
    backend.release_lease(lease_id=first["lease_id"], actor_id="human.alice")
    second = backend.acquire_lease(resource_ref="role:manager", actor_id="human.bob")

    assert second["fencing_token"] == first["fencing_token"] + 1
    with pytest.raises(PermissionError, match="active lease"):
        backend.guarded_append_event(
            stream="transitions",
            event={"event": "role.updated"},
            resource_ref="role:manager",
            lease_id=first["lease_id"],
            actor_id="human.alice",
            fencing_token=first["fencing_token"],
        )


def test_postgres_transaction_sql_documents_fenced_append_contract():
    schema = postgres_transactional_mutation_schema_sql()
    guarded = postgres_guarded_append_transaction_sql()

    assert "cognitive_firm_events" in schema
    assert "cognitive_firm_leases" in schema
    assert "FOR UPDATE" in guarded
    assert "held_by_actor_id = %(actor_id)s" in guarded
    assert "fencing_token = %(fencing_token)s" in guarded


def test_postgres_schema_includes_transactional_backend_tables():
    schema = postgres_transactional_mutation_schema_sql()

    assert "JSONB" in schema
    assert "cognitive_firm_events" in schema
    assert "cognitive_firm_leases" in schema
    assert "fencing_token BIGINT NOT NULL" in schema
