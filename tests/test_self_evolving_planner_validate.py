from __future__ import annotations

import json

from demos.self_evolving_org.planner_validate import main, validate_planner_file


def test_self_evolving_planner_validate_accepts_bounded_artifact(tmp_path, capsys):
    artifact = tmp_path / "planner.json"
    artifact.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "step_id": "bounded_handoff",
                        "title": "Bounded handoff",
                        "change_kind": "mandate_change",
                        "target_ref": "org/mandates/bounded_handoff.md",
                        "rationale": "Evidence handoff needs a durable note.",
                        "expected_behavior_change": "Future handoffs cite source refs.",
                        "risk_summary": "Narrows handoff criteria; no new authority.",
                        "rollback_plan": "Remove org/mandates/bounded_handoff.md.",
                        "applied_relpath": "org/mandates/bounded_handoff.md",
                        "applied_text": "# Bounded Handoff\n\nCite source refs before handoff.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = validate_planner_file(artifact)
    assert result["valid"] is True
    assert result["step_count"] == 1
    assert result["steps"][0]["step_id"] == "bounded_handoff"
    assert result["steps"][0]["target_ref"] == "org/mandates/bounded_handoff.md"

    assert main([str(artifact)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["valid"] is True


def test_self_evolving_planner_validate_rejects_malformed_json(tmp_path, capsys):
    artifact = tmp_path / "planner.json"
    artifact.write_text("not json\n", encoding="utf-8")

    result = validate_planner_file(artifact)
    assert result["valid"] is False
    assert "Expecting value" in result["error"]

    assert main([str(artifact)]) == 1
    printed = json.loads(capsys.readouterr().out)
    assert printed["valid"] is False


def test_self_evolving_planner_validate_rejects_unsafe_role_yaml(tmp_path):
    artifact = tmp_path / "planner.json"
    artifact.write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "step_id": "unsafe_tool_role",
                        "title": "Unsafe tool role",
                        "change_kind": "role_change",
                        "target_ref": "org/roles/unsafe_tool_role.yaml",
                        "rationale": "bad",
                        "expected_behavior_change": "bad",
                        "risk_summary": "bad",
                        "rollback_plan": "bad",
                        "applied_relpath": "org/roles/unsafe_tool_role.yaml",
                        "applied_text": (
                            "role_id: role.unsafe\n"
                            "authorized_paths:\n"
                            "  - org/reviews/**\n"
                            "tools:\n"
                            "  - bash\n"
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = validate_planner_file(artifact)
    assert result["valid"] is False
    assert "cannot declare external capability or secret fields" in result["error"]
