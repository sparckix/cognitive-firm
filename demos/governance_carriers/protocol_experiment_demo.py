#!/usr/bin/env python3
"""No-cost demo for governed protocol experiment evidence."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request  # noqa: E402
from cognitive_firm.orchestration.governance_changes import REQUIRED_INVARIANTS  # noqa: E402
from cognitive_firm.orchestration.protocol_experiments import (  # noqa: E402
    build_protocol_experiment_report,
    protocol_experiment_resource,
    record_protocol_observation,
    start_protocol_experiment,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


def _passing_invariant_checks() -> list[dict[str, object]]:
    return [
        {
            "invariant": invariant,
            "status": "pass",
            "rationale": f"{invariant} preserved by review-only protocol promotion.",
            "evidence_refs": [f"demo:protocol_experiment:{invariant}"],
        }
        for invariant in sorted(REQUIRED_INVARIANTS)
    ]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-protocol-experiment-") as raw:
        root = Path(raw)
        log = root / "protocol_experiments.jsonl"
        config = KernelServiceConfig(
            org_dir=root / "org",
            protocol_experiments_log=log,
            transition_log=root / "transitions.jsonl",
        )
        experiment = start_protocol_experiment(
            objective="select a coordination pattern for evidence-repair work",
            owner_role="role.org_evolver",
            candidate_protocols=["coordinator", "sequential", "batched_sequential"],
            baseline_protocol="coordinator",
            tenant_id="demo",
            project_id="self_evolving_org",
            log_path=log,
        )
        samples = [
            ("coordinator", "work://baseline-1", 0.64, 4, 4),
            ("coordinator", "work://baseline-2", 0.66, 4, 5),
            ("sequential", "work://sequential-1", 0.74, 3, 3),
            ("sequential", "work://sequential-2", 0.76, 3, 3),
            ("batched_sequential", "work://batched-1", 0.88, 2, 2),
            ("batched_sequential", "work://batched-2", 0.86, 2, 2),
        ]
        for protocol, task_ref, quality, latency, cost in samples:
            experiment = record_protocol_observation(
                experiment_id=experiment.experiment_id,
                protocol=protocol,
                task_ref=task_ref,
                quality_score=quality,
                latency_units=latency,
                cost_units=cost,
                evidence_refs=[f"bundle://{task_ref.removeprefix('work://')}"],
                log_path=log,
            )
        experiment = build_protocol_experiment_report(
            experiment_id=experiment.experiment_id,
            proposed_by="role.org_evolver",
            target_ref="protocol://evidence-repair-routing",
            min_observations_per_protocol=2,
            min_quality_delta=0.05,
            log_path=log,
        )
        report = experiment.reports[-1]
        resource_errors = validate_resource(protocol_experiment_resource(experiment).as_dict())
        candidates = dispatch_kernel_request(
            "GET",
            "/kernel/learning-transition-candidates?source=protocol_experiment",
            config=config,
        )
        protocol_candidates = [
            candidate
            for candidate in candidates.payload.get("candidates", [])
            if f"protocol_experiment:{experiment.experiment_id}"
            in candidate.get("source_refs", [])
        ]
        candidate = protocol_candidates[0] if protocol_candidates else None
        promoted = None
        decision = None
        if candidate is not None:
            governance_candidate = report["governance_change_candidate"]
            promoted = dispatch_kernel_request(
                "POST",
                f"/kernel/learning-transition-candidates/{candidate['candidate_id']}/governance-change",
                {
                    "source": "protocol_experiment",
                    "change_kind": governance_candidate["change_kind"],
                    "title": governance_candidate["title"],
                    "target_ref": governance_candidate["target_ref"],
                    "proposed_by": governance_candidate["proposed_by"],
                    "expected_behavior_change": governance_candidate[
                        "expected_behavior_change"
                    ],
                    "risk_summary": governance_candidate["risk_summary"],
                    "rollback_plan": governance_candidate["rollback_plan"],
                    "owner_role": "role.principal",
                    "tenant_id": "demo",
                    "project_id": "self_evolving_org",
                    "invariant_checks": _passing_invariant_checks(),
                    "metadata": {
                        "demo": "protocol_experiment",
                        "recommended_protocol": report["recommended_protocol"],
                        "review_queue": "governance",
                    },
                },
                config=config,
            )
            if promoted.status == 201 and promoted.payload["proposal"]["status"] == "review_ready":
                proposal_id = promoted.payload["proposal"]["proposal_id"]
                decision = dispatch_kernel_request(
                    "POST",
                    f"/kernel/governance-changes/{proposal_id}/decision",
                    {
                        "decision": "approve",
                        "reason": (
                            "No-cost demo approval for a bounded protocol "
                            "recommendation; routing is not auto-mutated."
                        ),
                    },
                    config=config,
                )

        proposal = promoted.payload["proposal"] if promoted and promoted.status == 201 else {}
        decision_result = (
            decision.payload["result"] if decision and decision.status == 200 else {}
        )
        governed_promotion_ok = (
            candidate is not None
            and promoted is not None
            and promoted.status == 201
            and proposal.get("status") == "review_ready"
            and decision is not None
            and decision.status == 200
            and decision_result.get("decision") == "approve"
        )

    payload = {
        "demo": "protocol_experiment",
        "no_external_calls": True,
        "summary": {
            "experiment_status": experiment.status,
            "observations": len(experiment.observations),
            "report_status": report["status"],
            "recommended_protocol": report["recommended_protocol"],
            "governance_candidate_kind": report["governance_change_candidate"].get("change_kind"),
            "learning_candidate_id": candidate.get("candidate_id") if candidate else None,
            "proposal_id": proposal.get("proposal_id"),
            "proposal_status": proposal.get("status"),
            "decision": decision_result.get("decision"),
            "approval_event_id": decision_result.get("event_id"),
            "governed_promotion_ok": governed_promotion_ok,
            "resource_schema_ok": not resource_errors,
            "verdict": (
                "passed"
                if report["status"] == "review_ready"
                and report["recommended_protocol"] == "batched_sequential"
                and governed_promotion_ok
                and not resource_errors
                else "failed"
            ),
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["summary"]["verdict"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
