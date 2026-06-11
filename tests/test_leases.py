from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.actor_identity import ActorContext  # noqa: E402
from cognitive_firm.orchestration.leases import (  # noqa: E402
    acquire_lease,
    lease_resource,
    list_leases,
    main as leases_main,
    release_lease,
    verify_lease,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


def test_acquire_verify_and_release_lease(tmp_path: Path):
    log = tmp_path / "leases.jsonl"
    actor = ActorContext(actor_id="human.alice", actor_kind="human", role_id="role.manager")

    lease = acquire_lease(
        resource_ref="human_work:hws_1",
        actor=actor,
        ttl_seconds=60,
        log_path=log,
    )

    assert lease.fencing_token == 1
    assert verify_lease(
        resource_ref="human_work:hws_1",
        lease_id=lease.lease_id,
        actor=actor,
        required=True,
        log_path=log,
    ) == lease

    released = release_lease(lease.lease_id, actor=actor, log_path=log)
    assert released.state == "released"
    assert list_leases(resource_ref="human_work:hws_1", state="released", log_path=log)


def test_lease_blocks_other_actor_and_resource_double_acquire(tmp_path: Path):
    log = tmp_path / "leases.jsonl"
    alice = ActorContext(actor_id="human.alice", actor_kind="human")
    bob = ActorContext(actor_id="human.bob", actor_kind="human")
    lease = acquire_lease(resource_ref="accountability_cases:create", actor=alice, log_path=log)

    with pytest.raises(PermissionError, match="leased by"):
        acquire_lease(resource_ref="accountability_cases:create", actor=bob, log_path=log)

    with pytest.raises(PermissionError, match="does not match"):
        verify_lease(
            resource_ref="accountability_cases:create",
            lease_id=lease.lease_id,
            actor=bob,
            required=True,
            log_path=log,
        )


def test_missing_required_lease_fails_closed(tmp_path: Path):
    actor = ActorContext(actor_id="service.kernel", actor_kind="service")

    with pytest.raises(PermissionError, match="lease required"):
        verify_lease(
            resource_ref="human_work:hws_1",
            lease_id=None,
            actor=actor,
            required=True,
            log_path=tmp_path / "leases.jsonl",
        )


def test_verify_lease_rejects_stale_fencing_token(tmp_path: Path):
    log = tmp_path / "leases.jsonl"
    actor = ActorContext(actor_id="human.alice", actor_kind="human")
    lease = acquire_lease(resource_ref="human_work:hws_2", actor=actor, log_path=log)

    assert verify_lease(
        resource_ref="human_work:hws_2",
        lease_id=lease.lease_id,
        actor=actor,
        required=True,
        fencing_token=lease.fencing_token,
        log_path=log,
    ) == lease
    with pytest.raises(PermissionError, match="fencing token"):
        verify_lease(
            resource_ref="human_work:hws_2",
            lease_id=lease.lease_id,
            actor=actor,
            required=True,
            fencing_token=lease.fencing_token + 1,
            log_path=log,
        )


def test_lease_projects_to_resource_envelope(tmp_path: Path):
    log = tmp_path / "leases.jsonl"
    actor = ActorContext(actor_id="human.alice", actor_kind="human", role_id="role.manager")
    lease = acquire_lease(
        resource_ref="human_work:hws_3",
        actor=actor,
        ttl_seconds=60,
        purpose="integrate receipt",
        metadata={"cognitive_run_id": "run_123"},
        log_path=log,
    )

    resource = lease_resource(lease).as_dict()

    assert validate_resource(resource) == []
    assert resource["kind"] == "Lease"
    assert resource["metadata"]["name"] == lease.lease_id
    assert resource["metadata"]["annotations"]["cognitive_run_id"] == "run_123"
    assert resource["spec"]["resource_ref"] == "human_work:hws_3"
    assert resource["spec"]["held_by_actor_id"] == "human.alice"
    assert resource["spec"]["held_by_role_id"] == "role.manager"
    assert resource["spec"]["purpose"] == "integrate receipt"
    assert resource["status"]["state"] == "active"
    assert resource["status"]["fencing_token"] == lease.fencing_token
    assert {"rel": "leased_resource", "href": "human_work:hws_3"} in resource["links"]
    assert {"rel": "holder_actor", "href": "human.alice"} in resource["links"]
    assert {"rel": "holder_role", "href": "role.manager"} in resource["links"]


def test_lease_resource_reflects_released_state(tmp_path: Path):
    log = tmp_path / "leases.jsonl"
    actor = ActorContext(actor_id="human.alice", actor_kind="human", role_id="role.manager")
    lease = acquire_lease(
        resource_ref="accountability_case:acct_1",
        actor=actor,
        log_path=log,
    )
    released = release_lease(lease.lease_id, actor=actor, log_path=log)

    resource = lease_resource(released).as_dict()

    assert resource["status"]["state"] == "released"
    assert resource["status"]["released_at_utc"] is not None
    assert validate_resource(resource) == []


def test_lease_cli_can_render_resource_envelopes(tmp_path: Path, capsys):
    log = tmp_path / "leases.jsonl"
    actor = ActorContext(actor_id="service.kernel", actor_kind="service", role_id="role.manager")
    lease = acquire_lease(resource_ref="human_work:hws_4", actor=actor, log_path=log)

    rc = leases_main(["list", "--log-path", str(log), "--resource"])
    payloads = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]

    assert rc == 0
    assert len(payloads) == 1
    assert payloads[0]["kind"] == "Lease"
    assert payloads[0]["metadata"]["name"] == lease.lease_id
    assert validate_resource(payloads[0]) == []
