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
from cognitive_firm.orchestration.action_attestation import (
    create_action_attestation,
    digest_text,
)
from cognitive_firm.orchestration.action_impact import (
    context_signature,
    load_summary_from_json,
)
from cognitive_firm.orchestration.artifact_bundle import (
    build_governed_run_attestation_bundle,
    governed_run_bundle_summary,
    governed_run_bundle_to_dict,
    validate_governed_run_bundle_payload,
)
from cognitive_firm.orchestration.business_function_bandit import propose_business_function_policy
from cognitive_firm.orchestration.outcome_links import (
    create_outcome_link,
    record_metric_snapshot,
    record_verdict,
)
from cognitive_firm.orchestration.run_checkpoints import (
    append_checkpoint,
    set_run_state,
    start_run,
)


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
        "transitions": root / "transitions.jsonl",
        "attestations": root / "action_attestations.jsonl",
        "outcomes": root / "outcome_links.jsonl",
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
                "packet_id": packet["packet_id"],
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
    run = start_run(
        owner_role="role.support_manager",
        objective="replay support action-impact logs into policy-review evidence",
        tenant_id="tenant-northstar-support",
        project_id="project-support-routing",
        idempotency_key="decision-log-replay-demo",
        run_id="run_decision_log_replay",
        log_path=logs["transitions"],
    )
    append_checkpoint(
        run.run_id,
        actor="role.support_manager",
        step_id="replay_policy_logs",
        status="completed",
        summary=(
            "Replayed action-impact logs into one review-ready packet and one "
            "blocked packet."
        ),
        payload_ref=str(logs["packets"]),
        side_effect_key="decision-log-replay:policy-packets",
        log_path=logs["transitions"],
    )
    packet_digest = digest_text(json.dumps(packet_rows, sort_keys=True))
    attestation = create_action_attestation(
        subject_kind="artifact",
        subject_ref="decision-log-replay:policy-promotion-packets",
        subject_digest=packet_digest,
        producer="role.support_manager",
        action_type="decision_log_replay",
        runtime_ref="scripts/decision_log_replay_demo.py",
        input_refs=[
            str(logs["summary"]),
            str(logs["safe_map"]),
            str(logs["unsafe_map"]),
            str(logs["evaluations"]),
        ],
        output_refs=[
            f"policy_promotion_packet:{row['packet_id']}"
            for row in packet_rows
        ],
        verification_status="verified",
        verification_summary=(
            "Replay reconstructed exactly two packet rows: one review-ready "
            "and one blocked by guardrails."
        ),
        tenant_id="tenant-northstar-support",
        project_id="project-support-routing",
        run_id=run.run_id,
        metadata={
            "demo": "decision_log_replay",
            "review_ready": review_ready,
            "blocked": blocked,
        },
        log_path=logs["attestations"],
    )
    outcome = create_outcome_link(
        change_ref=f"run:{run.run_id}",
        change_kind="decision_log_replay_demo",
        metric_name="replay_packet_reconstruction",
        metric_unit="passed_check",
        created_by="role.support_manager",
        tenant_id="tenant-northstar-support",
        project_id="project-support-routing",
        owner_role="role.support_manager",
        direction="increase",
        metadata={"cognitive_run_id": run.run_id, "demo": "decision_log_replay"},
        log_path=logs["outcomes"],
    )
    record_metric_snapshot(
        outcome.outcome_link_id,
        kind="baseline",
        value=0,
        captured_by="role.support_manager",
        measurement_ref=str(logs["summary"]),
        note="No replay proof before reconstructing packet rows.",
        log_path=logs["outcomes"],
    )
    record_metric_snapshot(
        outcome.outcome_link_id,
        kind="post",
        value=1,
        captured_by="role.support_manager",
        measurement_ref=f"attestation:{attestation.attestation_id}",
        note="Replay proof reconstructed safe and blocked packet rows.",
        log_path=logs["outcomes"],
    )
    record_verdict(
        outcome.outcome_link_id,
        verdict="improved",
        recorded_by="role.support_manager",
        rationale="The replay produced validated review evidence from logs alone.",
        log_path=logs["outcomes"],
    )
    append_checkpoint(
        run.run_id,
        actor="role.support_manager",
        step_id="attest_replay",
        status="completed",
        summary="Recorded replay attestation and outcome verdict.",
        payload_ref=f"attestation:{attestation.attestation_id}",
        side_effect_key="decision-log-replay:attestation",
        log_path=logs["transitions"],
    )
    set_run_state(
        run.run_id,
        actor="role.support_manager",
        state="completed",
        log_path=logs["transitions"],
    )
    bundle = build_governed_run_attestation_bundle(
        run.run_id,
        transition_log_path=logs["transitions"],
        action_attestation_log_path=logs["attestations"],
        outcome_links_log_path=logs["outcomes"],
        authority_root=root,
    )
    bundle_payload = governed_run_bundle_to_dict(bundle)
    bundle_validation_errors = validate_governed_run_bundle_payload(bundle_payload)
    bundle_summary = governed_run_bundle_summary(bundle)
    bundle_ok = not bundle_validation_errors and bundle_summary["verdict"] == "passed"
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
            "bundle_verdict": bundle_summary["verdict"],
            "verdict": "passed" if review_ready == 1 and blocked == 1 and bundle_ok else "failed",
        },
        "candidate_proposer": {
            "safe_status": safe_proposal.status,
            "safe_contexts": len(safe_proposal.candidate_action_by_context),
            "unsafe_status": unsafe_proposal.status,
            "unsafe_rejected_contexts": len(unsafe_proposal.rejected_contexts),
        },
        "replayed_packets": sorted(packet_rows, key=lambda row: row["candidate_policy_id"]),
        "governed_run_bundle": bundle_summary,
        "bundle_validation": {
            "ok": not bundle_validation_errors,
            "errors": bundle_validation_errors,
        },
        "governed_run_attestation": bundle_payload,
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
            "governed_run_bundle": payload["governed_run_bundle"],
            "bundle_validation": payload["bundle_validation"],
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
