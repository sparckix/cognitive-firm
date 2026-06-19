from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_impact import summary_from_mapping as action_summary  # noqa: E402
from cognitive_firm.orchestration.forecast_market import summary_from_mapping as forecast_summary  # noqa: E402
from cognitive_firm.orchestration.learning_transition_compiler import (  # noqa: E402
    compile_attention_transition_candidates,
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


def test_compiler_maps_a2h_pressure_to_observer_only_learning_candidate():
    surface = {
        "forecast_state": {},
        "action_impact_state": {},
        "strategy_review_state": {},
        "a2h_pressure": [
            {
                "agent_counterparty_role": "role.researcher",
                "bottleneck_class": "access",
                "active_count": 3,
                "waiting_count": 2,
                "missing_receipt_count": 2,
                "stale_count": 0,
                "session_ids": ["hws_1", "hws_2", "hws_3"],
                "recommendation": "consider source connector, tooling, or mandate change",
            }
        ],
    }

    plan = compile_learning_transitions(surface)

    assert plan.n_candidates == 1
    candidate = plan.candidates[0]
    assert candidate.observer_only is True
    assert candidate.source_kind == "a2h_pressure"
    assert candidate.transition_kind == "source_repair"
    assert candidate.object_ref == "a2h_pressure:role.researcher:access"
    assert candidate.source_refs == [
        "human_work_session:hws_1",
        "human_work_session:hws_2",
        "human_work_session:hws_3",
    ]
    assert candidate.proposed_payload["missing_receipt_count"] == 2
    assert candidate.proposed_payload["boundary"].startswith("observer-only")


def test_compiler_maps_repeated_damage_to_observer_only_learning_candidate():
    surface = {
        "forecast_state": {},
        "action_impact_state": {},
        "strategy_review_state": {},
        "recent_damage_signals": [
            {
                "timestamp_utc": "2026-06-18T00:00:00+00:00",
                "source": "spend_tracker",
                "kind": "cost_spike",
                "detail": "Tool spend jumped above baseline.",
                "session_id": "run_1",
                "severity": "warn",
            },
            {
                "timestamp_utc": "2026-06-18T00:02:00+00:00",
                "source": "spend_tracker",
                "kind": "cost_spike",
                "detail": "Tool spend jumped above baseline again.",
                "session_id": "run_2",
                "severity": "warn",
            },
            {
                "timestamp_utc": "2026-06-18T00:03:00+00:00",
                "source": "quality_monitor",
                "kind": "style_warning",
                "detail": "One cosmetic issue.",
                "severity": "warn",
            },
        ],
    }

    plan = compile_learning_transitions(surface)

    damage_candidates = [
        candidate
        for candidate in plan.candidates
        if candidate.source_kind == "damage_pattern"
    ]
    assert len(damage_candidates) == 1
    candidate = damage_candidates[0]
    assert candidate.observer_only is True
    assert candidate.transition_kind == "mandate_review"
    assert candidate.object_ref == "damage_pattern:cost_spike"
    assert candidate.proposed_payload["signal_count"] == 2
    assert candidate.proposed_payload["sources"] == ["spend_tracker"]
    assert candidate.proposed_payload["session_ids"] == ["run_1", "run_2"]
    assert candidate.source_refs == [
        "damage_signal:spend_tracker:cost_spike:2026-06-18T00:00:00+00:00",
        "damage_signal:spend_tracker:cost_spike:2026-06-18T00:02:00+00:00",
    ]
    assert "does not quarantine" in candidate.proposed_payload["boundary"]


def test_compiler_maps_unrouted_attention_to_observer_only_candidate():
    plan = compile_attention_transition_candidates(
        [
            {
                "signal_id": "gate_1",
                "signal_class": "governance_interrupt",
                "pace_layer": "fast",
                "urgency": "approval_pending",
                "target_role_id": "tenant_authority",
                "target_actor_id": None,
                "headline": "Gate needs review",
                "primary_action": "approve",
                "source_ref": "gate://gate_1",
                "age_seconds": 120,
            }
        ]
    )

    assert plan.n_candidates == 1
    candidate = plan.candidates[0]
    assert candidate.observer_only is True
    assert candidate.source_kind == "attention_unrouted_signal"
    assert candidate.transition_kind == "route_policy_change"
    assert candidate.suggested_owner_role == "tenant_authority"
    assert candidate.source_refs == ["gate://gate_1"]
    assert candidate.proposed_payload["target_actor_id"] is None
    assert "does not reroute" in candidate.proposed_payload["boundary"]


def test_compiler_maps_repeated_attention_pressure_to_review_candidate():
    routed = [
        {
            "signal_id": f"hws_{index}",
            "signal_class": "work_interrupt",
            "pace_layer": "working",
            "urgency": "blocking_now",
            "target_role_id": "role.researcher",
            "target_actor_id": f"human.{index}",
            "headline": "Human work needed",
            "primary_action": "claim",
            "source_ref": f"human_work_session:hws_{index}",
            "age_seconds": 60,
        }
        for index in range(3)
    ]

    plan = compile_attention_transition_candidates(routed, repeated_threshold=3)

    assert plan.n_candidates == 1
    candidate = plan.candidates[0]
    assert candidate.source_kind == "attention_pressure"
    assert candidate.transition_kind == "human_work_session"
    assert candidate.object_ref == (
        "attention_pressure:role.researcher:work_interrupt:blocking_now"
    )
    assert candidate.proposed_payload["signal_count"] == 3
    assert candidate.proposed_payload["target_actor_ids"] == [
        "human.0",
        "human.1",
        "human.2",
    ]
