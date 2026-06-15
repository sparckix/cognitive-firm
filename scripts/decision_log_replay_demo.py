#!/usr/bin/env python3
"""Replay action-impact logs into governance review packets.

The demo uses a fictional support desk and deterministic fixture rows. It does
not call a model, API, subscription runtime, or network service. Its point is
to show that a learned-routing candidate can be reconstructed from saved logs:

action-impact summary + candidate map -> offline evaluation -> promotion packet

The kernel still does not promote policy. It produces review evidence.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request
from cognitive_firm.orchestration.action_impact import (
    context_signature,
    load_summary_from_json,
)
from cognitive_firm.orchestration.business_function_bandit import propose_business_function_policy


def _assert_status(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label} failed with status {actual}; expected {expected}")


def _support_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx in range(30):
        senior = idx % 2 == 0
        rows.append(
            {
                "action_id": f"enterprise-{idx}",
                "action_ref": f"action-impact://support/enterprise/{idx}",
                "actor": "role.support_router",
                "objective_metric": "resolution_quality",
                "status": "measured",
                "context_features": {"segment": "enterprise"},
                "action_arm": "senior_review" if senior else "fast_lane",
                "logging_policy_probability": 0.5,
                "counterfactual_action": "fast_lane" if senior else "senior_review",
                "reward": 0.9 if senior else 0.6,
                "guardrail_metrics": {"sla_hours": 4.0 if senior else 2.0},
                "externalities": {"customer_trust": 0.0},
                "requires_human_review": False,
            }
        )
    for idx in range(12):
        auto = idx % 2 == 0
        rows.append(
            {
                "action_id": f"renewals-{idx}",
                "action_ref": f"action-impact://support/renewals/{idx}",
                "actor": "role.support_router",
                "objective_metric": "tickets_per_hour",
                "status": "measured",
                "context_features": {"queue": "renewals"},
                "action_arm": "auto_send" if auto else "manual_review",
                "logging_policy_probability": 0.5,
                "counterfactual_action": "manual_review" if auto else "auto_send",
                "reward": 1.0 if auto else 0.5,
                "negative_externality_tags": ["customer_trust"] if auto else [],
                "requires_human_review": auto,
                "guardrail_metrics": {"complaint_rate": 0.08 if auto else 0.01},
            }
        )
    return rows


def _write_fixture_logs(root: Path) -> dict[str, Path]:
    logs = {
        "summary": root / "action_impact_summary.json",
        "safe_map": root / "candidate_enterprise_review.json",
        "safe_proposal": root / "candidate_enterprise_review_proposal.json",
        "unsafe_proposal": root / "candidate_renewals_auto_send_proposal.json",
        "unsafe_map": root / "candidate_renewals_auto_send.json",
        "evaluations": root / "policy_evaluations.jsonl",
        "packets": root / "policy_promotion_packets.jsonl",
        "authority_diff": root / "authority_diff_enterprise_review.json",
    }
    root.mkdir(parents=True, exist_ok=True)
    logs["summary"].write_text(
        json.dumps({"records": _support_rows()}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    renewals_sig = context_signature({"queue": "renewals"}, ["queue"])
    if renewals_sig is None:
        raise AssertionError("fixture signatures unexpectedly failed")
    logs["unsafe_map"].write_text(
        json.dumps({renewals_sig: "auto_send"}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    logs["authority_diff"].write_text(
        json.dumps(
            {
                "change": "route enterprise support cases to senior review",
                "authority_change": "none",
                "review_surface": "role.support_manager",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return logs


def run_replay(root: Path) -> dict[str, Any]:
    logs = _write_fixture_logs(root)
    config = KernelServiceConfig(
        action_impact_summary=logs["summary"],
        policy_evaluations_log=logs["evaluations"],
        policy_promotion_packets_log=logs["packets"],
        org_dir=root / "org",
    )
    actor_context = {
        "actor_id": "role.support_manager",
        "actor_kind": "service",
        "role_id": "role.support_manager",
        "surface": "decision_log_replay_demo",
    }
    summary = load_summary_from_json(logs["summary"])
    safe_proposal = propose_business_function_policy(
        summary.records,
        candidate_policy_id="policy.support.enterprise-senior-review",
        objective_metric="resolution_quality",
        context_keys=["segment"],
        min_context_rows=10,
        min_arm_rows=5,
        evidence_refs=[str(logs["summary"])],
        metadata={"demo": "decision_log_replay"},
    )
    unsafe_proposal = propose_business_function_policy(
        summary.records,
        candidate_policy_id="policy.support.renewals-auto-send",
        objective_metric="tickets_per_hour",
        context_keys=["queue"],
        min_context_rows=6,
        min_arm_rows=3,
        max_negative_externality_rate=0.0,
        max_human_review_rate=0.25,
        evidence_refs=[str(logs["summary"])],
        metadata={"demo": "decision_log_replay"},
    )
    logs["safe_proposal"].write_text(
        json.dumps(safe_proposal.as_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    logs["unsafe_proposal"].write_text(
        json.dumps(unsafe_proposal.as_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    logs["safe_map"].write_text(
        json.dumps(safe_proposal.candidate_action_by_context, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    safe_map = json.loads(logs["safe_map"].read_text(encoding="utf-8"))
    unsafe_map = json.loads(logs["unsafe_map"].read_text(encoding="utf-8"))

    safe_evaluation_response = dispatch_kernel_request(
        "POST",
        "/kernel/action-impact/policy-evaluations/evaluate",
        {
            "candidate_policy_id": "policy.support.enterprise-senior-review",
            "candidate_policy_ref": "policy://support/enterprise-senior-review",
            "candidate_action_by_context": {str(k): str(v) for k, v in safe_map.items()},
            "context_keys": ["segment"],
            "objective_metric": "resolution_quality",
            "min_matched": 10,
            "min_support_coverage": 0.4,
            "max_negative_externality_rate": 0.0,
            "max_human_review_rate": 0.25,
            "evidence_refs": [str(logs["summary"]), str(logs["safe_map"])],
            "metadata": {"demo": "decision_log_replay"},
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(safe_evaluation_response.status, 201, "safe policy evaluation")
    safe_report = safe_evaluation_response.payload["policy_evaluation"]
    unsafe_evaluation_response = dispatch_kernel_request(
        "POST",
        "/kernel/action-impact/policy-evaluations/evaluate",
        {
            "candidate_policy_id": "policy.support.renewals-auto-send",
            "candidate_policy_ref": "policy://support/renewals-auto-send",
            "candidate_action_by_context": {str(k): str(v) for k, v in unsafe_map.items()},
            "context_keys": ["queue"],
            "objective_metric": "tickets_per_hour",
            "min_matched": 4,
            "min_support_coverage": 0.4,
            "max_negative_externality_rate": 0.0,
            "max_human_review_rate": 0.25,
            "evidence_refs": [str(logs["summary"]), str(logs["unsafe_map"])],
            "metadata": {"demo": "decision_log_replay"},
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(unsafe_evaluation_response.status, 201, "unsafe policy evaluation")
    unsafe_report = unsafe_evaluation_response.payload["policy_evaluation"]

    safe_packet_response = dispatch_kernel_request(
        "POST",
        "/kernel/action-impact/policy-promotion-packets",
        {
            "evaluation_id": safe_report["evaluation_id"],
            "proposed_by": "role.support_manager",
            "authority_diff_ref": str(logs["authority_diff"]),
            "title": "Review enterprise senior-review routing policy",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(safe_packet_response.status, 201, "safe promotion packet")
    unsafe_packet_response = dispatch_kernel_request(
        "POST",
        "/kernel/action-impact/policy-promotion-packets",
        {
            "evaluation_id": unsafe_report["evaluation_id"],
            "proposed_by": "role.support_manager",
            "authority_diff_ref": "authority-diff://renewals-auto-send",
            "title": "Review renewals auto-send routing policy",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(unsafe_packet_response.status, 201, "unsafe promotion packet")

    replayed_reports_response = dispatch_kernel_request(
        "GET",
        "/kernel/action-impact/policy-evaluations",
        config=config,
    )
    _assert_status(replayed_reports_response.status, 200, "policy evaluation replay")
    replayed_packets_response = dispatch_kernel_request(
        "GET",
        "/kernel/action-impact/policy-promotion-packets",
        config=config,
    )
    _assert_status(replayed_packets_response.status, 200, "policy packet replay")
    replayed_reports = replayed_reports_response.payload["policy_evaluations"]
    replayed_packets = replayed_packets_response.payload["policy_promotion_packets"]
    report_by_id = {str(report["evaluation_id"]): report for report in replayed_reports}
    packet_rows = []
    for packet in replayed_packets:
        report = report_by_id[packet["evaluation_report"]["evaluation_id"]]
        packet_rows.append(
            {
                "candidate_policy_id": packet["candidate_policy_id"],
                "evaluation_status": report["status"],
                "packet_status": packet["status"],
                "delta_mean_reward": report["delta_mean_reward"],
                "support_coverage": report["support_coverage"],
                "negative_externality_rate": report["negative_externality_rate"],
                "human_review_rate": report["human_review_rate"],
                "review_blockers": list(packet["review_blockers"]),
            }
        )

    review_ready = sum(1 for row in packet_rows if row["packet_status"] == "review_ready")
    blocked = sum(1 for row in packet_rows if row["packet_status"] == "blocked")
    return {
        "demo": "decision_log_replay",
        "fictional_firm": "Northstar Support Co.",
        "no_external_calls": True,
        "logs_only_replay": True,
        "summary": {
            "records": len(summary.records),
            "evaluations": len(replayed_reports),
            "packets": len(replayed_packets),
            "review_ready": review_ready,
            "blocked": blocked,
            "verdict": "passed" if review_ready == 1 and blocked == 1 else "failed",
        },
        "candidate_proposer": {
            "safe_status": safe_proposal.status,
            "safe_contexts": len(safe_proposal.candidate_action_by_context),
            "unsafe_status": unsafe_proposal.status,
            "unsafe_rejected_contexts": len(unsafe_proposal.rejected_contexts),
        },
        "replayed_packets": sorted(packet_rows, key=lambda row: row["candidate_policy_id"]),
        "log_paths": {name: str(path) for name, path in logs.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay action-impact logs into governance policy packets.",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        help="Optional directory to keep generated fixture logs. Defaults to a temp dir.",
    )
    parser.add_argument(
        "--full-json",
        action="store_true",
        help="Print log paths and full replay rows. Compact output omits log paths.",
    )
    args = parser.parse_args(argv)

    if args.workdir:
        payload = run_replay(args.workdir)
    else:
        with tempfile.TemporaryDirectory(prefix="cf-decision-replay-") as raw:
            payload = run_replay(Path(raw))

    if not args.full_json:
        payload = {
            "demo": payload["demo"],
            "fictional_firm": payload["fictional_firm"],
            "no_external_calls": payload["no_external_calls"],
            "logs_only_replay": payload["logs_only_replay"],
            "summary": payload["summary"],
            "candidate_proposer": payload["candidate_proposer"],
            "replayed_packets": [
                {
                    "candidate_policy_id": row["candidate_policy_id"],
                    "evaluation_status": row["evaluation_status"],
                    "packet_status": row["packet_status"],
                    "delta_mean_reward": row["delta_mean_reward"],
                    "review_blockers": row["review_blockers"],
                }
                for row in payload["replayed_packets"]
            ],
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["summary"]["verdict"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
