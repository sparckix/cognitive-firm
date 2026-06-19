from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_script():
    script_path = ROOT / "scripts" / "agent_fleet_audit_demo.py"
    spec = importlib.util.spec_from_file_location("agent_fleet_audit_demo", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_burden_compiler():
    script_path = ROOT / "scripts" / "field_pilot_operator_burden_compile.py"
    spec = importlib.util.spec_from_file_location(
        "field_pilot_operator_burden_compile",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_fleet_audit_demo_compact_summary(capsys) -> None:
    module = _load_script()

    assert module.main([]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["demo"] == "agent_fleet_audit_trail"
    assert payload["no_external_calls"] is True
    assert payload["bundle_validation"]["ok"] is True
    assert payload["summary"]["verdict"] == "passed"
    assert payload["summary"]["counts"]["action_attestations"] == 1
    assert payload["summary"]["counts"]["human_work_sessions"] == 0
    assert payload["summary"]["run_state"] == "completed"
    assert payload["summary"]["owner_role"] == "role.manager"
    assert payload["agent_invocation"]["schema_version"] == "agent_invocation_receipt.v1"
    assert payload["agent_invocation"]["runtime"] == "claude"
    assert payload["agent_invocation"]["adapter"] == "claude_print"
    assert payload["agent_invocation"]["agent_session_id"] == "claude-demo-session"
    assert payload["operator_burden_field_pilot"] == {
        "schema": "operator_burden_field_pilot_summary.v1",
        "measurement_status": "stable",
        "n_total": 6,
        "mean_touchpoint_delta": -2.3333,
        "projection_undercounted_rows": 0,
        "review_reasons": [],
    }


def test_agent_fleet_audit_demo_full_json_redacts_prompt(capsys) -> None:
    module = _load_script()

    assert module.main(["--full-json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    receipt = payload["agent_invocation_receipt"]
    attestation = payload["action_attestation"]
    bundle = payload["governed_run_attestation"]

    assert payload["bundle_validation"]["ok"] is True
    assert receipt["command_argv"][-1] == "{prompt}"
    assert "Inspect the launch checklist" not in json.dumps(receipt["command_argv"])
    assert receipt["prompt_digest"].startswith("sha256:")
    assert payload["operator_burden_field_pilot"]["schema"] == (
        "operator_burden_field_pilot_summary.v1"
    )
    assert payload["operator_burden_field_pilot"]["measurement_status"] == "stable"
    assert attestation["subject_ref"].startswith("agent_invocation_receipt:")
    assert attestation["metadata"]["agent_invocation_receipt"]["schema_version"] == (
        "agent_invocation_receipt.v1"
    )
    assert bundle["action_attestations"][0]["attestation_id"] == attestation["attestation_id"]
    assert bundle["verdict"] == "passed"


def test_agent_fleet_audit_demo_writes_operator_runbook(tmp_path, capsys) -> None:
    module = _load_script()
    outdir = tmp_path / "agent-fleet-audit"

    assert module.main(["--output-dir", str(outdir)]) == 0
    payload = json.loads(capsys.readouterr().out)
    runbook = payload["operator_runbook"]

    assert Path(runbook["json"]).exists()
    assert Path(runbook["markdown"]).exists()
    assert Path(runbook["packet"]).exists()
    assert Path(runbook["operator_burden_field_pilot"]).exists()

    runbook_json = json.loads(Path(runbook["json"]).read_text())
    assert runbook_json["schema"] == "governed_run_operator_summary.v1"
    assert runbook_json["run_label"] == "agent_fleet_audit"
    assert runbook_json["summary"]["verdict"] == "passed"
    assert runbook_json["status"]["bundle_count"] == 1
    assert runbook_json["status"]["operator_burden_level"] == "low"
    assert runbook_json["status"]["estimated_human_touchpoints"] == 0
    assert runbook_json["operator_burden"]["schema"] == "operator_burden_projection.v1"
    assert runbook_json["operator_burden"]["boundary"]["does_not_assign_work"] is True
    assert runbook_json["metadata"]["runtime"] == "claude"
    assert runbook_json["metadata"]["adapter"] == "claude_print"
    assert runbook_json["commands"][0]["label"] == "rerun no-cost audit"

    burden_summary = json.loads(
        Path(runbook["operator_burden_field_pilot"]).read_text()
    )
    assert burden_summary["schema"] == "operator_burden_field_pilot_summary.v1"
    assert burden_summary["measurement_status"] == "stable"
    assert burden_summary["phases"]["pilot"]["mean_actual_human_touchpoints"] == 1.6667
    assert burden_summary["boundary"]["does_not_optimize_routing"] is True

    runbook_md = Path(runbook["markdown"]).read_text()
    assert "# Governed Run Operator Summary" in runbook_md
    assert "## Operator Burden" in runbook_md
    assert "agent invocation receipt" in runbook_md
    assert "make agent-fleet-audit-demo" in runbook_md


def test_agent_fleet_audit_demo_can_write_result_file(tmp_path, capsys) -> None:
    module = _load_script()
    output_path = tmp_path / "agent-fleet-result.json"

    assert module.main(["--output", str(output_path)]) == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert file_payload == stdout_payload
    assert file_payload["summary"]["verdict"] == "passed"
    assert file_payload["bundle_validation"]["ok"] is True
    assert file_payload["agent_invocation"]["receipt_ref"].startswith(
        "agent_invocation_receipt:"
    )


def test_agent_fleet_review_packet_make_target_writes_persistent_artifacts(
    tmp_path: Path,
) -> None:
    outdir = tmp_path / "agent-fleet-review"

    result = subprocess.run(
        [
            "make",
            "-s",
            "agent-fleet-review-packet",
            f"AGENT_FLEET_AUDIT_OUTDIR={outdir}",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["demo"] == "agent_fleet_audit_trail"
    assert payload["summary"]["verdict"] == "passed"
    assert payload["bundle_validation"]["ok"] is True
    assert (outdir / "agent-fleet-audit-summary.json").exists()
    assert (outdir / "agent-fleet-audit-runbook.md").exists()
    assert (outdir / "agent-fleet-audit-runbook.json").exists()
    assert (outdir / "agent-fleet-audit-packet.json").exists()
    assert (outdir / "operator-burden-field-pilot-summary.json").exists()

    runbook_md = (outdir / "agent-fleet-audit-runbook.md").read_text(
        encoding="utf-8"
    )
    assert "agent invocation receipt" in runbook_md
    assert "make agent-fleet-audit-demo" in runbook_md


def test_field_pilot_operator_burden_compile_csv_rows(tmp_path: Path) -> None:
    module = _load_burden_compiler()
    rows = tmp_path / "operator-burden.csv"
    rows.write_text(
        "\n".join(
            [
                "phase,run_ref,actual_human_touchpoints,projected_human_touchpoints,coordination_minutes,rework_count,missing_receipts,hidden_burden_reported",
                "baseline,run:base_1,4,,35,1,1,false",
                "baseline,run:base_2,3,,30,1,0,false",
                "pilot,run:pilot_1,2,2,18,0,0,false",
                "pilot,run:pilot_2,1,1,12,0,0,false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.compile_operator_burden(
        tmp_path,
        rows,
        min_baseline_runs=2,
        min_pilot_runs=2,
    )

    assert payload["verdict"] == "passed"
    assert payload["summary"] == {
        "schema": "operator_burden_field_pilot_summary.v1",
        "measurement_status": "stable",
        "n_total": 4,
        "baseline_runs": 2,
        "pilot_runs": 2,
        "mean_touchpoint_delta": -2.0,
        "projection_undercounted_rows": 0,
        "review_reasons": [],
    }
    output = tmp_path / "operator-burden-field-pilot-summary.json"
    assert output.exists()
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["boundary"]["does_not_assign_work"] is True


def test_field_pilot_operator_burden_compile_jsonl_review_required(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_burden_compiler()
    rows = tmp_path / "operator-burden.jsonl"
    rows.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "phase": "baseline",
                        "run_ref": "run:base_1",
                        "actual_human_touchpoints": 1,
                    }
                ),
                json.dumps(
                    {
                        "phase": "pilot",
                        "run_ref": "run:pilot_1",
                        "actual_human_touchpoints": 4,
                        "projected_human_touchpoints": 1,
                        "hidden_burden_reported": True,
                        "missing_receipts": 1,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert module.main([str(tmp_path), str(rows), "--projection-tolerance", "0.5"]) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["verdict"] == "review_required"
    reasons = {reason["reason"] for reason in payload["summary"]["review_reasons"]}
    assert "hidden_burden_reported" in reasons
    assert "projection_undercounted_human_touchpoints" in reasons
