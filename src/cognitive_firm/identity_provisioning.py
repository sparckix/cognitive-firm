"""Directory-to-kernel provisioning seam for actor identities and memberships.

This module is not an IAM admin system. It lets an IdP, HRIS, SCIM bridge, or
tenant setup script compile external directory facts into kernel-owned actor
identity and actor-membership records.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cognitive_firm.orchestration.actor_identity import (
    ActorIdentity,
    get_actor_identity,
    register_actor_identity,
)
from cognitive_firm.orchestration.actor_membership import (
    ActorMembership,
    grant_actor_membership,
    list_actor_memberships,
)


@dataclass(frozen=True)
class DirectoryActor:
    actor_id: str
    actor_kind: str
    display_name: str
    auth_subject: str
    identity_provider: str
    roles_allowed: list[str] = field(default_factory=list)
    tenant_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DirectoryMembership:
    actor_id: str
    role_id: str
    granted_by: str
    decision_right_basis: str
    tenant_id: str | None = None
    project_id: str | None = None
    expires_at_utc: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProvisioningPlan:
    actors: list[DirectoryActor] = field(default_factory=list)
    memberships: list[DirectoryMembership] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "actors": [asdict(actor) for actor in self.actors],
            "memberships": [asdict(membership) for membership in self.memberships],
        }


@dataclass(frozen=True)
class ProvisioningResult:
    actors_created: list[ActorIdentity] = field(default_factory=list)
    actors_existing: list[str] = field(default_factory=list)
    memberships_created: list[ActorMembership] = field(default_factory=list)
    memberships_existing: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "actors_created": [asdict(actor) for actor in self.actors_created],
            "actors_existing": self.actors_existing,
            "memberships_created": [membership.as_dict() for membership in self.memberships_created],
            "memberships_existing": self.memberships_existing,
        }


def load_provisioning_plan(path: Path) -> ProvisioningPlan:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return provisioning_plan_from_payload(payload)


def provisioning_plan_from_payload(payload: dict[str, Any]) -> ProvisioningPlan:
    actors = [DirectoryActor(**dict(row)) for row in payload.get("actors", [])]
    memberships = [DirectoryMembership(**dict(row)) for row in payload.get("memberships", [])]
    return ProvisioningPlan(actors=actors, memberships=memberships)


def apply_provisioning_plan(
    plan: ProvisioningPlan,
    *,
    actor_identity_log: Path | None = None,
    actor_membership_log: Path | None = None,
) -> ProvisioningResult:
    """Apply a directory provisioning plan idempotently.

    Existing actors and matching active memberships are left in place. This
    function deliberately does not delete actors or revoke memberships; tenant
    lifecycle policy should issue explicit revocation records.
    """
    actors_created: list[ActorIdentity] = []
    actors_existing: list[str] = []
    memberships_created: list[ActorMembership] = []
    memberships_existing: list[str] = []

    for actor in plan.actors:
        existing = get_actor_identity(actor.actor_id, log_path=actor_identity_log)
        if existing is not None:
            actors_existing.append(actor.actor_id)
            continue
        actors_created.append(
            register_actor_identity(
                actor_id=actor.actor_id,
                actor_kind=actor.actor_kind,
                display_name=actor.display_name,
                auth_subject=actor.auth_subject,
                identity_provider=actor.identity_provider,
                roles_allowed=actor.roles_allowed,
                tenant_ids=actor.tenant_ids,
                metadata=actor.metadata,
                log_path=actor_identity_log,
            )
        )

    for membership in plan.memberships:
        existing = list_actor_memberships(
            actor_id=membership.actor_id,
            role_id=membership.role_id,
            tenant_id=membership.tenant_id,
            project_id=membership.project_id,
            status="active",
            log_path=actor_membership_log,
        )
        if existing:
            memberships_existing.append(existing[0].assignment_id)
            continue
        memberships_created.append(
            grant_actor_membership(
                actor_id=membership.actor_id,
                role_id=membership.role_id,
                granted_by=membership.granted_by,
                decision_right_basis=membership.decision_right_basis,
                tenant_id=membership.tenant_id,
                project_id=membership.project_id,
                expires_at_utc=membership.expires_at_utc,
                metadata=membership.metadata,
                log_path=actor_membership_log,
            )
        )

    return ProvisioningResult(
        actors_created=actors_created,
        actors_existing=actors_existing,
        memberships_created=memberships_created,
        memberships_existing=memberships_existing,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply cognitive-firm identity provisioning plans.")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--actor-identity-log", type=Path)
    parser.add_argument("--actor-membership-log", type=Path)
    args = parser.parse_args(argv)
    result = apply_provisioning_plan(
        load_provisioning_plan(args.plan),
        actor_identity_log=args.actor_identity_log,
        actor_membership_log=args.actor_membership_log,
    )
    print(json.dumps(result.as_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
