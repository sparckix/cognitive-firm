from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request  # noqa: E402
from cognitive_firm.orchestration.action_impact import context_signature  # noqa: E402
from cognitive_firm.orchestration.governance_changes import REQUIRED_INVARIANTS  # noqa: E402
from cognitive_firm.orchestration.state_backends import SqliteMutationBackend  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exercise the local kernel service against temporary state.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the smoke JSON summary. Stdout is still written.",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="cognitive-firm-kernel-smoke-") as raw:
        root = Path(raw)
        backend = SqliteMutationBackend(root / "mutations.sqlite3")
        actor_context = {
            "actor_id": "human.alice",
            "actor_kind": "human",
            "role_id": "role.manager",
            "surface": "kernel_service_smoke",
        }
        config = KernelServiceConfig(
            human_work_log=root / "human_work.jsonl",
            accountability_cases_log=root / "accountability_cases.jsonl",
            actor_identity_log=root / "actors.jsonl",
            leases_log=root / "leases.jsonl",
            org_dir=root / "org",
            gates_dir=root / "workspace" / "gates" / "pending",
            gates_resolved_dir=root / "workspace" / "gates" / "resolved",
            transition_log=root / "workspace" / "transitions.jsonl",
            action_attestation_log=root / "org" / "attestations" / "action_attestations.jsonl",
            formal_verification_log=root / "org" / "attestations" / "formal_verifications.jsonl",
            trace_events_log=root / "org" / "multi_agent_traces" / "trace_events.jsonl",
            attribution_packets_log=root
            / "org"
            / "multi_agent_traces"
            / "attribution_packets.jsonl",
            phase_execution_log=root / "org" / "phase_execution" / "phase_execution.jsonl",
            protocol_experiments_log=root
            / "org"
            / "protocol_experiments"
            / "protocol_experiments.jsonl",
            capability_signals_log=root / "org" / "capability_signals" / "capability_signals.jsonl",
            decision_aggregation_log=root
            / "org"
            / "decision_aggregation"
            / "decision_aggregation_cases.jsonl",
            action_impact_summary=root / "org" / "action_impact" / "action_impact_summary.json",
            policy_evaluations_log=root / "org" / "action_impact" / "policy_evaluations.jsonl",
            policy_promotion_packets_log=root
            / "org"
            / "action_impact"
            / "policy_promotion_packets.jsonl",
            outcome_links_log=root / "org" / "outcome_links" / "outcome_links.jsonl",
            routine_reviews_log=root / "org" / "routine_reviews" / "routine_reviews.jsonl",
            learning_events_log=root / "org" / "learning_events" / "learning_events.jsonl",
            learning_encounters_log=root
            / "org"
            / "learning_events"
            / "learning_event_encounters.jsonl",
            mutation_backend=backend,
        )

        health = dispatch_kernel_request("GET", "/health", config=config)
        _assert_status(health.status, 200, "health")

        lease = dispatch_kernel_request(
            "POST",
            "/kernel/leases",
            {
                "resource_ref": "smoke:resource",
                "ttl_seconds": 60,
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(lease.status, 201, "lease")
        lease_record = lease.payload["lease"]

        accepted = dispatch_kernel_request(
            "POST",
            "/kernel/mutation-events",
            {
                "stream": "transitions",
                "resource_ref": "smoke:resource",
                "lease_id": lease_record["lease_id"],
                "fencing_token": lease_record["fencing_token"],
                "event": {"event": "smoke.mutation.accepted"},
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(accepted.status, 201, "guarded append")

        rejected = dispatch_kernel_request(
            "POST",
            "/kernel/mutation-events",
            {
                "stream": "transitions",
                "resource_ref": "smoke:resource",
                "lease_id": lease_record["lease_id"],
                "fencing_token": lease_record["fencing_token"] + 1,
                "event": {"event": "smoke.mutation.stale"},
                "actor_context": actor_context,
            },
            config=config,
        )
        if rejected.status != 400:
            raise AssertionError(f"stale fencing unexpectedly accepted: {rejected.payload}")

        events = backend.read_events("transitions")
        if len(events) != 1 or events[0]["event"] != "smoke.mutation.accepted":
            raise AssertionError(f"unexpected events: {events}")

        governance_proposal = dispatch_kernel_request(
            "POST",
            "/kernel/governance-changes",
            {
                "change_kind": "mandate_change",
                "title": "Clarify smoke-test mandate",
                "target_ref": "org/mandates/smoke.md",
                "rationale": "Smoke verifies the governed proposal path.",
                "source_refs": ["smoke:mutation.accepted"],
                "expected_behavior_change": "Future smoke work uses the clarified mandate.",
                "risk_summary": "No authority expansion; test-only workspace.",
                "rollback_plan": "Delete the temp workspace.",
                "invariant_checks": [
                    {
                        "invariant": invariant,
                        "status": "pass",
                        "rationale": f"{invariant} preserved by test fixture.",
                        "evidence_refs": [f"smoke:{invariant}"],
                    }
                    for invariant in sorted(REQUIRED_INVARIANTS)
                ],
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(governance_proposal.status, 201, "governance proposal")
        proposal_id = governance_proposal.payload["proposal"]["proposal_id"]
        if governance_proposal.payload["proposal"]["status"] != "review_ready":
            raise AssertionError(
                f"proposal not review-ready: {governance_proposal.payload}"
            )

        governance_resource = dispatch_kernel_request(
            "GET",
            f"/kernel/governance-changes/{proposal_id}?resource=true",
            config=config,
        )
        _assert_status(governance_resource.status, 200, "governance resource")
        if governance_resource.payload["proposal"]["kind"] != "GovernanceChangeProposal":
            raise AssertionError(
                f"unexpected governance resource: {governance_resource.payload}"
            )

        governance_decision = dispatch_kernel_request(
            "POST",
            f"/kernel/governance-changes/{proposal_id}/decision",
            {
                "decision": "approve",
                "reason": "smoke test approval",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(governance_decision.status, 200, "governance decision")
        run = dispatch_kernel_request(
            "POST",
            "/kernel/runs",
            {
                "owner_role": "role.manager",
                "objective": "smoke governed-run bundle route",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(run.status, 201, "run start")
        run_id = run.payload["run"]["run_id"]
        attestation = dispatch_kernel_request(
            "POST",
            "/kernel/action-attestations",
            {
                "subject_kind": "artifact",
                "subject_ref": "workspace/smoke-report.md",
                "subject_digest": _digest_text("smoke report"),
                "producer": "role.manager",
                "action_type": "write_artifact",
                "verification_status": "verified",
                "run_id": run_id,
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(attestation.status, 201, "action attestation create")
        run_done = dispatch_kernel_request(
            "POST",
            f"/kernel/runs/{run_id}/state",
            {
                "state": "completed",
                "actor": "role.manager",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(run_done.status, 200, "run complete")
        bundle = dispatch_kernel_request(
            "POST",
            "/kernel/governed-run-bundles/build?summary=true",
            {
                "run_id": run_id,
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(bundle.status, 200, "governed-run bundle build")
        if bundle.payload["summary"]["verdict"] != "passed":
            raise AssertionError(f"bundle did not pass: {bundle.payload}")
        _seed_closed_loop_provenance_records(
            config=config,
            actor_context=actor_context,
            run_id=run_id,
            proposal_id=proposal_id,
            attestation_id=attestation.payload["action_attestation"]["attestation_id"],
        )
        provenance_report_counts = _check_provenance_report_route(
            config=config,
            run_id=run_id,
        )
        proof = dispatch_kernel_request(
            "POST",
            "/kernel/mutation-proofs/build",
            {
                "step_id": "kernel_service_smoke",
                "change_kind": "mandate_change",
                "target_ref": "org/mandates/smoke.md",
                "run_id": "run_smoke",
                "work_id": "work_smoke",
                "proposal_id": proposal_id,
                "approval_event_id": governance_decision.payload["result"]["event_id"],
                "mutation_ref": "file://org/mandates/smoke.md",
                "attestation_id": "aat_smoke",
                "learning_event_id": "learn_smoke",
                "outcome_link_id": "olink_smoke",
                "routine_review_id": "rrev_smoke",
                "bundle_id": "gab_run_smoke",
                "bundle_digest": "sha256:" + "d" * 64,
                "bundle_verdict": "passed",
                "commit_sha": "smokecommit",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(proof.status, 200, "mutation proof build")
        proof_validation = dispatch_kernel_request(
            "POST",
            "/kernel/mutation-proofs/validate",
            {
                "proof": proof.payload["proof"],
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(proof_validation.status, 200, "mutation proof validate")
        if not proof_validation.payload["valid"]:
            raise AssertionError(f"mutation proof failed: {proof_validation.payload}")

        human_work_pressure_counts = _seed_and_check_human_work_pressure_routes(
            config=config,
            actor_context=actor_context,
        )
        human_speed_envelope_counts = _check_human_speed_envelope_route(
            config=config,
        )
        execution_projection_counts = _seed_and_check_execution_carrier_routes(
            config=config,
            actor_context=actor_context,
        )
        action_impact_counts = _seed_and_check_action_impact_routes(
            config=config,
            actor_context=actor_context,
        )
        prediction_review_counts = _seed_and_check_prediction_review_routes(
            config=config,
            actor_context=actor_context,
        )

        rendered = json.dumps(
            {
                "ok": True,
                "service": health.payload["service"],
                "backend": backend.connector_id,
                "accepted_events": len(events),
                "governance_proposal_status": governance_proposal.payload[
                    "proposal"
                ]["status"],
                "governance_decision": governance_decision.payload["result"][
                    "decision"
                ],
                "human_work_pressure_counts": human_work_pressure_counts,
                "human_speed_envelope_counts": human_speed_envelope_counts,
                "execution_projection_counts": execution_projection_counts,
                "action_impact_counts": action_impact_counts,
                "prediction_review_counts": prediction_review_counts,
                "provenance_report_counts": provenance_report_counts,
                "governed_run_bundle_verdict": bundle.payload["summary"]["verdict"],
                "mutation_proof_validated": proof_validation.payload["valid"],
                "stale_rejected": True,
            },
            sort_keys=True,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
    return 0


def _check_human_speed_envelope_route(config: KernelServiceConfig) -> dict[str, object]:
    envelope = dispatch_kernel_request(
        "GET",
        (
            "/kernel/human-speed-envelope?"
            "risk_tier=irreversible&"
            "bottleneck_class=authority&"
            "deployment_class=external_write&"
            "external_side_effect=true"
        ),
        config=config,
    )
    _assert_status(envelope.status, 200, "human-speed envelope")
    row = envelope.payload["envelope"]
    if row["schema"] != "human_speed_envelope.v1":
        raise AssertionError(f"unexpected human-speed schema: {envelope.payload}")
    if row["speed_class"] != "gate_before_action":
        raise AssertionError(f"unexpected human-speed class: {envelope.payload}")
    if row["required_record"] != "policy_decision_or_gate_plus_lease":
        raise AssertionError(f"unexpected human-speed record: {envelope.payload}")
    boundary = row.get("boundary") or {}
    if boundary.get("does_not_dispatch_work") is not True:
        raise AssertionError(f"human-speed boundary weakened: {envelope.payload}")

    return {
        "schema": row["schema"],
        "speed_class": row["speed_class"],
        "required_record": row["required_record"],
        "observer_only": envelope.payload["observer_only"],
        "dispatch_boundary": boundary["does_not_dispatch_work"],
    }


def _seed_closed_loop_provenance_records(
    *,
    config: KernelServiceConfig,
    actor_context: dict[str, str],
    run_id: str,
    proposal_id: str,
    attestation_id: str,
) -> None:
    learning = dispatch_kernel_request(
        "POST",
        "/kernel/learning-events",
        {
            "learning_unit_kind": "routine_change",
            "decision_use": "Treat governed smoke runs as reviewable evidence chains.",
            "future_application_cue": "governed run review",
            "approved_by": "role.manager",
            "approval_ref": f"governance_change:{proposal_id}",
            "source_carrier_refs": [
                run_id,
                f"run:{run_id}",
                f"action_attestation:{attestation_id}",
            ],
            "owner_role": "role.manager",
            "metadata": {"run_id": run_id, "proposal_id": proposal_id},
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(learning.status, 201, "learning event create")
    learning_event_id = learning.payload["learning_event"]["learning_event_id"]

    outcome = dispatch_kernel_request(
        "POST",
        "/kernel/outcome-links",
        {
            "change_ref": f"run:{run_id}",
            "change_kind": "governed_run",
            "learning_event_id": learning_event_id,
            "metric_name": "reviewability",
            "metric_unit": "verdict",
            "created_by": "role.manager",
            "owner_role": "role.manager",
            "metadata": {"run_id": run_id, "proposal_id": proposal_id},
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(outcome.status, 201, "outcome link create")
    outcome_link_id = outcome.payload["outcome_link"]["outcome_link_id"]

    for kind, value in (("baseline", 0.0), ("post", 1.0)):
        snapshot = dispatch_kernel_request(
            "POST",
            f"/kernel/outcome-links/{outcome_link_id}/snapshots",
            {
                "kind": kind,
                "value": value,
                "captured_by": "role.manager",
                "measurement_ref": f"smoke:reviewability:{kind}",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(snapshot.status, 200, f"outcome {kind} snapshot")

    verdict = dispatch_kernel_request(
        "POST",
        f"/kernel/outcome-links/{outcome_link_id}/verdict",
        {
            "verdict": "improved",
            "rationale": "The run now carries a compact provenance handoff.",
            "recorded_by": "role.manager",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(verdict.status, 200, "outcome verdict record")

    review = dispatch_kernel_request(
        "POST",
        "/kernel/routine-reviews",
        {
            "routine_ref": f"learning_event:{learning_event_id}",
            "routine_kind": "learning_event",
            "learning_event_id": learning_event_id,
            "review_due_utc": "2030-01-01T00:00:00+00:00",
            "scheduled_by": "role.manager",
            "reason": "Verify that the smoke learning still improves reviewability.",
            "metadata": {"run_id": run_id, "proposal_id": proposal_id},
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(review.status, 201, "routine review schedule")

    encounter = dispatch_kernel_request(
        "POST",
        "/kernel/learning-event-encounters",
        {
            "learning_event_id": learning_event_id,
            "role": "role.manager",
            "cue": "governed run review",
            "outcome": "applied",
            "work_ref": f"run:{run_id}",
            "evidence_refs": [
                f"outcome_link:{outcome_link_id}",
                f"action_attestation:{attestation_id}",
            ],
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(encounter.status, 201, "learning-use receipt")


def _check_provenance_report_route(
    *,
    config: KernelServiceConfig,
    run_id: str,
) -> dict[str, object]:
    report_response = dispatch_kernel_request(
        "GET",
        f"/kernel/provenance-report?run_id={run_id}&event_limit=4",
        config=config,
    )
    _assert_status(report_response.status, 200, "provenance report")
    report = report_response.payload["report"]
    if report["read_only"] is not True or report["projection_only"] is not True:
        raise AssertionError(f"provenance report is not projection-only: {report}")
    if report["report_kind"] != "provenance_handoff":
        raise AssertionError(f"unexpected provenance report kind: {report}")
    source_counts = report["summary"]["source_counts"]
    if source_counts.get("action_attestations") != 1:
        raise AssertionError(f"attestation missing from provenance report: {report}")
    if report["summary"]["event_count"] < 3:
        raise AssertionError(f"too few provenance events: {report}")
    if "# Provenance Report" not in report["markdown"]:
        raise AssertionError(f"markdown export missing: {report}")
    if "## Follow-Through" not in report["markdown"]:
        raise AssertionError(f"markdown follow-through missing: {report}")
    follow = report["follow_through"]
    if follow["status"] != "closed_loop_observed":
        raise AssertionError(f"closed-loop follow-through missing: {report}")
    if follow["outcome_links"] < 1 or follow["routine_reviews"] < 1:
        raise AssertionError(f"outcome/review follow-through missing: {report}")
    if follow["learning_events"] < 1 or follow["learning_use_receipts"] < 1:
        raise AssertionError(f"learning follow-through missing: {report}")
    refs = {row["ref"] for row in report["evidence_refs"]}
    if "workspace/smoke-report.md" not in refs:
        raise AssertionError(f"artifact ref missing from provenance report: {report}")
    return {
        "provenance_report_events": report["summary"]["event_count"],
        "provenance_report_refs": len(report["evidence_refs"]),
        "provenance_report_coverage": report["coverage"]["status"],
        "provenance_follow_through": follow["status"],
        "provenance_outcome_links": follow["outcome_links"],
        "provenance_routine_reviews": follow["routine_reviews"],
        "provenance_learning_events": follow["learning_events"],
        "provenance_learning_use_receipts": follow["learning_use_receipts"],
    }


def _seed_and_check_human_work_pressure_routes(
    *,
    config: KernelServiceConfig,
    actor_context: dict[str, str],
) -> dict[str, object]:
    for index in range(3):
        response = dispatch_kernel_request(
            "POST",
            "/kernel/human-work",
            {
                "coordination_pattern": "a2h_work_request",
                "requested_by": "role.researcher",
                "human_actor": f"human.source_reviewer_{index}",
                "objective": f"Check restricted source {index}.",
                "work_mode": "source_check",
                "bottleneck_class": "access",
                "human_deliverable": "bounded source receipt",
                "tenant_id": "tenant-smoke",
                "project_id": "project-smoke",
                "receipt_required": True,
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(response.status, 201, "human-work create")

    pressure = dispatch_kernel_request(
        "GET",
        "/kernel/human-work-pressure?tenant_id=tenant-smoke&project_id=project-smoke",
        config=config,
    )
    _assert_status(pressure.status, 200, "human-work pressure")
    pressure_groups = pressure.payload["pressure"]
    if len(pressure_groups) != 1:
        raise AssertionError(f"unexpected human-work pressure: {pressure.payload}")
    if pressure_groups[0]["missing_receipt_count"] != 3:
        raise AssertionError(f"missing receipt pressure absent: {pressure.payload}")

    candidates = dispatch_kernel_request(
        "GET",
        "/kernel/learning-transition-candidates?source=human_work",
        config=config,
    )
    _assert_status(candidates.status, 200, "human-work learning candidates")
    candidate_rows = candidates.payload["candidates"]
    if len(candidate_rows) != 1:
        raise AssertionError(f"unexpected human-work candidates: {candidates.payload}")
    candidate = candidate_rows[0]
    if candidate["source_kind"] != "a2h_pressure":
        raise AssertionError(f"wrong human-work candidate kind: {candidates.payload}")

    promoted = dispatch_kernel_request(
        "POST",
        f"/kernel/learning-transition-candidates/{candidate['candidate_id']}/governance-change",
        {
            "source": "human_work",
            "target_ref": "org/policies/smoke-source-access.md",
            "proposed_by": "role.researcher",
            "expected_behavior_change": (
                "Review repeated source-access pressure before future routing changes."
            ),
            "risk_summary": "May over-automate useful human source checks.",
            "rollback_plan": "Discard the temporary smoke proposal.",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(promoted.status, 201, "human-work candidate promotion")
    promotion_status = promoted.payload["proposal"]["status"]
    if promotion_status != "blocked":
        raise AssertionError(
            f"human-work candidate should remain blocked without invariants: {promoted.payload}"
        )

    return {
        "a2h_pressure_groups": len(pressure_groups),
        "human_work_learning_candidates": len(candidate_rows),
        "human_work_candidate_promotion": promotion_status,
    }


def _seed_and_check_execution_carrier_routes(
    config: KernelServiceConfig,
    actor_context: dict[str, object],
) -> dict[str, int]:
    trace_write = dispatch_kernel_request(
        "POST",
        "/kernel/multi-agent-trace-events",
        {
            "runtime_name": "kernel_service_smoke_runtime",
            "external_run_id": "external_smoke",
            "cognitive_run_id": "run_smoke",
            "events": [
                {
                    "event_id": "mate_smoke_root",
                    "event_kind": "agent_spawned",
                    "agent_id": "agent.root",
                    "summary": "Root agent spawned worker.",
                },
                {
                    "event_id": "mate_smoke_worker",
                    "event_kind": "abstention",
                    "agent_id": "agent.worker",
                    "parent_agent_id": "agent.root",
                    "status": "abstained",
                    "summary": "Worker abstained because evidence was missing.",
                },
            ],
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(trace_write.status, 201, "trace event write")

    packet_write = dispatch_kernel_request(
        "POST",
        "/kernel/failure-attribution-packets",
        {
            "runtime_name": "kernel_service_smoke_runtime",
            "external_run_id": "external_smoke",
            "source_event_ids": ["mate_smoke_root", "mate_smoke_worker"],
            "failure_summary": "Worker abstention exposed an evidence routing gap.",
            "proposed_carrier_kind": "learning_transition",
            "owner_role": "role.evaluator",
            "risk_summary": "Observer-only carrier.",
            "rollback_plan": "Discard carrier if review rejects it.",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(packet_write.status, 201, "failure attribution write")

    phase_write = dispatch_kernel_request(
        "POST",
        "/kernel/phase-execution-plans",
        {
            "objective": "Separate planning, execution, and verification for smoke work.",
            "owner_role": "role.executor",
            "plan_id": "pex_smoke",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(phase_write.status, 201, "phase execution write")

    experiment_write = dispatch_kernel_request(
        "POST",
        "/kernel/protocol-experiments",
        {
            "objective": "Compare coordination protocols for smoke work.",
            "owner_role": "role.evaluator",
            "candidate_protocols": ["coordinator", "sequential"],
            "baseline_protocol": "sequential",
            "experiment_id": "pexp_smoke",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(experiment_write.status, 201, "protocol experiment write")
    for protocol, score in (
        ("sequential", 0.70),
        ("sequential", 0.72),
        ("coordinator", 0.84),
        ("coordinator", 0.86),
    ):
        observation_write = dispatch_kernel_request(
            "POST",
            "/kernel/protocol-experiments/pexp_smoke/observations",
            {
                "protocol": protocol,
                "task_ref": f"task:{protocol}:{score}",
                "quality_score": score,
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(observation_write.status, 201, "protocol observation write")
    report_write = dispatch_kernel_request(
        "POST",
        "/kernel/protocol-experiments/pexp_smoke/reports",
        {
            "proposed_by": "role.evaluator",
            "target_ref": "route_policy:smoke",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(report_write.status, 201, "protocol report write")

    signal_write = dispatch_kernel_request(
        "POST",
        "/kernel/capability-signals",
        {
            "signal_kind": "abstention",
            "source_ref": "run:run_smoke",
            "summary": "Agent abstained because evidence was missing.",
            "owner_role": "role.evaluator",
            "severity": "warning",
            "recommended_route": "request_evidence",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(signal_write.status, 201, "capability signal write")

    execution_route = dispatch_kernel_request(
        "POST",
        "/kernel/execution-evidence/route",
        {
            "signal_id": "csig_smoke_route",
            "signal_kind": "capability_gap",
            "source_ref": "agent_runtime:kernel_service_smoke",
            "summary": "Planner abstained because the smoke role lacked a capability.",
            "owner_role": "role.evaluator",
            "severity": "blocking",
            "worker_ref": "actor.smoke-agent",
            "run_id": "run_smoke",
            "work_id": "work_smoke",
            "capability_ref": "capability:smoke",
            "route_kind": "open_learning_candidate",
            "routed_by": "role.evaluator",
            "route_rationale": "Review future smoke routing before retry.",
            "evidence_refs": ["phase_execution_plan:pex_smoke"],
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(execution_route.status, 201, "execution evidence route")
    if execution_route.payload["proposal"] is not None:
        raise AssertionError(
            f"execution route unexpectedly opened proposal: {execution_route.payload}"
        )
    if execution_route.payload["learning_candidate"] is None:
        raise AssertionError(
            f"execution route did not expose a learning candidate: {execution_route.payload}"
        )

    decision_case = dispatch_kernel_request(
        "POST",
        "/kernel/decision-aggregation-cases",
        {
            "subject_ref": "governance_change:gcp_smoke_packet_record",
            "decision_class": "structural_change",
            "scope_kind": "project",
            "scope_ref": "proj.smoke",
            "procedure_kind": "quorum_majority",
            "opened_by": "role.principal",
            "eligibility_basis": "smoke quorum review",
            "eligible_roles": [
                "role.principal",
                "role.evaluator",
                "role.risk_guardian",
                "role.learning_steward",
            ],
            "quorum": 4,
            "evidence_refs": ["phase_execution_plan:pex_smoke"],
            "case_id": "dac_smoke_quorum_gap",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(decision_case.status, 201, "decision aggregation case")
    for role_id, position in (
        ("role.principal", "approve"),
        ("role.evaluator", "approve"),
        ("role.risk_guardian", "abstain"),
        ("role.learning_steward", "approve"),
    ):
        position_response = dispatch_kernel_request(
            "POST",
            "/kernel/decision-aggregation-cases/dac_smoke_quorum_gap/positions",
            {
                "actor_id": f"agent.{role_id.rsplit('.', 1)[-1]}",
                "role_id": role_id,
                "position": position,
                "rationale": f"{role_id} records {position} for smoke.",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(position_response.status, 200, "decision position")
    decision_compute = dispatch_kernel_request(
        "POST",
        "/kernel/decision-aggregation-cases/dac_smoke_quorum_gap/compute",
        {"actor_context": actor_context},
        config=config,
    )
    _assert_status(decision_compute.status, 200, "decision aggregation compute")
    if decision_compute.payload["decision_aggregation_case"]["status"] != "escalated":
        raise AssertionError(
            f"smoke decision case did not escalate: {decision_compute.payload}"
        )
    decision_route = dispatch_kernel_request(
        "POST",
        "/kernel/decision-aggregation-cases/dac_smoke_quorum_gap/route-escalation",
        {
            "signal_id": "csig_smoke_quorum_gap",
            "summary": "Smoke reviewer quorum failed after one abstention.",
            "route_kind": "open_learning_candidate",
            "routed_by": "role.evaluator",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(decision_route.status, 201, "decision escalation route")
    if decision_route.payload["signal"]["status"] != "routed":
        raise AssertionError(
            f"decision escalation did not route signal: {decision_route.payload}"
        )
    if decision_route.payload["boundary"]["resolved_decision"]:
        raise AssertionError(
            f"decision escalation unexpectedly resolved decision: {decision_route.payload}"
        )

    trace_response = dispatch_kernel_request(
        "GET",
        "/kernel/multi-agent-trace-events?runtime_name=kernel_service_smoke_runtime&resource=true",
        config=config,
    )
    _assert_status(trace_response.status, 200, "trace event projection")
    trace_count = len(trace_response.payload["trace_events"])
    if trace_count != 2:
        raise AssertionError(f"unexpected trace event projection: {trace_response.payload}")

    graph_response = dispatch_kernel_request(
        "GET",
        "/kernel/delegation-graph?runtime_name=kernel_service_smoke_runtime&external_run_id=external_smoke",
        config=config,
    )
    _assert_status(graph_response.status, 200, "delegation graph projection")
    if graph_response.payload["graph"]["diagnostics"]["abstentions"] != 1:
        raise AssertionError(f"unexpected graph diagnostics: {graph_response.payload}")

    packet_response = dispatch_kernel_request(
        "GET",
        "/kernel/failure-attribution-packets?status=review_ready&resource=true",
        config=config,
    )
    _assert_status(packet_response.status, 200, "failure attribution projection")
    packet_count = len(packet_response.payload["packets"])
    if packet_count != 1:
        raise AssertionError(f"unexpected attribution projection: {packet_response.payload}")

    phase_response = dispatch_kernel_request(
        "GET",
        "/kernel/phase-execution-plans?resource=true",
        config=config,
    )
    _assert_status(phase_response.status, 200, "phase execution projection")
    phase_count = len(phase_response.payload["plans"])
    if phase_count != 1:
        raise AssertionError(f"unexpected phase projection: {phase_response.payload}")

    experiment_response = dispatch_kernel_request(
        "GET",
        "/kernel/protocol-experiments?resource=true",
        config=config,
    )
    _assert_status(experiment_response.status, 200, "protocol experiment projection")
    experiment_count = len(experiment_response.payload["experiments"])
    if experiment_count != 1:
        raise AssertionError(f"unexpected protocol projection: {experiment_response.payload}")

    signal_response = dispatch_kernel_request(
        "GET",
        "/kernel/capability-signals?summary=true",
        config=config,
    )
    _assert_status(signal_response.status, 200, "capability signal projection")
    signal_count = int(signal_response.payload["summary"]["n_signals"])
    if signal_count != 3:
        raise AssertionError(f"unexpected capability signal summary: {signal_response.payload}")

    candidate_response = dispatch_kernel_request(
        "GET",
        "/kernel/learning-transition-candidates?source=execution",
        config=config,
    )
    _assert_status(candidate_response.status, 200, "execution learning candidate projection")
    candidate_count = int(candidate_response.payload["n_candidates"])
    source_kinds = {
        candidate["source_kind"]
        for candidate in candidate_response.payload["candidates"]
    }
    expected_source_kinds = {
        "multi_agent_failure_attribution",
        "capability_signal",
        "protocol_experiment_report",
    }
    if candidate_count != 5 or source_kinds != expected_source_kinds:
        raise AssertionError(
            f"unexpected execution learning candidates: {candidate_response.payload}"
        )
    candidate_id = candidate_response.payload["candidates"][0]["candidate_id"]
    candidate_promotion = dispatch_kernel_request(
        "POST",
        f"/kernel/learning-transition-candidates/{candidate_id}/governance-change",
        {
            "source": "execution",
            "target_ref": "org/mandates/smoke-evaluator.md",
            "proposed_by": "role.evaluator",
            "expected_behavior_change": "Future smoke evaluator work requires clearer source evidence.",
            "risk_summary": "Narrows review behavior and does not expand authority.",
            "rollback_plan": "Discard the temporary smoke proposal.",
            "invariant_checks": [
                {
                    "invariant": invariant,
                    "status": "pass",
                    "rationale": f"{invariant} preserved by execution-candidate smoke.",
                    "evidence_refs": [f"smoke:candidate:{invariant}"],
                }
                for invariant in sorted(REQUIRED_INVARIANTS)
            ],
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(candidate_promotion.status, 201, "candidate governance promotion")
    candidate_promotion_status = candidate_promotion.payload["proposal"]["status"]
    if candidate_promotion_status != "review_ready":
        raise AssertionError(
            f"candidate promotion not review-ready: {candidate_promotion.payload}"
        )

    return {
        "capability_signals": signal_count,
        "decision_escalation_route": decision_route.payload["signal"]["status"],
        "execution_evidence_route": execution_route.payload["signal"]["status"],
        "execution_learning_candidates": candidate_count,
        "execution_candidate_promotion": candidate_promotion_status,
        "failure_attribution_packets": packet_count,
        "phase_execution_plans": phase_count,
        "protocol_experiments": experiment_count,
        "trace_events": trace_count,
    }


def _seed_and_check_action_impact_routes(
    config: KernelServiceConfig,
    actor_context: dict[str, object],
) -> dict[str, object]:
    rows = []
    for idx in range(30):
        arm = "senior_review" if idx % 2 == 0 else "fast_lane"
        rows.append(
            {
                "action_id": f"smoke_action_{idx}",
                "action_ref": f"smoke/actions/{idx}",
                "actor": "role.support_router",
                "objective_metric": "resolution_quality",
                "status": "measured",
                "context_features": {"segment": "enterprise"},
                "action_arm": arm,
                "logging_policy_probability": 0.5,
                "counterfactual_action": "other",
                "reward": 0.9 if arm == "senior_review" else 0.6,
                "guardrail_metrics": {"sla_hours": 4.0},
            }
        )
    config.action_impact_summary.parent.mkdir(parents=True, exist_ok=True)
    config.action_impact_summary.write_text(
        json.dumps({"records": rows}, sort_keys=True),
        encoding="utf-8",
    )
    enterprise_sig = context_signature({"segment": "enterprise"}, ["segment"])
    if enterprise_sig is None:
        raise AssertionError("context signature unexpectedly missing")

    evaluation = dispatch_kernel_request(
        "POST",
        "/kernel/action-impact/policy-evaluations/evaluate",
        {
            "candidate_policy_id": "policy.smoke.enterprise-review",
            "candidate_policy_ref": "policy://smoke/enterprise-review",
            "candidate_action_by_context": {enterprise_sig: "senior_review"},
            "context_keys": ["segment"],
            "objective_metric": "resolution_quality",
            "min_matched": 10,
            "min_support_coverage": 0.4,
            "evidence_refs": ["action_impact_summary:smoke"],
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(evaluation.status, 201, "action-impact policy evaluation")
    report = evaluation.payload["policy_evaluation"]
    if report["status"] != "promotable" or report["n_matched"] != 15:
        raise AssertionError(f"unexpected policy evaluation: {evaluation.payload}")

    evaluations = dispatch_kernel_request(
        "GET",
        "/kernel/action-impact/policy-evaluations?status=promotable",
        config=config,
    )
    _assert_status(evaluations.status, 200, "action-impact evaluation listing")
    evaluation_count = len(evaluations.payload["policy_evaluations"])
    if evaluation_count != 1:
        raise AssertionError(f"unexpected evaluation listing: {evaluations.payload}")

    packet = dispatch_kernel_request(
        "POST",
        "/kernel/action-impact/policy-promotion-packets",
        {
            "evaluation_id": report["evaluation_id"],
            "proposed_by": "role.governance_reviewer",
            "authority_diff_ref": "authority-diff://smoke-enterprise-review",
            "predicted_effect": {
                "metric_name": "resolution_quality",
                "metric_unit": "score",
                "direction": "higher_is_better",
                "threshold": 0.05,
                "review_horizon": "after_next_20_cases",
            },
            "evidence_refs": [
                f"action_impact_policy_evaluation:{report['evaluation_id']}"
            ],
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(packet.status, 201, "action-impact promotion packet")
    promotion_packet = packet.payload["policy_promotion_packet"]
    if promotion_packet["status"] != "review_ready":
        raise AssertionError(f"unexpected promotion packet: {packet.payload}")

    packets = dispatch_kernel_request(
        "GET",
        "/kernel/action-impact/policy-promotion-packets?status=review_ready",
        config=config,
    )
    _assert_status(packets.status, 200, "action-impact promotion packet listing")
    packet_count = len(packets.payload["policy_promotion_packets"])
    if packet_count != 1:
        raise AssertionError(f"unexpected promotion packet listing: {packets.payload}")

    proposal = dispatch_kernel_request(
        "POST",
        f"/kernel/action-impact/policy-promotion-packets/{promotion_packet['packet_id']}/governance-change",
        {
            "proposal_id": "gcp_smoke_policy_promotion",
            "owner_role": "role.governance_reviewer",
            "tenant_id": "tenant-smoke",
            "project_id": "project-smoke",
            "invariant_checks": [
                {
                    "invariant": invariant,
                    "status": "pass",
                    "rationale": f"{invariant} preserved by smoke policy-promotion route.",
                    "evidence_refs": [f"smoke:{invariant}"],
                }
                for invariant in sorted(REQUIRED_INVARIANTS)
            ],
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(proposal.status, 201, "action-impact promotion governance change")
    governance_change = proposal.payload["proposal"]
    if governance_change["status"] != "review_ready":
        raise AssertionError(f"unexpected promotion governance change: {proposal.payload}")
    if proposal.payload["boundary"] != {
        "approved_governance": False,
        "applied_policy": False,
        "executed_runtime": False,
    }:
        raise AssertionError(f"unexpected promotion boundary: {proposal.payload}")

    decision = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes/gcp_smoke_policy_promotion/decision",
        {
            "decision": "approve",
            "reason": "smoke test approves the review-ready policy promotion proposal",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(decision.status, 200, "action-impact promotion governance approval")

    outcome = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes/gcp_smoke_policy_promotion/outcome-link",
        {
            "created_by": "role.governance_reviewer",
            "outcome_link_id": "olink_smoke_policy_promotion",
            "metadata": {"smoke_route": "policy_promotion_outcome_link"},
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(outcome.status, 201, "action-impact promotion outcome link")
    outcome_link = outcome.payload["outcome_link"]
    metadata = outcome_link.get("metadata") or {}
    if metadata.get("source_policy_promotion_packet_id") != promotion_packet["packet_id"]:
        raise AssertionError(
            "policy-promotion provenance missing from outcome link: "
            f"{outcome.payload}"
        )
    if metadata.get("predicted_effect", {}).get("metric_name") != "resolution_quality":
        raise AssertionError(
            "policy-promotion predicted effect missing from outcome link: "
            f"{outcome.payload}"
        )

    return {
        "policy_evaluations": evaluation_count,
        "policy_evaluation_status": report["status"],
        "policy_promotion_packets": packet_count,
        "policy_promotion_status": promotion_packet["status"],
        "policy_promotion_governance_change_status": governance_change["status"],
        "policy_promotion_governance_decision": decision.payload["result"]["decision"],
        "policy_promotion_outcome_link": outcome_link["outcome_link_id"],
        "policy_promotion_outcome_metric": outcome_link["metric_name"],
        "policy_promotion_provenance_preserved": True,
    }


def _seed_and_check_prediction_review_routes(
    config: KernelServiceConfig,
    actor_context: dict[str, object],
) -> dict[str, object]:
    proposal = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes",
        {
            "proposal_id": "gcp_smoke_predicted",
            "change_kind": "mandate_change",
            "title": "Measure smoke evidence-gap rule",
            "target_ref": "org/mandates/smoke-evaluator.md",
            "rationale": "Smoke verifies prediction-gated mutation wiring.",
            "source_refs": ["capability_signal:csig_smoke_route"],
            "predicted_effect": {
                "metric_name": "open_gaps",
                "metric_unit": "count",
                "direction": "lower_is_better",
                "threshold": 1,
                "review_horizon": "next_routine_review",
            },
            "risk_summary": "Narrows smoke review criteria; no authority expansion.",
            "rollback_plan": "Delete the temporary smoke mandate.",
            "invariant_checks": [
                {
                    "invariant": invariant,
                    "status": "pass",
                    "rationale": f"{invariant} preserved by prediction smoke fixture.",
                    "evidence_refs": [f"smoke_prediction:{invariant}"],
                }
                for invariant in sorted(REQUIRED_INVARIANTS)
            ],
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(proposal.status, 201, "predicted governance proposal")

    unapproved_link = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes/gcp_smoke_predicted/outcome-link",
        {
            "created_by": "role.evaluator",
            "actor_context": actor_context,
        },
        config=config,
    )
    if unapproved_link.status != 409:
        raise AssertionError(
            "predicted outcome link opened before governance approval: "
            f"{unapproved_link.payload}"
        )

    decision = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes/gcp_smoke_predicted/decision",
        {
            "decision": "approve",
            "reason": "smoke test predicted mutation approval",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(decision.status, 200, "predicted governance approval")

    link = dispatch_kernel_request(
        "POST",
        "/kernel/governance-changes/gcp_smoke_predicted/outcome-link",
        {
            "created_by": "role.evaluator",
            "outcome_link_id": "olink_smoke_predicted",
            "metadata": {"smoke_route": "governance_change_outcome_link"},
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(link.status, 201, "predicted outcome link create from proposal")
    link_id = link.payload["outcome_link"]["outcome_link_id"]
    if link_id != "olink_smoke_predicted":
        raise AssertionError(f"stable outcome link id was not preserved: {link.payload}")
    metadata = link.payload["outcome_link"].get("metadata") or {}
    if metadata.get("source_recipe") != "predicted_mutation_outcome_link_request.v1":
        raise AssertionError(f"predicted outcome link did not use route recipe: {link.payload}")
    if metadata.get("predicted_effect", {}).get("metric_name") != "open_gaps":
        raise AssertionError(f"predicted effect missing from outcome link: {link.payload}")

    for kind, value in (("baseline", 3.0), ("post", 3.0)):
        snapshot = dispatch_kernel_request(
            "POST",
            f"/kernel/outcome-links/{link_id}/snapshots",
            {
                "kind": kind,
                "value": value,
                "captured_by": "role.evaluator",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(snapshot.status, 200, f"predicted outcome {kind} snapshot")

    verdict = dispatch_kernel_request(
        "POST",
        f"/kernel/outcome-links/{link_id}/verdict",
        {
            "verdict": "no_change",
            "recorded_by": "role.evaluator",
            "rationale": "Open gaps did not decrease after the governed change.",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(verdict.status, 200, "predicted outcome verdict")
    prediction_review = verdict.payload["outcome_link"]["metadata"].get("prediction_review")
    if not isinstance(prediction_review, dict) or prediction_review.get("status") != "prediction_failed":
        raise AssertionError(f"unexpected prediction review: {verdict.payload}")

    reversal_review = dispatch_kernel_request(
        "POST",
        f"/kernel/outcome-links/{link_id}/reversal-review",
        {
            "review_due_utc": "2030-01-02T00:00:00+00:00",
            "scheduled_by": "role.evaluator",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(reversal_review.status, 201, "prediction reversal review")
    review = reversal_review.payload["routine_review"]
    if review["routine_ref"] != "governance_change:gcp_smoke_predicted":
        raise AssertionError(f"unexpected reversal review: {reversal_review.payload}")
    metadata = review.get("metadata") or {}
    if metadata.get("reversal_candidate") is not True:
        raise AssertionError(f"review is not a reversal candidate: {reversal_review.payload}")

    reviews = dispatch_kernel_request(
        "GET",
        "/kernel/routine-reviews?review_cadence=prediction_failure",
        config=config,
    )
    _assert_status(reviews.status, 200, "prediction reversal review listing")
    review_count = len(
        [
            row
            for row in reviews.payload["routine_reviews"]
            if row.get("review_cadence") == "prediction_failure"
        ]
    )
    if review_count != 1:
        raise AssertionError(f"unexpected prediction review listing: {reviews.payload}")

    return {
        "outcome_links": 1,
        "prediction_review_status": prediction_review["status"],
        "reversal_reviews": review_count,
        "opened_from_governance_change_route": True,
        "unapproved_shortcut_rejected": True,
    }


def _assert_status(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label} returned {actual}, expected {expected}")


def _digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
