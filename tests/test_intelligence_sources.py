from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.intelligence_sources import (  # noqa: E402
    build_intelligence_coverage,
    routing_readiness_from_coverage,
)


def test_intelligence_coverage_flags_forecast_decision_use_gap():
    coverage = build_intelligence_coverage(
        forecast_state={
            "n_contracts": 3,
            "n_decision_use_rows": 0,
            "n_score_debt": 1,
        },
        action_impact_state={"n_total": 0},
        strategy_review_state={"n_findings": 1},
        surface_counts={"active_learning_events": 0},
    )

    ids = {item.improvement_id for item in coverage.improvement_backlog}

    assert "forecast_market.decision_use_missing" in ids
    assert "forecast_market.score_debt" in ids
    assert "learning_events.findings_not_promoted" in ids
    assert coverage.n_warning_or_blocking_improvements == 2
    assert coverage.counts_by_health["debt"] >= 2


def test_intelligence_coverage_keeps_tenant_sources_distinct():
    coverage = build_intelligence_coverage()
    by_id = {source.source_id: source for source in coverage.sources}

    assert by_id["forecast_market"].tenant_owned is True
    assert by_id["action_impact"].tenant_owned is True
    assert by_id["mcp_outbox"].connector_family == "enterprise_system"
    assert by_id["runtime_adapters"].connector_family == "runtime"
    assert by_id["org_surface"].health == "proxy_only"
    assert coverage.n_sources >= 1


def test_routing_readiness_blocks_on_source_health_debt():
    coverage = build_intelligence_coverage(
        forecast_state={
            "n_contracts": 2,
            "n_decision_use_rows": 0,
            "n_score_debt": 1,
        },
        action_impact_state={
            "n_total": 1,
            "n_review_required": 1,
            "n_local_with_negative_externalities": 1,
        },
    )

    readiness = routing_readiness_from_coverage(
        coverage,
        source_ids=["forecast_market", "action_impact"],
    )

    assert readiness.ready is False
    assert [item.improvement_id for item in readiness.blocking_improvements] == [
        "forecast_market.decision_use_missing"
    ]
    assert {item.source_id for item in readiness.warning_improvements} == {
        "forecast_market",
        "action_impact",
    }


def test_routing_readiness_warns_on_thin_tenant_sources_without_improvement_rows():
    coverage = build_intelligence_coverage(
        forecast_state={},
        action_impact_state={},
    )

    readiness = routing_readiness_from_coverage(
        coverage,
        source_ids=["forecast_market", "action_impact"],
    )

    assert readiness.ready is False
    assert {
        item.improvement_id for item in readiness.warning_improvements
    } >= {
        "forecast_market.source_health_thin",
        "action_impact.source_health_thin",
    }
