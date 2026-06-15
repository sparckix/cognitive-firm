from __future__ import annotations

from cognitive_firm.orchestration.governed_run_recipes import (
    BoundedRunControlInput,
    ExecutionEvidenceRouteInput,
    GovernedMutationEvidenceInput,
    GovernedMutationRecipeInput,
    GovernedRunOperatorSummaryInput,
    PredictedMutationOutcomeInput,
    PredictedMutationReversalReviewInput,
    build_bounded_run_controls,
    build_execution_evidence_route_packet,
    build_governed_mutation_evidence_pack,
    build_governed_run_operator_summary,
    build_mutation_proof_request,
    build_predicted_mutation_outcome_link_request,
    build_predicted_mutation_reversal_review_request,
    governed_mutation_evidence_requirements,
    governed_mutation_evidence_refs,
    governed_work_completion_artifact_refs,
    render_governed_run_operator_summary_markdown,
    validate_governed_mutation_evidence_pack,
)


def test_build_predicted_mutation_reversal_review_request_schedules_review_only() -> None:
    request = build_predicted_mutation_reversal_review_request(
        PredictedMutationReversalReviewInput(
            outcome_link={
                "outcome_link_id": "olink_1",
                "change_ref": "governance_change:gcp_1",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "metadata": {
                    "prediction_review": {
                        "status": "prediction_failed",
                        "recommended_action": "file_reversal_candidate_at_routine_review",
                        "evidence_refs": [
                            "outcome_link:olink_1",
                            "governance_change:gcp_1",
                        ],
                    }
                },
            },
            review_due_utc="2026-06-13T00:00:00+00:00",
            scheduled_by="role.evaluator",
            review_id="rrev_1",
            metadata={"run_id": "run_1"},
        )
    )

    assert request == {
        "review_id": "rrev_1",
        "routine_ref": "governance_change:gcp_1",
        "routine_kind": "other",
        "review_due_utc": "2026-06-13T00:00:00+00:00",
        "scheduled_by": "role.evaluator",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "reason": (
            "Predicted structural mutation failed its outcome review; "
            "evaluate amend, retire, or escalation."
        ),
        "review_cadence": "prediction_failure",
        "metadata": {
            "run_id": "run_1",
            "source_recipe": "predicted_mutation_reversal_review_request.v1",
            "source_outcome_link_id": "olink_1",
            "source_outcome_link_ref": "outcome_link:olink_1",
            "prediction_review": {
                "status": "prediction_failed",
                "recommended_action": "file_reversal_candidate_at_routine_review",
                "evidence_refs": [
                    "outcome_link:olink_1",
                    "governance_change:gcp_1",
                ],
            },
            "evidence_refs": ["outcome_link:olink_1", "governance_change:gcp_1"],
            "reversal_candidate": True,
        },
    }


def test_build_predicted_mutation_reversal_review_request_requires_failed_prediction() -> None:
    try:
        build_predicted_mutation_reversal_review_request(
            PredictedMutationReversalReviewInput(
                outcome_link={
                    "outcome_link_id": "olink_1",
                    "change_ref": "governance_change:gcp_1",
                    "metadata": {
                        "prediction_review": {"status": "prediction_met"}
                    },
                },
                review_due_utc="2026-06-13T00:00:00+00:00",
                scheduled_by="role.evaluator",
            )
        )
    except ValueError as exc:
        assert "prediction_review.status must be prediction_failed" in str(exc)
    else:
        raise AssertionError("nonfailed prediction should not schedule reversal review")


def test_build_predicted_mutation_outcome_link_request_carries_proposal_prediction() -> None:
    request = build_predicted_mutation_outcome_link_request(
        PredictedMutationOutcomeInput(
            proposal={
                "proposal_id": "gcp_1",
                "change_kind": "mandate_change",
                "target_ref": "org/mandates/evaluator.md",
                "owner_role": "role.principal",
                "tenant_id": "tenant-a",
                "project_id": "project-a",
                "metadata": {
                    "source_recipe": "policy_promotion_packet_governance_change_request.v1",
                    "source_policy_promotion_packet_id": "ppp_1",
                    "candidate_policy_id": "policy.enterprise-review",
                },
                "predicted_effect": {
                    "metric_name": "handoff_rework_rate",
                    "metric_unit": "ratio",
                    "direction": "lower_is_better",
                    "threshold": 0.1,
                    "review_horizon": "after_next_10_handoffs",
                    "expected_verdict": "improved",
                    "rationale": None,
                },
            },
            created_by="role.evaluator",
            learning_event_id="learn_1",
            metadata={"run_id": "run_1"},
            outcome_link_id="olink_1",
        )
    )

    assert request == {
        "outcome_link_id": "olink_1",
        "change_ref": "governance_change:gcp_1",
        "change_kind": "governance_change",
        "metric_name": "handoff_rework_rate",
        "metric_unit": "ratio",
        "direction": "lower_is_better",
        "created_by": "role.evaluator",
        "learning_event_id": "learn_1",
        "owner_role": "role.principal",
        "tenant_id": "tenant-a",
        "project_id": "project-a",
        "metadata": {
            "candidate_policy_id": "policy.enterprise-review",
            "run_id": "run_1",
            "source_policy_promotion_packet_id": "ppp_1",
            "source_proposal_id": "gcp_1",
            "source_proposal_ref": "governance_change:gcp_1",
            "source_proposal_recipe": "policy_promotion_packet_governance_change_request.v1",
            "source_recipe": "predicted_mutation_outcome_link_request.v1",
            "target_ref": "org/mandates/evaluator.md",
            "proposal_change_kind": "mandate_change",
            "predicted_effect": {
                "metric_name": "handoff_rework_rate",
                "metric_unit": "ratio",
                "direction": "lower_is_better",
                "threshold": 0.1,
                "review_horizon": "after_next_10_handoffs",
                "expected_verdict": "improved",
                "rationale": None,
            },
        },
    }


def test_build_predicted_mutation_outcome_link_request_requires_prediction() -> None:
    try:
        build_predicted_mutation_outcome_link_request(
            PredictedMutationOutcomeInput(
                proposal={"proposal_id": "gcp_1"},
                created_by="role.evaluator",
            )
        )
    except ValueError as exc:
        assert "proposal.predicted_effect is required" in str(exc)
    else:
        raise AssertionError("missing predicted_effect should fail")


def test_build_execution_evidence_route_packet_shapes_existing_service_calls() -> None:
    packet = build_execution_evidence_route_packet(
        ExecutionEvidenceRouteInput(
            signal_id="csig_1",
            signal_kind="capability_gap",
            source_ref="agent_runtime:codex_exec",
            summary="Planner abstained because the target role lacked file-edit authority.",
            owner_role="role.org_evolver",
            severity="blocking",
            worker_ref="actor.codex",
            run_id="run_1",
            work_id="work_1",
            capability_ref="capability:file_edit",
            route_kind="open_learning_candidate",
            routed_by="role.evaluator",
            route_rationale="Similar work should be routed through an authority review before retry.",
            counts_as_failure=True,
            evidence_refs=["phase_execution_plan:pex_1", "a2a_message:msg_1"],
            metadata={"runtime": "codex"},
            governance_change_target_ref="org/mandates/org_evolver.md",
            governance_change_kind="mandate_review",
            proposed_by="role.org_evolver",
        )
    )

    assert packet["schema"] == "execution_evidence_route_packet.v1"
    assert packet["signal_ref"] == "capability_signal:csig_1"
    assert packet["object_ref"] == "work_1"
    assert packet["evidence_carrier_refs"] == [
        "capability_signal:csig_1",
        "phase_execution_plan:pex_1",
        "a2a_message:msg_1",
    ]
    assert packet["candidate_lookup"] == {
        "source": "capability",
        "source_kind": "capability_signal",
        "object_ref": "work_1",
        "source_refs_contains": "capability_signal:csig_1",
    }
    assert packet["boundary"] == {
        "does_not_execute_runtime": True,
        "does_not_approve_governance": True,
        "does_not_mutate_files": True,
    }

    calls = packet["service_calls"]
    assert [call["label"] for call in calls] == [
        "record_capability_signal",
        "route_capability_signal",
        "list_learning_transition_candidates",
        "open_governance_change_from_candidate",
    ]
    assert calls[0] == {
        "label": "record_capability_signal",
        "method": "POST",
        "path": "/kernel/capability-signals",
        "body": {
            "signal_id": "csig_1",
            "signal_kind": "capability_gap",
            "source_ref": "agent_runtime:codex_exec",
            "summary": "Planner abstained because the target role lacked file-edit authority.",
            "owner_role": "role.org_evolver",
            "severity": "blocking",
            "worker_ref": "actor.codex",
            "run_id": "run_1",
            "work_id": "work_1",
            "capability_ref": "capability:file_edit",
            "recommended_route": "open_learning_candidate",
            "counts_as_failure": True,
            "evidence_refs": ["phase_execution_plan:pex_1", "a2a_message:msg_1"],
            "metadata": {"runtime": "codex"},
        },
        "expected_ref": "capability_signal:csig_1",
    }
    assert calls[1]["path"] == "/kernel/capability-signals/csig_1/route"
    assert calls[1]["body"] == {
        "route_kind": "open_learning_candidate",
        "routed_by": "role.evaluator",
        "rationale": "Similar work should be routed through an authority review before retry.",
    }
    assert calls[3]["path"] == (
        "/kernel/learning-transition-candidates/{candidate_id}/governance-change"
    )
    assert calls[3]["body"]["metadata"]["source_capability_signal_ref"] == (
        "capability_signal:csig_1"
    )


def test_execution_evidence_route_packet_supports_unknown_created_signal_id() -> None:
    packet = build_execution_evidence_route_packet(
        ExecutionEvidenceRouteInput(
            signal_kind="tool_unavailable",
            source_ref="agent_runtime:claude_print",
            summary="Reviewer runtime was unavailable.",
            owner_role="role.evaluator",
            run_id="run_1",
            route_kind=None,
        )
    )

    assert packet["signal_ref"] == "capability_signal:{created_signal_id}"
    assert packet["object_ref"] == "run_1"
    assert [call["label"] for call in packet["service_calls"]] == [
        "record_capability_signal",
        "list_learning_transition_candidates",
    ]
    assert packet["service_calls"][0]["body"]["recommended_route"] == (
        "open_learning_candidate"
    )


def test_execution_evidence_route_packet_requires_identity_fields() -> None:
    try:
        build_execution_evidence_route_packet(
            ExecutionEvidenceRouteInput(
                signal_kind=" ",
                source_ref="agent_runtime:codex_exec",
                summary="missing",
                owner_role="role.org_evolver",
            )
        )
    except ValueError as exc:
        assert "signal_kind is required" in str(exc)
    else:
        raise AssertionError("missing signal_kind should fail")


def test_build_mutation_proof_request_preserves_service_body_shape() -> None:
    request = build_mutation_proof_request(
        GovernedMutationRecipeInput(
            step_id="step_1",
            change_kind="mandate_change",
            target_ref="org/mandates/evaluator.md",
            run_id="run_1",
            work_id="work_1",
            proposal_id="gcp_1",
            approval_event_id="evt_1",
            mutation_ref="file://org/mandates/evaluator.md",
            attestation_id="aat_1",
            learning_event_id="learn_1",
            outcome_link_id="olink_1",
            routine_review_id="rrev_1",
            bundle_id="gab_1",
            bundle_digest="sha256:" + "a" * 64,
            bundle_verdict="passed",
            commit_sha="abc123",
            bundle_validation_errors=[],
            evidence_carrier_refs=["capability_signal:csig_1"],
        )
    )

    assert request == {
        "step_id": "step_1",
        "change_kind": "mandate_change",
        "target_ref": "org/mandates/evaluator.md",
        "run_id": "run_1",
        "work_id": "work_1",
        "proposal_id": "gcp_1",
        "approval_event_id": "evt_1",
        "mutation_ref": "file://org/mandates/evaluator.md",
        "attestation_id": "aat_1",
        "learning_event_id": "learn_1",
        "outcome_link_id": "olink_1",
        "routine_review_id": "rrev_1",
        "bundle_id": "gab_1",
        "bundle_digest": "sha256:" + "a" * 64,
        "bundle_verdict": "passed",
        "commit_sha": "abc123",
        "bundle_validation_errors": [],
        "evidence_carrier_refs": ["capability_signal:csig_1"],
    }


def test_build_bounded_run_controls_records_remaining_budget() -> None:
    controls = build_bounded_run_controls(
        BoundedRunControlInput(
            budget_units_consumed=2,
            budget_units_total=5,
            stop_file=None,
            stop_file_seen=False,
            termination_reason="running",
            selected_steps=4,
            steps_run=2,
            live_snapshots_written=3,
        )
    )

    assert controls == {
        "schema": "bounded_run_controls.v1",
        "budget_units_total": 5,
        "budget_units_consumed": 2,
        "budget_units_remaining": 3,
        "stop_file": None,
        "stop_file_seen": False,
        "termination_reason": "running",
        "selected_steps": 4,
        "live_snapshots_written": 3,
        "simulation_clock": {
            "clock_kind": "bounded_harness_iteration",
            "tick_unit": "governed_iteration",
            "ticks_selected": 4,
            "ticks_run": 2,
            "next_tick_index": 3,
        },
    }


def test_build_bounded_run_controls_records_budget_stop_receipt() -> None:
    controls = build_bounded_run_controls(
        BoundedRunControlInput(
            budget_units_consumed=5,
            budget_units_total=5,
            stop_file=None,
            stop_file_seen=False,
            termination_reason="budget_exhausted",
            selected_steps=10,
            steps_run=5,
        )
    )

    assert controls["budget_units_remaining"] == 0
    assert controls["stop_receipt"] == {
        "receipt_kind": "bounded_run_stop_receipt",
        "source": "budget",
        "budget_units_total": 5,
        "budget_units_consumed": 5,
        "budget_units_remaining": 0,
        "observed_at_tick_boundary": 5,
        "termination_reason": "budget_exhausted",
    }


def test_build_bounded_run_controls_records_stop_file_receipt(tmp_path) -> None:
    stop_file = tmp_path / "stop"
    controls = build_bounded_run_controls(
        BoundedRunControlInput(
            budget_units_consumed=1,
            budget_units_total=None,
            stop_file=stop_file,
            stop_file_seen=True,
            termination_reason="stop_file",
            selected_steps=10,
            steps_run=1,
        )
    )

    assert controls["budget_units_remaining"] is None
    assert controls["stop_receipt"] == {
        "receipt_kind": "bounded_run_stop_receipt",
        "source": "stop_file",
        "stop_file": str(stop_file),
        "observed_at_tick_boundary": 1,
        "termination_reason": "stop_file",
    }


def test_governed_work_completion_artifact_refs_use_canonical_kinds() -> None:
    refs = governed_work_completion_artifact_refs(
        proposal_id="gcp_1",
        learning_event_id="learn_1",
        attestation_id="aat_1",
        run_id="run_1",
        phase_execution_plan_id="pex_1",
        a2a_refs=["a2a_message:msg_1"],
        reviewer_evidence_refs=[
            "attestation:aat_reviewer_1",
            "file://reports/reviewers/step/evaluator/review.json",
        ],
        decision_case_ref="decision_aggregation_case:dac_1",
        planner_evidence_refs=[
            "planner_receipt:planner_1",
            "file://reports/planner/planner_1/steps.json",
        ],
        trace_event_ids=["mate_1"],
    )

    assert refs == [
        {"kind": "governance_change", "ref": "governance_change:gcp_1"},
        {"kind": "learning_event", "ref": "learning_event:learn_1"},
        {"kind": "attestation", "ref": "attestation:aat_1"},
        {"kind": "run", "ref": "run:run_1"},
        {"kind": "phase_execution_plan", "ref": "phase_execution_plan:pex_1"},
        {"kind": "a2a_message", "ref": "a2a_message:msg_1"},
        {"kind": "action_attestation", "ref": "attestation:aat_reviewer_1"},
        {
            "kind": "reviewer_evidence",
            "ref": "file://reports/reviewers/step/evaluator/review.json",
        },
        {
            "kind": "decision_aggregation_case",
            "ref": "decision_aggregation_case:dac_1",
        },
        {"kind": "planner_receipt", "ref": "planner_receipt:planner_1"},
        {
            "kind": "multi_agent_trace_event",
            "ref": "multi_agent_trace_event:mate_1",
        },
    ]


def test_governed_mutation_evidence_refs_are_deduped_and_ordered() -> None:
    refs = governed_mutation_evidence_refs(
        capability_signal_id="csig_1",
        learning_candidate_id="ltc_1",
        phase_execution_plan_id="pex_1",
        a2a_refs=["a2a_message:msg_1", "a2a_message:msg_1"],
        reviewer_evidence_refs=["attestation:aat_reviewer_1", "attestation:aat_reviewer_1"],
        decision_case_ref="decision_aggregation_case:dac_1",
        planner_evidence_refs=["planner_receipt:planner_1", " "],
        trace_event_ids=["mate_1", "mate_1"],
    )

    assert refs == [
        "capability_signal:csig_1",
        "learning_transition_candidate:ltc_1",
        "phase_execution_plan:pex_1",
        "a2a_message:msg_1",
        "attestation:aat_reviewer_1",
        "decision_aggregation_case:dac_1",
        "planner_receipt:planner_1",
        "multi_agent_trace_event:mate_1",
    ]


def test_build_governed_mutation_evidence_pack_aligns_artifacts_and_proof_refs() -> None:
    pack = build_governed_mutation_evidence_pack(
        GovernedMutationEvidenceInput(
            proposal_id="gcp_1",
            learning_event_id="learn_1",
            attestation_id="aat_1",
            run_id="run_1",
            capability_signal_id="csig_1",
            learning_candidate_id="ltc_1",
            phase_execution_plan_id="pex_1",
            a2a_refs=["a2a_message:msg_1"],
            reviewer_evidence_refs=[
                "attestation:aat_reviewer_1",
                "file://reports/reviewers/step/evaluator/review.json",
            ],
            decision_case_ref="decision_aggregation_case:dac_1",
            planner_evidence_refs=[
                "planner_receipt:planner_1",
                "file://reports/planner/planner_1/steps.json",
            ],
            trace_event_ids=["mate_1"],
        )
    )

    assert pack["schema"] == "governed_mutation_evidence_pack.v1"
    artifact_refs = pack["artifact_refs"]
    evidence_refs = pack["evidence_carrier_refs"]
    assert {"kind": "action_attestation", "ref": "attestation:aat_reviewer_1"} in artifact_refs
    assert {
        "kind": "reviewer_evidence",
        "ref": "file://reports/reviewers/step/evaluator/review.json",
    } in artifact_refs
    assert "attestation:aat_reviewer_1" in evidence_refs
    assert "file://reports/reviewers/step/evaluator/review.json" in evidence_refs
    assert pack["summary"] == {
        "artifact_refs": len(artifact_refs),
        "evidence_carrier_refs": len(evidence_refs),
        "a2a_refs": 1,
        "reviewer_evidence_refs": 2,
        "planner_evidence_refs": 2,
        "trace_event_ids": 1,
    }

    validation = validate_governed_mutation_evidence_pack(
        pack,
        **governed_mutation_evidence_requirements(require_trace=False),
    )

    assert validation == {
        "schema": "governed_mutation_evidence_pack_validation.v1",
        "valid": True,
        "errors": [],
        "summary": {
            "artifact_refs": len(artifact_refs),
            "evidence_carrier_refs": len(evidence_refs),
            "required_evidence_prefixes": 6,
            "required_artifact_kinds": 8,
        },
    }


def test_validate_governed_mutation_evidence_pack_reports_missing_refs() -> None:
    validation = validate_governed_mutation_evidence_pack(
        {
            "schema": "governed_mutation_evidence_pack.v1",
            "artifact_refs": [{"kind": "run", "ref": "run:run_1"}],
            "evidence_carrier_refs": ["capability_signal:csig_1"],
        },
        required_evidence_prefixes=["phase_execution_plan:", "planner_receipt:"],
        required_artifact_kinds=["phase_execution_plan", "planner_receipt"],
    )

    assert validation["valid"] is False
    assert "missing evidence ref with prefix phase_execution_plan:" in validation["errors"]
    assert "missing evidence ref with prefix planner_receipt:" in validation["errors"]
    assert "missing artifact ref with kind phase_execution_plan" in validation["errors"]
    assert "missing artifact ref with kind planner_receipt" in validation["errors"]


def test_governed_mutation_evidence_requirements_encode_standard_profile() -> None:
    requirements = governed_mutation_evidence_requirements(require_reviewer_evidence=True)

    assert requirements == {
        "required_evidence_prefixes": [
            "capability_signal:",
            "learning_transition_candidate:",
            "phase_execution_plan:",
            "a2a_message:",
            "decision_aggregation_case:",
            "planner_receipt:",
            "multi_agent_trace_event:",
            "attestation:",
        ],
        "required_artifact_kinds": [
            "governance_change",
            "learning_event",
            "attestation",
            "run",
            "phase_execution_plan",
            "a2a_message",
            "decision_aggregation_case",
            "planner_receipt",
            "multi_agent_trace_event",
            "action_attestation",
        ],
    }


def test_build_governed_run_operator_summary_compacts_review_surface() -> None:
    summary = build_governed_run_operator_summary(
        GovernedRunOperatorSummaryInput(
            run_label="agent_fleet_audit",
            run_ref="run:run_1",
            summary={
                "verdict": "passed",
                "termination_reason": "completed",
                "budget_units_consumed": 2,
                "budget_units_remaining": 1,
            },
            operator_controls={"schema": "bounded_run_controls.v1"},
            artifacts=[
                {
                    "label": "viewer",
                    "ref": "file://reports/viewer.html",
                    "purpose": "Human inspection surface.",
                },
                {"label": "", "ref": "file://ignored"},
            ],
            commands=[
                {"label": "serve", "command": "make serve"},
                {"label": "blank", "command": ""},
            ],
            inspection_order=["viewer"],
            bundle_summaries=[
                {
                    "bundle_id": "gab_run_1",
                    "run_id": "run_1",
                    "verdict": "passed",
                    "counts": {"action_attestations": 1},
                    "authority_snapshot": {"status": "resolved"},
                    "ids": {"large": ["not copied"]},
                    "bundle_digest": "sha256:" + "a" * 64,
                }
            ],
            mutation_proofs=[
                {
                    "proof_kind": "governed_mutation_proof",
                    "step_id": "step_1",
                    "change_kind": "mandate_change",
                    "target_ref": "org/mandates/evaluator.md",
                    "valid": True,
                    "proof_digest": "sha256:" + "b" * 64,
                    "bundle_digest": "sha256:" + "a" * 64,
                    "bundle_verdict": "passed",
                    "commit": "abc123",
                    "chain": [{"large": "not copied"}],
                    "evidence_carrier_refs": ["capability_signal:csig_1"],
                }
            ],
            execution_signals=[
                {
                    "signal_id": "csig_1",
                    "signal_kind": "capability_gap",
                    "severity": "blocking",
                    "status": "routed",
                    "source_ref": "agent_runtime:codex_exec",
                    "owner_role": "role.org_evolver",
                    "worker_ref": "actor.codex",
                    "run_id": "run_1",
                    "work_id": "work_1",
                    "recommended_route": "open_learning_candidate",
                    "evidence_refs": ["phase_execution_plan:pex_1"],
                    "metadata": {"large": ["not copied"]},
                }
            ],
            learning_candidates=[
                {
                    "candidate_id": "ltc_1",
                    "source_kind": "capability_signal",
                    "transition_kind": "role_review",
                    "status": "review_ready",
                    "severity": "blocking",
                    "object_ref": "work_1",
                    "suggested_owner_role": "role.org_evolver",
                    "source_refs": ["capability_signal:csig_1"],
                    "proposed_payload": {"large": ["not copied"]},
                }
            ],
            phase_plans=[
                {
                    "plan_id": "pex_1",
                    "objective": "review execution evidence",
                    "owner_role": "role.org_evolver",
                    "status": "blocked",
                    "current_phase": "verification",
                    "remaining_budget_units": 0,
                    "attempts": 2,
                    "run_id": "run_1",
                    "work_id": "work_1",
                    "directives": [{"large": "not copied"}],
                }
            ],
            metadata={"adapter": "langgraph"},
        )
    )

    assert summary["schema"] == "governed_run_operator_summary.v1"
    assert summary["run_label"] == "agent_fleet_audit"
    assert summary["run_ref"] == "run:run_1"
    assert summary["status"] == {
        "verdict": "passed",
        "termination_reason": "completed",
        "bundle_count": 1,
        "mutation_proof_count": 1,
        "invalid_mutation_proofs": 0,
        "open_execution_signals": 1,
        "blocking_execution_signals": 1,
        "blocked_phase_plans": 1,
        "review_candidates": 1,
    }
    assert summary["artifacts"] == [
        {
            "label": "viewer",
            "ref": "file://reports/viewer.html",
            "purpose": "Human inspection surface.",
        }
    ]
    assert summary["commands"] == [{"label": "serve", "command": "make serve"}]
    assert summary["bundle_summaries"][0] == {
        "bundle_id": "gab_run_1",
        "run_id": "run_1",
        "verdict": "passed",
        "counts": {"action_attestations": 1},
        "authority_snapshot": {"status": "resolved"},
        "bundle_digest": "sha256:" + "a" * 64,
    }
    assert summary["mutation_proofs"][0]["step_id"] == "step_1"
    assert "chain" not in summary["mutation_proofs"][0]
    assert summary["execution_signals"][0]["signal_ref"] == "capability_signal:csig_1"
    assert "metadata" not in summary["execution_signals"][0]
    assert summary["learning_candidates"][0]["candidate_ref"] == (
        "learning_transition_candidate:ltc_1"
    )
    assert "proposed_payload" not in summary["learning_candidates"][0]
    assert summary["phase_plans"][0]["plan_ref"] == "phase_execution_plan:pex_1"
    assert "directives" not in summary["phase_plans"][0]

    markdown = render_governed_run_operator_summary_markdown(summary)
    assert "# Governed Run Operator Summary" in markdown
    assert "## Inspect First" in markdown
    assert "## Execution Health" in markdown
    assert "capability_signal:csig_1" in markdown
    assert "phase_execution_plan:pex_1" in markdown
    assert "learning_transition_candidate:ltc_1" in markdown
    assert "## Bundles" in markdown
    assert "## Mutation Proofs" in markdown
    assert "make serve" in markdown


def test_governed_run_operator_summary_rejects_missing_identity() -> None:
    try:
        build_governed_run_operator_summary(
            GovernedRunOperatorSummaryInput(
                run_label=" ",
                run_ref="run:run_1",
                summary={},
            )
        )
    except ValueError as exc:
        assert "run_label is required" in str(exc)
    else:
        raise AssertionError("missing run_label should fail")
