#!/usr/bin/env python3
"""Executable source-coverage walkthrough.

The fixture shows how a tenant-owned forecast summary can be present but still
too thin for reliable routing because it lacks decision-use evidence.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.learning_transition_compiler import compile_learning_transitions  # noqa: E402
from cognitive_firm.orchestration.org_surface import build_org_surface  # noqa: E402
from cognitive_firm.orchestration.intelligence_sources import (  # noqa: E402
    build_intelligence_coverage,
    routing_readiness_from_coverage,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-source-coverage-") as raw:
        root = Path(raw)
        forecast_summary = root / "forecast_market" / "global_health.json"
        forecast_summary.parent.mkdir(parents=True)
        forecast_summary.write_text(
            json.dumps(
                {
                    "contract_count": 2,
                    "decision_use": {"rows": 0},
                    "resolved_without_score": [{"contract_id": "forecast/demo-1"}],
                    "contracts": [
                        {
                            "contract_id": "forecast/demo-1",
                            "contract": {
                                "contract_id": "forecast/demo-1",
                                "layer": "micro",
                                "question": "Should the role route this branch now?",
                            },
                            "lifecycle": {
                                "state": "resolved_unscored",
                                "next_action": "score",
                            },
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        surface = build_org_surface(
            project_root=root,
            evidence_gaps_log=root / "org" / "evidence_gaps" / "evidence_gaps.jsonl",
            human_work_log=root / "org" / "human_work" / "human_work.jsonl",
            forecast_market_summary=forecast_summary,
            action_impact_summary=root / "org" / "action_impact" / "missing.json",
            governance_changes_log=root / "org" / "governance" / "governance_changes.jsonl",
            accountability_cases_log=root / "org" / "accountability" / "accountability_cases.jsonl",
            learning_events_log=root / "org" / "learning_events" / "learning_events.jsonl",
            transitions_log=root / "workspace" / "transitions.jsonl",
            damage_limit=0,
        )
        plan = compile_learning_transitions(surface)
        improvements = {
            item["improvement_id"]
            for item in surface.intelligence_coverage_state["improvement_backlog"]
        }
        source_repair = [
            candidate
            for candidate in plan.candidates
            if candidate.transition_kind == "source_repair"
        ]
        required = {
            "forecast_market.decision_use_missing",
            "forecast_market.score_debt",
        }
        if not required.issubset(improvements):
            raise SystemExit(f"missing source improvements: {required - improvements}")
        if not source_repair:
            raise SystemExit("source-improvement backlog did not compile to source_repair")
        coverage = build_intelligence_coverage(
            forecast_state=surface.forecast_state,
            action_impact_state=surface.action_impact_state,
            strategy_review_state=surface.strategy_review_state,
            surface_counts=surface.counts,
        )
        readiness = routing_readiness_from_coverage(
            coverage,
            source_ids=["forecast_market", "action_impact"],
        )
        if readiness.ready:
            raise SystemExit("routing was allowed despite unresolved source-health debt")

        print(
            json.dumps(
                {
                    "ok": True,
                    "forecast_contracts": surface.counts["forecast_contracts"],
                    "routing_ready": readiness.ready,
                    "source_improvements": sorted(improvements),
                    "source_repair_candidates": len(source_repair),
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
