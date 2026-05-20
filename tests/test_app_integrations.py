from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.app_integrations import (  # noqa: E402
    classify_integration,
    list_integration_boundaries,
)
from cognitive_firm.orchestration.connector_families import CONNECTOR_FAMILIES  # noqa: E402


def test_app_integration_registry_covers_connector_families():
    boundaries = list_integration_boundaries()
    families = {boundary.family for boundary in boundaries}

    assert families == set(CONNECTOR_FAMILIES)
    assert all(boundary.conformance_tests for boundary in boundaries)


def test_mcp_is_enterprise_system_not_universal_app_protocol():
    boundary = classify_integration("mcp")

    assert boundary is not None
    assert boundary.family == "enterprise_system"
    assert "MCP outbox relay" in boundary.primary_interface


def test_app_surface_and_identity_provider_have_distinct_boundaries():
    orbit = classify_integration("Orbit")
    oidc = classify_integration("OIDC")

    assert orbit is not None
    assert orbit.family == "app_surface"
    assert "kernel_service" in orbit.primary_interface
    assert oidc is not None
    assert oidc.family == "identity_provider"
    assert "kernel for actor authority" in oidc.source_of_truth
    assert "Provisioning" in oidc.notes


def test_webhook_classifies_as_inbound_event_not_mcp():
    boundary = classify_integration("webhook")

    assert boundary is not None
    assert boundary.family == "inbound_event"
    assert "signature" in boundary.primary_interface
