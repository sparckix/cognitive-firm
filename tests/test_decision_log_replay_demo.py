from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from decision_log_replay_demo import main, run_replay  # noqa: E402


def test_decision_log_replay_demo_reconstructs_safe_and_blocked_packets(tmp_path: Path):
    payload = run_replay(tmp_path)

    assert payload["summary"] == {
        "records": 42,
        "evaluations": 2,
        "packets": 2,
        "review_ready": 1,
        "blocked": 1,
        "verdict": "passed",
    }
    assert payload["candidate_proposer"] == {
        "safe_status": "candidate",
        "safe_contexts": 1,
        "unsafe_status": "no_candidate",
        "unsafe_rejected_contexts": 1,
    }
    rows = {row["candidate_policy_id"]: row for row in payload["replayed_packets"]}
    safe = rows["policy.support.enterprise-senior-review"]
    unsafe = rows["policy.support.renewals-auto-send"]

    assert safe["evaluation_status"] == "promotable"
    assert safe["packet_status"] == "review_ready"
    assert safe["delta_mean_reward"] is not None
    assert safe["delta_mean_reward"] > 0
    assert safe["review_blockers"] == []

    assert unsafe["evaluation_status"] == "blocked"
    assert unsafe["packet_status"] == "blocked"
    assert unsafe["delta_mean_reward"] is not None
    assert unsafe["delta_mean_reward"] > 0
    assert any("negative externality rate" in blocker for blocker in unsafe["review_blockers"])
    assert any("human review rate" in blocker for blocker in unsafe["review_blockers"])


def test_decision_log_replay_demo_cli_compact(capsys):
    assert main([]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["demo"] == "decision_log_replay"
    assert payload["no_external_calls"] is True
    assert payload["logs_only_replay"] is True
    assert payload["summary"]["verdict"] == "passed"
    assert payload["candidate_proposer"]["safe_status"] == "candidate"
    assert payload["candidate_proposer"]["unsafe_status"] == "no_candidate"
    assert "log_paths" not in payload
    assert {row["packet_status"] for row in payload["replayed_packets"]} == {
        "review_ready",
        "blocked",
    }


def test_decision_log_replay_demo_cli_full_json_keeps_logs(tmp_path: Path, capsys):
    assert main(["--workdir", str(tmp_path), "--full-json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["verdict"] == "passed"
    assert "log_paths" in payload
    for path in payload["log_paths"].values():
        assert Path(path).exists()
