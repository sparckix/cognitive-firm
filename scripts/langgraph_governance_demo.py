#!/usr/bin/env python3
"""Runnable LangGraph-style governance projection demo.

This script does not depend on LangGraph. It models the callback shape an
external graph runtime would emit, then shows how cognitive-firm records the
organizational projection: run lifecycle, checkpoint, machine attestation, and
human-work interruption, outcome linkage, and accountable closure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request


ROOT = Path(__file__).resolve().parents[1]


def _digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assert_status(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label} failed with status {actual}; expected {expected}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a framework-free LangGraph-style governance demo.",
    )
    parser.add_argument(
        "--full-json",
        action="store_true",
        help="Print the full demo JSON instead of the compact adoption summary.",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = KernelServiceConfig(
            project_root=ROOT,
            transition_log=root / "transitions.jsonl",
            human_work_log=root / "human_work.jsonl",
            action_attestation_log=root / "action_attestations.jsonl",
            outcome_links_log=root / "outcome_links.jsonl",
            accountability_cases_log=root / "accountability_cases.jsonl",
            kernel_events_log=root / "kernel_events.jsonl",
        )
        actor_context = {
            "actor_id": "role.manager",
            "actor_kind": "service",
            "role_id": "role.manager",
            "surface": "langgraph_governance_demo",
        }

        started = dispatch_kernel_request(
            "POST",
            "/kernel/runs",
            {
                "owner_role": "role.manager",
                "objective": "draft and verify an external update under governance",
                "tenant_id": "tenant-demo",
                "project_id": "project-demo",
                "idempotency_key": "langgraph:thread-governance-demo",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(started.status, 201, "run start")
        run_id = started.payload["run"]["run_id"]

        checkpoint = dispatch_kernel_request(
            "POST",
            f"/kernel/runs/{run_id}/checkpoints",
            {
                "actor": "role.manager",
                "step_id": "node.retrieve_context",
                "status": "completed",
                "summary": "retrieved context packet before drafting external update",
                "payload_ref": "artifact://context-packet",
                "side_effect_key": "langgraph:thread-governance-demo:context-packet",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(checkpoint.status, 201, "runtime checkpoint")

        attestation = dispatch_kernel_request(
            "POST",
            "/kernel/action-attestations",
            {
                "subject_kind": "artifact",
                "subject_ref": "artifact://draft-external-update",
                "subject_digest": _digest_text("demo external update draft"),
                "producer": "role.manager",
                "action_type": "draft_external_update",
                "runtime_ref": "langgraph:thread-governance-demo",
                "policy_ref": "org/mandates/manager.yaml",
                "input_refs": ["artifact://context-packet"],
                "output_refs": ["artifact://draft-external-update"],
                "verification_status": "verified",
                "verification_summary": "demo digest and source refs checked",
                "tenant_id": "tenant-demo",
                "project_id": "project-demo",
                "run_id": run_id,
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(attestation.status, 201, "action attestation")

        human_work = dispatch_kernel_request(
            "POST",
            "/kernel/human-work",
            {
                "coordination_pattern": "a2h_work_request",
                "requested_by": "role.manager",
                "human_actor": "human.reviewer",
                "objective": "Approve or reject the external update before the runtime resumes",
                "work_mode": "judgment",
                "bottleneck_class": "authority",
                "human_deliverable": "approval note or rejection rationale",
                "tenant_id": "tenant-demo",
                "project_id": "project-demo",
                "agent_followup_ref": "langgraph://thread-governance-demo/resume/human-approval-before-send",
                "metadata": {
                    "runtime_name": "langgraph",
                    "external_run_id": "thread-governance-demo",
                    "interrupt_id": "human-approval-before-send",
                    "cognitive_run_id": run_id,
                },
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(human_work.status, 201, "human work request")
        session_id = human_work.payload["session"]["session_id"]

        in_progress = dispatch_kernel_request(
            "POST",
            f"/kernel/human-work/{session_id}/state",
            {"state": "in_progress", "actor_context": actor_context},
            config=config,
        )
        _assert_status(in_progress.status, 200, "human work in progress")
        completed_work = dispatch_kernel_request(
            "POST",
            f"/kernel/human-work/{session_id}/state",
            {
                "state": "completed",
                "completion_summary": "Human reviewer approved the external update with one wording constraint.",
                "receipt": "approved with source attribution retained",
                "confidence": "high",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(completed_work.status, 200, "human work completed")
        integrated_work = dispatch_kernel_request(
            "POST",
            f"/kernel/human-work/{session_id}/state",
            {
                "state": "integrated",
                "integration_ref": "artifact://approved-external-update",
                "agent_followup_required": False,
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(integrated_work.status, 200, "human work integrated")

        completed_run = dispatch_kernel_request(
            "POST",
            f"/kernel/runs/{run_id}/state",
            {
                "state": "completed",
                "actor": "role.manager",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(completed_run.status, 200, "run completed")

        outcome = dispatch_kernel_request(
            "POST",
            "/kernel/outcome-links",
            {
                "change_ref": f"run:{run_id}",
                "change_kind": "governed_run",
                "metric_name": "review_rework_rate",
                "metric_unit": "ratio",
                "created_by": "role.manager",
                "tenant_id": "tenant-demo",
                "project_id": "project-demo",
                "metadata": {"cognitive_run_id": run_id},
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(outcome.status, 201, "outcome link")
        outcome_link_id = outcome.payload["outcome_link"]["outcome_link_id"]
        baseline = dispatch_kernel_request(
            "POST",
            f"/kernel/outcome-links/{outcome_link_id}/snapshots",
            {
                "kind": "baseline",
                "value": 0.25,
                "captured_by": "role.manager",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(baseline.status, 200, "baseline snapshot")
        post = dispatch_kernel_request(
            "POST",
            f"/kernel/outcome-links/{outcome_link_id}/snapshots",
            {
                "kind": "post",
                "value": 0.10,
                "captured_by": "role.manager",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(post.status, 200, "post snapshot")
        verdict = dispatch_kernel_request(
            "POST",
            f"/kernel/outcome-links/{outcome_link_id}/verdict",
            {
                "verdict": "improved",
                "recorded_by": "role.manager",
                "rationale": "demo metric improved after governed human-review pause",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(verdict.status, 200, "outcome verdict")

        case = dispatch_kernel_request(
            "POST",
            "/kernel/accountability-cases",
            {
                "trigger_ref": f"run:{run_id}",
                "accountable_role": "role.manager",
                "responsible_actor": "role.manager",
                "decision_right_basis": "mandate",
                "authority_envelope_ref": "org/mandates/manager.yaml",
                "risk_tier": "medium",
                "recourse_path": "reopen",
                "tenant_id": "tenant-demo",
                "project_id": "project-demo",
                "metadata": {"cognitive_run_id": run_id},
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(case.status, 201, "accountability case")
        case_id = case.payload["case"]["case_id"]
        closed_case = dispatch_kernel_request(
            "POST",
            f"/kernel/accountability-cases/{case_id}/status",
            {
                "status": "closed",
                "closure_evidence_refs": [
                    f"run:{run_id}",
                    f"human_work:{session_id}",
                    f"outcome_link:{outcome_link_id}",
                ],
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(closed_case.status, 200, "accountability case closed")

        fetched_run = dispatch_kernel_request(
            "GET",
            f"/kernel/runs/{run_id}",
            config=config,
        )
        _assert_status(fetched_run.status, 200, "run projection")
        bundle_response = dispatch_kernel_request(
            "POST",
            "/kernel/governed-run-bundles/build",
            {"run_id": run_id, "actor_context": actor_context},
            config=config,
        )
        _assert_status(bundle_response.status, 200, "governed-run bundle")
        sessions = [integrated_work.payload["session"]]
        bundle = bundle_response.payload["bundle"]
        bundle_validation = bundle_response.payload["validation"]
        summary = bundle_response.payload["summary"]

        if session_id not in summary["ids"]["human_work_sessions"]:
            raise RuntimeError("bundle summary did not include service-routed human work")
        if outcome_link_id not in summary["ids"]["outcome_links"]:
            raise RuntimeError("bundle summary did not include service-routed outcome link")
        if case_id not in summary["ids"]["accountability_cases"]:
            raise RuntimeError("bundle summary did not include service-routed accountability case")

        projection = fetched_run.payload["run"]
        projection["runtime_projection"] = {
            "runtime_name": "langgraph",
            "external_run_id": "thread-governance-demo",
            "resume_ref": "langgraph://thread-governance-demo/resume/human-approval-before-send",
            "evidence_refs": [
                f"run:{run_id}",
                f"human_work:{session_id}",
                f"outcome_link:{outcome_link_id}",
            ],
        }

        payload = (
            {
                "demo": "langgraph_governance_projection",
                "no_external_calls": True,
                "summary": summary,
                "run_projection": projection,
                "human_work_sessions": sessions,
                "governed_run_attestation": bundle,
                "bundle_validation": bundle_validation,
            }
            if args.full_json
            else {
                "demo": "langgraph_governance_projection",
                "summary": summary,
                "bundle_validation": bundle_validation,
            }
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
