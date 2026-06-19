from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_a2h_command_conformance_script_runs_cli_path():
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT / "src") if not existing else f"{ROOT / 'src'}{os.pathsep}{existing}"

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "a2h_command_conformance.py")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["fixture"] == "a2h_command_conformance"
    assert payload["receipt_before_integration_enforced"] is True
    assert payload["ready_for_agent_followup_before_integration"] is True
    assert payload["followup_missing_receipt_visible"] is True
    assert payload["followup_cleared_after_integration"] is True
    assert payload["completed_without_receipt_state"] == "completed"
    assert payload["final_state"] == "integrated"
    assert payload["resource_kind"] == "HumanWorkSession"
    assert payload["resource_receipt_present"] is True
