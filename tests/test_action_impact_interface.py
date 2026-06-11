from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_impact import (  # noqa: E402
    append_policy_evaluation,
    append_policy_promotion_packet,
    build_policy_promotion_packet,
    context_signature,
    evaluate_offline_policy_candidate,
    list_policy_evaluations,
    list_policy_promotion_packets,
    load_summary_from_json,
    main as action_impact_main,
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
    assert first.reward == 0.4


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


def test_evaluates_promotable_offline_policy_candidate():
    rows = []
    for idx in range(30):
        region = "enterprise"
        arm = "senior_review" if idx % 2 == 0 else "fast_lane"
        reward = 0.9 if arm == "senior_review" else 0.6
        rows.append(
            {
                "action_id": f"a{idx}",
                "action_ref": f"actions/{idx}",
                "actor": "role.support_router",
                "objective_metric": "resolution_quality",
                "status": "measured",
                "context_features": {"segment": region},
                "action_arm": arm,
                "logging_policy_probability": 0.5,
                "counterfactual_action": "other",
                "reward": reward,
                "guardrail_metrics": {"sla_hours": 4.0},
            }
        )
    summary = summary_from_mapping({"records": rows})
    enterprise_sig = context_signature({"segment": "enterprise"}, ["segment"])
    assert enterprise_sig is not None
    report = evaluate_offline_policy_candidate(
        summary.records,
        candidate_policy_id="policy.support.enterprise-review",
        candidate_policy_ref="policy://support/enterprise-review",
        candidate_action_by_context={enterprise_sig: "senior_review"},
        context_keys=["segment"],
        objective_metric="resolution_quality",
        min_matched=10,
        min_support_coverage=0.4,
    )

    assert report.status == "promotable"
    assert report.promotion_allowed is True
    assert report.n_logged == 30
    assert report.n_eligible == 30
    assert report.n_matched == 15
    assert report.support_coverage == 0.5
    assert report.delta_mean_reward is not None
    assert report.delta_mean_reward > 0
    assert report.has_logging_propensities is True
    assert report.has_counterfactuals is True
    assert report.has_guardrail_metrics is True


def test_blocks_policy_candidate_with_thin_support_and_externalities():
    rows = [
        {
            "action_id": "a1",
            "action_ref": "actions/1",
            "actor": "role.router",
            "objective_metric": "throughput",
            "status": "measured",
            "context_features": {"queue": "sales"},
            "action_arm": "auto_send",
            "reward": 1.0,
            "negative_externality_tags": ["trust"],
        },
        {
            "action_id": "a2",
            "action_ref": "actions/2",
            "actor": "role.router",
            "objective_metric": "throughput",
            "status": "measured",
            "context_features": {"queue": "support"},
            "action_arm": "manual_review",
            "reward": 0.8,
        },
    ]
    summary = summary_from_mapping({"records": rows})
    sales_sig = context_signature({"queue": "sales"}, ["queue"])
    assert sales_sig is not None
    report = evaluate_offline_policy_candidate(
        summary.records,
        candidate_policy_id="policy.fast-sales",
        candidate_action_by_context={sales_sig: "auto_send"},
        context_keys=["queue"],
        objective_metric="throughput",
        min_matched=5,
        min_support_coverage=0.5,
    )

    assert report.status == "blocked"
    assert report.promotion_allowed is False
    assert report.negative_externality_rate == 1.0
    assert any("matched rows below threshold" in blocker for blocker in report.promotion_blockers)
    assert any("negative externality rate" in blocker for blocker in report.promotion_blockers)


def test_records_policy_evaluation_reports(tmp_path: Path):
    log_path = tmp_path / "policy_evaluations.jsonl"
    summary = summary_from_mapping(
        {
            "records": [
                {
                    "action_id": "a1",
                    "action_ref": "actions/1",
                    "actor": "role.router",
                    "objective_metric": "quality",
                    "status": "measured",
                    "context_features": {"tier": "gold"},
                    "action_arm": "review",
                    "reward": 1.0,
                }
            ]
        }
    )
    sig = context_signature({"tier": "gold"}, ["tier"])
    assert sig is not None
    report = evaluate_offline_policy_candidate(
        summary.records,
        candidate_policy_id="policy.gold-review",
        candidate_action_by_context={sig: "review"},
        context_keys=["tier"],
        objective_metric="quality",
        min_matched=1,
        min_support_coverage=1.0,
    )

    append_policy_evaluation(report, log_path=log_path)
    loaded = list_policy_evaluations(log_path=log_path)
    assert [row.evaluation_id for row in loaded] == [report.evaluation_id]


def test_builds_policy_promotion_packet_without_applying_policy():
    rows = []
    for idx in range(24):
        rows.append(
            {
                "action_id": f"a{idx}",
                "action_ref": f"actions/{idx}",
                "actor": "role.router",
                "objective_metric": "resolution_quality",
                "status": "measured",
                "context_features": {"segment": "enterprise"},
                "action_arm": "senior_review" if idx % 2 == 0 else "fast_lane",
                "reward": 1.0 if idx % 2 == 0 else 0.5,
                "logging_policy_probability": 0.5,
                "counterfactual_action": "other",
                "guardrail_metrics": {"sla_hours": 3.0},
            }
        )
    summary = summary_from_mapping({"records": rows})
    sig = context_signature({"segment": "enterprise"}, ["segment"])
    assert sig is not None
    report = evaluate_offline_policy_candidate(
        summary.records,
        candidate_policy_id="policy.enterprise-review",
        candidate_policy_ref="policy://support/enterprise-review",
        candidate_action_by_context={sig: "senior_review"},
        context_keys=["segment"],
        objective_metric="resolution_quality",
        min_matched=10,
        min_support_coverage=0.4,
        evidence_refs=["action-impact:fixture"],
    )

    packet = build_policy_promotion_packet(
        report,
        proposed_by="role.governance_reviewer",
        authority_diff_ref="authority-diff://policy-enterprise-review",
        formal_verification_refs=["formal-verification:fver_policy_boundary"],
        learning_event_refs=["learning-event:learn_route_review"],
    )

    assert packet.status == "review_ready"
    assert packet.review_blockers == []
    assert packet.governance_change_candidate["change_kind"] == "route_policy_change"
    assert packet.governance_change_candidate["target_ref"] == "policy://support/enterprise-review"
    assert "authority-diff://policy-enterprise-review" in packet.evidence_refs
    assert packet.guardrail_summary["has_guardrail_metrics"] is True
    assert packet.evaluation_report.evaluation_id == report.evaluation_id


def test_policy_promotion_packet_is_advisory_without_authority_diff(tmp_path: Path):
    summary = summary_from_mapping(
        {
            "records": [
                {
                    "action_id": f"a{idx}",
                    "action_ref": f"actions/{idx}",
                    "actor": "role.router",
                    "objective_metric": "quality",
                    "status": "measured",
                    "context_features": {"tier": "gold"},
                    "action_arm": "review" if idx % 2 == 0 else "fast_lane",
                    "reward": 1.0 if idx % 2 == 0 else 0.5,
                    "logging_policy_probability": 0.5,
                    "counterfactual_action": "other",
                    "guardrail_metrics": {"sla_hours": 2.0},
                }
                for idx in range(6)
            ]
        }
    )
    sig = context_signature({"tier": "gold"}, ["tier"])
    assert sig is not None
    report = evaluate_offline_policy_candidate(
        summary.records,
        candidate_policy_id="policy.gold-review",
        candidate_action_by_context={sig: "review"},
        context_keys=["tier"],
        objective_metric="quality",
        min_matched=3,
        min_support_coverage=0.5,
    )
    packet = build_policy_promotion_packet(report, proposed_by="role.reviewer")
    log_path = tmp_path / "policy_promotion_packets.jsonl"

    append_policy_promotion_packet(packet, log_path=log_path)
    loaded = list_policy_promotion_packets(log_path=log_path, candidate_policy_id="policy.gold-review")

    assert packet.status == "advisory"
    assert "authority diff not attached" in packet.review_blockers
    assert loaded[0].packet_id == packet.packet_id
    assert loaded[0].evaluation_report.evaluation_id == report.evaluation_id


def test_cli_builds_and_records_policy_promotion_packet(tmp_path: Path, capsys):
    evaluations_log = tmp_path / "policy_evaluations.jsonl"
    packets_log = tmp_path / "policy_promotion_packets.jsonl"
    summary = summary_from_mapping(
        {
            "records": [
                {
                    "action_id": f"a{idx}",
                    "action_ref": f"actions/{idx}",
                    "actor": "role.router",
                    "objective_metric": "quality",
                    "status": "measured",
                    "context_features": {"tier": "gold"},
                    "action_arm": "review" if idx % 2 == 0 else "fast_lane",
                    "reward": 1.0 if idx % 2 == 0 else 0.5,
                    "logging_policy_probability": 0.5,
                    "counterfactual_action": "other",
                    "guardrail_metrics": {"sla_hours": 2.0},
                }
                for idx in range(8)
            ]
        }
    )
    sig = context_signature({"tier": "gold"}, ["tier"])
    assert sig is not None
    report = evaluate_offline_policy_candidate(
        summary.records,
        candidate_policy_id="policy.gold-review",
        candidate_policy_ref="policy://support/gold-review",
        candidate_action_by_context={sig: "review"},
        context_keys=["tier"],
        objective_metric="quality",
        min_matched=4,
        min_support_coverage=0.5,
    )
    append_policy_evaluation(report, log_path=evaluations_log)

    rc = action_impact_main(
        [
            "build-promotion-packet",
            "--evaluation-id",
            report.evaluation_id,
            "--policy-evaluations-log",
            str(evaluations_log),
            "--proposed-by",
            "role.governance_reviewer",
            "--authority-diff-ref",
            "authority-diff://gold-review",
            "--formal-verification-ref",
            "formal-verification:fver_gold_review",
            "--learning-event-ref",
            "learning-event:learn_gold_review",
            "--record",
            "--policy-promotion-packets-log",
            str(packets_log),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    loaded = list_policy_promotion_packets(log_path=packets_log)

    assert rc == 0
    assert payload["status"] == "review_ready"
    assert payload["governance_change_candidate"]["target_ref"] == "policy://support/gold-review"
    assert loaded[0].packet_id == payload["packet_id"]
