from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.policy_decisions import (  # noqa: E402
    PolicyDecisionRequest,
    PolicyRule,
    evaluate_policy,
    list_policy_decisions,
    policy_decision_from_authorization,
)
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
