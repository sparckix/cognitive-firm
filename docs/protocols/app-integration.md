# App Integration

**Status:** boundary protocol.
**Module:** `cognitive_firm.orchestration.app_integrations`
**Tests:** `tests/test_app_integrations.py`
**Shared enum:** `cognitive_firm.orchestration.connector_families`
**Related modules:** `cognitive_firm.kernel_service`,
`cognitive_firm.role_extensions.mcp_bridge`,
`cognitive_firm.orchestration.runtime_adapters`,
`cognitive_firm.orchestration.state_backends`,
`cognitive_firm.notifications.channels`

App integration is not one protocol. The kernel uses separate connector
families because different integrations carry different authority and failure
modes.

## Connector Families

| Boundary | Use | Primary interface |
|---|---|---|
| App surface -> kernel | Orbit, Slack/Teams, local web apps, scripts, operator consoles | Kernel service |
| Kernel -> external tools/data systems | Linear, Salesforce, ERP, CRM, ticketing, document systems | MCP outbox relay with capability checks and deterministic projections |
| External runtime -> kernel | LangGraph, AutoGen, CrewAI, OpenAI Agents SDK, custom runtimes | Runtime adapter -> run checkpoints |
| Kernel state storage | Filesystem, SQLite, future database/object store | SourceConnector / state backend |
| External event -> kernel | Webhooks, CloudEvents, AsyncAPI event streams | Inbound event projection with signature/idempotency checks |
| Kernel -> human attention surface | Telegram, null/local, future Slack/Teams pager | Notification-channel adapter |
| Request authentication | Local bearer token, OIDC, SAML, mTLS, gateway auth | Identity provider adapter |
| Directory -> kernel authority records | SCIM/HRIS/group export/setup script | Identity provisioning plan -> actor identity + actor membership |

MCP is therefore not the app-integration protocol. MCP is the governed
external-system action protocol.

Render the registry:

```bash
python -m cognitive_firm.orchestration.app_integrations
python -m cognitive_firm.orchestration.app_integrations --classify linear
python -m cognitive_firm.orchestration.app_integrations --json
```

## Rules

1. **Apps call kernel commands.** App surfaces should not reimplement lifecycle
   rules for human work, gates, directives, controls, chat, A2A obligations,
   accountability cases, leases, or learning events. They should call the
   kernel service. CLIs and Python modules remain local developer/operator
   tools, not app-surface write paths.
2. **External systems stay external.** Linear, Salesforce, ERPs, CRMs, and
   ticketing systems remain their own source of truth. The kernel records
   attempted governed actions, deterministic projections, and follow-up state.
3. **No LLM at projection.** MCP responses become kernel transitions only
   through registered deterministic projection functions. Unregistered or
   ambiguous tool responses are rejected.
4. **Authority is kernel-owned.** MCP servers, app surfaces, and identity
   providers can authenticate, transport, or expose capabilities. The kernel
   decides whether a role may act, whether a resource lease is required, and
   whether a case can close.
5. **Inbound events are observations.** Webhooks and event streams must pass
   signature, idempotency, and deterministic projection checks before becoming
   kernel events.
6. **Use one connector family per boundary.** Do not route ERP data through a
   state backend, do not use MCP as an app UI protocol, and do not make a graph
   runtime the durable organization record.

## MCP Scope

Use MCP when a role office needs to read or act against an external system.
The shipped path is:

```text
role office
-> mcp_call_requested row in transitions.jsonl
-> capability check
-> MCP transport
-> deterministic projection
-> mcp_call_dispatched or mcp_call_failed row
```

The Linear binding is intentionally read-only. It verifies server registration,
projection shape, capability gating, and relay behavior without giving the
kernel write authority over a third-party issue tracker by default.

For optional live validation:

```bash
export LINEAR_API_KEY=...
make mcp-linear-live-smoke
```

This command is not part of `make smoke-public` because it requires network
access and a tenant-owned credential.

For deterministic local validation:

```bash
make app-integration-conformance
```

This fixture exercises the current Linear Streamable HTTP projection shape and
the inbound-event signature/idempotency/conflict path without network access.
It also exercises the GitHub webhook provider adapter against a deterministic
signed replay fixture.

## Standards Context

- [Model Context Protocol](https://modelcontextprotocol.io/specification/)
  standardizes tool, resource, prompt, and transport semantics for LLM-facing
  external integrations.
- [MCP authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
  defines OAuth-based authorization for HTTP transports.
- [Agent2Agent](https://a2a-protocol.org/v0.2.4/specification/) targets
  interoperability among independent agent systems. cognitive-firm's A2A
  protocol is an organization-kernel protocol; a future remote adapter can
  translate at the boundary if needed.
- CloudEvents, OpenAPI, AsyncAPI, and ordinary webhook/API gateway patterns
  remain useful app and enterprise integration tools. They do not replace the
  kernel's authority, lease, and accountability records.

## Current Gap

The kernel has the connector-family registry, inbound-event T1 adapter, route
boundaries, identity provisioning seam, tenant-scope guard, and deterministic
conformance fixtures for Linear MCP projection, generic signed inbound events,
GitHub/Linear/Stripe webhook signature/header mapping, identity provisioning,
and actor membership enforcement. It does not yet ship a complete enterprise
OIDC/SAML provider implementation or durable T2 replay-window storage.

## Adoption Check

Before adding an integration, answer:

1. Is this an app surface, external system, runtime, state backend,
   notification provider, or identity provider?
2. What is the source of truth after the call?
3. Which role or actor is accountable for the mutation?
4. Which mandate, capability, lease, or accountability case authorizes it?
5. What deterministic projection makes the result reviewable?
6. What live smoke or replay fixture proves the adapter still works?

## Conformance Checklist

An adapter should not be treated as supported until it has at least one
deterministic conformance fixture. The fixture should prove:

1. **Identity:** the incoming subject maps to an `ActorContext` or service
   actor without bypassing registered actor checks.
2. **Authority:** role, tenant, capability, or mandate scope is enforced before
   a mutation or external side effect.
3. **Lease behavior:** contested mutable resources either require a lease or
   explicitly document why they are append-only.
4. **Idempotency:** replayed inbound events or retries do not create duplicate
   durable facts.
5. **Dead-letter path:** ambiguous, unverifiable, or unauthorized inputs land
   in a reviewable failure state.
6. **Projection shape:** tool/runtime/app responses are reduced by a
   deterministic projection function, not by an LLM interpretation step.
7. **Audit trail:** the resulting kernel record names producer, actor,
   source/system, payload or digest, correlation/idempotency key, and follow-up
   obligation when one exists.

Live credentials can have optional smoke tests. Public CI should use replay
fixtures or local fakes so adopters can run the checks without granting access
to their systems.
