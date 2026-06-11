"""Tests for L1 — the userland attention router."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cognitive_firm.userland import signal_classes as sc
from cognitive_firm.orchestration.actor_membership import grant_actor_membership
from cognitive_firm.userland.attention_router import (
    AttentionSignal,
    authority_resolver_from_org,
    pending_gate_signals,
    resolve_authority_role,
    route_signals,
    signals_for_actor,
)


def _gov_signal(signal_id: str = "g1") -> AttentionSignal:
    return AttentionSignal(
        signal_id=signal_id,
        kind="gate_pending",
        headline="Gate: a goal — needs a decision",
        source_ref=f"/gates/{signal_id}.json",
    )


def _work_signal(actor: str) -> AttentionSignal:
    return AttentionSignal(
        signal_id="hws_1",
        kind="a2h_waiting",
        headline="Review the draft",
        source_ref="hws_1",
        target_role_id="analyst",
        target_actor_id=actor,
    )


def test_governance_interrupt_routes_to_the_authority():
    routed = route_signals(
        [_gov_signal()],
        authority_actor_id="principal_actor",
        authority_role_id="principal",
    )
    assert len(routed) == 1
    r = routed[0]
    assert r.signal_class == sc.GOVERNANCE_INTERRUPT
    assert r.target_actor_id == "principal_actor"
    assert r.target_role_id == "principal"
    assert r.primary_action == "approve"


def test_governance_interrupt_can_route_by_signal_scope():
    tenant_gate = AttentionSignal(
        signal_id="g_tenant",
        kind="gate_pending",
        headline="Gate: tenant work",
        source_ref="gate",
        tenant_id="tenant-a",
    )

    routed = route_signals(
        [tenant_gate],
        authority_resolver=lambda signal: (
            "tenant_authority",
            "human.tenant_owner",
        )
        if signal.tenant_id == "tenant-a"
        else (None, None),
    )

    assert routed[0].target_role_id == "tenant_authority"
    assert routed[0].target_actor_id == "human.tenant_owner"


def test_work_interrupt_routes_to_the_named_member_human():
    routed = route_signals(
        [_work_signal("alice")], authority_actor_id="principal_actor"
    )
    r = routed[0]
    assert r.signal_class == sc.WORK_INTERRUPT
    assert r.target_actor_id == "alice"  # not the authority
    assert r.primary_action == "claim"


def test_unroutable_governance_signal_is_surfaced_not_dropped():
    routed = route_signals([_gov_signal()])  # no authority resolved
    assert len(routed) == 1
    assert routed[0].target_actor_id is None


def test_unassigned_work_interrupt_falls_back_to_the_authority():
    # F-19: an a2h_waiting session with no assigned human (target_actor_id
    # None) must reach the authority to be assigned, not vanish.
    unassigned = AttentionSignal(
        signal_id="hws_unassigned",
        kind="a2h_waiting",
        headline="Unassigned human-work session",
        source_ref="hws_unassigned",
        target_role_id=None,
        target_actor_id=None,
    )
    routed = route_signals(
        [unassigned],
        authority_actor_id="principal_actor",
        authority_role_id="principal",
    )
    r = routed[0]
    assert r.signal_class == sc.WORK_INTERRUPT
    assert r.target_actor_id == "principal_actor"
    assert r.target_role_id == "principal"
    # And it actually lands in the authority's feed.
    assert {x.signal_id for x in signals_for_actor(routed, "principal_actor")} == {
        "hws_unassigned"
    }


def test_unknown_kind_is_informational():
    routed = route_signals(
        [AttentionSignal("x", "mystery_kind", "huh", "ref")],
        authority_actor_id="op",
    )
    assert routed[0].signal_class == sc.INFORMATIONAL
    assert routed[0].primary_action == "none"


def test_signals_for_actor_filters_to_one_participant():
    routed = route_signals(
        [_gov_signal("g1"), _work_signal("alice")],
        authority_actor_id="operator",
    )
    assert {r.signal_id for r in signals_for_actor(routed, "operator")} == {"g1"}
    assert {r.signal_id for r in signals_for_actor(routed, "alice")} == {"hws_1"}


def test_age_seconds_is_computed():
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    signal = AttentionSignal("g1", "gate_pending", "h", "ref", created_at_utc=old)
    routed = route_signals([signal], authority_actor_id="op")
    assert routed[0].age_seconds >= 7000  # ~2h


def test_pending_gate_signals_reads_the_gate_directory(tmp_path):
    gates = tmp_path / "gates" / "pending"
    gates.mkdir(parents=True)
    (gates / "goal_alpha_review_1.json").write_text(
        json.dumps(
            {
                "type": "goal_gate_escalation",
                "goal_name": "Ship the report",
                "gate_description": "approve external publication",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "tenant_id": "tenant-a",
                "decision_class": "publication",
            }
        )
    )
    (gates / "broken.json").write_text("{not json")
    signals = pending_gate_signals(gates)
    assert len(signals) == 1  # the malformed file is skipped, not fatal
    assert signals[0].kind == "gate_pending"
    assert "Ship the report" in signals[0].headline
    assert signals[0].tenant_id == "tenant-a"
    assert signals[0].decision_class == "publication"


def test_pending_gate_signals_empty_when_no_directory(tmp_path):
    assert pending_gate_signals(tmp_path / "nope") == []


def test_resolve_authority_role(tmp_path):
    roles = tmp_path / "roles"
    roles.mkdir()
    (roles / "principal.yaml").write_text(
        "role_id: principal\nrole_class: authority\n"
    )
    (roles / "lead.yaml").write_text("role_id: lead\nrole_class: manager\n")
    assert resolve_authority_role(tmp_path) == "principal"


def test_resolve_authority_role_none_when_ambiguous(tmp_path):
    roles = tmp_path / "roles"
    roles.mkdir()
    (roles / "a.yaml").write_text("role_id: a\nrole_class: authority\n")
    (roles / "b.yaml").write_text("role_id: b\nrole_class: authority\n")
    assert resolve_authority_role(tmp_path) is None


def test_resolve_authority_role_uses_authority_domains(tmp_path):
    roles = tmp_path / "roles"
    roles.mkdir()
    (roles / "principal.yaml").write_text(
        "role_id: principal\nrole_class: authority\n"
    )
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

    assert resolve_authority_role(tmp_path, tenant_id="tenant-a") == "tenant_authority"
    assert resolve_authority_role(tmp_path, tenant_id="tenant-b") == "principal"


def test_authority_resolver_from_org_routes_scoped_signal_to_active_actor(tmp_path):
    roles = tmp_path / "roles"
    roles.mkdir()
    (roles / "principal.yaml").write_text("role_id: principal\nrole_class: authority\n")
    (roles / "tenant_authority.yaml").write_text("role_id: tenant_authority\nrole_class: authority\n")
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
    membership_log = tmp_path / "actor_memberships.jsonl"
    grant_actor_membership(
        actor_id="service.tenant_authority_bot",
        role_id="tenant_authority",
        granted_by="human.admin",
        decision_right_basis="tenant-scoped automation authority",
        tenant_id="tenant-a",
        log_path=membership_log,
    )
    signal = AttentionSignal(
        signal_id="g_tenant",
        kind="gate_pending",
        headline="Tenant gate",
        source_ref="gate",
        tenant_id="tenant-a",
    )

    routed = route_signals(
        [signal],
        authority_resolver=authority_resolver_from_org(
            tmp_path,
            actor_membership_log=membership_log,
        ),
    )

    assert routed[0].target_role_id == "tenant_authority"
    assert routed[0].target_actor_id == "service.tenant_authority_bot"


def test_authority_resolver_from_org_surfaces_role_without_active_actor(tmp_path):
    roles = tmp_path / "roles"
    roles.mkdir()
    (roles / "principal.yaml").write_text("role_id: principal\nrole_class: authority\n")
    signal = AttentionSignal(
        signal_id="g",
        kind="gate_pending",
        headline="Global gate",
        source_ref="gate",
    )

    routed = route_signals(
        [signal],
        authority_resolver=authority_resolver_from_org(tmp_path),
    )

    assert routed[0].target_role_id == "principal"
    assert routed[0].target_actor_id is None
