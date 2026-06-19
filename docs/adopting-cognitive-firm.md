# Adopting cognitive-firm

This guide is for a person or organization that wants to fork the kernel and
run its own role offices. The public repository should stay generic. Your
organization-specific roles, mandates, project content, private evidence, and
preferences should live in a tenant overlay or a private fork.

If you are still deciding how humans and agents should divide work, start with
[Human-Agent Work](human-agent-work.md). This guide assumes you already want to
adopt the kernel shape and focuses on setup boundaries.

## What You Are Adopting

`cognitive-firm` is a governance kernel. It gives you durable primitives for:

- role offices and mandates;
- human approval and human work sessions;
- agent-to-agent messages and obligation state;
- work items, leases, and scoped resource allocation;
- capability-gated MCP calls;
- notification-channel intents with provider adapters;
- project charters;
- governance-change proposals, approvals, and review packets;
- evidence gaps;
- action attestations and governed-run bundles;
- approved learning events, learning-use receipts, outcome links, and routine
  reviews;
- damage signals;
- forecast-market read models;
- action-impact read models;
- organizational surface reads;
- local kernel service calls for app surfaces;
- userland commands and provenance projections for adopter-built surfaces;
- actor identity and per-action attribution;
- actor memberships for scoped human, agent, or service authority;
- optional leases over mutable resources.

Those primitives serve the invariants in
[Kernel Invariants](kernel-invariants.md): separation, typed authority, human
work as state, machine provenance, accountable closure, and durable learning.

It does not replace your agent runtime, project management system, document
store, or enterprise identity provider. Those are adapters around the kernel.
The built-in daemon is a first-party governed work runtime: it discovers work,
applies mandate/gate policy, dispatches role-bearing agent CLIs and
capability-gated tools, routes human interrupts, and records durable
organization state. External graph runtimes can still own graph replay and
provider-native execution when that is the better fit.

## Boundary Model

Keep three layers separate:

| Layer | Contains | Should you fork it? |
|---|---|---|
| Kernel | Generic protocols, state machines, parsers, tests, CLI modules | Fork only for reusable behavior. |
| Tenant overlay | Your roles, mandates, preferences, charters, evidence policy, project files | Keep private or organization-owned. |
| App surface | Orbit, Telegram, CLI, future Slack/Teams/web apps | Replace or extend as needed. |

Orbit is a useful local dashboard. It is not the durable architecture. The
durable architecture is the typed state in `org/`, the transition log, and the
protocol modules under `src/cognitive_firm/orchestration/`.

Run app surfaces as projections by default. Orbit exposes
`ORBIT_SURFACE_MODE=projection_only` when you want a read-only dashboard and
`ORBIT_SURFACE_MODE=kernel_intents` when you want it to submit typed human
intents such as gate resolution or human-work updates. In `kernel_intents`
mode, Orbit and the Telegram push channel call the kernel service rather than
writing governance files directly.

## Minimum Adoption Path

1. Fork the repository.
2. Read `docs/first-30-minutes.md`.
3. Run `make smoke-public`.
4. Install the package in editable mode inside your virtual environment.
5. Copy the role and mandate templates under `org/`.
6. Create a private tenant overlay with your real roles, mandates, preferences,
   and project charters.
7. Configure `.env` with at least one agent runtime and the notification
   surface you intend to use.
8. Run `scripts/org_role_preflight.py` for each role you intend to activate.
9. Run one dry-run daemon tick before allowing autonomous dispatch.
10. Inspect the organization surface before and after a live task.

Useful commands:

For a first serious review, start with the first three commands: the public
smoke, the on-ramp evidence collector, and the read-only readiness handoff. The
remaining commands are integration surfaces for teams that are already wiring a
tenant, daemon, or service deployment. The command surface exposes the same
sequence as read-only metadata through
`cognitive-firm-userland commands "first serious review"` or directly through
`cognitive-firm-userland operator-path first_review`.

```bash
make smoke-public
make adoption-onramp-packet
make adoption-readiness-packet
pip install -e .
python scripts/org_role_preflight.py --role research_director
python scripts/agent_daemon.py --role research_director --tick-once --dry-run
python -m cognitive_firm.orchestration.org_surface
python -m cognitive_firm.orchestration.org_surface --json
cognitive-firm-kernel-service --host 127.0.0.1 --port 8765
cognitive-firm-userland operator-path first_review
cognitive-firm-userland commands "adoption readiness packet"
```

`make adoption-onramp-packet` runs the fixed no-cost first-review proof set
with timeouts and writes observed JSON outputs, command logs, and
`adoption-readiness-packet.md` under `.cognitive-firm-runs/adoption-onramp/...`.
It is a bounded evidence collector, not a planner or workflow engine. If a
bounded live-agent run or release gate was produced separately, pass it through
`scripts/adoption_onramp_packet.py --result CHECK_ID=path`; the collector cites
the artifact without running that substrate. For `bounded_live_agent_run`, pass
the generated `reports/self-evolving-org-demo.json` report rather than a
clipped stdout summary so the reviewer packet can inspect the v0.4
learning-use, verified context-packet, provenance, and proposal-review counts,
including proposal follow-through that shows whether at least one proposal
reached closed-loop evidence. Those counts must be present and nonzero for the
live-agent row to count as fully reviewable. Missing optional evidence stays
visible as deferred evidence, but a supplied optional artifact that fails its
checks blocks the packet from reporting `ok: true`.

`make adoption-onramp-replay` is the portability check for that same path. It
copies the public repo surface into an isolated worktree, excludes `internal/`,
local run state, virtualenvs, and `.env`, and runs the core on-ramp collector
from the copy. Use it when reviewing whether the on-ramp is clean-clone
replayable rather than dependent on author-local files.

`make adoption-onramp-full-replay` runs the same clean-copy replay with the full
no-cost collector, including adapter-policy preview, formal-provider proof pack,
runtime-adapter proof pack, agent-fleet audit, and field-pilot rows.

`make adoption-readiness-packet` prints a read-only packet. After
`make adoption-onramp-packet`, it re-renders the latest collected on-ramp
packet; before any on-ramp exists, it falls back to the expected first-run proof
paths and records missing checks explicitly instead of pretending the setup is
complete. To mark checks as observed manually, pass JSON outputs to
`scripts/adoption_readiness_packet.py --result CHECK_ID=path`.
For observed first-gated-action and learning-loop outputs, the packet also
embeds a governed-action composition matrix. That matrix checks whether the
proof chain actually carries the expected authority, work, human-work,
attestation, outcome, bundle, context-packet, and learning-use links. A command
can pass while the adoption packet still blocks review if those links are not
present.
Each check row also reports expected, present, and missing evidence fields. A
required check can pass its command expectations but still block review when the
payload is too thin to carry the expected evidence.
The Markdown handoff includes a `Reviewer Path` section with the same first
serious review sequence exposed by the command surface, plus purpose and
`not_a` boundary text so a reviewer can see whether they are looking at the
public gate, the evidence collector, or the readiness handoff without treating
the sequence as a workflow runner.
The same check is available directly through
`cognitive-firm-userland composition-packet --observed-json ... --action-label
...`, which calls the read-only `POST /kernel/governed-action-composition`
route and exits non-zero when required composition links are missing.
`scripts/native_e2e_demo.py --output ...`,
`scripts/kernel_service_smoke.py --output ...`, and
`scripts/learning_loop_walkthrough.py --output ...` are the shortest required
deterministic evidence files for that packet. The kernel-service smoke output is
expected to include provenance follow-through fields showing a closed-loop
service report over outcome, routine-review, learning-event, and learning-use
records; an older thin smoke JSON remains a review blocker. Optional
adoption-wedge evidence can be captured the same way with
`scripts/agent_fleet_audit_demo.py --output ...` and
`scripts/field_pilot_action_impact_demo.py --output ...`; optional proof-pack
evidence can be captured with `scripts/formal_provider_proof_pack.py --output ...`
and `scripts/runtime_adapter_proof_pack.py --output ...`. Optional
adapter-policy evidence can be captured with
`scripts/langgraph_adapter_policy_preview.py --output ...`.

For the smallest overlay shape, inspect `tenants/example/`. It is intentionally
generic and should be copied into a private tenant repo before real use.

For steps 5-6 you can also install the bundled `starter-firm` distro instead of
copying templates by hand. `cognitive-firm-distro install starter-firm --into
./my-firm` lays down a day-one governance loop (principal, lead, analyst,
reviewer) as a transactional git-backed install, verified by `boot_check` and
revertable with `cognitive-firm-distro rollback`. See
[`protocols/distribution.md`](protocols/distribution.md).

## Project Setup

For each project, create a project charter with the required sections:

- Core Question
- Out Of Scope
- End States
- Forecast Type
- Inheritance
- Anchor Proxies

Validate it with:

```bash
python -m cognitive_firm.orchestration.project_charter path/to/project_charter.md
```

The charter is not a full ontology. It is a scope-fidelity surface that tells
roles, reviewers, and forecast agents what object they are operating on and
what would count as drift.

## Human Work

Do not model humans only as approval buttons. If a human must read a restricted
source, make a judgment call, edit a sensitive artifact, talk to another person,
or operate inside a system the agent cannot access, create a human work session.

```bash
python -m cognitive_firm.orchestration.human_work create \
  --requested-by role.manager \
  --human-actor principal \
  --objective "verify restricted source and attach receipt" \
  --work-mode source_check \
  --bottleneck-class access \
  --receipt-required \
  --receipt-type note
```

For non-digitized work, record observability and receipt honestly. If the
kernel cannot observe the work, it should store a bounded claim, a confidence
level, and whether the item should be sampled for review. It should not pretend
that private conversations or offline reading are directly observable.

For actual co-work, append interaction events rather than burying the handoff
in chat:

```bash
python -m cognitive_firm.orchestration.human_work interaction hws_... \
  --actor principal \
  --event-type offline_call \
  --surface offline \
  --summary "Source owner confirmed the document is current." \
  --artifact-ref crm/source-owner-note \
  --agent-followup-required
```

This gives the role office a durable handle for what happened, which surface it
happened on, what evidence exists, and whether the agent must act next.

## Evidence Gaps

When a role finds a missing source, missing comparator, or missing adversarial
check, create an evidence gap instead of burying it in prose.

```bash
python -m cognitive_firm.orchestration.evidence_gaps create \
  --gap-type missing_source \
  --target "main claim" \
  --description "Need a primary source before continuing." \
  --severity blocking \
  --producer role.reviewer
```

Blocking evidence gaps are surfaced by work discovery and the org surface. They
are learning carriers, not comments.

## Organization Surface

The org surface is a read model over current kernel state. It summarizes:

- blocking evidence gaps;
- open evidence gaps;
- active and waiting human work sessions;
- blocked A2A obligations;
- recent damage signals;
- invalid project charters;
- forecast-market and action-impact summary state;
- strategy-review findings;
- active and failed long-running runs.

Use it before starting material work and during reviews:

```bash
python -m cognitive_firm.orchestration.org_surface
```

Applications can render the same state, but the surface is deliberately exposed
as a CLI/module so a human, a role office, or another app can consume it.

## Kernel Service, Actors, And Leases

Use the kernel service when an app surface should submit typed requests without
importing Python modules directly:

```bash
cognitive-firm-kernel-service --host 127.0.0.1 --port 8765
```

The default mode is appropriate for local T1 use. For a small team or service
pilot, move in this order:

```bash
cognitive-firm-kernel-service --enforce-registered-actors
cognitive-firm-kernel-service --enforce-registered-actors --enforce-actor-membership
cognitive-firm-kernel-service --enforce-registered-actors --require-leases
```

Actor identity is first-party because the kernel must know which actor, role,
surface, and session caused a mutation. Authentication remains an adapter:

```bash
export COGNITIVE_FIRM_KERNEL_TOKEN=...
export COGNITIVE_FIRM_KERNEL_ACTOR_ID=human.alice
export COGNITIVE_FIRM_KERNEL_ACTOR_KIND=human
cognitive-firm-kernel-service --require-token
```

The built-in bearer-token adapter is for local and conformance use. A tenant
that needs SSO should implement OIDC, SAML, mTLS, or gateway authentication as
an identity-provider adapter that returns authenticated subject facts. The
kernel still decides authority through actor records, mandates, leases, and
accountability policy.

For directory-driven setup, compile IdP/HRIS/SCIM facts into kernel records
instead of letting the IdP own role authority:

```bash
cognitive-firm-identity-provisioning provisioning-plan.json
```

That plan creates actor identities and actor memberships idempotently. Use the
tenant-isolation guard in setup scripts or app surfaces when applying files into
tenant overlays. It checks that actor tenant scope and overlay paths match; hard
tenant isolation across separate authority domains remains a deployment
architecture concern.

## Learning Transitions

Use the learning-transition compiler when existing carriers should be reviewed
for possible changes to future work:

```bash
python -m cognitive_firm.orchestration.learning_transition_compiler --json
```

Compiler output is advisory. After review, record an approved learning event
when the organization accepts a durable behavior change:

```bash
python -m cognitive_firm.orchestration.learning_events create \
  --learning-unit-kind routine_change \
  --decision-use "require independent evidence before retrying this branch" \
  --future-application-cue "same failure mode repeats across reviewed runs" \
  --approved-by role.principal \
  --approval-ref review/2026-05-19-1 \
  --source-carrier-ref forecast/c1 \
  --source-carrier-ref action-impact/a1 \
  --before-state "branch retries by default" \
  --after-state "branch requires independent evidence before retry"
```

The event is the durable learning record. The tenant still owns the actual
route, mandate, charter, threshold, routine, or policy-adapter change.

Before a role starts related future work, inspect the service projection
instead of searching old conversations:

```bash
cognitive-firm-userland work-context \
  --assigned-to role.manager \
  --cue "same failure mode repeats across reviewed runs"
```

`work-context` returns a read-only context packet over matching approved
learning events, outcome links, routine-review state, and current work
candidates. After the work, record whether the learning was applied, ignored,
or deferred:

```bash
cognitive-firm-userland learning-use <learning_event_id> \
  --role role.manager \
  --cue "same failure mode repeats across reviewed runs" \
  --outcome applied \
  --context-packet-ref <ctx_id> \
  --work-ref work_item:<id>
```

This keeps learning observable without turning the kernel into a hidden memory
store or workflow engine.

For "why did this happen?" or "what did this affect?" views, use the
projection routes instead of rebuilding state from raw JSONL:

```bash
cognitive-firm-userland timeline --ref <object_or_artifact_ref>
cognitive-firm-userland graph --ref <object_or_artifact_ref>
```

The graph is a read-only event/ref projection over the same canonical records
as the timeline. It is intended for adopter-built dashboards and lineage views,
not as a workflow database.

To inspect whether A2H work is repeatedly bottlenecking on the same role and
human-work class, use the observer-only pressure view:

```bash
cognitive-firm-userland human-pressure --agent-counterparty-role role.manager --tenant-id tenant-a
cognitive-firm-userland learning-candidates --source human_work
```

Treat these rows as review signals. Access, labor, or cognition pressure may
justify tooling or mandate review; taste, safety, relationship, and authority
pressure often means the human boundary is doing useful work. In multi-tenant
logs, apply `tenant_id` / `project_id` selectors so one tenant's human-work
pressure does not shape another tenant's review.
Use the candidate command when the whole-firm pressure groups should enter a
review queue; it keeps source refs back to human-work sessions and does not
automate, reroute, or close the work.
If a candidate should become a governance proposal, use
`cognitive-firm-userland proposal-from-candidate <candidate_id> --target-ref <ref>`.
The command preserves candidate evidence but still requires target, risk,
rollback, and invariant evidence; incomplete requests are stored as blocked
proposals.

## Governance Changes

Use governance change proposals when a role or agent suggests modifying the
kernel's own governance surface: mandates, role definitions, route policy,
capability policy, gate policy, learning policy, or tenant policy.

```bash
python -m cognitive_firm.orchestration.governance_changes propose \
  --change-kind mandate_change \
  --title "tighten reviewer write scope" \
  --proposed-by role.research_director \
  --target-ref org/mandates/reviewer_mandate.md \
  --rationale "repeated scope drift requires narrower defaults" \
  --invariant-check-json '{"invariant":"principal_independence","status":"pass","rationale":"principal approval remains required"}' \
  --invariant-check-json '{"invariant":"deterministic_enforcement_floor","status":"pass","rationale":"the write-scope guard still computes diffs"}' \
  --invariant-check-json '{"invariant":"fail_closed_behavior","status":"pass","rationale":"missing approval blocks execution"}' \
  --invariant-check-json '{"invariant":"write_scope_preserved","status":"pass","rationale":"the role cannot edit its own mandate"}' \
  --invariant-check-json '{"invariant":"tenant_boundary_preserved","status":"pass","rationale":"no tenant policy becomes a kernel default"}'
```

The proposal becomes `review_ready` only if all required invariants pass. It is
still just a proposal. The tenant or principal must approve and apply the
referenced change through the appropriate authority path.
Use `cognitive-firm-userland proposal-packet <proposal_id>` when a reviewer
needs the compact "why this proposal, what evidence, what happened after" view.
The packet includes a provenance-derived follow-through status, so a proposal
can show as proposal-only, decision observed, or closed-loop evidence observed
without creating a workflow runner or new lifecycle.

## Long-Running Work

Use run checkpoints when a role office starts work that should be resumable or
inspectable across agent invocations:

```bash
python -m cognitive_firm.orchestration.run_checkpoints start \
  --owner-role role.manager \
  --objective "sync reviewed external state" \
  --idempotency-key sync-demo
```

The interface appends `run.*` events to the canonical transition log and
derives current state by replay. It is not a second durable ledger.

## Runtime Adapters

The daemon projects its own dispatched work into the run-checkpoint surface as
`cognitive_firm_daemon` runtime events. If your tenant uses LangGraph, CrewAI,
OpenAI Agents SDK, Google ADK, Microsoft Agent Framework, AutoGen, Letta, or a
custom runtime, keep that runtime in the app layer and emit the same event
shape:

```bash
python -m cognitive_firm.orchestration.runtime_adapters \
  --event-json '{
    "runtime_name": "langgraph",
    "external_run_id": "thread-123",
    "kind": "started",
    "owner_role": "role.research_director",
    "actor": "role.research_director",
    "objective": "run project-scoped evidence graph"
  }'
```

Use a graph runtime when your application needs node replay, graph-state
persistence, streaming, or framework-native tracing. Use the cognitive-firm
daemon when the work unit is an organizational role-office tick governed by
mandates, gates, project charters, and human notification policy. Both can feed
the same organization surface.

## What To Customize

Customize:

- role names and mandate prose;
- budget caps and allowed paths;
- MCP capability bindings;
- project charter content and tenant validators;
- evidence policy and sourcing workflow;
- notification surfaces;
- app UI.

Do not customize by hard-coding project semantics into kernel modules. Add
tenant adapters or validators around the generic primitives.

## Forecast and Impact Adapters

If your organization already has a forecast market, prediction ledger, yield
ledger, or P&L attribution system, keep that implementation in the tenant
overlay. Expose a summary/read model to the kernel instead of copying the
tenant engine into core.

Useful commands:

```bash
python -m cognitive_firm.orchestration.forecast_market \
  --summary-json path/to/forecast_market/global_health.json
python -m cognitive_firm.orchestration.action_impact \
  --summary-json path/to/action_impact_summary.json
python -m cognitive_firm.orchestration.org_surface \
  --forecast-market-summary path/to/forecast_market/global_health.json \
  --action-impact-summary path/to/action_impact_summary.json
```

Bandit or mini-RL policies belong behind tenant adapters. Before a tenant lets
one affect live routing, it should be evaluated offline against logged
baselines, counterfactuals, decision changes, costs, and externalities.

## App And External-System Integration

Do not use one integration mechanism for every boundary. Use:

- kernel service or Python CLI/module calls for app surfaces;
- MCP for governed external-system actions;
- runtime adapters for external agent/graph runtimes;
- state backends for kernel event/artifact storage;
- notification-channel adapters for human attention;
- identity-provider adapters for request authentication.
- identity provisioning for directory-to-actor setup.

For Linear or another external system, first write a deterministic projection
and capability policy. Then add a live smoke outside `make smoke-public`:

```bash
export LINEAR_API_KEY=...
make mcp-linear-live-smoke
```

Live external-system smoke should stay optional because it uses network access,
tenant credentials, and vendor state.

## Source Connectors And Storage

Keep connector families separate:

- `state_backend`: kernel event streams and artifacts, such as filesystem or
  SQLite-backed state;
- `enterprise_system`: external business systems reached through MCP, such as
  issue trackers, CRMs, ERPs, or document systems;
- `runtime`: graph, crew, chat, or custom agent runtimes that emit run events;
- `notification`: attention surfaces such as Telegram or a null/local channel.

Do not route ERP or CRM data through the state backend just because both are
"sources." The state backend stores kernel state. MCP and other enterprise
connectors reach external systems under explicit capabilities.

## Learning Transition Candidates

After inspecting the organization surface, compile candidate learning
transitions:

```bash
python -m cognitive_firm.orchestration.learning_transition_compiler --json
```

Candidates are review objects. A tenant may convert one into a mandate review,
evidence gap, human-work session, forecast contract, source repair, or role
review, but the compiler does not apply the transition.

## Accountability And Local Reviews

Use the accountability summary when you need a follow-up view by owner,
project, review status, due date, and externality:

```bash
python -m cognitive_firm.orchestration.accountability --json
```

For significant primitive, mandate, charter, strategy, or tenant-policy
changes, keep interdisciplinary or synthetic-review artifacts under the local
`reviews/` workspace. That directory is gitignored by default. Promote only the
public-safe conclusion into docs or tenant policy.

## Notification Channels

The kernel publishes notification intents through
`cognitive_firm.notifications.channels`. Telegram is the default provider, but
the provider is replaceable:

```bash
COGNITIVE_FIRM_NOTIFICATION_CHANNEL=telegram python scripts/agent_daemon.py ...
COGNITIVE_FIRM_NOTIFICATION_CHANNEL=null python scripts/agent_daemon.py ...
```

Provider-specific inbound behavior, such as Telegram callback buttons, remains
in the provider adapter. Kernel code should call `push_notification` or
`send_notification`, not provider-specific implementation details for ordinary alerts.

## Operating Discipline

Before work:

- read the mandate for the active role;
- inspect the org surface;
- check for blocking evidence gaps and human work sessions;
- check forecast-market score debt and action-impact review items when those
  adapters are configured;
- check damage signals;
- verify the project charter when work is project-scoped.

After work:

- close or update the relevant obligation, evidence gap, or human work session;
- record forecast decision-use or action-impact rows when a forecast or
  measured intervention changed what happened next;
- attach artifacts by reference;
- emit a damage signal if an invariant was violated;
- update a mandate or charter only when behavior should change for future runs.

The kernel compounds only when findings become durable state transitions.
