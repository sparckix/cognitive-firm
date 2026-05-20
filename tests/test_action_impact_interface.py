from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_impact import (  # noqa: E402
    load_summary_from_json,
    summary_from_mapping,
)


def test_normalizes_action_impact_summary():
    summary = summary_from_mapping(
        {
            "records": [
                {
                    "action_id": "a1",
                    "action_ref": "analytics/yield.md#row-1",
                    "actor": "role.research_director",
                    "actor_role": "research_director",
                    "action_kind": "route_change",
                    "decision_stage": "pre_tick",
                    "baseline_action": "continue_branch",
                    "counterfactual_action": "ask_independent_agent",
                    "expected_effect": "reduce false closure risk",
                    "observed_outcome": "branch split before execution",
                    "impact_summary": "forecast changed the route",
                    "old_state": "single_agent_route",
                    "new_state": "independent_check",
                    "artifact_refs": ["contracts/c1"],
                    "cost_units": 2.0,
                    "wall_seconds": 1800,
                    "evaluator_role": "research_director",
                    "independence_boundary": "cross_agent",
                    "decision_changed_bool": True,
                    "externality_tags": ["operator_load"],
                    "negative_externality_tags": ["latency"],
                    "ignored_or_overridden_reason": None,
                    "objective_metric": "scientific_yield",
                    "expected_impact": 0.2,
                    "actual_impact": 0.4,
                    "status": "measured",
                    "optimization_scope": "project",
                    "externalities": {"operator_load": -0.1},
                },
                {
                    "action_id": "a2",
                    "action_ref": "analytics/yield.md#row-2",
                    "actor": "role.research_director",
                    "objective_metric": "scientific_yield",
                    "status": "planned",
                    "optimization_scope": "local",
                    "requires_human_review": True,
                },
            ]
        },
        root="tenant/action_impact",
    )

    assert summary.root == "tenant/action_impact"
    assert summary.n_total == 2
    assert summary.n_measured == 1
    assert summary.n_planned == 1
    assert summary.n_review_required == 1
    assert summary.mean_actual_impact_by_metric["scientific_yield"] == 0.4
    first = summary.records[0]
    assert first.actor_role == "research_director"
    assert first.action_kind == "route_change"
    assert first.decision_stage == "pre_tick"
    assert first.baseline_action == "continue_branch"
    assert first.counterfactual_action == "ask_independent_agent"
    assert first.decision_changed_bool is True
    assert first.artifact_refs == ["contracts/c1"]
    assert first.negative_externality_tags == ["latency"]


def test_flags_local_negative_externalities():
    summary = summary_from_mapping(
        {
            "records": [
                {
                    "action_id": "a1",
                    "action_ref": "x",
                    "actor": "agent",
                    "objective_metric": "profit",
                    "actual_impact": 1.0,
                    "status": "measured",
                    "optimization_scope": "local",
                    "externalities": {"trust": -0.5},
                }
            ]
        }
    )

    assert summary.n_local_with_negative_externalities == 1
    assert summary.local_with_negative_externalities[0].action_id == "a1"


def test_flags_tag_only_local_negative_externalities():
    summary = summary_from_mapping(
        {
            "records": [
                {
                    "action_id": "a1",
                    "action_ref": "x",
                    "actor": "agent",
                    "objective_metric": "throughput",
                    "status": "measured",
                    "optimization_scope": "local",
                    "negative_externality_tags": ["operator_load"],
                }
            ]
        }
    )

    assert summary.n_local_with_negative_externalities == 1
    assert summary.local_with_negative_externalities[0].negative_externality_tags == ["operator_load"]


def test_preserves_zero_actual_impact_and_string_false_review_flag():
    summary = summary_from_mapping(
        {
            "records": [
                {
                    "action_id": "a1",
                    "action_ref": "x",
                    "actor": "agent",
                    "objective_metric": "scientific_yield",
                    "actual_impact": 0.0,
                    "status": "measured",
                    "requires_human_review": "false",
                }
            ]
        }
    )

    assert summary.records[0].actual_impact == 0.0
    assert summary.mean_actual_impact_by_metric["scientific_yield"] == 0.0
    assert summary.n_review_required == 0


def test_load_summary_from_json(tmp_path: Path):
    path = tmp_path / "action_impact_summary.json"
    path.write_text(json.dumps({"n_total": 3}), encoding="utf-8")
    summary = load_summary_from_json(path)
    assert summary.n_total == 3
