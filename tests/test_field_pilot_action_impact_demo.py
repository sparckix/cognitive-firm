from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from field_pilot_action_impact_demo import main, run_demo  # noqa: E402
from field_pilot_action_impact_compile import compile_action_impact, load_rows  # noqa: E402
from field_pilot_validate import validate_pilot  # noqa: E402


def test_field_pilot_action_impact_demo_builds_review_ready_packet(tmp_path: Path):
    payload = run_demo(tmp_path)

    assert payload["summary"]["verdict"] == "passed"
    assert payload["pilot_validation"]["ok"] is True
    assert payload["pilot_validation"]["action_impact"]["n_total"] == 34
    assert payload["candidate_proposal"]["status"] == "candidate"
    assert payload["candidate_proposal"]["contexts"] == 1
    assert payload["policy_evaluation"]["status"] == "promotable"
    assert payload["policy_evaluation"]["promotion_allowed"] is True
    assert payload["promotion_packet"]["status"] == "review_ready"
    assert payload["promotion_packet"]["review_blockers"] == []


def test_field_pilot_validator_can_require_action_impact(tmp_path: Path):
    tmp_path.mkdir(exist_ok=True)
    result = validate_pilot(tmp_path, require_action_impact=True, min_action_impact_records=1)

    assert result["ok"] is False
    assert any("action-impact summary required" in error for error in result["errors"])


def test_field_pilot_action_impact_demo_cli_compact(capsys):
    assert main([]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["demo"] == "field_pilot_action_impact"
    assert payload["no_external_calls"] is True
    assert payload["summary"]["verdict"] == "passed"
    assert "log_paths" not in payload


def test_field_pilot_action_impact_demo_cli_full_json_keeps_logs(tmp_path: Path, capsys):
    assert main(["--workdir", str(tmp_path), "--full-json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["verdict"] == "passed"
    assert "log_paths" in payload
    for path in payload["log_paths"].values():
        assert Path(path).exists()


def test_field_pilot_action_impact_compile_csv_rows(tmp_path: Path):
    run_demo(tmp_path)
    rows = tmp_path / "pilot-rows.csv"
    rows.write_text(
        "\n".join(
            [
                "action_id,action_ref,actor,objective_metric,status,context_features,action_arm,reward,requires_human_review,negative_externality_tags",
                'row-1,field-pilot://row-1,role.router,quality,measured,"{""decision_class"": ""customer_facing""}",specialist_review,0.9,false,',
                'row-2,field-pilot://row-2,role.router,quality,measured,"{""decision_class"": ""customer_facing""}",general_review,0.6,false,',
                'row-3,field-pilot://row-3,role.router,throughput,measured,"{""decision_class"": ""low_risk""}",auto_approve,0.95,true,customer_confusion',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = compile_action_impact(tmp_path, rows, validate=True, min_records=3)

    assert payload["verdict"] == "passed"
    assert payload["summary"]["n_total"] == 3
    assert payload["summary"]["n_measured"] == 3
    assert payload["summary"]["n_review_required"] == 1
    assert payload["summary"]["n_local_with_negative_externalities"] == 1
    assert payload["validation"]["ok"] is True
    assert (tmp_path / "action-impact-summary.json").exists()


def test_field_pilot_action_impact_compile_jsonl_rows(tmp_path: Path):
    rows = tmp_path / "rows.jsonl"
    rows.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "action_id": "row-1",
                        "action_ref": "field-pilot://row-1",
                        "actor": "role.router",
                        "objective_metric": "quality",
                        "status": "measured",
                        "context_features": {"decision_class": "customer_facing"},
                        "action_arm": "specialist_review",
                        "reward": 0.9,
                    }
                ),
                json.dumps(
                    {
                        "action_id": "row-2",
                        "action_ref": "field-pilot://row-2",
                        "actor": "role.router",
                        "objective_metric": "quality",
                        "status": "measured",
                        "context_features": {"decision_class": "customer_facing"},
                        "action_arm": "general_review",
                        "reward": 0.6,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_rows(rows)

    assert len(loaded) == 2
    assert loaded[0]["action_id"] == "row-1"
