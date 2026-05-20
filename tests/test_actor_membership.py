from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.actor_identity import (  # noqa: E402
    build_actor_context,
    register_actor_identity,
)
from cognitive_firm.orchestration.actor_membership import (  # noqa: E402
    actor_has_membership,
    grant_actor_membership,
    list_actor_memberships,
    revoke_actor_membership,
)


def test_membership_grants_two_humans_distinct_roles(tmp_path: Path):
    identities = tmp_path / "actors.jsonl"
    memberships = tmp_path / "memberships.jsonl"

    for actor_id, role_id in (
        ("human.alice", "role.manager"),
        ("human.bob", "role.reviewer"),
    ):
        register_actor_identity(
            actor_id=actor_id,
            actor_kind="human",
            display_name=actor_id,
            roles_allowed=[role_id],
            tenant_ids=["tenant-a"],
            log_path=identities,
        )
        grant_actor_membership(
            actor_id=actor_id,
            role_id=role_id,
            granted_by="human.owner",
            decision_right_basis="team operating agreement",
            tenant_id="tenant-a",
            log_path=memberships,
        )

    alice = build_actor_context(
        actor_id="human.alice",
        role_id="role.manager",
        tenant_id="tenant-a",
        identity_log=identities,
        membership_log=memberships,
        enforce_registered=True,
        enforce_membership=True,
    )
    bob = build_actor_context(
        actor_id="human.bob",
        role_id="role.reviewer",
        tenant_id="tenant-a",
        identity_log=identities,
        membership_log=memberships,
        enforce_registered=True,
        enforce_membership=True,
    )

    assert alice.actor_kind == "human"
    assert bob.actor_kind == "human"
    assert len(list_actor_memberships(log_path=memberships)) == 2


def test_membership_enforcement_rejects_missing_or_expired_assignment(tmp_path: Path):
    identities = tmp_path / "actors.jsonl"
    memberships = tmp_path / "memberships.jsonl"
    register_actor_identity(
        actor_id="human.alice",
        actor_kind="human",
        display_name="Alice",
        roles_allowed=["role.manager"],
        tenant_ids=["tenant-a"],
        log_path=identities,
    )

    with pytest.raises(PermissionError, match="no active membership"):
        build_actor_context(
            actor_id="human.alice",
            role_id="role.manager",
            tenant_id="tenant-a",
            identity_log=identities,
            membership_log=memberships,
            enforce_registered=True,
            enforce_membership=True,
        )

    expired = grant_actor_membership(
        actor_id="human.alice",
        role_id="role.manager",
        granted_by="human.owner",
        decision_right_basis="time-boxed test",
        tenant_id="tenant-a",
        expires_at_utc=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        log_path=memberships,
    )

    assert actor_has_membership(
        actor_id="human.alice",
        role_id="role.manager",
        tenant_id="tenant-a",
        log_path=memberships,
    ) is False

    revoked = revoke_actor_membership(
        expired.assignment_id,
        revoked_by="human.owner",
        reason="test cleanup",
        log_path=memberships,
    )
    assert revoked.status == "revoked"
