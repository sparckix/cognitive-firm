from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.accountability_cases import (  # noqa: E402
    accountability_case_resource,
    build_damage_signal_accountability_case_request,
    create_accountability_case,
    list_accountability_cases,
    main as accountability_cases_main,
    update_accountability_case_status,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402
from cognitive_firm.signals.damage import DamageSignal  # noqa: E402


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


def test_accountability_case_projects_to_resource_envelope(tmp_path: Path):
    log = tmp_path / "accountability_cases.jsonl"
    case = create_accountability_case(
        trigger_ref="run:run_123",
        accountable_role="role.manager",
        responsible_actor="human.alice",
        decision_right_basis="mandate",
        authority_envelope_ref="org/mandates/manager_mandate.md",
        risk_tier="irreversible",
        recourse_path="external_review",
        review_sla="PT24H",
        tenant_id="tenant-a",
        project_id="project-a",
        due_at_utc="2026-06-11T00:00:00+00:00",
        externality_tags=["customer_impact"],
        operator_burden="high",
        rationale="Residual customer-facing risk needs closure.",
        metadata={"cognitive_run_id": "run_123"},
        log_path=log,
    )

    resource = accountability_case_resource(case).as_dict()

    assert validate_resource(resource) == []
    assert resource["kind"] == "AccountabilityCase"
    assert resource["metadata"]["name"] == case.case_id
    assert resource["metadata"]["tenant_id"] == "tenant-a"
    assert resource["metadata"]["project_id"] == "project-a"
    assert resource["metadata"]["annotations"]["cognitive_run_id"] == "run_123"
    assert resource["spec"]["trigger_ref"] == "run:run_123"
    assert resource["spec"]["accountable_role"] == "role.manager"
    assert resource["spec"]["decision_right_basis"] == "mandate"
    assert resource["spec"]["risk_tier"] == "irreversible"
    assert resource["spec"]["recourse_path"] == "external_review"
    assert resource["spec"]["externality_tags"] == ["customer_impact"]
    assert resource["status"]["status"] == "open"
    assert {"rel": "trigger", "href": "run:run_123"} in resource["links"]
    assert {"rel": "responsible_actor", "href": "human.alice"} in resource["links"]
    assert {
        "rel": "authority_envelope",
        "href": "org/mandates/manager_mandate.md",
    } in resource["links"]


def test_accountability_case_resource_reflects_closure(tmp_path: Path):
    log = tmp_path / "accountability_cases.jsonl"
    case = create_accountability_case(
        trigger_ref="damage_signal:dmg_1",
        accountable_role="role.manager",
        responsible_actor="role.engineer",
        decision_right_basis="tenant_rule",
        authority_envelope_ref="tenant/policy.md",
        risk_tier="high",
        recourse_path="rollback",
        log_path=log,
    )
    closed = update_accountability_case_status(
        case.case_id,
        "closed",
        closure_evidence_refs=["artifact://rollback-report"],
        log_path=log,
    )

    resource = accountability_case_resource(closed).as_dict()

    assert validate_resource(resource) == []
    assert resource["status"]["status"] == "closed"
    assert resource["status"]["closure_evidence_refs"] == ["artifact://rollback-report"]
    assert {
        "rel": "closure_evidence",
        "href": "artifact://rollback-report",
    } in resource["links"]


def test_accountability_case_cli_can_render_resource_envelopes(tmp_path: Path, capsys):
    log = tmp_path / "accountability_cases.jsonl"
    case = create_accountability_case(
        trigger_ref="action_impact:act_1",
        accountable_role="role.manager",
        responsible_actor="role.agent",
        decision_right_basis="policy",
        authority_envelope_ref="policy://action-impact",
        risk_tier="medium",
        recourse_path="reopen",
        log_path=log,
    )

    rc = accountability_cases_main(["list", "--log-path", str(log), "--resource"])
    payloads = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]

    assert rc == 0
    assert len(payloads) == 1
    assert payloads[0]["kind"] == "AccountabilityCase"
    assert payloads[0]["metadata"]["name"] == case.case_id
    assert validate_resource(payloads[0]) == []


def test_damage_signal_builds_accountability_case_request(tmp_path: Path):
    log = tmp_path / "accountability_cases.jsonl"
    request = build_damage_signal_accountability_case_request(
        {
            "timestamp_utc": "2026-06-12T20:30:00+00:00",
            "source": "runtime:codex",
            "kind": "mandate_hash_mismatch",
            "detail": "Mandate changed while the role session was active.",
            "session_id": "sess_1",
            "severity": "critical",
        },
        accountable_role="role.manager",
        authority_envelope_ref="org/mandates/manager_mandate.md",
        tenant_id="tenant-a",
        project_id="project-a",
        case_id="acct_damage_1",
    )

    assert request == {
        "trigger_ref": "damage_signal:mandate_hash_mismatch:6bd58dfcd320",
        "accountable_role": "role.manager",
        "responsible_actor": "runtime:codex",
        "decision_right_basis": "tenant_rule",
        "authority_envelope_ref": "org/mandates/manager_mandate.md",
        "risk_tier": "high",
        "recourse_path": "escalate",
        "review_sla": None,
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "due_at_utc": None,
        "externality_tags": ["damage:mandate_hash_mismatch"],
        "operator_burden": "high",
        "rationale": (
            "Damage signal 'mandate_hash_mismatch' from runtime:codex: "
            "Mandate changed while the role session was active."
        ),
        "metadata": {
            "source_recipe": "damage_signal_accountability_case_request.v1",
            "damage_signal": {
                "timestamp_utc": "2026-06-12T20:30:00+00:00",
                "source": "runtime:codex",
                "kind": "mandate_hash_mismatch",
                "detail": "Mandate changed while the role session was active.",
                "session_id": "sess_1",
                "severity": "critical",
            },
        },
        "case_id": "acct_damage_1",
    }

    case = create_accountability_case(log_path=log, **request)

    assert case.case_id == "acct_damage_1"
    assert case.status == "open"
    assert case.risk_tier == "high"
    assert case.recourse_path == "escalate"
    assert case.metadata["source_recipe"] == (
        "damage_signal_accountability_case_request.v1"
    )


def test_damage_signal_request_accepts_dataclass_and_warning_defaults() -> None:
    signal = DamageSignal(
        timestamp_utc="2026-06-12T20:30:00+00:00",
        source="agent_daemon",
        kind="agent_returned_no_progress",
        detail="Agent exited without closing or updating the task.",
        session_id=None,
        severity="warn",
    )

    request = build_damage_signal_accountability_case_request(
        signal,
        accountable_role="role.manager",
        responsible_actor="role.manager",
        decision_right_basis="mandate",
        authority_envelope_ref="org/mandates/manager_mandate.md",
        trigger_ref="damage_signal:agent_returned_no_progress:explicit",
        metadata={"run_id": "run_1"},
    )

    assert request["trigger_ref"] == "damage_signal:agent_returned_no_progress:explicit"
    assert request["responsible_actor"] == "role.manager"
    assert request["decision_right_basis"] == "mandate"
    assert request["risk_tier"] == "medium"
    assert request["recourse_path"] == "reopen"
    assert request["operator_burden"] == "medium"
    assert request["metadata"]["run_id"] == "run_1"
    assert request["metadata"]["damage_signal"]["severity"] == "warn"
