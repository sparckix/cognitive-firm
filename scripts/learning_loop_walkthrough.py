#!/usr/bin/env python3
"""Executable incident/evidence/forecast/action-impact to learning walkthrough."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.accountability_cases import (  # noqa: E402
    create_accountability_case,
    update_accountability_case_status,
)
from cognitive_firm.orchestration.action_attestation import (  # noqa: E402
    create_action_attestation,
    digest_text,
)
from cognitive_firm.orchestration.evidence_gaps import (  # noqa: E402
    create_evidence_gap,
    update_evidence_gap_status,
)
from cognitive_firm.orchestration.human_work import (  # noqa: E402
    create_agent_requested_human_work_session,
    update_human_work_state,
)
from cognitive_firm.orchestration.learning_events import (  # noqa: E402
    learning_event_from_candidate,
    replay_learning_events,
)
from cognitive_firm.orchestration.learning_transition_compiler import compile_learning_transitions  # noqa: E402
from cognitive_firm.orchestration.org_surface import build_org_surface  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-learning-loop-") as raw:
        root = Path(raw)
        logs = {
            "evidence": root / "org" / "evidence_gaps" / "evidence_gaps.jsonl",
            "human": root / "org" / "human_work" / "human_work.jsonl",
            "accountability": root / "org" / "accountability" / "accountability_cases.jsonl",
            "learning": root / "org" / "learning_events" / "learning_events.jsonl",
            "attestation": root / "org" / "attestations" / "action_attestations.jsonl",
            "transitions": root / "workspace" / "transitions.jsonl",
        }
        action_summary = root / "org" / "action_impact" / "action_impact_summary.json"
        forecast_summary = root / "org" / "forecast_market" / "global_health.json"
        action_summary.parent.mkdir(parents=True)
        forecast_summary.parent.mkdir(parents=True)

        gap = create_evidence_gap(
            gap_type="missing_source",
            target="restricted-source claim",
            description="Claim needs a bounded human check before routing.",
            severity="blocking",
            producer="role.researcher",
            owner_role="role.manager",
            source_ref="project/demo/claim-1",
            log_path=logs["evidence"],
        )
        session = create_agent_requested_human_work_session(
            requested_by_role="role.researcher",
            human_actor="human.principal",
            objective="Check the restricted source and return support/contradict.",
            work_mode="source_check",
            bottleneck_class="access",
            human_deliverable="bounded source receipt",
            artifact_refs=[gap.gap_id],
            log_path=logs["human"],
        )
        update_human_work_state(session.session_id, "claimed", log_path=logs["human"])
        update_human_work_state(session.session_id, "in_progress", log_path=logs["human"])
        completed = update_human_work_state(
            session.session_id,
            "completed",
            completion_summary="Source supports the claim, but only for population Y.",
            receipt="support-limited-to-population-y",
            confidence="medium",
            log_path=logs["human"],
        )
        integrated = update_human_work_state(
            completed.session_id,
            "integrated",
            integration_ref="artifact/demo/evidence-brief",
            agent_followup_required=False,
            log_path=logs["human"],
        )
        update_evidence_gap_status(gap.gap_id, "closed", log_path=logs["evidence"])
        attestation = create_action_attestation(
            subject_kind="artifact",
            subject_ref="artifact/demo/evidence-brief",
            subject_digest=digest_text(integrated.receipt or ""),
            producer="role.researcher",
            action_type="integrate_human_receipt",
            input_refs=[gap.gap_id, completed.session_id],
            output_refs=["artifact/demo/evidence-brief"],
            verification_status="verified",
            verification_summary="Receipt integrated into bounded evidence brief.",
            log_path=logs["attestation"],
        )
        case = create_accountability_case(
            trigger_ref="action/demo/reused-local-heuristic",
            accountable_role="role.manager",
            responsible_actor="role.researcher",
            decision_right_basis="project charter",
            authority_envelope_ref="org/mandates/manager_mandate.md",
            risk_tier="medium",
            recourse_path="reopen",
            externality_tags=["operator_load"],
            rationale="Action-impact record showed repeated local heuristic with review burden.",
            log_path=logs["accountability"],
        )
        update_accountability_case_status(
            case.case_id,
            "closed",
            closure_evidence_refs=[attestation.attestation_id],
            log_path=logs["accountability"],
        )

        forecast_summary.write_text(
            json.dumps(
                {
                    "contract_count": 1,
                    "decision_use": {"rows": 1},
                    "contracts": [
                        {
                            "contract_id": "forecast/demo-human-check",
                            "decision_use": {
                                "summary": "Forecast routed the branch to human source work.",
                                "owner_role": "role.manager",
                            },
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        action_summary.write_text(
            json.dumps(
                {
                    "records": [
                        {
                            "action_id": "action/demo-reused-local-heuristic",
                            "action_ref": "action/demo/reused-local-heuristic",
                            "actor": "role.researcher",
                            "objective_metric": "review_burden",
                            "status": "measured",
                            "optimization_scope": "local",
                            "actual_impact": -1.0,
                            "negative_externality_tags": ["operator_load"],
                            "requires_human_review": True,
                            "artifact_refs": [attestation.attestation_id],
                        }
                    ]
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        surface = build_org_surface(
            project_root=root,
            evidence_gaps_log=logs["evidence"],
            human_work_log=logs["human"],
            forecast_market_summary=forecast_summary,
            action_impact_summary=action_summary,
            accountability_cases_log=logs["accountability"],
            learning_events_log=logs["learning"],
            transitions_log=logs["transitions"],
            damage_limit=0,
        )
        plan = compile_learning_transitions(surface)
        candidate = next(
            (
                item
                for item in plan.candidates
                if item.transition_kind in {"role_review", "human_work_session", "source_repair"}
            ),
            None,
        )
        if candidate is None:
            raise SystemExit("learning-transition compiler produced no reviewable candidate")
        event = learning_event_from_candidate(
            candidate,
            learning_unit_kind="routine_change",
            decision_use="Require explicit source plan before repeating this routing pattern.",
            future_application_cue="restricted-source claim with repeated local review burden",
            approved_by="role.manager",
            approval_ref=case.case_id,
            before_state="ad hoc restricted-source routing",
            after_state="predeclare source plan and review burden before dispatch",
            externality_review_ref=case.case_id,
            log_path=logs["learning"],
        )
        replayed = replay_learning_events(
            role=event.owner_role,
            cue="restricted-source claim",
            log_path=logs["learning"],
        )
        if [item.learning_event_id for item in replayed] != [event.learning_event_id]:
            raise SystemExit("approved learning event was not replayed for future work")
        final_surface = build_org_surface(
            project_root=root,
            evidence_gaps_log=logs["evidence"],
            human_work_log=logs["human"],
            forecast_market_summary=forecast_summary,
            action_impact_summary=action_summary,
            accountability_cases_log=logs["accountability"],
            learning_events_log=logs["learning"],
            transitions_log=logs["transitions"],
            damage_limit=0,
        )
        if final_surface.counts["active_learning_events"] != 1:
            raise SystemExit("approved learning event was not visible on organization surface")

        print(
            json.dumps(
                {
                    "ok": True,
                    "evidence_gap_status": "closed",
                    "human_work_state": integrated.state,
                    "attestation": attestation.attestation_id,
                    "accountability_case": case.case_id,
                    "learning_candidate": candidate.candidate_id,
                    "learning_event": event.learning_event_id,
                    "replayed_for_future_work": True,
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
