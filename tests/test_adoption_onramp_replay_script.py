from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.adoption_onramp_replay import public_repo_paths


ROOT = Path(__file__).resolve().parents[1]


def test_public_repo_paths_exclude_private_and_local_state() -> None:
    paths = public_repo_paths()

    assert "README.md" in paths
    assert "scripts/adoption_onramp_packet.py" in paths
    assert "scripts/adoption_onramp_replay.py" in paths
    assert not any(path.startswith("internal/") for path in paths)
    assert not any(path.startswith(".cognitive-firm-runs/") for path in paths)
    assert ".env" not in paths


def test_adoption_onramp_replay_runs_core_checks_from_public_copy(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "replay"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/adoption_onramp_replay.py",
            "--target-label",
            "outside-adopter-test",
            "--output-dir",
            str(output_dir),
            "--timeout-seconds",
            "30",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        timeout=120,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "adoption_onramp_replay.v1"
    assert payload["ok"] is True
    assert payload["boundary"]["uses_clean_public_copy"] is True
    assert payload["boundary"]["not_a_workflow_engine"] is True
    assert Path(payload["public_copy_root"]).exists()
    assert Path(payload["public_copy_root"], "README.md").exists()
    assert not Path(payload["public_copy_root"], "internal").exists()

    collector_payload = payload["collector"]["payload"]
    assert collector_payload["schema"] == "adoption_onramp_collection.v1"
    assert collector_payload["summary"]["commands"] == 3
    assert collector_payload["summary"]["passed_commands"] == 3
    assert collector_payload["summary"]["ready_for_human_adoption_review"] is True
    assert Path(payload["collector_packet_path"]).exists()
    assert Path(payload["collector_markdown_path"]).exists()

    manifest = json.loads(
        Path(payload["public_copy_manifest_path"]).read_text(encoding="utf-8")
    )
    assert manifest["schema"] == "public_worktree_copy_manifest.v1"
    assert manifest["copied_path_count"] == payload["copied_path_count"]
    assert not any(path.startswith("internal/") for path in manifest["paths"])


def test_adoption_onramp_replay_can_run_full_checks_from_public_copy(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "full-replay"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/adoption_onramp_replay.py",
            "--target-label",
            "outside-adopter-full-test",
            "--output-dir",
            str(output_dir),
            "--include-optional",
            "--timeout-seconds",
            "30",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        timeout=180,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "adoption_onramp_replay.v1"
    assert payload["ok"] is True
    assert payload["boundary"]["uses_clean_public_copy"] is True
    collector_payload = payload["collector"]["payload"]
    assert collector_payload["schema"] == "adoption_onramp_collection.v1"
    assert collector_payload["summary"]["commands"] == 8
    assert collector_payload["summary"]["passed_commands"] == 8
    assert collector_payload["summary"]["observed_checks"] == 8
    assert collector_payload["summary"]["ready_for_human_adoption_review"] is True

    command_ids = {row["check_id"] for row in collector_payload["commands"]}
    assert "adapter_policy_preview" in command_ids
    assert "runtime_adapter_proof_pack" in command_ids
    assert Path(payload["collector_packet_path"]).exists()
