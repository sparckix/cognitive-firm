from __future__ import annotations

import http.client
import json
import sys
import threading
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.kernel_service import (  # noqa: E402
    KernelServiceConfig,
    dispatch_kernel_request,
    make_kernel_server,
)
from cognitive_firm.orchestration.action_impact import context_signature  # noqa: E402
from cognitive_firm.orchestration.action_attestation import (  # noqa: E402
    create_action_attestation,
    digest_text,
)
from cognitive_firm.identity_providers import (  # noqa: E402
    AuthenticatedSubject,
    StaticBearerTokenIdentityProvider,
)
from cognitive_firm.distribution.signing import generate_keypair  # noqa: E402
from cognitive_firm.orchestration.formal_verification import (  # noqa: E402
    FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
    configure_trusted_provider,
    sign_provider_payload,
)
from cognitive_firm.orchestration.learning_events import (  # noqa: E402
    create_learning_event,
    record_learning_event_encounter,
)
from cognitive_firm.orchestration.governance_changes import REQUIRED_INVARIANTS  # noqa: E402
from cognitive_firm.orchestration.capability_signals import record_capability_signal  # noqa: E402
from cognitive_firm.orchestration.multi_agent_trace_attribution import (  # noqa: E402
    create_failure_attribution_packet,
    record_trace_event,
)
from cognitive_firm.orchestration.outcome_links import (  # noqa: E402
    create_outcome_link,
    record_metric_snapshot,
    record_verdict,
)
from cognitive_firm.orchestration.phase_execution import start_phase_execution_plan  # noqa: E402
from cognitive_firm.orchestration.protocol_experiments import (  # noqa: E402
    build_protocol_experiment_report,
    record_protocol_observation,
    start_protocol_experiment,
)
from cognitive_firm.orchestration.routine_reviews import schedule_routine_review  # noqa: E402
from cognitive_firm.orchestration.state_backends import SqliteMutationBackend  # noqa: E402


def _passing_governance_checks() -> list[dict[str, object]]:
    return [
        {
            "invariant": invariant,
            "status": "pass",
            "rationale": f"{invariant} preserved by deterministic guard.",
            "evidence_refs": [f"test:{invariant}"],
        }
        for invariant in sorted(REQUIRED_INVARIANTS)
    ]


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


def test_kernel_service_a2a_messages_use_configured_org_dir(tmp_path: Path) -> None:
    org_dir = tmp_path / "demo-firm" / "org"
    roles_dir = org_dir / "roles"
    roles_dir.mkdir(parents=True)
    (roles_dir / "org_evolver.yaml").write_text(
        """
role_id: role.org_evolver
delegates_to:
  - role.evaluator
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (roles_dir / "evaluator.yaml").write_text(
        """
role_id: role.evaluator
escalates_to:
  - role.principal
""".strip()
        + "\n",
        encoding="utf-8",
    )
    config = KernelServiceConfig(
        org_dir=org_dir,
        transition_log=tmp_path / "transitions.jsonl",
    )

    sent = dispatch_kernel_request(
        "POST",
        "/kernel/a2a/messages",
        {
            "from_role": "org_evolver",
            "to_role": "evaluator",
            "kind": "request",
            "subject": "Review proposed route policy change",
            "body": "Check evidence before governance proposal promotion.",
            "references": ["work:work_demo"],
            "artifacts": ["proposal:gcp_demo"],
        },
        config=config,
    )

    assert sent.status == 201
    message = sent.payload["message"]
    assert message["obligation_state"] == "pending"
    inbox_file = org_dir / "channels" / "evaluator" / "inbox" / f"{message['message_id']}.json"
    sent_file = org_dir / "channels" / "org_evolver" / "sent" / f"{message['message_id']}.json"
    assert inbox_file.exists()
    assert sent_file.exists()
    transitions = config.transition_log.read_text(encoding="utf-8")
    assert "agent.message.sent" in transitions
    assert message["message_id"] in transitions


def test_kernel_service_updates_a2a_obligation_lifecycle(tmp_path: Path) -> None:
    org_dir = tmp_path / "demo-firm" / "org"
    roles_dir = org_dir / "roles"
    roles_dir.mkdir(parents=True)
    (roles_dir / "org_evolver.yaml").write_text(
        """
role_id: role.org_evolver
delegates_to:
  - role.evaluator
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (roles_dir / "evaluator.yaml").write_text(
        "role_id: role.evaluator\n",
        encoding="utf-8",
    )
    config = KernelServiceConfig(
        org_dir=org_dir,
        transition_log=tmp_path / "transitions.jsonl",
    )
    sent = dispatch_kernel_request(
        "POST",
        "/kernel/a2a/messages",
        {
            "from_role": "org_evolver",
            "to_role": "evaluator",
            "kind": "request",
            "subject": "Review proposed route policy change",
            "body": "Check evidence before governance proposal promotion.",
        },
        config=config,
    )
    message_id = sent.payload["message"]["message_id"]

    acknowledged = dispatch_kernel_request(
        "POST",
        f"/kernel/a2a/messages/{message_id}/status",
        {
            "role_id": "evaluator",
            "status": "acknowledged",
            "actor": "agent.evaluator",
            "note": "review request opened",
        },
        config=config,
    )
    assert acknowledged.status == 200
    assert acknowledged.payload["message"]["status"] == "acknowledged"

    for state in ("accepted", "in_progress", "fulfilled"):
        updated = dispatch_kernel_request(
            "POST",
            f"/kernel/a2a/messages/{message_id}/obligation",
            {
                "role_id": "evaluator",
                "state": state,
                "actor": "agent.evaluator",
                "note": f"review obligation {state}",
            },
            config=config,
        )
        assert updated.status == 200
        assert updated.payload["message"]["obligation_state"] == state

    illegal = dispatch_kernel_request(
        "POST",
        f"/kernel/a2a/messages/{message_id}/obligation",
        {
            "role_id": "evaluator",
            "state": "accepted",
            "actor": "agent.evaluator",
        },
        config=config,
    )
    assert illegal.status == 400
    assert "terminal" in illegal.payload["error"]
    transitions = config.transition_log.read_text(encoding="utf-8")
    assert "agent.message.acknowledged" in transitions
    assert "agent.obligation.accepted" in transitions
    assert "agent.obligation.in_progress" in transitions
    assert "agent.obligation.fulfilled" in transitions
    inbox_file = org_dir / "channels" / "evaluator" / "inbox" / f"{message_id}.json"
    payload = json.loads(inbox_file.read_text(encoding="utf-8"))
    assert payload["obligation_state"] == "fulfilled"


def test_kernel_service_records_decision_aggregation_case(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        decision_aggregation_log=tmp_path / "decision_aggregation_cases.jsonl"
    )

    opened = dispatch_kernel_request(
        "POST",
        "/kernel/decision-aggregation-cases",
        {
            "subject_ref": "governance_change:gcp_123",
            "decision_class": "structural_change",
            "scope_kind": "project",
            "scope_ref": "proj.demo",
            "procedure_kind": "quorum_majority",
            "opened_by": "role.principal",
            "eligibility_basis": "project review policy",
            "eligible_roles": ["role.principal", "role.evaluator"],
            "quorum": 2,
            "evidence_refs": ["a2a_message:msg_123"],
            "case_id": "dac_demo_structural_review",
        },
        config=config,
    )
    assert opened.status == 201
    case_id = opened.payload["decision_aggregation_case"]["case_id"]
    assert case_id == "dac_demo_structural_review"

    for actor_id, role_id in (
        ("human.principal", "role.principal"),
        ("agent.evaluator", "role.evaluator"),
    ):
        position = dispatch_kernel_request(
            "POST",
            f"/kernel/decision-aggregation-cases/{case_id}/positions",
            {
                "actor_id": actor_id,
                "role_id": role_id,
                "position": "approve",
                "rationale": f"{role_id} approves",
                "position_id": f"dpos_{role_id.rsplit('.', 1)[-1]}",
            },
            config=config,
        )
        assert position.status == 200

    computed = dispatch_kernel_request(
        "POST",
        f"/kernel/decision-aggregation-cases/{case_id}/compute",
        {},
        config=config,
    )
    assert computed.status == 200
    result = computed.payload["decision_aggregation_case"]["result"]
    assert result["recommendation"] == "approve"
    assert result["quorum_met"] is True
    assert {
        position["position_id"]
        for position in computed.payload["decision_aggregation_case"]["positions"]
    } == {"dpos_principal", "dpos_evaluator"}

    listed = dispatch_kernel_request(
        "GET",
        "/kernel/decision-aggregation-cases?procedure_kind=quorum_majority",
        config=config,
    )
    assert listed.status == 200
    assert listed.payload["decision_aggregation_cases"][0]["case_id"] == case_id
    resources = dispatch_kernel_request(
        "GET",
        "/kernel/decision-aggregation-cases?resource=true",
        config=config,
    )
    assert resources.status == 200
    assert resources.payload["decision_aggregation_cases"][0]["kind"] == "DecisionAggregationCase"


def test_kernel_service_lists_decision_procedure_profiles() -> None:
    response = dispatch_kernel_request("GET", "/kernel/decision-procedure-profiles")

    assert response.status == 200
    profiles = response.payload["decision_procedure_profiles"]
    profile_ids = {profile["profile_id"] for profile in profiles}
    assert {"single_authority", "majority", "quorum_majority", "unanimity", "veto_review"} <= profile_ids
    unanimity = next(profile for profile in profiles if profile["profile_id"] == "unanimity")
    assert unanimity["procedure_kind"] == "unanimity"
    assert unanimity["quorum_rule"] == "all_eligible"
    assert unanimity["binding_semantics"] == "evidence_only"


def test_kernel_service_opens_decision_aggregation_case_from_profile(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        decision_aggregation_log=tmp_path / "decision_aggregation_cases.jsonl"
    )

    opened = dispatch_kernel_request(
        "POST",
        "/kernel/decision-aggregation-cases",
        {
            "subject_ref": "governance_change:gcp_789",
            "decision_class": "charter_amendment",
            "scope_kind": "project",
            "scope_ref": "proj.demo",
            "procedure_profile": "unanimity",
            "opened_by": "role.principal",
            "eligibility_basis": "tier-1 amendment rule",
            "eligible_actors": ["human.principal", "agent.evaluator", "agent.risk"],
        },
        config=config,
    )

    assert opened.status == 201
    case = opened.payload["decision_aggregation_case"]
    assert case["procedure_kind"] == "unanimity"
    assert case["quorum"] == 3
    assert case["metadata"]["procedure_profile"] == "unanimity"


def test_kernel_service_routes_escalated_decision_aggregation_case(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        decision_aggregation_log=tmp_path / "decision_aggregation_cases.jsonl",
        capability_signals_log=tmp_path / "capability_signals.jsonl",
        leases_log=tmp_path / "leases.jsonl",
    )
    opened = dispatch_kernel_request(
        "POST",
        "/kernel/decision-aggregation-cases",
        {
            "subject_ref": "governance_change:gcp_packet_record",
            "decision_class": "structural_change",
            "scope_kind": "project",
            "scope_ref": "proj.demo",
            "procedure_kind": "quorum_majority",
            "opened_by": "role.principal",
            "eligibility_basis": "demo quorum review",
            "eligible_roles": [
                "role.principal",
                "role.evaluator",
                "role.risk_guardian",
                "role.learning_steward",
            ],
            "quorum": 4,
            "evidence_refs": ["phase_execution_plan:pex_packet_record"],
            "case_id": "dac_packet_record_review",
        },
        config=config,
    )
    assert opened.status == 201
    case_id = opened.payload["decision_aggregation_case"]["case_id"]
    positions = [
        ("agent.principal", "role.principal", "approve"),
        ("agent.evaluator", "role.evaluator", "approve"),
        ("agent.risk_guardian", "role.risk_guardian", "abstain"),
        ("agent.learning_steward", "role.learning_steward", "approve"),
    ]
    for actor_id, role_id, position in positions:
        response = dispatch_kernel_request(
            "POST",
            f"/kernel/decision-aggregation-cases/{case_id}/positions",
            {
                "actor_id": actor_id,
                "role_id": role_id,
                "position": position,
                "rationale": f"{role_id} records {position}",
                "evidence_refs": [f"a2a_message:{role_id.rsplit('.', 1)[-1]}"],
            },
            config=config,
        )
        assert response.status == 200

    computed = dispatch_kernel_request(
        "POST",
        f"/kernel/decision-aggregation-cases/{case_id}/compute",
        {},
        config=config,
    )
    assert computed.status == 200
    assert computed.payload["decision_aggregation_case"]["status"] == "escalated"
    assert computed.payload["decision_aggregation_case"]["result"]["quorum_met"] is False

    routed = dispatch_kernel_request(
        "POST",
        f"/kernel/decision-aggregation-cases/{case_id}/route-escalation",
        {
            "signal_id": "csig_quorum_gap",
            "summary": "Reviewer quorum failed because one eligible reviewer abstained.",
            "route_kind": "open_learning_candidate",
            "routed_by": "role.evaluator",
            "evidence_refs": ["file://reports/reviewers/risk_guardian/review.json"],
        },
        config=config,
    )

    assert routed.status == 201
    assert routed.payload["decision_aggregation_case"]["case_id"] == case_id
    signal = routed.payload["signal"]
    assert signal["signal_id"] == "csig_quorum_gap"
    assert signal["signal_kind"] == "evidence_gap"
    assert signal["severity"] == "blocking"
    assert signal["status"] == "routed"
    assert signal["counts_as_failure"] is True
    assert signal["source_ref"] == f"decision_aggregation_case:{case_id}"
    assert "governance_change:gcp_packet_record" in signal["evidence_refs"]
    assert "file://reports/reviewers/risk_guardian/review.json" in signal["evidence_refs"]
    assert signal["metadata"]["source_route"] == "decision_aggregation_escalation.v1"
    assert signal["metadata"]["quorum_met"] is False
    assert routed.payload["learning_candidate"]["transition_kind"] == "evidence_gap"
    assert routed.payload["learning_candidate"]["source_kind"] == "capability_signal"
    assert routed.payload["learning_candidate"]["observer_only"] is True
    assert routed.payload["resolved_refs"]["signal_ref"] == "capability_signal:csig_quorum_gap"
    assert routed.payload["boundary"]["approved_governance"] is False
    assert routed.payload["boundary"]["mutated_files"] is False
    assert routed.payload["boundary"]["resolved_decision"] is False
    assert routed.payload["boundary"]["overrode_aggregation"] is False


def test_kernel_service_routes_escalated_decision_with_single_outer_lease(tmp_path: Path) -> None:
    base_config = KernelServiceConfig(
        decision_aggregation_log=tmp_path / "decision_aggregation_cases.jsonl",
        capability_signals_log=tmp_path / "capability_signals.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        require_leases=False,
    )
    opened = dispatch_kernel_request(
        "POST",
        "/kernel/decision-aggregation-cases",
        {
            "subject_ref": "governance_change:gcp_lease_guard",
            "decision_class": "structural_change",
            "scope_kind": "project",
            "scope_ref": "proj.demo",
            "procedure_kind": "quorum_majority",
            "opened_by": "role.principal",
            "eligibility_basis": "lease regression review",
            "eligible_roles": ["role.principal", "role.evaluator"],
            "quorum": 2,
            "case_id": "dac_lease_guard",
        },
        config=base_config,
    )
    assert opened.status == 201
    position = dispatch_kernel_request(
        "POST",
        "/kernel/decision-aggregation-cases/dac_lease_guard/positions",
        {
            "actor_id": "human.principal",
            "role_id": "role.principal",
            "position": "approve",
            "rationale": "Only one eligible position arrived.",
        },
        config=base_config,
    )
    assert position.status == 200
    computed = dispatch_kernel_request(
        "POST",
        "/kernel/decision-aggregation-cases/dac_lease_guard/compute",
        {},
        config=base_config,
    )
    assert computed.status == 200
    assert computed.payload["decision_aggregation_case"]["status"] == "escalated"

    leased_config = replace(base_config, require_leases=True)
    actor_context = {
        "actor_id": "agent.evaluator",
        "actor_kind": "agent",
        "role_id": "role.evaluator",
    }
    lease = dispatch_kernel_request(
        "POST",
        "/kernel/leases",
        {
            "resource_ref": "decision_aggregation_case:dac_lease_guard:route_escalation",
            "ttl_seconds": 60,
            "actor_context": actor_context,
        },
        config=leased_config,
    )
    assert lease.status == 201
    lease_record = lease.payload["lease"]

    routed = dispatch_kernel_request(
        "POST",
        "/kernel/decision-aggregation-cases/dac_lease_guard/route-escalation",
        {
            "signal_id": "csig_lease_guard",
            "summary": "Route escalation should require only the outer decision-case lease.",
            "lease_id": lease_record["lease_id"],
            "fencing_token": lease_record["fencing_token"],
            "actor_context": actor_context,
        },
        config=leased_config,
    )

    assert routed.status == 201
    assert routed.payload["signal"]["signal_id"] == "csig_lease_guard"
    assert routed.payload["boundary"]["resolved_decision"] is False


def test_kernel_service_a2a_thread_guard_blocks_unbounded_message_loop(tmp_path: Path) -> None:
    org_dir = tmp_path / "demo-firm" / "org"
    roles_dir = org_dir / "roles"
    roles_dir.mkdir(parents=True)
    (roles_dir / "org_evolver.yaml").write_text(
        """
role_id: role.org_evolver
delegates_to:
  - role.evaluator
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (roles_dir / "evaluator.yaml").write_text(
        "role_id: role.evaluator\n",
        encoding="utf-8",
    )
    config = KernelServiceConfig(
        org_dir=org_dir,
        transition_log=tmp_path / "transitions.jsonl",
        a2a_max_thread_messages=2,
    )
    for idx in range(2):
        sent = dispatch_kernel_request(
            "POST",
            "/kernel/a2a/messages",
            {
                "from_role": "org_evolver",
                "to_role": "evaluator",
                "kind": "request",
                "subject": f"Review loop check {idx}",
                "body": "Bounded review request.",
                "thread_id": "thread_loop_guard",
            },
            config=config,
        )
        assert sent.status == 201

    blocked = dispatch_kernel_request(
        "POST",
        "/kernel/a2a/messages",
        {
            "from_role": "org_evolver",
            "to_role": "evaluator",
            "kind": "request",
            "subject": "Review loop check 3",
            "body": "This should exceed the thread limit.",
            "thread_id": "thread_loop_guard",
        },
        config=config,
    )

    assert blocked.status == 400
    assert "limit is 2" in blocked.payload["error"]
    inbox_files = list((org_dir / "channels" / "evaluator" / "inbox").glob("*.json"))
    assert len(inbox_files) == 2


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


def test_kernel_service_updates_accountability_case_status(tmp_path: Path):
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
            "trigger_ref": "run:run_service_case",
            "accountable_role": "role.manager",
            "responsible_actor": "role.manager",
            "decision_right_basis": "mandate",
            "authority_envelope_ref": "org/roles/manager.yaml",
            "risk_tier": "medium",
            "recourse_path": "reopen",
        },
        config=config,
    )
    assert created.status == 201
    case_id = created.payload["case"]["case_id"]

    blocked = dispatch_kernel_request(
        "POST",
        f"/kernel/accountability-cases/{case_id}/status",
        {"status": "closed"},
        config=config,
    )
    assert blocked.status == 400
    assert "closure evidence" in blocked.payload["error"]

    closed = dispatch_kernel_request(
        "POST",
        f"/kernel/accountability-cases/{case_id}/status",
        {
            "status": "closed",
            "closure_evidence_refs": ["run:run_service_case"],
        },
        config=config,
    )
    assert closed.status == 200
    assert closed.payload["case"]["status"] == "closed"
    assert closed.payload["case"]["closure_evidence_refs"] == ["run:run_service_case"]


def test_kernel_service_creates_accountability_case_from_damage_signal(tmp_path: Path):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
    )

    created = dispatch_kernel_request(
        "POST",
        "/kernel/accountability-cases/from-damage-signal",
        {
            "case_id": "acct_damage_signal_1",
            "signal": {
                "timestamp_utc": "2026-06-12T21:00:00+00:00",
                "source": "agent_daemon",
                "kind": "agent_returned_no_progress",
                "detail": "Role session exited without closing the task.",
                "session_id": "sess_1",
                "severity": "warn",
            },
            "accountable_role": "role.manager",
            "authority_envelope_ref": "org/mandates/manager_mandate.md",
            "decision_right_basis": "mandate",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "metadata": {"run_id": "run_1"},
        },
        config=config,
    )

    assert created.status == 201
    case = created.payload["case"]
    assert case["case_id"] == "acct_damage_signal_1"
    assert case["trigger_ref"].startswith(
        "damage_signal:agent_returned_no_progress:"
    )
    assert case["responsible_actor"] == "agent_daemon"
    assert case["risk_tier"] == "medium"
    assert case["recourse_path"] == "reopen"
    assert case["externality_tags"] == ["damage:agent_returned_no_progress"]
    assert case["metadata"]["source_recipe"] == (
        "damage_signal_accountability_case_request.v1"
    )
    assert case["metadata"]["run_id"] == "run_1"

    summary = dispatch_kernel_request("GET", "/kernel/accountability-summary", config=config)
    items = summary.payload["summary"]["items"]
    assert any(
        item["source_kind"] == "accountability_case"
        and item["object_ref"] == "acct_damage_signal_1"
        for item in items
    )


def test_kernel_service_org_surface_uses_configured_learning_logs(tmp_path: Path):
    config = KernelServiceConfig(
        project_root=tmp_path,
        human_work_log=tmp_path / "human_work.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        evidence_gaps_log=tmp_path / "evidence_gaps.jsonl",
        forecast_market_summary=tmp_path / "forecast_summary.json",
        action_impact_summary=tmp_path / "action_impact_summary.json",
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
        transition_log=tmp_path / "transitions.jsonl",
    )
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Prefer a lower-friction review path for recurring quality checks.",
        future_application_cue="When a recurring quality check repeats with the same inputs.",
        approved_by="role.owner",
        approval_ref="decision:test-learning",
        source_carrier_refs=["work:test-1"],
        log_path=config.learning_events_log,
    )
    record_learning_event_encounter(
        learning_event_id=event.learning_event_id,
        role="role.operator",
        cue="Recurring quality check repeated.",
        outcome="applied",
        work_ref="work:test-2",
        log_path=config.learning_encounters_log,
    )
    link = create_outcome_link(
        change_ref=f"learning_event:{event.learning_event_id}",
        change_kind="learning_event",
        metric_name="review_cycles",
        metric_unit="count",
        created_by="role.owner",
        learning_event_id=event.learning_event_id,
        log_path=config.outcome_links_log,
    )
    record_metric_snapshot(
        link.outcome_link_id,
        kind="baseline",
        value=3,
        captured_by="role.owner",
        log_path=config.outcome_links_log,
    )
    record_metric_snapshot(
        link.outcome_link_id,
        kind="post",
        value=2,
        captured_by="role.owner",
        log_path=config.outcome_links_log,
    )
    record_verdict(
        link.outcome_link_id,
        verdict="improved",
        recorded_by="role.owner",
        rationale="Fewer review cycles on the same class of work.",
        log_path=config.outcome_links_log,
    )
    schedule_routine_review(
        routine_ref=f"learning_event:{event.learning_event_id}",
        routine_kind="learning_event",
        review_due_utc="2000-01-01T00:00:00+00:00",
        scheduled_by="role.owner",
        learning_event_id=event.learning_event_id,
        log_path=config.routine_reviews_log,
    )

    surface = dispatch_kernel_request("GET", "/kernel/org-surface", config=config)

    assert surface.status == 200
    counts = surface.payload["surface"]["counts"]
    summary = surface.payload["surface"]["learning_event_summary"]
    assert counts["active_learning_events"] == 1
    assert counts["learning_events_with_encounters"] == 1
    assert counts["learning_event_outcome_links"] == 1
    assert counts["learning_event_overdue_reviews"] == 1
    assert summary["outcome_verdict_coverage"] == 1.0


def test_kernel_service_routes_governance_change_lifecycle(tmp_path: Path):
    config = KernelServiceConfig(
        org_dir=tmp_path / "org",
        transition_log=tmp_path / "transitions.jsonl",
    )

    created = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes",
        {
            "change_kind": "mandate_change",
            "title": "Clarify evaluator escalation authority",
            "target_ref": "org/mandates/evaluator.md",
            "rationale": "Recent review work found ambiguous escalation language.",
            "source_refs": ["work:review-42"],
            "expected_behavior_change": (
                "Evaluator escalates unclear authority cases before execution."
            ),
            "risk_summary": "Narrows execution authority; no new capability grant.",
            "rollback_plan": "Restore the previous mandate file from git.",
            "owner_role": "role.principal",
            "tenant_id": "tenant-a",
            "project_id": "project-alpha",
            "invariant_checks": _passing_governance_checks(),
            "metadata": {"review_queue": "governance"},
            "actor_context": {
                "actor_id": "agent.org_evolver",
                "actor_kind": "agent",
                "role_id": "role.org_evolver",
                "tenant_id": "tenant-a",
                "project_id": "project-alpha",
            },
        },
        config=config,
    )
    assert created.status == 201
    proposal = created.payload["proposal"]
    proposal_id = proposal["proposal_id"]
    assert proposal["status"] == "review_ready"
    assert proposal["proposed_by"] == "agent.org_evolver"

    filtered = dispatch_kernel_request(
        "GET",
        (
            "/kernel/governance-changes"
            "?status=review_ready&change_kind=mandate_change"
            "&tenant_id=tenant-a&project_id=project-alpha"
        ),
        config=config,
    )
    assert filtered.status == 200
    assert [row["proposal_id"] for row in filtered.payload["proposals"]] == [
        proposal_id
    ]
    assert filtered.payload["proposals"][0]["decided"] is False

    listed_resources = dispatch_kernel_request(
        "GET", "/kernel/governance-changes?resource=true", config=config
    )
    assert listed_resources.status == 200
    resource = listed_resources.payload["proposals"][0]
    assert resource["kind"] == "GovernanceChangeProposal"
    assert resource["metadata"]["resource_id"] == proposal_id
    assert resource["metadata"]["labels"]["review_ready"] == "true"

    fetched_resource = dispatch_kernel_request(
        "GET", f"/kernel/governance-changes/{proposal_id}?resource=true", config=config
    )
    assert fetched_resource.status == 200
    assert fetched_resource.payload["proposal"]["spec"]["title"] == (
        "Clarify evaluator escalation authority"
    )

    decided = dispatch_kernel_request(
        "POST",
        f"/kernel/governance-changes/{proposal_id}/decision",
        {
            "decision": "approve",
            "reason": "Evidence and invariant checks are sufficient.",
            "actor_context": {
                "actor_id": "human.principal",
                "actor_kind": "human",
                "role_id": "role.principal",
            },
        },
        config=config,
    )
    assert decided.status == 200
    assert decided.payload["result"]["decided_by"] == "human.principal"

    fetched = dispatch_kernel_request(
        "GET", f"/kernel/governance-changes/{proposal_id}", config=config
    )
    assert fetched.status == 200
    assert fetched.payload["proposal"]["decided"] is True

    duplicate = dispatch_kernel_request(
        "POST",
        f"/kernel/governance-changes/{proposal_id}/decision",
        {"decision": "decline"},
        config=config,
    )
    assert duplicate.status == 409
    assert "already been decided" in duplicate.payload["error"]

    missing = dispatch_kernel_request(
        "GET", "/kernel/governance-changes/gcp_missing", config=config
    )
    assert missing.status == 404


def test_decision_aggregation_approval_does_not_decide_governance_change(
    tmp_path: Path,
) -> None:
    config = KernelServiceConfig(
        org_dir=tmp_path / "org",
        transition_log=tmp_path / "transitions.jsonl",
        decision_aggregation_log=tmp_path / "decision_aggregation_cases.jsonl",
    )
    created = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes",
        {
            "change_kind": "mandate_change",
            "title": "Clarify reviewer handoff",
            "target_ref": "org/mandates/evaluator.md",
            "rationale": "Review handoff evidence should be easier to inspect.",
            "source_refs": ["work:review-handoff"],
            "expected_behavior_change": "Reviewer handoffs cite decision evidence.",
            "risk_summary": "No authority expansion; review evidence only.",
            "rollback_plan": "Restore the previous mandate file from git.",
            "owner_role": "role.principal",
            "invariant_checks": _passing_governance_checks(),
            "actor_context": {
                "actor_id": "agent.org_evolver",
                "actor_kind": "agent",
                "role_id": "role.org_evolver",
            },
        },
        config=config,
    )
    assert created.status == 201
    proposal_id = created.payload["proposal"]["proposal_id"]

    opened = dispatch_kernel_request(
        "POST",
        "/kernel/decision-aggregation-cases",
        {
            "subject_ref": f"governance_change:{proposal_id}",
            "downstream_ref": f"governance_change:{proposal_id}",
            "decision_class": "structural_change_review",
            "scope_kind": "project",
            "scope_ref": "self_evolving_org_demo",
            "procedure_kind": "quorum_majority",
            "opened_by": "role.evaluator",
            "eligibility_basis": (
                "reviewer quorum is evidence for the principal approval path"
            ),
            "eligible_roles": ["role.evaluator", "role.risk_guardian"],
            "quorum": 2,
        },
        config=config,
    )
    assert opened.status == 201
    case_id = opened.payload["decision_aggregation_case"]["case_id"]
    for actor_id, role_id in (
        ("agent.evaluator", "role.evaluator"),
        ("agent.risk_guardian", "role.risk_guardian"),
    ):
        position = dispatch_kernel_request(
            "POST",
            f"/kernel/decision-aggregation-cases/{case_id}/positions",
            {
                "actor_id": actor_id,
                "role_id": role_id,
                "position": "approve",
                "rationale": f"{role_id} approves as review evidence.",
                "evidence_refs": [f"governance_change:{proposal_id}"],
            },
            config=config,
        )
        assert position.status == 200

    computed = dispatch_kernel_request(
        "POST",
        f"/kernel/decision-aggregation-cases/{case_id}/compute",
        {},
        config=config,
    )
    assert computed.status == 200
    assert computed.payload["decision_aggregation_case"]["result"]["recommendation"] == (
        "approve"
    )

    fetched = dispatch_kernel_request(
        "GET", f"/kernel/governance-changes/{proposal_id}", config=config
    )
    assert fetched.status == 200
    assert fetched.payload["proposal"]["decided"] is False
    assert fetched.payload["proposal"]["status"] == "review_ready"

    shortcut = dispatch_kernel_request(
        "POST",
        f"/kernel/governance-changes/{proposal_id}/outcome-link",
        {"outcome_link_id": "olink_should_not_open"},
        config=config,
    )
    assert shortcut.status == 409
    assert "approved governance change" in shortcut.payload["error"]

    decided = dispatch_kernel_request(
        "POST",
        f"/kernel/governance-changes/{proposal_id}/decision",
        {
            "decision": "approve",
            "reason": "Principal uses reviewer aggregation as evidence.",
            "actor_context": {
                "actor_id": "human.principal",
                "actor_kind": "human",
                "role_id": "role.principal",
            },
        },
        config=config,
    )
    assert decided.status == 200
    assert decided.payload["result"]["decided_by"] == "human.principal"


def test_kernel_service_preserves_governance_change_predicted_effect(tmp_path: Path):
    config = KernelServiceConfig(
        org_dir=tmp_path / "org",
        transition_log=tmp_path / "transitions.jsonl",
    )

    created = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes",
        {
            "change_kind": "mandate_change",
            "title": "Measure evaluator handoff rule",
            "target_ref": "org/mandates/evaluator.md",
            "rationale": "Verifier history shows handoff quality should be measured.",
            "source_refs": ["phase_execution_plan:pex_1"],
            "predicted_effect": {
                "metric_name": "handoff_rework_rate",
                "metric_unit": "ratio",
                "direction": "lower_is_better",
                "threshold": 0.1,
                "review_horizon": "after_next_10_handoffs",
            },
            "risk_summary": "Narrows review acceptance; no new authority.",
            "rollback_plan": "Restore the previous evaluator mandate.",
            "invariant_checks": _passing_governance_checks(),
        },
        config=config,
    )

    assert created.status == 201
    proposal = created.payload["proposal"]
    assert proposal["status"] == "review_ready"
    assert proposal["expected_behavior_change"] is None
    assert proposal["predicted_effect"] == {
        "metric_name": "handoff_rework_rate",
        "metric_unit": "ratio",
        "direction": "lower_is_better",
        "threshold": 0.1,
        "review_horizon": "after_next_10_handoffs",
        "expected_verdict": "improved",
        "rationale": None,
    }


def test_kernel_service_opens_predicted_mutation_outcome_link_from_approved_proposal(
    tmp_path: Path,
):
    config = KernelServiceConfig(
        org_dir=tmp_path / "org",
        transition_log=tmp_path / "transitions.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        kernel_events_log=tmp_path / "kernel_events.jsonl",
    )

    created = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes",
        {
            "proposal_id": "gcp_predicted_handoff",
            "change_kind": "mandate_change",
            "title": "Measure evaluator handoff rule",
            "target_ref": "org/mandates/evaluator.md",
            "rationale": "Verifier history shows handoff quality should be measured.",
            "source_refs": ["phase_execution_plan:pex_1"],
            "predicted_effect": {
                "metric_name": "handoff_rework_rate",
                "metric_unit": "ratio",
                "direction": "lower_is_better",
                "threshold": 0.1,
                "review_horizon": "after_next_10_handoffs",
            },
            "risk_summary": "Narrows review acceptance; no new authority.",
            "rollback_plan": "Restore the previous evaluator mandate.",
            "owner_role": "role.evaluator",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "invariant_checks": _passing_governance_checks(),
        },
        config=config,
    )
    assert created.status == 201

    blocked = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes/gcp_predicted_handoff/outcome-link",
        {"created_by": "role.evaluator"},
        config=config,
    )
    assert blocked.status == 409
    assert "require an approved governance change" in blocked.payload["error"]

    approved = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes/gcp_predicted_handoff/decision",
        {
            "decision": "approve",
            "reason": "Prediction and invariant checks are sufficient.",
            "actor_context": {
                "actor_id": "human.principal",
                "actor_kind": "human",
                "role_id": "role.principal",
            },
        },
        config=config,
    )
    assert approved.status == 200

    opened = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes/gcp_predicted_handoff/outcome-link",
        {
            "created_by": "role.evaluator",
            "learning_event_id": "learn_handoff_rule",
            "metadata": {"run_id": "run_1"},
            "outcome_link_id": "olink_predicted_handoff",
        },
        config=config,
    )
    assert opened.status == 201
    link = opened.payload["outcome_link"]
    assert link["outcome_link_id"] == "olink_predicted_handoff"
    assert link["change_ref"] == "governance_change:gcp_predicted_handoff"
    assert link["change_kind"] == "governance_change"
    assert link["metric_name"] == "handoff_rework_rate"
    assert link["metric_unit"] == "ratio"
    assert link["direction"] == "lower_is_better"
    assert link["learning_event_id"] == "learn_handoff_rule"
    assert link["tenant_id"] == "tenant-a"
    assert link["project_id"] == "project-a"
    assert link["owner_role"] == "role.evaluator"
    assert link["metadata"]["source_recipe"] == (
        "predicted_mutation_outcome_link_request.v1"
    )
    assert link["metadata"]["source_proposal_id"] == "gcp_predicted_handoff"
    assert link["metadata"]["target_ref"] == "org/mandates/evaluator.md"
    assert link["metadata"]["predicted_effect"]["threshold"] == 0.1
    assert opened.payload["request"]["change_ref"] == (
        "governance_change:gcp_predicted_handoff"
    )


def test_kernel_service_records_action_impact_policy_evaluation_and_promotion_packet(
    tmp_path: Path,
) -> None:
    rows = []
    for idx in range(30):
        arm = "senior_review" if idx % 2 == 0 else "fast_lane"
        rows.append(
            {
                "action_id": f"a{idx}",
                "action_ref": f"actions/{idx}",
                "actor": "role.support_router",
                "objective_metric": "resolution_quality",
                "status": "measured",
                "context_features": {"segment": "enterprise"},
                "action_arm": arm,
                "logging_policy_probability": 0.5,
                "counterfactual_action": "other",
                "reward": 0.9 if arm == "senior_review" else 0.6,
                "guardrail_metrics": {"sla_hours": 4.0},
            }
        )
    summary_path = tmp_path / "action_impact_summary.json"
    summary_path.write_text(json.dumps({"records": rows}), encoding="utf-8")
    config = KernelServiceConfig(
        action_impact_summary=summary_path,
        policy_evaluations_log=tmp_path / "policy_evaluations.jsonl",
        policy_promotion_packets_log=tmp_path / "policy_promotion_packets.jsonl",
        transition_log=tmp_path / "transitions.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        kernel_events_log=tmp_path / "kernel_events.jsonl",
        org_dir=tmp_path / "org",
    )
    enterprise_sig = context_signature({"segment": "enterprise"}, ["segment"])
    assert enterprise_sig is not None

    evaluated = dispatch_kernel_request(
        "POST",
        "/kernel/action-impact/policy-evaluations/evaluate",
        {
            "candidate_policy_id": "policy.support.enterprise-review",
            "candidate_policy_ref": "policy://support/enterprise-review",
            "candidate_action_by_context": {enterprise_sig: "senior_review"},
            "context_keys": ["segment"],
            "objective_metric": "resolution_quality",
            "min_matched": 10,
            "min_support_coverage": 0.4,
            "evidence_refs": ["action_impact_summary:test"],
        },
        config=config,
    )

    assert evaluated.status == 201
    report = evaluated.payload["policy_evaluation"]
    assert report["status"] == "promotable"
    assert report["promotion_allowed"] is True
    assert report["n_matched"] == 15
    assert report["delta_mean_reward"] > 0

    listed_evaluations = dispatch_kernel_request(
        "GET",
        "/kernel/action-impact/policy-evaluations?status=promotable",
        config=config,
    )
    assert listed_evaluations.status == 200
    assert [row["evaluation_id"] for row in listed_evaluations.payload["policy_evaluations"]] == [
        report["evaluation_id"]
    ]

    packet_response = dispatch_kernel_request(
        "POST",
        "/kernel/action-impact/policy-promotion-packets",
        {
            "evaluation_id": report["evaluation_id"],
            "proposed_by": "role.governance_reviewer",
            "authority_diff_ref": "authority-diff://support-enterprise-review",
            "formal_verification_refs": ["formal_verification:fver_policy_boundary"],
            "learning_event_refs": ["learning_event:learn_policy_support"],
            "predicted_effect": {
                "metric_name": "resolution_quality",
                "metric_unit": "score",
                "direction": "higher_is_better",
                "threshold": 0.05,
                "review_horizon": "after_next_20_cases",
            },
            "evidence_refs": [f"action_impact_policy_evaluation:{report['evaluation_id']}"],
        },
        config=config,
    )

    assert packet_response.status == 201
    packet = packet_response.payload["policy_promotion_packet"]
    assert packet["status"] == "review_ready"
    assert packet["candidate_policy_id"] == "policy.support.enterprise-review"
    assert packet["governance_change_candidate"]["predicted_effect"][
        "metric_name"
    ] == "resolution_quality"
    assert packet["review_blockers"] == []

    listed_packets = dispatch_kernel_request(
        "GET",
        "/kernel/action-impact/policy-promotion-packets?status=review_ready",
        config=config,
    )
    assert listed_packets.status == 200
    assert [
        row["packet_id"]
        for row in listed_packets.payload["policy_promotion_packets"]
    ] == [packet["packet_id"]]

    proposed = dispatch_kernel_request(
        "POST",
        f"/kernel/action-impact/policy-promotion-packets/{packet['packet_id']}/governance-change",
        {
            "proposal_id": "gcp_enterprise_review_policy",
            "owner_role": "role.governance_reviewer",
            "tenant_id": "tenant-support",
            "project_id": "project-enterprise",
            "invariant_checks": _passing_governance_checks(),
            "metadata": {"requested_from": "kernel_service_test"},
        },
        config=config,
    )

    assert proposed.status == 201
    proposal = proposed.payload["proposal"]
    assert proposal["proposal_id"] == "gcp_enterprise_review_policy"
    assert proposal["status"] == "review_ready"
    assert proposal["change_kind"] == "route_policy_change"
    assert proposal["target_ref"] == "policy://support/enterprise-review"
    assert proposal["predicted_effect"]["metric_name"] == "resolution_quality"
    assert proposal["metadata"]["source_policy_promotion_packet_id"] == packet["packet_id"]
    assert proposal["metadata"]["source_recipe"] == (
        "policy_promotion_packet_governance_change_request.v1"
    )
    assert f"policy_promotion_packet:{packet['packet_id']}" in proposal["source_refs"]
    assert proposed.payload["boundary"] == {
        "approved_governance": False,
        "applied_policy": False,
        "executed_runtime": False,
    }

    approved = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes/gcp_enterprise_review_policy/decision",
        {
            "decision": "approve",
            "reason": "Policy promotion packet and invariant checks are sufficient.",
            "actor_context": {
                "actor_id": "human.principal",
                "actor_kind": "human",
                "role_id": "role.principal",
            },
        },
        config=config,
    )
    assert approved.status == 200

    opened_outcome = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes/gcp_enterprise_review_policy/outcome-link",
        {
            "created_by": "role.governance_reviewer",
            "learning_event_id": "learn_policy_support",
            "outcome_link_id": "olink_enterprise_review_policy",
            "metadata": {"source_test": "policy_promotion_packet_e2e"},
        },
        config=config,
    )

    assert opened_outcome.status == 201
    outcome_link = opened_outcome.payload["outcome_link"]
    assert outcome_link["outcome_link_id"] == "olink_enterprise_review_policy"
    assert outcome_link["change_ref"] == "governance_change:gcp_enterprise_review_policy"
    assert outcome_link["change_kind"] == "governance_change"
    assert outcome_link["metric_name"] == "resolution_quality"
    assert outcome_link["metric_unit"] == "score"
    assert outcome_link["direction"] == "higher_is_better"
    assert outcome_link["learning_event_id"] == "learn_policy_support"
    assert outcome_link["tenant_id"] == "tenant-support"
    assert outcome_link["project_id"] == "project-enterprise"
    assert outcome_link["owner_role"] == "role.governance_reviewer"
    assert outcome_link["metadata"]["source_policy_promotion_packet_id"] == packet["packet_id"]
    assert outcome_link["metadata"]["source_recipe"] == (
        "predicted_mutation_outcome_link_request.v1"
    )
    assert outcome_link["metadata"]["predicted_effect"]["threshold"] == 0.05
    assert opened_outcome.payload["request"]["metadata"][
        "source_test"
    ] == "policy_promotion_packet_e2e"


def test_kernel_service_evaluates_and_lists_policy_decisions(tmp_path: Path) -> None:
    config = KernelServiceConfig(policy_decisions_log=tmp_path / "policy_decisions.jsonl")

    evaluated = dispatch_kernel_request(
        "POST",
        "/kernel/policy-decisions/evaluate",
        {
            "request": {
                "action": "kernel_event.append",
                "actor_id": "service.worker",
                "resource_ref": "kernel_event:project-a",
                "tenant_id": "tenant-a",
                "role_id": "role.worker",
                "project_id": "project-a",
            },
            "rules": [
                {
                    "rule_id": "allow-worker-project-a",
                    "effect": "allow",
                    "reason": "worker has scoped project membership",
                    "match": {"actor_id": "service.worker", "project_id": "project-a"},
                }
            ],
        },
        config=config,
    )

    assert evaluated.status == 201
    decision = evaluated.payload["policy_decision"]
    assert decision["allowed"] is True
    assert decision["matched_rule_id"] == "allow-worker-project-a"

    listed = dispatch_kernel_request(
        "GET",
        "/kernel/policy-decisions?effect=allow&actor_id=service.worker",
        config=config,
    )
    assert listed.status == 200
    assert [row["decision_id"] for row in listed.payload["policy_decisions"]] == [
        decision["decision_id"]
    ]


def test_kernel_service_rejects_advisory_policy_promotion_packet_for_governance_change(
    tmp_path: Path,
) -> None:
    rows = [
        {
            "action_id": f"a{idx}",
            "action_ref": f"actions/{idx}",
            "actor": "role.support_router",
            "objective_metric": "resolution_quality",
            "status": "measured",
            "context_features": {"segment": "enterprise"},
            "action_arm": "senior_review" if idx % 2 == 0 else "fast_lane",
            "logging_policy_probability": 0.5,
            "counterfactual_action": "other",
            "reward": 0.9 if idx % 2 == 0 else 0.6,
            "guardrail_metrics": {"sla_hours": 4.0},
        }
        for idx in range(12)
    ]
    summary_path = tmp_path / "action_impact_summary.json"
    summary_path.write_text(json.dumps({"records": rows}), encoding="utf-8")
    config = KernelServiceConfig(
        action_impact_summary=summary_path,
        policy_evaluations_log=tmp_path / "policy_evaluations.jsonl",
        policy_promotion_packets_log=tmp_path / "policy_promotion_packets.jsonl",
        org_dir=tmp_path / "org",
    )
    enterprise_sig = context_signature({"segment": "enterprise"}, ["segment"])
    assert enterprise_sig is not None
    evaluated = dispatch_kernel_request(
        "POST",
        "/kernel/action-impact/policy-evaluations/evaluate",
        {
            "candidate_policy_id": "policy.support.enterprise-review",
            "candidate_action_by_context": {enterprise_sig: "senior_review"},
            "context_keys": ["segment"],
            "objective_metric": "resolution_quality",
            "min_matched": 5,
            "min_support_coverage": 0.4,
        },
        config=config,
    )
    assert evaluated.status == 201
    packet_response = dispatch_kernel_request(
        "POST",
        "/kernel/action-impact/policy-promotion-packets",
        {
            "evaluation_id": evaluated.payload["policy_evaluation"]["evaluation_id"],
            "proposed_by": "role.governance_reviewer",
        },
        config=config,
    )
    assert packet_response.status == 201
    packet = packet_response.payload["policy_promotion_packet"]
    assert packet["status"] == "advisory"

    proposed = dispatch_kernel_request(
        "POST",
        f"/kernel/action-impact/policy-promotion-packets/{packet['packet_id']}/governance-change",
        {"invariant_checks": _passing_governance_checks()},
        config=config,
    )

    assert proposed.status == 400
    assert "must be review_ready" in proposed.payload["error"]


def test_kernel_service_can_attach_deletion_duty_check(tmp_path: Path):
    config = KernelServiceConfig(
        org_dir=tmp_path / "org",
        transition_log=tmp_path / "transitions.jsonl",
    )

    missing_duty = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes",
        {
            "change_kind": "role_change",
            "title": "Add a new review office",
            "target_ref": "org/roles/new_review_office.yaml",
            "rationale": "Workload probes need a bounded reviewer.",
            "source_refs": ["workload_packet:packet-004"],
            "expected_behavior_change": "Repeated review gaps route to a named office.",
            "risk_summary": "Adds structure and review overhead.",
            "rollback_plan": "Remove the new role file and route back to Evaluator.",
            "require_deletion_duty": True,
            "invariant_checks": _passing_governance_checks(),
        },
        config=config,
    )
    assert missing_duty.status == 201
    proposal = missing_duty.payload["proposal"]
    assert proposal["status"] == "blocked"
    deletion_check = next(
        check
        for check in proposal["invariant_checks"]
        if check["invariant"] == "deletion_duty_checked"
    )
    assert deletion_check["status"] == "fail"
    assert "deletion_duty:missing_retirement_or_justification" in deletion_check[
        "evidence_refs"
    ]

    justified = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes",
        {
            "change_kind": "role_change",
            "title": "Add a narrow packet scorer office",
            "target_ref": "org/roles/packet_scorer.yaml",
            "rationale": "Workload probes need external scoring receipts.",
            "source_refs": ["workload_packet:packet-001"],
            "expected_behavior_change": "Score receipts are produced by a bounded office.",
            "risk_summary": "Adds a narrow office without execution authority.",
            "rollback_plan": "Remove the scorer office and return scoring to the harness.",
            "require_deletion_duty": True,
            "net_growth_justification": "The hidden scorer is a separate control surface.",
            "deletion_duty_evidence_refs": ["routine_review:packet-scoring-design"],
            "invariant_checks": _passing_governance_checks(),
        },
        config=config,
    )
    assert justified.status == 201
    proposal = justified.payload["proposal"]
    assert proposal["status"] == "review_ready"
    deletion_check = next(
        check
        for check in proposal["invariant_checks"]
        if check["invariant"] == "deletion_duty_checked"
    )
    assert deletion_check["status"] == "pass"
    assert "net_growth_justification:present" in deletion_check["evidence_refs"]
    assert "routine_review:packet-scoring-design" in deletion_check["evidence_refs"]


def _valid_mutation_proof_request() -> dict[str, object]:
    return {
        "step_id": "evaluator_handoff",
        "change_kind": "mandate_change",
        "target_ref": "org/mandates/evaluator.md",
        "run_id": "run_123",
        "work_id": "work_123",
        "proposal_id": "gcp_123",
        "approval_event_id": "evt_123",
        "mutation_ref": "file://org/mandates/evaluator.md",
        "attestation_id": "aat_123",
        "learning_event_id": "learn_123",
        "outcome_link_id": "olink_123",
        "routine_review_id": "rrev_123",
        "bundle_id": "gab_run_123",
        "bundle_digest": "sha256:" + "c" * 64,
        "bundle_verdict": "passed",
        "commit_sha": "abc123",
    }


def test_kernel_service_builds_and_validates_mutation_proofs() -> None:
    built = dispatch_kernel_request(
        "POST",
        "/kernel/mutation-proofs/build",
        {
            **_valid_mutation_proof_request(),
            "evidence_carrier_refs": [
                "capability_signal:csig_123",
                "learning_transition_candidate:ltc_123",
            ],
        },
    )

    assert built.status == 200
    proof = built.payload["proof"]
    assert proof["proof_kind"] == "governed_mutation_proof"
    assert proof["valid"] is True
    assert proof["validation_errors"] == []
    assert proof["evidence_carrier_refs"] == [
        "capability_signal:csig_123",
        "learning_transition_candidate:ltc_123",
    ]

    validated = dispatch_kernel_request(
        "POST",
        "/kernel/mutation-proofs/validate",
        {"proof": proof},
    )

    assert validated.status == 200
    assert validated.payload["valid"] is True
    assert validated.payload["errors"] == []
    assert validated.payload["proof_digest"] == proof["proof_digest"]


def test_kernel_service_mutation_proof_validation_is_read_only_post() -> None:
    config = KernelServiceConfig(
        surface_write_modes={"orbit": "projection_only"},
    )
    built = dispatch_kernel_request(
        "POST",
        "/kernel/mutation-proofs/build",
        {
            **_valid_mutation_proof_request(),
            "actor_context": {"surface": "orbit"},
        },
        config=config,
    )

    assert built.status == 200
    assert built.payload["proof"]["valid"] is True

    tampered = dict(built.payload["proof"])
    tampered["commit"] = "tampered"
    validated = dispatch_kernel_request(
        "POST",
        "/kernel/mutation-proofs/validate",
        {
            "proof": tampered,
            "actor_context": {"surface": "orbit"},
        },
        config=config,
    )

    assert validated.status == 200
    assert validated.payload["valid"] is False
    assert any("proof_digest mismatch" in error for error in validated.payload["errors"])


def test_kernel_service_builds_and_validates_governed_run_bundles(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        project_root=tmp_path,
        transition_log=tmp_path / "transitions.jsonl",
        action_attestation_log=tmp_path / "action_attestations.jsonl",
        formal_verification_log=tmp_path / "formal_verifications.jsonl",
        human_work_log=tmp_path / "human_work.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        accountability_cases_log=tmp_path / "accountability_cases.jsonl",
        work_items_log=tmp_path / "work_items.jsonl",
        leases_log=tmp_path / "leases.jsonl",
    )
    started = dispatch_kernel_request(
        "POST",
        "/kernel/runs",
        {
            "owner_role": "role.manager",
            "objective": "Build service-routed bundle.",
            "idempotency_key": "service-bundle-test",
        },
        config=config,
    )
    assert started.status == 201
    run_id = started.payload["run"]["run_id"]
    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        verification_summary="digest checked",
        run_id=run_id,
        log_path=config.action_attestation_log,
    )
    completed = dispatch_kernel_request(
        "POST",
        f"/kernel/runs/{run_id}/state",
        {"state": "completed", "actor": "role.manager"},
        config=config,
    )
    assert completed.status == 200

    built = dispatch_kernel_request(
        "POST",
        "/kernel/governed-run-bundles/build",
        {"run_id": run_id},
        config=config,
    )

    assert built.status == 200
    assert built.payload["summary"]["verdict"] == "passed"
    assert built.payload["validation"] == {"ok": True, "errors": []}
    assert built.payload["bundle"]["run"]["run_id"] == run_id

    validated = dispatch_kernel_request(
        "POST",
        "/kernel/governed-run-bundles/validate",
        {"bundle": built.payload["bundle"]},
        config=config,
    )

    assert validated.status == 200
    assert validated.payload["valid"] is True
    assert validated.payload["errors"] == []
    assert validated.payload["bundle_digest"] == built.payload["bundle"]["bundle_digest"]


def test_kernel_service_creates_action_attestations(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        action_attestation_log=tmp_path / "action_attestations.jsonl",
    )

    invocation_receipt = {
        "schema_version": "agent_invocation_receipt.v1",
        "runtime": "claude",
        "adapter": "claude_print",
        "command_argv": ["claude", "--print", "{prompt}"],
        "prompt_digest": digest_text("prompt"),
        "stdout_digest": digest_text("stdout"),
        "stderr_digest": digest_text(""),
    }
    created = dispatch_kernel_request(
        "POST",
        "/kernel/action-attestations",
        {
            "subject_kind": "runtime_event",
            "subject_ref": "agent_invocation_receipt:abc123",
            "subject_digest": digest_text("receipt"),
            "producer": "role.manager",
            "action_type": "agent_cli_dispatch",
            "verification_status": "verified",
            "verification_summary": "digest checked",
            "run_id": "run_123",
            "metadata": {
                "fixture": "service-route",
                "agent_invocation_receipt": invocation_receipt,
            },
        },
        config=config,
    )

    assert created.status == 201
    attestation = created.payload["action_attestation"]
    assert attestation["attestation_id"].startswith("aat_")
    assert attestation["producer"] == "role.manager"
    assert attestation["subject_digest"].startswith("sha256:")
    assert attestation["run_id"] == "run_123"

    listed = dispatch_kernel_request(
        "GET",
        "/kernel/action-attestations?run_id=run_123",
        config=config,
    )
    assert listed.status == 200
    assert [row["attestation_id"] for row in listed.payload["action_attestations"]] == [
        attestation["attestation_id"]
    ]

    resources = dispatch_kernel_request(
        "GET",
        "/kernel/action-attestations?producer=role.manager&resource=true",
        config=config,
    )
    assert resources.status == 200
    resource = resources.payload["action_attestations"][0]
    assert resource["kind"] == "ActionAttestation"
    assert resource["metadata"]["name"] == attestation["attestation_id"]
    assert resource["status"]["verification_status"] == "verified"
    assert resource["spec"]["metadata"]["agent_invocation_receipt"] == invocation_receipt

    create_action_attestation(
        subject_kind="runtime_event",
        subject_ref="agent_invocation_receipt:def456",
        subject_digest=digest_text("receipt 2"),
        producer="role.manager",
        action_type="agent_cli_dispatch",
        verification_status="failed",
        verification_summary="non-zero return code",
        run_id="run_456",
        metadata={
            "agent_invocation_receipt": {
                "schema_version": "agent_invocation_receipt.v1",
                "runtime": "codex",
                "adapter": "codex_exec",
                "prompt_transport": "file",
                "returncode": 1,
                "agent_session_id": "sess_agent_2",
                "prompt_digest": digest_text("prompt 2"),
                "stdout_digest": digest_text("stdout 2"),
                "stderr_digest": digest_text("stderr 2"),
            }
        },
        log_path=config.action_attestation_log,
    )
    create_action_attestation(
        subject_kind="artifact",
        subject_ref="artifact:report",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="report_written",
        verification_status="verified",
        metadata={"agent_invocation_receipt": invocation_receipt},
        log_path=config.action_attestation_log,
    )

    invocations = dispatch_kernel_request(
        "GET",
        "/kernel/agent-invocations?producer=role.manager&limit=1",
        config=config,
    )
    assert invocations.status == 200
    assert invocations.payload["limit"] == 1
    assert [row["run_id"] for row in invocations.payload["agent_invocations"]] == [
        "run_456"
    ]
    invocation = invocations.payload["agent_invocations"][0]
    assert invocation["runtime"] == "codex"
    assert invocation["adapter"] == "codex_exec"
    assert invocation["returncode"] == 1
    assert invocation["agent_session_id"] == "sess_agent_2"
    assert invocation["stderr_digest"] == digest_text("stderr 2")

    failed_invocations = dispatch_kernel_request(
        "GET",
        "/kernel/agent-invocations?verification_status=failed",
        config=config,
    )
    assert failed_invocations.status == 200
    assert [row["run_id"] for row in failed_invocations.payload["agent_invocations"]] == [
        "run_456"
    ]


def test_kernel_service_records_formal_provider_payload(tmp_path: Path) -> None:
    org_dir = tmp_path / "org"
    keypair = generate_keypair()
    configure_trusted_provider(
        provider="leanmill",
        public_key_pem=keypair.public_pem,
        authority_root=org_dir,
        public_key_ref="leanmill://keys/service-test",
        trust_basis="Service route test provider key.",
    )
    config = KernelServiceConfig(
        org_dir=org_dir,
        formal_verification_log=tmp_path / "formal_verifications.jsonl",
        action_attestation_log=tmp_path / "action_attestations.jsonl",
    )
    payload = {
        "schema_version": FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
        "provider": "leanmill",
        "formal_system": "lean",
        "verifier_ref": "leanmill:service-test",
        "property_class": "workflow_safety",
        "subject_ref": "workflow://release-review-before-send",
        "subject_digest": digest_text("release workflow requires review before send"),
        "claim_ref": "claim://release-review-before-send",
        "certificate_ref": "leanmill://certificates/release-review-before-send",
        "certificate_digest": digest_text("leanmill checked certificate fixture"),
        "verdict": "verified",
        "verification_summary": "Provider emitted a checked workflow-safety invariant.",
        "run_id": "run_formal_service",
        "faithfulness_refs": ["leanmill://faithfulness/release-review-before-send"],
        "checker_evidence_refs": ["leanmill://kernel-log/release-review-before-send"],
        "metadata": {},
    }
    payload["metadata"]["provider_payload_signature"] = sign_provider_payload(
        payload,
        private_key_pem=keypair.private_pem,
    )

    created = dispatch_kernel_request(
        "POST",
        "/kernel/formal-verifications/provider-payload",
        {"payload": payload},
        config=config,
    )
    assert created.status == 201
    record = created.payload["formal_verification"]
    assert record["metadata"]["provider_payload_signature_verified"] is True
    assert record["action_attestation_id"].startswith("aat_")

    listed = dispatch_kernel_request(
        "GET",
        "/kernel/formal-verifications?run_id=run_formal_service",
        config=config,
    )
    assert listed.status == 200
    assert [row["verification_id"] for row in listed.payload["formal_verifications"]] == [
        record["verification_id"]
    ]
    attestations = dispatch_kernel_request(
        "GET",
        "/kernel/action-attestations?run_id=run_formal_service",
        config=config,
    )
    assert attestations.status == 200
    assert [row["attestation_id"] for row in attestations.payload["action_attestations"]] == [
        record["action_attestation_id"]
    ]


def test_kernel_service_creates_approved_learning_events(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        learning_events_log=tmp_path / "learning_events.jsonl",
    )

    created = dispatch_kernel_request(
        "POST",
        "/kernel/learning-events",
        {
            "learning_unit_kind": "routine_change",
            "decision_use": "Use reviewer handoff when queue stalls.",
            "future_application_cue": "queue stalls",
            "approved_by": "role.owner",
            "approval_ref": "governance_change:gcp_123",
            "source_carrier_refs": ["capability_signal:csig_123"],
            "owner_role": "role.manager",
            "metadata": {"tags": ["service_route"]},
        },
        config=config,
    )

    assert created.status == 201
    event = created.payload["learning_event"]
    assert event["learning_event_id"].startswith("learn_")
    assert event["approval_ref"] == "governance_change:gcp_123"
    assert event["source_carrier_refs"] == ["capability_signal:csig_123"]

    replayed = dispatch_kernel_request(
        "GET",
        "/kernel/learning-events/replay?role=role.manager&cue=queue+stalls",
        config=config,
    )
    assert replayed.status == 200
    assert [row["learning_event_id"] for row in replayed.payload["learning_events"]] == [
        event["learning_event_id"]
    ]


def test_kernel_service_bundle_routes_are_read_only_posts(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        project_root=tmp_path,
        transition_log=tmp_path / "transitions.jsonl",
        action_attestation_log=tmp_path / "action_attestations.jsonl",
        formal_verification_log=tmp_path / "formal_verifications.jsonl",
        surface_write_modes={"orbit": "projection_only"},
    )
    started = dispatch_kernel_request(
        "POST",
        "/kernel/runs",
        {
            "owner_role": "role.manager",
            "objective": "Build read-only proof route fixture.",
            "actor_context": {"surface": "cli"},
        },
        config=config,
    )
    assert started.status == 201
    run_id = started.payload["run"]["run_id"]
    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        run_id=run_id,
        log_path=config.action_attestation_log,
    )
    completed = dispatch_kernel_request(
        "POST",
        f"/kernel/runs/{run_id}/state",
        {"state": "completed", "actor": "role.manager", "actor_context": {"surface": "cli"}},
        config=config,
    )
    assert completed.status == 200

    built = dispatch_kernel_request(
        "POST",
        "/kernel/governed-run-bundles/build?summary=true",
        {
            "run_id": run_id,
            "actor_context": {"surface": "orbit"},
        },
        config=config,
    )

    assert built.status == 200
    assert built.payload["summary"]["run_id"] == run_id
    assert built.payload["summary"]["verdict"] == "passed"
    assert "bundle" not in built.payload


def test_kernel_service_surfaces_execution_evidence_carriers(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        trace_events_log=tmp_path / "trace_events.jsonl",
        attribution_packets_log=tmp_path / "attribution_packets.jsonl",
        phase_execution_log=tmp_path / "phase_execution.jsonl",
        protocol_experiments_log=tmp_path / "protocol_experiments.jsonl",
        capability_signals_log=tmp_path / "capability_signals.jsonl",
    )
    root_event = record_trace_event(
        runtime_name="fixture_runtime",
        external_run_id="external_1",
        cognitive_run_id="run_1",
        event_kind="agent_spawned",
        agent_id="agent.root",
        summary="Root agent spawned worker.",
        log_path=config.trace_events_log,
    )
    child_event = record_trace_event(
        runtime_name="fixture_runtime",
        external_run_id="external_1",
        cognitive_run_id="run_1",
        event_kind="abstention",
        agent_id="agent.worker",
        parent_agent_id="agent.root",
        status="abstained",
        summary="Worker abstained due to missing evidence.",
        log_path=config.trace_events_log,
    )
    create_failure_attribution_packet(
        events=[root_event, child_event],
        failure_summary="Worker abstention exposed an evidence routing gap.",
        proposed_carrier_kind="learning_transition",
        owner_role="role.evaluator",
        risk_summary="Carrier is observer-only.",
        rollback_plan="Discard the learning candidate if review rejects it.",
        log_path=config.attribution_packets_log,
    )
    start_phase_execution_plan(
        objective="Separate planning, execution, and verification for the fixture.",
        owner_role="role.executor",
        plan_id="pex_test",
        log_path=config.phase_execution_log,
    )
    experiment = start_protocol_experiment(
        objective="Compare coordination protocols for fixture work.",
        owner_role="role.evaluator",
        candidate_protocols=["coordinator", "sequential"],
        baseline_protocol="sequential",
        experiment_id="pexp_test",
        log_path=config.protocol_experiments_log,
    )
    for protocol, score in (
        ("sequential", 0.7),
        ("sequential", 0.72),
        ("coordinator", 0.83),
        ("coordinator", 0.86),
    ):
        record_protocol_observation(
            experiment_id=experiment.experiment_id,
            protocol=protocol,
            task_ref=f"task:{protocol}:{score}",
            quality_score=score,
            log_path=config.protocol_experiments_log,
        )
    build_protocol_experiment_report(
        experiment_id=experiment.experiment_id,
        proposed_by="role.evaluator",
        target_ref="route_policy:fixture",
        log_path=config.protocol_experiments_log,
    )
    record_capability_signal(
        signal_kind="abstention",
        source_ref="run:run_1",
        summary="Agent abstained because evidence was missing.",
        owner_role="role.evaluator",
        severity="warning",
        recommended_route="request_evidence",
        log_path=config.capability_signals_log,
    )

    trace_response = dispatch_kernel_request(
        "GET",
        "/kernel/multi-agent-trace-events?runtime_name=fixture_runtime&resource=true",
        config=config,
    )
    assert trace_response.status == 200
    assert len(trace_response.payload["trace_events"]) == 2
    assert trace_response.payload["trace_events"][0]["kind"] == "MultiAgentTraceEvent"

    graph_response = dispatch_kernel_request(
        "GET",
        "/kernel/delegation-graph?runtime_name=fixture_runtime&external_run_id=external_1",
        config=config,
    )
    assert graph_response.status == 200
    assert graph_response.payload["graph"]["diagnostics"]["abstentions"] == 1

    packet_response = dispatch_kernel_request(
        "GET",
        "/kernel/failure-attribution-packets?status=review_ready&resource=true",
        config=config,
    )
    assert packet_response.status == 200
    assert packet_response.payload["packets"][0]["kind"] == "FailureAttributionPacket"

    phase_response = dispatch_kernel_request(
        "GET",
        "/kernel/phase-execution-plans?resource=true",
        config=config,
    )
    assert phase_response.status == 200
    assert phase_response.payload["plans"][0]["kind"] == "PhaseExecutionPlan"

    experiment_response = dispatch_kernel_request(
        "GET",
        "/kernel/protocol-experiments?resource=true",
        config=config,
    )
    assert experiment_response.status == 200
    experiment_payload = experiment_response.payload["experiments"][0]
    assert experiment_payload["kind"] == "ProtocolExperiment"
    assert experiment_payload["status"]["reports"][0]["recommended_protocol"] == "coordinator"

    signal_summary = dispatch_kernel_request(
        "GET",
        "/kernel/capability-signals?summary=true",
        config=config,
    )
    assert signal_summary.status == 200
    assert signal_summary.payload["summary"]["counts_by_kind"] == {"abstention": 1}


def test_kernel_service_routes_execution_evidence_into_learning_path(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        org_dir=tmp_path / "org",
        capability_signals_log=tmp_path / "capability_signals.jsonl",
    )

    response = dispatch_kernel_request(
        "POST",
        "/kernel/execution-evidence/route",
        {
            "signal_id": "csig_service_route",
            "signal_kind": "capability_gap",
            "source_ref": "agent_runtime:codex_exec",
            "summary": "Planner abstained because file-edit authority was missing.",
            "owner_role": "role.org_evolver",
            "severity": "blocking",
            "worker_ref": "actor.codex",
            "run_id": "run_service",
            "work_id": "work_service",
            "capability_ref": "capability:file_edit",
            "route_kind": "open_learning_candidate",
            "routed_by": "role.evaluator",
            "route_rationale": "Review future routing before retrying similar work.",
            "counts_as_failure": True,
            "evidence_refs": ["phase_execution_plan:pex_service"],
            "governance_change_target_ref": "org/mandates/org_evolver.md",
            "governance_change_kind": "mandate_change",
            "proposed_by": "role.org_evolver",
        },
        config=config,
    )

    assert response.status == 201
    payload = response.payload
    assert payload["route_packet"]["schema"] == "execution_evidence_route_packet.v1"
    assert payload["resolved_refs"]["signal_ref"] == (
        "capability_signal:csig_service_route"
    )
    assert payload["resolved_refs"]["learning_candidate_ref"].startswith(
        "learning_transition_candidate:ltc_"
    )
    assert payload["resolved_refs"]["proposal_ref"].startswith("governance_change:gcp_")
    assert payload["signal"]["status"] == "routed"
    assert payload["signal"]["recommended_route"] == "open_learning_candidate"
    assert payload["learning_candidate"]["source_kind"] == "capability_signal"
    assert payload["learning_candidate"]["observer_only"] is True
    assert payload["proposal"]["status"] == "blocked"
    assert payload["proposal"]["target_ref"] == "org/mandates/org_evolver.md"
    assert "capability_signal:csig_service_route" in payload["proposal"]["source_refs"]
    assert payload["boundary"] == {
        "approved_governance": False,
        "mutated_files": False,
        "executed_runtime": False,
    }

    signals = dispatch_kernel_request(
        "GET",
        "/kernel/capability-signals",
        config=config,
    )
    assert signals.status == 200
    assert signals.payload["signals"][0]["signal_id"] == "csig_service_route"
    assert signals.payload["signals"][0]["status"] == "routed"

    candidates = dispatch_kernel_request(
        "GET",
        "/kernel/learning-transition-candidates?source=capability",
        config=config,
    )
    assert candidates.status == 200
    assert [
        candidate["candidate_id"]
        for candidate in candidates.payload["candidates"]
    ] == [payload["learning_candidate"]["candidate_id"]]

    proposals = dispatch_kernel_request(
        "GET",
        "/kernel/governance-changes",
        config=config,
    )
    assert proposals.status == 200
    assert [proposal["proposal_id"] for proposal in proposals.payload["proposals"]] == [
        payload["proposal"]["proposal_id"]
    ]


def test_kernel_service_routes_execution_evidence_with_single_outer_lease(
    tmp_path: Path,
) -> None:
    base_config = KernelServiceConfig(
        org_dir=tmp_path / "org",
        capability_signals_log=tmp_path / "capability_signals.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        require_leases=False,
    )
    leased_config = replace(base_config, require_leases=True)
    actor_context = {
        "actor_id": "agent.evaluator",
        "actor_kind": "agent",
        "role_id": "role.evaluator",
    }
    blocked = dispatch_kernel_request(
        "POST",
        "/kernel/execution-evidence/route",
        {
            "signal_id": "csig_execution_lease_guard",
            "signal_kind": "tool_unavailable",
            "source_ref": "agent_runtime:codex_exec",
            "summary": "Route should require the outer execution-evidence lease.",
            "actor_context": actor_context,
        },
        config=leased_config,
    )
    assert blocked.status == 400
    assert "lease" in blocked.payload["error"].lower()

    lease = dispatch_kernel_request(
        "POST",
        "/kernel/leases",
        {
            "resource_ref": "execution_evidence:route",
            "ttl_seconds": 60,
            "actor_context": actor_context,
        },
        config=leased_config,
    )
    assert lease.status == 201
    lease_record = lease.payload["lease"]

    routed = dispatch_kernel_request(
        "POST",
        "/kernel/execution-evidence/route",
        {
            "signal_id": "csig_execution_lease_guard",
            "signal_kind": "tool_unavailable",
            "source_ref": "agent_runtime:codex_exec",
            "summary": "Route should require the outer execution-evidence lease.",
            "route_kind": "open_learning_candidate",
            "route_rationale": "Retry only after runtime availability is reviewed.",
            "lease_id": lease_record["lease_id"],
            "fencing_token": lease_record["fencing_token"],
            "actor_context": actor_context,
        },
        config=leased_config,
    )

    assert routed.status == 201
    assert routed.payload["signal"]["signal_id"] == "csig_execution_lease_guard"
    assert routed.payload["signal"]["status"] == "routed"
    assert routed.payload["learning_candidate"]["source_kind"] == "capability_signal"
    assert routed.payload["boundary"] == {
        "approved_governance": False,
        "mutated_files": False,
        "executed_runtime": False,
    }


def test_kernel_service_records_execution_carriers_through_boundary(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        trace_events_log=tmp_path / "trace_events.jsonl",
        attribution_packets_log=tmp_path / "attribution_packets.jsonl",
        phase_execution_log=tmp_path / "phase_execution.jsonl",
        protocol_experiments_log=tmp_path / "protocol_experiments.jsonl",
        capability_signals_log=tmp_path / "capability_signals.jsonl",
    )

    imported = dispatch_kernel_request(
        "POST",
        "/kernel/multi-agent-trace-events",
        {
            "runtime_name": "service_runtime",
            "external_run_id": "external_service_1",
            "cognitive_run_id": "run_service_1",
            "events": [
                {
                    "event_id": "mate_service_root",
                    "event_kind": "agent_spawned",
                    "agent_id": "agent.root",
                    "owner_role": "role.evaluator",
                },
                {
                    "event_id": "mate_service_worker",
                    "event_kind": "abstention",
                    "agent_id": "agent.worker",
                    "parent_agent_id": "agent.root",
                    "owner_role": "role.executor",
                    "status": "abstained",
                    "summary": "Worker lacked sufficient evidence.",
                },
            ],
        },
        config=config,
    )
    assert imported.status == 201
    assert [event["event_id"] for event in imported.payload["trace_events"]] == [
        "mate_service_root",
        "mate_service_worker",
    ]

    packet = dispatch_kernel_request(
        "POST",
        "/kernel/failure-attribution-packets",
        {
            "runtime_name": "service_runtime",
            "external_run_id": "external_service_1",
            "source_event_ids": ["mate_service_root", "mate_service_worker"],
            "failure_summary": "Evidence gap caused a grounded abstention.",
            "proposed_carrier_kind": "learning_transition",
            "owner_role": "role.evaluator",
            "risk_summary": "Observer-only packet.",
            "rollback_plan": "Discard if review rejects it.",
        },
        config=config,
    )
    assert packet.status == 201
    assert packet.payload["packet"]["status"] == "review_ready"

    phase = dispatch_kernel_request(
        "POST",
        "/kernel/phase-execution-plans",
        {
            "plan_id": "pex_service_1",
            "objective": "Separate planning and verification.",
            "owner_role": "role.executor",
            "total_budget_units": 2.0,
        },
        config=config,
    )
    assert phase.status == 201

    directive = dispatch_kernel_request(
        "POST",
        "/kernel/phase-execution-plans/pex_service_1/directives",
        {
            "phase": "strategy",
            "issued_by": "role.evaluator",
            "directive": "State assumptions before execution.",
        },
        config=config,
    )
    assert directive.status == 201
    assert directive.payload["plan"]["current_phase"] == "strategy"

    feedback = dispatch_kernel_request(
        "POST",
        "/kernel/phase-execution-plans/pex_service_1/verification-feedback",
        {
            "verifier_role": "role.evaluator",
            "verdict": "failed",
            "rationale": "Verification found incomplete evidence.",
            "budget_decay": 0.25,
        },
        config=config,
    )
    assert feedback.status == 201
    assert feedback.payload["plan"]["remaining_budget_units"] == 0.5

    experiment = dispatch_kernel_request(
        "POST",
        "/kernel/protocol-experiments",
        {
            "experiment_id": "pexp_service_1",
            "objective": "Compare routing patterns.",
            "owner_role": "role.evaluator",
            "candidate_protocols": ["sequential", "coordinator"],
            "baseline_protocol": "sequential",
        },
        config=config,
    )
    assert experiment.status == 201

    for protocol, score in (
        ("sequential", 0.71),
        ("sequential", 0.72),
        ("coordinator", 0.82),
        ("coordinator", 0.84),
    ):
        observed = dispatch_kernel_request(
            "POST",
            "/kernel/protocol-experiments/pexp_service_1/observations",
            {
                "protocol": protocol,
                "task_ref": f"task:{protocol}:{score}",
                "quality_score": score,
            },
            config=config,
        )
        assert observed.status == 201

    report = dispatch_kernel_request(
        "POST",
        "/kernel/protocol-experiments/pexp_service_1/reports",
        {
            "proposed_by": "role.evaluator",
            "target_ref": "route_policy:service-fixture",
        },
        config=config,
    )
    assert report.status == 201
    assert report.payload["experiment"]["reports"][0]["recommended_protocol"] == "coordinator"

    signal = dispatch_kernel_request(
        "POST",
        "/kernel/capability-signals",
        {
            "signal_id": "csig_service_1",
            "signal_kind": "abstention",
            "source_ref": "run:run_service_1",
            "summary": "Worker abstained with a capability threshold mismatch.",
            "owner_role": "role.evaluator",
            "recommended_route": "request_evidence",
        },
        config=config,
    )
    assert signal.status == 201
    assert signal.payload["signal"]["status"] == "observed"

    routed = dispatch_kernel_request(
        "POST",
        "/kernel/capability-signals/csig_service_1/route",
        {
            "route_kind": "request_evidence",
            "routed_by": "role.evaluator",
            "rationale": "The worker needs a source receipt before retry.",
            "target_ref": "human_work:evidence-request",
        },
        config=config,
    )
    assert routed.status == 200
    assert routed.payload["signal"]["status"] == "routed"

    closed = dispatch_kernel_request(
        "POST",
        "/kernel/capability-signals/csig_service_1/close",
        {
            "closed_by": "role.evaluator",
            "closure_ref": "human_work:evidence-request",
            "rationale": "Evidence receipt was attached.",
        },
        config=config,
    )
    assert closed.status == 200
    assert closed.payload["signal"]["status"] == "closed"

    projection = dispatch_kernel_request(
        "GET",
        "/kernel/capability-signals?summary=true",
        config=config,
    )
    assert projection.status == 200
    assert projection.payload["summary"]["open_signals"] == 0


def test_kernel_service_projection_only_surface_cannot_write_execution_carriers(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        capability_signals_log=tmp_path / "capability_signals.jsonl",
        surface_write_modes={"orbit": "projection_only"},
    )

    denied = dispatch_kernel_request(
        "POST",
        "/kernel/capability-signals",
        {
            "signal_kind": "abstention",
            "source_ref": "run:blocked",
            "summary": "Projection surface tried to write evidence.",
            "owner_role": "role.evaluator",
            "actor_context": {"surface": "orbit"},
        },
        config=config,
    )

    assert denied.status == 403
    assert "projection-only" in denied.payload["error"]


def test_kernel_service_projects_execution_learning_candidates(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        trace_events_log=tmp_path / "trace_events.jsonl",
        attribution_packets_log=tmp_path / "attribution_packets.jsonl",
        capability_signals_log=tmp_path / "capability_signals.jsonl",
        phase_execution_log=tmp_path / "phase_execution.jsonl",
        protocol_experiments_log=tmp_path / "protocol_experiments.jsonl",
    )

    dispatch_kernel_request(
        "POST",
        "/kernel/multi-agent-trace-events",
        {
            "runtime_name": "learning_candidate_runtime",
            "external_run_id": "candidate_run",
            "events": [
                {
                    "event_id": "mate_candidate_root",
                    "event_kind": "agent_spawned",
                    "agent_id": "agent.root",
                },
                {
                    "event_id": "mate_candidate_verifier",
                    "event_kind": "verifier_verdict",
                    "agent_id": "agent.verifier",
                    "parent_agent_id": "agent.root",
                    "status": "failed",
                },
            ],
        },
        config=config,
    )
    packet = dispatch_kernel_request(
        "POST",
        "/kernel/failure-attribution-packets",
        {
            "runtime_name": "learning_candidate_runtime",
            "external_run_id": "candidate_run",
            "source_event_ids": ["mate_candidate_root", "mate_candidate_verifier"],
            "failure_summary": "Verifier failure exposed a mandate review gap.",
            "proposed_carrier_kind": "learning_transition",
            "proposed_transition_kind": "mandate_review",
            "owner_role": "role.evaluator",
            "risk_summary": "Observer-only candidate.",
            "rollback_plan": "Discard if review rejects it.",
        },
        config=config,
    )
    assert packet.status == 201

    signal = dispatch_kernel_request(
        "POST",
        "/kernel/capability-signals",
        {
            "signal_id": "csig_candidate_open",
            "signal_kind": "evidence_gap",
            "source_ref": "work_item:work_candidate",
            "summary": "A worker abstained because source evidence was missing.",
            "owner_role": "role.evaluator",
            "recommended_route": "request_evidence",
            "evidence_refs": ["trace://missing-source"],
        },
        config=config,
    )
    assert signal.status == 201
    closed_signal = dispatch_kernel_request(
        "POST",
        "/kernel/capability-signals",
        {
            "signal_id": "csig_candidate_closed",
            "signal_kind": "overload",
            "source_ref": "runtime:pool",
            "summary": "Temporary overload was resolved.",
            "owner_role": "role.dispatcher",
        },
        config=config,
    )
    assert closed_signal.status == 201
    closed = dispatch_kernel_request(
        "POST",
        "/kernel/capability-signals/csig_candidate_closed/close",
        {
            "closed_by": "role.dispatcher",
            "closure_ref": "runtime:pool:recovered",
            "rationale": "Capacity recovered.",
        },
        config=config,
    )
    assert closed.status == 200
    phase = dispatch_kernel_request(
        "POST",
        "/kernel/phase-execution-plans",
        {
            "plan_id": "pex_candidate_blocked",
            "objective": "Repair verifier evidence handoff.",
            "owner_role": "role.evaluator",
            "total_budget_units": 1.0,
            "max_attempts": 1,
            "work_id": "work_phase_candidate",
            "metadata": {"proposed_transition_kind": "evidence_gap"},
        },
        config=config,
    )
    assert phase.status == 201
    feedback = dispatch_kernel_request(
        "POST",
        "/kernel/phase-execution-plans/pex_candidate_blocked/verification-feedback",
        {
            "verifier_role": "role.evaluator",
            "verdict": "failed",
            "rationale": "Verifier blocked because evidence refs were missing.",
            "evidence_refs": ["artifact://phase-verification"],
        },
        config=config,
    )
    assert feedback.status == 201
    assert feedback.payload["plan"]["status"] == "blocked"
    experiment = dispatch_kernel_request(
        "POST",
        "/kernel/protocol-experiments",
        {
            "experiment_id": "pexp_candidate_review",
            "objective": "Compare evidence-repair routing patterns.",
            "owner_role": "role.evaluator",
            "candidate_protocols": ["coordinator", "sequential"],
            "baseline_protocol": "coordinator",
        },
        config=config,
    )
    assert experiment.status == 201
    for protocol, score in (
        ("coordinator", 0.55),
        ("sequential", 0.75),
    ):
        observed = dispatch_kernel_request(
            "POST",
            "/kernel/protocol-experiments/pexp_candidate_review/observations",
            {
                "protocol": protocol,
                "task_ref": f"work:{protocol}",
                "quality_score": score,
            },
            config=config,
        )
        assert observed.status == 201
    report = dispatch_kernel_request(
        "POST",
        "/kernel/protocol-experiments/pexp_candidate_review/reports",
        {
            "proposed_by": "role.evaluator",
            "target_ref": "route_policy:evidence-repair",
            "min_observations_per_protocol": 1,
            "min_quality_delta": 0.05,
        },
        config=config,
    )
    assert report.status == 201
    assert report.payload["experiment"]["reports"][0]["status"] == "review_ready"

    candidates = dispatch_kernel_request(
        "GET",
        "/kernel/learning-transition-candidates?source=execution",
        config=config,
    )

    assert candidates.status == 200
    assert candidates.payload["source_counts"]["attribution"] == 1
    assert candidates.payload["source_counts"]["capability"] == 1
    assert candidates.payload["source_counts"]["phase_execution"] == 1
    assert candidates.payload["source_counts"]["protocol_experiment"] == 1
    assert candidates.payload["n_candidates"] == 4
    source_kinds = {candidate["source_kind"] for candidate in candidates.payload["candidates"]}
    assert source_kinds == {
        "multi_agent_failure_attribution",
        "capability_signal",
        "phase_execution_plan",
        "protocol_experiment_report",
    }
    transition_kinds = {candidate["transition_kind"] for candidate in candidates.payload["candidates"]}
    assert transition_kinds == {"mandate_review", "evidence_gap", "route_policy_change"}
    phase_candidates = [
        candidate
        for candidate in candidates.payload["candidates"]
        if candidate["source_kind"] == "phase_execution_plan"
    ]
    assert phase_candidates[0]["object_ref"] == "work_phase_candidate"
    assert "phase_execution_plan:pex_candidate_blocked" in phase_candidates[0]["source_refs"]
    protocol_candidates = [
        candidate
        for candidate in candidates.payload["candidates"]
        if candidate["source_kind"] == "protocol_experiment_report"
    ]
    assert protocol_candidates[0]["object_ref"] == "route_policy:evidence-repair"
    assert "protocol_experiment:pexp_candidate_review" in protocol_candidates[0]["source_refs"]

    with_closed = dispatch_kernel_request(
        "GET",
        "/kernel/learning-transition-candidates?source=capability&include_closed=true",
        config=config,
    )
    assert with_closed.status == 200
    assert with_closed.payload["source_counts"]["capability"] == 2


def test_kernel_service_promotes_learning_candidate_to_governance_proposal(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        org_dir=tmp_path / "org",
        trace_events_log=tmp_path / "trace_events.jsonl",
        attribution_packets_log=tmp_path / "attribution_packets.jsonl",
        capability_signals_log=tmp_path / "capability_signals.jsonl",
    )
    trace = dispatch_kernel_request(
        "POST",
        "/kernel/multi-agent-trace-events",
        {
            "runtime_name": "promotion_runtime",
            "external_run_id": "promotion_run",
            "events": [
                {
                    "event_id": "mate_promotion_root",
                    "event_kind": "agent_spawned",
                    "agent_id": "agent.root",
                },
                {
                    "event_id": "mate_promotion_verifier",
                    "event_kind": "verifier_verdict",
                    "agent_id": "agent.verifier",
                    "parent_agent_id": "agent.root",
                    "status": "failed",
                },
            ],
        },
        config=config,
    )
    assert trace.status == 201
    packet = dispatch_kernel_request(
        "POST",
        "/kernel/failure-attribution-packets",
        {
            "runtime_name": "promotion_runtime",
            "external_run_id": "promotion_run",
            "source_event_ids": ["mate_promotion_root", "mate_promotion_verifier"],
            "failure_summary": "Verifier failures show mandate evidence requirements are too weak.",
            "proposed_carrier_kind": "learning_transition",
            "proposed_transition_kind": "mandate_review",
            "owner_role": "role.evaluator",
            "risk_summary": "Observer-only packet.",
            "rollback_plan": "Discard if review rejects it.",
        },
        config=config,
    )
    assert packet.status == 201
    candidates = dispatch_kernel_request(
        "GET",
        "/kernel/learning-transition-candidates?source=attribution",
        config=config,
    )
    candidate_id = candidates.payload["candidates"][0]["candidate_id"]

    promoted = dispatch_kernel_request(
        "POST",
        f"/kernel/learning-transition-candidates/{candidate_id}/governance-change",
        {
            "source": "attribution",
            "target_ref": "org/mandates/evaluator.md",
            "proposed_by": "role.evaluator",
            "expected_behavior_change": "Evaluator mandate requires source refs before accepting handoffs.",
            "risk_summary": "Narrows verifier acceptance criteria and does not expand authority.",
            "rollback_plan": "Restore the previous evaluator mandate.",
            "invariant_checks": _passing_governance_checks(),
            "metadata": {"review_queue": "governance"},
        },
        config=config,
    )

    assert promoted.status == 201
    proposal = promoted.payload["proposal"]
    assert proposal["status"] == "review_ready"
    assert proposal["change_kind"] == "mandate_change"
    assert proposal["metadata"]["candidate_id"] == candidate_id
    assert "learning_transition_candidate:" + candidate_id in proposal["source_refs"]
    assert any(ref.startswith("multi_agent_attribution:") for ref in proposal["source_refs"])

    listed = dispatch_kernel_request(
        "GET",
        "/kernel/governance-changes?resource=true",
        config=config,
    )
    assert listed.status == 200
    assert listed.payload["proposals"][0]["kind"] == "GovernanceChangeProposal"


def test_kernel_service_candidate_promotion_keeps_evidence_gate(tmp_path: Path) -> None:
    config = KernelServiceConfig(
        org_dir=tmp_path / "org",
        capability_signals_log=tmp_path / "capability_signals.jsonl",
    )
    signal = dispatch_kernel_request(
        "POST",
        "/kernel/capability-signals",
        {
            "signal_id": "csig_promotion_gate",
            "signal_kind": "evidence_gap",
            "source_ref": "work_item:work_promotion_gate",
            "summary": "Missing source evidence should be reviewed before retry.",
            "owner_role": "role.evaluator",
            "recommended_route": "request_evidence",
        },
        config=config,
    )
    assert signal.status == 201
    candidates = dispatch_kernel_request(
        "GET",
        "/kernel/learning-transition-candidates?source=capability",
        config=config,
    )
    candidate_id = candidates.payload["candidates"][0]["candidate_id"]

    promoted = dispatch_kernel_request(
        "POST",
        f"/kernel/learning-transition-candidates/{candidate_id}/governance-change",
        {
            "source": "capability",
            "target_ref": "org/policies/learning.md",
            "proposed_by": "role.evaluator",
        },
        config=config,
    )

    assert promoted.status == 201
    proposal = promoted.payload["proposal"]
    assert proposal["status"] == "blocked"
    assert proposal["evidence_sufficiency"]["status"] == "fail"


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


def test_kernel_service_auth_provider_pins_governance_proposer(tmp_path: Path):
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
        org_dir=tmp_path / "org",
        transition_log=tmp_path / "transitions.jsonl",
        identity_provider=provider,
    )

    created = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes",
        {
            "change_kind": "mandate_change",
            "title": "Clarify review handoff",
            "proposed_by": "agent.spoof",
            "target_ref": "org/mandates/reviewer.md",
            "rationale": "Review handoff should be explicit.",
            "source_refs": ["work:review-1"],
            "expected_behavior_change": "Reviewer escalates ambiguous authority.",
            "risk_summary": "Narrows authority; no new capability grant.",
            "rollback_plan": "Restore previous mandate from git.",
            "invariant_checks": _passing_governance_checks(),
        },
        config=config,
        headers={"Authorization": "Bearer secret"},
    )

    assert created.status == 201
    assert created.payload["proposal"]["proposed_by"] == "human.alice"


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
            "worker_roles": ["role.support_agent", "role.support_reviewer"],
            "worker_role_classes": {
                "role.support_agent": "agent",
                "role.support_reviewer": "governance",
            },
            "worker_role_archetypes": {
                "role.support_agent": "fungible_agent_worker",
                "role.support_reviewer": "independent_reviewer",
            },
            "tenant_id": "tenant-a",
        },
        config=config,
    )
    assert defined.status == 201
    assert defined.payload["operating_unit"]["worker_role_classes"] == {
        "role.support_agent": "agent",
        "role.support_reviewer": "governance",
    }
    assert defined.payload["operating_unit"]["worker_role_archetypes"] == {
        "role.support_agent": "fungible_agent_worker",
        "role.support_reviewer": "independent_reviewer",
    }

    units = dispatch_kernel_request(
        "GET", "/kernel/operating-units?tenant_id=tenant-a", config=config
    )
    assert units.status == 200
    assert [unit["unit_id"] for unit in units.payload["operating_units"]] == ["support_desk"]

    other_tenant_units = dispatch_kernel_request(
        "GET", "/kernel/operating-units?tenant_id=tenant-b", config=config
    )
    assert other_tenant_units.status == 200
    assert other_tenant_units.payload["operating_units"] == []

    unit_resource = dispatch_kernel_request(
        "GET", "/kernel/operating-units?resource=true", config=config
    )
    assert unit_resource.status == 200
    assert unit_resource.payload["operating_units"][0]["kind"] == "OperatingUnit"
    assert (
        unit_resource.payload["operating_units"][0]["metadata"]["resource_id"]
        == "support_desk"
    )

    fetched_unit = dispatch_kernel_request(
        "GET", "/kernel/operating-units/support_desk", config=config
    )
    assert fetched_unit.status == 200
    assert fetched_unit.payload["operating_unit"]["tenant_id"] == "tenant-a"

    fetched_unit_resource = dispatch_kernel_request(
        "GET", "/kernel/operating-units/support_desk?resource=true", config=config
    )
    assert fetched_unit_resource.status == 200
    assert fetched_unit_resource.payload["operating_unit"]["kind"] == "OperatingUnit"

    missing_unit = dispatch_kernel_request(
        "GET", "/kernel/operating-units/missing_unit", config=config
    )
    assert missing_unit.status == 404

    enqueued = dispatch_kernel_request(
        "POST",
        "/kernel/work-items",
        {"unit_id": "support_desk", "kind": "triage_ticket", "payload": {"ticket": "T-1"}},
        config=config,
    )
    assert enqueued.status == 201
    work_id = enqueued.payload["work_item"]["work_id"]

    queued = dispatch_kernel_request(
        "GET", "/kernel/work-items?unit_id=support_desk&status=queued", config=config
    )
    assert queued.status == 200
    assert [item["work_id"] for item in queued.payload["work_items"]] == [work_id]

    queued_resources = dispatch_kernel_request(
        "GET",
        "/kernel/work-items?unit_id=support_desk&status=queued&resource=true",
        config=config,
    )
    assert queued_resources.status == 200
    assert queued_resources.payload["work_items"][0]["kind"] == "WorkItem"
    assert (
        queued_resources.payload["work_items"][0]["metadata"]["resource_id"]
        == work_id
    )

    fetched = dispatch_kernel_request("GET", f"/kernel/work-items/{work_id}", config=config)
    assert fetched.status == 200
    assert fetched.payload["work_item"]["payload"] == {"ticket": "T-1"}

    claimed = dispatch_kernel_request(
        "POST",
        "/kernel/work-items/claim-next",
        {
            "unit_id": "support_desk",
            "actor": "actor.agent_1",
            "role_id": "role.support_agent",
        },
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

    done = dispatch_kernel_request(
        "GET", "/kernel/work-items?unit_id=support_desk&status=done", config=config
    )
    assert done.status == 200
    assert [item["work_id"] for item in done.payload["work_items"]] == [work_id]

    done_resource = dispatch_kernel_request(
        "GET", f"/kernel/work-items/{work_id}?resource=true", config=config
    )
    assert done_resource.status == 200
    assert done_resource.payload["work_item"]["kind"] == "WorkItem"
    assert done_resource.payload["work_item"]["status"]["status"] == "done"

    missing = dispatch_kernel_request(
        "GET", "/kernel/work-items/work_missing", config=config
    )
    assert missing.status == 404

    dashboard = dispatch_kernel_request(
        "GET", "/kernel/operating-unit-dashboard", config=config
    )
    assert dashboard.status == 200
    unit = dashboard.payload["dashboard"]["units"][0]
    assert unit["unit_id"] == "support_desk"
    assert unit["done"] == 1


def test_kernel_service_routes_run_checkpoint_lifecycle(tmp_path: Path):
    config = KernelServiceConfig(
        transition_log=tmp_path / "transitions.jsonl",
        actor_identity_log=tmp_path / "actors.jsonl",
        leases_log=tmp_path / "leases.jsonl",
    )

    started = dispatch_kernel_request(
        "POST",
        "/kernel/runs",
        {
            "owner_role": "role.operator",
            "objective": "sync external state",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "idempotency_key": "sync:external-state",
        },
        config=config,
    )
    assert started.status == 201
    run_id = started.payload["run"]["run_id"]

    repeated = dispatch_kernel_request(
        "POST",
        "/kernel/runs",
        {
            "owner_role": "role.operator",
            "objective": "duplicate start",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "idempotency_key": "sync:external-state",
        },
        config=config,
    )
    assert repeated.status == 201
    assert repeated.payload["run"]["run_id"] == run_id

    fetched = dispatch_kernel_request("GET", f"/kernel/runs/{run_id}", config=config)
    assert fetched.status == 200
    assert fetched.payload["run"]["objective"] == "sync external state"

    checkpoint = dispatch_kernel_request(
        "POST",
        f"/kernel/runs/{run_id}/checkpoints",
        {
            "actor": "role.operator",
            "step_id": "fetch",
            "status": "completed",
            "summary": "fetched source state",
            "side_effect_key": "fetch:source",
        },
        config=config,
    )
    assert checkpoint.status == 201

    skipped = dispatch_kernel_request(
        "POST",
        f"/kernel/runs/{run_id}/checkpoints",
        {
            "actor": "role.operator",
            "step_id": "fetch_retry",
            "status": "completed",
            "summary": "retry saw same side effect",
            "side_effect_key": "fetch:source",
        },
        config=config,
    )
    assert skipped.status == 201

    resume = dispatch_kernel_request("GET", f"/kernel/runs/{run_id}/resume", config=config)
    assert resume.status == 200
    assert resume.payload["summary"]["completed_step_ids"] == ["fetch"]
    assert resume.payload["summary"]["checkpoints"][-1]["status"] == "skipped"

    listed = dispatch_kernel_request(
        "GET", "/kernel/runs?state=running&tenant_id=tenant-a", config=config
    )
    assert listed.status == 200
    assert [run["run_id"] for run in listed.payload["runs"]] == [run_id]

    completed = dispatch_kernel_request(
        "POST",
        f"/kernel/runs/{run_id}/state",
        {"actor": "role.operator", "state": "completed"},
        config=config,
    )
    assert completed.status == 200

    terminal_checkpoint = dispatch_kernel_request(
        "POST",
        f"/kernel/runs/{run_id}/checkpoints",
        {
            "actor": "role.operator",
            "step_id": "late",
            "status": "completed",
            "summary": "too late",
        },
        config=config,
    )
    assert terminal_checkpoint.status == 400
    assert "terminal run" in terminal_checkpoint.payload["error"]

    missing = dispatch_kernel_request("GET", "/kernel/runs/run_missing", config=config)
    assert missing.status == 404


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
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
        resource_allocation_log=tmp_path / "resource_allocation.jsonl",
        residual_rights_log=tmp_path / "residual_rights.jsonl",
        residual_decisions_log=tmp_path / "residual_decisions.jsonl",
        kernel_events_log=tmp_path / "kernel_events.jsonl",
    )

    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Require reviewer handoff when a similar queue stalls.",
        future_application_cue="similar queue stalls",
        approved_by="role.owner",
        approval_ref="decision:learning-42",
        source_carrier_refs=["multi_agent_attribution:packet_42"],
        owner_role="role.manager",
        tenant_id="tenant-a",
        metadata={"tags": ["trace_attribution"]},
        log_path=config.learning_events_log,
    )
    listed = dispatch_kernel_request(
        "GET", "/kernel/learning-events?resource=true", config=config
    )
    assert listed.status == 200
    assert listed.payload["learning_events"][0]["kind"] == "LearningEvent"

    replayed = dispatch_kernel_request(
        "GET",
        "/kernel/learning-events/replay?role=role.manager&tenant_id=tenant-a&cue=queue+stalls",
        config=config,
    )
    assert replayed.status == 200
    assert [row["learning_event_id"] for row in replayed.payload["learning_events"]] == [
        event.learning_event_id
    ]
    replayed_by_ref = dispatch_kernel_request(
        "GET",
        "/kernel/learning-events/replay?tenant_id=tenant-a&source_ref=multi_agent_attribution:packet_42",
        config=config,
    )
    assert replayed_by_ref.status == 200
    assert [
        row["learning_event_id"] for row in replayed_by_ref.payload["learning_events"]
    ] == [event.learning_event_id]
    replayed_by_tag = dispatch_kernel_request(
        "GET",
        "/kernel/learning-events/replay?tenant_id=tenant-a&tag=trace_attribution",
        config=config,
    )
    assert replayed_by_tag.status == 200
    assert [
        row["learning_event_id"] for row in replayed_by_tag.payload["learning_events"]
    ] == [event.learning_event_id]
    other_tenant = dispatch_kernel_request(
        "GET",
        "/kernel/learning-events/replay?role=role.manager&tenant_id=tenant-b&cue=queue+stalls",
        config=config,
    )
    assert other_tenant.status == 200
    assert other_tenant.payload["learning_events"] == []

    encounter = dispatch_kernel_request(
        "POST",
        "/kernel/learning-event-encounters",
        {
            "learning_event_id": event.learning_event_id,
            "role": "role.manager",
            "cue": "A similar queue stalls during triage.",
            "outcome": "applied",
            "work_ref": "work:triage-1",
            "tenant_id": "tenant-a",
        },
        config=config,
    )
    assert encounter.status == 201
    missing_encounter = dispatch_kernel_request(
        "POST",
        "/kernel/learning-event-encounters",
        {
            "learning_event_id": "learn_missing",
            "role": "role.manager",
            "cue": "A similar queue stalls during triage.",
        },
        config=config,
    )
    assert missing_encounter.status == 404
    learning_summary = dispatch_kernel_request(
        "GET", "/kernel/learning-events/summary?tenant_id=tenant-a", config=config
    )
    assert learning_summary.status == 200
    assert learning_summary.payload["summary"]["active"] == 1
    assert learning_summary.payload["summary"]["encounter_counts"]["applied"] == 1

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
    outcome_resources = dispatch_kernel_request(
        "GET", "/kernel/outcome-links?resource=true", config=config
    )
    assert outcome_resources.status == 200
    assert outcome_resources.payload["outcome_links"][0]["kind"] == "OutcomeLink"
    assert (
        outcome_resources.payload["outcome_links"][0]["metadata"]["resource_id"]
        == link_id
    )

    # Failed prediction: schedule a reversal-candidate routine review from the
    # outcome-link verdict, without auto-reverting the governed change.
    predicted = dispatch_kernel_request(
        "POST",
        "/kernel/outcome-links",
        {
            "change_ref": "governance_change:gcp_predicted",
            "change_kind": "governance_change",
            "metric_name": "open_gaps",
            "metric_unit": "count",
            "direction": "lower_is_better",
            "created_by": "actor.analyst",
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "metadata": {
                "predicted_effect": {
                    "metric_name": "open_gaps",
                    "metric_unit": "count",
                    "direction": "lower_is_better",
                    "threshold": 1,
                    "review_horizon": "next_routine_review",
                }
            },
        },
        config=config,
    )
    assert predicted.status == 201
    predicted_id = predicted.payload["outcome_link"]["outcome_link_id"]
    for kind, value in (("baseline", 3.0), ("post", 3.0)):
        snap = dispatch_kernel_request(
            "POST",
            f"/kernel/outcome-links/{predicted_id}/snapshots",
            {"kind": kind, "value": value, "captured_by": "actor.analyst"},
            config=config,
        )
        assert snap.status == 200
    failed_verdict = dispatch_kernel_request(
        "POST",
        f"/kernel/outcome-links/{predicted_id}/verdict",
        {
            "verdict": "no_change",
            "rationale": "open gaps did not decrease after the mutation",
        },
        config=config,
    )
    assert failed_verdict.status == 200
    assert failed_verdict.payload["outcome_link"]["metadata"]["prediction_review"][
        "status"
    ] == "prediction_failed"

    reversal_review = dispatch_kernel_request(
        "POST",
        f"/kernel/outcome-links/{predicted_id}/reversal-review",
        {
            "review_due_utc": "2030-01-02T00:00:00+00:00",
            "scheduled_by": "actor.manager",
            "metadata": {"source": "kernel-service-test"},
        },
        config=config,
    )
    assert reversal_review.status == 201
    review = reversal_review.payload["routine_review"]
    assert review["routine_ref"] == "governance_change:gcp_predicted"
    assert review["review_cadence"] == "prediction_failure"
    assert review["tenant_id"] == "tenant-a"
    assert review["project_id"] == "project-a"
    assert review["metadata"]["reversal_candidate"] is True
    assert review["metadata"]["source_outcome_link_id"] == predicted_id
    assert "governance_change:gcp_predicted" in review["metadata"]["evidence_refs"]

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
    review_id = scheduled.payload["routine_review"]["review_id"]
    due = dispatch_kernel_request("GET", "/kernel/routine-reviews/due", config=config)
    assert due.status == 200
    assert len(due.payload["due_reviews"]) == 1
    review_resources = dispatch_kernel_request(
        "GET", "/kernel/routine-reviews?resource=true", config=config
    )
    assert review_resources.status == 200
    review_resource_by_id = {
        row["metadata"]["resource_id"]: row
        for row in review_resources.payload["routine_reviews"]
    }
    assert review_resource_by_id[review_id]["kind"] == "RoutineReview"
    assert (
        review_resource_by_id[review_id]["metadata"]["resource_id"]
        == review_id
    )
    due_resources = dispatch_kernel_request(
        "GET", "/kernel/routine-reviews/due?resource=true", config=config
    )
    assert due_resources.status == 200
    assert due_resources.payload["due_reviews"][0]["status"]["overdue"] is True

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
