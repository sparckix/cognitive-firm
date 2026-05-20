from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_impact import summary_from_mapping as action_summary  # noqa: E402
from cognitive_firm.orchestration.forecast_market import summary_from_mapping as forecast_summary  # noqa: E402
from cognitive_firm.orchestration.learning_transition_compiler import (  # noqa: E402
    compile_learning_transitions,
)
from cognitive_firm.orchestration.org_surface import OrgSurface  # noqa: E402
from cognitive_firm.orchestration.strategy_office import build_strategy_review  # noqa: E402


def test_compiler_turns_strategy_findings_into_reviewable_candidates():
    forecast = forecast_summary({"contract_count": 2, "decision_use": {"rows": 0}})
    action = action_summary(
        {
            "records": [
                {
                    "action_id": "a1",
                    "action_ref": "tenant/action/a1",
                    "actor": "role.manager",
                    "objective_metric": "throughput",
                    "status": "measured",
                    "optimization_scope": "local",
                    "negative_externality_tags": ["operator_load"],
                }
            ]
        }
    )
    review = build_strategy_review(
        forecast_summary=forecast,
        action_impact_summary=action,
        evidence_gaps=[{"gap_id": "gap_1", "severity": "blocking", "target": "claim"}],
    )
    surface = OrgSurface(
        forecast_state=forecast.as_dict(),
        action_impact_state=action.as_dict(),
        strategy_review_state=review.as_dict(),
    )

    plan = compile_learning_transitions(surface)

    kinds = {candidate.transition_kind for candidate in plan.candidates}
    assert "source_repair" in kinds
    assert "evidence_gap" in kinds
    assert "role_review" in kinds
    assert all(candidate.observer_only for candidate in plan.candidates)
    assert plan.candidates[0].severity == "blocking"
    assert sum(1 for candidate in plan.candidates if candidate.object_ref == "tenant/action/a1") == 1


def test_compiler_maps_forecast_allocation_to_transition_kind():
    surface = {
        "forecast_state": {
            "contracts": [
                {
                    "contract_id": "c1",
                    "allocation_recommendation": {
                        "action": "request_human_work",
                        "reason": "Restricted source must be checked by the principal.",
                        "voi_proxy": 0.8,
                    },
                }
            ]
        },
        "action_impact_state": {},
        "strategy_review_state": {},
    }

    plan = compile_learning_transitions(surface)

    assert plan.n_candidates == 1
    candidate = plan.candidates[0]
    assert candidate.transition_kind == "human_work_session"
    assert candidate.source_kind == "forecast_allocation_recommendation"
    assert candidate.proposed_payload["contract_id"] == "c1"


def test_compiler_maps_intelligence_source_improvements_to_source_repair():
    surface = {
        "forecast_state": {},
        "action_impact_state": {},
        "strategy_review_state": {},
        "intelligence_coverage_state": {
            "improvement_backlog": [
                {
                    "improvement_id": "forecast_market.decision_use_missing",
                    "source_id": "forecast_market",
                    "severity": "blocking",
                    "issue": "Forecast contracts exist, but decision-use rows are missing.",
                    "recommended_action": "Emit decision-use rows.",
                    "owner_hint": "tenant forecast-market adapter",
                    "source_refs": ["forecast_market"],
                }
            ]
        },
    }

    plan = compile_learning_transitions(surface)

    assert plan.n_candidates == 1
    candidate = plan.candidates[0]
    assert candidate.transition_kind == "source_repair"
    assert candidate.source_kind == "intelligence_source_improvement"
    assert candidate.object_ref == "forecast_market"
    assert candidate.proposed_payload["recommended_action"] == "Emit decision-use rows."
