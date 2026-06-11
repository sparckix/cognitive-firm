"""Tests for the userland kernel-service routes: L1 attention, L4 vocabulary."""

from __future__ import annotations

import json

from cognitive_firm.kernel_service import (
    KernelServiceConfig,
    dispatch_kernel_request,
)
from cognitive_firm.orchestration.actor_membership import grant_actor_membership
from cognitive_firm.orchestration.human_work import create_human_work_session


def test_vocabulary_route_serves_the_glossary():
    resp = dispatch_kernel_request("GET", "/kernel/vocabulary")
    assert resp.status == 200
    assert resp.payload["schema_version"] == 1
    assert any(term["key"] == "gate" for term in resp.payload["terms"])


def test_attention_route_is_empty_for_a_quiet_org(tmp_path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "hw.jsonl",
        gates_dir=tmp_path / "gates",
        org_dir=tmp_path,
        actor_membership_log=tmp_path / "m.jsonl",
    )
    resp = dispatch_kernel_request(
        "GET", "/kernel/attention/alice", config=config
    )
    assert resp.status == 200
    assert resp.payload["actor_id"] == "alice"
    assert resp.payload["signals"] == []


def test_attention_route_routes_a2h_work_to_the_member_human(tmp_path):
    human_work = tmp_path / "hw.jsonl"
    create_human_work_session(
        requested_by="research_office",
        human_actor="alice",
        objective="review the draft",
        work_mode="edit",
        bottleneck_class="taste",
        agent_followup_required=True,
        log_path=human_work,
    )
    config = KernelServiceConfig(
        human_work_log=human_work,
        gates_dir=tmp_path / "gates",
        org_dir=tmp_path,
        actor_membership_log=tmp_path / "m.jsonl",
    )
    resp = dispatch_kernel_request(
        "GET", "/kernel/attention/alice", config=config
    )
    assert resp.status == 200
    signals = resp.payload["signals"]
    assert len(signals) == 1
    assert signals[0]["signal_class"] == "work_interrupt"
    assert signals[0]["target_actor_id"] == "alice"

    # a different participant's feed does not see Alice's work
    other = dispatch_kernel_request(
        "GET", "/kernel/attention/bob", config=config
    )
    assert other.payload["signals"] == []


def test_attention_route_uses_authority_domain_for_governance_gate(tmp_path):
    roles = tmp_path / "roles"
    roles.mkdir()
    (roles / "principal.yaml").write_text("role_id: principal\nrole_class: authority\n")
    (roles / "tenant_authority.yaml").write_text(
        "role_id: tenant_authority\nrole_class: authority\n"
    )
    domains = tmp_path / "authority_domains" / "authority_domains.json"
    domains.parent.mkdir()
    domains.write_text(
        json.dumps(
            {
                "authority_domains": [
                    {
                        "domain_id": "global",
                        "authority_role_id": "role.principal",
                        "scope_kind": "global",
                        "scope_id": "*",
                    },
                    {
                        "domain_id": "tenant_a",
                        "authority_role_id": "role.tenant_authority",
                        "scope_kind": "tenant",
                        "scope_id": "tenant-a",
                    },
                ]
            }
        )
    )
    gates = tmp_path / "gates"
    gates.mkdir()
    (gates / "tenant_gate.json").write_text(
        json.dumps(
            {
                "goal_name": "Approve tenant policy",
                "gate_description": "tenant scoped review",
                "tenant_id": "tenant-a",
            }
        )
    )
    membership_log = tmp_path / "memberships.jsonl"
    grant_actor_membership(
        actor_id="agent.tenant_governor",
        role_id="tenant_authority",
        granted_by="human.root",
        decision_right_basis="tenant operating agreement delegates bounded policy review",
        tenant_id="tenant-a",
        log_path=membership_log,
    )
    grant_actor_membership(
        actor_id="human.root",
        role_id="principal",
        granted_by="human.root",
        decision_right_basis="founding authority",
        log_path=membership_log,
    )

    config = KernelServiceConfig(
        human_work_log=tmp_path / "hw.jsonl",
        gates_dir=gates,
        org_dir=tmp_path,
        actor_membership_log=membership_log,
    )

    tenant_feed = dispatch_kernel_request(
        "GET", "/kernel/attention/agent.tenant_governor", config=config
    )
    root_feed = dispatch_kernel_request(
        "GET", "/kernel/attention/human.root", config=config
    )

    assert tenant_feed.status == 200
    assert [signal["target_role_id"] for signal in tenant_feed.payload["signals"]] == [
        "tenant_authority"
    ]
    assert [signal["target_actor_id"] for signal in tenant_feed.payload["signals"]] == [
        "agent.tenant_governor"
    ]
    assert root_feed.payload["signals"] == []


def test_work_inbox_route_lists_a_member_humans_tasks(tmp_path):
    human_work = tmp_path / "hw.jsonl"
    create_human_work_session(
        requested_by="research_office",
        human_actor="alice",
        objective="review the draft",
        work_mode="edit",
        bottleneck_class="taste",
        log_path=human_work,
    )
    config = KernelServiceConfig(human_work_log=human_work)
    resp = dispatch_kernel_request(
        "GET", "/kernel/work-inbox/alice", config=config
    )
    assert resp.status == 200
    assert resp.payload["actor_id"] == "alice"
    assert len(resp.payload["items"]) == 1
    assert resp.payload["items"][0]["objective"] == "review the draft"


def test_surface_policy_blocks_a_projection_only_surface(tmp_path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "hw.jsonl",
        surface_write_modes={"orbit": "projection_only"},
    )
    resp = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        body={"actor_context": {"surface": "orbit"}},
        config=config,
    )
    # A surface-policy denial is an authorization failure, not a state
    # conflict — 403, so clients do not retry it as transient.
    assert resp.status == 403


def test_surface_policy_allows_an_unrestricted_surface(tmp_path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "hw.jsonl",
        surface_write_modes={"orbit": "projection_only"},
    )
    # 'cli' is not projection-only; the guard lets it through (the request may
    # still fail downstream for an unrelated reason, but not with a 409).
    resp = dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        body={"actor_context": {"surface": "cli"}},
        config=config,
    )
    assert resp.status != 403
