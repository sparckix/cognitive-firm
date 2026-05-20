from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.resource_envelope import make_resource, validate_resource  # noqa: E402


def test_resource_envelope_has_stable_top_level_shape():
    resource = make_resource(
        kind="LearningEvent",
        name="learn_1",
        tenant_id="tenant-a",
        project_id="project-a",
        spec={"future_application_cue": "same failure repeats"},
        status={"state": "active"},
        links=[{"rel": "source", "href": "forecast/c1"}],
        stability="beta",
    )
    payload = resource.as_dict()

    assert payload["api_version"] == "cognitive-firm/v1alpha1"
    assert payload["kind"] == "LearningEvent"
    assert payload["stability"] == "beta"
    assert payload["metadata"]["name"] == "learn_1"
    assert payload["spec"]["future_application_cue"] == "same failure repeats"
    assert validate_resource(payload) == []


def test_resource_validation_reports_missing_contract_fields():
    errors = validate_resource({"kind": "Run", "metadata": {}, "spec": [], "stability": "draft"})

    assert "api_version is required" in errors
    assert "metadata.name is required" in errors
    assert "spec must be an object" in errors
    assert "stability must be alpha, beta, or stable" in errors
