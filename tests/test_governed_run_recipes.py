from __future__ import annotations

from cognitive_firm.orchestration.governed_run_recipes import (
    AdoptionReadinessPacketInput,
    BoundedRunControlInput,
    ExecutionEvidenceRouteInput,
    GovernedActionCompositionInput,
    GovernedMutationEvidenceInput,
    GovernedMutationRecipeInput,
    GovernedRunOperatorSummaryInput,
    PredictedMutationOutcomeInput,
    PredictedMutationReversalReviewInput,
    build_adoption_readiness_packet,
    build_governed_action_composition_packet,
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
    refresh_adoption_readiness_packet_projection,
    render_adoption_readiness_packet_markdown,
    render_governed_run_operator_summary_markdown,
    summarize_operator_burden_field_pilot,
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
                    "counts": {"action_attestations": 1, "human_work_sessions": 1},
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
            learning_closure=[
                {
                    "step_id": "step_1",
                    "title": "Evaluator mandate update",
                    "learning_event_id": "learn_1",
                    "learning_use_receipt_id": "lenc_1",
                    "target_ref": "org/mandates/evaluator.md",
                    "future_replay_intent": "apply approved learning before evaluator work",
                    "future_replay_candidate_source": "learning-event-replay",
                    "context_packet_refs": ["ctx_1"],
                    "outcome_link_id": "olink_1",
                    "outcome_review_status": "prediction_met",
                    "outcome_recommended_action": "reaffirm_or_continue",
                    "routine_review_id": "rrev_1",
                    "routine_review_status": "scheduled",
                    "evidence_refs": [
                        "learning_event:learn_1",
                        "outcome_link:olink_1",
                        "learning_event:learn_1",
                    ],
                    "large": ["not copied"],
                }
            ],
            operator_burden={
                "human_work_pressure": [
                    {
                        "agent_counterparty_role": "role.reviewer",
                        "bottleneck_class": "authority",
                        "active_count": 2,
                        "waiting_count": 1,
                        "missing_receipt_count": 1,
                        "stale_count": 0,
                        "session_ids": ["hws_1", "hws_2"],
                        "recommendation": "preserve human boundary; batch review",
                        "metadata": {"large": ["not copied"]},
                    }
                ],
                "action_impact_summary": {
                    "n_total": 10,
                    "n_review_required": 3,
                    "n_local_with_negative_externalities": 1,
                    "records": [{"large": "not copied"}],
                },
                "review_questions": ["Is the review load justified by risk reduction?"],
            },
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
        "learning_closure_count": 1,
        "learning_closure_needs_review": 0,
        "operator_burden_level": "high",
        "operator_burden_score": 4,
        "estimated_human_touchpoints": 5,
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
        "counts": {"action_attestations": 1, "human_work_sessions": 1},
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
    assert summary["learning_closure"][0] == {
        "step_id": "step_1",
        "title": "Evaluator mandate update",
        "learning_event_id": "learn_1",
        "learning_event_ref": "learning_event:learn_1",
        "learning_use_receipt_id": "lenc_1",
        "learning_use_receipt_ref": "learning_event_encounter:lenc_1",
        "changed_context_ref": "org/mandates/evaluator.md",
        "future_work_context": "apply approved learning before evaluator work",
        "future_replay_source": "learning-event-replay",
        "context_packet_refs": ["ctx_1"],
        "outcome_link_id": "olink_1",
        "outcome_link_ref": "outcome_link:olink_1",
        "outcome_review_status": "prediction_met",
        "outcome_recommended_action": "reaffirm_or_continue",
        "routine_review_id": "rrev_1",
        "routine_review_ref": "routine_review:rrev_1",
        "routine_review_status": "scheduled",
        "evidence_refs": ["learning_event:learn_1", "outcome_link:olink_1"],
    }
    assert summary["operator_burden"]["schema"] == "operator_burden_projection.v1"
    assert summary["operator_burden"]["summary"] == {
        "burden_level": "high",
        "burden_score": 4,
        "estimated_human_touchpoints": 5,
        "pressure_groups": 1,
        "missing_receipts": 1,
        "stale_sessions": 0,
        "action_impact_total": 10,
        "action_impact_review_required": 3,
        "action_impact_review_rate": 0.3,
        "action_impact_negative_externalities": 1,
        "bundle_human_work_sessions": 1,
        "bundle_accountability_cases": 0,
        "bundle_approval_events": 0,
    }
    assert summary["operator_burden"]["pressure_groups"][0] == {
        "agent_counterparty_role": "role.reviewer",
        "bottleneck_class": "authority",
        "active_count": 2,
        "waiting_count": 1,
        "missing_receipt_count": 1,
        "stale_count": 0,
        "session_ids": ["hws_1", "hws_2"],
        "recommendation": "preserve human boundary; batch review",
    }
    assert summary["operator_burden"]["boundary"] == {
        "does_not_assign_work": True,
        "does_not_schedule_work": True,
        "does_not_approve_policy": True,
        "does_not_optimize_routing": True,
    }

    markdown = render_governed_run_operator_summary_markdown(summary)
    assert "# Governed Run Operator Summary" in markdown
    assert "## Inspect First" in markdown
    assert "## Operator Burden" in markdown
    assert "role.reviewer/authority" in markdown
    assert "## Learning Closure" in markdown
    assert "learning_event:learn_1" in markdown
    assert "ctx_1" in markdown
    assert "outcome_link:olink_1" in markdown
    assert "routine_review:rrev_1" in markdown
    assert "## Execution Health" in markdown
    assert "capability_signal:csig_1" in markdown
    assert "phase_execution_plan:pex_1" in markdown
    assert "learning_transition_candidate:ltc_1" in markdown
    assert "## Bundles" in markdown
    assert "## Mutation Proofs" in markdown
    assert "make serve" in markdown


def test_summarize_operator_burden_field_pilot_reports_stable_measurement() -> None:
    summary = summarize_operator_burden_field_pilot(
        [
            {
                "phase": "baseline",
                "run_ref": "run:base_1",
                "actual_human_touchpoints": 4,
                "coordination_minutes": 35,
                "rework_count": 1,
            },
            {
                "phase": "baseline",
                "run_ref": "run:base_2",
                "actual_human_touchpoints": 3,
                "coordination_minutes": 30,
                "rework_count": 1,
            },
            {
                "phase": "baseline",
                "run_ref": "run:base_3",
                "actual_human_touchpoints": 5,
                "coordination_minutes": 40,
                "rework_count": 1,
            },
            {
                "phase": "pilot",
                "run_ref": "run:pilot_1",
                "actual_human_touchpoints": 2,
                "projected_human_touchpoints": 2,
                "coordination_minutes": 20,
            },
            {
                "phase": "pilot",
                "run_ref": "run:pilot_2",
                "actual_human_touchpoints": 2,
                "operator_burden_projection": {
                    "summary": {"estimated_human_touchpoints": 3}
                },
                "coordination_minutes": 18,
            },
            {
                "phase": "pilot",
                "run_ref": "run:pilot_3",
                "actual_human_touchpoints": 3,
                "projected_human_touchpoints": 2,
                "coordination_minutes": 22,
                "rework_count": 1,
            },
        ],
        min_baseline_runs=3,
        min_pilot_runs=3,
    )

    assert summary["schema"] == "operator_burden_field_pilot_summary.v1"
    assert summary["measurement_status"] == "stable"
    assert summary["n_total"] == 6
    assert summary["phases"]["baseline"]["mean_actual_human_touchpoints"] == 4.0
    assert summary["phases"]["pilot"]["mean_actual_human_touchpoints"] == 2.3333
    assert summary["deltas"]["mean_actual_human_touchpoints"] == -1.6667
    assert summary["projection_fit"] == {
        "rows_with_projection": 3,
        "projection_tolerance": 1.0,
        "mean_actual_minus_projected": 0.0,
        "undercounted_rows": [],
        "undercounted_rate": 0.0,
    }
    assert summary["review_reasons"] == []
    assert summary["boundary"] == {
        "does_not_assign_work": True,
        "does_not_schedule_work": True,
        "does_not_approve_policy": True,
        "does_not_optimize_routing": True,
        "does_not_mutate_kernel_state": True,
    }


def test_summarize_operator_burden_field_pilot_flags_hidden_burden() -> None:
    summary = summarize_operator_burden_field_pilot(
        [
            {
                "phase": "baseline",
                "run_ref": "run:base_1",
                "actual_human_touchpoints": 2,
                "coordination_minutes": 15,
            },
            {
                "phase": "pilot",
                "run_ref": "run:pilot_1",
                "actual_human_touchpoints": 4,
                "projected_human_touchpoints": 1,
                "coordination_minutes": 45,
                "missing_receipts": 1,
                "hidden_burden_reported": True,
                "burden_shift_reported": True,
            },
        ],
        projection_tolerance=0.5,
    )

    assert summary["measurement_status"] == "needs_review"
    reasons = {reason["reason"] for reason in summary["review_reasons"]}
    assert reasons == {
        "pilot_human_touchpoints_increased",
        "hidden_burden_reported",
        "burden_shift_reported",
        "pilot_missing_receipts",
        "projection_undercounted_human_touchpoints",
    }
    assert summary["projection_fit"]["undercounted_rows"] == [
        {
            "row_index": 1,
            "run_ref": "run:pilot_1",
            "actual_human_touchpoints": 4.0,
            "projected_human_touchpoints": 1.0,
            "delta": 3.0,
        }
    ]


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


def test_build_governed_action_composition_packet_checks_first_gated_chain() -> None:
    packet = build_governed_action_composition_packet(
        GovernedActionCompositionInput(
            action_label="first gated action",
            observed_result={
                "bundle_validation": {"ok": True},
                "summary": {
                    "verdict": "passed",
                    "run_id": "run_1",
                    "bundle_id": "gab_1",
                    "bundle_digest": "sha256:" + "a" * 64,
                    "authority_snapshot": {
                        "status": "resolved",
                        "role_ref": "org/roles/analyst.yaml",
                        "mandate_ref": "org/mandates/analyst.md",
                        "mandate_hash": "abc123",
                    },
                    "ids": {
                        "action_attestations": ["aat_1"],
                        "human_work_sessions": ["hws_1"],
                        "outcome_links": ["olink_1"],
                        "work_items": ["work_1"],
                    },
                },
                "work_item": {"status": "done", "work_id": "work_1"},
            },
        )
    )

    assert packet["schema"] == "governed_action_composition_packet.v1"
    assert packet["status"] == "ready_for_review"
    assert packet["summary"] == {
        "links": 8,
        "required_links": 8,
        "passed_links": 8,
        "missing_links": 0,
        "failed_links": 0,
        "required_blockers": 0,
    }
    by_id = {row["link_id"]: row for row in packet["links"]}
    assert by_id["run"]["evidence_refs"] == ["run:run_1"]
    assert by_id["human_work"]["evidence_refs"] == ["human_work:hws_1"]
    assert by_id["action_attestation"]["evidence_refs"] == [
        "action_attestation:aat_1"
    ]
    assert by_id["outcome_link"]["evidence_refs"] == ["outcome_link:olink_1"]
    assert by_id["governed_bundle"]["evidence_refs"] == [
        "governed_run_bundle:gab_1",
        "sha256:" + "a" * 64,
    ]
    assert packet["boundary"] == {
        "does_not_execute_commands": True,
        "does_not_call_service_routes": True,
        "does_not_approve_governance": True,
        "does_not_schedule_work": True,
        "does_not_mutate_kernel_state": True,
        "does_not_verify_row_existence": True,
    }


def test_governed_action_composition_packet_blocks_disconnected_passed_demo() -> None:
    packet = build_governed_action_composition_packet(
        GovernedActionCompositionInput(
            action_label="thin green demo",
            observed_result={
                "bundle_validation": {"ok": True},
                "summary": {
                    "verdict": "passed",
                    "run_id": "run_1",
                    "bundle_id": "gab_1",
                    "bundle_digest": "sha256:" + "a" * 64,
                    "authority_snapshot": {"status": "resolved"},
                    "ids": {"action_attestations": ["aat_1"]},
                },
                "work_item": {"status": "done", "work_id": "work_1"},
            },
        )
    )

    by_id = {row["link_id"]: row for row in packet["links"]}
    assert packet["status"] == "missing_required_evidence"
    assert by_id["human_work"]["status"] == "missing"
    assert by_id["outcome_link"]["status"] == "missing"
    assert by_id["authority"]["status"] == "missing"
    assert packet["summary"]["required_blockers"] == 4
    assert "human_work" in packet["review_questions"][-1]


def test_governed_action_composition_packet_checks_learning_loop_profile() -> None:
    packet = build_governed_action_composition_packet(
        GovernedActionCompositionInput(
            action_label="learning loop",
            profile="learning_loop",
            observed_result={
                "ok": True,
                "replayed_for_future_work": True,
                "learning_event": "learn_1",
                "context_packet": "ctx_1",
                "verified_context_packet": "ctx_1",
                "learning_use_receipt": "lenc_1",
                "learning_loop_outcome_links": 1,
                "learning_loop_routine_reviews": 1,
            },
        )
    )

    assert packet["status"] == "ready_for_review"
    by_id = {row["link_id"]: row for row in packet["links"]}
    assert by_id["learning_event"]["evidence_refs"] == ["learning_event:learn_1"]
    assert by_id["context_packet"]["evidence_refs"] == ["context_packet:ctx_1"]
    assert by_id["learning_use_receipt"]["evidence_refs"] == [
        "learning_event_encounter:lenc_1"
    ]


def test_build_adoption_readiness_packet_marks_observed_and_missing_checks() -> None:
    packet = build_adoption_readiness_packet(
        AdoptionReadinessPacketInput(
            target_label="field-pilot-alpha",
            generated_at_utc="2026-06-17T00:00:00+00:00",
            include_live_agent=True,
            observed_results={
                "first_gated_action": {
                    "bundle_validation": {"ok": True},
                    "summary": {
                        "verdict": "passed",
                        "run_id": "run_1",
                        "bundle_id": "gab_1",
                        "bundle_digest": "sha256:" + "a" * 64,
                        "authority_snapshot": {
                            "status": "resolved",
                            "role_ref": "org/roles/analyst.yaml",
                            "mandate_ref": "org/mandates/analyst.md",
                            "mandate_hash": "abc123",
                        },
                        "ids": {
                            "action_attestations": ["aat_1"],
                            "human_work_sessions": ["hws_1"],
                            "outcome_links": ["olink_1"],
                            "work_items": ["work_1"],
                        },
                    },
                    "work_item": {"status": "done", "work_id": "work_1"},
                },
                "kernel_service_smoke": {
                    "ok": True,
                    "governed_run_bundle_verdict": "passed",
                    "mutation_proof_validated": True,
                    "stale_rejected": True,
                    "governance_proposal_status": "review_ready",
                    "governance_decision": "approve",
                    "provenance_report_counts": {
                        "provenance_report_coverage": "partial",
                        "provenance_follow_through": "closed_loop_observed",
                        "provenance_outcome_links": 1,
                        "provenance_routine_reviews": 1,
                        "provenance_learning_events": 1,
                        "provenance_learning_use_receipts": 1,
                    },
                },
                "learning_loop_walkthrough": {
                    "ok": True,
                    "replayed_for_future_work": True,
                    "learning_event": "learn_1",
                    "context_packet": "ctx_1",
                    "verified_context_packet": "ctx_1",
                    "learning_use_receipt": "lenc_1",
                    "learning_loop_state": "awaiting_outcome_verdict",
                    "learning_loop_outcome_links": 1,
                    "learning_loop_routine_reviews": 1,
                },
            },
            evidence_refs=["file://reports/adoption-readiness.md"],
        )
    )

    assert packet["schema"] == "adoption_readiness_packet.v1"
    assert packet["packet_kind"] == "adoption_readiness_handoff"
    assert packet["target_label"] == "field-pilot-alpha"
    assert packet["read_only"] is True
    assert packet["projection_only"] is True
    assert packet["boundary"] == {
        "does_not_execute_commands": True,
        "does_not_approve_release": True,
        "does_not_mutate_kernel_state": True,
        "does_not_replace_human_diff_review": True,
    }
    assert packet["summary"] == {
        "checks": 10,
        "required_checks": 3,
        "observed_checks": 3,
        "missing_checks": 7,
        "failed_checks": 0,
        "warning_checks": 0,
        "required_blockers": 0,
        "evidence_quality_blockers": 0,
        "optional_evidence_blockers": 0,
        "composition_packets": 2,
        "composition_blockers": 0,
        "ready_for_human_adoption_review": True,
    }
    assert packet["reviewer_path"]["path_id"] == "first_review"
    assert packet["reviewer_path"]["purpose"] == (
        "Verify the public gate, collect deterministic adoption evidence, "
        "and render a reviewer handoff."
    )
    assert packet["reviewer_path"]["not_a"] == [
        "command runner",
        "scheduler",
        "adoption approval",
        "workflow engine",
    ]
    assert packet["reviewer_path"]["read_only"] is True
    assert packet["reviewer_path"]["boundary"]["does_not_execute_commands"] is True
    assert [
        step["command"] for step in packet["reviewer_path"]["steps"]
    ] == [
        "make smoke-public",
        "make adoption-onramp-packet",
        "make adoption-readiness-packet",
    ]
    assert [
        step["packet_status"] for step in packet["reviewer_path"]["steps"]
    ] == [
        "external_gate",
        "recommended_collector",
        "this_packet",
    ]
    by_id = {row["check_id"]: row for row in packet["checks"]}
    assert by_id["first_gated_action"]["status"] == "passed"
    assert by_id["first_gated_action"]["evidence_refs"] == [
        "run_1",
        "gab_1",
        "sha256:" + "a" * 64,
        "work_1",
    ]
    assert by_id["first_gated_action"]["evidence_quality"] == "complete"
    assert by_id["first_gated_action"]["missing_evidence_fields"] == []
    assert by_id["kernel_service_smoke"]["result_summary"] == {
        "provenance_report_counts.provenance_report_coverage": "partial",
        "provenance_report_counts.provenance_follow_through": (
            "closed_loop_observed"
        ),
        "provenance_report_counts.provenance_outcome_links": 1,
        "provenance_report_counts.provenance_routine_reviews": 1,
        "provenance_report_counts.provenance_learning_events": 1,
        "provenance_report_counts.provenance_learning_use_receipts": 1,
        "governance_proposal_status": "review_ready",
        "governance_decision": "approve",
    }
    assert by_id["agent_fleet_audit_demo"]["status"] == "missing"
    assert by_id["formal_provider_proof_pack"]["status"] == "missing"
    assert by_id["adapter_policy_preview"]["status"] == "missing"
    assert by_id["runtime_adapter_proof_pack"]["status"] == "missing"
    assert by_id["bounded_live_agent_run"]["status"] == "missing"
    assert packet["evidence_refs"] == ["file://reports/adoption-readiness.md"]
    assert [row["profile"] for row in packet["composition_packets"]] == [
        "first_gated_action",
        "learning_loop",
    ]
    assert "deterministic fixture proof sufficient" in " ".join(
        packet["review_questions"]
    )

    markdown = render_adoption_readiness_packet_markdown(packet)
    assert "# Adoption Readiness Packet" in markdown
    assert "First gated action" in markdown
    assert "make first-gated-action" in markdown
    assert "Bounded live agent run" in markdown
    assert "Adapter-policy preview" in markdown
    assert "Evidence quality blockers" in markdown
    assert "Reviewer Path" in markdown
    assert (
        "Purpose: Verify the public gate, collect deterministic adoption "
        "evidence, and render a reviewer handoff."
    ) in markdown
    assert (
        "Not a: command runner, scheduler, adoption approval, workflow engine"
    ) in markdown
    assert "make adoption-onramp-packet" in markdown
    assert "this_packet" in markdown
    assert "Composition Coverage" in markdown
    assert "does not approve a release" in markdown


def test_adoption_readiness_packet_marks_thin_live_agent_result_partial() -> None:
    packet = build_adoption_readiness_packet(
        AdoptionReadinessPacketInput(
            include_live_agent=True,
            observed_results={
                "bounded_live_agent_run": {
                    "planner_transport": "subscription_cli",
                    "summary": {
                        "verdict": "passed",
                        "budget_units_remaining": 0,
                        "learning_events": 1,
                        "mutation_proofs_valid": True,
                        "mutation_proof_replay_valid": True,
                        "termination_reason": "completed_selected_steps",
                    },
                }
            },
        )
    )

    by_id = {row["check_id"]: row for row in packet["checks"]}
    live_row = by_id["bounded_live_agent_run"]
    assert live_row["status"] == "warning"
    assert live_row["evidence_quality"] == "partial"
    assert live_row["missing_evidence_fields"] == [
        "summary.budget_units_consumed",
        "summary.learning_use_receipts",
        "summary.context_packets",
        "summary.verified_context_packets",
        "summary.provenance_reports",
        "summary.proposal_review_packets",
        "summary.proposal_review_follow_through_closed_loop",
    ]


def test_adoption_readiness_packet_rejects_zero_live_agent_evidence_counts() -> None:
    packet = build_adoption_readiness_packet(
        AdoptionReadinessPacketInput(
            include_live_agent=True,
            observed_results={
                "bounded_live_agent_run": {
                    "planner_transport": "subscription_cli",
                    "summary": {
                        "verdict": "passed",
                        "budget_units_consumed": 0,
                        "budget_units_remaining": 0,
                        "learning_events": 0,
                        "learning_use_receipts": 0,
                        "context_packets": 0,
                        "verified_context_packets": 0,
                        "provenance_reports": 0,
                        "proposal_review_packets": 0,
                        "proposal_review_follow_through_closed_loop": 0,
                        "mutation_proofs_valid": True,
                        "mutation_proof_replay_valid": True,
                        "termination_reason": "completed_selected_steps",
                    },
                }
            },
        )
    )

    by_id = {row["check_id"]: row for row in packet["checks"]}
    live_row = by_id["bounded_live_agent_run"]
    assert live_row["status"] == "failed"
    assert live_row["evidence_quality"] == "complete"
    assert packet["summary"]["optional_evidence_blockers"] == 1
    assert packet["summary"]["ready_for_human_adoption_review"] is False
    assert any(
        "summary.learning_use_receipts expected at least 1, observed 0"
        in error
        for error in live_row["errors"]
    )
    assert any(
        "summary.verified_context_packets expected at least 1, observed 0"
        in error
        for error in live_row["errors"]
    )
    assert any(
        "summary.proposal_review_follow_through_closed_loop expected at least 1, observed 0"
        in error
        for error in live_row["errors"]
    )


def test_refresh_adoption_readiness_packet_projection_refreshes_reviewer_path() -> None:
    packet = build_adoption_readiness_packet(
        AdoptionReadinessPacketInput(
            metadata={"collector": "scripts/adoption_onramp_packet.py"},
        )
    )
    packet["reviewer_path"]["steps"][2]["description"] = "stale stored copy"
    packet["markdown"] = "stale stored markdown"

    refreshed = refresh_adoption_readiness_packet_projection(packet)

    assert refreshed["reviewer_path"]["steps"][1]["packet_status"] == (
        "source_collector"
    )
    assert refreshed["reviewer_path"]["steps"][2]["description"] == (
        "Render the latest on-ramp handoff, or expected proof gaps when "
        "no on-ramp packet exists."
    )
    assert "stale stored copy" not in refreshed["markdown"]
    assert "latest on-ramp handoff" in refreshed["markdown"]


def test_adoption_readiness_packet_accepts_adapter_policy_preview() -> None:
    packet = build_adoption_readiness_packet(
        AdoptionReadinessPacketInput(
            observed_results={
                "adapter_policy_preview": {
                    "schema": "adapter_policy_preview.v1",
                    "ok": True,
                    "package": "langgraph-runtime-adapter",
                    "package_version": "0.1.0",
                    "preview": {
                        "status": "review_ready",
                        "can_proceed": True,
                        "expands_authority": False,
                    },
                    "validation": {
                        "expected_files_present": True,
                        "authority_neutral": True,
                    },
                    "adapter_manifest": {
                        "adapter_id": "langgraph-runtime-adapter",
                        "protocol": "runtime_event",
                    },
                }
            }
        )
    )

    by_id = {row["check_id"]: row for row in packet["checks"]}
    row = by_id["adapter_policy_preview"]
    assert row["status"] == "passed"
    assert row["result_summary"] == {
        "package": "langgraph-runtime-adapter",
        "package_version": "0.1.0",
        "adapter_manifest.adapter_id": "langgraph-runtime-adapter",
        "adapter_manifest.protocol": "runtime_event",
        "preview.status": "review_ready",
    }
    assert row["evidence_refs"] == [
        "langgraph-runtime-adapter",
        "0.1.0",
        "runtime_event",
        "review_ready",
    ]
    assert packet["summary"]["warning_checks"] == 0


def test_adoption_readiness_packet_blocks_disconnected_required_composition() -> None:
    packet = build_adoption_readiness_packet(
        AdoptionReadinessPacketInput(
            observed_results={
                "first_gated_action": {
                    "bundle_validation": {"ok": True},
                    "summary": {
                        "verdict": "passed",
                        "run_id": "run_1",
                        "bundle_id": "gab_1",
                        "bundle_digest": "sha256:" + "a" * 64,
                        "authority_snapshot": {"status": "resolved"},
                    },
                    "work_item": {"status": "done", "work_id": "work_1"},
                },
                "kernel_service_smoke": {
                    "ok": True,
                    "governed_run_bundle_verdict": "passed",
                    "mutation_proof_validated": True,
                    "stale_rejected": True,
                    "governance_proposal_status": "review_ready",
                    "governance_decision": "approve",
                    "provenance_report_counts": {
                        "provenance_report_coverage": "partial",
                        "provenance_follow_through": "closed_loop_observed",
                        "provenance_outcome_links": 1,
                        "provenance_routine_reviews": 1,
                        "provenance_learning_events": 1,
                        "provenance_learning_use_receipts": 1,
                    },
                },
                "learning_loop_walkthrough": {
                    "ok": True,
                    "replayed_for_future_work": True,
                    "learning_event": "learn_1",
                    "context_packet": "ctx_1",
                    "verified_context_packet": "ctx_1",
                    "learning_use_receipt": "lenc_1",
                    "learning_loop_outcome_links": 1,
                    "learning_loop_routine_reviews": 1,
                },
            }
        )
    )

    assert packet["summary"]["required_blockers"] == 0
    assert packet["summary"]["composition_blockers"] > 0
    assert packet["summary"]["ready_for_human_adoption_review"] is False
    first = packet["composition_packets"][0]
    assert first["profile"] == "first_gated_action"
    assert first["status"] == "missing_required_evidence"


def test_adoption_readiness_packet_blocks_required_green_but_thin_evidence() -> None:
    packet = build_adoption_readiness_packet(
        AdoptionReadinessPacketInput(
            observed_results={
                "first_gated_action": {
                    "bundle_validation": {"ok": True},
                    "summary": {
                        "verdict": "passed",
                        "run_id": "run_1",
                        "bundle_id": "gab_1",
                    },
                    "work_item": {"status": "done"},
                },
                "kernel_service_smoke": {
                    "ok": True,
                    "governed_run_bundle_verdict": "passed",
                    "mutation_proof_validated": True,
                    "stale_rejected": True,
                    "governance_proposal_status": "review_ready",
                    "governance_decision": "approve",
                    "provenance_report_counts": {
                        "provenance_report_coverage": "partial"
                    },
                },
                "learning_loop_walkthrough": {
                    "ok": True,
                    "replayed_for_future_work": True,
                    "learning_event": "learn_1",
                    "context_packet": "ctx_1",
                    "verified_context_packet": "ctx_1",
                    "learning_use_receipt": "lenc_1",
                    "learning_loop_state": "awaiting_outcome_verdict",
                    "learning_loop_outcome_links": 1,
                    "learning_loop_routine_reviews": 1,
                },
            }
        )
    )

    by_id = {row["check_id"]: row for row in packet["checks"]}
    row = by_id["first_gated_action"]
    assert row["status"] == "warning"
    assert row["evidence_quality"] == "partial"
    assert row["missing_evidence_fields"] == [
        "summary.bundle_digest",
        "work_item.work_id",
    ]
    assert "missing expected evidence field" in row["warnings"][0]
    kernel_row = by_id["kernel_service_smoke"]
    assert kernel_row["status"] == "failed"
    assert any(
        "provenance_report_counts.provenance_follow_through expected"
        in error
        for error in kernel_row["errors"]
    )
    assert kernel_row["missing_evidence_fields"] == [
        "provenance_report_counts.provenance_follow_through",
        "provenance_report_counts.provenance_outcome_links",
        "provenance_report_counts.provenance_routine_reviews",
        "provenance_report_counts.provenance_learning_events",
        "provenance_report_counts.provenance_learning_use_receipts",
    ]
    assert packet["summary"]["required_blockers"] == 1
    assert packet["summary"]["evidence_quality_blockers"] == 1
    assert packet["summary"]["ready_for_human_adoption_review"] is False
    assert "Which failed check blocks adoption" in " ".join(
        packet["review_questions"]
    )
    assert "passed without its expected evidence fields" in " ".join(
        packet["review_questions"]
    )


def test_build_adoption_readiness_packet_blocks_failed_required_check() -> None:
    packet = build_adoption_readiness_packet(
        AdoptionReadinessPacketInput(
            observed_results={
                "first_gated_action": {
                    "bundle_validation": {"ok": False},
                    "summary": {"verdict": "failed"},
                    "work_item": {"status": "done"},
                }
            },
            include_release_gate=True,
        )
    )

    by_id = {row["check_id"]: row for row in packet["checks"]}
    assert by_id["first_gated_action"]["status"] == "failed"
    assert "bundle_validation.ok expected True" in by_id["first_gated_action"][
        "errors"
    ][0]
    assert by_id["release_candidate_check"]["status"] == "missing"
    assert packet["summary"]["required_blockers"] == 4
    assert packet["summary"]["composition_blockers"] > 0
    assert packet["summary"]["ready_for_human_adoption_review"] is False
