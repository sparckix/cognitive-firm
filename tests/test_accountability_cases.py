from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.accountability_cases import (  # noqa: E402
    create_accountability_case,
    list_accountability_cases,
    update_accountability_case_status,
)


def test_create_and_list_accountability_case(tmp_path: Path):
    log = tmp_path / "accountability_cases.jsonl"
    case = create_accountability_case(
        trigger_ref="damage_signal/dmg_1",
        accountable_role="role.manager",
        responsible_actor="role.engineer",
        decision_right_basis="mandate",
        authority_envelope_ref="org/mandates/engineer_mandate.md",
        risk_tier="high",
        recourse_path="rollback",
        review_sla="PT24H",
        tenant_id="tenant_a",
        project_id="project_a",
        externality_tags=["customer_impact"],
        operator_burden="medium",
        rationale="External side effect needs accountable closure.",
        log_path=log,
    )

    rows = list_accountability_cases(log_path=log)
    assert rows == [case]
    assert case.case_id.startswith("acct_")
    assert case.status == "open"
    assert case.risk_tier == "high"


def test_filter_accountability_cases(tmp_path: Path):
    log = tmp_path / "accountability_cases.jsonl"
    create_accountability_case(
        trigger_ref="run/run_1",
        accountable_role="role.manager",
        responsible_actor="runtime:codex",
        decision_right_basis="gate",
        authority_envelope_ref="gate/gate_1",
        risk_tier="medium",
        recourse_path="reopen",
        tenant_id="tenant_a",
        log_path=log,
    )
    create_accountability_case(
        trigger_ref="action_impact/act_1",
        accountable_role="role.reviewer",
        responsible_actor="role.engineer",
        decision_right_basis="tenant_rule",
        authority_envelope_ref="tenant/policy/action-impact.md",
        risk_tier="low",
        recourse_path="none",
        tenant_id="tenant_b",
        log_path=log,
    )

    assert len(list_accountability_cases(accountable_role="role.manager", log_path=log)) == 1
    assert len(list_accountability_cases(tenant_id="tenant_b", log_path=log)) == 1
    assert len(list_accountability_cases(risk_tier="low", log_path=log)) == 1


def test_accountability_case_status_lifecycle(tmp_path: Path):
    log = tmp_path / "accountability_cases.jsonl"
    case = create_accountability_case(
        trigger_ref="negative_externality/action_1",
        accountable_role="role.manager",
        responsible_actor="role.researcher",
        decision_right_basis="mandate",
        authority_envelope_ref="org/mandates/researcher_mandate.md",
        risk_tier="medium",
        recourse_path="escalate",
        log_path=log,
    )

    reviewed = update_accountability_case_status(case.case_id, "under_review", log_path=log)
    assert reviewed.status == "under_review"
    remediated = update_accountability_case_status(
        case.case_id,
        "remediated",
        closure_evidence_refs=["org/actions/remediation.md"],
        log_path=log,
    )
    assert remediated.status == "remediated"
    closed = update_accountability_case_status(
        case.case_id,
        "closed",
        closure_evidence_refs=["org/reviews/closure.md"],
        log_path=log,
    )
    assert closed.status == "closed"
    assert closed.closure_evidence_refs == ["org/actions/remediation.md", "org/reviews/closure.md"]


def test_accepted_risk_requires_residual_risk_owner(tmp_path: Path):
    log = tmp_path / "accountability_cases.jsonl"
    case = create_accountability_case(
        trigger_ref="forecast/contract_1",
        accountable_role="role.manager",
        responsible_actor="role.manager",
        decision_right_basis="principal_directive",
        authority_envelope_ref="directive/dir_1",
        risk_tier="high",
        recourse_path="external_review",
        log_path=log,
    )

    with pytest.raises(ValueError, match="accepted_risk requires"):
        update_accountability_case_status(case.case_id, "accepted_risk", log_path=log)

    accepted = update_accountability_case_status(
        case.case_id,
        "accepted_risk",
        residual_risk_accepted_by="principal",
        log_path=log,
    )
    assert accepted.status == "accepted_risk"
    assert accepted.residual_risk_accepted_by == "principal"


def test_invalid_accountability_case_fields_fail(tmp_path: Path):
    log = tmp_path / "accountability_cases.jsonl"
    with pytest.raises(ValueError):
        create_accountability_case(
            trigger_ref="x",
            accountable_role="role.manager",
            responsible_actor="role.engineer",
            decision_right_basis="mandate",
            authority_envelope_ref="org/mandates/engineer_mandate.md",
            risk_tier="catastrophic",
            recourse_path="rollback",
            log_path=log,
        )
