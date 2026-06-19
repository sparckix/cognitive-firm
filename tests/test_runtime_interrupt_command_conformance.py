from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_interrupt_command_conformance_script_runs_cli_path():
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT / "src") if not existing else f"{ROOT / 'src'}{os.pathsep}{existing}"

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "runtime_interrupt_command_conformance.py")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["fixture"] == "runtime_interrupt_command_conformance"
    assert payload["checkpoint_before_start_blocked"] is True
    assert payload["missing_interrupt_fields_blocked"] is True
    assert payload["started_event_idempotent"] is True
    assert payload["run_paused_on_interrupt"] is True
    assert payload["interrupt_checkpoint_recorded"] is True
    assert payload["human_work_receipt_required"] is True
    assert payload["human_work_agent_followup_required"] is True
    assert payload["human_work_resume_ref_preserved"] is True
    assert payload["interrupt_replay_reused_human_work"] is True
    assert payload["interrupt_side_effect_key_unique"] is True
    assert payload["boundary"]["executes_runtime"] is False
    assert payload["boundary"]["resumes_runtime"] is False
    assert payload["boundary"]["assigns_human"] is False
    assert payload["boundary"]["owns_workflow"] is False
