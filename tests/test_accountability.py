from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.accountability import build_accountability_summary  # noqa: E402


def test_accountability_summary_joins_learning_carriers():
    surface = {
        "blocking_evidence_gaps": [
            {
                "gap_id": "gap_1",
                "severity": "blocking",
                "status": "open",
                "producer": "role.reviewer",
                "project_id": "demo",
                "target": "claim",
                "description": "Need primary source.",
            }
        ],
        "active_human_work_sessions": [
            {
                "session_id": "hws_1",
                "state": "handed_off",
                "requested_by": "role.manager",
                "human_actor": "principal",
                "project_id": "demo",
                "objective": "verify restricted source",
                "receipt_required": True,
                "receipt": None,
                "agent_followup_required": True,
                "deadline_utc": "2026-05-20T00:00:00+00:00",
            }
        ],
        "action_impact_state": {
            "review_required": [
                {
                    "action_id": "a1",
                    "action_ref": "tenant/action/a1",
                    "actor": "role.manager",
                    "project_id": "demo",
                    "objective_metric": "source_readiness",
                    "requires_human_review": True,
                    "status": "planned",
                }
            ],
            "local_with_negative_externalities": [
                {
                    "action_id": "a2",
                    "action_ref": "tenant/action/a2",
                    "actor": "role.manager",
                    "project_id": "demo",
                    "status": "measured",
                    "negative_externality_tags": ["principal_time"],
                }
            ],
        },
        "forecast_state": {
            "contracts": [
                {
                    "contract_id": "c1",
                    "lifecycle_state": "aggregate_ready",
                    "allocation_recommendation": {
                        "action": "request_human_work",
                        "reason": "Need source access.",
                    },
                }
            ]
        },
        "strategy_review_state": {
            "findings": [
                {
                    "finding_id": "f1",
                    "severity": "warning",
                    "suggested_owner_role": "role.manager",
                    "object_ref": "c1",
                    "rationale": "Forecast needs decision-use linkage.",
                    "source_refs": ["c1"],
                }
            ]
        },
        "open_accountability_cases": [
            {
                "case_id": "acct_1",
                "status": "open",
                "trigger_ref": "action:a1",
                "accountable_role": "role.manager",
                "responsible_actor": "agent.researcher",
                "decision_right_basis": "role mandate",
                "authority_envelope_ref": "org/roles/manager.yaml",
                "risk_tier": "high",
                "recourse_path": "reopen",
                "project_id": "demo",
                "rationale": "Residual-risk owner must close the case.",
            }
        ],
        "recent_damage_signals": [{"kind": "mandate_hash_mismatch", "severity": "warning"}],
        "failed_runs": [{"run_id": "run_1", "owner_role": "role.manager", "project_id": "demo"}],
    }

    summary = build_accountability_summary(surface)

    assert summary.n_items >= 7
    assert summary.n_review_required >= 6
    assert summary.n_blocking == 1
    assert summary.n_by_project_id["demo"] >= 4
    kinds = {item.source_kind for item in summary.items}
    assert "evidence_gap" in kinds
    assert "human_work" in kinds
    assert "negative_externality" in kinds
    assert "forecast_allocation" in kinds
    assert "strategy_finding" in kinds
    assert "accountability_case" in kinds
    assert "damage_signal" in kinds
    assert "failed_run" in kinds
