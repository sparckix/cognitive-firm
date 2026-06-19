from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_a2a_delegation_command_conformance_script_runs_service_path():
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT / "src") if not existing else f"{ROOT / 'src'}{os.pathsep}{existing}"

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "a2a_delegation_command_conformance.py")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["fixture"] == "a2a_delegation_command_conformance"
    assert payload["unauthorized_edge_blocked"] is True
    assert payload["unauthorized_edge_wrote_no_message"] is True
    assert "receiver is in sender" in payload["allowed_handoff_policy"]
    assert payload["handoff_started_pending"] is True
    assert payload["envelope_ack_obligation_still_pending"] is True
    assert payload["pending_to_fulfilled_blocked"] is True
    assert payload["ordered_lifecycle"] == ["accepted", "in_progress", "fulfilled"]
    assert payload["terminal_transition_blocked"] is True
    assert payload["inform_has_no_obligation"] is True
    assert payload["thread_guard_blocked"] is True
    assert payload["parent_depth_guard_blocked"] is True
    assert payload["mirrors_stay_consistent"] is True
    assert payload["boundary"]["synthesizes_route"] is False
    assert payload["boundary"]["schedules_work"] is False
    assert payload["boundary"]["runs_agent"] is False
    assert payload["boundary"]["owns_workflow"] is False
