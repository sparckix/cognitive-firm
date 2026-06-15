from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase_execution_demo_runs():
    result = subprocess.run(
        [sys.executable, "demos/governance_carriers/phase_execution_demo.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    summary = payload["summary"]
    assert payload["no_external_calls"] is True
    assert summary["verdict"] == "passed"
    assert summary["plan_status"] == "passed"
    assert summary["attempts"] == 1
    assert summary["directives"] == 3
    assert summary["feedback"] == 2
    assert summary["budget_after_failed_verification"] == 4
