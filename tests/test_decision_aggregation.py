from __future__ import annotations

from pathlib import Path

import pytest

from cognitive_firm.orchestration.decision_aggregation import (
    compute_decision_aggregation_case,
    decision_aggregation_case_resource,
    get_decision_procedure_profile,
    list_decision_aggregation_cases,
    open_decision_aggregation_case_from_profile,
    open_decision_aggregation_case,
    record_decision_position,
    resolve_decision_procedure_profile,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource


def _open_case(log_path: Path, **overrides):
    base = dict(
        subject_ref="governance_change:gcp_123",
        decision_class="structural_change",
        scope_kind="project",
        scope_ref="proj.demo",
        procedure_kind="quorum_majority",
        opened_by="role.principal",
        eligibility_basis="project charter review policy",
        eligible_roles=["role.principal", "role.evaluator"],
        quorum=2,
        log_path=log_path,
    )
    base.update(overrides)
    return open_decision_aggregation_case(**base)


def test_quorum_majority_records_positions_and_computes_approval(tmp_path: Path):
    log_path = tmp_path / "decision_aggregation.jsonl"
    case = _open_case(log_path)

    record_decision_position(
        case.case_id,
        actor_id="human.principal",
        role_id="role.principal",
        position="approve",
        rationale="principal approves the bounded change",
        evidence_refs=["governance_change:gcp_123"],
        log_path=log_path,
    )
    record_decision_position(
        case.case_id,
        actor_id="agent.evaluator",
        role_id="role.evaluator",
        position="approve",
        rationale="evaluator found no authority expansion",
        evidence_refs=["a2a_message:msg_123"],
        log_path=log_path,
    )

    computed = compute_decision_aggregation_case(case.case_id, log_path=log_path)

    assert computed.status == "computed"
    assert computed.result is not None
    assert computed.result.recommendation == "approve"
    assert computed.result.quorum_met is True
    assert computed.result.approvals == 2
    assert computed.result.rejections == 0
    assert computed.result.evidence_refs == [
        "a2a_message:msg_123",
        "governance_change:gcp_123",
    ]


def test_quorum_majority_escalates_when_quorum_missing(tmp_path: Path):
    log_path = tmp_path / "decision_aggregation.jsonl"
    case = _open_case(log_path)
    record_decision_position(
        case.case_id,
        actor_id="human.principal",
        role_id="role.principal",
        position="approve",
        rationale="principal position only",
        log_path=log_path,
    )

    computed = compute_decision_aggregation_case(case.case_id, log_path=log_path)

    assert computed.status == "escalated"
    assert computed.result is not None
    assert computed.result.recommendation == "escalate"
    assert computed.result.quorum_met is False


def test_veto_rejects_even_with_majority_approval(tmp_path: Path):
    log_path = tmp_path / "decision_aggregation.jsonl"
    case = _open_case(
        log_path,
        procedure_kind="veto",
        eligible_roles=["role.principal", "role.evaluator", "role.risk_guardian"],
        quorum=2,
    )
    record_decision_position(
        case.case_id,
        actor_id="human.principal",
        role_id="role.principal",
        position="approve",
        rationale="principal approves",
        log_path=log_path,
    )
    record_decision_position(
        case.case_id,
        actor_id="agent.evaluator",
        role_id="role.evaluator",
        position="approve",
        rationale="evaluator approves",
        log_path=log_path,
    )
    record_decision_position(
        case.case_id,
        actor_id="agent.risk_guardian",
        role_id="role.risk_guardian",
        position="veto",
        rationale="risk guardian found missing rollback evidence",
        log_path=log_path,
    )

    computed = compute_decision_aggregation_case(case.case_id, log_path=log_path)

    assert computed.status == "computed"
    assert computed.result is not None
    assert computed.result.recommendation == "reject"
    assert computed.result.vetoes == 1


def test_single_authority_requires_exactly_one_non_abstaining_position(tmp_path: Path):
    log_path = tmp_path / "decision_aggregation.jsonl"
    case = _open_case(
        log_path,
        procedure_kind="single_authority",
        eligible_roles=["role.principal"],
        quorum=1,
    )
    record_decision_position(
        case.case_id,
        actor_id="human.principal",
        role_id="role.principal",
        position="abstain",
        rationale="principal needs more evidence",
        log_path=log_path,
    )

    computed = compute_decision_aggregation_case(case.case_id, log_path=log_path)

    assert computed.status == "escalated"
    assert computed.result is not None
    assert computed.result.recommendation == "escalate"
    assert computed.result.abstentions == 1


def test_recusal_is_visible_and_does_not_satisfy_quorum(tmp_path: Path):
    log_path = tmp_path / "decision_aggregation.jsonl"
    case = _open_case(log_path)
    record_decision_position(
        case.case_id,
        actor_id="human.principal",
        role_id="role.principal",
        position="approve",
        rationale="principal approves",
        log_path=log_path,
    )
    record_decision_position(
        case.case_id,
        actor_id="agent.evaluator",
        role_id="role.evaluator",
        position="recuse",
        rationale="evaluator generated the candidate evidence and should not count toward quorum",
        log_path=log_path,
    )

    computed = compute_decision_aggregation_case(case.case_id, log_path=log_path)

    assert computed.status == "escalated"
    assert computed.result is not None
    assert computed.result.recommendation == "escalate"
    assert computed.result.approvals == 1
    assert computed.result.recusals == 1
    assert computed.result.quorum_met is False


def test_duplicate_or_ineligible_position_is_rejected(tmp_path: Path):
    log_path = tmp_path / "decision_aggregation.jsonl"
    case = _open_case(log_path)
    record_decision_position(
        case.case_id,
        actor_id="human.principal",
        role_id="role.principal",
        position="approve",
        rationale="principal approves",
        log_path=log_path,
    )

    with pytest.raises(ValueError, match="already recorded"):
        record_decision_position(
            case.case_id,
            actor_id="human.principal",
            role_id="role.principal",
            position="reject",
            rationale="changed mind without reopening",
            log_path=log_path,
        )
    with pytest.raises(PermissionError, match="role is not eligible"):
        record_decision_position(
            case.case_id,
            actor_id="agent.random",
            role_id="role.random",
            position="approve",
            rationale="not eligible",
            log_path=log_path,
        )


def test_decision_aggregation_case_projects_to_resource(tmp_path: Path):
    log_path = tmp_path / "decision_aggregation.jsonl"
    case = _open_case(log_path, downstream_ref="governance_change:gcp_123")
    computed = compute_decision_aggregation_case(case.case_id, log_path=log_path)

    payload = decision_aggregation_case_resource(computed).as_dict()

    assert validate_resource(payload) == []
    assert payload["kind"] == "DecisionAggregationCase"
    assert payload["metadata"]["labels"]["procedure_kind"] == "quorum_majority"
    assert payload["metadata"]["labels"]["status"] == "escalated"
    assert payload["metadata"]["labels"]["recommendation"] == "escalate"
    assert payload["spec"]["subject_ref"] == "governance_change:gcp_123"
    assert payload["spec"]["downstream_ref"] == "governance_change:gcp_123"
    assert {"rel": "subject", "href": "governance_change:gcp_123"} in payload["links"]
    assert {"rel": "downstream", "href": "governance_change:gcp_123"} in payload["links"]


def test_list_filters_by_status_and_procedure(tmp_path: Path):
    log_path = tmp_path / "decision_aggregation.jsonl"
    first = _open_case(log_path)
    second = _open_case(
        log_path,
        subject_ref="governance_change:gcp_456",
        procedure_kind="veto",
        eligible_roles=["role.principal"],
    )
    compute_decision_aggregation_case(first.case_id, log_path=log_path)

    assert [case.case_id for case in list_decision_aggregation_cases(status="escalated", log_path=log_path)] == [
        first.case_id
    ]
    assert [
        case.case_id
        for case in list_decision_aggregation_cases(
            procedure_kind="veto",
            log_path=log_path,
        )
    ] == [second.case_id]


def test_procedure_profile_resolves_majority_quorum_from_eligible_snapshot():
    resolved = resolve_decision_procedure_profile(
        "majority",
        eligible_actors=["human.a", "human.b", "human.c"],
    )

    assert resolved["procedure_kind"] == "quorum_majority"
    assert resolved["quorum"] == 2
    assert resolved["metadata"]["procedure_profile"] == "majority"


def test_unknown_procedure_profile_fails_closed():
    with pytest.raises(ValueError, match="invalid procedure_profile"):
        get_decision_procedure_profile("lottery_box")


def test_unanimity_profile_requires_all_eligible_approvals(tmp_path: Path):
    log_path = tmp_path / "decision_aggregation.jsonl"
    case = open_decision_aggregation_case_from_profile(
        procedure_profile="unanimity",
        subject_ref="governance_change:gcp_789",
        decision_class="mandate_change",
        scope_kind="project",
        scope_ref="proj.demo",
        opened_by="role.principal",
        eligibility_basis="charter tier-1 amendment rule",
        eligible_actors=["human.principal", "agent.evaluator", "agent.risk"],
        log_path=log_path,
    )

    assert case.procedure_kind == "unanimity"
    assert case.quorum == 3
    assert case.metadata["procedure_profile"] == "unanimity"

    for actor_id, role_id in (
        ("human.principal", "role.principal"),
        ("agent.evaluator", "role.evaluator"),
        ("agent.risk", "role.risk_guardian"),
    ):
        record_decision_position(
            case.case_id,
            actor_id=actor_id,
            role_id=role_id,
            position="approve",
            rationale=f"{actor_id} approves",
            log_path=log_path,
        )

    computed = compute_decision_aggregation_case(case.case_id, log_path=log_path)

    assert computed.status == "computed"
    assert computed.result is not None
    assert computed.result.recommendation == "approve"
    assert computed.result.rationale == "all eligible positions approved"


def test_unanimity_rejects_on_any_rejection(tmp_path: Path):
    log_path = tmp_path / "decision_aggregation.jsonl"
    case = open_decision_aggregation_case_from_profile(
        procedure_profile="unanimity",
        subject_ref="governance_change:gcp_790",
        decision_class="mandate_change",
        scope_kind="project",
        scope_ref="proj.demo",
        opened_by="role.principal",
        eligibility_basis="charter tier-1 amendment rule",
        eligible_actors=["human.principal", "agent.evaluator", "agent.risk"],
        log_path=log_path,
    )

    record_decision_position(
        case.case_id,
        actor_id="human.principal",
        role_id="role.principal",
        position="approve",
        rationale="principal approves",
        log_path=log_path,
    )
    record_decision_position(
        case.case_id,
        actor_id="agent.evaluator",
        role_id="role.evaluator",
        position="approve",
        rationale="evaluator approves",
        log_path=log_path,
    )
    record_decision_position(
        case.case_id,
        actor_id="agent.risk",
        role_id="role.risk_guardian",
        position="reject",
        rationale="risk evidence is incomplete",
        log_path=log_path,
    )

    computed = compute_decision_aggregation_case(case.case_id, log_path=log_path)

    assert computed.status == "computed"
    assert computed.result is not None
    assert computed.result.recommendation == "reject"
    assert computed.result.rationale == "eligible rejection recorded under unanimity"
