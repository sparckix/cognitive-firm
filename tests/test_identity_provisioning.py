from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.identity_provisioning import (  # noqa: E402
    DirectoryActor,
    DirectoryMembership,
    ProvisioningPlan,
    apply_provisioning_plan,
)
from cognitive_firm.orchestration.actor_identity import build_actor_context  # noqa: E402


def test_identity_provisioning_applies_actor_and_membership_idempotently(tmp_path: Path):
    actors = tmp_path / "actors.jsonl"
    memberships = tmp_path / "memberships.jsonl"
    plan = ProvisioningPlan(
        actors=[
            DirectoryActor(
                actor_id="human.alice",
                actor_kind="human",
                display_name="Alice",
                auth_subject="oidc:alice",
                identity_provider="corp-oidc",
                roles_allowed=["role.manager"],
                tenant_ids=["tenant-a"],
            )
        ],
        memberships=[
            DirectoryMembership(
                actor_id="human.alice",
                role_id="role.manager",
                granted_by="service.provisioner",
                decision_right_basis="directory group cf-managers",
                tenant_id="tenant-a",
            )
        ],
    )

    created = apply_provisioning_plan(
        plan,
        actor_identity_log=actors,
        actor_membership_log=memberships,
    )
    repeated = apply_provisioning_plan(
        plan,
        actor_identity_log=actors,
        actor_membership_log=memberships,
    )

    assert len(created.actors_created) == 1
    assert len(created.memberships_created) == 1
    assert repeated.actors_existing == ["human.alice"]
    assert repeated.memberships_existing == [created.memberships_created[0].assignment_id]
    context = build_actor_context(
        actor_id="human.alice",
        role_id="role.manager",
        tenant_id="tenant-a",
        identity_log=actors,
        membership_log=memberships,
        enforce_registered=True,
        enforce_membership=True,
    )
    assert context.auth_subject == "oidc:alice"
