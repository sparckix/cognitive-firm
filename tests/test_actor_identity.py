from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.actor_identity import (  # noqa: E402
    actor_context_from_payload,
    actor_identity_resource,
    build_actor_context,
    list_actor_identities,
    main as actor_identity_main,
    register_actor_identity,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


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


def test_actor_identity_projects_to_resource_envelope(tmp_path: Path):
    log = tmp_path / "actors.jsonl"
    identity = register_actor_identity(
        actor_id="service.importer",
        actor_kind="service",
        display_name="Importer Service",
        auth_subject="svc:importer",
        identity_provider="gateway",
        roles_allowed=["role.importer"],
        tenant_ids=["tenant-a"],
        metadata={"owner": "platform"},
        log_path=log,
    )

    resource = actor_identity_resource(identity).as_dict()

    assert validate_resource(resource) == []
    assert resource["kind"] == "ActorIdentity"
    assert resource["metadata"]["name"] == "service.importer"
    assert resource["metadata"]["annotations"]["owner"] == "platform"
    assert resource["spec"]["actor_kind"] == "service"
    assert resource["spec"]["roles_allowed"] == ["role.importer"]
    assert resource["status"]["status"] == "active"
    assert {"rel": "allowed_role", "href": "role.importer"} in resource["links"]
    assert {"rel": "tenant", "href": "tenant-a"} in resource["links"]


def test_actor_identity_cli_can_render_resource_envelopes(tmp_path: Path, capsys):
    log = tmp_path / "actors.jsonl"
    identity = register_actor_identity(
        actor_id="human.alice",
        actor_kind="human",
        display_name="Alice",
        roles_allowed=["role.manager"],
        log_path=log,
    )

    rc = actor_identity_main(["list", "--log-path", str(log), "--resource"])
    payloads = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]

    assert rc == 0
    assert len(payloads) == 1
    assert payloads[0]["kind"] == "ActorIdentity"
    assert payloads[0]["metadata"]["name"] == identity.actor_id
    assert validate_resource(payloads[0]) == []
