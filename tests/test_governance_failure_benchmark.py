from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from governance_failure_benchmark import main, run_benchmark  # noqa: E402


def test_governance_failure_benchmark_passes_all_fixtures():
    payload = run_benchmark()

    assert payload["summary"] == {
        "passed": 10,
        "total": 10,
        "verdict": "passed",
    }
    fixture_ids = {row["fixture_id"] for row in payload["fixtures"]}
    assert fixture_ids == {
        "unauthorized_write",
        "failed_attestation",
        "missing_human_receipt",
        "unresolved_outcome",
        "open_accountability_case",
        "formal_refutation",
        "missing_referenced_lease",
        "missing_governance_approval",
        "local_reward_externality_downgrade",
        "weakly_evidenced_governance_change",
    }
    assert all(row["passed"] for row in payload["fixtures"])


def test_governance_failure_benchmark_cli_compact(capsys):
    assert main([]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["verdict"] == "passed"
    assert "details" not in payload["fixtures"][0]
    assert {row["kernel_surface"] for row in payload["fixtures"]} == {
        "task_authorization.authorize_dispatch",
        "action_attestation + governed-run bundle",
        "human_work + governed-run bundle",
        "outcome_links + governed-run bundle",
        "accountability_cases + governed-run bundle",
        "formal_verification + governed-run bundle",
        "lease evidence + governed-run bundle",
        "governance approval evidence + governed-run bundle",
        "action-impact offline evaluation + policy promotion packet",
        "governance_changes evidence sufficiency",
    }


def test_governance_failure_benchmark_cli_full_json(capsys):
    assert main(["--full-json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["verdict"] == "passed"
    assert all("details" in row for row in payload["fixtures"])
    unauthorized = next(
        row for row in payload["fixtures"] if row["fixture_id"] == "unauthorized_write"
    )
    assert unauthorized["details"]["allowed"] is False
    assert unauthorized["details"]["terminal"] is True
    downgrade = next(
        row for row in payload["fixtures"] if row["fixture_id"] == "local_reward_externality_downgrade"
    )
    assert downgrade["details"]["report"]["delta_mean_reward"] > 0
    assert downgrade["details"]["packet"]["status"] == "blocked"
    weak_proposal = next(
        row for row in payload["fixtures"]
        if row["fixture_id"] == "weakly_evidenced_governance_change"
    )
    assert weak_proposal["details"]["proposal"]["status"] == "blocked"
    assert weak_proposal["details"]["proposal"]["evidence_sufficiency"]["status"] == "fail"
    assert (
        "source_refs"
        in weak_proposal["details"]["proposal"]["evidence_sufficiency"]["missing"]
    )
