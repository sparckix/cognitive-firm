"""Connector-family registry for app and system integrations.

This module does not implement transport. It classifies integration boundaries
so adopters do not collapse app surfaces, MCP tools, runtimes, state backends,
identity providers, and notification providers into one generic connector.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field

from cognitive_firm.orchestration.connector_families import ConnectorFamily


@dataclass(frozen=True)
class IntegrationBoundary:
    family: ConnectorFamily
    purpose: str
    primary_interface: str
    source_of_truth: str
    authority_owner: str
    examples: list[str] = field(default_factory=list)
    conformance_tests: list[str] = field(default_factory=list)
    notes: str = ""

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


INTEGRATION_BOUNDARIES: tuple[IntegrationBoundary, ...] = (
    IntegrationBoundary(
        family="app_surface",
        purpose="Let UI, local tools, and operator consoles submit typed kernel requests.",
        primary_interface="cognitive_firm.kernel_service",
        source_of_truth="kernel state written by underlying primitives",
        authority_owner="kernel mandates, actor identity, leases, and primitive validators",
        examples=["Orbit", "CLI", "future Slack/Teams/web app"],
        conformance_tests=["tests/test_kernel_service.py"],
    ),
    IntegrationBoundary(
        family="enterprise_system",
        purpose="Reach external systems whose state remains outside the kernel.",
        primary_interface="MCP outbox relay with deterministic projections",
        source_of_truth="external system plus kernel transition log of attempted action/projection",
        authority_owner="kernel MCP capability policy and role mandate",
        examples=["Linear", "Salesforce", "ERP", "CRM", "ticketing"],
        conformance_tests=[
            "tests/test_mcp_outbox_relay.py",
            "tests/test_mcp_linear_server.py",
            "tests/test_mcp_capabilities.py",
        ],
    ),
    IntegrationBoundary(
        family="runtime",
        purpose="Project external graph, crew, chat, or agent-runtime lifecycle into the org surface.",
        primary_interface="runtime adapter -> run checkpoint events",
        source_of_truth="runtime owns execution; kernel owns organizational projection",
        authority_owner="kernel role mandate and run-checkpoint primitive",
        examples=["LangGraph", "AutoGen", "CrewAI", "OpenAI Agents SDK", "custom runtime"],
        conformance_tests=["tests/test_runtime_adapters.py", "tests/test_runtime_adapter_conformance.py"],
    ),
    IntegrationBoundary(
        family="state_backend",
        purpose="Store kernel events and artifacts without changing protocol semantics.",
        primary_interface="SourceConnector / EventSource",
        source_of_truth="selected kernel state backend",
        authority_owner="kernel primitive writer",
        examples=["filesystem", "SQLite", "future Postgres/event store/object store"],
        conformance_tests=["tests/test_state_backends.py", "tests/test_state_surface_inventory.py"],
    ),
    IntegrationBoundary(
        family="inbound_event",
        purpose="Ingest external webhooks or event streams as quarantinable observations.",
        primary_interface="inbound event projection with signature and idempotency checks",
        source_of_truth="external event producer plus kernel accepted/quarantine logs",
        authority_owner="kernel projection registry and tenant webhook policy",
        examples=["webhook", "CloudEvents", "AsyncAPI event stream"],
        conformance_tests=["tests/test_inbound_events.py"],
    ),
    IntegrationBoundary(
        family="notification",
        purpose="Deliver human attention intents without owning durable organization state.",
        primary_interface="notification-channel adapter",
        source_of_truth="provider delivery system plus any kernel event recorded by caller",
        authority_owner="kernel caller and notification policy",
        examples=["Telegram", "null/local", "future Slack/Teams pager"],
        conformance_tests=["tests/test_notification_channels.py"],
    ),
    IntegrationBoundary(
        family="identity_provider",
        purpose="Authenticate service requests and return subject facts.",
        primary_interface="IdentityProviderAdapter",
        source_of_truth="external IdP for authentication; kernel for actor authority",
        authority_owner="external IdP authenticates, kernel authorizes",
        examples=["local bearer token", "OIDC", "SAML", "mTLS", "API gateway"],
        conformance_tests=[
            "tests/test_identity_providers.py",
            "tests/test_identity_provisioning.py",
            "tests/test_kernel_service.py",
        ],
        notes=(
            "Provisioning adapters may compile directory facts into actor identity "
            "and actor membership records; the IdP itself does not own role authority."
        ),
    ),
    IntegrationBoundary(
        family="tenant_adapter",
        purpose="Expose tenant-owned summaries without moving tenant policy into the public kernel.",
        primary_interface="read-model adapter",
        source_of_truth="tenant system",
        authority_owner="tenant policy and kernel read-model validation",
        examples=["forecast market", "action-impact ledger", "domain evidence policy"],
        conformance_tests=["tests/test_forecast_market_interface.py", "tests/test_action_impact_interface.py"],
    ),
)


def list_integration_boundaries() -> list[IntegrationBoundary]:
    return list(INTEGRATION_BOUNDARIES)


def app_integration_inventory() -> list[dict[str, object]]:
    return [boundary.as_dict() for boundary in INTEGRATION_BOUNDARIES]


def get_integration_boundary(family: str) -> IntegrationBoundary | None:
    for boundary in INTEGRATION_BOUNDARIES:
        if boundary.family == family:
            return boundary
    return None


def classify_integration(name_or_family: str) -> IntegrationBoundary | None:
    target = name_or_family.strip().lower().replace("-", "_")
    aliases = {
        "orbit": "app_surface",
        "cli": "app_surface",
        "slack": "app_surface",
        "teams": "app_surface",
        "linear": "enterprise_system",
        "salesforce": "enterprise_system",
        "erp": "enterprise_system",
        "crm": "enterprise_system",
        "mcp": "enterprise_system",
        "langgraph": "runtime",
        "autogen": "runtime",
        "crewai": "runtime",
        "filesystem": "state_backend",
        "sqlite": "state_backend",
        "postgres": "state_backend",
        "webhook": "inbound_event",
        "cloudevents": "inbound_event",
        "asyncapi": "inbound_event",
        "telegram": "notification",
        "oidc": "identity_provider",
        "saml": "identity_provider",
        "mtls": "identity_provider",
        "forecast_market": "tenant_adapter",
        "action_impact": "tenant_adapter",
    }
    return get_integration_boundary(aliases.get(target, target))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render cognitive-firm app integration boundaries.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--classify")
    args = parser.parse_args(argv)

    if args.classify:
        boundary = classify_integration(args.classify)
        if boundary is None:
            print(json.dumps({"found": False, "query": args.classify}, indent=2, sort_keys=True))
            return 1
        print(json.dumps(boundary.as_dict(), indent=2, sort_keys=True))
        return 0

    if args.json:
        print(json.dumps(app_integration_inventory(), indent=2, sort_keys=True))
    else:
        for boundary in INTEGRATION_BOUNDARIES:
            print(f"- {boundary.family}: {boundary.primary_interface}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
