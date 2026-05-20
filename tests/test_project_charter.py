from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.project_charter import (  # noqa: E402
    load_project_charter,
    parse_project_charter,
    validate_project_charter,
)


VALID_CHARTER = """# Example Project

## Core Question

Can this workflow preserve approval boundaries while reducing review latency?

## Out Of Scope

Changing the approval policy itself.

## End States

- Ship if latency falls and approval boundary remains intact.
- Kill if the approval boundary cannot be represented as an anchor.

## Forecast Type

directional_forecast

## Inheritance

- Prior onboarding checklist.

## Anchor Proxies

- anchor: approval_boundary_preserved
  type: checklist_id
  predicate: approval remains required above threshold

- anchor: export_schema_stable
  type: schema_predicate
  predicate: required retention fields remain present
"""


def test_parse_valid_project_charter():
    charter = parse_project_charter(VALID_CHARTER)
    assert validate_project_charter(charter) == []
    assert charter.forecast_type == "directional_forecast"
    assert [anchor.name for anchor in charter.anchors] == [
        "approval_boundary_preserved",
        "export_schema_stable",
    ]
    assert charter.anchors[0].fields["type"] == "checklist_id"


def test_missing_required_section_fails_validation():
    charter = parse_project_charter("""## Core Question\n\nWhat should happen?\n""")
    errors = validate_project_charter(charter)
    assert "missing required section: out of scope" in errors
    assert "missing required section: anchor proxies" in errors


def test_invalid_forecast_type_fails_validation():
    charter = parse_project_charter(
        VALID_CHARTER.replace("directional_forecast", "market-oracle")
    )
    errors = validate_project_charter(charter)
    assert any("invalid forecast type" in error for error in errors)


def test_load_project_charter_from_path(tmp_path: Path):
    path = tmp_path / "project_charter.md"
    path.write_text(VALID_CHARTER, encoding="utf-8")
    charter = load_project_charter(path)
    assert charter.path == path
    assert charter.is_valid is True


def test_anchor_section_without_anchor_entries_fails_validation():
    charter = parse_project_charter(
        VALID_CHARTER.replace("- anchor: approval_boundary_preserved", "- approval boundary")
        .replace("- anchor: export_schema_stable", "- export schema")
    )
    errors = validate_project_charter(charter)
    assert "anchor proxies section is present but no `anchor:` entries were parsed" in errors
