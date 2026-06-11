from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.policy_decisions import (  # noqa: E402
    PolicyDecisionRequest,
    PolicyRule,
    evaluate_policy,
    list_policy_decisions,
    main as policy_decisions_main,
    policy_decision_from_authorization,
    policy_decision_resource,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402
from cognitive_firm.orchestration.task_authorization import AuthorizationDecision  # noqa: E402


def test_policy_decision_first_match_allow_is_recorded(tmp_path: Path):
    log = tmp_path / "policy.jsonl"
    request = PolicyDecisionRequest(
        action="kernel.mutate",
        actor_id="human.alice",
        role_id="role.manager",
        tenant_id="tenant-a",
        resource_ref="human_work:hws_1",
        context={"risk_tier": "low"},
    )

    result = evaluate_policy(
        request,
        rules=[
            PolicyRule(
                rule_id="allow-low-risk-manager",
                effect="allow",
                reason="manager may mutate low-risk human-work records",
                match={"role_id": "role.manager", "context.risk_tier": "low"},
            )
        ],
        policy_ref="policy/local-test",
        log_path=log,
    )

    assert result.allowed is True
    assert result.status == "matched"
    assert result.matched_rule_id == "allow-low-risk-manager"
    assert list_policy_decisions(log_path=log)[0].decision_id == result.decision_id


def test_policy_decision_projects_to_resource_envelope(tmp_path: Path):
    log = tmp_path / "policy.jsonl"
    request = PolicyDecisionRequest(
        action="kernel.mutate",
        actor_id="human.alice",
        role_id="role.manager",
        tenant_id="tenant-a",
        project_id="project-a",
        resource_ref="human_work:hws_1",
        context={"risk_tier": "low"},
    )

    result = evaluate_policy(
        request,
        rules=[
            PolicyRule(
                rule_id="allow-low-risk-manager",
                effect="allow",
                reason="manager may mutate low-risk human-work records",
                match={"role_id": "role.manager", "context.risk_tier": "low"},
            )
        ],
        policy_ref="policy/local-test",
        evidence_refs=["evidence://risk-score"],
        metadata={"source": "unit-test"},
        log_path=log,
    )

    payload = policy_decision_resource(result).as_dict()

    assert validate_resource(payload) == []
    assert payload["kind"] == "PolicyDecision"
    assert payload["metadata"]["name"] == result.decision_id
    assert payload["metadata"]["tenant_id"] == "tenant-a"
    assert payload["metadata"]["project_id"] == "project-a"
    assert payload["metadata"]["labels"]["effect"] == "allow"
    assert payload["metadata"]["labels"]["status"] == "matched"
    assert payload["metadata"]["labels"]["action"] == "kernel.mutate"
    assert payload["metadata"]["labels"]["actor_id"] == "human.alice"
    assert payload["metadata"]["labels"]["matched_rule_id"] == "allow-low-risk-manager"
    assert payload["metadata"]["annotations"]["source"] == "unit-test"
    assert payload["spec"]["request"]["resource_ref"] == "human_work:hws_1"
    assert payload["spec"]["policy_ref"] == "policy/local-test"
    assert payload["spec"]["evidence_refs"] == ["evidence://risk-score"]
    assert payload["status"]["allowed"] is True
    assert payload["status"]["effect"] == "allow"
    assert {"rel": "actor", "href": "human.alice"} in payload["links"]
    assert {"rel": "role", "href": "role.manager"} in payload["links"]
    assert {"rel": "resource", "href": "human_work:hws_1"} in payload["links"]
    assert {"rel": "policy", "href": "policy/local-test"} in payload["links"]
    assert {"rel": "evidence", "href": "evidence://risk-score"} in payload["links"]


def test_policy_decision_defaults_deny(tmp_path: Path):
    log = tmp_path / "policy.jsonl"

    result = evaluate_policy(
        PolicyDecisionRequest(
            action="kernel.mutate",
            actor_id="role.engineer",
            role_id="role.engineer",
            resource_ref="accountability_case:case_1",
        ),
        rules=[],
        log_path=log,
    )

    assert result.allowed is False
    assert result.effect == "deny"
    assert result.status == "defaulted"
    assert list_policy_decisions(effect="deny", log_path=log)[0].request.actor_id == "role.engineer"


def test_policy_decision_wraps_existing_authorization_shape(tmp_path: Path):
    log = tmp_path / "policy.jsonl"
    authorization = AuthorizationDecision(
        allowed=False,
        reason="outside authorized paths",
        required_approval="principal",
        matched_paths=("secrets/token.txt",),
        terminal=False,
    )

    result = policy_decision_from_authorization(
        authorization=authorization,
        action="daemon.dispatch",
        actor_id="role.engineer",
        role_id="role.engineer",
        resource_ref="task:demo",
        source_decision_ref="authz:demo",
        log_path=log,
    )

    assert result.allowed is False
    assert result.source_surface == "task_authorization"
    assert result.required_approval == "principal"
    assert result.matched_paths == ["secrets/token.txt"]


def test_policy_decision_resource_preserves_authorization_wrapper_fields(tmp_path: Path):
    log = tmp_path / "policy.jsonl"
    authorization = AuthorizationDecision(
        allowed=False,
        reason="outside authorized paths",
        required_approval="principal",
        matched_paths=("secrets/token.txt",),
        terminal=False,
    )

    result = policy_decision_from_authorization(
        authorization=authorization,
        action="daemon.dispatch",
        actor_id="role.engineer",
        role_id="role.engineer",
        resource_ref="task:demo",
        source_decision_ref="authz:demo",
        log_path=log,
    )

    payload = policy_decision_resource(result).as_dict()

    assert payload["metadata"]["labels"]["effect"] == "deny"
    assert payload["status"]["allowed"] is False
    assert payload["status"]["required_approval"] == "principal"
    assert payload["status"]["terminal"] is False
    assert payload["spec"]["source_surface"] == "task_authorization"
    assert payload["spec"]["source_decision_ref"] == "authz:demo"
    assert payload["spec"]["matched_paths"] == ["secrets/token.txt"]
    assert {"rel": "source_decision", "href": "authz:demo"} in payload["links"]


def test_policy_decision_cli_can_render_resource_envelope(
    tmp_path: Path,
    capsys,
):
    log = tmp_path / "policy.jsonl"
    request = {
        "action": "kernel.mutate",
        "actor_id": "human.alice",
        "role_id": "role.manager",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "resource_ref": "human_work:hws_1",
        "context": {"risk_tier": "low"},
    }
    rules = [
        {
            "rule_id": "allow-low-risk-manager",
            "effect": "allow",
            "reason": "manager may mutate low-risk human-work records",
            "match": {"role_id": "role.manager", "context.risk_tier": "low"},
        }
    ]

    rc = policy_decisions_main(
        [
            "--request-json",
            json.dumps(request),
            "--rules-json",
            json.dumps(rules),
            "--policy-ref",
            "policy/local-test",
            "--log-path",
            str(log),
            "--resource",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "PolicyDecision"
    assert payload["metadata"]["labels"]["effect"] == "allow"
    assert payload["spec"]["matched_rule_id"] == "allow-low-risk-manager"
