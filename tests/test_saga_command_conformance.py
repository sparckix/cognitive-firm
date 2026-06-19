from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_saga_command_conformance_script_runs_cli_path():
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT / "src") if not existing else f"{ROOT / 'src'}{os.pathsep}{existing}"

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "saga_command_conformance.py")],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["fixture"] == "saga_command_conformance"
    assert payload["non_terminal_compensation_blocked"] is True
    assert payload["compensation_requests"] == 1
    assert payload["active_saga_visible_before_completion"] is True
    assert payload["active_saga_cleared_after_completion"] is True
    assert payload["compensation_parent_links_root_failure"] is True
    assert payload["compensation_target_role"] == "bob"
