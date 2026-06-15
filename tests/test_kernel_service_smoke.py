from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_kernel_service_smoke_help_is_non_mutating() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/kernel_service_smoke.py", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Exercise the local kernel service" in result.stdout
    assert '"ok": true' not in result.stdout


def test_kernel_service_smoke_can_write_output_file(tmp_path: Path) -> None:
    output = tmp_path / "kernel-service-smoke.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/kernel_service_smoke.py",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    stdout_payload = json.loads(result.stdout)
    file_payload = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_payload["ok"] is True
    assert file_payload == stdout_payload
    assert stdout_payload["action_impact_counts"][
        "policy_promotion_governance_change_status"
    ] == "review_ready"
    assert stdout_payload["action_impact_counts"][
        "policy_promotion_governance_decision"
    ] == "approve"
    assert stdout_payload["action_impact_counts"][
        "policy_promotion_outcome_link"
    ] == "olink_smoke_policy_promotion"
    assert stdout_payload["action_impact_counts"][
        "policy_promotion_provenance_preserved"
    ] is True
