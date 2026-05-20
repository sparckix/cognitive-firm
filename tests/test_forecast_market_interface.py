from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.forecast_market import (  # noqa: E402
    load_summary_from_json,
    summary_from_mapping,
)


def test_normalizes_tenant_global_health_summary():
    summary = summary_from_mapping(
        {
            "forecast_pool_root": "analytics/public/forecast_pool",
            "contract_count": 2,
            "resolved_without_score": {"count": 1, "samples": ["c1"]},
            "aggregate_missing": {"count": 1, "samples": ["c2"]},
            "decision_use": {"rows": 3},
            "reliability": {"score_rows": 7, "high_confidence_miss_count": 2},
            "reflexive_insights": {"insights": [{"id": "decision_use_capture_gap"}]},
            "maintenance_plan": {"items": [{"kind": "score_debt"}]},
        }
    )

    assert summary.root == "analytics/public/forecast_pool"
    assert summary.n_contracts == 2
    assert summary.n_score_debt == 1
    assert summary.n_aggregate_debt == 1
    assert summary.n_decision_use_rows == 3
    assert summary.n_score_rows == 7
    assert summary.n_high_confidence_misses == 2
    assert summary.reflexive_insights[0]["id"] == "decision_use_capture_gap"


def test_normalizes_contract_read_model():
    summary = summary_from_mapping(
        {
            "contracts": [
                {
                    "contract_id": "c1",
                    "contract": {
                        "layer": "micro",
                        "question": "Will this route close?",
                        "task_type": "proof_search",
                    },
                    "lifecycle": {"state": "aggregate_ready", "next_action": "await_outcome"},
                    "forecasts": {"latest_count": 2},
                    "effective_independence": {"effective_n": 2},
                    "aggregate": {
                        "p_success": 0.7,
                        "allocation_recommendation": {
                            "action": "run_now",
                            "reason": "positive expected value",
                            "voi_proxy": 0.2,
                        },
                    },
                }
            ]
        }
    )

    state = summary.contracts[0]
    assert state.contract_id == "c1"
    assert state.contract is not None
    assert state.contract.layer == "micro"
    assert state.latest_forecast_count == 2
    assert state.effective_independent_forecaster_count == 2
    assert state.allocation_recommendation is not None
    assert state.allocation_recommendation.action == "run_now"


def test_load_summary_from_json(tmp_path: Path):
    path = tmp_path / "global_health.json"
    path.write_text(json.dumps({"contract_count": 1}), encoding="utf-8")
    summary = load_summary_from_json(path)
    assert summary.n_contracts == 1
