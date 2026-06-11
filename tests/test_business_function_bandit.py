from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_impact import (  # noqa: E402
    evaluate_offline_policy_candidate,
    summary_from_mapping,
)
from cognitive_firm.orchestration.business_function_bandit import (  # noqa: E402
    propose_business_function_policy,
)


def _rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx in range(30):
        senior = idx % 2 == 0
        rows.append(
            {
                "action_id": f"enterprise-{idx}",
                "action_ref": f"support/{idx}",
                "actor": "role.support_router",
                "objective_metric": "resolution_quality",
                "status": "measured",
                "context_features": {"segment": "enterprise"},
                "action_arm": "senior_review" if senior else "fast_lane",
                "reward": 0.9 if senior else 0.6,
                "logging_policy_probability": 0.5,
                "counterfactual_action": "fast_lane" if senior else "senior_review",
                "guardrail_metrics": {"sla_hours": 4.0},
            }
        )
    for idx in range(12):
        auto = idx % 2 == 0
        rows.append(
            {
                "action_id": f"renewals-{idx}",
                "action_ref": f"renewals/{idx}",
                "actor": "role.support_router",
                "objective_metric": "tickets_per_hour",
                "status": "measured",
                "context_features": {"queue": "renewals"},
                "action_arm": "auto_send" if auto else "manual_review",
                "reward": 1.0 if auto else 0.5,
                "negative_externality_tags": ["customer_trust"] if auto else [],
                "requires_human_review": auto,
                "guardrail_metrics": {"complaint_rate": 0.08 if auto else 0.01},
            }
        )
    return rows


def test_proposes_safe_candidate_map_for_repeated_business_function():
    summary = summary_from_mapping({"records": _rows()})
    candidate = propose_business_function_policy(
        summary.records,
        candidate_policy_id="policy.support.enterprise-senior-review",
        objective_metric="resolution_quality",
        context_keys=["segment"],
        min_context_rows=10,
        min_arm_rows=5,
    )

    assert candidate.status == "candidate"
    assert candidate.n_logged == 30
    assert candidate.n_contexts == 1
    assert list(candidate.candidate_action_by_context.values()) == ["senior_review"]
    assert candidate.selected_arms[0].delta_mean_reward > 0

    report = evaluate_offline_policy_candidate(
        summary.records,
        candidate_policy_id=candidate.candidate_policy_id,
        candidate_action_by_context=candidate.candidate_action_by_context,
        context_keys=candidate.context_keys,
        objective_metric=candidate.objective_metric,
        min_matched=10,
        min_support_coverage=0.4,
    )
    assert report.status == "promotable"


def test_refuses_high_reward_arm_when_guardrails_are_bad():
    summary = summary_from_mapping({"records": _rows()})
    candidate = propose_business_function_policy(
        summary.records,
        candidate_policy_id="policy.support.renewals-auto-send",
        objective_metric="tickets_per_hour",
        context_keys=["queue"],
        min_context_rows=6,
        min_arm_rows=3,
        max_negative_externality_rate=0.0,
        max_human_review_rate=0.25,
    )

    assert candidate.status == "no_candidate"
    assert candidate.candidate_action_by_context == {}
    assert candidate.rejected_contexts
    arms = candidate.rejected_contexts[0]["arms"]
    auto_send = next(row for row in arms if row["action_arm"] == "auto_send")
    assert auto_send["delta_mean_reward"] > 0
    assert auto_send["negative_externality_rate"] == 1.0
    assert auto_send["human_review_rate"] == 1.0


def test_requires_context_keys_and_candidate_id():
    summary = summary_from_mapping({"records": _rows()})
    try:
        propose_business_function_policy(
            summary.records,
            candidate_policy_id="",
            objective_metric="resolution_quality",
            context_keys=["segment"],
        )
    except ValueError as exc:
        assert "candidate_policy_id" in str(exc)
    else:
        raise AssertionError("empty candidate id should fail")

    try:
        propose_business_function_policy(
            summary.records,
            candidate_policy_id="policy.x",
            objective_metric="resolution_quality",
            context_keys=[],
        )
    except ValueError as exc:
        assert "context_keys" in str(exc)
    else:
        raise AssertionError("empty context keys should fail")
