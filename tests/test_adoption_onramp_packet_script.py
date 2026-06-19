from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    script_path = ROOT / "scripts" / "adoption_onramp_packet.py"
    spec = importlib.util.spec_from_file_location("adoption_onramp_packet", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_adoption_onramp_packet_collects_adapter_policy_preview_by_default() -> None:
    module = _load_script()
    optional_steps = {step.check_id: step for step in module.OPTIONAL_STEPS}

    step = optional_steps["adapter_policy_preview"]
    assert step.args == ("scripts/langgraph_adapter_policy_preview.py",)
    assert step.output_name == "adapter-policy-preview.json"
    assert step.optional is True


def test_adoption_onramp_packet_core_collection(tmp_path: Path) -> None:
    output_dir = tmp_path / "onramp"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/adoption_onramp_packet.py",
            "--target-label",
            "core-onramp",
            "--output-dir",
            str(output_dir),
            "--core-only",
            "--timeout-seconds",
            "30",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)

    assert payload["schema"] == "adoption_onramp_collection.v1"
    assert payload["ok"] is True
    assert payload["summary"]["commands"] == 3
    assert payload["summary"]["passed_commands"] == 3
    assert payload["summary"]["failed_checks"] == 0
    assert payload["summary"]["warning_checks"] == 0
    assert payload["summary"]["evidence_quality_blockers"] == 0
    assert payload["summary"]["optional_evidence_blockers"] == 0
    assert payload["summary"]["ready_for_human_adoption_review"] is True
    assert payload["boundary"]["not_a_workflow_engine"] is True
    assert Path(payload["packet_path"]).exists()
    assert Path(payload["markdown_path"]).exists()

    packet = json.loads(Path(payload["packet_path"]).read_text(encoding="utf-8"))
    assert packet["schema"] == "adoption_readiness_packet.v1"
    assert packet["summary"]["observed_checks"] == 3
    assert packet["summary"]["composition_packets"] == 2
    assert packet["summary"]["composition_blockers"] == 0
    assert packet["summary"]["evidence_quality_blockers"] == 0
    assert [
        step["packet_status"] for step in packet["reviewer_path"]["steps"]
    ] == [
        "external_gate",
        "source_collector",
        "this_packet",
    ]
    assert "First gated action" in Path(payload["markdown_path"]).read_text(
        encoding="utf-8"
    )
    assert "Reviewer Path" in Path(payload["markdown_path"]).read_text(
        encoding="utf-8"
    )


def test_adoption_onramp_packet_accepts_external_live_agent_result(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "onramp"
    live_result = tmp_path / "live-agent-result.json"
    live_result.write_text(
        json.dumps(
            {
                "planner_transport": "subscription_cli",
                "summary": {
                    "verdict": "passed",
                    "budget_units_consumed": 1,
                    "budget_units_remaining": 0,
                    "learning_events": 1,
                    "learning_use_receipts": 1,
                    "context_packets": 1,
                    "verified_context_packets": 1,
                    "provenance_reports": 1,
                    "proposal_review_packets": 2,
                    "proposal_review_follow_through_closed_loop": 1,
                    "mutation_proofs_valid": True,
                    "mutation_proof_replay_valid": True,
                    "termination_reason": "completed_selected_steps",
                }
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/adoption_onramp_packet.py",
            "--target-label",
            "live-onramp",
            "--output-dir",
            str(output_dir),
            "--core-only",
            "--timeout-seconds",
            "30",
            "--result",
            f"bounded_live_agent_run={live_result}",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["summary"]["commands"] == 3
    assert payload["summary"]["external_results"] == 1
    assert payload["summary"]["observed_checks"] == 4
    assert payload["summary"]["failed_checks"] == 0
    assert payload["summary"]["optional_evidence_blockers"] == 0
    assert payload["summary"]["ready_for_human_adoption_review"] is True
    assert payload["external_results"][0]["check_id"] == "bounded_live_agent_run"
    assert payload["boundary"]["does_not_run_external_agents"] is True

    packet = json.loads(Path(payload["packet_path"]).read_text(encoding="utf-8"))
    by_id = {row["check_id"]: row for row in packet["checks"]}
    live_row = by_id["bounded_live_agent_run"]
    assert live_row["status"] == "passed"
    assert live_row["result_summary"] == {
        "planner_transport": "subscription_cli",
        "summary.budget_units_consumed": 1,
        "summary.learning_events": 1,
        "summary.learning_use_receipts": 1,
        "summary.context_packets": 1,
        "summary.verified_context_packets": 1,
        "summary.provenance_reports": 1,
        "summary.proposal_review_packets": 2,
        "summary.proposal_review_follow_through_closed_loop": 1,
        "summary.mutation_proofs_valid": True,
        "summary.mutation_proof_replay_valid": True,
        "summary.termination_reason": "completed_selected_steps",
    }
    assert f"file://{live_result.resolve()}" in packet["evidence_refs"]


def test_adoption_onramp_packet_blocks_failed_external_live_agent_result(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "onramp"
    live_result = tmp_path / "live-agent-result.json"
    live_result.write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/adoption_onramp_packet.py",
            "--target-label",
            "live-onramp",
            "--output-dir",
            str(output_dir),
            "--core-only",
            "--timeout-seconds",
            "30",
            "--result",
            f"bounded_live_agent_run={live_result}",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["summary"]["commands"] == 3
    assert payload["summary"]["failed_checks"] == 1
    assert payload["summary"]["optional_evidence_blockers"] == 1
    assert payload["summary"]["ready_for_human_adoption_review"] is False

    packet = json.loads(Path(payload["packet_path"]).read_text(encoding="utf-8"))
    by_id = {row["check_id"]: row for row in packet["checks"]}
    live_row = by_id["bounded_live_agent_run"]
    assert live_row["status"] == "failed"
    assert live_row["required"] is False
    assert any(
        "summary.context_packets expected at least 1, observed 0" in error
        for error in live_row["errors"]
    )
