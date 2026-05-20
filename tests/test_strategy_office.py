from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_impact import summary_from_mapping as action_summary  # noqa: E402
from cognitive_firm.orchestration.forecast_market import summary_from_mapping as forecast_summary  # noqa: E402
from cognitive_firm.orchestration.strategy_office import build_strategy_review  # noqa: E402


def test_strategy_office_flags_invalid_charter_as_alignment_issue():
    review = build_strategy_review(
        forecast_summary=forecast_summary({}),
        action_impact_summary=action_summary({"records": []}),
        charter_issues=[
            {
                "path": "projects/example/project_charter.md",
                "errors": ["missing required section: out of scope"],
                "summary": {"valid": False},
            }
        ],
    )

    assert review.n_blocking == 1
    finding = review.findings[0]
    assert finding.kind == "charter_alignment"
    assert finding.recommendation == "repair_project_charter"
    assert finding.candidate_transition_kind == "project_charter_update"


def test_strategy_office_flags_forecast_source_health_gap():
    review = build_strategy_review(
        forecast_summary=forecast_summary(
            {
                "forecast_pool_root": "tenant/forecast",
                "contract_count": 3,
                "decision_use": {"rows": 0},
            }
        ),
        action_impact_summary=action_summary({"records": []}),
    )

    assert review.observer_only is True
    assert review.n_blocking == 1
    finding = review.findings[0]
    assert finding.finding_id == "forecast_decision_use_missing"
    assert finding.recommendation == "repair_source_emitter"
    assert finding.candidate_transition_kind == "action_impact_repair"
    assert finding.review_question
    assert finding.promotion_gate


def test_strategy_office_surfaces_debt_and_externalities():
    review = build_strategy_review(
        forecast_summary=forecast_summary(
            {
                "forecast_pool_root": "tenant/forecast",
                "contract_count": 2,
                "decision_use": {"rows": 4},
                "resolved_without_score": {"count": 1},
                "reliability": {"high_confidence_miss_count": 1},
                "reflexive_insights": {"insights": [{"id": "calibration_drift"}]},
                "maintenance_plan": {"items": [{"kind": "score_debt"}]},
            }
        ),
        action_impact_summary=action_summary(
            {
                "records": [
                    {
                        "action_id": "a1",
                        "action_ref": "tenant/action/a1",
                        "actor": "role.manager",
                        "objective_metric": "throughput",
                        "status": "measured",
                        "actual_impact": 1.0,
                        "optimization_scope": "local",
                        "externalities": {"trust": -0.4},
                    },
                    {
                        "action_id": "a2",
                        "action_ref": "tenant/action/a2",
                        "actor": "role.reviewer",
                        "objective_metric": "scientific_yield",
                        "requires_human_review": True,
                    },
                ]
            }
        ),
    )

    ids = {finding.finding_id for finding in review.findings}
    assert "forecast_score_debt" in ids
    assert "forecast_high_confidence_misses" in ids
    assert "forecast_reflexive_insight_1" in ids
    assert "forecast_maintenance_item_1" in ids
    assert "negative_externality_a1" in ids
    assert "action_review_required_a2" in ids
    assert all(finding.observer_only for finding in review.findings)
    negative = next(finding for finding in review.findings if finding.finding_id == "negative_externality_a1")
    assert negative.scope == "local"
    assert negative.review_question


def test_strategy_office_reads_evidence_human_damage_and_failed_runs():
    review = build_strategy_review(
        forecast_summary=forecast_summary({}),
        action_impact_summary=action_summary({"records": []}),
        evidence_gaps=[
            {
                "gap_id": "gap_1",
                "severity": "blocking",
                "target": "claim",
                "status": "open",
            }
        ],
        human_work_sessions=[
            {
                "session_id": "hws_1",
                "state": "completed",
                "receipt_required": True,
                "agent_followup_required": True,
            }
        ],
        recent_damage_signals=[{"kind": "mandate_hash_mismatch"}],
        failed_runs=[{"run_id": "run_1", "failure_reason": "source inaccessible"}],
    )

    ids = {finding.finding_id for finding in review.findings}
    assert "blocking_evidence_gaps" in ids
    assert "human_work_agent_followup" in ids
    assert "human_work_receipt_missing" in ids
    assert "recent_damage_signals" in ids
    assert "failed_runs_present" in ids
