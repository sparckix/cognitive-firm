from __future__ import annotations

import json
import subprocess
from pathlib import Path

from demos.self_evolving_org.daemon_smoke import (
    _build_report,
    run_governed_smoke,
    run_smoke,
)


def test_self_evolving_daemon_smoke_runs_against_installed_starter_firm(tmp_path: Path) -> None:
    report = run_smoke(tmp_path)

    summary = report["summary"]
    assert summary["verdict"] == "passed"
    assert summary["daemon_process_ok"] is True
    assert summary["task_closed_done"] is True
    assert summary["role_session_count"] == 1
    assert summary["daemon_continuity_written"] is True
    assert summary["task_checkpoint_written"] is True
    assert summary["transition_log_written"] is True
    assert summary["daemon_prompt_written"] is True
    assert summary["action_attestation_written"] is True
    assert summary["stub_runtime_invoked"] is True
    assert summary["runtime_run_count"] == 1
    assert summary["runtime_run_completed"] is True
    assert summary["dispatch_chain_valid"] is True
    assert report["dispatch_proof"]["valid"] is True
    assert report["dispatch_proof"]["attestation_count"] == 1
    assert report["dispatch_proof"]["verified_dispatch_attestation"] is True
    assert report["dispatch_proof"]["checkpoint_statuses"] == {
        "dispatch_agent_cli": "started",
        "dispatch_agent_cli_result": "completed",
    }
    demo_firm = tmp_path / "demo-firm"
    charter = demo_firm / "org" / "charters" / "self_evolving_firm.md"
    assert charter.exists()
    assert "trailing workload score per unit dispatched budget" in charter.read_text(
        encoding="utf-8"
    )
    assert (demo_firm / "org" / "workload" / "inbox" / "packets.jsonl").exists()
    attestation_rows = [
        json.loads(line)
        for line in (
            demo_firm / "org" / "attestations" / "action_attestations.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    receipt = attestation_rows[0]["metadata"]["agent_invocation_receipt"]
    assert receipt["schema_version"] == "agent_invocation_receipt.v1"
    assert receipt["command_argv"][-1] == "{prompt}"
    assert receipt["stdout_digest"].startswith("sha256:")
    assert any(ref.startswith("prompt:sha256:") for ref in attestation_rows[0]["input_refs"])
    assert any(ref.startswith("stdout:sha256:") for ref in attestation_rows[0]["output_refs"])
    reports_dir = demo_firm / "reports"
    markdown = (reports_dir / "self-evolving-daemon-smoke.md").read_text(
        encoding="utf-8"
    )
    assert "# Self-Evolving Daemon Dispatch Smoke" in markdown
    assert "## Dispatch Proof" in markdown
    assert "| action attestation | org/attestations/action_attestations.jsonl |" in markdown
    assert "| daemon prompt | workspace/agent_prompts/" in markdown
    assert (demo_firm / report["artifacts"]["daemon_prompt"]).exists()
    daemon_prompt = (demo_firm / report["artifacts"]["daemon_prompt"]).read_text(
        encoding="utf-8"
    )
    assert "org/charters/self_evolving_firm.md" in daemon_prompt
    assert "org/workload/inbox" in daemon_prompt

    timeline = json.loads(
        (reports_dir / "self-evolving-daemon-timeline.json").read_text(
            encoding="utf-8"
        )
    )
    assert timeline["graph_kind"] == "self_evolving_daemon_dispatch_timeline"
    assert timeline["summary"]["dispatch_chain_valid"] is True
    node_ids = {node["id"] for node in timeline["nodes"]}
    assert "role:org_evolver" in node_ids
    assert "mandate:org_evolver" in node_ids
    assert "attestation:agent_cli_dispatch" in node_ids
    assert any(edge["label"] == "attests" for edge in timeline["edges"])

    html = (reports_dir / "self-evolving-daemon-timeline.html").read_text(
        encoding="utf-8"
    )
    assert "Self-Evolving Daemon Dispatch Timeline" in html
    assert 'id="graph-data"' in html
    assert "textContent = text(node.kind)" in html


def test_self_evolving_daemon_governed_smoke_routes_planner_output(tmp_path: Path) -> None:
    report = run_governed_smoke(tmp_path)
    demo_firm = tmp_path / "demo-firm"

    assert report["demo"] == "self_evolving_daemon_governed_smoke"
    assert report["no_external_calls"] is True
    assert report["planner_transport"] == "daemon_subscription_cli"
    assert report["iterations_run"] == 1
    assert report["summary"]["verdict"] == "passed"
    assert report["summary"]["approved"] == 1
    assert report["summary"]["mutation_proofs_valid"] is True
    assert report["summary"]["mutation_proof_replay_valid"] is True
    assert report["summary"]["decision_aggregation_cases"] == 1
    assert report["daemon_dispatch"]["valid"] is True
    assert report["daemon_dispatch"]["run_id"]
    assert report["daemon_dispatch"]["report_ref"] == "file://reports/self-evolving-daemon-smoke.json"
    assert (demo_firm / "workspace" / "daemon_planner_steps.json").exists()

    receipt = report["planner_receipts"][0]
    assert receipt["transport"] == "daemon_subscription_cli"
    assert receipt["metadata"]["daemon_run_id"] == report["daemon_dispatch"]["run_id"]
    assert receipt["metadata"]["planner_artifact_ref"] == "file://workspace/daemon_planner_steps.json"
    assert f"file://reports/planner/{receipt['receipt_id']}/prompt.md" in receipt[
        "artifact_refs"
    ]
    assert (demo_firm / "reports" / "planner" / receipt["receipt_id"] / "prompt.md").exists()

    step = report["steps"][0]
    assert step["step_id"] == "daemon_planned_evidence_route"
    assert step["decision_aggregation_result"]["procedure_kind"] == "quorum_majority"
    assert step["decision_aggregation_result"]["recommendation"] == "approve"
    assert step["decision_aggregation_result"]["quorum_met"] is True
    assert f"planner_receipt:{receipt['receipt_id']}" in step["proof_evidence_carrier_refs"]
    assert step["decision_aggregation_case_ref"] in step["proof_evidence_carrier_refs"]
    assert step["mutation_proof"]["valid"] is True
    assert (demo_firm / step["applied_path"]).exists()

    markdown = (demo_firm / "reports" / "self-evolving-org-demo.md").read_text(
        encoding="utf-8"
    )
    assert "## Daemon Dispatch" in markdown
    assert report["daemon_dispatch"]["run_id"] in markdown

    timeline = json.loads(
        (demo_firm / "reports" / "self-evolving-org-timeline.json").read_text(
            encoding="utf-8"
        )
    )
    assert any(node["kind"] == "daemon_dispatch" for node in timeline["nodes"])
    assert any(node["kind"] == "decision_aggregation_case" for node in timeline["nodes"])
    assert any(edge["label"] == "plans" for edge in timeline["edges"])


def test_self_evolving_daemon_governed_smoke_accepts_live_agent_cli_shape(
    tmp_path: Path,
) -> None:
    agent_cli = tmp_path / "live_agent_cli.py"
    agent_cli.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

Path("workspace").mkdir(exist_ok=True)
Path("workspace/daemon_planner_steps.json").write_text(json.dumps({
    "steps": [{
        "step_id": "live_cli_evidence_route",
        "title": "Live CLI evidence route",
        "change_kind": "mandate_change",
        "target_ref": "org/mandates/live_cli_evidence_route.md",
        "rationale": "The live CLI-shaped role saw that evidence routes need a durable note.",
        "expected_behavior_change": "Future proposals preserve evidence routes before review.",
        "risk_summary": "Narrows evidence requirements; grants no new authority.",
        "rollback_plan": "Remove org/mandates/live_cli_evidence_route.md.",
        "applied_relpath": "org/mandates/live_cli_evidence_route.md",
        "applied_text": "# Live CLI Evidence Route\\n\\nPreserve evidence routes before review."
    }]
}), encoding="utf-8")
print(json.dumps({"status": "completed", "planner_artifact": "workspace/daemon_planner_steps.json"}))
""",
        encoding="utf-8",
    )
    agent_cli.chmod(0o755)

    report = run_governed_smoke(
        tmp_path / "live-shape",
        agent_cli=str(agent_cli),
        agent_adapter="claude_print",
    )
    demo_firm = tmp_path / "live-shape" / "demo-firm"

    assert report["demo"] == "self_evolving_daemon_governed_smoke"
    assert report["no_external_calls"] is False
    assert report["summary"]["verdict"] == "passed"
    assert report["summary"]["decision_aggregation_cases"] == 1
    assert report["steps"][0]["step_id"] == "live_cli_evidence_route"
    assert report["steps"][0]["decision_aggregation_result"]["recommendation"] == "approve"
    assert (demo_firm / "org" / "mandates" / "live_cli_evidence_route.md").exists()

    daemon_report = json.loads(
        (demo_firm / "reports" / "self-evolving-daemon-smoke.json").read_text(
            encoding="utf-8"
        )
    )
    assert daemon_report["summary"]["prompt_capture_expected"] is False
    assert daemon_report["summary"]["stub_runtime_invoked"] is False
    assert daemon_report["summary"]["daemon_continuity_written"] is True
    assert daemon_report["summary"]["task_checkpoint_written"] is True
    assert daemon_report["summary"]["daemon_prompt_written"] is True
    assert daemon_report["artifacts"]["session_checkpoint"].startswith("org/sessions/")
    assert daemon_report["artifacts"]["daemon_prompt"].startswith("workspace/agent_prompts/")
    assert (demo_firm / daemon_report["artifacts"]["daemon_prompt"]).exists()
    receipt = report["planner_receipts"][0]
    assert receipt["metadata"]["stub_runtime"] is False
    assert receipt["metadata"]["agent_cli"] == "live_agent_cli.py"
    runbook = report["operator_runbook"]
    daemon_rerun = [
        row["command"] for row in runbook["commands"] if row["label"] == "daemon_live_rerun"
    ][0]
    assert "AGENT_CLI=live_agent_cli.py" in daemon_rerun
    assert "AGENT_ADAPTER=claude_print" in daemon_rerun
    assert f"file://reports/planner/{receipt['receipt_id']}/prompt.md" in receipt[
        "artifact_refs"
    ]
    company_state = json.loads(
        (demo_firm / "reports" / "self-evolving-org-company-state.json").read_text(
            encoding="utf-8"
        )
    )
    planner_transcript = company_state["agent_transcripts"]["planner_receipts"][0]
    assert planner_transcript["prompt_text"]
    assert "You are the autonomous org_evolver role" in planner_transcript["prompt_text"]
    assert "org/charters/self_evolving_firm.md" in planner_transcript["prompt_text"]


def test_self_evolving_daemon_governed_smoke_accepts_live_reviewer_runtime(
    tmp_path: Path,
) -> None:
    agent_cli = tmp_path / "live_agent_cli.py"
    agent_cli.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

Path("workspace").mkdir(exist_ok=True)
Path("workspace/daemon_planner_steps.json").write_text(json.dumps({
    "steps": [{
        "step_id": "daemon_live_review_route",
        "title": "Daemon live review route",
        "change_kind": "mandate_change",
        "target_ref": "org/mandates/daemon_live_review_route.md",
        "rationale": "Daemon-governed runs should preserve live reviewer evidence.",
        "expected_behavior_change": "Reviewer receipts join the governed mutation proof.",
        "risk_summary": "Adds reviewer evidence; grants no new authority.",
        "rollback_plan": "Remove org/mandates/daemon_live_review_route.md.",
        "applied_relpath": "org/mandates/daemon_live_review_route.md",
        "applied_text": "# Daemon Live Review Route\\n\\nLive reviewer receipts join the proof."
    }]
}), encoding="utf-8")
print(json.dumps({"status": "completed", "planner_artifact": "workspace/daemon_planner_steps.json"}))
""",
        encoding="utf-8",
    )
    reviewer = tmp_path / "reviewer.py"
    reviewer.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import json
import sys

prompt = sys.argv[-1]
assert "cognitive-firm reviewer office" in prompt
print(json.dumps({
    "position": "approve",
    "rationale": "The daemon-governed proposal is bounded and evidence-carrying.",
    "evidence_summary": "Reviewed daemon proposal prompt."
}))
""",
        encoding="utf-8",
    )
    agent_cli.chmod(0o755)
    reviewer.chmod(0o755)

    report = run_governed_smoke(
        tmp_path / "live-reviewer-shape",
        agent_cli=str(agent_cli),
        agent_adapter="claude_print",
        reviewer_runtime=str(reviewer),
        reviewer_adapter="claude_print",
        reviewer_timeout_seconds=30,
    )
    demo_firm = tmp_path / "live-reviewer-shape" / "demo-firm"

    assert report["summary"]["verdict"] == "passed"
    step = report["steps"][0]
    assert step["step_id"] == "daemon_live_review_route"
    assert len(step["reviewer_invocations"]) == 3
    assert any(ref.startswith("attestation:") for ref in step["proof_evidence_carrier_refs"])
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


def test_daemon_timeout_report_falls_back_to_prompt_file(tmp_path: Path) -> None:
    demo_firm = tmp_path / "demo-firm"
    prompt_dir = demo_firm / "workspace" / "agent_prompts"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "org_evolver_20260612T034404Z.md"
    prompt_file.write_text("bounded role prompt", encoding="utf-8")

    report = _build_report(
        demo_firm=demo_firm,
        receipt={},
        command=["agent-daemon"],
        result=subprocess.CompletedProcess(
            ["agent-daemon"],
            returncode=124,
            stdout="",
            stderr="daemon subprocess timed out after 120 seconds",
        ),
        expect_prompt_capture=False,
    )

    assert report["summary"]["verdict"] == "failed"
    assert report["summary"]["daemon_returncode"] == 124
    assert report["summary"]["daemon_process_timed_out"] is True
    assert report["summary"]["daemon_prompt_written"] is True
    assert (
        report["artifacts"]["daemon_prompt"]
        == "workspace/agent_prompts/org_evolver_20260612T034404Z.md"
    )
