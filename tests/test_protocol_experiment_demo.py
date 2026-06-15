from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_protocol_experiment_demo_runs_without_external_calls():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "demos" / "governance_carriers" / "protocol_experiment_demo.py"),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["demo"] == "protocol_experiment"
    assert payload["no_external_calls"] is True
    assert payload["summary"]["verdict"] == "passed"
    assert payload["summary"]["report_status"] == "review_ready"
    assert payload["summary"]["recommended_protocol"] == "batched_sequential"
    assert payload["summary"]["governance_candidate_kind"] == "route_policy_change"
    assert payload["summary"]["learning_candidate_id"].startswith("ltc_")
    assert payload["summary"]["proposal_id"].startswith("gcp_")
    assert payload["summary"]["proposal_status"] == "review_ready"
    assert payload["summary"]["decision"] == "approve"
    assert payload["summary"]["approval_event_id"].startswith("kevt_")
    assert payload["summary"]["governed_promotion_ok"] is True
