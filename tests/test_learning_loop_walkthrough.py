from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_learning_loop_walkthrough_emits_context_packet_and_receipt(
    tmp_path: Path,
) -> None:
    default_workspace = tmp_path / "default-workspace"
    env = {**os.environ, "COGNITIVE_FIRM_WORKSPACE": str(default_workspace)}
    result = subprocess.run(
        [sys.executable, "scripts/learning_loop_walkthrough.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["context_packet"].startswith("ctx_")
    assert payload["verified_context_packet"] == payload["context_packet"]
    assert payload["learning_use_receipt"].startswith("lenc_")
    assert payload["learning_loop_state"] == "awaiting_outcome_verdict"
    assert payload["learning_loop_outcome_links"] == 1
    assert payload["learning_loop_routine_reviews"] == 1
    assert payload["run_id"] == "run_learning_loop_demo"
    assert payload["replayed_for_future_work"] is True
    assert (default_workspace / "transitions.jsonl").exists() is False


def test_learning_loop_walkthrough_can_write_output_file(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "learning-loop.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/learning_loop_walkthrough.py",
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    stdout_payload = json.loads(result.stdout)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert file_payload == stdout_payload
    assert file_payload["ok"] is True
    assert file_payload["learning_use_receipt"].startswith("lenc_")
