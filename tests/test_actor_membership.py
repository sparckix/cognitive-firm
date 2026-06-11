from __future__ import annotations

import json
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
    actor_membership_resource,
    grant_actor_membership,
    list_actor_memberships,
    main as actor_membership_main,
    revoke_actor_membership,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


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


def test_actor_membership_projects_to_resource_envelope(tmp_path: Path):
    memberships = tmp_path / "memberships.jsonl"
    membership = grant_actor_membership(
        actor_id="human.alice",
        role_id="role.manager",
        granted_by="human.owner",
        decision_right_basis="operating agreement section 2",
        tenant_id="tenant-a",
        project_id="project-a",
        starts_at_utc="2026-06-10T00:00:00+00:00",
        expires_at_utc="2026-07-10T00:00:00+00:00",
        metadata={"review_ticket": "ticket-1"},
        log_path=memberships,
    )

    resource = actor_membership_resource(membership).as_dict()

    assert validate_resource(resource) == []
    assert resource["kind"] == "ActorMembership"
    assert resource["metadata"]["name"] == membership.assignment_id
    assert resource["metadata"]["tenant_id"] == "tenant-a"
    assert resource["metadata"]["project_id"] == "project-a"
    assert resource["metadata"]["annotations"]["review_ticket"] == "ticket-1"
    assert resource["spec"]["actor_id"] == "human.alice"
    assert resource["spec"]["role_id"] == "role.manager"
    assert resource["spec"]["decision_right_basis"] == "operating agreement section 2"
    assert resource["status"]["status"] == "active"
    assert {"rel": "actor", "href": "human.alice"} in resource["links"]
    assert {"rel": "role", "href": "role.manager"} in resource["links"]
    assert {"rel": "granted_by", "href": "human.owner"} in resource["links"]


def test_actor_membership_cli_can_render_resource_envelopes(tmp_path: Path, capsys):
    memberships = tmp_path / "memberships.jsonl"
    membership = grant_actor_membership(
        actor_id="human.alice",
        role_id="role.manager",
        granted_by="human.owner",
        decision_right_basis="test basis",
        log_path=memberships,
    )

    rc = actor_membership_main(["list", "--log-path", str(memberships), "--resource"])
    payloads = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]

    assert rc == 0
    assert len(payloads) == 1
    assert payloads[0]["kind"] == "ActorMembership"
    assert payloads[0]["metadata"]["name"] == membership.assignment_id
    assert validate_resource(payloads[0]) == []
