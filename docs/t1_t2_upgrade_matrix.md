# T1 / T2 Upgrade Matrix

**Status:** deployment boundary guide.

cognitive-firm is designed to be useful as a filesystem-backed kernel for a
single authority domain before it becomes an enterprise control plane. This
matrix names the boundary so adopters can avoid both premature platform work
and overstated deployment claims.

## Deployment Classes

| Class | Description | Default stance |
|---|---|---|
| T1 Solo | One accountable authority, trusted hardware, private repo, filesystem system of record | Supported target. |
| T1 Small Team | A few trusted operators with shared repo access | Supported with explicit process discipline and optional actor membership. |
| T2 Controlled | Multiple users, role-separated approvals, audit expectations | Lean MVP supported for audit integrity, actor identity, actor membership, adapter authentication, and leases; policy hardening still required. |
| T2 Regulated | External audit, compliance controls, identity management | Requires hardened backend and signed audit. |
| T2 Multi-Authority | Multiple authority roles, departments, operating units, projects, or tenants with separate decision rights | Actor membership and scoped records are partially supported; domain-aware authority routing, boot checks, tenant isolation, and enterprise IAM remain deployment work. |

## Runtime Shape

The T1 runtime is filesystem-backed on one trusted host. Git is audit,
rollback, and synchronization, not the live message bus. Orbit, CLI, and
notification providers are app surfaces over the same kernel state.

For a startup, this is viable when the operating model is one accountable
authority or a small trusted operator set running one deployment. It is the
right shape for local pilots, research firms, founder-led operations, and early
adopter teams that value inspectability over multi-user platform polish.

Move toward a service API and stronger backend when more than one active
operator needs concurrent writes, enforceable identity boundaries, reliable
leases, or external compliance evidence. The intended path is:

```text
filesystem SourceConnector + Git
-> SQLite event source on one host
-> service API over the same kernel commands
-> Postgres/event-store/object-store connector for larger deployments
```

The primitives should stay stable across that path.

## Upgrade Axes

| Axis | T1 behavior | T2 trigger | T2 requirement |
|---|---|---|---|
| Identity | One accountable authority or small trusted set; actor context accepted from payloads | A second operator needs enforceable authority boundaries | Third-party authentication plus first-party actor identity, actor membership, trusted-header gateway adapter, subject-scope checks, role mapping, and per-action attribution. |
| Authority domains | Exactly one boot authority role; userland resolves one default authority for governance interrupts | More than one authority role can approve different classes of work | Domain-aware authority records, scoped escalation chains, and per-domain attention routing. |
| Audit | Git and append-only files by convention | External proof of non-tampering is needed | Chained log manifests ship as a lean T2-local seam; external timestamp/transparency-log references bind local roots to tenant-selected proof systems. |
| Leases | Filesystem atomicity on one host; leases optional | Multiple hosts or unreliable shared volume | First-party leases with fencing tokens and expiry; contested mutations should use the transactional backend path. |
| Outbox | Local filesystem polling | Network side effects or external webhooks | Retryable outbox with delivered, failed, and dead-letter states. |
| Observability | Logs and heartbeats | Operator cannot answer health questions quickly | Structured logs, counters, health checks, and alerting. |
| Recovery | Git plus manual restore | Downtime or data loss has external consequences | Snapshot cadence, restore runbook, and tested recovery. |
| Backend | Filesystem `SourceConnector` | Multi-host writes or compliance storage | SQLite event source and SQLite transactional mutation backend as lean T2 steps; database/object-store adapter preserving the same logical primitives for larger deployments. |
| Forecast market | Local forecast ledger | Forecasts affect shared budgets or regulated decisions | Scored calibration, routing policy, and approval boundaries. |
| Accountability | Follow-up summary | Agent actions create residual risk, externalities, or irreversible effects | Accountability cases with decision-right basis, recourse path, SLA, residual-risk owner, and closure evidence. |
| A2H work coordination | Agent-requested human work sessions with waiting, receipt, and follow-up read models | Humans repeatedly carry access, labor, safety, relationship, or authority work | Receipt policy, sampling, retention, rate limits, and escalation to accountability cases. |
| App surface | Orbit as local projection over filesystem state | Multiple operators, configurable workflows, or external adopter UX | Replaceable app layer backed by a generic org-surface read model. |

## Kernel / Config / App Boundary

The durable boundary is the kernel, not the current UI.

| Layer | Owns | Stability expectation |
|---|---|---|
| Kernel | Roles, mandates, transitions, A2A, MCP, project charters, evidence gaps, human work sessions, damage signals | Stable logical primitives. |
| Config / tenant overlay | Role set, mandates, project content, anchor validators, forecast policy, evidence policy, approval thresholds | Tenant-specific and replaceable. |
| App surface | Orbit, Telegram, CLI, future Slack/Teams/web apps, dashboards, work panes | Replaceable projection over kernel state. |

Orbit is the current T1 app surface. It is useful as a local principal cockpit,
but it should not be treated as the enterprise product boundary. The enterprise
track should preserve kernel state contracts while allowing a different app
surface to render the same org state.

The public kernel now ships a generic org-surface read model that joins:

- blocked A2A obligations;
- unresolved damage signals;
- project-charter validity;
- blocking evidence gaps;
- active human work sessions.
- A2H waiting-on-human, follow-up, missing receipts, and repeated human-work pressure.

Orbit, CLI, Telegram, or an enterprise web app can then render the same read
model without duplicating kernel logic.

Pending gates and forecast/calibration state remain natural extensions for
tenants that route budget or project scope through those surfaces.

## Source Connector Rule

Use one connector family per boundary:

- `state_backend` for kernel event/artifact storage.
- `enterprise_system` through MCP for ERP, CRM, issue trackers, and similar
  external systems.
- `runtime` through runtime adapters for graph/agent execution engines.
- `notification` through notification channels for human-facing alerts.

Do not route ERP or CRM data through the state backend just because it is
convenient. The state backend records kernel state; MCP records governed
external actions against systems whose source of truth remains outside the
kernel.

## Documentation Rule

Public docs should state which class a feature supports. They should not use
marketing language to imply T2 coverage when the shipped behavior is T1.

## Current Lean T2 Seams

The public kernel now ships the smallest useful T2-local seams:

- SQLite event source for stronger local event storage.
- SQLite transactional mutation backend for fenced lease acquisition/release and
  guarded mutation-event append through the kernel service.
- Kernel event envelope for framework-neutral event projection.
- Action attestations for machine-side provenance.
- Audit-integrity manifests for tamper-evident JSONL log verification, with
  external timestamp/transparency-log proof references.
- Accountability cases for accountable closure when ordinary follow-up
  visibility is not enough.
- Actor identity records for first-party actor context over external identity
  providers.
- Actor membership records for scoped role authority across multiple human,
  agent, or service actors in one deployment.
- Identity provider adapter interface, local bearer-token adapter, and
  trusted-header adapter for gateway-verified OIDC/SAML/mTLS deployments.
- Subject-scope enforcement for authenticated role/tenant claims.
- Resource leases for time-bounded mutation control.
- EU AI Act deploy gate for explicit mapping checks where a tenant opts in.

This is not a complete regulated-enterprise deployment. It does not yet include
tenant-specific OIDC/SAML configuration, enterprise RBAC administration,
managed key custody, or a hosted compliance control plane.

## Tenant Overlay Rule

Tenant overlays may implement stricter controls without changing the public
kernel. A tenant can require signed approvals, domain-specific forecast gates,
or private evidence workflows while still using the generic protocols.

When a tenant-specific control proves generally reusable, promote the interface
to the public kernel and keep the policy values in the tenant overlay.
