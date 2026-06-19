from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_a2a_h2a_command_conformance_script_runs_service_and_cli_path():
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT / "src") if not existing else f"{ROOT / 'src'}{os.pathsep}{existing}"

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "a2a_h2a_command_conformance.py")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["fixture"] == "a2a_h2a_command_conformance"
    assert payload["pending_to_fulfilled_blocked"] is True
    assert payload["blocked_state_seen"] == "blocked_input"
    assert payload["blocked_obligation_visible"] is True
    assert payload["human_work_obligation_linked"] is True
    assert payload["receipt_before_integration_enforced"] is True
    assert payload["final_human_work_state"] == "integrated"
    assert payload["final_obligation_state"] == "fulfilled"
    assert payload["blocked_obligation_cleared"] is True
