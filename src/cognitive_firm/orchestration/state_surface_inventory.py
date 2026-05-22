"""Inventory of cognitive-firm state surfaces and connector boundaries."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from cognitive_firm.orchestration.connector_families import ConnectorFamily


StateSurfaceKind = Literal["event_stream", "artifact", "jsonl", "summary_read_model", "projection"]
StateSurfaceClass = Literal["canonical_state", "read_model", "projection", "telemetry", "tenant_owned_ledger"]


@dataclass(frozen=True)
class StateSurface:
    primitive: str
    module: str
    surface_kind: StateSurfaceKind | str
    connector_family: ConnectorFamily | str
    state_class: StateSurfaceClass | str
    default_location: str
    writer: str
    reader: str
    tenant_owned: bool = False
    notes: str = ""
    conformance_tests: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


STATE_SURFACES: tuple[StateSurface, ...] = (
    StateSurface(
        primitive="transition_log",
        module="cognitive_firm.orchestration.transition_log",
        surface_kind="event_stream",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="cognitive_firm_workspace/transitions.jsonl",
        writer="append_transition",
        reader="run checkpoints, artifact dependencies, MCP relay, org surface",
        conformance_tests=["tests/test_run_checkpoints.py", "tests/test_mcp_outbox_relay.py"],
    ),
    StateSurface(
        primitive="state_backends",
        module="cognitive_firm.orchestration.state_backends",
        surface_kind="event_stream",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="caller-selected filesystem root or SQLite path",
        writer="FilesystemStateBackend.append_event / SqliteEventSource.append_event",
        reader="EventSource.read_events",
        conformance_tests=["tests/test_state_backends.py"],
    ),
    StateSurface(
        primitive="kernel_events",
        module="cognitive_firm.orchestration.kernel_events",
        surface_kind="event_stream",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="cognitive_firm_workspace/transitions.jsonl as embedded kernel_event",
        writer="record_kernel_event / append_kernel_event",
        reader="list_kernel_events, future projection registry, conformance fixtures",
        notes="Canonical event envelope embedded in the transition stream; explicit raw JSONL paths are fixture/migration adapters only.",
        conformance_tests=["tests/test_kernel_events.py"],
    ),
    StateSurface(
        primitive="resource_envelope",
        module="cognitive_firm.orchestration.resource_envelope",
        surface_kind="projection",
        connector_family="state_backend",
        state_class="projection",
        default_location="computed resource shape",
        writer="none",
        reader="conformance fixtures, docs, migrations, external adapters",
        notes="Compatibility envelope: api_version, kind, metadata, spec, status, links.",
        conformance_tests=["tests/test_resource_envelope.py"],
    ),
    StateSurface(
        primitive="policy_decisions",
        module="cognitive_firm.orchestration.policy_decisions",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/policy/policy_decisions.jsonl",
        writer="evaluate_policy / append_policy_decision",
        reader="list_policy_decisions, conformance fixtures, audit review",
        notes="Auditable bounded policy decisions; does not replace mandates or role authorization.",
        conformance_tests=["tests/test_policy_decisions.py"],
    ),
    StateSurface(
        primitive="otel_export",
        module="cognitive_firm.orchestration.otel_export",
        surface_kind="projection",
        connector_family="runtime",
        state_class="projection",
        default_location="caller-selected OpenTelemetry projection artifact",
        writer="write_otel_projection",
        reader="deployment observability adapters",
        notes="Projection only. Kernel events and transition rows remain canonical.",
        conformance_tests=["tests/test_otel_export.py"],
    ),
    StateSurface(
        primitive="migrations",
        module="cognitive_firm.orchestration.migrations",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/migrations/migrations.jsonl",
        writer="record_migration",
        reader="list_migrations, release checks, conformance fixtures",
        notes="Dry-run-first records for schema/state migrations.",
        conformance_tests=["tests/test_migrations.py"],
    ),
    StateSurface(
        primitive="audit_integrity",
        module="cognitive_firm.orchestration.audit_integrity",
        surface_kind="artifact",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/audit/*.manifest.json",
        writer="create_audit_manifest_for_file",
        reader="verify_audit_manifest_for_file",
        notes="Tamper-evident chained manifests over JSONL kernel logs; lean T2 audit MVP.",
        conformance_tests=["tests/test_audit_integrity.py"],
    ),
    StateSurface(
        primitive="actor_identity",
        module="cognitive_firm.orchestration.actor_identity",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/identity/actor_identities.jsonl",
        writer="register_actor_identity",
        reader="actor_context_from_payload, kernel service, audit/accountability surfaces",
        notes="First-party organizational actor context; external IdPs authenticate subjects.",
        conformance_tests=["tests/test_actor_identity.py", "tests/test_kernel_service.py"],
    ),
    StateSurface(
        primitive="actor_membership",
        module="cognitive_firm.orchestration.actor_membership",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/identity/actor_memberships.jsonl",
        writer="grant_actor_membership / revoke_actor_membership",
        reader="actor_context_from_payload, kernel service, audit/accountability surfaces",
        notes="Scoped role membership for multi-principal T1/T2 deployments.",
        conformance_tests=["tests/test_actor_membership.py", "tests/test_kernel_service.py"],
    ),
    StateSurface(
        primitive="leases",
        module="cognitive_firm.orchestration.leases",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/leases/leases.jsonl",
        writer="acquire_lease / release_lease",
        reader="verify_lease, kernel service mutation boundary",
        notes="Time-bounded resource mutation claims with fencing tokens.",
        conformance_tests=["tests/test_leases.py", "tests/test_kernel_service.py"],
    ),
    StateSurface(
        primitive="accountability_cases",
        module="cognitive_firm.orchestration.accountability_cases",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/accountability/accountability_cases.jsonl",
        writer="create_accountability_case / update_accountability_case_status",
        reader="list_accountability_cases, review queues, future org surface",
        notes="Write-side records for authority, residual-risk acceptance, recourse, and accountable closure.",
        conformance_tests=["tests/test_accountability_cases.py"],
    ),
    StateSurface(
        primitive="evidence_gaps",
        module="cognitive_firm.orchestration.evidence_gaps",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/evidence_gaps/evidence_gaps.jsonl",
        writer="create_evidence_gap / update_evidence_gap_status",
        reader="list_evidence_gaps, work discovery, org surface",
        conformance_tests=["tests/test_evidence_gaps.py", "tests/test_org_surface.py"],
    ),
    StateSurface(
        primitive="human_work",
        module="cognitive_firm.orchestration.human_work",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/human_work/human_work.jsonl",
        writer="create_human_work_session / create_agent_requested_human_work_session / update_human_work_state",
        reader=(
            "list_human_work_sessions, A2H waiting/follow-up/pressure, "
            "work discovery, org surface"
        ),
        conformance_tests=["tests/test_human_work.py", "tests/test_org_surface.py"],
    ),
    StateSurface(
        primitive="forecast_market",
        module="cognitive_firm.orchestration.forecast_market",
        surface_kind="summary_read_model",
        connector_family="tenant_adapter",
        state_class="tenant_owned_ledger",
        default_location="org/forecast_market/global_health.json",
        writer="tenant forecast market",
        reader="market_summary_from_optional_path, org surface, strategy office",
        tenant_owned=True,
        notes="Kernel consumes the read model; tenants own contracts, scoring, and calibration.",
        conformance_tests=["tests/test_forecast_market_interface.py"],
    ),
    StateSurface(
        primitive="action_impact",
        module="cognitive_firm.orchestration.action_impact",
        surface_kind="summary_read_model",
        connector_family="tenant_adapter",
        state_class="tenant_owned_ledger",
        default_location="org/action_impact/action_impact_summary.json",
        writer="tenant action-impact ledger",
        reader="summary_from_optional_path, org surface, strategy office, accountability",
        tenant_owned=True,
        notes="Kernel consumes the read model; tenants own metric definitions and optimizer policy.",
        conformance_tests=["tests/test_action_impact_interface.py"],
    ),
    StateSurface(
        primitive="action_attestation",
        module="cognitive_firm.orchestration.action_attestation",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/attestations/action_attestations.jsonl",
        writer="create_action_attestation",
        reader="list_action_attestations, release/review queues, future signed-audit surfaces",
        notes="Machine-side provenance counterpart to human work receipts.",
        conformance_tests=["tests/test_action_attestation.py"],
    ),
    StateSurface(
        primitive="runtime_adapters",
        module="cognitive_firm.orchestration.runtime_adapters",
        surface_kind="projection",
        connector_family="runtime",
        state_class="projection",
        default_location="transition log as run.* events",
        writer="record_runtime_event",
        reader="run checkpoint projection and org surface",
        conformance_tests=["tests/test_runtime_adapters.py", "tests/test_run_checkpoints.py"],
    ),
    StateSurface(
        primitive="notifications",
        module="cognitive_firm.notifications.channels",
        surface_kind="projection",
        connector_family="notification",
        state_class="projection",
        default_location="provider adapter",
        writer="send_notification / push_notification",
        reader="provider-specific delivery system",
        notes="Notification intents are not durable state unless caller records a transition.",
        conformance_tests=["tests/test_notification_channels.py"],
    ),
    StateSurface(
        primitive="mcp_outbox",
        module="cognitive_firm.role_extensions.mcp_bridge",
        surface_kind="event_stream",
        connector_family="enterprise_system",
        state_class="canonical_state",
        default_location="transition log as mcp_call_requested/follow-up events",
        writer="append_transition and outbox relay",
        reader="MCP relay and deterministic projections",
        notes="Enterprise-system connector; not a state backend.",
        conformance_tests=["tests/test_mcp_outbox_relay.py", "tests/test_mcp_capabilities.py"],
    ),
    StateSurface(
        primitive="inbound_events",
        module="cognitive_firm.orchestration.inbound_events",
        surface_kind="jsonl",
        connector_family="inbound_event",
        state_class="canonical_state",
        default_location="org/inbound_events/inbound_events.jsonl and quarantine.jsonl",
        writer="ingest_inbound_event",
        reader="list_inbound_events, kernel event projections, tenant review queues",
        notes="Inbound external observations; accepted only after signature/idempotency/projection checks.",
        conformance_tests=["tests/test_inbound_events.py"],
    ),
    StateSurface(
        primitive="org_surface",
        module="cognitive_firm.orchestration.org_surface",
        surface_kind="projection",
        connector_family="state_backend",
        state_class="read_model",
        default_location="computed from primitive read models",
        writer="none",
        reader="humans, role offices, Orbit, learning compiler, accountability summary",
        notes="Read model only; mutate state through the underlying primitives.",
        conformance_tests=["tests/test_org_surface.py"],
    ),
    StateSurface(
        primitive="intelligence_sources",
        module="cognitive_firm.orchestration.intelligence_sources",
        surface_kind="projection",
        connector_family="state_backend",
        state_class="read_model",
        default_location="computed from state-surface inventory and organization-surface inputs",
        writer="none",
        reader="org surface, learning transition compiler, operator briefs",
        notes="Coverage and repair projection for kernel-facing intelligence sources.",
        conformance_tests=["tests/test_intelligence_sources.py", "tests/test_org_surface.py"],
    ),
    StateSurface(
        primitive="strategy_office",
        module="cognitive_firm.orchestration.strategy_office",
        surface_kind="projection",
        connector_family="state_backend",
        state_class="read_model",
        default_location="computed from org-surface inputs",
        writer="none",
        reader="org surface, learning transition compiler, accountability summary",
        notes="Observer-only findings.",
        conformance_tests=["tests/test_strategy_office.py"],
    ),
    StateSurface(
        primitive="governance_changes",
        module="cognitive_firm.orchestration.governance_changes",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/governance_changes/governance_changes.jsonl",
        writer="propose_governance_change",
        reader="list_governance_changes, org surface, tenant review queues",
        notes="Governed self-modification proposals; records invariant checks but does not apply changes.",
        conformance_tests=["tests/test_governance_changes.py", "tests/test_org_surface.py"],
    ),
    StateSurface(
        primitive="learning_transition_compiler",
        module="cognitive_firm.orchestration.learning_transition_compiler",
        surface_kind="projection",
        connector_family="state_backend",
        state_class="read_model",
        default_location="computed from organization surface",
        writer="none",
        reader="tenant review queues or role offices",
        notes="Candidates only; does not mutate governance state.",
        conformance_tests=["tests/test_learning_transition_compiler.py"],
    ),
    StateSurface(
        primitive="learning_events",
        module="cognitive_firm.orchestration.learning_events",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/learning_events/learning_events.jsonl",
        writer="create_learning_event / learning_event_from_candidate",
        reader="list_learning_events, org surface, tenant review queues",
        notes="Approved durable behavior-change events; does not apply the referenced change.",
        conformance_tests=["tests/test_learning_events.py"],
    ),
    StateSurface(
        primitive="learning_event_encounters",
        module="cognitive_firm.orchestration.learning_events",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="telemetry",
        default_location="org/learning_events/learning_encounters.jsonl",
        writer="record_learning_event_encounter",
        reader="list_learning_event_encounters, work discovery, learning replay audits",
        notes="Optional idempotent telemetry for whether active learning was encountered, applied, ignored, or deferred by later work.",
        conformance_tests=["tests/test_learning_events.py", "tests/test_work_discovery_learning_carriers.py"],
    ),
    StateSurface(
        primitive="accountability",
        module="cognitive_firm.orchestration.accountability",
        surface_kind="projection",
        connector_family="state_backend",
        state_class="read_model",
        default_location="computed from organization surface",
        writer="none",
        reader="humans, role offices, review queues",
        notes="Read model joining owners, projects, externalities, due dates, and review state.",
        conformance_tests=["tests/test_accountability.py"],
    ),
    StateSurface(
        primitive="operating_units",
        module="cognitive_firm.orchestration.operating_units",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/operating_units/operating_units.jsonl",
        writer="define_operating_unit / set_operating_unit_status",
        reader="list_operating_units, work items, operating-unit dashboard",
        notes="Typed contracts for recurring production lanes; tenants own the work kinds and exit meanings.",
        conformance_tests=["tests/test_operating_units.py"],
    ),
    StateSurface(
        primitive="work_items",
        module="cognitive_firm.orchestration.work_items",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/work_items/work_items.jsonl",
        writer="enqueue_work_item / claim_work_item / complete_work_item / fail_work_item",
        reader="list_work_items, operating-unit dashboard, kernel event stream",
        notes="Durable production queue with lease-fenced claims, retries, dead letters, and bounded exits.",
        conformance_tests=["tests/test_work_items.py"],
    ),
    StateSurface(
        primitive="operating_unit_surface",
        module="cognitive_firm.orchestration.operating_unit_surface",
        surface_kind="projection",
        connector_family="state_backend",
        state_class="read_model",
        default_location="computed from operating units and work items",
        writer="none",
        reader="humans, role offices, Orbit, operator briefs",
        notes="Production-health read model: backlog, claimed, p95, throughput, blockers per unit.",
        conformance_tests=["tests/test_operating_unit_surface.py"],
    ),
    StateSurface(
        primitive="outcome_links",
        module="cognitive_firm.orchestration.outcome_links",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/outcome_links/outcome_links.jsonl",
        writer="create_outcome_link / record_metric_snapshot / record_verdict / void_outcome_link",
        reader="summarize_outcome_links, routine reviews, org surface",
        notes="Ties an approved change to a tenant-measured outcome and verdict; kernel owns the record and lifecycle, tenant owns the metric.",
        conformance_tests=["tests/test_outcome_links.py"],
    ),
    StateSurface(
        primitive="routine_reviews",
        module="cognitive_firm.orchestration.routine_reviews",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/routine_reviews/routine_reviews.jsonl",
        writer="schedule_routine_review / start_routine_review / record_review_outcome / retire_routine",
        reader="list_due_reviews, summarize_routine_reviews, review queues, org surface",
        notes="Review-and-retirement lifecycle over durable routines; the overdue surface is the organizational-forgetting pressure.",
        conformance_tests=["tests/test_routine_reviews.py"],
    ),
    StateSurface(
        primitive="resource_allocation",
        module="cognitive_firm.orchestration.resource_allocation",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/resource_allocation/allocation_decisions.jsonl",
        writer="record_allocation_decision / apply_allocation_decision / revert_allocation_decision",
        reader="current_allocation, allocation_summary, operating-unit dashboard, audit review",
        notes="Governed capital/capacity allocation decisions across operating units; kernel records decisions, tenant owns the optimizer.",
        conformance_tests=["tests/test_resource_allocation.py"],
    ),
    StateSurface(
        primitive="residual_right_assignments",
        module="cognitive_firm.orchestration.decision_rights",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/decision_rights/residual_right_assignments.jsonl",
        writer="assign_residual_right",
        reader="get_residual_right_holder, summarize_decision_rights, governance review",
        notes="Names the default decider (residual control right) per scope when a mandate is silent; idempotent on scope with supersede.",
        conformance_tests=["tests/test_decision_rights.py"],
    ),
    StateSurface(
        primitive="residual_decisions",
        module="cognitive_firm.orchestration.decision_rights",
        surface_kind="jsonl",
        connector_family="state_backend",
        state_class="canonical_state",
        default_location="org/decision_rights/residual_decisions.jsonl",
        writer="record_residual_decision / review_residual_decision",
        reader="list_residual_decisions, summarize_decision_rights, governance review",
        notes="Decisions taken where no mandate clause applied; unauthorized flag fails open; promote_to_mandate_clause bridges back to a complete contract.",
        conformance_tests=["tests/test_decision_rights.py"],
    ),
)


def registered_state_modules() -> set[str]:
    return {surface.module for surface in STATE_SURFACES}


def discover_stateful_modules(src_root: Path) -> set[str]:
    """Discover modules with default log constants under orchestration.

    This is a guardrail, not a perfect static analyzer. It catches the common
    failure mode: adding a new JSONL-backed primitive without registering its
    surface.
    """
    modules: set[str] = set()
    orchestration_root = src_root / "cognitive_firm" / "orchestration"
    for path in orchestration_root.glob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                if name.startswith("DEFAULT_") and name.endswith(("LOG", "LOG_PATH")):
                    modules.add(f"cognitive_firm.orchestration.{path.stem}")
    return modules


def unregistered_stateful_modules(src_root: Path) -> list[str]:
    return sorted(discover_stateful_modules(src_root) - registered_state_modules())


def list_state_surfaces() -> list[StateSurface]:
    return list(STATE_SURFACES)


def state_surface_inventory() -> list[dict[str, object]]:
    return [surface.as_dict() for surface in STATE_SURFACES]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render cognitive-firm state surface inventory.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps(state_surface_inventory(), indent=2, sort_keys=True))
    else:
        for surface in STATE_SURFACES:
            print(
                f"- {surface.primitive}: {surface.surface_kind} "
                f"via {surface.connector_family} ({surface.default_location})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
