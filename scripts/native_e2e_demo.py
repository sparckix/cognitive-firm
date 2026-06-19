#!/usr/bin/env python3
"""No-cost end-to-end demo over cognitive-firm's native kernel primitives.

The fictional tenant is Kettle & Compass, a tiny field-kit company verifying a
product-page claim before publication. The artifacts are deterministic stubs;
no model, API, subscription, network, or external service is called.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from cognitive_firm.orchestration.accountability_cases import (
    create_accountability_case,
    update_accountability_case_status,
)
from cognitive_firm.orchestration.action_attestation import create_action_attestation, digest_text
from cognitive_firm.orchestration.actor_identity import register_actor_identity
from cognitive_firm.orchestration.actor_membership import grant_actor_membership
from cognitive_firm.orchestration.artifact_bundle import (
    build_governed_run_attestation_bundle,
    governed_run_bundle_to_dict,
    governed_run_bundle_summary,
    validate_governed_run_bundle_payload,
)
from cognitive_firm.orchestration.human_work import (
    create_human_work_session,
    update_human_work_state,
)
from cognitive_firm.orchestration.operating_units import define_operating_unit
from cognitive_firm.orchestration.outcome_links import (
    create_outcome_link,
    record_metric_snapshot,
    record_verdict,
)
from cognitive_firm.orchestration.run_checkpoints import (
    append_checkpoint,
    get_run,
    set_run_state,
    start_run,
)
from cognitive_firm.orchestration.work_items import (
    claim_next_work_item,
    complete_work_item,
    enqueue_work_item,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a no-cost cognitive-firm native governance demo.",
    )
    parser.add_argument(
        "--full-json",
        action="store_true",
        help="Print all demo records instead of the compact adoption summary.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the emitted JSON payload. Stdout is still written.",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="cf-native-e2e-") as raw:
        root = Path(raw)
        _seed_demo_authority(root)
        logs = {
            "actors": root / "identity" / "actor_identities.jsonl",
            "memberships": root / "identity" / "actor_memberships.jsonl",
            "units": root / "operating_units.jsonl",
            "work": root / "work_items.jsonl",
            "events": root / "kernel_events.jsonl",
            "transitions": root / "transitions.jsonl",
            "human": root / "human_work.jsonl",
            "attestations": root / "action_attestations.jsonl",
            "outcomes": root / "outcome_links.jsonl",
            "accountability": root / "accountability_cases.jsonl",
        }

        analyst = register_actor_identity(
            actor_id="actor.claims_analyst_stub",
            actor_kind="service",
            display_name="Claims Analyst Stub",
            auth_subject="stub://kettle-compass/claims-analyst",
            identity_provider="demo",
            roles_allowed=["role.analyst"],
            tenant_ids=["tenant-kettle-compass"],
            log_path=logs["actors"],
        )
        reviewer = register_actor_identity(
            actor_id="human.launch_reviewer",
            actor_kind="human",
            display_name="Launch Reviewer",
            auth_subject="stub://kettle-compass/launch-reviewer",
            identity_provider="demo",
            roles_allowed=["role.reviewer"],
            tenant_ids=["tenant-kettle-compass"],
            log_path=logs["actors"],
        )
        grant_actor_membership(
            actor_id=analyst.actor_id,
            role_id="role.analyst",
            granted_by="human.principal",
            decision_right_basis="Kettle & Compass claims mandate",
            tenant_id="tenant-kettle-compass",
            project_id="project-pocket-kettle-launch",
            log_path=logs["memberships"],
        )
        grant_actor_membership(
            actor_id=reviewer.actor_id,
            role_id="role.reviewer",
            granted_by="human.principal",
            decision_right_basis="Kettle & Compass launch-review mandate",
            tenant_id="tenant-kettle-compass",
            project_id="project-pocket-kettle-launch",
            log_path=logs["memberships"],
        )

        unit = define_operating_unit(
            unit_id="claim_review_desk",
            unit_kind="review_lane",
            display_name="Claim Review Desk",
            owner_role="role.manager",
            allowed_work_kinds=["product_claim_check"],
            allowed_exits=["claim_ready_for_launch"],
            worker_roles=["role.analyst"],
            worker_role_archetypes={"role.analyst": "fungible_agent_worker"},
            governance_required_for=["claim_ready_for_launch"],
            tenant_id="tenant-kettle-compass",
            project_id="project-pocket-kettle-launch",
            log_path=logs["units"],
        )
        work = enqueue_work_item(
            unit_id=unit.unit_id,
            kind="product_claim_check",
            payload={
                "objective": (
                    "Check whether Kettle & Compass can publish the claim "
                    "'the pocket kettle reaches trail-ready heat 20% faster.'"
                ),
                "input_refs": [
                    "stub://lab/run-17",
                    "stub://field-notes/batch-c",
                ],
            },
            tenant_id="tenant-kettle-compass",
            project_id="project-pocket-kettle-launch",
            actor="role.manager",
            log_path=logs["work"],
            operating_units_log=logs["units"],
            kernel_events_log=logs["events"],
        )
        claimed = claim_next_work_item(
            unit_id=unit.unit_id,
            actor=analyst.actor_id,
            role_id="role.analyst",
            log_path=logs["work"],
            operating_units_log=logs["units"],
            kernel_events_log=logs["events"],
        )
        if claimed is None:
            raise SystemExit("demo work item was not claimable")

        run = start_run(
            owner_role="role.analyst",
            objective="verify a Kettle & Compass product-page claim before launch",
            tenant_id="tenant-kettle-compass",
            project_id="project-pocket-kettle-launch",
            idempotency_key=f"work:{claimed.work_id}",
            log_path=logs["transitions"],
        )
        append_checkpoint(
            run.run_id,
            actor=analyst.actor_id,
            step_id="load_stub_sources",
            status="completed",
            summary="loaded lab run and field-note stubs",
            payload_ref="stub://kettle-compass/source-pack",
            side_effect_key="stub:load_sources",
            log_path=logs["transitions"],
        )
        stub_brief = (
            "Claim brief: lab run 17 supports the 20% faster heating claim, "
            "field notes batch C supports launch copy only for calm-weather use."
        )
        attestation = create_action_attestation(
            subject_kind="artifact",
            subject_ref="artifact://kettle-compass/pocket-kettle-claim-brief",
            subject_digest=digest_text(stub_brief),
            producer="role.analyst",
            action_type="write_product_claim_brief",
            runtime_ref=f"native_stub:{run.run_id}",
            policy_ref="org/mandates/analyst_mandate.md",
            input_refs=[
                "stub://lab/run-17",
                "stub://field-notes/batch-c",
                f"work_item:{claimed.work_id}",
            ],
            output_refs=["artifact://kettle-compass/pocket-kettle-claim-brief"],
            verification_status="verified",
            verification_summary="stub digest and source refs checked",
            tenant_id="tenant-kettle-compass",
            project_id="project-pocket-kettle-launch",
            run_id=run.run_id,
            log_path=logs["attestations"],
        )
        session = create_human_work_session(
            requested_by="role.analyst",
            human_actor=reviewer.actor_id,
            objective="Review the pocket-kettle claim brief and return a launch-copy receipt.",
            work_mode="judgment",
            bottleneck_class="authority",
            tenant_id="tenant-kettle-compass",
            project_id="project-pocket-kettle-launch",
            collaborating_roles=["role.analyst", "role.reviewer"],
            artifact_refs=[attestation.attestation_id, f"run:{run.run_id}"],
            receipt_required=True,
            receipt_type="note",
            agent_counterparty_role="role.analyst",
            human_deliverable="approval note, wording constraint, or rejection rationale",
            metadata={"cognitive_run_id": run.run_id},
            log_path=logs["human"],
        )
        update_human_work_state(session.session_id, "in_progress", log_path=logs["human"])
        completed_session = update_human_work_state(
            session.session_id,
            "completed",
            completion_summary="Reviewer approved the claim with a calm-weather wording constraint.",
            receipt="approved: 20% faster in calm-weather tests only",
            confidence="high",
            log_path=logs["human"],
        )
        integrated_session = update_human_work_state(
            completed_session.session_id,
            "integrated",
            integration_ref="artifact://kettle-compass/reviewed-pocket-kettle-claim",
            agent_followup_required=False,
            log_path=logs["human"],
        )
        completed_work = complete_work_item(
            claimed.work_id,
            actor=analyst.actor_id,
            claim_token=claimed.claim_token,
            exit_kind="claim_ready_for_launch",
            result="pass",
            producer="role.analyst",
            verifier="role.reviewer",
            artifact_refs=[
                {"kind": "attestation", "path": attestation.attestation_id},
                {"kind": "human_work", "path": integrated_session.session_id},
                {"kind": "run", "path": run.run_id},
            ],
            log_path=logs["work"],
            operating_units_log=logs["units"],
            kernel_events_log=logs["events"],
        )
        append_checkpoint(
            run.run_id,
            actor=analyst.actor_id,
            step_id="human_review_integrated",
            status="completed",
            summary="integrated launch-review receipt into the product-page claim",
            payload_ref=f"human_work:{integrated_session.session_id}",
            side_effect_key="stub:integrate_review",
            log_path=logs["transitions"],
        )
        set_run_state(
            run.run_id,
            actor=analyst.actor_id,
            state="completed",
            log_path=logs["transitions"],
        )

        outcome = create_outcome_link(
            change_ref=f"run:{run.run_id}",
            change_kind="native_e2e_demo",
            metric_name="launch_copy_rework_rate",
            metric_unit="ratio",
            created_by="role.manager",
            tenant_id="tenant-kettle-compass",
            project_id="project-pocket-kettle-launch",
            metadata={"cognitive_run_id": run.run_id, "work_id": claimed.work_id},
            log_path=logs["outcomes"],
            kernel_events_log=logs["events"],
        )
        record_metric_snapshot(
            outcome.outcome_link_id,
            kind="baseline",
            value=0.20,
            captured_by="role.manager",
            log_path=logs["outcomes"],
            kernel_events_log=logs["events"],
        )
        record_metric_snapshot(
            outcome.outcome_link_id,
            kind="post",
            value=0.05,
            captured_by="role.manager",
            log_path=logs["outcomes"],
            kernel_events_log=logs["events"],
        )
        record_verdict(
            outcome.outcome_link_id,
            verdict="improved",
            recorded_by="role.manager",
            rationale="stubbed launch-copy rework rate improved in the demo scenario",
            log_path=logs["outcomes"],
            kernel_events_log=logs["events"],
        )
        case = create_accountability_case(
            trigger_ref=f"run:{run.run_id}",
            accountable_role="role.manager",
            responsible_actor="role.analyst",
            decision_right_basis="Kettle & Compass launch mandate",
            authority_envelope_ref="org/mandates/manager.yaml",
            risk_tier="low",
            recourse_path="reopen",
            tenant_id="tenant-kettle-compass",
            project_id="project-pocket-kettle-launch",
            metadata={"cognitive_run_id": run.run_id, "work_id": claimed.work_id},
            log_path=logs["accountability"],
        )
        update_accountability_case_status(
            case.case_id,
            "closed",
            closure_evidence_refs=[
                f"run:{run.run_id}",
                f"work_item:{completed_work.work_id}",
                f"attestation:{attestation.attestation_id}",
                f"human_work:{integrated_session.session_id}",
                f"outcome_link:{outcome.outcome_link_id}",
            ],
            log_path=logs["accountability"],
        )

        bundle = build_governed_run_attestation_bundle(
            run.run_id,
            transition_log_path=logs["transitions"],
            action_attestation_log_path=logs["attestations"],
            human_work_log_path=logs["human"],
            outcome_links_log_path=logs["outcomes"],
            accountability_cases_log_path=logs["accountability"],
            work_items_log_path=logs["work"],
            authority_root=root,
        )
        summary = governed_run_bundle_summary(bundle)
        bundle_payload = governed_run_bundle_to_dict(bundle)
        bundle_validation_errors = validate_governed_run_bundle_payload(bundle_payload)
        payload = (
            {
                "demo": "native_cognitive_firm_e2e",
                "no_external_calls": True,
                "summary": summary,
                "actors": [asdict(analyst), asdict(reviewer)],
                "operating_unit": unit.as_dict(),
                "work_item": completed_work.as_dict(),
                "run_projection": get_run(run.run_id, log_path=logs["transitions"]).as_dict(),
                "governed_run_attestation": bundle_payload,
                "bundle_validation": {
                    "ok": not bundle_validation_errors,
                    "errors": bundle_validation_errors,
                },
            }
            if args.full_json
            else {
                "demo": "native_cognitive_firm_e2e",
                "fictional_firm": "Kettle & Compass Field Kits",
                "no_external_calls": True,
                "summary": summary,
                "bundle_validation": {
                    "ok": not bundle_validation_errors,
                    "errors": bundle_validation_errors,
                },
                "work_item": {
                    "work_id": completed_work.work_id,
                    "status": completed_work.status,
                    "exit_kind": completed_work.exit_kind,
                    "producer": completed_work.producer,
                    "verifier": completed_work.verifier,
                },
            }
        )
        rendered = json.dumps(payload, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
    return 0


def _seed_demo_authority(root: Path) -> None:
    roles_dir = root / "org" / "roles"
    mandates_dir = root / "org" / "mandates"
    roles_dir.mkdir(parents=True, exist_ok=True)
    mandates_dir.mkdir(parents=True, exist_ok=True)

    roles = {
        "analyst": (
            "Analyze source packets, produce verified claim briefs, and request "
            "bounded reviewer work before publication."
        ),
        "reviewer": "Review bounded human-work requests and return receipts.",
        "manager": "Own the claim-review desk and accountable closure.",
    }
    for role, purpose in roles.items():
        (roles_dir / f"{role}.yaml").write_text(
            (
                f"role_id: role.{role}\n"
                f"display_name: {role.title()}\n"
                f"mandate_path: org/mandates/{role}_mandate.md\n"
                f"purpose: {purpose}\n"
            ),
            encoding="utf-8",
        )
        (mandates_dir / f"{role}_mandate.md").write_text(
            (
                f"# {role.title()} Mandate\n\n"
                f"{purpose} Actions must carry source refs, provenance, outcome "
                "evidence, and accountable closure when they affect external claims.\n"
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    raise SystemExit(main())
