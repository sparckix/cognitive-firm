# protocols

_Folder index. Prose may be added above the auto-index block._

See also [A2H — Agent-to-Human Work Coordination](a2h.md), the protocol
pattern for agent-requested bounded human work, [Strategy Office Interface](strategy-office.md), the observer-only
review layer over forecast-market and action-impact learning carriers,
[Run Checkpoint Interface](run-checkpoints.md), the transition-log-backed
durable-run projection, and [Runtime Adapter Interface](runtime-adapters.md),
the boundary for first-party daemon and optional external runtime events.
[OpenTelemetry Export](otel-export.md) defines the observability projection for
run checkpoints.
[State Backends](state-backends.md) defines the `SourceConnector` family for
filesystem and database-backed kernel state.
[Kernel Service](kernel-service.md) defines the local HTTP boundary over the
same Python kernel commands.
[App Integration](app-integration.md) defines which connector family to use
for app surfaces, external systems, runtimes, state backends, notification
providers, and identity providers.
[Adapter Conformance](adapter-conformance.md) defines the fixture matrix for
supported adapters.
[Kernel Event Envelope](kernel-events.md), [Resource Envelope](resource-envelope.md),
and [Migration Records](migrations.md) define the compatibility layer for
events, resources, and versioned state changes. [Policy Decisions](policy-decisions.md)
records bounded allow/deny decisions without replacing mandates or existing
authorization checks.
[Inbound Events](inbound-events.md) defines webhook/event-stream ingestion with
signature checks, idempotency, quarantine, and deterministic projection.
[Learning Transition Compiler](learning-transition-compiler.md) turns
observer findings into reviewable transition candidates without mutating state.
[Intelligence Sources](intelligence-sources.md) records source coverage,
portable input metrics, and source-improvement backlog items over admitted
kernel-facing sources.
[Governance Change Proposals](governance-changes.md) records proposed
self-modifications with deterministic invariant checks before review.
[Approved Learning Events](learning-events.md) records reviewed behavior-change
events after candidate approval. [Audit Integrity](audit-integrity.md) defines
tamper-evident chain manifests for JSONL kernel logs.
[Actor Identity](actor-identity.md) defines first-party actor context while
leaving authentication to [Identity Provider Adapters](identity-providers.md).
[Actor Membership](actor-membership.md) defines scoped role authority for
multiple humans, agents, or services inside one deployment.
[Identity Provisioning](identity-provisioning.md) defines the adapter seam that
compiles external directory facts into actor identity and membership records.
[Tenant Isolation](tenant-isolation.md) defines the lean local scope guard and
deployment boundary for separate authority domains.
[Leases](leases.md) defines time-bounded write claims over mutable kernel
resources.
[Accountability Cases](accountability-cases.md) record authority, recourse,
residual-risk acceptance, and accountable closure; [Accountability Summary](accountability.md)
is the read model. [State Surface Inventory](state-surface-inventory.md) defines
the connector-inventory surface. [Action Attestation](action-attestation.md)
records compact machine-side provenance for actions, tool calls, runtime events,
and artifacts. [EU AI Act Deploy Gate](eu-ai-act-deploy-gate.md) defines the
optional T2 mapping check for roles that opt into it.
[Work Items And Operating Units](work-items.md) defines the production layer:
typed operating-unit contracts and a durable, lease-fenced work queue with
retries, dead letters, and bounded exits.
[Outcome Links](outcome-links.md) record whether an approved change improved a
measured outcome. [Routine Reviews](routine-reviews.md) schedule review and
accountable retirement of stale routines. [Resource Allocation](resource-allocation.md)
makes cross-operating-unit budget/capacity movement a governed decision.
[Decision Rights](decision-rights.md) record residual control rights for
situations an incomplete mandate does not cover.
Re-run the folder index generator when refreshing the managed index below.

<!-- AUTO-INDEX:START (managed by scripts/gen_folder_index.py — edit prose OUTSIDE this block) -->

## Index

**Sub-folders**

- None

**Documents**

- [a2a.md](a2a.md)
- [a2h.md](a2h.md)
- [accountability-cases.md](accountability-cases.md)
- [accountability.md](accountability.md)
- [action-attestation.md](action-attestation.md)
- [action-impact.md](action-impact.md)
- [actor-identity.md](actor-identity.md)
- [actor-membership.md](actor-membership.md)
- [adapter-conformance.md](adapter-conformance.md)
- [app-integration.md](app-integration.md)
- [audit-integrity.md](audit-integrity.md)
- [decision-rights.md](decision-rights.md)
- [eu-ai-act-deploy-gate.md](eu-ai-act-deploy-gate.md)
- [forecast-market.md](forecast-market.md)
- [governance-changes.md](governance-changes.md)
- [h2a.md](h2a.md)
- [identity-providers.md](identity-providers.md)
- [identity-provisioning.md](identity-provisioning.md)
- [inbound-events.md](inbound-events.md)
- [intelligence-sources.md](intelligence-sources.md)
- [kernel-events.md](kernel-events.md)
- [kernel-service.md](kernel-service.md)
- [learning-events.md](learning-events.md)
- [learning-transition-compiler.md](learning-transition-compiler.md)
- [leases.md](leases.md)
- [mandate.md](mandate.md)
- [mcp.md](mcp.md)
- [migrations.md](migrations.md)
- [otel-export.md](otel-export.md)
- [outcome-links.md](outcome-links.md)
- [policy-decisions.md](policy-decisions.md)
- [project-charter.md](project-charter.md)
- [resource-allocation.md](resource-allocation.md)
- [resource-envelope.md](resource-envelope.md)
- [routine-reviews.md](routine-reviews.md)
- [run-checkpoints.md](run-checkpoints.md)
- [runtime-adapters.md](runtime-adapters.md)
- [state-backends.md](state-backends.md)
- [state-surface-inventory.md](state-surface-inventory.md)
- [strategy-office.md](strategy-office.md)
- [tenant-isolation.md](tenant-isolation.md)
- [work-items.md](work-items.md)

<sub>0 sub-folder(s), 42 document(s). Auto-generated; re-run `scripts/gen_folder_index.py` after adding files.</sub>

