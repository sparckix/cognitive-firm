from __future__ import annotations

import json
import shlex
import sys

import pytest

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request
from demos.self_evolving_org.run import (
    PlannerRejectionError,
    _llm_evolution_prompt,
    _parse_llm_evolution_steps,
    main,
    run_demo,
    run_feedback_comparison,
)


def test_self_evolving_org_demo_runs_governed_iterations(tmp_path):
    report = run_demo(tmp_path, iterations=3)
    demo_firm = tmp_path / "demo-firm"

    assert report["demo"] == "self_evolving_org"
    assert report["no_external_calls"] is True
    assert report["planner_transport"] == "fixture"
    assert report["iterations_run"] == 3
    assert report["summary"]["proposals"] == 3
    assert report["summary"]["blocked_proposals"] == 1
    assert report["summary"]["approved"] == 3
    assert report["summary"]["learning_events"] == 3
    assert report["summary"]["simulation_ticks"] == 3
    assert report["summary"]["future_replay_proofs"] == 3
    assert report["summary"]["phase_execution_plans"] == 3
    assert report["summary"]["a2a_messages"] == 9
    assert report["summary"]["a2a_obligations_fulfilled"] == 9
    assert report["summary"]["decision_aggregation_cases"] == 3
    assert report["summary"]["trace_events"] == 15
    assert report["summary"]["delegation_graphs"] == 3
    assert report["summary"]["planner_receipts"] == 1
    assert report["summary"]["genesis_workload_packets"] == 20
    assert report["summary"]["workload_probe_packets"] == 20
    assert report["summary"]["workload_feedback_visibility"] == "score_totals"
    assert report["summary"]["workload_firm_received_scores"] is True
    assert report["summary"]["workload_capability_score_per_budget_unit"] > 0
    assert report["summary"]["live_snapshots_written"] == 4
    assert report["summary"]["mutation_proofs"] == 3
    assert report["summary"]["mutation_proofs_valid"] is True
    assert report["summary"]["mutation_proofs_reconstructed"] == 3
    assert report["summary"]["mutation_proof_replay_valid"] is True
    assert report["summary"]["verdict"] == "passed"
    assert len(report["mutation_proofs"]) == 3
    assert len(report["mutation_proof_replay"]) == 3
    assert all(row["matches_saved"] and row["valid"] for row in report["mutation_proof_replay"])
    assert len(report["planner_receipts"]) == 1
    receipt = report["planner_receipts"][0]
    assert receipt["receipt_id"].startswith("planner_fixture_")
    assert receipt["transport"] == "fixture"
    assert receipt["step_ids"] == ["evaluator_handoff", "risk_guardian_role", "learning_review_cadence"]
    assert receipt["response_digest"].startswith("sha256:")
    assert (demo_firm / "reports" / "planner" / receipt["receipt_id"] / "receipt.json").exists()
    assert (demo_firm / "reports" / "planner" / receipt["receipt_id"] / "response.txt").exists()
    assert (demo_firm / "reports" / "planner" / receipt["receipt_id"] / "steps.json").exists()
    assert (demo_firm / "org" / "workload" / "inbox" / "packets.jsonl").exists()
    assert (demo_firm / "org" / "workload" / "executions" / "IN-01.md").exists()
    assert (tmp_path / "operator-only" / "workload-probes" / "IN-01.scorecard.json").exists()
    assert not list((demo_firm / "org").rglob("*.scorecard.json"))
    workload_probe = report["workload_probe"]
    assert workload_probe["summary"]["packet_count"] == 20
    assert workload_probe["summary"]["firm_received_scores"] is True
    assert workload_probe["summary"]["rubric_visible_to_firm"] is False
    assert workload_probe["summary"]["total_budget_units"] == 40
    assert workload_probe["packets"][0]["packet_id"] == "IN-01"
    assert workload_probe["packets"][0]["score"] is not None
    assert len(report["blocked_proposals"]) == 1
    blocked = report["blocked_proposals"][0]
    assert blocked["capability_signal_id"].startswith("csig_")
    assert blocked["learning_candidate_id"].startswith("ltc_")
    assert blocked["proposal_id"].startswith("gcp_")
    assert blocked["status"] == "blocked"
    assert blocked["evidence_sufficiency"]["status"] == "fail"
    assert blocked["target_ref"] == "org/roles/unsafe_self_modifier.yaml"
    assert not (demo_firm / "org" / "roles" / "unsafe_self_modifier.yaml").exists()

    for step in report["steps"]:
        assert step["decision"] == "approve"
        assert step["simulation_tick"]["tick_id"].startswith("tick_")
        assert step["simulation_tick"]["tick_label"].startswith("T+")
        assert step["simulation_tick"]["tick_unit"] == "governed_iteration"
        assert step["change_kind"] in {
            "mandate_change",
            "role_change",
            "project_charter_change",
            "learning_policy_change",
        }
        assert step["target_ref"].startswith("org/")
        assert step["capability_signal_id"].startswith("csig_")
        assert step["learning_candidate_id"].startswith("ltc_")
        assert step["proposal_source"] == "learning_candidate_promotion"
        assert f"capability_signal:{step['capability_signal_id']}" in step["proposal_source_refs"]
        assert f"learning_transition_candidate:{step['learning_candidate_id']}" in step[
            "proposal_source_refs"
        ]
        assert step["learning_event_id"].startswith("learn_")
        assert step["learning_encounter_id"].startswith("lenc_")
        assert step["future_replay"]["learning_event_id"] == step["learning_event_id"]
        assert step["future_replay"]["candidate_source"] == "learning-event-replay"
        assert "apply approved learning" in step["future_replay"]["intent"]
        assert step["phase_execution_plan_id"].startswith("pex_")
        assert step["a2a_message_id"].startswith("msg_")
        assert step["a2a_message_ref"] == f"a2a_message:{step['a2a_message_id']}"
        assert step["a2a_obligation_state"] == "fulfilled"
        assert len(step["a2a_messages"]) == 3
        assert step["a2a_messages"][0]["from_role"] == "org_evolver"
        assert step["a2a_messages"][0]["to_role"] == "evaluator"
        assert step["a2a_messages"][0]["obligation_state"] == "fulfilled"
        assert step["a2a_messages"][1]["from_role"] == "evaluator"
        assert step["a2a_messages"][1]["to_role"] == "risk_guardian"
        assert step["a2a_messages"][1]["obligation_state"] == "fulfilled"
        assert step["a2a_messages"][2]["from_role"] == "evaluator"
        assert step["a2a_messages"][2]["to_role"] == "learning_steward"
        assert step["a2a_messages"][2]["obligation_state"] == "fulfilled"
        assert step["decision_aggregation_case_id"].startswith("dac_")
        assert (
            step["decision_aggregation_case_ref"]
            == f"decision_aggregation_case:{step['decision_aggregation_case_id']}"
        )
        assert step["decision_aggregation_result"]["procedure_kind"] == "quorum_majority"
        assert step["decision_aggregation_result"]["recommendation"] == "approve"
        assert step["decision_aggregation_result"]["quorum_met"] is True
        assert step["decision_aggregation_result"]["approvals"] == 4
        assert step["decision_aggregation_result"]["quorum"] == 4
        assert (
            demo_firm
            / "org"
            / "channels"
            / "evaluator"
            / "inbox"
            / f"{step['a2a_message_id']}.json"
        ).exists()
        assert (
            demo_firm
            / "org"
            / "channels"
            / "risk_guardian"
            / "inbox"
            / f"{step['a2a_messages'][1]['message_id']}.json"
        ).exists()
        assert (
            demo_firm
            / "org"
            / "channels"
            / "learning_steward"
            / "inbox"
            / f"{step['a2a_messages'][2]['message_id']}.json"
        ).exists()
        assert f"planner_receipt:{receipt['receipt_id']}" in step["planner_evidence_refs"]
        assert len(step["trace_event_ids"]) == 5
        assert step["delegation_graph"]["runtime_name"] == "self_evolving_org_demo"
        assert step["delegation_graph"]["diagnostics"]["n_events"] == 5
        assert step["outcome_link_id"].startswith("olink_")
        assert step["outcome_prediction_review"]["status"] == "prediction_met"
        assert step["outcome_prediction_review"]["recommended_action"] == (
            "reaffirm_or_continue"
        )
        assert step["routine_review_id"].startswith("rrev_")
        assert step["attestation_id"].startswith("aat_")
        assert step["bundle_validation"] == {"ok": True, "errors": []}
        assert step["bundle"]["verdict"] == "passed"
        assert step["bundle"]["authority_snapshot"]["status"] == "resolved"
        assert step["bundle"]["counts"]["action_attestations"] == 1
        assert step["bundle"]["counts"]["approval_events"] == 1
        assert step["bundle"]["counts"]["outcome_links"] == 1
        assert step["bundle"]["counts"]["work_items"] == 1
        proof = step["mutation_proof"]
        assert step["proof_evidence_carrier_refs"] == proof["evidence_carrier_refs"]
        assert step["mutation_proof_validation"] == {"valid": True, "errors": []}
        assert proof["proof_kind"] == "governed_mutation_proof"
        assert proof["proof_digest"].startswith("sha256:")
        assert proof["valid"] is True
        assert f"capability_signal:{step['capability_signal_id']}" in proof[
            "evidence_carrier_refs"
        ]
        assert f"learning_transition_candidate:{step['learning_candidate_id']}" in proof[
            "evidence_carrier_refs"
        ]
        assert f"phase_execution_plan:{step['phase_execution_plan_id']}" in proof[
            "evidence_carrier_refs"
        ]
        assert step["a2a_message_ref"] in proof["evidence_carrier_refs"]
        assert step["a2a_messages"][1]["ref"] in proof["evidence_carrier_refs"]
        assert step["a2a_messages"][2]["ref"] in proof["evidence_carrier_refs"]
        assert step["decision_aggregation_case_ref"] in proof["evidence_carrier_refs"]
        assert f"planner_receipt:{receipt['receipt_id']}" in proof["evidence_carrier_refs"]
        for trace_id in step["trace_event_ids"]:
            assert f"multi_agent_trace_event:{trace_id}" in proof["evidence_carrier_refs"]
        assert proof["bundle_digest"] == step["bundle"]["bundle_digest"]
        assert proof["commit"] == step["commit"]
        assert [item["stage"] for item in proof["chain"]] == [
            "run",
            "work_item",
            "proposal",
            "approval",
            "mutation",
            "attestation",
            "learning",
            "outcome",
            "review",
            "bundle",
            "commit",
        ]
        assert f"governance_change:{step['proposal_id']}" in [
            item["ref"] for item in proof["chain"]
        ]
        assert f"git:{step['commit']}" in [item["ref"] for item in proof["chain"]]

    proof_report = json.loads(
        (demo_firm / "reports" / "self-evolving-org-mutation-proofs.json").read_text(
            encoding="utf-8"
        )
    )
    assert proof_report == report["mutation_proofs"]
    timeline = json.loads(
        (demo_firm / "reports" / "self-evolving-org-timeline.json").read_text(
            encoding="utf-8"
        )
    )
    assert timeline["graph_kind"] == "self_evolving_org_timeline"
    assert timeline["summary"]["future_replay_proofs"] == 3
    assert timeline["summary"]["timeline_nodes"] == len(timeline["nodes"])
    assert timeline["summary"]["timeline_edges"] == len(timeline["edges"])
    node_ids = {node["id"] for node in timeline["nodes"]}
    assert "demo:self_evolving_org" in node_ids
    assert f"planner_receipt:{receipt['receipt_id']}" in node_ids
    assert sum(1 for node in timeline["nodes"] if node["kind"] == "simulation_tick") == 3
    for step in report["steps"]:
        assert step["a2a_message_ref"] in node_ids
    a2a_nodes = [node for node in timeline["nodes"] if node["kind"] == "a2a_message"]
    assert len(a2a_nodes) == 9
    assert sum(node["metadata"]["to_role"] == "evaluator" for node in a2a_nodes) == 3
    assert sum(node["metadata"]["to_role"] == "risk_guardian" for node in a2a_nodes) == 3
    assert sum(node["metadata"]["to_role"] == "learning_steward" for node in a2a_nodes) == 3
    assert all(node["metadata"]["obligation_state"] == "fulfilled" for node in a2a_nodes)
    decision_case_nodes = [
        node for node in timeline["nodes"] if node["kind"] == "decision_aggregation_case"
    ]
    assert len(decision_case_nodes) == 3
    assert all(
        node["metadata"]["procedure_kind"] == "quorum_majority"
        for node in decision_case_nodes
    )
    assert all(node["metadata"]["recommendation"] == "approve" for node in decision_case_nodes)
    assert all(node["metadata"]["quorum_met"] is True for node in decision_case_nodes)
    assert any(node["kind"] == "future_replay" for node in timeline["nodes"])
    assert any(node["kind"] == "blocked_proposal" for node in timeline["nodes"])
    assert any(edge["label"] == "evidence_for" for edge in timeline["edges"])
    assert not (demo_firm / "reports" / "self-evolving-org-timeline.html").exists()
    company_state = json.loads(
        (demo_firm / "reports" / "self-evolving-org-company-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert company_state["projection_kind"] == "self_evolving_org_company_state"
    assert company_state["planner_transport"] == "fixture"
    assert company_state["summary"]["offices"] >= 5
    assert company_state["summary"]["simulation_ticks"] == 3
    assert company_state["summary"]["accepted_mutations"] == 3
    assert company_state["summary"]["learning_units"] == 3
    assert company_state["summary"]["a2a_messages"] == 9
    assert company_state["summary"]["decision_cases"] == 3
    assert company_state["summary"]["planner_transcripts"] == 1
    assert company_state["summary"]["agent_invocations"] == 0
    assert company_state["summary"]["live_runtime_offices"] == 0
    assert company_state["summary"]["timeline_nodes"] == len(company_state["timeline_graph"]["nodes"])
    assert company_state["summary"]["timeline_edges"] == len(company_state["timeline_graph"]["edges"])
    assert company_state["summary"]["workload_packets"] == 20
    assert company_state["summary"]["workload_probe_packets"] == 20
    assert company_state["summary"]["workload_feedback_visibility"] == "score_totals"
    assert company_state["summary"]["workload_firm_received_scores"] is True
    assert company_state["summary"]["workload_capability_score_per_budget_unit"] > 0
    assert company_state["workload"][0]["title"] == "New-hire setup, Calder Point"
    assert any("calibration rig" in packet["title"].lower() for packet in company_state["workload"])
    assert company_state["workload_probe"]["summary"]["packet_count"] == 20
    assert "coordination desk" in (
        demo_firm / "org" / "workload" / "README.md"
    ).read_text(encoding="utf-8").lower()
    assert sum(
        1
        for node in company_state["timeline_graph"]["nodes"]
        if node["kind"] == "simulation_tick"
    ) == 3
    assert sum(
        1
        for node in company_state["timeline_graph"]["nodes"]
        if node["kind"] == "a2a_message"
    ) == 9
    assert any(office["role_id"] == "role.org_evolver" for office in company_state["offices"])
    assert any(office["role_id"] == "role.risk_guardian" for office in company_state["offices"])
    assert any(office["role_id"] == "role.learning_steward" for office in company_state["offices"])
    slots_by_role = {slot["role_id"]: slot for slot in company_state["runtime_slots"]}
    assert slots_by_role["role.org_evolver"]["binding"] == "durable_office"
    assert slots_by_role["role.evaluator"]["binding"] == "kernel_protocol_office"
    assert slots_by_role["role.risk_guardian"]["binding"] == "kernel_protocol_office"
    assert slots_by_role["role.learning_steward"]["binding"] == "kernel_protocol_office"
    assert slots_by_role["role.principal"]["binding"] == "governance_authority"
    assert any(
        mutation["rationale"] and mutation["expected_behavior_change"]
        for mutation in company_state["accepted_mutations"]
    )
    assert all(
        mutation["predicted_effect"]["metric_name"] == "open_org_design_gaps"
        for mutation in company_state["accepted_mutations"]
    )
    assert all(
        mutation["predicted_effect"]["review_horizon"] == "same_governed_iteration"
        for mutation in company_state["accepted_mutations"]
    )
    assert all(
        mutation["decision_positions"]
        for mutation in company_state["accepted_mutations"]
    )
    assert all(
        mutation["outcome_prediction_review"]["status"] == "prediction_met"
        for mutation in company_state["accepted_mutations"]
    )
    assert len(company_state["agent_transcripts"]["a2a_messages"]) == 9
    assert company_state["agent_transcripts"]["agent_invocations"] == []
    assert all(
        unit["learning_steward_review_ref"].startswith("a2a_message:")
        for unit in company_state["learning_units"]
    )
    assert company_state["agent_transcripts"]["planner_receipts"][0]["response_text"]
    company_html = (
        demo_firm / "reports" / "self-evolving-org-company-state.html"
    ).read_text(encoding="utf-8")
    assert "Self-Evolving Organization Demo Viewer" in company_html
    assert "Governed Emergence Demo" in company_html
    assert "Halloway Coordination Desk" in company_html
    assert "What To Look At First" in company_html
    assert "Plain-English Decoder" in company_html
    assert "Work packet" in company_html
    assert "Decision aggregation" in company_html
    assert "Mutation proof" in company_html
    assert "Learning unit" in company_html
    assert "not an invisible chat transcript" in company_html
    assert "not authority by itself" in company_html
    assert "sealed coordination floor" in company_html
    assert "Inspect the company" in company_html
    assert "Show prompt excerpt" in company_html
    assert "What Happened" in company_html
    assert "What Improved" in company_html
    assert "Agent Discussion" in company_html
    assert "coordination desk" in company_html
    assert "Planner Transcript" in company_html
    assert "Runtime Slots" in company_html
    assert "Agent Invocation Audit" in company_html
    assert "A2A Messages" in company_html
    assert "Kernel Trace" in company_html
    assert "Agent Work" in company_html
    assert "Proof Chain" in company_html
    assert 'data-tab-target="company-tab"' in company_html
    assert 'data-tab-target="communications-tab"' in company_html
    assert 'data-tab-target="proof-tab"' in company_html
    assert "learning steward:" in company_html
    assert "simulation ticks" in company_html
    assert 'id="state-data"' in company_html
    markdown_report = (
        demo_firm / "reports" / "self-evolving-org-demo.md"
    ).read_text(encoding="utf-8")
    assert "# Self-Evolving Organization Demo Report" in markdown_report
    assert "## Approved Mutations" in markdown_report
    assert "## Planner Receipts" in markdown_report
    assert "## Proof Chains" in markdown_report
    assert "Decision Procedure" in markdown_report
    assert "| Tick | Step | Proposal |" in markdown_report
    assert "| Simulation ticks | 3 |" in markdown_report
    assert "quorum_majority" in markdown_report
    assert "Future replay proofs" in markdown_report
    assert "Mutation proof replay valid" in markdown_report
    assert "## Blocked Proposals" in markdown_report
    assert "| Stage | Ref |" in markdown_report
    assert "| Evidence Carrier Ref |" in markdown_report
    assert "| Planner Evidence Ref |" in markdown_report
    assert "| Nodes | 4 |" in markdown_report
    assert "| Events | 5 |" in markdown_report
    assert f"| {blocked['proposal_id']} |" in markdown_report
    runbook = json.loads(
        (demo_firm / "reports" / "self-evolving-org-runbook.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["operator_runbook"]["schema"] == "governed_run_operator_summary.v1"
    assert runbook["schema"] == "governed_run_operator_summary.v1"
    assert runbook["run_label"] == "self_evolving_org"
    assert runbook["metadata"]["demo"] == "self_evolving_org"
    assert runbook["metadata"]["demo_firm"] == str(demo_firm)
    assert runbook["metadata"]["planner_transport"] == "fixture"
    assert runbook["summary"]["verdict"] == "passed"
    assert runbook["status"]["verdict"] == "passed"
    assert runbook["status"]["mutation_proof_count"] == 3
    assert runbook["status"]["bundle_count"] == 3
    assert runbook["status"]["invalid_mutation_proofs"] == 0
    assert runbook["status"]["open_execution_signals"] == 1
    assert runbook["status"]["blocking_execution_signals"] == 1
    assert runbook["status"]["blocked_phase_plans"] == 0
    assert len(runbook["execution_signals"]) == 4
    assert any(
        signal["signal_ref"] == f"capability_signal:{blocked['capability_signal_id']}"
        and signal["severity"] == "blocking"
        and signal["status"] == "routed"
        for signal in runbook["execution_signals"]
    )
    assert len(runbook["phase_plans"]) == 3
    assert all(plan["status"] == "passed" for plan in runbook["phase_plans"])
    assert any(
        candidate["candidate_ref"]
        == f"learning_transition_candidate:{blocked['learning_candidate_id']}"
        and candidate["status"] == "blocked"
        for candidate in runbook["learning_candidates"]
    )
    assert runbook["operator_controls"]["schema"] == "bounded_run_controls.v1"
    assert runbook["operator_controls"]["simulation_clock"]["tick_unit"] == "governed_iteration"
    assert any(
        artifact["ref"] == "file://reports/self-evolving-org-company-state.html"
        for artifact in runbook["artifacts"]
    )
    assert any(
        artifact["ref"] == "file://reports/self-evolving-org-mutation-proofs.json"
        for artifact in runbook["artifacts"]
    )
    assert any(command["label"] == "serve_viewer" for command in runbook["commands"])
    runbook_markdown = (
        demo_firm / "reports" / "self-evolving-org-runbook.md"
    ).read_text(encoding="utf-8")
    assert "# Self-Evolving Organization Operator Runbook" in runbook_markdown
    assert "## Execution Health" in runbook_markdown
    assert f"capability_signal:{blocked['capability_signal_id']}" in runbook_markdown
    assert "phase_execution_plan:pex_evaluator_handoff" in runbook_markdown
    assert "## Mutation Proofs" in runbook_markdown
    assert "## Bundles" in runbook_markdown
    assert "self-evolving-org-company-state.html" in runbook_markdown
    assert "make self-evolving-org-serve" in runbook_markdown
    assert "SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS= make" not in runbook_markdown


def test_self_evolving_org_demo_respects_budget_units(tmp_path):
    report = run_demo(tmp_path, iterations=4, max_budget_units=2)

    assert report["iterations_requested"] == 4
    assert report["iterations_run"] == 2
    assert report["operator_controls"]["selected_steps"] == 4
    assert report["operator_controls"]["schema"] == "bounded_run_controls.v1"
    assert report["operator_controls"]["budget_units_total"] == 2
    assert report["operator_controls"]["budget_units_consumed"] == 2
    assert report["operator_controls"]["budget_units_remaining"] == 0
    assert report["operator_controls"]["live_snapshots_written"] == 3
    assert report["operator_controls"]["termination_reason"] == "budget_exhausted"
    assert report["operator_controls"]["stop_receipt"]["source"] == "budget"
    assert report["operator_controls"]["stop_receipt"]["observed_at_tick_boundary"] == 2
    assert report["summary"]["proposals"] == 2
    assert report["summary"]["budget_units_total"] == 2
    assert report["summary"]["budget_units_consumed"] == 2
    assert report["summary"]["budget_units_remaining"] == 0
    assert report["summary"]["stop_receipt"]["source"] == "budget"
    assert report["summary"]["termination_reason"] == "budget_exhausted"
    assert report["summary"]["decision_aggregation_cases"] == 2
    assert report["summary"]["verdict"] == "passed"

    markdown_report = (
        tmp_path / "demo-firm" / "reports" / "self-evolving-org-demo.md"
    ).read_text(encoding="utf-8")
    assert "Termination reason" in markdown_report
    assert "budget_exhausted" in markdown_report


def test_self_evolving_org_demo_supports_withheld_workload_feedback(tmp_path):
    report = run_demo(tmp_path, iterations=1, workload_feedback="withheld")
    demo_firm = tmp_path / "demo-firm"

    assert report["summary"]["workload_probe_packets"] == 20
    assert report["summary"]["workload_feedback_visibility"] == "withheld"
    assert report["summary"]["workload_firm_received_scores"] is False
    assert report["summary"]["workload_capability_score_per_budget_unit"] is None
    workload_probe = report["workload_probe"]
    assert workload_probe["summary"]["firm_received_scores"] is False
    assert workload_probe["summary"]["total_score"] is None
    assert workload_probe["packets"][0]["score"] is None
    assert workload_probe["packets"][0]["max_score"] is None
    visible_receipt = (
        demo_firm / "org" / "workload" / "executions" / "IN-01.md"
    ).read_text(encoding="utf-8")
    assert "withheld from firm-visible state" in visible_receipt
    assert "Rubric visible to firm: `false`" in visible_receipt
    operator_scorecard = json.loads(
        (tmp_path / "operator-only" / "workload-probes" / "IN-01.scorecard.json").read_text(
            encoding="utf-8"
        )
    )
    assert operator_scorecard["score"] > 0
    assert operator_scorecard["score_visible_to_firm"] is False


def test_self_evolving_org_feedback_comparison_runs_both_arms(tmp_path):
    report = run_feedback_comparison(tmp_path, iterations=1)

    assert report["demo"] == "self_evolving_org_feedback_comparison"
    assert report["no_external_calls"] is True
    assert report["arms"]["score_feedback"]["firm_received_scores"] is True
    assert report["arms"]["no_feedback"]["firm_received_scores"] is False
    assert report["arms"]["score_feedback"][
        "visible_capability_score_per_budget_unit"
    ] is not None
    assert report["arms"]["no_feedback"][
        "visible_capability_score_per_budget_unit"
    ] is None
    assert report["comparison"]["operator_hidden_total_scores_equal"] is True
    assert report["arms"]["score_feedback"]["operator_hidden_total_score"] == report[
        "arms"
    ]["no_feedback"]["operator_hidden_total_score"]
    assert report["arms"]["score_feedback"][
        "operator_score_per_budget_unit"
    ] == report["arms"]["no_feedback"]["operator_score_per_budget_unit"]
    assert report["comparison"]["score_feedback_operator_score_per_budget"] == report[
        "comparison"
    ]["no_feedback_operator_score_per_budget"]
    assert report["comparison"]["score_feedback_visible_capability"] is not None
    assert report["comparison"]["no_feedback_visible_capability"] is None
    assert (
        tmp_path
        / "reports"
        / "self-evolving-feedback-comparison.json"
    ).exists()
    assert (
        tmp_path
        / "reports"
        / "self-evolving-feedback-comparison.md"
    ).exists()
    assert (
        tmp_path
        / "reports"
        / "self-evolving-feedback-comparison.html"
    ).exists()
    assert (tmp_path / "index.html").exists()
    comparison_html = (
        tmp_path
        / "reports"
        / "self-evolving-feedback-comparison.html"
    ).read_text(encoding="utf-8")
    assert "Does feedback anchor self-organization?" in comparison_html
    assert "score-feedback/demo-firm/reports/self-evolving-org-company-state.html" in comparison_html
    assert "no-feedback/demo-firm/reports/self-evolving-org-company-state.html" in comparison_html
    assert "broader process change" not in comparison_html
    assert (
        tmp_path
        / "score-feedback"
        / "demo-firm"
        / "reports"
        / "self-evolving-org-company-state.html"
    ).exists()
    assert (
        tmp_path
        / "no-feedback"
        / "demo-firm"
        / "reports"
        / "self-evolving-org-company-state.html"
    ).exists()
    saved = json.loads(
        (
            tmp_path
            / "reports"
            / "self-evolving-feedback-comparison.json"
        ).read_text(encoding="utf-8")
    )
    assert saved == report


def test_self_evolving_org_feedback_comparison_accepts_subscription_planner(tmp_path):
    planner = tmp_path / "planner.py"
    planner.write_text(
        """
import json
print(json.dumps({
    "steps": [{
        "step_id": "comparison_agent_handoff",
        "title": "Comparison agent handoff rule",
        "change_kind": "mandate_change",
        "target_ref": "org/mandates/comparison_agent_handoff.md",
        "rationale": "The live comparison planner saw handoff evidence loss.",
        "expected_behavior_change": "Future handoffs preserve evidence refs.",
        "risk_summary": "Narrows handoff requirements; grants no authority.",
        "rollback_plan": "Remove org/mandates/comparison_agent_handoff.md.",
        "applied_relpath": "org/mandates/comparison_agent_handoff.md",
        "applied_text": "# Comparison Agent Handoff\\n\\nHandoffs preserve evidence refs."
    }]
}))
""",
        encoding="utf-8",
    )

    report = run_feedback_comparison(
        tmp_path / "live-comparison",
        iterations=1,
        planner_transport="subscription_cli",
        planner_command=f"{sys.executable} {planner}",
    )

    assert report["no_external_calls"] is False
    assert report["planner_transport"] == "subscription_cli"
    assert report["arms"]["score_feedback"]["firm_received_scores"] is True
    assert report["arms"]["no_feedback"]["firm_received_scores"] is False
    score_report = json.loads(
        (
            tmp_path
            / "live-comparison"
            / "score-feedback"
            / "demo-firm"
            / "reports"
            / "self-evolving-org-demo.json"
        ).read_text(encoding="utf-8")
    )
    withheld_report = json.loads(
        (
            tmp_path
            / "live-comparison"
            / "no-feedback"
            / "demo-firm"
            / "reports"
            / "self-evolving-org-demo.json"
        ).read_text(encoding="utf-8")
    )
    assert score_report["planner_transport"] == "subscription_cli"
    assert withheld_report["planner_transport"] == "subscription_cli"
    assert score_report["steps"][0]["step_id"] == "comparison_agent_handoff"
    assert withheld_report["steps"][0]["step_id"] == "comparison_agent_handoff"


def test_self_evolving_org_demo_accepts_live_workload_executor(tmp_path):
    executor = tmp_path / "executor.py"
    executor.write_text(
        f"""#!{sys.executable}
import sys
prompt = sys.argv[-1]
assert "Visible packet JSON" in prompt
assert "IN-01" in prompt
assert "answer_key.json" not in prompt
assert "scorecard.json" not in prompt
print("Primary destination: Facilities. Set up the desk and badge for Monday. Secondary action: Security review is required because Priya Raman is a contractor and records-drive access cannot use the standard Facilities request.")
""",
        encoding="utf-8",
    )
    executor.chmod(0o755)

    report = run_demo(
        tmp_path / "live-workload-run",
        iterations=0,
        workload_executor_runtime=str(executor),
        workload_executor_adapter="claude_print",
        workload_executor_limit=1,
        workload_executor_timeout_seconds=30,
    )

    demo_firm = tmp_path / "live-workload-run" / "demo-firm"
    assert report["summary"]["workload_probe_packets"] == 20
    assert report["workload_probe"]["summary"]["executor_mode"] == "mixed"
    assert report["workload_probe"]["summary"]["live_executor_packets"] == 1
    first = report["workload_probe"]["packets"][0]
    assert first["packet_id"] == "IN-01"
    assert first["executor_mode"] == "live_agent"
    assert first["live_executor"]["verification_status"] == "verified"
    assert first["score"] == 20
    assert (demo_firm / "reports" / "workload-probes" / "live" / "IN-01" / "prompt.md").exists()
    assert (demo_firm / "reports" / "workload-probes" / "live" / "IN-01" / "artifact.md").exists()
    assert not list((demo_firm / "org").rglob("*.scorecard.json"))

    company_state = json.loads(
        (demo_firm / "reports" / "self-evolving-org-company-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert company_state["summary"]["workload_executor_mode"] == "mixed"
    assert company_state["summary"]["live_workload_executor_packets"] == 1
    assert company_state["summary"]["agent_invocations"] == 1
    assert company_state["agent_transcripts"]["agent_invocations"][0]["producer"] == (
        "role.org_evolver"
    )
    company_html = (
        demo_firm / "reports" / "self-evolving-org-company-state.html"
    ).read_text(encoding="utf-8")
    assert "live work packets" in company_html
    assert "executor:" in company_html


def test_self_evolving_org_demo_respects_existing_stop_file(tmp_path):
    stop_file = tmp_path / "stop-demo"
    stop_file.write_text("stop\n", encoding="utf-8")

    report = run_demo(tmp_path, iterations=3, stop_file=stop_file)

    assert report["iterations_run"] == 0
    assert report["operator_controls"]["stop_file"] == str(stop_file)
    assert report["operator_controls"]["stop_file_seen"] is True
    assert report["operator_controls"]["termination_reason"] == "stop_file"
    assert report["operator_controls"]["stop_receipt"] == {
        "receipt_kind": "bounded_run_stop_receipt",
        "source": "stop_file",
        "stop_file": str(stop_file),
        "observed_at_tick_boundary": 0,
        "termination_reason": "stop_file",
    }
    assert report["operator_controls"]["live_snapshots_written"] == 1
    assert report["summary"]["proposals"] == 0
    assert report["summary"]["blocked_proposals"] == 0
    assert report["summary"]["budget_units_consumed"] == 0
    assert report["summary"]["budget_units_remaining"] is None
    assert report["summary"]["stop_receipt"]["source"] == "stop_file"
    assert report["summary"]["stop_file_seen"] is True
    assert report["summary"]["termination_reason"] == "stop_file"
    assert report["summary"]["verdict"] == "empty"


def test_self_evolving_org_demo_accepts_subscription_cli_planner(tmp_path):
    planner = tmp_path / "planner.py"
    planner.write_text(
        """
import json
import sys
_prompt = open(sys.argv[1], encoding="utf-8").read()
print(json.dumps({
    "steps": [{
        "step_id": "agent_planned_handoff",
        "title": "Agent planned handoff rule",
        "change_kind": "mandate_change",
        "target_ref": "org/mandates/agent_planned_handoff.md",
        "rationale": "The subscription CLI planner saw that verifier handoffs need source refs.",
        "expected_behavior_change": "Verifier handoffs include source refs before review.",
        "risk_summary": "Narrows handoff requirements; grants no new authority.",
        "rollback_plan": "Remove org/mandates/agent_planned_handoff.md.",
        "applied_relpath": "org/mandates/agent_planned_handoff.md",
        "applied_text": "# Agent Planned Handoff\\n\\nVerifier handoffs include source refs before review."
    }]
}))
""",
        encoding="utf-8",
    )

    report = run_demo(
        tmp_path / "agent-run",
        iterations=1,
        planner_transport="subscription_cli",
        planner_command=f"{sys.executable} {planner} {{prompt_file}}",
    )

    assert report["no_external_calls"] is False
    assert report["planner_transport"] == "subscription_cli"
    assert report["summary"]["planner_receipts"] == 1
    assert report["summary"]["live_snapshots_written"] == 2
    assert report["summary"]["future_replay_proofs"] == 1
    assert report["planner_receipts"][0]["transport"] == "subscription_cli"
    assert "command_argv" in report["planner_receipts"][0]["metadata"]
    assert report["summary"]["mutation_proofs"] == 1
    assert report["summary"]["mutation_proofs_valid"] is True
    assert report["summary"]["mutation_proofs_reconstructed"] == 1
    assert report["summary"]["mutation_proof_replay_valid"] is True
    assert report["steps"][0]["step_id"] == "agent_planned_handoff"
    assert len(report["planner_receipts"]) == 1
    receipt = report["planner_receipts"][0]
    demo_firm = tmp_path / "agent-run" / "demo-firm"
    receipt_dir = demo_firm / "reports" / "planner" / receipt["receipt_id"]
    assert receipt["receipt_id"].startswith("planner_subscription_cli_")
    assert receipt["prompt_digest"].startswith("sha256:")
    assert receipt["response_digest"].startswith("sha256:")
    assert receipt["steps_digest"].startswith("sha256:")
    assert receipt["metadata"]["used_prompt_file"] is True
    assert receipt["metadata"]["returncode"] == 0
    assert "{prompt_file}" in receipt["metadata"]["command_argv"]
    assert (receipt_dir / "prompt.md").exists()
    assert (receipt_dir / "response.txt").exists()
    assert (receipt_dir / "steps.json").exists()
    assert (receipt_dir / "receipt.json").exists()
    assert json.loads((receipt_dir / "steps.json").read_text(encoding="utf-8"))[0][
        "step_id"
    ] == "agent_planned_handoff"
    step = report["steps"][0]
    assert f"planner_receipt:{receipt['receipt_id']}" in step["planner_evidence_refs"]
    assert f"planner_receipt:{receipt['receipt_id']}" in step["proof_evidence_carrier_refs"]
    assert f"planner_receipt:{receipt['receipt_id']}" in step["mutation_proof"][
        "evidence_carrier_refs"
    ]
    assert any(
        ref.startswith(f"file://reports/planner/{receipt['receipt_id']}/")
        for ref in step["proof_evidence_carrier_refs"]
    )
    timeline = json.loads(
        (demo_firm / "reports" / "self-evolving-org-timeline.json").read_text(
            encoding="utf-8"
        )
    )
    assert f"planner_receipt:{receipt['receipt_id']}" in {
        node["id"] for node in timeline["nodes"]
    }
    assert step["a2a_message_ref"] in {node["id"] for node in timeline["nodes"]}
    assert step["decision_aggregation_case_ref"] in {
        node["id"] for node in timeline["nodes"]
    }
    evidence_pack = step["governed_mutation_evidence_pack"]
    assert evidence_pack["schema"] == "governed_mutation_evidence_pack.v1"
    assert step["proof_evidence_carrier_refs"] == evidence_pack["evidence_carrier_refs"]
    assert evidence_pack["summary"]["a2a_refs"] == 3
    assert step["governed_mutation_evidence_pack_validation"]["valid"] is True
    assert step["governed_mutation_evidence_pack_validation"]["errors"] == []
    invocations = dispatch_kernel_request(
        "GET",
        "/kernel/agent-invocations?limit=5",
        config=KernelServiceConfig(
            org_dir=demo_firm / "org",
            project_root=demo_firm,
            action_attestation_log=demo_firm
            / "org"
            / "attestations"
            / "action_attestations"
            / "action_attestations.jsonl",
        ),
    )
    assert invocations.status == 200
    assert [row["subject_ref"] for row in invocations.payload["agent_invocations"]] == [
        f"planner_receipt:{receipt['receipt_id']}"
    ]
    invocation = invocations.payload["agent_invocations"][0]
    assert invocation["producer"] == "role.org_evolver"
    assert invocation["adapter"] is None
    assert invocation["returncode"] == 0
    assert invocation["prompt_digest"] == receipt["metadata"]["prompt_digest"]
    assert invocation["stdout_digest"] == receipt["metadata"]["stdout_digest"]
    company_state = json.loads(
        (demo_firm / "reports" / "self-evolving-org-company-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert company_state["summary"]["agent_invocations"] == 1
    assert company_state["summary"]["live_runtime_offices"] == 1
    assert company_state["agent_transcripts"]["agent_invocations"][0]["subject_ref"] == (
        f"planner_receipt:{receipt['receipt_id']}"
    )
    slots_by_role = {slot["role_id"]: slot for slot in company_state["runtime_slots"]}
    assert slots_by_role["role.org_evolver"]["binding"] == "live_agent_cli"
    assert slots_by_role["role.org_evolver"]["invocation_count"] == 1
    assert slots_by_role["role.evaluator"]["binding"] == "kernel_protocol_office"
    company_html = (
        demo_firm / "reports" / "self-evolving-org-company-state.html"
    ).read_text(encoding="utf-8")
    assert "Runtime Slots" in company_html
    assert "Agent Invocation Audit" in company_html
    runbook = json.loads(
        (demo_firm / "reports" / "self-evolving-org-runbook.json").read_text(
            encoding="utf-8"
        )
    )
    bounded_rerun = [
        row["command"] for row in runbook["commands"] if row["label"] == "bounded_live_rerun"
    ][0]
    assert "AGENT_ADAPTER=" not in bounded_rerun
    assert "SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS=600" in bounded_rerun
    assert "SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS= make" not in bounded_rerun


def test_self_evolving_org_demo_accepts_runtime_planner_policy(tmp_path):
    runtime = tmp_path / "fake_claude.py"
    runtime.write_text(
        f"""#!{sys.executable}
import json
import sys
prompt = sys.argv[-1]
assert "bounded organization-structure improvements" in prompt
assert "Live-smoke mode" in prompt
assert "--permission-mode" in sys.argv
print(json.dumps({{
    "steps": [{{
        "step_id": "runtime_policy_handoff",
        "title": "Runtime policy handoff rule",
        "change_kind": "mandate_change",
        "target_ref": "org/mandates/runtime_policy_handoff.md",
        "rationale": "The runtime planner used the shared daemon invocation policy.",
        "expected_behavior_change": "Runtime-sourced handoffs cite their invocation policy receipt.",
        "risk_summary": "Narrows evidence requirements; grants no new authority.",
        "rollback_plan": "Remove org/mandates/runtime_policy_handoff.md.",
        "applied_relpath": "org/mandates/runtime_policy_handoff.md",
        "applied_text": "# Runtime Policy Handoff\\n\\nRuntime-sourced handoffs cite their invocation policy receipt."
    }}]
}}))
""",
        encoding="utf-8",
    )
    runtime.chmod(0o755)

    report = run_demo(
        tmp_path / "runtime-run",
        iterations=1,
        planner_transport="subscription_cli",
        planner_command=None,
        planner_runtime=str(runtime),
        planner_adapter="claude_print",
        planner_prompt_mode="compact",
        planner_timeout_seconds=30,
    )

    receipt = report["planner_receipts"][0]
    assert report["summary"]["mutation_proofs_valid"] is True
    assert report["steps"][0]["step_id"] == "runtime_policy_handoff"
    assert receipt["metadata"]["runtime"] == str(runtime)
    assert receipt["metadata"]["adapter"] == "claude_print"
    assert receipt["metadata"]["schema_version"] == "agent_invocation_receipt.v1"
    assert receipt["metadata"]["prompt_transport"] == "argv"
    assert receipt["metadata"]["prompt_mode"] == "compact"
    assert receipt["metadata"]["timeout_seconds"] == 30
    assert receipt["metadata"]["used_prompt_file"] is False
    assert receipt["metadata"]["stdout_digest"].startswith("sha256:")
    assert "{prompt}" in receipt["metadata"]["command_argv"]
    assert "bounded organization-structure improvements" not in json.dumps(
        receipt["metadata"]["command_argv"]
    )
    runbook = json.loads(
        (
            tmp_path
            / "runtime-run"
            / "demo-firm"
            / "reports"
            / "self-evolving-org-runbook.json"
        ).read_text(encoding="utf-8")
    )
    bounded_rerun = [
        row["command"] for row in runbook["commands"] if row["label"] == "bounded_live_rerun"
    ][0]
    assert "AGENT_ADAPTER=claude_print" in bounded_rerun
    assert "SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS=30" in bounded_rerun


def test_self_evolving_org_demo_accepts_live_reviewer_runtime(tmp_path):
    planner = tmp_path / "planner.py"
    planner.write_text(
        f"""#!{sys.executable}
import json
print(json.dumps({{
    "steps": [{{
        "step_id": "live_reviewer_handoff",
        "title": "Live reviewer handoff rule",
        "change_kind": "mandate_change",
        "target_ref": "org/mandates/live_reviewer_handoff.md",
        "rationale": "Live reviewer offices should leave invocation evidence.",
        "expected_behavior_change": "Reviewer outputs are attached to A2A and decision evidence.",
        "risk_summary": "Adds review evidence only; grants no authority.",
        "rollback_plan": "Remove org/mandates/live_reviewer_handoff.md.",
        "applied_relpath": "org/mandates/live_reviewer_handoff.md",
        "applied_text": "# Live Reviewer Handoff\\n\\nReviewer outputs cite invocation receipts."
    }}]
}}))
""",
        encoding="utf-8",
    )
    reviewer = tmp_path / "reviewer.py"
    reviewer.write_text(
        f"""#!{sys.executable}
import json
import sys
prompt = sys.argv[-1]
assert "cognitive-firm reviewer office" in prompt
assert "Return only JSON" in prompt
print(json.dumps({{
    "position": "approve",
    "rationale": "The proposed change is bounded and evidence-carrying.",
    "evidence_summary": "Reviewed prompt evidence."
}}))
""",
        encoding="utf-8",
    )
    planner.chmod(0o755)
    reviewer.chmod(0o755)

    report = run_demo(
        tmp_path / "live-reviewer-run",
        iterations=1,
        planner_transport="subscription_cli",
        planner_command=str(planner),
        reviewer_runtime=str(reviewer),
        reviewer_adapter="claude_print",
        reviewer_timeout_seconds=30,
    )

    step = report["steps"][0]
    assert report["summary"]["mutation_proofs_valid"] is True
    assert len(step["reviewer_invocations"]) == 3
    assert all(
        invocation["verification_status"] == "verified"
        for invocation in step["reviewer_invocations"]
    )
    assert step["governed_mutation_evidence_pack"]["summary"][
        "reviewer_evidence_refs"
    ] == 9
    assert any(
        ref.startswith("attestation:")
        for ref in step["proof_evidence_carrier_refs"]
    )
    demo_firm = tmp_path / "live-reviewer-run" / "demo-firm"
    company_state = json.loads(
        (demo_firm / "reports" / "self-evolving-org-company-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert company_state["summary"]["agent_invocations"] == 4
    assert company_state["summary"]["live_runtime_offices"] == 4
    slots_by_role = {slot["role_id"]: slot for slot in company_state["runtime_slots"]}
    assert slots_by_role["role.org_evolver"]["binding"] == "live_agent_cli"
    assert slots_by_role["role.evaluator"]["binding"] == "live_agent_cli"
    assert slots_by_role["role.risk_guardian"]["binding"] == "live_agent_cli"
    assert slots_by_role["role.learning_steward"]["binding"] == "live_agent_cli"
    assert all(
        slots_by_role[role]["invocation_count"] == 1
        for role in [
            "role.evaluator",
            "role.risk_guardian",
            "role.learning_steward",
        ]
    )
    runbook = json.loads(
        (demo_firm / "reports" / "self-evolving-org-runbook.json").read_text(
            encoding="utf-8"
        )
    )
    bounded_rerun = [
        row["command"] for row in runbook["commands"] if row["label"] == "bounded_live_rerun"
    ][0]
    assert f"AGENT_REVIEWER_RUNTIME={shlex.quote(str(reviewer))}" in bounded_rerun
    assert "AGENT_REVIEWER_ADAPTER=claude_print" in bounded_rerun
    assert "SELF_EVOLVING_REVIEWER_TIMEOUT_SECONDS=30" in bounded_rerun


def test_self_evolving_org_demo_reports_live_reviewer_abstention(tmp_path):
    planner = tmp_path / "planner.py"
    planner.write_text(
        f"""#!{sys.executable}
import json
print(json.dumps({{
    "steps": [{{
        "step_id": "reviewer_abstention_case",
        "title": "Reviewer abstention case",
        "change_kind": "learning_policy_change",
        "target_ref": "org/policies/reviewer_abstention_case.md",
        "rationale": "The planner proposes a measured policy but reviewers may abstain.",
        "expected_behavior_change": "Reviewer abstention is preserved as blocked evidence.",
        "risk_summary": "Adds no authority.",
        "rollback_plan": "Remove org/policies/reviewer_abstention_case.md.",
        "applied_relpath": "org/policies/reviewer_abstention_case.md",
        "applied_text": "# Reviewer Abstention Case\\n\\nBlocked proposals are visible."
    }}]
}}))
""",
        encoding="utf-8",
    )
    reviewer = tmp_path / "reviewer.py"
    reviewer.write_text(
        f"""#!{sys.executable}
import json
import sys
prompt = sys.argv[-1]
position = "approve"
if "role.risk_guardian" in prompt:
    position = "abstain"
print(json.dumps({{
    "position": position,
    "rationale": "Risk evidence is insufficient." if position == "abstain" else "Evidence is sufficient.",
    "evidence_summary": "Synthetic reviewer fixture."
}}))
""",
        encoding="utf-8",
    )
    planner.chmod(0o755)
    reviewer.chmod(0o755)

    report = run_demo(
        tmp_path / "live-reviewer-blocked-run",
        iterations=1,
        planner_transport="subscription_cli",
        planner_command=str(planner),
        reviewer_runtime=str(reviewer),
        reviewer_adapter="claude_print",
        reviewer_timeout_seconds=30,
    )

    assert report["iterations_run"] == 0
    assert report["summary"]["verdict"] == "blocked"
    assert report["summary"]["termination_reason"] == "blocked_by_reviewer_quorum"
    assert report["summary"]["blocked_proposals"] == 1
    blocked = report["blocked_proposals"][0]
    assert blocked["blocked_by"] == "reviewer_quorum"
    assert blocked["decision_aggregation_result"]["recommendation"] == "escalate"
    assert blocked["decision_aggregation_result"]["quorum_met"] is False
    assert blocked["route_packet"]["schema"] == "execution_evidence_route_packet.v1"
    assert blocked["route_packet"]["boundary"]["does_not_approve_governance"] is True
    assert blocked["route_packet"]["boundary"]["does_not_mutate_files"] is True
    assert blocked["status"] in {"blocked", "review_ready"}
    demo_firm = tmp_path / "live-reviewer-blocked-run" / "demo-firm"
    assert (demo_firm / "reports" / "self-evolving-org-demo.json").exists()
    assert (demo_firm / "reports" / "self-evolving-org-company-state.html").exists()
    runbook = json.loads(
        (demo_firm / "reports" / "self-evolving-org-runbook.json").read_text(
            encoding="utf-8"
        )
    )
    assert runbook["status"]["verdict"] == "blocked"
    assert runbook["status"]["open_execution_signals"] == 1
    assert runbook["status"]["blocking_execution_signals"] == 1
    assert runbook["execution_signals"][0]["signal_kind"] == "evidence_gap"
    assert runbook["execution_signals"][0]["counts_as_failure"] is True
    assert runbook["execution_signals"][0]["source_ref"] == blocked[
        "decision_aggregation_case_ref"
    ]
    runbook_markdown = (
        demo_firm / "reports" / "self-evolving-org-runbook.md"
    ).read_text(encoding="utf-8")
    assert "## Execution Health" in runbook_markdown
    assert blocked["decision_aggregation_case_ref"] in runbook_markdown


def test_self_evolving_org_demo_rejects_bad_subscription_planner_with_receipt(tmp_path):
    planner = tmp_path / "bad_planner.py"
    planner.write_text(
        """
print('not json')
""",
        encoding="utf-8",
    )
    workdir = tmp_path / "bad-agent-run"

    with pytest.raises(PlannerRejectionError) as excinfo:
        run_demo(
            workdir,
            iterations=1,
            planner_transport="subscription_cli",
            planner_command=f"{sys.executable} {planner} {{prompt_file}}",
        )

    report = excinfo.value.report
    demo_firm = workdir / "demo-firm"
    assert report["status"] == "planner_rejected"
    assert report["summary"]["verdict"] == "blocked"
    assert report["summary"]["mutations_applied"] == 0
    assert report["planner_transport"] == "subscription_cli"
    receipt = report["planner_receipts"][0]
    assert receipt["status"] == "rejected"
    assert receipt["receipt_id"].startswith("planner_subscription_cli_rejected_")
    receipt_dir = demo_firm / "reports" / "planner" / receipt["receipt_id"]
    assert (receipt_dir / "prompt.md").exists()
    assert (receipt_dir / "response.txt").read_text(encoding="utf-8").strip() == "not json"
    assert (receipt_dir / "error.txt").exists()
    assert (receipt_dir / "receipt.json").exists()
    assert (demo_firm / "reports" / "self-evolving-org-planner-rejection.json").exists()
    markdown = (
        demo_firm / "reports" / "self-evolving-org-planner-rejection.md"
    ).read_text(encoding="utf-8")
    assert "No governance proposal was opened" in markdown
    assert not (demo_firm / "org" / "mandates" / "agent_planned_handoff.md").exists()


def test_self_evolving_org_demo_rejects_unsafe_subscription_role_with_receipt(tmp_path):
    planner = tmp_path / "unsafe_planner.py"
    planner.write_text(
        """
import json
print(json.dumps({
    "steps": [{
        "step_id": "unsafe_tool_role",
        "title": "Unsafe tool role",
        "change_kind": "role_change",
        "target_ref": "org/roles/unsafe_tool_role.yaml",
        "rationale": "bad",
        "expected_behavior_change": "bad",
        "risk_summary": "bad",
        "rollback_plan": "bad",
        "applied_relpath": "org/roles/unsafe_tool_role.yaml",
        "applied_text": "role_id: role.unsafe\\nauthorized_paths:\\n  - org/reviews/**\\ntools:\\n  - bash\\n"
    }]
}))
""",
        encoding="utf-8",
    )

    with pytest.raises(PlannerRejectionError) as excinfo:
        run_demo(
            tmp_path / "unsafe-agent-run",
            iterations=1,
            planner_transport="subscription_cli",
            planner_command=f"{sys.executable} {planner} {{prompt_file}}",
        )

    reason = excinfo.value.report["summary"]["reason"]
    assert "cannot declare external capability or secret fields" in reason
    assert excinfo.value.report["summary"]["mutations_applied"] == 0


def test_self_evolving_org_demo_cli_returns_two_on_planner_rejection(tmp_path, capsys):
    planner = tmp_path / "failing_planner.py"
    planner.write_text(
        """
import sys
print('partial output')
print('planner failed', file=sys.stderr)
raise SystemExit(7)
""",
        encoding="utf-8",
    )
    workdir = tmp_path / "cli-rejection"

    status = main(
        [
            "--workdir",
            str(workdir),
            "--agent-planner-command",
            f"{sys.executable} {planner} {{prompt_file}}",
        ]
    )

    assert status == 2
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "planner_rejected"
    assert printed["summary"]["reason"] == "planner command exited 7"
    receipt = printed["planner_receipts"][0]
    receipt_dir = workdir / "demo-firm" / "reports" / "planner" / receipt["receipt_id"]
    assert (receipt_dir / "stderr.txt").read_text(encoding="utf-8").strip() == "planner failed"


def test_self_evolving_org_demo_classifies_subscription_login_failure(tmp_path):
    planner = tmp_path / "logged_out_planner.py"
    planner.write_text(
        """
print("Not logged in · Please run /login")
raise SystemExit(1)
""",
        encoding="utf-8",
    )

    with pytest.raises(PlannerRejectionError) as excinfo:
        run_demo(
            tmp_path / "logged-out-planner",
            iterations=1,
            planner_transport="subscription_cli",
            planner_command=f"{sys.executable} {planner}",
        )

    report = excinfo.value.report
    assert report["status"] == "planner_rejected"
    assert report["summary"]["reason"] == "planner command requires local agent login"
    receipt = report["planner_receipts"][0]
    assert "Not logged in" in (
        tmp_path
        / "logged-out-planner"
        / "demo-firm"
        / "reports"
        / "planner"
        / receipt["receipt_id"]
        / "response.txt"
    ).read_text(encoding="utf-8")


def test_self_evolving_org_demo_classifies_runtime_initialization_failure(tmp_path):
    planner = tmp_path / "runtime_init_failure.py"
    planner.write_text(
        """
import sys
print("Error: failed to initialize in-process app-server client", file=sys.stderr)
raise SystemExit(1)
""",
        encoding="utf-8",
    )

    with pytest.raises(PlannerRejectionError) as excinfo:
        run_demo(
            tmp_path / "runtime-init-failure",
            iterations=1,
            planner_transport="subscription_cli",
            planner_command=f"{sys.executable} {planner}",
        )

    report = excinfo.value.report
    assert report["summary"]["reason"] == "planner command runtime initialization failed"
    assert report["summary"]["mutations_applied"] == 0


def test_self_evolving_org_demo_records_subscription_planner_timeout(tmp_path):
    planner = tmp_path / "slow_planner.py"
    planner.write_text(
        """
import time
time.sleep(10)
""",
        encoding="utf-8",
    )

    with pytest.raises(PlannerRejectionError) as excinfo:
        run_demo(
            tmp_path / "slow-planner",
            iterations=1,
            planner_transport="subscription_cli",
            planner_command=f"{sys.executable} {planner}",
            planner_timeout_seconds=1,
        )

    report = excinfo.value.report
    assert report["summary"]["reason"] == "planner command timed out"
    receipt = report["planner_receipts"][0]
    assert receipt["metadata"]["timeout_seconds"] == 1
    assert receipt["metadata"]["prompt_mode"] == "full"
    assert report["summary"]["mutations_applied"] == 0


def test_self_evolving_org_demo_rejects_missing_subscription_planner_command(tmp_path):
    with pytest.raises(PlannerRejectionError) as excinfo:
        run_demo(
            tmp_path / "missing-planner",
            iterations=1,
            planner_transport="subscription_cli",
            planner_command="definitely-not-a-cognitive-firm-planner {prompt_file}",
        )

    report = excinfo.value.report
    assert report["status"] == "planner_rejected"
    assert "planner command not found" in report["summary"]["reason"]
    assert report["summary"]["mutations_applied"] == 0
    receipt = report["planner_receipts"][0]
    assert receipt["metadata"]["returncode"] is None


def test_self_evolving_org_demo_fixture_supports_longer_configurable_runs(tmp_path):
    report = run_demo(tmp_path, iterations=10)
    demo_firm = tmp_path / "demo-firm"

    assert report["iterations_requested"] == 10
    assert report["iterations_run"] == 10
    assert report["summary"]["approved"] == 10
    assert report["summary"]["learning_events"] == 10
    assert report["summary"]["simulation_ticks"] == 10
    assert report["summary"]["future_replay_proofs"] == 10
    assert report["summary"]["mutation_proofs"] == 10
    assert report["summary"]["mutation_proofs_reconstructed"] == 10
    assert report["summary"]["mutation_proofs_valid"] is True
    assert report["summary"]["mutation_proof_replay_valid"] is True
    assert report["summary"]["phase_execution_plans"] == 10
    assert report["summary"]["decision_aggregation_cases"] == 10
    assert report["summary"]["a2a_messages"] == 30
    assert report["summary"]["a2a_obligations_fulfilled"] == 30
    assert report["summary"]["trace_events"] == 50
    assert report["summary"]["delegation_graphs"] == 10
    assert report["summary"]["blocked_proposals"] == 1
    assert report["summary"]["planner_receipts"] == 1
    assert report["summary"]["live_snapshots_written"] == 11
    assert len({step["step_id"] for step in report["steps"]}) == 10
    assert report["steps"][3]["step_id"].startswith("generated_04_")
    assert (demo_firm / report["steps"][3]["applied_path"]).exists()
    assert all(step["mutation_proof"]["valid"] for step in report["steps"])

    timeline = json.loads(
        (demo_firm / "reports" / "self-evolving-org-timeline.json").read_text(
            encoding="utf-8"
        )
    )
    assert sum(1 for node in timeline["nodes"] if node["kind"] == "approved_step") == 10
    assert sum(1 for node in timeline["nodes"] if node["kind"] == "simulation_tick") == 10
    assert sum(1 for node in timeline["nodes"] if node["kind"] == "a2a_message") == 30
    assert sum(1 for node in timeline["nodes"] if node["kind"] == "decision_aggregation_case") == 10


def test_self_evolving_org_demo_requires_fresh_workdir_or_replace(tmp_path):
    first = run_demo(tmp_path, iterations=1)
    demo_firm = tmp_path / "demo-firm"
    assert first["summary"]["verdict"] == "passed"
    assert demo_firm.exists()

    sentinel = demo_firm / "sentinel.txt"
    sentinel.write_text("old generated output\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="already exists"):
        run_demo(tmp_path, iterations=1)
    assert sentinel.exists()

    second = run_demo(tmp_path, iterations=1, replace_existing=True)
    assert second["summary"]["verdict"] == "passed"
    assert not sentinel.exists()


def test_llm_evolution_step_parser_bounds_paths_and_schema():
    steps = _parse_llm_evolution_steps(
        """
        {
          "steps": [
            {
              "step_id": "Evidence Repair",
              "title": "Add evidence repair mandate",
              "change_kind": "mandate_change",
              "target_ref": "org/mandates/evidence_repair.md",
              "rationale": "Missing evidence should route before execution.",
              "expected_behavior_change": "Evidence gaps are repaired before verifier work.",
              "risk_summary": "Narrows dispatch; no new authority.",
              "rollback_plan": "Remove org/mandates/evidence_repair.md.",
              "applied_relpath": "org/mandates/evidence_repair.md",
              "applied_text": "# Evidence Repair\\n\\nRepair missing source refs before verification."
            }
          ]
        }
        """,
        max_steps=1,
    )

    assert len(steps) == 1
    assert steps[0].step_id == "evidence_repair"
    assert steps[0].work_kind == "org_diagnosis"
    assert steps[0].applied_relpath == "org/mandates/evidence_repair.md"
    assert steps[0].applied_text.endswith("\n")

    role_steps = _parse_llm_evolution_steps(
        """
        {
          "steps": [
            {
              "step_id": "Review Coordinator",
              "title": "Add review coordinator role",
              "change_kind": "role_change",
              "target_ref": "org/roles/review_coordinator.yaml",
              "rationale": "Structural proposals need a bounded review coordinator.",
              "expected_behavior_change": "Review coordination writes stay in review artifacts.",
              "risk_summary": "Adds a review office with no external capability grants.",
              "rollback_plan": "Remove org/roles/review_coordinator.yaml.",
              "applied_relpath": "org/roles/review_coordinator.yaml",
              "applied_text": "role_id: role.review_coordinator\\ndisplay_name: Review Coordinator\\nauthorized_paths:\\n  - org/reviews/**\\n"
            }
          ]
        }
        """,
        max_steps=1,
    )

    assert role_steps[0].step_id == "review_coordinator"
    assert role_steps[0].work_kind == "role_design"
    assert role_steps[0].applied_relpath == "org/roles/review_coordinator.yaml"

    charter_steps = _parse_llm_evolution_steps(
        """
        {
          "steps": [
            {
              "step_id": "Refine Firm Charter",
              "title": "Refine self-organizing firm charter",
              "change_kind": "project_charter_change",
              "target_ref": "org/charters/self_evolving_firm.md",
              "rationale": "The firm needs a sharper objective frame before it creates more offices.",
              "expected_behavior_change": "Future proposals cite the firm objective before changing structure.",
              "risk_summary": "Clarifies objective; grants no new authority.",
              "rollback_plan": "Revert org/charters/self_evolving_firm.md.",
              "applied_relpath": "org/charters/self_evolving_firm.md",
              "applied_text": "# Self-Evolving Firm Charter\\n\\nImprove the operating model one governed change at a time."
            }
          ]
        }
        """,
        max_steps=1,
    )

    assert charter_steps[0].step_id == "refine_firm_charter"
    assert charter_steps[0].change_kind == "project_charter_change"
    assert charter_steps[0].work_kind == "charter_design"
    assert charter_steps[0].applied_relpath == "org/charters/self_evolving_firm.md"

    try:
        _parse_llm_evolution_steps(
            """
            {"steps": [{
              "step_id": "bad",
              "title": "Bad",
              "change_kind": "role_change",
              "target_ref": "src/bad.py",
              "rationale": "bad",
              "expected_behavior_change": "bad",
              "risk_summary": "bad",
              "rollback_plan": "bad",
              "applied_relpath": "src/bad.py",
              "applied_text": "bad"
            }]}
            """,
            max_steps=1,
        )
    except ValueError as exc:
        assert "outside the governed demo envelope" in str(exc)
    else:
        raise AssertionError("expected unsafe LLM path to fail")

    try:
        _parse_llm_evolution_steps(
            """
            {"steps": [{
              "step_id": "bad_kind_path",
              "title": "Bad kind path",
              "change_kind": "role_change",
              "target_ref": "org/mandates/not_a_role.md",
              "rationale": "bad",
              "expected_behavior_change": "bad",
              "risk_summary": "bad",
              "rollback_plan": "bad",
              "applied_relpath": "org/mandates/not_a_role.md",
              "applied_text": "bad"
            }]}
            """,
            max_steps=1,
        )
    except ValueError as exc:
        assert "role_change must target org/roles/*.yaml" in str(exc)
    else:
        raise AssertionError("expected change_kind/path mismatch to fail")

    try:
        _parse_llm_evolution_steps(
            """
            {"steps": [
              {
                "step_id": "same",
                "title": "One",
                "change_kind": "mandate_change",
                "target_ref": "org/mandates/one.md",
                "rationale": "one",
                "expected_behavior_change": "one",
                "risk_summary": "one",
                "rollback_plan": "one",
                "applied_relpath": "org/mandates/one.md",
                "applied_text": "one"
              },
              {
                "step_id": "same",
                "title": "Two",
                "change_kind": "mandate_change",
                "target_ref": "org/mandates/two.md",
                "rationale": "two",
                "expected_behavior_change": "two",
                "risk_summary": "two",
                "rollback_plan": "two",
                "applied_relpath": "org/mandates/two.md",
                "applied_text": "two"
              }
            ]}
            """,
            max_steps=2,
        )
    except ValueError as exc:
        assert "duplicate LLM step_id" in str(exc)
    else:
        raise AssertionError("expected duplicate LLM step_id to fail")

    try:
        _parse_llm_evolution_steps(
            """
            {"steps": [{
              "step_id": "broad_role",
              "title": "Broad role",
              "change_kind": "role_change",
              "target_ref": "org/roles/broad_role.yaml",
              "rationale": "bad",
              "expected_behavior_change": "bad",
              "risk_summary": "bad",
              "rollback_plan": "bad",
              "applied_relpath": "org/roles/broad_role.yaml",
              "applied_text": "role_id: role.broad\\nauthorized_paths:\\n  - src/**\\n"
            }]}
            """,
            max_steps=1,
        )
    except ValueError as exc:
        assert "must stay under demo org governance paths" in str(exc)
    else:
        raise AssertionError("expected broad generated role authority to fail")

    try:
        _parse_llm_evolution_steps(
            """
            {"steps": [{
              "step_id": "tool_role",
              "title": "Tool role",
              "change_kind": "role_change",
              "target_ref": "org/roles/tool_role.yaml",
              "rationale": "bad",
              "expected_behavior_change": "bad",
              "risk_summary": "bad",
              "rollback_plan": "bad",
              "applied_relpath": "org/roles/tool_role.yaml",
              "applied_text": "role_id: role.tool\\nauthorized_paths:\\n  - org/reviews/**\\ntools:\\n  - bash\\n"
            }]}
            """,
            max_steps=1,
        )
    except ValueError as exc:
        assert "cannot declare external capability or secret fields" in str(exc)
    else:
        raise AssertionError("expected generated role tool declaration to fail")


def test_live_planner_prompt_prioritizes_self_evolving_firm_charter(tmp_path):
    run_demo(tmp_path, iterations=0)
    demo_firm = tmp_path / "demo-firm"

    prompt = _llm_evolution_prompt(demo_firm, iterations=1, prompt_mode="compact")

    assert "--- org/charters/self_evolving_firm.md ---" in prompt
    assert "trailing workload score per dispatched budget unit" in prompt
    assert "org/workload/inbox" in prompt
    assert "project_charter_change" in prompt
