from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.actor_identity import (  # noqa: E402
    actor_context_from_payload,
    build_actor_context,
    list_actor_identities,
    register_actor_identity,
)


def test_register_and_resolve_actor_identity(tmp_path: Path):
    log = tmp_path / "actors.jsonl"
    identity = register_actor_identity(
        actor_id="human.alice",
        actor_kind="human",
        display_name="Alice",
        auth_subject="oidc:alice",
        identity_provider="example-idp",
        roles_allowed=["role.manager"],
        tenant_ids=["tenant-a"],
        log_path=log,
    )

    context = build_actor_context(
        actor_id=identity.actor_id,
        role_id="role.manager",
        tenant_id="tenant-a",
        identity_log=log,
        enforce_registered=True,
    )

    assert context.actor_kind == "human"
    assert context.auth_subject == "oidc:alice"
    assert context.identity_provider == "example-idp"
    assert len(list_actor_identities(log_path=log)) == 1


def test_actor_context_enforces_registered_roles_and_tenants(tmp_path: Path):
    log = tmp_path / "actors.jsonl"
    register_actor_identity(
        actor_id="agent.researcher",
        actor_kind="agent",
        display_name="Researcher",
        roles_allowed=["role.researcher"],
        tenant_ids=["tenant-a"],
        log_path=log,
    )

    with pytest.raises(PermissionError, match="not allowed to act"):
        build_actor_context(
            actor_id="agent.researcher",
            role_id="role.manager",
            identity_log=log,
            enforce_registered=True,
        )

    with pytest.raises(PermissionError, match="not allowed in tenant"):
        build_actor_context(
            actor_id="agent.researcher",
            role_id="role.researcher",
            tenant_id="tenant-b",
            identity_log=log,
            enforce_registered=True,
        )


def test_actor_context_from_payload_allows_t1_unregistered_actor():
    context = actor_context_from_payload(
        {
            "actor_context": {
                "actor_id": "service.local",
                "actor_kind": "service",
                "role_id": "role.manager",
                "surface": "test",
            }
        }
    )

    assert context.actor_id == "service.local"
    assert context.role_id == "role.manager"
    assert context.surface == "test"


def test_actor_context_preserves_project_scope():
    context = actor_context_from_payload(
        {
            "actor_context": {
                "actor_id": "human.alice",
                "actor_kind": "human",
                "role_id": "role.manager",
                "tenant_id": "tenant-a",
                "project_id": "project-1",
            }
        }
    )

    assert context.tenant_id == "tenant-a"
    assert context.project_id == "project-1"
