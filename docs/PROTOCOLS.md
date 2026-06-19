# cognitive-firm protocols

This index names the core protocols cognitive-firm defines. Each protocol has
its own spec under `docs/protocols/`.

The protocols sit on the OS / Config / App layer separation from the companion paper:

```
┌────────────────────────────────────────────────────────────────────┐
│  PRINCIPAL (human)                                                 │
│  ↕ H2A protocol — notification channel, Orbit, CLI                  │
│  ↕ A2H pattern — bounded human work requested by role offices       │
└──────────────────────────┬─────────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────────┐
│  ROLE OFFICES (research_director, manager, debate_runner, …)       │
│  ↕ A2A protocol — typed channels, obligation lifecycle,            │
│                   artifact dependencies                            │
└──────────────────────────┬─────────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────────┐
│  AGENT RUNTIMES (Claude, Codex, Gemini)                            │
│  ↕ MCP protocol — capability-gated tool dispatch                   │
└──────────────────────────┬─────────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────────┐
│  EXTERNAL SYSTEMS (Linear, Salesforce, ERPs)                       │
│  ← cognitive-firm reaches via MCP servers                          │
└────────────────────────────────────────────────────────────────────┘

Mandate protocol (orthogonal): typed contract files in org/mandates/*.md
defining what each role may do autonomously vs what requires escalation.

Project charter protocol (orthogonal): tenant/project scope-fidelity files
that keep work aligned with its intended object without turning the kernel into
a project-type ontology.

Run checkpoints (orthogonal): long-running role-office work is recorded as
`run.*` events in the transition log, then projected by replay. This gives the
kernel durable-execution visibility without importing graph-runtime semantics.

Runtime adapters (orthogonal): external agent runtimes such as LangGraph,
OpenAI Agents SDK, Google ADK, Microsoft Agent Framework, CrewAI, AutoGen, or
Letta can project lifecycle events into the run-checkpoint interface. The
runtime owns execution; cognitive-firm owns the organizational projection.

Multi-agent trace attribution (orthogonal): recursive delegation, team
evolution, phase-based execution, and protocol-test runtimes can import local
and cross-agent trace evidence as review carriers. The kernel records
attribution packets, delegation graph projections, and diagnostics; it does
not execute agents or mutate governance state from traces.

Phase execution (orthogonal): runtimes or demos can record Strategy ->
Execution -> Verification directives and verifier feedback with bounded retry
budget decay. This is a small execution overlay, not a general runtime.

Protocol experiments (orthogonal): runtimes or demos can record bounded
comparisons of coordinator, sequential, batched sequential, shared, broadcast,
or custom coordination patterns. Reports can emit observer-only route-policy
candidates, but any promotion still requires governance review and approval.

Capability signals (orthogonal): runtimes, work queues, authorization gates, or
role offices can record abstention, insufficient authority, evidence gaps,
capability gaps, tool unavailability, overload, budget exhaustion, or unsafe
requests as routing evidence. A signal is not task failure by default; it routes
to reassignment, escalation, evidence repair, capability request, learning, or
governance review.

Worker taxonomy (orthogonal): capability, fungibility, state, and transport
are separate axes. This vocabulary explains whether a worker is a bare model
call, tool-using agent, deterministic system, or human, and whether the worker
is interchangeable or a named continuing role. It does not grant authority;
roles, mandates, memberships, and leases still decide who may act.

Forecast market and action-impact interfaces (orthogonal): read-model adapters
that let tenant forecast markets and measured-impact ledgers feed the generic
organization surface without moving tenant policy or optimizers into the
kernel. The strategy-office interface is a second-order observer over those
learning carriers; it emits review findings but does not route work. The
learning-transition compiler turns those findings into reviewable candidates
without applying them. Accountability summaries join owners, projects,
externalities, and review status across those carriers.

Intelligence-source coverage (orthogonal): read-model projection over the
state-surface inventory and organization-surface inputs. It marks tenant-owned
sources, proxy-only projections, thin signals, score/decision-use debt, and
source-improvement items without collecting tenant-specific metrics.

Action attestations (orthogonal): compact machine-side provenance rows for
agent actions, tool calls, runtime events, prompts, datasets, and artifacts.
They are the machine counterpart to human-work receipts and expose a
resource-envelope projection for adapter and dashboard compatibility.

Formal verification (orthogonal): provider-agnostic certificate rows from Lean,
SMT, Isabelle, Coq, Alloy, TLA+, or tenant checkers. A refuted or invalid
certificate fails the governed-run bundle; an inconclusive certificate makes it
incomplete. Signed provider payloads can be packaged into
`formal_provider_proof_pack.v1` adoption receipts; missing provider trust,
checker evidence, or faithfulness refs remain explicit bundle caveats.

Audit integrity (orthogonal): chained manifests over JSONL state logs, with
optional HMAC verification and external timestamp/transparency-log proof
references. This is a lean T2-local audit seam; tenant deployments still own
key custody, notary/TSA selection, and compliance operations.

Accountability cases (orthogonal): write-side records for authority envelope,
decision right, accountable role, residual-risk acceptance, recourse path, and
closure evidence. The accountability summary is a read model; cases are the
review/closure primitive.

A2H work coordination (orthogonal): role offices can request bounded human
work through human work sessions without turning the human into an agent
message endpoint or transferring accountability away from the role office.

State backends (orthogonal): source connectors for kernel state transport.
The T1 implementation is filesystem-backed; lean T2 paths include SQLite event
storage, SQLite transactional mutation fencing, and an optional Postgres
mutation backend. MCP remains the enterprise-system connector family for ERPs,
Linear, Salesforce, and similar systems.

Kernel service, identity providers, actor identity, actor membership, authority domains, and leases (orthogonal):
app surfaces can call the same kernel primitives through a local HTTP service.
Authentication remains an adapter concern; actor attribution and leases remain
first-party kernel records because they carry accountability and mutation
control. Gateway-verified OIDC/SAML/mTLS deployments can use the trusted-header
identity adapter, identity-provisioning seam, subject-scope enforcement, and
scoped actor memberships. Authority domains resolve which authority role owns a
tenant, project, operating unit, resource class, or decision class. Tenant
isolation starts with kernel scope guards, but hard isolation across authority
domains remains deployment architecture.

App integration (orthogonal): app surfaces, external enterprise systems,
runtime engines, state backends, notification providers, and identity providers
use separate connector families. MCP is the external-system action connector,
not the universal app-integration mechanism.

Inbound events (orthogonal): webhooks and external event streams enter as
quarantinable observations. They become kernel events only after
signature/idempotency checks and deterministic projection.

Local review artifacts (orthogonal): tenant-owned records for interdisciplinary
or synthetic reviews of significant primitive, mandate, charter, strategy, or
tenant-policy changes. Keep artifacts under the gitignored `reviews/`
workspace by default, and promote only durable conclusions into docs or policy.

Distribution (orthogonal): versioned `distro`/`overlay` packages, a package
registry, and a transactional git-backed installer compose a runnable governed
organization an operator installs in one action. The installer is the userland
of the OS analogy; it never writes the kernel, only overlay files the adopter
owns. Extension schemas (orthogonal) let a package register a per-`kind` JSON
Schema to validate custom primitive payloads without a kernel change.
```

## The core protocols

### [A2A — Agent-to-Agent](protocols/a2a.md)

How role offices coordinate with each other inside the kernel. Typed `AgentMessage` envelopes, seven performative kinds (`request`, `proposal`, `handoff`, `inform`, `clarification`, `refusal`, `status`), an **obligation lifecycle** distinct from envelope status (so "B is blocked waiting on A's output" is structurally visible, not inferred), and a **content-addressed artifact-dependency primitive** so "task B requires task A's output X with property Y" is a typed event rather than implicit knowledge.

Status: shipped for single-authority governance kernels. Phase A (obligation lifecycle), Phase B (artifact dependencies), and Phase C (saga compensation) all shipped. `make a2a-delegation-command-conformance` exercises standalone role-policy and handoff lifecycle, `make a2a-h2a-command-conformance` exercises the blocked-obligation-to-human-work seam, and `make saga-command-conformance` exercises the saga compensation command path. Remote adapter (cross-VPS role-to-role messaging) remains queued for T2 deployments.

### [H2A — Human-to-Agent](protocols/h2a.md)

How the principal interacts with role offices. Three surfaces:
**notification channel** (mobile/fast pager + STOP authority; Telegram is the
default provider), **Orbit** (desktop projection with TLDraw spatial canvas +
governance pane + chat pane + damage feed), **CLI** (direct invocation for
ops). Each surface has an explicit attention-layer assignment under Stewart
Brand's pace-layering principle: slow (mandate config), working (tasks,
hourly), fast (damage signals, seconds). The chat surface carries a persistent
conversation state per role with cross-day memory and self-extending pinned
facts. Human work sessions capture cases where the human performs actual work
alongside a role office rather than merely approving or rejecting a gate.

Status: these surfaces are implemented as kernel/app interfaces and covered by
the public smoke path where practical.

### [A2H — Agent-to-Human Work Coordination](protocols/a2h.md)

How a role office asks a human to do bounded object-level work, such as a
restricted-source check, partner call, physical-world check, taste call, or
private judgment. A2H is a pattern over human work sessions: the role creates a
session with a concrete deliverable, the human records a bounded receipt or
claim, and the role remains responsible for integration. Link the session to an
A2A obligation when the human work is carrying a role-to-role dependency.
The organization surface exposes A2H waiting, follow-up, missing receipts, and
repeated pressure by role/bottleneck class. Work discovery routes A2H sessions
back to the role office only after the human has handed off or completed the
bounded work. Human-work sessions also expose a resource-envelope projection
for adapter and dashboard compatibility while keeping the JSONL rows
authoritative.

Status: shipped as a helper and protocol pattern over `human_work.py`, with a
resource projection and tests.

### [MCP — Model Context Protocol](protocols/mcp.md)

How role offices reach external enterprise systems (Linear, Salesforce, ERPs, ticketing). The kernel writes one `mcp_call_requested` row to `transitions.jsonl` (the outbox). An outbox-relay reads pending rows, dispatches via JSON-RPC to the registered MCP server (stdio or HTTP transport), applies a deterministic projection function to map the response into a typed transition class, and appends a follow-up event. **No LLM at projection** — ambiguous returns are rejected, not interpreted.

A capability-token primitive at the Config layer gates which (role, server, tool) tuples are permitted. Capabilities can be mandate-lifetime or task-bound (revoked when the task closes).

Status: Phase 1 (outbox-relay) + Phase 1.5 (transport + Linear binding) + Phase 2 (capability tokens) shipped. Phase 3 (supply-chain pinning: digest + signed manifest + revocation feed) and Phase 4 (IdP federation) deferred until concrete adopter demand.

### [App Integration](protocols/app-integration.md)

How app surfaces, external enterprise systems, runtime engines, state backends,
notification providers, and identity providers attach to the kernel without
collapsing into one integration protocol.

Status: registry, boundary protocol, and tests shipped. Live external-system
smoke remains optional and credentialed.

### [Adapter Conformance](protocols/adapter-conformance.md)

The fixture matrix every app, runtime, provider, identity, state, notification,
or tenant adapter should satisfy before it is treated as supported.

Status: public protocol and deterministic conformance helpers shipped. Runtime
adapter support now also has `make runtime-adapter-proof-pack`, which compares
native and external-runtime governed-run evidence without installing or
running the external framework.

### [Inbound Events](protocols/inbound-events.md)

How external webhooks and event-stream messages enter the kernel without
turning into trusted mutations by default. The adapter verifies signatures,
deduplicates by idempotency key, quarantines failures, and records accepted
events through the kernel event envelope.

Status: T1 adapter and tests shipped.

### [Mandate](protocols/mandate.md)

The typed contract format that defines a role's authority. Each role has a `org/roles/<role_id>.yaml` file (the structured part: authorized_paths, forbidden_paths, budget caps, delegates_to / escalates_to, authorized_mcp_capabilities) and an `org/mandates/<role_id>_mandate.md` file (the prose part: discipline, run-vs-analyze rules, recursion guards, damage-signal classes). The kernel verifies the mandate hash each tick.

Status: shipped for T1 use. Schema documented inline in the role yaml + mandate templates.

### [Project Charter](protocols/project-charter.md)

How a tenant or project records scope fidelity: core question, out-of-scope
boundaries, end states, forecast type, inheritance, and anchor proxies. The
charter protocol keeps project intent inspectable by dispatchers, reviewers,
forecast agents, and operators while keeping tenant policy out of the public
kernel.

Status: protocol spec for tenant/project overlays. Enforcement can be advisory,
parsed, or anchored depending on which tenant-side validators are present.

### [Forecast Market Interface](protocols/forecast-market.md)

How the kernel consumes tenant forecast-market state without owning the market.
The interface normalizes lifecycle state, forecast debt, score debt,
decision-use rows, high-confidence misses, allocation recommendations, and
reflexive insights. Tenants own contract creation, forecaster wakeups,
aggregation, scoring, calibration policy, and domain-specific externality
analysis.

Status: read-model interface and org-surface integration shipped.

### [Intelligence Sources](protocols/intelligence-sources.md)

How the kernel inventories source coverage across state surfaces, tenant-owned
read models, process/input signals, and source-improvement backlog items.

Status: projection and org-surface integration shipped.

### [Action Impact Interface](protocols/action-impact.md)

How the kernel consumes measured intervention outcomes without shipping a
generic optimizer. The interface preserves baseline and counterfactual actions,
decision stage, expected effect, observed outcome, costs, evaluator role,
decision-changed flag, and externality tags so tenants can evaluate future
bandit or mini-RL policies offline before any live routing.

Status: read-model interface, org-surface integration, conservative offline
policy evaluation, and service-routed promotion packets shipped.

### [Action Attestation](protocols/action-attestation.md)

How the kernel records compact provenance for agent/runtime/tool work. An
attestation binds a subject reference and digest to a producer, action type,
runtime/tool/policy refs, input/output refs, and verification status. It does
not prove correctness; it makes machine-side work reviewable.

Status: T1 filesystem adapter and tests shipped.

### [Governed Run Attestation Bundle](protocols/governed-run-attestation.md)

How the kernel exports one governed run as a compact audit packet over
existing records: run checkpoints, action attestations, formal verifications,
human work sessions, linked production work items, outcome links,
accountability cases, linked leases, referenced governance approvals,
derived evidence hashes, observability refs, plus an owner-authority snapshot.
The bundle reports caveats rather than turning provenance into a correctness
claim. Existing bundle JSON can be validated against the v1 interchange schema
and digest before another runtime or provider consumes it. Read-only
kernel-service routes can build and validate the same bundle for app surfaces
and demos.

Status: export view, CLI, kernel-service routes, and tests shipped.

### [Governed Mutation Proofs](protocols/mutation-proofs.md)

How the kernel summarizes an approved state mutation as an ordered proof row
over existing records: run, work item, proposal, approval, mutation,
attestation, learning, outcome, review, governed-run bundle, and git commit.
The proof row is a review/export projection. It does not authorize mutation
and it does not replace the underlying ledgers. Read-only kernel-service routes
can build and validate proof payloads for app surfaces and demos.

Status: projection helper, kernel-service routes, and tests shipped.

### [Governed Run Recipes](protocols/governed-run-recipes.md)

How demos, adapters, and starter overlays compose common governed paths without
duplicating lifecycle glue. The current helpers shape mutation-proof request
bodies and work-completion artifact refs, then call existing kernel service
routes. Recipes do not authorize work, approve proposals, mutate files, build
proofs, or create a second governance lifecycle.

Status: thin helper module and tests shipped.

### [Loop Engineering](protocols/loop-engineering.md)

How the kernel wraps repeated agent and human-agent loops with authority,
state, verification, escalation, outcome, and learning records. Agent runtimes
own execution; cognitive-firm owns the organizational packet around the loop.

Status: composition guide over shipped primitives.

### [Audit Integrity](protocols/audit-integrity.md)

How the kernel creates and verifies tamper-evident chain manifests over JSONL
state logs. This gives T2 adopters a concrete local integrity check for
transition logs and other JSONL state surfaces before they add external
signing, timestamping, key management, or transparency logs.

Status: lean T2-local audit seam and tests shipped.

### [Accountability Cases](protocols/accountability-cases.md)

How the kernel records accountable closure when work crosses a boundary that
cannot be handled by ordinary follow-up visibility. Cases name the accountable
role, responsible actor, decision-right basis, authority envelope, risk tier,
recourse path, SLA, residual-risk owner, and closure evidence.

Status: lean T2-local primitive and tests shipped.

### [Actor Identity](protocols/actor-identity.md)

How the kernel records first-party actor context for organizational
accountability while leaving authentication and federation to IdP/OIDC/SAML
adapters.

Status: first-party interface and tests shipped.

### [Actor Membership](protocols/actor-membership.md)

How the kernel records scoped role assignments for humans, agents, and services.
Memberships let one deployment support multiple actors with different role,
tenant, or project authority without making the kernel an enterprise IAM
system.

Status: first-party interface, kernel-service routes, CLI, and tests shipped.

### [Identity Provider Adapters](protocols/identity-providers.md)

How service deployments authenticate requests without treating the external
identity provider as the source of organizational authority. Adapters return
authenticated subject facts; the kernel maps those facts through actor identity,
actor membership, mandates, leases, and accountability records.

Status: adapter interface and local bearer-token adapter shipped.

### [Identity Provisioning](protocols/identity-provisioning.md)

How a tenant-owned directory, SCIM/HRIS bridge, or setup script compiles
external identity facts into actor identity and actor-membership records. This
keeps IAM administration outside the kernel while giving the kernel enforceable
authority records.

Status: adapter seam, CLI, and tests shipped.

### [Tenant Isolation](protocols/tenant-isolation.md)

How local app/config code checks actor tenant scope and tenant overlay path
boundaries. This prevents common cross-tenant mistakes without claiming hosted
multi-tenant infrastructure.

Status: lean scope guard and tests shipped.

### [Leases](protocols/leases.md)

How the kernel records time-bounded mutation claims over resources so
multi-operator deployments can prevent concurrent writes without changing
primitive semantics.

Status: first-party interface and tests shipped.

### [Work Items And Operating Units](protocols/work-items.md)

How the kernel runs recurring production work under the governance layer. An
operating unit is the typed contract for one production lane (a station, desk,
or department); a work item is one durable, claimable unit of work that flows
through it. Claims are lease-fenced with monotonic tokens, failures retry and
then dead-letter, and completion must land on a bounded exit the unit declared
in advance. Every transition emits a kernel event. The operating-unit dashboard
projects backlog, claimed, p95, throughput, and blockers per unit.

Status: first-party interfaces, kernel-service routes, CLIs, and tests shipped.

### [Worker Taxonomy](protocols/worker-taxonomy.md)

How the kernel describes worker roles without collapsing capability,
fungibility, state, and transport. A worker can be a tool-using agent and still
be interchangeable if all relevant context is externalized; a worker can be
stateful and singular when continuity or review identity matters. Transport
choices such as API, subscription CLI, local process, or human channel are
sourcing decisions, not governance categories.

Status: shared vocabulary module, operating-unit import, protocol doc, and
tests shipped.

### [Outcome Links](protocols/outcome-links.md)

How the kernel records whether an approved change actually improved a measured
outcome. An outcome link ties a change (a learning event, governance change, or
accountability case) to a baseline metric snapshot, post-change snapshots, and
a tenant verdict. The kernel owns the typed record and lifecycle; the tenant
owns the metric and the verdict. This makes the kernel's central claim —
durable learning produces measurable improvement — testable from kernel
records rather than asserted.

Status: first-party interface, kernel-service routes, CLI, and tests shipped.

### [Routine Reviews](protocols/routine-reviews.md)

How the kernel sunsets stale routines. Approved learning events otherwise only
accumulate; routine reviews schedule a review of a routine by a due date,
surface overdue reviews as forgetting pressure, and record an accountable
retirement transition. The kernel owns the schedule and the transition; the
tenant owns the review cadence and the judgment.

Status: first-party interface, kernel-service routes, CLI, and tests shipped.

### [Resource Allocation](protocols/resource-allocation.md)

How the kernel makes cross-operating-unit resource movement a governed
decision. The kernel ships divisions (operating units) and a dashboard; this
adds the general-office function: a typed allocation decision moves budget or
capacity between units with a deciding role, authority basis, and rationale,
and projects an allocation ledger. The kernel records decisions; the tenant
owns the optimizer that proposes the numbers.

Status: first-party interface, kernel-service routes, CLI, and tests shipped.

### [Decision Rights](protocols/decision-rights.md)

How the kernel records residual control rights for incomplete mandates. A
mandate is an incomplete contract; when it is silent, the residual-rights
holder decides. Residual-right assignments name the default decider per scope;
residual decisions record what was decided where no clause applied, flag an
unauthorized decider rather than rejecting the record, and can be promoted to a
new mandate clause. Both canonical row types expose resource-envelope
projections for adapter and dashboard compatibility while keeping the JSONL
rows authoritative. This keeps mandate-gap decisions reviewable.
The holder-resolution read model also projects the accountable authority-domain
role when no explicit assignment exists, while preserving explicit assignments
as the only residual-decision authorization source.

Status: first-party interfaces, kernel-service routes, CLI, and tests shipped.

### [Decision Aggregation Cases](protocols/decision-aggregation.md)

How the kernel records decision procedure evidence without replacing authority.
Decision rights answer who may decide; decision aggregation records how eligible
inputs were collected and computed for a specific subject. Shipped procedures
include `single_authority`, `quorum_majority`, `veto`, and `unanimity`, with
built-in read-only procedure profiles that expand into the same case shape. A
computed case is evidence for governance, policy, residual-decision,
accountability, or learning paths; it does not apply organization mutations by
itself.

Status: first-party interface, kernel-service routes, resource projection, and
tests shipped.

### [Accountability Summary](protocols/accountability.md)

How the kernel joins owners, projects, review status, due dates, source
references, and externality tags across the organization surface. It is a
read model for follow-up visibility, not a blame ledger and not a writer.

Status: read-model interface and tests shipped.

### [Run Checkpoint Interface](protocols/run-checkpoints.md)

How role offices expose long-running work to the organization surface. The
interface records `run.started`, `run.checkpointed`, and `run.state_changed`
events through the canonical transition log. Current state is derived by
replay, preserving the design rule that `transitions.jsonl` is the local
outbox/event adapter and not one ledger among many.

Status: transition-log-backed interface and org-surface integration shipped.

### [Execution Routing](protocols/execution-routing.md)

How the first-party daemon and tenant adapters turn work-item frontmatter and
body text into a conservative route contract before execution. It can identify
direct work, expert review, synthesis review, scripted runs, artifact builds,
joint human work, experiment loops, and docs/records work. The route is not
authority: mandates, leases, policy decisions, and resource envelopes still
decide what may run.

Status: first-party route-contract helper and tests shipped.

### [Runtime Adapter Interface](protocols/runtime-adapters.md)

How external graph, crew, chat, or agent runtimes expose lifecycle state to the
kernel without making cognitive-firm depend on any one framework. Adapters emit
`started`, `checkpointed`, `state_changed`, and `interrupted` events keyed by
`runtime:<runtime_name>:<external_run_id>`, then the kernel records the
organizational projection as canonical `run.*` transition rows. Interrupted
runs are bridged into A2H human-work sessions; the external runtime keeps its
own resume token.

Status: framework-neutral adapter and tests shipped.
`make runtime-interrupt-command-conformance` exercises the CLI path for
external-runtime HITL pauses: pre-start checkpoints and incomplete interrupts
are rejected, a valid interrupt pauses the run, creates one receipt-required
A2H human-work request, preserves the resume ref, and reuses that request on
interrupt replay. `make runtime-adapter-proof-pack` validates the bundled
LangGraph adapter-policy manifest/config and proves that native and
LangGraph-style demos share one governed-run evidence contract. First-party
vendor wrappers are intentionally left to tenants until a concrete integration
needs one.

### [Agent Runtime Invocation Policy](protocols/agent-runtime-invocation.md)

How the first-party Python daemon and live kernel-native demos construct
local/subscription agent subprocess commands without becoming a model runtime
or graph scheduler. The policy resolves Claude/Codex adapters, project roots,
permission modes, sandbox flags, optional tool controls, and subscription-auth
environment scrubbing. It records redacted command shape for receipts while
leaving model execution, tool calls, and native memory to the selected CLI.

Status: shared daemon/demo invocation helper and tests shipped.

### [Multi-Agent Trace Attribution](protocols/multi-agent-trace-attribution.md)

How recursive delegation, team-evolution, phase-based execution, and protocol
experiment runtimes import local-agent and cross-agent trace evidence into the
kernel. The primitive records `MultiAgentTraceEvent` rows, summarizes
abstention, failed handoff, verifier-failure, overcommitment, and
undercommitment signals, and creates `FailureAttributionPacket` carriers that
project to observer-only learning-transition candidates in the service review
queue. It also projects an observer-only delegation graph for demos, audits,
and dashboards. It does not spawn agents, approve changes, or mutate roles,
mandates, protocols, or policies.

Status: alpha evidence carrier and tests shipped.

### [Phase Execution Overlay](protocols/phase-execution.md)

How agent runtimes or deterministic harnesses record Strategy -> Execution ->
Verification directives and independent verifier feedback. Failed, blocked, or
inconclusive verification decays remaining retry budget and can block a plan
when attempts or budget are exhausted. The overlay records the execution
evidence; it does not execute agents or approve changes.

Status: alpha execution overlay and tests shipped.

### [Protocol Experiments](protocols/protocol-experiments.md)

How runtimes or deterministic harnesses compare coordination patterns before
promoting a route-policy change. Experiments record candidate protocols,
observations, summaries, blockers, and observer-only governance candidates.
They do not execute agents or mutate routing policy.

Status: alpha telemetry carrier and tests shipped.

### [Capability Signals](protocols/capability-signals.md)

How runtimes, role offices, work queues, and authorization gates record
grounded abstention or capability gaps without treating them as task failure.
Signals preserve source refs, severity, route recommendation, evidence refs,
and closure receipts for reassignment, escalation, evidence repair, capability
request, learning, or governance review. Open signals project to observer-only
learning-transition candidates so abstention and authority gaps can affect
future review without counting as task failure.

Status: alpha routing-evidence carrier and tests shipped.

### [OpenTelemetry Export](protocols/otel-export.md)

How run checkpoints are projected into OpenTelemetry GenAI-shaped span dictionaries without
making traces the source of organizational truth.

Status: projection shape and tests shipped.

### [State Backends](protocols/state-backends.md)

How kernel state storage is abstracted without changing protocol semantics.
State backends are `SourceConnector` implementations for event streams and
artifacts. The filesystem backend supports T1 local operation. SQLite event
source and SQLite transactional mutation backend are the lean T2 migration
points for adopters who need stronger local append semantics and lease-fenced
mutation events before moving to Postgres, an event store, or object storage.

Status: filesystem backend, SQLite event source, SQLite mutation backend, and
optional Postgres mutation adapter shipped with tests/conformance coverage.

### [Kernel Service](protocols/kernel-service.md)

How local app surfaces call kernel commands through HTTP without reimplementing
primitive lifecycle rules. The service is stdlib-only and calls the same Python
functions as the CLI and tests.

Status: local service adapter shipped, including v0.4 read/write surfaces for
proposal templates, review projections, proposal review packets, human-work
receipts and pressure, human-speed envelopes, human-work pressure learning candidates, pre-work
learning context packets, learning-use receipts, provenance timeline,
projection-only provenance graph, and portable provenance handoff reports.

### [Kernel Event Envelope](protocols/kernel-events.md)

The canonical event envelope and compatibility adapter for newer primitives and
gradual migration from older transition-log rows. It records actor, verb,
object refs, tenant/project, causation/correlation IDs, idempotency, payload,
and payload hash. The transition log remains the T1 source of truth for runtime
governance mutations until a primitive is deliberately migrated.

Status: envelope, legacy transition projection, local JSONL compatibility
adapter, and tests shipped.

### [Resource Envelope](protocols/resource-envelope.md)

The lightweight object shape for kernel resources:
`api_version`, `kind`, `metadata`, `spec`, `status`, and `links`. This is a
compatibility convention, not a storage backend.

Status: envelope and validation tests shipped.

### [Policy Decisions](protocols/policy-decisions.md)

How bounded allow/deny decisions are recorded with request, matched rule,
reason, and evidence refs. This is an audit shape for policy decisions, not a
replacement for mandates, task authorization, MCP capability checks, or human
approval. Policy decisions also expose a resource-envelope projection for
adapter and dashboard compatibility while keeping the append-only row
authoritative.

Status: local deterministic evaluator, JSONL record, resource projection, and
tests shipped.

### [Migration Records](protocols/migrations.md)

The dry-run-first protocol for state/schema migrations across durable kernel
files and event streams.

Status: migration record adapter and tests shipped.

### [State Surface Inventory](protocols/state-surface-inventory.md)

How the kernel records which primitive owns which state surface, which
connector family it belongs to, and which tests cover the boundary. This is the
code-backed conformance list for `SourceConnector` discipline.

Status: inventory and tests shipped.

### [Strategy Office Interface](protocols/strategy-office.md)

How the kernel emits observer-only strategy-review findings over generic
learning carriers such as evidence gaps, human work, damage signals, failed
runs, forecast-market state, and action-impact state. This is a
primitive interface, not a mandatory new role: tenants decide which office or
role reviews the findings and whether any finding becomes a mandate update,
evidence gap, human-work session, or task.

Status: read-model interface shipped.

### [Governance Change Proposals](protocols/governance-changes.md)

How the kernel records proposed changes to mandates, roles, routes, gates,
capability policy, learning policy, or tenant policy while keeping
self-modification governed. Proposals must carry deterministic invariant checks
and structural evidence sufficiency: source refs, expected behavior change,
risk summary, rollback plan, and evidence refs for passing invariant checks.
They are either blocked or review-ready. The primitive does not apply changes.
Governance-change proposals also expose a resource-envelope projection for
adapter, dashboard, migration, and conformance compatibility. Learning
transition candidates can be promoted into governance-change proposals through
the service route, but the normal evidence-sufficiency gate still decides
whether the result is blocked or review-ready. Charters can opt into a
deletion-duty check so structure-adding proposals must name a retirement
candidate or justify net growth.

Status: proposal log, candidate-promotion helper, invariant checks, evidence
sufficiency gate, optional deletion-duty evidence, resource projection,
org-surface integration, and tests shipped.

### [Learning Transition Compiler](protocols/learning-transition-compiler.md)

How the kernel turns organization-surface findings into reviewable transition
candidates. The compiler is a generic bridge from learning carriers to possible
durable state changes, but it remains observer-only: tenants decide who reviews
the candidates and which, if any, become real updates.

Status: compiler, human-work/attention/execution candidate service
projections, candidate-to-governance proposal route, userland inspection, and
tests shipped.

### [Approved Learning Events](protocols/learning-events.md)

How reviewed transition candidates become durable behavior-change records.
Approved learning events record decision-use, source carriers, before/after
state, approval references, and future application cues without applying the
referenced mutation themselves.

Status: filesystem adapter, deterministic replay, context-packet projection,
learning-use receipts, loop projection, userland commands, and tests shipped.

### [Distribution](protocols/distribution.md)

How a runnable governed organization is packaged, installed, verified, and
rolled back. A `distro` is a curated day-one-runnable starter organization; an
`overlay` is an add-on installed on an existing organization. Install is
transactional and git-backed: the installer ensures the target is its own git
repo, applies the package, enforces a kernel-version gate, verifies the
governance graph and installed adapter/provider policy, and only then commits
and tags the result `install/<package>/<version>`. A failed or unbootable
install leaves the target untouched. A component carries a composition `op` —
`add` / `replace` / `patch` (RFC 7386 JSON Merge Patch). `rollback` undoes a
bad install — a clean `git reset` when nothing has run since the install
boundary, or a compensating `git revert` forward commit when the org has run.
Installing an overlay onto a *running* org is governed: it files an
authority-diff proposal and is blocked if it would widen a role's authority. A
package can be installed from a git URL (SHA-pinned, recorded in a
content-hashed `packages.lock`), and a distro may `extends` a base distro. The
bundled `starter-firm` distro and the `cognitive-firm-distro` CLI (`list / show
/ install / verify / upgrade / rollback / uninstall / lint`, with
`install --dry-run`) ship in the wheel.

Status: package registry, transactional installer with `op` composition,
`boot_check` verifier, governed overlay install, remote git-URL fetch with
lockfile, `extends` inheritance, rollback, `lint`/`--dry-run` authoring loop,
`starter-firm` distro, CLI, and tests shipped.

### [Extension Schemas](protocols/extension-schemas.md)

How a package or org validates a custom primitive type without a kernel
change. A package ships JSON Schema files under
`extension_schemas/<primitive>/<type_key>.schema.json`; the generic
`validate_payload` hook checks a payload against any registered schema. Open by
default — a `kind` with no registered schema is enqueued unconstrained, so the
kernel's open-typed baseline is preserved. The hook is wired into
`enqueue_work_item` today; the same one-line idiom is how future primitives opt
in.

Status: first-party interface, `WorkItem` enqueue call site, and tests
shipped.

## Organizational Learning

The protocol layer is paired with a generic
[`organizational learning loop`](organizational_learning_loop.md): findings
compound only when translated into durable state objects such as mandate
updates, charter updates, evidence gaps, forecast calibration rows, damage
signals, action-impact rows, A2A obligations, or artifact dependencies.

The generic organization surface in
`cognitive_firm.orchestration.org_surface` reads those carriers back out for
humans and agents before work begins. It currently summarizes blocking evidence
gaps, open evidence gaps, human work sessions, blocked obligations, damage
signals, invalid project charters, forecast-market health, action-impact
review items, strategy-review findings, active approved learning events, plus
active and failed long-running runs. The learning-transition compiler can be
run over that surface to produce reviewable candidates. The service can also
compile the routed attention feed into observer-only candidates for unrouted,
stale, or repeated attention pressure without changing routing behavior.
Repeated or critical damage signals can likewise compile into observer-only
review candidates; accountability cases remain the explicit write-side closure
path.

Deployment-class boundaries are documented in the
[`T1 / T2 upgrade matrix`](t1_t2_upgrade_matrix.md).

## Honest scope

These specs describe **what is currently shipped**, not what is aspirational. Where a primitive is queued (MCP Phase 3 supply-chain pinning, MCP Phase 4 IdP federation, A2A remote adapter) the spec says so explicitly. Adopters who read these docs to understand what they would integrate against can rely on every "shipped" claim being backed by tests in `cognitive-firm/tests/`. Test references are listed in the relevant protocol specs.

## Threat-model coverage

Each protocol spec ends with a threat-model table separating **T1** (single-authority, trusted-hardware) from **T2** (regulated enterprise, multi-tenant). Some primitives ship for both; some are queued at one and deferred at the other; some are explicitly out of scope. The discipline is to state which adversary class each primitive defends against.
