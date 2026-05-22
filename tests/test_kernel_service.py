from __future__ import annotations

import http.client
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.kernel_service import (  # noqa: E402
    KernelServiceConfig,
    dispatch_kernel_request,
    make_kernel_server,
)
from cognitive_firm.identity_providers import (  # noqa: E402
    AuthenticatedSubject,
    StaticBearerTokenIdentityProvider,
)
from cognitive_firm.orchestration.state_backends import SqliteMutationBackend  # noqa: E402


def test_kernel_service_creates_and_updates_a2h_human_work(tmp_path: Path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
    )

    created = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "coordination_pattern": "a2h_work_request",
            "requested_by": "role.researcher",
            "human_actor": "principal",
            "objective": "Check restricted source.",
            "work_mode": "source_check",
            "bottleneck_class": "access",
            "human_deliverable": "support claim",
        },
        config=config,
    )

    assert created.status == 201
    session_id = created.payload["session"]["session_id"]

    surface = dispatch_kernel_request("GET", "/kernel/org-surface", config=config)
    assert surface.payload["surface"]["counts"]["a2h_waiting_on_human_sessions"] == 1
    assert surface.payload["surface"]["counts"]["a2h_followup_sessions"] == 0

    for state in ("claimed", "in_progress"):
        updated = dispatch_kernel_request(
            "POST",
            f"/kernel/human-work/{session_id}/state",
            {"state": state},
            config=config,
        )
        assert updated.status == 200

    completed = dispatch_kernel_request(
        "POST",
        f"/kernel/human-work/{session_id}/state",
        {
            "state": "completed",
            "completion_summary": "Source supports the claim.",
            "receipt": "source note",
        },
        config=config,
    )
    assert completed.status == 200

    surface = dispatch_kernel_request("GET", "/kernel/org-surface", config=config)
    assert surface.payload["surface"]["counts"]["a2h_waiting_on_human_sessions"] == 0
    assert surface.payload["surface"]["counts"]["a2h_followup_sessions"] == 1


def test_kernel_service_blocks_receipt_required_integration_without_receipt(tmp_path: Path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
    )
    created = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "principal",
            "objective": "Verify source.",
            "work_mode": "source_check",
            "bottleneck_class": "access",
            "receipt_required": True,
            "receipt_type": "note",
        },
        config=config,
    )
    session_id = created.payload["session"]["session_id"]
    for state in ("claimed", "in_progress", "completed"):
        response = dispatch_kernel_request(
            "POST",
            f"/kernel/human-work/{session_id}/state",
            {"state": state},
            config=config,
        )
        assert response.status == 200

    blocked = dispatch_kernel_request(
        "POST",
        f"/kernel/human-work/{session_id}/state",
        {"state": "integrated"},
        config=config,
    )

    assert blocked.status == 400
    assert "requires receipt" in blocked.payload["error"]


def test_kernel_service_surfaces_accountability_cases(tmp_path: Path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
    )

    created = dispatch_kernel_request(
        "POST",
        "/kernel/accountability-cases",
        {
            "trigger_ref": "action:external-send",
            "accountable_role": "role.manager",
            "responsible_actor": "agent.researcher",
            "decision_right_basis": "role mandate",
            "authority_envelope_ref": "org/roles/manager.yaml",
            "risk_tier": "high",
            "recourse_path": "reopen",
        },
        config=config,
    )
    assert created.status == 201

    summary = dispatch_kernel_request("GET", "/kernel/accountability-summary", config=config)
    kinds = {
        item["source_kind"]
        for item in summary.payload["summary"]["items"]
    }
    assert "accountability_case" in kinds


def test_kernel_service_can_enforce_registered_actor_and_lease(tmp_path: Path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        actor_membership_log=tmp_path / "memberships.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        enforce_registered_actors=True,
        require_leases=True,
    )
    actor_context = {
        "actor_id": "human.alice",
        "actor_kind": "human",
        "role_id": "role.manager",
        "surface": "test",
    }

    registered = dispatch_kernel_request(
        "POST",
        "/kernel/actors",
        {
            "actor_id": "human.alice",
            "actor_kind": "human",
            "display_name": "Alice",
            "roles_allowed": ["role.manager"],
            "actor_context": {
                "actor_id": "service.bootstrap",
                "actor_kind": "service",
            },
        },
        config=KernelServiceConfig(
            human_work_log=config.human_work_log,
            accountability_cases_log=config.accountability_cases_log,
            actor_identity_log=config.actor_identity_log,
            actor_membership_log=config.actor_membership_log,
            leases_log=config.leases_log,
        ),
    )
    assert registered.status == 201

    blocked = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "principal",
            "objective": "Verify source.",
            "work_mode": "source_check",
            "bottleneck_class": "access",
            "actor_context": actor_context,
        },
        config=config,
    )
    assert blocked.status == 400
    assert "lease required" in blocked.payload["error"]

    lease = dispatch_kernel_request(
        "POST",
        "/kernel/leases",
        {
            "resource_ref": "human_work:create",
            "ttl_seconds": 60,
            "actor_context": actor_context,
        },
        config=config,
    )
    assert lease.status == 201

    created = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "principal",
            "objective": "Verify source.",
            "work_mode": "source_check",
            "bottleneck_class": "access",
            "actor_context": actor_context,
            "lease_id": lease.payload["lease"]["lease_id"],
            "fencing_token": lease.payload["lease"]["fencing_token"],
        },
        config=config,
    )
    assert created.status == 201

    stale = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "principal",
            "objective": "Verify source again.",
            "work_mode": "source_check",
            "bottleneck_class": "access",
            "actor_context": actor_context,
            "lease_id": lease.payload["lease"]["lease_id"],
            "fencing_token": lease.payload["lease"]["fencing_token"] + 1,
        },
        config=config,
    )
    assert stale.status == 400
    assert "fencing token" in stale.payload["error"]


def test_kernel_service_enforces_membership_for_multiple_humans(tmp_path: Path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        actor_membership_log=tmp_path / "memberships.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        enforce_registered_actors=True,
        enforce_actor_membership=True,
    )
    bootstrap = KernelServiceConfig(
        human_work_log=config.human_work_log,
        accountability_cases_log=config.accountability_cases_log,
        actor_identity_log=config.actor_identity_log,
        actor_membership_log=config.actor_membership_log,
        leases_log=config.leases_log,
    )

    for actor_id, role_id in (
        ("human.alice", "role.manager"),
        ("human.bob", "role.reviewer"),
    ):
        registered = dispatch_kernel_request(
            "POST",
            "/kernel/actors",
            {
                "actor_id": actor_id,
                "actor_kind": "human",
                "display_name": actor_id,
                "roles_allowed": [role_id],
                "tenant_ids": ["tenant-a"],
                "actor_context": {
                    "actor_id": "service.bootstrap",
                    "actor_kind": "service",
                },
            },
            config=bootstrap,
        )
        assert registered.status == 201

    granted = dispatch_kernel_request(
        "POST",
        "/kernel/memberships",
        {
            "actor_id": "human.alice",
            "role_id": "role.manager",
            "granted_by": "human.owner",
            "decision_right_basis": "team operating agreement",
            "tenant_id": "tenant-a",
            "actor_context": {
                "actor_id": "service.bootstrap",
                "actor_kind": "service",
            },
        },
        config=bootstrap,
    )
    assert granted.status == 201

    accepted = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "human.alice",
            "objective": "Verify source.",
            "work_mode": "source_check",
            "bottleneck_class": "access",
            "actor_context": {
                "actor_id": "human.alice",
                "actor_kind": "human",
                "role_id": "role.manager",
                "tenant_id": "tenant-a",
            },
        },
        config=config,
    )
    assert accepted.status == 201

    blocked = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.reviewer",
            "human_actor": "human.bob",
            "objective": "Review source.",
            "work_mode": "source_check",
            "bottleneck_class": "review",
            "actor_context": {
                "actor_id": "human.bob",
                "actor_kind": "human",
                "role_id": "role.reviewer",
                "tenant_id": "tenant-a",
            },
        },
        config=config,
    )
    assert blocked.status == 400
    assert "no active membership" in blocked.payload["error"]


def test_kernel_service_identity_admin_routes_require_admin_role(tmp_path: Path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        actor_membership_log=tmp_path / "memberships.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        enforce_registered_actors=True,
        enforce_actor_membership=True,
    )
    bootstrap = KernelServiceConfig(
        human_work_log=config.human_work_log,
        accountability_cases_log=config.accountability_cases_log,
        actor_identity_log=config.actor_identity_log,
        actor_membership_log=config.actor_membership_log,
        leases_log=config.leases_log,
    )
    for actor_id, role_id in (
        ("human.alice", "role.manager"),
        ("human.admin", "role.identity_admin"),
    ):
        registered = dispatch_kernel_request(
            "POST",
            "/kernel/actors",
            {
                "actor_id": actor_id,
                "actor_kind": "human",
                "display_name": actor_id,
                "roles_allowed": [role_id],
                "tenant_ids": ["tenant-a"],
                "actor_context": {"actor_id": "service.bootstrap", "actor_kind": "service"},
            },
            config=bootstrap,
        )
        assert registered.status == 201
        granted = dispatch_kernel_request(
            "POST",
            "/kernel/memberships",
            {
                "actor_id": actor_id,
                "role_id": role_id,
                "granted_by": "service.bootstrap",
                "decision_right_basis": "test bootstrap",
                "tenant_id": "tenant-a",
                "actor_context": {"actor_id": "service.bootstrap", "actor_kind": "service"},
            },
            config=bootstrap,
        )
        assert granted.status == 201

    blocked = dispatch_kernel_request(
        "POST",
        "/kernel/memberships",
        {
            "actor_id": "human.alice",
            "role_id": "role.reviewer",
            "granted_by": "human.alice",
            "decision_right_basis": "self grant",
            "tenant_id": "tenant-a",
            "actor_context": {
                "actor_id": "human.alice",
                "actor_kind": "human",
                "role_id": "role.manager",
                "tenant_id": "tenant-a",
            },
        },
        config=config,
    )
    assert blocked.status == 400
    assert "identity admin role required" in blocked.payload["error"]

    accepted = dispatch_kernel_request(
        "POST",
        "/kernel/memberships",
        {
            "actor_id": "human.alice",
            "role_id": "role.reviewer",
            "granted_by": "human.admin",
            "decision_right_basis": "admin grant",
            "tenant_id": "tenant-a",
            "actor_context": {
                "actor_id": "human.admin",
                "actor_kind": "human",
                "role_id": "role.identity_admin",
                "tenant_id": "tenant-a",
            },
        },
        config=config,
    )
    assert accepted.status == 201


def test_kernel_service_identity_admin_requires_explicit_registered_role(tmp_path: Path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        actor_membership_log=tmp_path / "memberships.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        enforce_registered_actors=True,
    )
    bootstrap = KernelServiceConfig(
        human_work_log=config.human_work_log,
        accountability_cases_log=config.accountability_cases_log,
        actor_identity_log=config.actor_identity_log,
        actor_membership_log=config.actor_membership_log,
        leases_log=config.leases_log,
    )
    registered = dispatch_kernel_request(
        "POST",
        "/kernel/actors",
        {
            "actor_id": "human.admin",
            "actor_kind": "human",
            "display_name": "Admin without explicit roles",
            "roles_allowed": [],
            "actor_context": {"actor_id": "service.bootstrap", "actor_kind": "service"},
        },
        config=bootstrap,
    )
    assert registered.status == 201

    blocked = dispatch_kernel_request(
        "POST",
        "/kernel/actors",
        {
            "actor_id": "human.other",
            "actor_kind": "human",
            "display_name": "Other",
            "actor_context": {
                "actor_id": "human.admin",
                "actor_kind": "human",
                "role_id": "role.identity_admin",
            },
        },
        config=config,
    )

    assert blocked.status == 400
    assert "explicitly allowed" in blocked.payload["error"]


def test_kernel_service_auth_provider_supplies_actor_context(tmp_path: Path):
    provider = StaticBearerTokenIdentityProvider(
        {
            "secret": AuthenticatedSubject(
                auth_subject="oidc:alice",
                identity_provider="test-idp",
                actor_id="human.alice",
                actor_kind="human",
            )
        }
    )
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        identity_provider=provider,
    )

    blocked = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "principal",
            "objective": "Verify source.",
            "work_mode": "source_check",
            "bottleneck_class": "access",
        },
        config=config,
        headers={"Authorization": "Bearer wrong"},
    )
    assert blocked.status == 400
    assert "authentication failed" in blocked.payload["error"]

    created = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "principal",
            "objective": "Verify source.",
            "work_mode": "source_check",
            "bottleneck_class": "access",
        },
        config=config,
        headers={"Authorization": "Bearer secret"},
    )
    assert created.status == 201


def test_kernel_service_http_get_forwards_auth_headers(tmp_path: Path):
    provider = StaticBearerTokenIdentityProvider(
        {
            "secret": AuthenticatedSubject(
                auth_subject="oidc:service",
                identity_provider="test-idp",
                actor_id="service.kernel",
                actor_kind="service",
            )
        }
    )
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        identity_provider=provider,
    )
    try:
        server = make_kernel_server(host="127.0.0.1", port=0, config=config)
    except PermissionError:
        pytest.skip("local socket binding is unavailable in this sandbox")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/health", headers={"Authorization": "Bearer secret"})
        health = conn.getresponse()
        assert health.status == 200
        health.read()
        conn.close()

        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/kernel/org-surface", headers={"Authorization": "Bearer secret"})
        surface = conn.getresponse()
        assert surface.status == 200
        surface.read()
        conn.close()

        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request("GET", "/health", headers={"Authorization": "Bearer wrong"})
        blocked = conn.getresponse()
        assert blocked.status == 400
        blocked.read()
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_kernel_service_rejects_authenticated_actor_spoof(tmp_path: Path):
    provider = StaticBearerTokenIdentityProvider(
        {
            "alice-token": AuthenticatedSubject(
                auth_subject="oidc:alice",
                identity_provider="test-idp",
                actor_id="human.alice",
                actor_kind="human",
            )
        }
    )
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        identity_provider=provider,
        enforce_registered_actors=True,
    )
    bootstrap = KernelServiceConfig(
        human_work_log=config.human_work_log,
        accountability_cases_log=config.accountability_cases_log,
        actor_identity_log=config.actor_identity_log,
        leases_log=config.leases_log,
    )
    dispatch_kernel_request(
        "POST",
        "/kernel/actors",
        {
            "actor_id": "human.bob",
            "actor_kind": "human",
            "display_name": "Bob",
            "auth_subject": "oidc:bob",
            "identity_provider": "test-idp",
        },
        config=bootstrap,
    )

    blocked = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "principal",
            "objective": "Verify source.",
            "work_mode": "source_check",
            "bottleneck_class": "access",
            "actor_context": {"actor_id": "human.bob", "actor_kind": "human"},
        },
        config=config,
        headers={"Authorization": "Bearer alice-token"},
    )

    assert blocked.status == 400
    assert "human.alice" in blocked.payload["error"]


def test_kernel_service_can_enforce_authenticated_subject_role_and_tenant_scope(tmp_path: Path):
    provider = StaticBearerTokenIdentityProvider(
        {
            "alice-token": AuthenticatedSubject(
                auth_subject="oidc:alice",
                identity_provider="test-idp",
                actor_id="human.alice",
                actor_kind="human",
                roles_allowed=["role.manager"],
                tenant_ids=["tenant-a"],
            )
        }
    )
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        identity_provider=provider,
        enforce_subject_scope=True,
    )

    wrong_tenant = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "principal",
            "objective": "Verify source.",
            "work_mode": "source_check",
            "bottleneck_class": "access",
            "actor_context": {
                "role_id": "role.manager",
                "tenant_id": "tenant-b",
            },
        },
        config=config,
        headers={"Authorization": "Bearer alice-token"},
    )
    assert wrong_tenant.status == 400
    assert "tenant-b" in wrong_tenant.payload["error"]

    wrong_role = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.researcher",
            "human_actor": "principal",
            "objective": "Verify source.",
            "work_mode": "source_check",
            "bottleneck_class": "access",
            "actor_context": {
                "role_id": "role.researcher",
                "tenant_id": "tenant-a",
            },
        },
        config=config,
        headers={"Authorization": "Bearer alice-token"},
    )
    assert wrong_role.status == 400
    assert "role.researcher" in wrong_role.payload["error"]

    accepted = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "principal",
            "objective": "Verify source.",
            "work_mode": "source_check",
            "bottleneck_class": "access",
            "actor_context": {
                "role_id": "role.manager",
                "tenant_id": "tenant-a",
            },
        },
        config=config,
        headers={"Authorization": "Bearer alice-token"},
    )
    assert accepted.status == 201


def test_kernel_service_exposes_app_intent_routes(tmp_path: Path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        org_dir=tmp_path / "org",
        gates_dir=tmp_path / "workspace" / "gates" / "pending",
        gates_resolved_dir=tmp_path / "workspace" / "gates" / "resolved",
        transition_log=tmp_path / "workspace" / "transitions.jsonl",
    )
    config.gates_dir.mkdir(parents=True)
    (config.gates_dir / "gate_1.json").write_text(
        '{"gate_id":"gate_1","question":"approve?"}\n',
        encoding="utf-8",
    )

    gate = dispatch_kernel_request(
        "POST",
        "/kernel/gates/gate_1/resolve",
        {"chosen_option": "approve", "reason": "ok"},
        config=config,
    )
    directive = dispatch_kernel_request(
        "POST",
        "/kernel/directives",
        {"target_role": "researcher", "message": "Inspect source."},
        config=config,
    )
    control = dispatch_kernel_request(
        "POST",
        "/kernel/controls",
        {"target_role": "researcher", "action": "PAUSE"},
        config=config,
    )
    chat = dispatch_kernel_request(
        "POST",
        "/kernel/chat/messages",
        {"role_id": "researcher", "text": "Status?"},
        config=config,
    )
    (config.org_dir / "roles").mkdir(parents=True)
    (config.org_dir / "roles" / "researcher.yaml").write_text(
        "role_id: researcher\n",
        encoding="utf-8",
    )
    utilization = dispatch_kernel_request(
        "POST",
        "/kernel/roles/researcher/agent-utilization",
        {
            "agent_utilization": {
                "daily_cap_seconds": 10,
                "daily_cap_output_tokens": 1000,
                "daily_cap_turn_count": 3,
                "session_cap_seconds": 5,
                "absolute_ceiling_seconds": 20,
                "warn_threshold_frac": 0.8,
            }
        },
        config=config,
    )

    assert gate.status == 200
    assert directive.status == 201
    assert control.status == 201
    assert chat.status == 201
    assert utilization.status == 200
    assert (config.gates_resolved_dir / "gate_1.json").exists()
    assert (config.gates_dir / "gate_1.json.handled").exists()
    assert list((config.org_dir / "directives").glob("*_researcher.json"))
    assert (config.org_dir / "controls" / "researcher.json").exists()
    assert list((config.org_dir / "sessions" / "researcher" / "chat").glob("*.jsonl"))
    assert "agent_utilization" in (config.org_dir / "roles" / "researcher.yaml").read_text(
        encoding="utf-8"
    )
    transition_rows = config.transition_log.read_text(encoding="utf-8").splitlines()
    assert len(transition_rows) == 5


def test_kernel_service_can_use_sqlite_mutation_backend_for_fenced_events(tmp_path: Path):
    backend = SqliteMutationBackend(tmp_path / "mutations.sqlite3")
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        mutation_backend=backend,
    )
    actor_context = {
        "actor_id": "human.alice",
        "actor_kind": "human",
        "role_id": "role.manager",
        "surface": "test",
    }

    lease = dispatch_kernel_request(
        "POST",
        "/kernel/leases",
        {
            "resource_ref": "demo:resource",
            "ttl_seconds": 60,
            "actor_context": actor_context,
        },
        config=config,
    )
    assert lease.status == 201
    assert not (tmp_path / "leases.jsonl").exists()

    appended = dispatch_kernel_request(
        "POST",
        "/kernel/mutation-events",
        {
            "stream": "transitions",
            "resource_ref": "demo:resource",
            "lease_id": lease.payload["lease"]["lease_id"],
            "fencing_token": lease.payload["lease"]["fencing_token"],
            "event": {"event": "demo.updated", "value": 1},
            "actor_context": actor_context,
        },
        config=config,
    )
    assert appended.status == 201
    assert backend.read_events("transitions")[0]["event"] == "demo.updated"

    stale = dispatch_kernel_request(
        "POST",
        "/kernel/mutation-events",
        {
            "stream": "transitions",
            "resource_ref": "demo:resource",
            "lease_id": lease.payload["lease"]["lease_id"],
            "fencing_token": lease.payload["lease"]["fencing_token"] + 1,
            "event": {"event": "demo.updated", "value": 2},
            "actor_context": actor_context,
        },
        config=config,
    )
    assert stale.status == 400
    assert len(backend.read_events("transitions")) == 1


def test_kernel_service_primitive_routes_verify_sqlite_mutation_leases(tmp_path: Path):
    backend = SqliteMutationBackend(tmp_path / "mutations.sqlite3")
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        mutation_backend=backend,
        require_leases=True,
    )
    actor_context = {
        "actor_id": "human.alice",
        "actor_kind": "human",
        "role_id": "role.manager",
        "surface": "test",
    }

    missing = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "human.alice",
            "objective": "verify source",
            "actor_context": actor_context,
        },
        config=config,
    )
    assert missing.status == 400
    assert "active lease is required" in missing.payload["error"]

    lease = dispatch_kernel_request(
        "POST",
        "/kernel/leases",
        {
            "resource_ref": "human_work:create",
            "ttl_seconds": 60,
            "actor_context": actor_context,
        },
        config=config,
    )
    assert lease.status == 201

    created = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "human.alice",
            "objective": "verify source",
            "lease_id": lease.payload["lease"]["lease_id"],
            "fencing_token": lease.payload["lease"]["fencing_token"],
            "actor_context": actor_context,
        },
        config=config,
    )
    assert created.status == 201
    assert not (tmp_path / "leases.jsonl").exists()

    stale = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "requested_by": "role.manager",
            "human_actor": "human.alice",
            "objective": "verify another source",
            "lease_id": lease.payload["lease"]["lease_id"],
            "fencing_token": lease.payload["lease"]["fencing_token"] + 1,
            "actor_context": actor_context,
        },
        config=config,
    )
    assert stale.status == 400
    assert "fencing token" in stale.payload["error"]


def test_kernel_service_runs_a_work_item_through_an_operating_unit(tmp_path: Path):
    config = KernelServiceConfig(
        work_items_log=tmp_path / "work_items.jsonl",
        operating_units_log=tmp_path / "operating_units.jsonl",
        kernel_events_log=tmp_path / "kernel_events.jsonl",
    )

    defined = dispatch_kernel_request(
        "POST",
        "/kernel/operating-units",
        {
            "unit_id": "support_desk",
            "unit_kind": "qualification_desk",
            "display_name": "Support Desk",
            "owner_role": "role.support_manager",
            "allowed_work_kinds": ["triage_ticket"],
            "allowed_exits": ["resolved", "escalated"],
        },
        config=config,
    )
    assert defined.status == 201

    enqueued = dispatch_kernel_request(
        "POST",
        "/kernel/work-items",
        {"unit_id": "support_desk", "kind": "triage_ticket", "payload": {"ticket": "T-1"}},
        config=config,
    )
    assert enqueued.status == 201
    work_id = enqueued.payload["work_item"]["work_id"]

    claimed = dispatch_kernel_request(
        "POST",
        "/kernel/work-items/claim-next",
        {"unit_id": "support_desk", "actor": "actor.agent_1"},
        config=config,
    )
    assert claimed.status == 200
    token = claimed.payload["work_item"]["claim_token"]

    completed = dispatch_kernel_request(
        "POST",
        f"/kernel/work-items/{work_id}/complete",
        {"actor": "actor.agent_1", "claim_token": token, "exit_kind": "resolved"},
        config=config,
    )
    assert completed.status == 200
    assert completed.payload["work_item"]["status"] == "done"

    dashboard = dispatch_kernel_request(
        "GET", "/kernel/operating-unit-dashboard", config=config
    )
    assert dashboard.status == 200
    unit = dashboard.payload["dashboard"]["units"][0]
    assert unit["unit_id"] == "support_desk"
    assert unit["done"] == 1


def test_kernel_service_rejects_unbounded_work_item_exit(tmp_path: Path):
    config = KernelServiceConfig(
        work_items_log=tmp_path / "work_items.jsonl",
        operating_units_log=tmp_path / "operating_units.jsonl",
        kernel_events_log=tmp_path / "kernel_events.jsonl",
    )
    dispatch_kernel_request(
        "POST",
        "/kernel/operating-units",
        {
            "unit_id": "support_desk",
            "unit_kind": "qualification_desk",
            "display_name": "Support Desk",
            "owner_role": "role.support_manager",
            "allowed_work_kinds": ["triage_ticket"],
            "allowed_exits": ["resolved"],
        },
        config=config,
    )
    enqueued = dispatch_kernel_request(
        "POST",
        "/kernel/work-items",
        {"unit_id": "support_desk", "kind": "triage_ticket"},
        config=config,
    )
    work_id = enqueued.payload["work_item"]["work_id"]
    claimed = dispatch_kernel_request(
        "POST",
        "/kernel/work-items/claim-next",
        {"unit_id": "support_desk", "actor": "actor.agent_1"},
        config=config,
    )
    token = claimed.payload["work_item"]["claim_token"]
    rejected = dispatch_kernel_request(
        "POST",
        f"/kernel/work-items/{work_id}/complete",
        {"actor": "actor.agent_1", "claim_token": token, "exit_kind": "not_an_exit"},
        config=config,
    )
    assert rejected.status == 400
    assert "allowed_exits" in rejected.payload["error"]


def test_kernel_service_routes_the_durable_learning_layer(tmp_path: Path):
    config = KernelServiceConfig(
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
        resource_allocation_log=tmp_path / "resource_allocation.jsonl",
        residual_rights_log=tmp_path / "residual_rights.jsonl",
        residual_decisions_log=tmp_path / "residual_decisions.jsonl",
        kernel_events_log=tmp_path / "kernel_events.jsonl",
    )

    # Outcome link: open, measure baseline + post, record a verdict.
    link = dispatch_kernel_request(
        "POST",
        "/kernel/outcome-links",
        {
            "change_ref": "le_42",
            "change_kind": "learning_event",
            "metric_name": "ticket_cycle_time",
            "metric_unit": "hours",
            "created_by": "actor.analyst",
        },
        config=config,
    )
    assert link.status == 201
    link_id = link.payload["outcome_link"]["outcome_link_id"]
    for kind, value in (("baseline", 12.0), ("post", 8.0)):
        snap = dispatch_kernel_request(
            "POST",
            f"/kernel/outcome-links/{link_id}/snapshots",
            {"kind": kind, "value": value, "captured_by": "actor.analyst"},
            config=config,
        )
        assert snap.status == 200
    verdict = dispatch_kernel_request(
        "POST",
        f"/kernel/outcome-links/{link_id}/verdict",
        {"verdict": "improved", "rationale": "cycle time fell after the change"},
        config=config,
    )
    assert verdict.status == 200
    summary = dispatch_kernel_request("GET", "/kernel/outcome-links/summary", config=config)
    assert summary.status == 200

    # Routine review: schedule one already overdue, confirm it surfaces as due.
    scheduled = dispatch_kernel_request(
        "POST",
        "/kernel/routine-reviews",
        {
            "routine_ref": "le_42",
            "routine_kind": "learning_event",
            "learning_event_id": "le_42",
            "review_due_utc": "2020-01-01T00:00:00+00:00",
            "scheduled_by": "actor.manager",
        },
        config=config,
    )
    assert scheduled.status == 201
    due = dispatch_kernel_request("GET", "/kernel/routine-reviews/due", config=config)
    assert due.status == 200
    assert len(due.payload["due_reviews"]) == 1

    # Resource allocation: record a move, apply it, read the ledger.
    decision = dispatch_kernel_request(
        "POST",
        "/kernel/allocation-decisions",
        {
            "resource_kind": "worker_capacity",
            "from_unit": "__reserve__",
            "to_unit": "triage_lane",
            "amount": 5,
            "deciding_role": "role.general_office",
            "authority_basis": "quarterly allocation review",
            "rationale": "triage backlog growth",
        },
        config=config,
    )
    assert decision.status == 201
    decision_id = decision.payload["allocation_decision"]["decision_id"]
    applied = dispatch_kernel_request(
        "POST", f"/kernel/allocation-decisions/{decision_id}/apply", {}, config=config
    )
    assert applied.status == 200
    ledger = dispatch_kernel_request(
        "GET", "/kernel/allocation-ledger/worker_capacity", config=config
    )
    assert ledger.status == 200
    assert ledger.payload["ledger"]["triage_lane"] == 5.0

    # Decision rights: assign a residual right, record a decision under it.
    assigned = dispatch_kernel_request(
        "POST",
        "/kernel/residual-rights",
        {
            "scope_kind": "project",
            "scope_ref": "proj.atlas",
            "holder_role": "role.project_lead",
            "basis": "charter delegates unspecified calls to the lead",
            "assigned_by": "actor.principal",
        },
        config=config,
    )
    assert assigned.status == 201
    holder = dispatch_kernel_request(
        "GET",
        "/kernel/residual-rights/holder?scope_kind=project&scope_ref=proj.atlas",
        config=config,
    )
    assert holder.status == 200
    assert holder.payload["holder"]["holder_role"] == "role.project_lead"
    residual = dispatch_kernel_request(
        "POST",
        "/kernel/residual-decisions",
        {
            "scope_kind": "project",
            "scope_ref": "proj.atlas",
            "deciding_role": "role.project_lead",
            "decision_summary": "chose vendor A; mandate was silent",
            "rationale": "time-critical and within project scope",
        },
        config=config,
    )
    assert residual.status == 201
    assert residual.payload["residual_decision"]["unauthorized"] is False
