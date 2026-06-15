from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.state_surface_inventory import (  # noqa: E402
    CAPABILITY_GROUPS,
    capability_inventory,
    execution_boundary_for_surface,
    list_state_surfaces,
    render_capability_inventory_markdown,
    unregistered_stateful_modules,
)
from cognitive_firm.orchestration.connector_families import CONNECTOR_FAMILIES  # noqa: E402


def test_state_surface_inventory_covers_core_primitives():
    surfaces = list_state_surfaces()
    primitives = {surface.primitive for surface in surfaces}

    expected = {
        "transition_log",
        "run_checkpoints",
        "state_backends",
        "kernel_events",
        "resource_envelope",
        "policy_decisions",
        "otel_export",
        "migrations",
        "audit_integrity",
        "governed_run_attestation",
        "actor_identity",
        "actor_membership",
        "authority_domains",
        "leases",
        "accountability_cases",
        "evidence_gaps",
        "human_work",
        "forecast_market",
        "action_impact",
        "action_attestation",
        "runtime_adapters",
        "notifications",
        "mcp_outbox",
        "inbound_events",
        "org_surface",
        "intelligence_sources",
        "strategy_office",
        "governance_changes",
        "learning_transition_compiler",
        "learning_events",
        "learning_event_encounters",
        "accountability",
        "operating_units",
        "work_items",
        "operating_unit_surface",
    }
    assert expected.issubset(primitives)


def test_state_surface_inventory_keeps_connector_families_distinct():
    allowed_families = set(CONNECTOR_FAMILIES)
    surfaces = list_state_surfaces()

    assert all(surface.connector_family in allowed_families for surface in surfaces)
    assert next(surface for surface in surfaces if surface.primitive == "mcp_outbox").connector_family == "enterprise_system"
    assert next(surface for surface in surfaces if surface.primitive == "inbound_events").connector_family == "inbound_event"
    assert next(surface for surface in surfaces if surface.primitive == "runtime_adapters").connector_family == "runtime"
    assert next(surface for surface in surfaces if surface.primitive == "forecast_market").tenant_owned is True
    assert all(surface.conformance_tests for surface in surfaces)


def test_state_surface_inventory_classifies_source_of_truth_level():
    allowed_classes = {"canonical_state", "read_model", "projection", "telemetry", "tenant_owned_ledger"}
    surfaces = list_state_surfaces()

    assert all(surface.state_class in allowed_classes for surface in surfaces)
    assert next(surface for surface in surfaces if surface.primitive == "human_work").state_class == "canonical_state"
    assert next(surface for surface in surfaces if surface.primitive == "org_surface").state_class == "read_model"
    assert next(surface for surface in surfaces if surface.primitive == "runtime_adapters").state_class == "projection"
    assert next(surface for surface in surfaces if surface.primitive == "learning_event_encounters").state_class == "telemetry"
    assert next(surface for surface in surfaces if surface.primitive == "forecast_market").state_class == "tenant_owned_ledger"


def test_state_surface_inventory_classifies_execution_boundary():
    surfaces = {surface.primitive: surface for surface in list_state_surfaces()}

    assert execution_boundary_for_surface(surfaces["work_items"]) == "work substrate"
    assert execution_boundary_for_surface(surfaces["phase_execution"]) == "first-party execution helper"
    assert execution_boundary_for_surface(surfaces["business_function_bandit"]) == "first-party execution helper"
    assert execution_boundary_for_surface(surfaces["runtime_adapters"]) == "runtime import/projection"
    assert execution_boundary_for_surface(surfaces["multi_agent_trace_attribution"]) == "runtime import/projection"
    assert execution_boundary_for_surface(surfaces["action_impact"]) == "tenant-owned input"
    assert execution_boundary_for_surface(surfaces["action_attestation"]) == "audit/proof"
    assert execution_boundary_for_surface(surfaces["governance_changes"]) == "kernel governance/state"


def test_state_surface_inventory_registers_all_default_log_modules():
    assert unregistered_stateful_modules(ROOT / "src") == []


def test_capability_groups_reference_registered_surfaces_once():
    primitives = {surface.primitive for surface in list_state_surfaces()}
    grouped = [
        primitive
        for _group, primitives_in_group in CAPABILITY_GROUPS
        for primitive in primitives_in_group
    ]

    assert set(grouped) == primitives
    assert len(grouped) == len(set(grouped))


def test_capability_inventory_renders_markdown_from_registered_surfaces():
    inventory = capability_inventory()
    rendered = render_capability_inventory_markdown()

    assert inventory
    assert "# Capability Map" in rendered
    assert "## Authority and access" in rendered
    assert "| Surface | Boundary | Class | Kind | Writer | Tests |" in rendered
    assert "`run_checkpoints`" in rendered
    assert "runtime import/projection" in rendered
    assert "first-party execution helper" in rendered
    assert "tests/test_run_checkpoints.py" in rendered


def test_checked_in_capability_map_matches_inventory_renderer():
    rendered = render_capability_inventory_markdown()
    checked_in = (ROOT / "docs" / "capability-map.md").read_text()

    assert checked_in == rendered
