from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_capability_signal_demo_runs_without_external_calls():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "demos" / "governance_carriers" / "capability_signal_demo.py"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["demo"] == "capability_signal"
    assert payload["no_external_calls"] is True
    assert payload["summary"]["verdict"] == "passed"
    assert payload["summary"]["signals"] == 2
    assert payload["summary"]["closed_abstention"] is True
    assert payload["summary"]["abstention_counts_as_failure"] is False
