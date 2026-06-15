from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_multi_agent_trace_attribution_demo_runs():
    result = subprocess.run(
        [sys.executable, "demos/governance_carriers/multi_agent_trace_attribution_demo.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    summary = payload["summary"]
    assert payload["no_external_calls"] is True
    assert summary["verdict"] == "passed"
    assert summary["trace_events"] == 5
    assert summary["packet_status"] == "review_ready"
    assert summary["candidate_transition_kind"] == "mandate_review"
    assert summary["candidate_observer_only"] is True
    assert summary["abstentions"] == 1
    assert summary["failed_handoffs"] == 1
    assert summary["verifier_failures"] == 1
    assert summary["graph_nodes"] == 4
    assert summary["graph_edges"] == 2
    assert summary["graph_max_depth"] == 3
