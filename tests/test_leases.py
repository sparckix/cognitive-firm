from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.actor_identity import ActorContext  # noqa: E402
from cognitive_firm.orchestration.leases import (  # noqa: E402
    acquire_lease,
    list_leases,
    release_lease,
    verify_lease,
)


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
