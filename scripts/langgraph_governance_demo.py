#!/usr/bin/env python3
"""Runnable LangGraph-style governance projection demo.

This script does not depend on LangGraph. It models the callback shape an
external graph runtime would emit, then shows how cognitive-firm records the
organizational projection: run lifecycle, checkpoint, machine attestation, and
human-work interruption, outcome linkage, and accountable closure.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from cognitive_firm.orchestration.action_attestation import (
    create_action_attestation,
    digest_text,
)
from cognitive_firm.orchestration.accountability_cases import (
    create_accountability_case,
    update_accountability_case_status,
)
from cognitive_firm.orchestration.artifact_bundle import (
    build_governed_run_attestation_bundle,
    governed_run_bundle_to_dict,
    governed_run_bundle_summary,
    validate_governed_run_bundle_payload,
)
from cognitive_firm.orchestration.human_work import list_human_work_sessions, update_human_work_state
from cognitive_firm.orchestration.outcome_links import (
    create_outcome_link,
    record_metric_snapshot,
    record_verdict,
)
from cognitive_firm.orchestration.run_checkpoints import get_run
from cognitive_firm.orchestration.runtime_adapters import RuntimeEvent, record_runtime_event


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
        transition_log = root / "transitions.jsonl"
        human_work_log = root / "human_work.jsonl"
        action_attestation_log = root / "action_attestations.jsonl"
        outcome_links_log = root / "outcome_links.jsonl"
        accountability_cases_log = root / "accountability_cases.jsonl"
        kernel_events_log = root / "kernel_events.jsonl"

        started = record_runtime_event(
            RuntimeEvent(
                runtime_name="langgraph",
                external_run_id="thread-governance-demo",
                kind="started",
                owner_role="role.manager",
                actor="role.manager",
                objective="draft and verify an external update under governance",
                tenant_id="tenant-demo",
                project_id="project-demo",
            ),
            log_path=transition_log,
        )
        run_id = str(started["cognitive_run_id"])

        record_runtime_event(
            RuntimeEvent(
                runtime_name="langgraph",
                external_run_id="thread-governance-demo",
                kind="checkpointed",
                owner_role="role.manager",
                actor="role.manager",
                step_id="node.retrieve_context",
                checkpoint_status="completed",
                summary="retrieved context packet before drafting external update",
                payload_ref="artifact://context-packet",
                side_effect_key="demo:context-packet",
            ),
            log_path=transition_log,
        )
        create_action_attestation(
            subject_kind="artifact",
            subject_ref="artifact://draft-external-update",
            subject_digest=digest_text("demo external update draft"),
            producer="role.manager",
            action_type="draft_external_update",
            runtime_ref="langgraph:thread-governance-demo",
            policy_ref="org/mandates/manager.yaml",
            input_refs=["artifact://context-packet"],
            output_refs=["artifact://draft-external-update"],
            verification_status="verified",
            verification_summary="demo digest and source refs checked",
            tenant_id="tenant-demo",
            project_id="project-demo",
            run_id=run_id,
            log_path=action_attestation_log,
        )
        record_runtime_event(
            RuntimeEvent(
                runtime_name="langgraph",
                external_run_id="thread-governance-demo",
                kind="interrupted",
                owner_role="role.manager",
                actor="role.manager",
                interrupt_id="human-approval-before-send",
                interrupt_summary="Approve or reject the external update before the runtime resumes",
                human_actor="human.reviewer",
                human_deliverable="approval note or rejection rationale",
                resume_ref="langgraph://thread-governance-demo/resume/human-approval-before-send",
                work_mode="judgment",
                bottleneck_class="authority",
            ),
            log_path=transition_log,
            human_work_log_path=human_work_log,
        )
        session = list_human_work_sessions(log_path=human_work_log)[0]
        update_human_work_state(
            session.session_id,
            "in_progress",
            log_path=human_work_log,
        )
        update_human_work_state(
            session.session_id,
            "completed",
            completion_summary="Human reviewer approved the external update with one wording constraint.",
            receipt="approved with source attribution retained",
            confidence="high",
            log_path=human_work_log,
        )
        update_human_work_state(
            session.session_id,
            "integrated",
            integration_ref="artifact://approved-external-update",
            agent_followup_required=False,
            log_path=human_work_log,
        )
        record_runtime_event(
            RuntimeEvent(
                runtime_name="langgraph",
                external_run_id="thread-governance-demo",
                kind="state_changed",
                owner_role="role.manager",
                actor="role.manager",
                state="completed",
            ),
            log_path=transition_log,
        )
        outcome = create_outcome_link(
            change_ref=f"run:{run_id}",
            change_kind="governed_run",
            metric_name="review_rework_rate",
            metric_unit="ratio",
            created_by="role.manager",
            tenant_id="tenant-demo",
            project_id="project-demo",
            metadata={"cognitive_run_id": run_id},
            log_path=outcome_links_log,
            kernel_events_log=kernel_events_log,
        )
        record_metric_snapshot(
            outcome.outcome_link_id,
            kind="baseline",
            value=0.25,
            captured_by="role.manager",
            log_path=outcome_links_log,
            kernel_events_log=kernel_events_log,
        )
        record_metric_snapshot(
            outcome.outcome_link_id,
            kind="post",
            value=0.10,
            captured_by="role.manager",
            log_path=outcome_links_log,
            kernel_events_log=kernel_events_log,
        )
        record_verdict(
            outcome.outcome_link_id,
            verdict="improved",
            recorded_by="role.manager",
            rationale="demo metric improved after governed human-review pause",
            log_path=outcome_links_log,
            kernel_events_log=kernel_events_log,
        )
        case = create_accountability_case(
            trigger_ref=f"run:{run_id}",
            accountable_role="role.manager",
            responsible_actor="role.manager",
            decision_right_basis="mandate",
            authority_envelope_ref="org/mandates/manager.yaml",
            risk_tier="medium",
            recourse_path="reopen",
            tenant_id="tenant-demo",
            project_id="project-demo",
            metadata={"cognitive_run_id": run_id},
            log_path=accountability_cases_log,
        )
        update_accountability_case_status(
            case.case_id,
            "closed",
            closure_evidence_refs=[
                f"run:{run_id}",
                f"human_work:{session.session_id}",
                f"outcome_link:{outcome.outcome_link_id}",
            ],
            log_path=accountability_cases_log,
        )

        projection = get_run(run_id, log_path=transition_log).as_dict()
        sessions = [session.__dict__ for session in list_human_work_sessions(log_path=human_work_log)]
        bundle_obj = build_governed_run_attestation_bundle(
            run_id,
            transition_log_path=transition_log,
            action_attestation_log_path=action_attestation_log,
            human_work_log_path=human_work_log,
            outcome_links_log_path=outcome_links_log,
            accountability_cases_log_path=accountability_cases_log,
        )
        bundle = governed_run_bundle_to_dict(bundle_obj)
        bundle_validation_errors = validate_governed_run_bundle_payload(bundle)
        summary = governed_run_bundle_summary(bundle_obj)

        payload = (
            {
                "run_projection": projection,
                "human_work_sessions": sessions,
                "governed_run_attestation": bundle,
                "bundle_validation": {
                    "ok": not bundle_validation_errors,
                    "errors": bundle_validation_errors,
                },
            }
            if args.full_json
            else {
                "demo": "langgraph_governance_projection",
                "summary": summary,
                "bundle_validation": {
                    "ok": not bundle_validation_errors,
                    "errors": bundle_validation_errors,
                },
            }
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
