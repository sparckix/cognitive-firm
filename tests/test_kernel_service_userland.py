"""Tests for the userland kernel-service routes: L1 attention, L4 vocabulary."""

from __future__ import annotations

import json

from cognitive_firm.kernel_service import (
    KernelServiceConfig,
    dispatch_kernel_request,
)
from cognitive_firm.orchestration.actor_membership import grant_actor_membership
from cognitive_firm.orchestration.authority_domains import AuthorityDomain
from cognitive_firm.orchestration.command_surface import command_surface_match_records
from cognitive_firm.orchestration.human_work import (
    create_agent_requested_human_work_session,
    create_human_work_session,
)
from cognitive_firm.signals.damage import DamageSignal


def test_vocabulary_route_serves_the_glossary():
    resp = dispatch_kernel_request("GET", "/kernel/vocabulary")
    assert resp.status == 200
    assert resp.payload["schema_version"] == 1
    assert any(term["key"] == "gate" for term in resp.payload["terms"])


def test_command_surface_route_matches_known_repo_commands():
    resp = dispatch_kernel_request(
        "GET",
        "/kernel/command-surface?query=build%20an%20adoption%20readiness%20packet",
    )

    assert resp.status == 200
    assert resp.payload["read_only"] is True
    assert resp.payload["projection_only"] is True
    assert resp.payload["boundary"] == {
        "does_not_execute_commands": True,
        "does_not_schedule_work": True,
        "does_not_mutate_kernel_state": True,
    }
    commands = [match["command"] for match in resp.payload["matches"]]
    assert "make adoption-readiness-packet" in commands
    match = next(
        match
        for match in resp.payload["matches"]
        if match["command"] == "make adoption-readiness-packet"
    )
    effect = match["authority_effects"][0]
    assert effect["decision_class"] == "adoption_readiness"
    assert effect["resource_class"] == "adoption_evidence"
    assert effect["authority_resolution"]["status"] == "single_authority_fallback"
    assert match["authority_effect_validation"]["status"] == "ok"
    assert resp.payload["authority_effects_are_projection_only"] is True
    assert all(match["executes"] is False for match in resp.payload["matches"])
    assert "Known repo command surface" in resp.payload["hint"]


def test_command_surface_route_matches_adoption_onramp_packet():
    resp = dispatch_kernel_request(
        "GET",
        "/kernel/command-surface?query=adoption%20onramp%20packet",
    )

    assert resp.status == 200
    commands = [match["command"] for match in resp.payload["matches"]]
    assert "make adoption-onramp-packet" in commands
    match = next(
        match
        for match in resp.payload["matches"]
        if match["command"] == "make adoption-onramp-packet"
    )
    effect = match["authority_effects"][0]
    assert effect["effect_kind"] == "evidence_collection"
    assert effect["decision_class"] == "adoption_readiness"
    assert effect["resource_class"] == "adoption_evidence"
    assert match["executes"] is False


def test_command_surface_route_returns_first_review_operator_path():
    resp = dispatch_kernel_request(
        "GET",
        "/kernel/command-surface?query=first%20serious%20review",
    )

    assert resp.status == 200
    commands = [match["command"] for match in resp.payload["matches"]]
    assert commands[:3] == [
        "make smoke-public",
        "make adoption-onramp-packet",
        "make adoption-readiness-packet",
    ]
    guidance = [
        match["operator_guidance"] for match in resp.payload["matches"][:3]
    ]
    assert [row["path_id"] for row in guidance] == ["first_review"] * 3
    assert [row["step"] for row in guidance] == [1, 2, 3]
    assert all(row["total_steps"] == 3 for row in guidance)
    assert all(match["executes"] is False for match in resp.payload["matches"])


def test_operator_path_route_returns_first_review_path():
    resp = dispatch_kernel_request(
        "GET",
        "/kernel/operator-path?path_id=first_review",
    )

    assert resp.status == 200
    path = resp.payload["operator_path"]
    assert path["path_id"] == "first_review"
    assert path["purpose"] == (
        "Verify the public gate, collect deterministic adoption evidence, "
        "and render a reviewer handoff."
    )
    assert path["use_when"] == (
        "Use before a first human/adopter review of the repo or release "
        "candidate."
    )
    assert path["not_a"] == [
        "command runner",
        "scheduler",
        "adoption approval",
        "workflow engine",
    ]
    assert path["read_only"] is True
    assert path["projection_only"] is True
    assert path["boundary"] == {
        "does_not_execute_commands": True,
        "does_not_schedule_work": True,
        "does_not_mutate_kernel_state": True,
        "does_not_approve_adoption": True,
    }
    assert [step["command"] for step in path["steps"]] == [
        "make smoke-public",
        "make adoption-onramp-packet",
        "make adoption-readiness-packet",
    ]


def test_operator_path_route_rejects_unknown_path():
    resp = dispatch_kernel_request(
        "GET",
        "/kernel/operator-path?path_id=missing",
    )

    assert resp.status == 404
    assert "unknown operator path" in resp.payload["error"]


def test_command_surface_route_matches_adoption_onramp_full_replay():
    resp = dispatch_kernel_request(
        "GET",
        "/kernel/command-surface?query=adoption%20onramp%20full%20replay",
    )

    assert resp.status == 200
    commands = [match["command"] for match in resp.payload["matches"]]
    assert "make adoption-onramp-full-replay" in commands
    match = next(
        match
        for match in resp.payload["matches"]
        if match["command"] == "make adoption-onramp-full-replay"
    )
    effect = match["authority_effects"][0]
    assert effect["effect_kind"] == "evidence_replay"
    assert effect["decision_class"] == "adoption_readiness"
    assert effect["resource_class"] == "adoption_evidence"
    assert match["executes"] is False


def test_command_surface_route_matches_agent_fleet_review_packet():
    resp = dispatch_kernel_request(
        "GET",
        "/kernel/command-surface?query=agent%20fleet%20review%20packet",
    )

    assert resp.status == 200
    commands = [match["command"] for match in resp.payload["matches"]]
    assert "make agent-fleet-review-packet" in commands
    match = next(
        match
        for match in resp.payload["matches"]
        if match["command"] == "make agent-fleet-review-packet"
    )
    effect = match["authority_effects"][0]
    assert effect["effect_kind"] == "evidence_collection"
    assert effect["decision_class"] == "agent_fleet_audit"
    assert effect["resource_class"] == "agent_invocation_receipt"
    assert match["executes"] is False


def test_command_surface_route_matches_langgraph_adapter_policy_preview():
    resp = dispatch_kernel_request(
        "GET",
        "/kernel/command-surface?query=langgraph%20adapter%20policy%20preview",
    )

    assert resp.status == 200
    commands = [match["command"] for match in resp.payload["matches"]]
    assert "make langgraph-adapter-policy-preview" in commands
    match = next(
        match
        for match in resp.payload["matches"]
        if match["command"] == "make langgraph-adapter-policy-preview"
    )
    effect = match["authority_effects"][0]
    assert effect["effect_kind"] == "overlay_preview"
    assert effect["decision_class"] == "adapter_policy"
    assert effect["resource_class"] == "runtime_adapter_policy_package"
    assert effect["requires_explicit_scope"] is True
    assert match["executes"] is False


def test_command_surface_route_does_not_fallback_when_domains_fail_to_load(tmp_path):
    domains_dir = tmp_path / "authority_domains"
    domains_dir.mkdir()
    (domains_dir / "authority_domains.json").write_text(
        "{not-json",
        encoding="utf-8",
    )
    config = KernelServiceConfig(org_dir=tmp_path)

    resp = dispatch_kernel_request(
        "GET",
        "/kernel/command-surface?query=build%20an%20adoption%20readiness%20packet",
        config=config,
    )

    assert resp.status == 200
    assert resp.payload["authority_domain_issues"]
    match = next(
        match
        for match in resp.payload["matches"]
        if match["command"] == "make adoption-readiness-packet"
    )
    effect = match["authority_effects"][0]
    assert effect["authority_resolution"]["status"] == "not_evaluated"
    assert match["authority_effect_validation"] == {
        "status": "not_evaluated",
        "checked": False,
        "issues": [],
    }


def test_command_surface_does_not_match_substrings_inside_ordinary_prose():
    records = command_surface_match_records(
        "latest release status",
        authority_domains=[],
    )

    commands = {record["command"] for record in records}
    assert "make test" not in commands
    assert "python src/cognitive_firm/orchestration/leases.py" not in commands


def test_command_surface_records_resolve_effects_against_authority_domains():
    domains = [
        AuthorityDomain(
            "adoption_review",
            "principal",
            "decision_class",
            "adoption_readiness",
        )
    ]

    records = command_surface_match_records(
        "build an adoption readiness packet",
        authority_domains=domains,
    )

    match = next(
        record
        for record in records
        if record["command"] == "make adoption-readiness-packet"
    )
    effect = match["authority_effects"][0]
    assert effect["authority_resolution"] == {
        "status": "resolved",
        "domain_id": "adoption_review",
        "authority_role_id": "principal",
        "scope_kind": "decision_class",
        "scope_id": "adoption_readiness",
    }
    assert match["authority_effect_validation"]["status"] == "ok"


def test_command_surface_records_source_role_escalation_mismatch():
    domains = [
        AuthorityDomain("global", "principal", "global", "*"),
        AuthorityDomain(
            "policy_change",
            "policy_authority",
            "decision_class",
            "policy_change",
        ),
    ]
    roles = {
        "principal": {"role_id": "principal", "role_class": "authority"},
        "policy_authority": {
            "role_id": "policy_authority",
            "role_class": "authority",
        },
        "worker": {
            "role_id": "worker",
            "role_class": "specialist",
            "escalates_to": ["role.principal"],
        },
    }

    records = command_surface_match_records(
        "run the field pilot action impact demo",
        authority_domains=domains,
        roles=roles,
        source_role_id="worker",
    )

    match = next(
        record
        for record in records
        if record["command"] == "make field-pilot-action-impact-demo"
    )
    effect = match["authority_effects"][0]
    assert effect["authority_resolution"]["authority_role_id"] == "policy_authority"
    assert effect["source_role_escalation"]["status"] == "blocked"
    assert effect["source_role_escalation"]["target_authority_role_id"] == (
        "policy_authority"
    )
    assert "does not reach scoped authority role policy_authority" in (
        match["authority_effect_validation"]["issues"][0]
    )
    assert match["authority_effect_validation"]["status"] == "blocked"


def test_command_surface_flags_sensitive_effect_global_fallback():
    domains = [AuthorityDomain("global", "principal", "global", "*")]

    records = command_surface_match_records(
        "run the field pilot action impact demo",
        authority_domains=domains,
    )

    match = next(
        record
        for record in records
        if record["command"] == "make field-pilot-action-impact-demo"
    )
    effect = match["authority_effects"][0]
    assert effect["authority_resolution"]["status"] == "global_fallback"
    assert match["authority_effect_validation"]["status"] == "blocked"
    assert "requires an explicit authority domain" in match[
        "authority_effect_validation"
    ]["issues"][0]


def test_command_surface_route_traces_source_role_to_typed_authority(tmp_path):
    roles = tmp_path / "roles"
    roles.mkdir()
    (roles / "principal.yaml").write_text(
        "role_id: principal\nrole_class: authority\nescalates_to: []\n"
    )
    (roles / "policy_authority.yaml").write_text(
        "role_id: policy_authority\nrole_class: authority\nescalates_to: []\n"
    )
    (roles / "worker.yaml").write_text(
        "role_id: worker\nrole_class: specialist\n"
        "escalates_to:\n  - role.policy_authority\n"
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
                        "domain_id": "policy_change",
                        "authority_role_id": "role.policy_authority",
                        "scope_kind": "decision_class",
                        "scope_id": "policy_change",
                    },
                ]
            }
        )
    )
    config = KernelServiceConfig(org_dir=tmp_path)

    resp = dispatch_kernel_request(
        "GET",
        (
            "/kernel/command-surface?"
            "query=run%20the%20field%20pilot%20action%20impact%20demo"
            "&role_id=worker"
        ),
        config=config,
    )

    assert resp.status == 200
    assert resp.payload["source_role_id"] == "worker"
    match = next(
        match
        for match in resp.payload["matches"]
        if match["command"] == "make field-pilot-action-impact-demo"
    )
    effect = match["authority_effects"][0]
    assert effect["authority_resolution"]["authority_role_id"] == "policy_authority"
    assert effect["source_role_escalation"]["status"] == "ok"
    assert effect["source_role_escalation"]["escalation_path"] == [
        "worker",
        "policy_authority",
    ]
    assert match["authority_effect_validation"]["status"] == "ok"


def test_command_surface_route_requires_a_query():
    resp = dispatch_kernel_request("GET", "/kernel/command-surface")

    assert resp.status == 400
    assert "query is required" in resp.payload["error"]


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


def test_learning_candidates_can_compile_attention_pressure(tmp_path):
    gates = tmp_path / "gates"
    gates.mkdir()
    (gates / "review_policy.json").write_text(
        json.dumps(
            {
                "goal_name": "Review policy",
                "gate_description": "approve policy update",
                "decision_class": "policy_change",
            }
        ),
        encoding="utf-8",
    )
    config = KernelServiceConfig(
        gates_dir=gates,
        org_dir=tmp_path,
        actor_membership_log=tmp_path / "m.jsonl",
    )

    resp = dispatch_kernel_request(
        "GET",
        "/kernel/learning-transition-candidates?source=attention",
        config=config,
    )

    assert resp.status == 200
    assert resp.payload["source"] == "attention"
    assert resp.payload["source_counts"]["attention"] == 1
    candidate = resp.payload["candidates"][0]
    assert candidate["observer_only"] is True
    assert candidate["source_kind"] == "attention_unrouted_signal"
    assert candidate["transition_kind"] == "route_policy_change"
    assert candidate["proposed_payload"]["target_actor_id"] is None
    assert "does not reroute" in candidate["proposed_payload"]["boundary"]


def test_learning_candidates_org_surface_includes_damage_pattern(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "cognitive_firm.signals.damage.list_recent",
        lambda limit=50: [
            DamageSignal(
                timestamp_utc="2026-06-18T00:00:00+00:00",
                source="quality_monitor",
                kind="output_regression",
                detail="Regression detected.",
                session_id="run_1",
                severity="warn",
            ),
            DamageSignal(
                timestamp_utc="2026-06-18T00:05:00+00:00",
                source="quality_monitor",
                kind="output_regression",
                detail="Regression detected again.",
                session_id="run_2",
                severity="warn",
            ),
        ],
    )
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        evidence_gaps_log=tmp_path / "evidence_gaps.jsonl",
        forecast_market_summary=tmp_path / "forecast.json",
        action_impact_summary=tmp_path / "action_impact.json",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
        action_attestation_log=tmp_path / "action_attestations.jsonl",
        transition_log=tmp_path / "transitions.jsonl",
        org_dir=tmp_path / "org",
        gates_dir=tmp_path / "gates",
    )

    resp = dispatch_kernel_request(
        "GET",
        "/kernel/learning-transition-candidates?source=org_surface",
        config=config,
    )

    assert resp.status == 200
    damage_candidates = [
        candidate
        for candidate in resp.payload["candidates"]
        if candidate["source_kind"] == "damage_pattern"
    ]
    assert len(damage_candidates) == 1
    candidate = damage_candidates[0]
    assert candidate["observer_only"] is True
    assert candidate["object_ref"] == "damage_pattern:output_regression"
    assert candidate["proposed_payload"]["signal_count"] == 2
    assert "does not quarantine" in candidate["proposed_payload"]["boundary"]


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


def test_human_work_pressure_route_is_observer_only(tmp_path):
    human_work = tmp_path / "hw.jsonl"
    for index in range(3):
        create_agent_requested_human_work_session(
            requested_by_role="role.researcher",
            human_actor=f"human.{index}",
            objective=f"Check restricted source {index}.",
            work_mode="source_check",
            bottleneck_class="access",
            human_deliverable="bounded source receipt",
            tenant_id="tenant-a",
            project_id="project-a",
            session_id=f"hws_tenant_a_{index}",
            log_path=human_work,
        )
    create_agent_requested_human_work_session(
        requested_by_role="role.researcher",
        human_actor="human.other-0",
        objective="Check other tenant source.",
        work_mode="source_check",
        bottleneck_class="access",
        human_deliverable="bounded source receipt",
        tenant_id="tenant-b",
        project_id="project-b",
        session_id="hws_tenant_b_0",
        log_path=human_work,
    )
    create_agent_requested_human_work_session(
        requested_by_role="role.researcher",
        human_actor="human.other-1",
        objective="Check other tenant source again.",
        work_mode="source_check",
        bottleneck_class="access",
        human_deliverable="bounded source receipt",
        tenant_id="tenant-b",
        project_id="project-b",
        session_id="hws_tenant_b_1",
        log_path=human_work,
    )
    create_agent_requested_human_work_session(
        requested_by_role="role.researcher",
        human_actor="human.other-2",
        objective="Check other tenant source a third time.",
        work_mode="source_check",
        bottleneck_class="access",
        human_deliverable="bounded source receipt",
        tenant_id="tenant-b",
        project_id="project-b",
        session_id="hws_tenant_b_2",
        log_path=human_work,
    )
    config = KernelServiceConfig(human_work_log=human_work)

    resp = dispatch_kernel_request(
        "GET",
        "/kernel/human-work-pressure?agent_counterparty_role=role.researcher&tenant_id=tenant-a",
        config=config,
    )

    assert resp.status == 200
    assert resp.payload["read_only"] is True
    assert resp.payload["observer_only"] is True
    assert len(resp.payload["pressure"]) == 1
    group = resp.payload["pressure"][0]
    assert group["agent_counterparty_role"] == "role.researcher"
    assert group["bottleneck_class"] == "access"
    assert group["active_count"] == 3
    assert group["missing_receipt_count"] == 3
    assert "source connector" in group["recommendation"]
    assert any("not automation" in caveat for caveat in resp.payload["caveats"])
    assert resp.payload["query"]["tenant_id"] == "tenant-a"

    candidates = dispatch_kernel_request(
        "GET",
        "/kernel/learning-transition-candidates?source=human_work",
        config=config,
    )

    assert candidates.status == 200
    assert candidates.payload["source"] == "human_work"
    assert candidates.payload["n_candidates"] == 1
    human_refs = {
        candidate["object_ref"]
        for candidate in candidates.payload["candidates"]
        if candidate["source_kind"] == "a2h_pressure"
    }
    assert "a2h_pressure:role.researcher:access" in human_refs
    assert candidates.payload["source_counts"]["org_surface"] == 0
    assert candidates.payload["source_counts"]["human_work"] == 1
    assert set(group["session_ids"]) == {
        "hws_tenant_a_0",
        "hws_tenant_a_1",
        "hws_tenant_a_2",
    }


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
