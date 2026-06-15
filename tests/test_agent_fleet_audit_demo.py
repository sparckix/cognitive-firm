from __future__ import annotations

import importlib.util
import json
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

    runbook_json = json.loads(Path(runbook["json"]).read_text())
    assert runbook_json["schema"] == "governed_run_operator_summary.v1"
    assert runbook_json["run_label"] == "agent_fleet_audit"
    assert runbook_json["summary"]["verdict"] == "passed"
    assert runbook_json["status"]["bundle_count"] == 1
    assert runbook_json["metadata"]["runtime"] == "claude"
    assert runbook_json["metadata"]["adapter"] == "claude_print"
    assert runbook_json["commands"][0]["label"] == "rerun no-cost audit"

    runbook_md = Path(runbook["markdown"]).read_text()
    assert "# Governed Run Operator Summary" in runbook_md
    assert "agent invocation receipt" in runbook_md
    assert "make agent-fleet-audit-demo" in runbook_md
