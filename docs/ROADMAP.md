# Roadmap

This roadmap lists public-kernel work that is useful across tenants. It avoids
tenant-specific research policy, scoring systems, and optimizer rules.

## Public Roadmap Principles

- Keep the kernel small: reusable authority, evidence, human-work,
  accountability, and learning mechanisms belong in the public kernel; tenant
  strategy and scoring policy do not.
- Treat agent runtimes as peers, not dependencies. Runtime adapters should
  project lifecycle events into the kernel without importing framework-specific
  execution semantics into durable organization state.
- Prefer conformance fixtures over broad claims. A feature is public-grade when
  it has an executable example, an invariant check, and a failure case.
- Make adoption measurable. The public validation path is one bounded field
  pilot with baseline metrics, not a generic claim that governance is better.
- Keep human burden visible. Governance should reduce hidden coordination
  costs, not merely move them into approval queues.

## Current Public-Kernel Baseline

- Filesystem T1 kernel with role offices, mandates, A2A, H2A, MCP outbox,
  project charters, evidence gaps, human work sessions, forecast/action-impact
  read models, organization surface, intelligence-source coverage,
  learning-transition candidates, approved learning events, governance-change proposals, runtime adapters, state
  backends, action attestations, audit-integrity manifests, and accountability
  cases.
- Local kernel service boundary with first-party actor identity, actor
  membership, identity provider adapter shape, and optional resource leases.
- Production layer: typed operating-unit contracts and a durable work-item
  queue with lease-fenced claims, retries, dead letters, bounded exits, and an
  operating-unit health dashboard. Operating units can annotate worker roles
  with coarse worker classes and fuller worker archetypes from the shared
  worker taxonomy; these annotations explain capability/fungibility/state
  shape but do not grant authority. Accountability cases, actor identities,
  actor memberships, human-work sessions, leases, operating units, policy decisions,
  residual-right assignments, residual decisions, governance changes, evidence
  gaps, action attestations, and work items project into the common resource
  envelope for adapter/dashboard compatibility while preserving their JSONL
  rows and kernel events as canonical state.
- Durable-learning layer: outcome links (did an approved change improve a
  measured outcome?), routine reviews (scheduled review and accountable
  retirement of stale routines), governed resource allocation across operating
  units, and residual decision-rights records for incomplete-mandate situations.
- Pre-work learning context projection: `GET /kernel/work-discovery` returns
  matching approved learning events joined to outcome links, routine-review
  state, and work-discovery candidates without recording encounter telemetry or
  applying a route change. It includes a projection-only `context_packet`
  digest over the exact refs/query basis so later work can cite what context was
  available. `cognitive-firm-userland work-context` makes that projection
  visible in the terminal userland, and `cognitive-firm-userland learning-use`
  records the later encounter/applied/ignored/deferred receipt through the
  canonical service route. `verify_learning_event_context_packet_use(...)`
  gives scripts/adapters the same read-only packet-integrity and
  learning-event-basis check without replaying logs or authorizing work.
  `GET /kernel/learning-events/{id}/loop` and `cognitive-firm-userland
  learning-loop` join one approved learning unit to its context-packet refs,
  encounters, outcome links, routine reviews, overdue reviews, and evidence
  refs as a read-only compounding-loop view.
- Provenance timeline/report projection: `GET /kernel/provenance-timeline`
  provides a read-only operator view over matching run/checkpoint events,
  action attestations, human-work sessions, governance proposals and approvals,
  outcome links, routine reviews, approved learning events, and learning-use
  receipts. `GET /kernel/provenance-graph` exposes the same selected records
  as projection-only event/ref nodes. `GET /kernel/provenance-report` packages
  the selected provenance into a portable reviewer handoff with coverage gaps,
  caveats, review questions, high-signal refs, a bounded timeline excerpt, and
  Markdown. These are readable adoption surfaces, not workflow engines.
  `cognitive-firm-userland timeline` / `graph` / `provenance-report` carry the
  same projections into the terminal userland, and Orbit's
  `ProvenanceTimelinePane` is a first-party read-only visualization over the
  same abstract service route.
- Proposal UX baseline: `GET /kernel/governance-change-template` returns a
  service-owned request skeleton for evidence-complete proposals, and
  `cognitive-firm-userland proposal <id>` renders evidence sufficiency,
  rollback, prediction, and invariant checks for one proposal without making
  the reviewer inspect raw JSON.
  `GET /kernel/governance-changes/{id}/review-packet` and
  `cognitive-firm-userland proposal-packet` package those facts with evidence
  refs, invariant rows, selected provenance, review questions, and Markdown for
  a portable reviewer handoff. `GET /kernel/governance-changes?view=review`
  is the read-only proposal-review projection for first-party and
  adopter-built surfaces: review state, evidence status, missing evidence,
  invariant gaps, evidence counts, and the canonical decision route.
- Public verification commands: `make smoke-public`, `make smoke-docker`, and
  the Python test suite.
- Backup/restore smoke for a minimal T1 organization snapshot and restored
  organization-surface read.
- Local audit commands: `make audit-manifest` and `make audit-verify`.
- Optional Linear MCP live smoke command for credentialed external-system
  validation.
- Deterministic app-integration conformance smoke for Linear MCP projection,
  GitHub/Linear/Stripe webhook signature mapping, and signed inbound-event
  replay/idempotency behavior.
- App-service integration smoke covering actor identity, actor membership,
  lease acquisition, service mutation, and organization-surface projection.
- Executable source-coverage and learning-loop walkthroughs included in
  `make smoke-public`.
- LangGraph-style governance demo included in `make smoke-public`: runtime
  lifecycle projection, interrupt-to-A2H human work, action attestation, and a
  governed-run attestation bundle through kernel-service routes.
- Governance failure benchmark included in `make smoke-public`: deterministic
  fixtures for forbidden-path dispatch, failed provenance, missing human
  receipts, unresolved outcome verdicts, unclosed accountability cases, and
  formal checker refutation. It also includes a local-reward downgrade fixture
  and a weakly evidenced self-modification fixture: a candidate policy with
  positive reward delta is blocked because negative externality and human-review
  burden exceed guardrails, and a governance-change proposal with passing
  invariant claims is blocked because structural review evidence is missing.
- Governed-run attestation bundle CLI:
  `cognitive-firm-governed-run-bundle <run_id>` exports run checkpoints,
  action attestations, formal verifications, human-work sessions, linked
  production work items, outcome links, accountability cases, linked leases,
  governance approval events, derived evidence hashes, observability refs,
  authority snapshot, caveats, and conservative verdict as one JSON packet. The
  same CLI validates existing bundle JSON against the v1 interchange schema and
  recomputes its digest.
- Action-impact policy reports: `cognitive-firm-action-impact evaluate-policy`
  performs conservative offline replay over logged action-impact rows, and
  `build-promotion-packet` packages a promotable/advisory candidate with
  guardrail summary, authority-diff refs, optional formal-verification refs,
  and a draft governance-change payload. The packet is review evidence; it
  does not mutate live policy. The kernel service can project a review-ready
  packet into a `route_policy_change` governance proposal while still refusing
  to approve governance, apply the policy, choose actions, or execute a
  runtime.
- Decision-log replay demo included in `make smoke-public`: deterministic
  action-impact logs are replayed into a business-function candidate proposal,
  conservative offline evaluation, governance review packet, run checkpoints,
  verified action attestation, outcome verdict, and governed-run attestation
  bundle. The fixture shows both a review-ready route and a high-reward route
  rejected because externality and review-burden guardrails fail.
- Field-pilot action-impact demo included in `make smoke-public`: a pilot
  folder can carry `action-impact-summary.json`, pass strict pilot validation,
  and produce a policy-promotion packet from measured pilot rows.
- Formal-provider bundle demo included in `make smoke-public`: a signed
  LeanMill-style provider payload is ingested through the kernel service and
  becomes clean governed-run evidence when org trust policy, signature
  verification, checker evidence, and faithfulness refs are present; a
  missing-evidence provider row keeps the bundle incomplete.
- Formal-provider proof pack: `make formal-provider-proof-pack` validates the
  bundled LeanMill manifest/config/trust-policy declarations and packages the
  signed-provider and missing-evidence bundle paths as
  `formal_provider_proof_pack.v1`. It proves provider adoption boundaries
  without running LeanMill, installing provider code, approving trust, or
  turning certificate success into mandate truth.
- Runtime adapter-policy package: the bundled `langgraph-runtime-adapter`
  overlay installs governance-side adapter and conformance declarations for a
  LangGraph-style runtime. It does not install executable adapter code and
  should preview as authority-neutral before governed install.
  `make langgraph-adapter-policy-preview` now proves that preview against a
  temporary starter org and validates the manifest/conformance declaration
  without installing LangGraph, applying the overlay, or writing a governance
  proposal.
- Runtime adapter proof pack: `make runtime-adapter-proof-pack` validates the
  bundled LangGraph adapter manifest/config pair and compares the native kernel
  demo with the LangGraph-style runtime demo against one governed-run summary
  contract. It proves substrate-equivalent governance evidence while keeping
  graph execution, checkpoint replay, and resume semantics outside the kernel.
- Authority-domain routing helper: `authority_resolver_from_org(...)` connects
  scoped attention signals to authority domains plus active actor memberships,
  preserving the role even when no active actor currently holds it.
- Package metadata smoke included in `make smoke-public`; it builds and
  inspects a local wheel when the build backend from `requirements.txt` is
  installed.
- Mid-level adoption packaging: abstraction map, resource/event catalog,
  blueprint index, and docs-surface check included in `make smoke-public`.
- Adoption readiness packet: `make adoption-readiness-packet` re-renders the
  latest on-ramp reviewer handoff when present, while
  `scripts/adoption_readiness_packet.py` can also package manually supplied
  proof outputs from existing smokes/demos. Missing and failed checks stay
  explicit. It does not run commands, approve release readiness, or write
  kernel state. Observed first-gated-action and learning-loop outputs are also
  checked through `governed_action_composition_packet.v1`, so a green command
  cannot hide a disconnected authority/work/human-work/attestation/outcome/
  bundle/learning-use proof chain. Check rows also report expected,
  present, and missing evidence fields; required checks with thin payloads
  remain review blockers even when their command expectations pass. The
  shortest deterministic proof scripts support `--output` so adopters can
  capture first-gated-action, kernel-service-smoke, learning-loop, agent-fleet,
  field-pilot, adapter-policy preview, formal-provider, and runtime-adapter
  evidence without shell redirection.
- Adoption on-ramp collector: `make adoption-onramp-packet` runs a fixed
  no-cost evidence set with per-command timeouts, captures JSON outputs and
  command logs under `.cognitive-firm-runs/adoption-onramp/...`, then renders
  the same adoption-readiness packet and Markdown handoff. The fixed set
  includes the adapter-policy preview row before the runtime-adapter proof
  pack, so package authority is checked before runtime evidence is compared. It
  is an operator harness for first review, not a configurable workflow runner
  or release approval path. Externally produced live-agent or release-gate JSON
  can be injected with `--result CHECK_ID=path`, preserving the boundary
  between evidence collection and runtime execution.
- Full clean-copy adoption replay: `make adoption-onramp-full-replay` reruns
  the default no-cost collector from an isolated public copy, excluding
  `internal/`, local run state, virtualenvs, and `.env`. It proves the full
  on-ramp packet is clone-replayable without adding a workflow engine or
  external-agent runner.
- Agent-fleet audit wedge: `make agent-fleet-review-packet` writes the
  persistent local/subscription agent invocation receipt, governed-run bundle,
  operator-burden field-pilot summary, and Markdown runbook under
  `.cognitive-firm-runs/agent-fleet-audit`. It is the one-command review path
  for "what did this agent do, under which role authority, with what receipt?"
  and does not execute an external runtime.
- Field-pilot starter pack with scope, baseline, metrics, and learning-event
  summary templates.
- Obsidian-compatible docs and a minimal example-tenant overlay.
- Distribution layer: versioned distro/overlay packages, a package registry,
  and a transactional git-backed installer with kernel-version gating and
  governance-graph `boot_check` verification. Installs commit and tag the
  target (`install/<pkg>/<version>`); `rollback` undoes a bad install (clean
  git reset, or a compensating git revert if the org has run). The
  `cognitive-firm-distro` CLI ships `list / show / install / install-overlay /
  verify / upgrade / rollback / uninstall / lint`, and the bundled
  `starter-firm` distro ships a
  day-one governance loop in the wheel.
  - Overlay composition: a component carries an `op` —
    `add` / `replace` / `patch` (RFC 7386 JSON Merge Patch).
  - Governed overlay install: installing an overlay onto a *running*
    org files a governance-change proposal whose `expected_behavior_change` is
    a rendered authority-diff; an overlay that expands a role's write scope (or
    changes authority uninterpretably) fails a required invariant and is
    blocked — a package may not widen authority. An approved install attests a
    `package.install_approved` event.
  - Remote packages: `install <git-url>` fetches a package SHA-pinned,
    recording a content-hashed `.cognitive-firm/packages.lock` that catches a
    moved tag or a force-push.
  - Distro inheritance: a manifest may `extends` a base distro;
    installing it installs the base first, then composes the extender (one
    level).
  - Authoring loop: `lint`, `install --dry-run`,
    `preview-overlay --json`, and a package template at
    `docs/templates/package/`. `preview-overlay` stages an overlay against a
    copy of an org, reports the file plan plus authority diff, writes no
    governance proposal, and exits nonzero when the overlay widens or
    ambiguously changes authority.
- Userland layer (`src/cognitive_firm/userland/`): the operator- and
  member-human-facing layer over the kernel, with five layers — L0 enrollment,
  L1 attention router, L2 action (operator `needs-me` queue, member-human work
  inbox), L3 inspection/surface-policy, L4 vocabulary spine. Exposed by
  kernel-service routes including `GET /kernel/attention/{actor_id}`,
  `GET /kernel/work-inbox/{actor_id}`, `GET /kernel/work-discovery`,
  `GET /kernel/vocabulary`, `GET /kernel/command-surface`, and read-only
  proof-chain checks such as `POST /kernel/governed-action-composition`. The
  `cognitive-firm-userland` CLI ships `needs-me`, `inbox`, `vocabulary`,
  `commands`, `status`, `resolve`, `work-context`,
  `composition-packet`, `human-pressure`, `learning-candidates`,
  `lease-acquire`, `leases`, `lease-release`, `receipt`, `learning-use`,
  `learning-loop`, `timeline`, `graph`, `provenance-report`,
  decision-aggregation evidence verbs `decision-profiles` /
  `decision-cases` / `decision-open` / `decision-position` /
  `decision-compute` / `decision-route-escalation`, and the governed-install
  human-review verbs `proposals` /
  `proposal` / `proposal-packet` / `proposal-template` /
  `proposal-from-candidate` / `approve` / `decline`. These commands
  sit over service routes including `GET /kernel/governance-change-template`,
  `GET /kernel/governance-changes`, `GET /kernel/command-surface`,
  `GET /kernel/decision-procedure-profiles`,
  `GET /kernel/decision-aggregation-cases`,
  `GET /kernel/leases`,
  `GET /kernel/provenance-timeline`,
  `GET /kernel/provenance-graph`, `GET /kernel/provenance-report`,
  `GET /kernel/human-work-pressure`, `GET /kernel/work-discovery`,
  `POST /kernel/leases`, `POST /kernel/leases/{id}/release`,
  `POST /kernel/decision-aggregation-cases`,
  `POST /kernel/decision-aggregation-cases/{id}/positions`,
  `POST /kernel/decision-aggregation-cases/{id}/compute`,
  `POST /kernel/decision-aggregation-cases/{id}/route-escalation`,
  `POST /kernel/learning-event-encounters`, and
  `POST /kernel/governance-changes/{id}/decision`. Orbit ships
  first-party projection panes for the operator attention queue, member-human
  work inbox, and read-only provenance timeline, but the reusable contract is
  the kernel service/userland boundary so adopters can build their own
  dashboards over the same routes.
- L3 surface-policy guard: the kernel service refuses a mutation from a
  `projection_only` surface (`KernelServiceConfig.surface_write_modes`).
- Governance-change evidence sufficiency gate: self-modification proposals are
  blocked unless they cite source refs, expected behavior change, risk summary,
  rollback plan, and evidence refs for every passing required invariant.
- Extension schemas: packages register JSON Schemas to validate custom
  primitive payload types, wired into `enqueue_work_item`. Open by default — a
  `kind` with no registered schema is unconstrained.

## Lean T2 Seams

The current lean T2 seams are deliberately small. They show how the kernel can
move beyond trusted single-authority files without claiming full enterprise
governance:

- SQLite event source as the lean state-backend migration target.
- Kernel event envelope embedded in transition rows.
- Runtime adapter conformance fixtures for framework-neutral lifecycle events.
- Runtime interrupt-to-human-work bridge for external HITL pauses, with a
  LangGraph-style executable demo.
- Offline business-function policy proposer over action-impact rows. It emits a
  candidate context-to-arm map and diagnostics only; evaluation and promotion
  still go through the action-impact and governance-change surfaces.
- OpenTelemetry GenAI-shaped projection for run/checkpoint observability.
- Policy-decision record shape for bounded local allow/deny checks.
- State-surface registration gate for new JSONL-backed primitives.
- Action attestations for machine-side provenance.
- Governed-run attestation bundle over run checkpoints, action attestations,
  formal verifications, human-work sessions, linked production work items,
  outcome links, accountability cases, linked leases, governance approvals,
  derived evidence hashes, authority snapshots, and observability refs.
- Audit-integrity manifests over JSONL logs, with optional HMAC verification.
- Accountability cases for authority, recourse, residual-risk acceptance, and
  closure evidence.
- Kernel service boundary over the same Python primitives used by CLI and app
  surfaces.
- Actor identity records for first-party actor context over external identity
  providers.
- Actor membership records for scoped role authority across multiple human,
  agent, or service actors in one deployment.
- Authority-domain records for scoped authority resolution across tenants,
  projects, operating units, resource classes, and decision classes, with
  T1-compatible boot checks and attention routing.
- Identity provisioning seam for directory/setup-script facts to create actor
  identities and memberships without making the kernel an IAM admin product.
- Tenant-scope guard for local overlay/app path checks.
- Identity provider adapter interface plus a static bearer-token adapter for
  local and conformance use.
- Trusted-header identity provider adapter for gateway-verified OIDC/SAML/mTLS
  deployments.
- Resource leases for time-bounded mutation control.
- SQLite transactional mutation backend for service-backed lease acquisition,
  release, and guarded mutation-event append.
- Optional Postgres transactional mutation backend preserving the same fenced
  mutation contract when deployments provide `psycopg`.
- A2H work coordination over human work sessions, including follow-up, missing
  receipt, waiting-on-human, and pressure read models.
- A2H command-path conformance fixture: `make a2h-command-conformance` creates
  an agent-requested human-work session through the CLI, verifies integration
  fails before a required receipt exists, then integrates successfully with the
  receipt and resource projection.
- Orbit and Telegram mutation actions route through the kernel service for gate
  resolution, directives, controls, chat, human-work state, and role
  utilization config.
- EU AI Act deploy gate for explicit tenant opt-in mapping checks.

What this MVP is good for:

- controlled pilots;
- small teams that need stronger audit discipline than git alone;
- adopters evaluating whether the kernel primitives fit their organization.

What this MVP is not:

- a complete federated identity deployment;
- full enterprise RBAC/SSO administration;
- external timestamp/transparency-log proof references over audit manifests;
- legal non-repudiation;
- multi-tenant isolation across separate authority domains;
- production compliance certification.

## Next Public-Grade Pull-Forwards

Current focus: make the self-evolving organization demo kernel-native by
feeding live runtime evidence through service routes, then routing structural
changes through existing proposal, approval, learning, outcome, review,
bundle, proof, and git receipts.
The demo now routes accepted structural changes through capability signals,
learning-transition candidates, candidate-promoted governance proposals,
approval, mutation, learning, proof, and git receipts. It also includes a
blocked unsafe structural proposal fixture so the same path demonstrates
rejection without mutation.

1. Resource/event model consolidation: keep the resource envelope, kernel event
   envelope, transition rows, JSONL state rows, and mutation events aligned
   under one documented compatibility contract. Accountability cases, actor
   identities, actor memberships, human-work sessions, leases, operating units,
   policy decisions, residual-right assignments, residual decisions,
   governance changes, evidence gaps, action attestations, and work items now
   expose resource-envelope projections; next apply the same discipline only
   where a projection adds real adapter value.
2. Public docs consistency pass: keep generated indexes, README claims, and T2
   language aligned with shipped tests.
3. First-party protocol conformance: keep H2A, A2A, and A2H visibly stronger
   than prose patterns. A2H receipt-before-integration now has a command-path
   fixture, and the same fixture now proves the ready-for-agent follow-up view
   before integration. Saga compensation now has a command-path fixture that
   proves terminal-failure-only compensation, active-saga visibility, and
   clearing after compensation fulfillment. The A2A/H2A seam now has a
   service/CLI fixture that proves a blocked A2A obligation can be linked to
   bounded A2H human work and closed only after receipt-backed integration.
   Runtime interrupts now have a command-path fixture proving the CLI adapter
   rejects pre-start checkpoints and incomplete interrupts, projects a paused
   run, creates one receipt-required A2H request, preserves the resume ref, and
   reuses the human-work session on interrupt replay. Standalone A2A
   delegation/handoff now also has a service-route fixture proving fail-closed
   unlinked edges, envelope/obligation separation, ordered lifecycle, and
   thread/depth guards without route synthesis or scheduling. Next expand only
   where a real adapter boundary needs a conformance trace.
4. External-connector conformance fixtures: add capability-policy examples for
   read and write tools beyond the shipped Linear/GitHub/Stripe fixtures.
5. Runtime-adapter proof packs beyond the shipped LangGraph-style demo: one
   minimal runnable example each for multi-agent orchestration,
   stateful-agent memory, and external workflow engines, all emitting the same
   framework-neutral lifecycle events.
6. Adapter manifest and package boundary: adapter packs should install
   governance policy, schemas, trusted-provider config, and adapter manifests
   while executable adapter code remains installed by its normal runtime path.
7. Portable attestation bundle hardening: the current governed-run bundle
   joins run checkpoints, action attestations, formal verifications, human-work
   sessions, linked production work items, outcome links, accountability cases,
   linked leases, referenced governance approvals, role/mandate authority
   snapshots when local files are present, derived contract/input-state hashes,
   and observability refs from checkpoints and action attestations.
   The v1 interchange schema and digest validator are shipped. Next harden the
   bundle with external timestamp/transparency refs where adopters need them.
8. Formal-verification providers: the provider-agnostic primitive now records
   Lean/SMT/Isabelle/Coq/Alloy/TLA+/other certificate rows. Provider trust is
   org policy; the bundled `leanmill-formal-verification` overlay installs the
   LeanMill policy without making LeanMill a hard package dependency. Next step
   is the LeanMill-side adapter that emits this record for policy, schema,
   contract, evidence-chain, workflow-safety, and math checks. The no-cost
   formal-provider bundle demo proves the cognitive-firm side of the boundary.
9. Userland completion: enough Orbit/userland surface area for an adopter to
   run the starter firm without reading the protocol catalog.
10. Enterprise multi-authority path: the first scoped authority-domain
    primitive is shipped for tenant, project, operating-unit, resource-class,
    and decision-class routing. Remaining work: enterprise admin UX,
    provisioning examples, richer escalation-chain validation per domain,
    tenant isolation hardening, and app surfaces that make domain routing easy
    to inspect.
11. Terminology migration: keep backwards-compatible `principal` file/role
    aliases for existing installs, but move public enterprise language toward
    `authority role`, `accountable actor`, `member human`, and `installation
    administrator` where those terms are more precise. Do not mechanically
    rename code until compatibility aliases and migration tests exist.

## Minimum Lovable v0.4

Keep v0.4 narrower than the full memory/context wishlist. The release should
make one governed learning loop visible and useful enough for a real operator:

1. **Learning Loop v1:** role-context projection at work-discovery time plus
   auditable learning-use receipts. The current `context_packet` digest answers
   "what context was available?"; encounter discipline answers "how was it
   used?"; `learning-loop` answers "did this lesson get used, measured, and
   scheduled for review?"
2. **Provenance / Timeline View:** a readable projection from run checkpoints
   through human work, action attestations, proposals, decisions, outcome links,
   routine reviews, and learning events. This should answer "why did we decide
   X and what happened after?" without making operators inspect raw JSONL.
   Current baseline: service timeline route, projection-only graph route,
   portable provenance-report route, CLI timeline/graph/report views, and a
   read-only Orbit example pane over the same projection and report-derived
   follow-through status.
3. **Proposal UX Improvements:** templates, pending-review visibility, and
   clearer authority/evidence diffs over existing governance-change routes.
   Current terminal baseline: proposal list/detail/packet/template commands
   over the canonical service routes, plus a read-only `view=review` proposal
   projection for first-party and adopter-built surfaces. Remaining UX work
   should improve app presentation, not create a second proposal system.
4. **Adoption Proof-Chain Quality:** the shortest first-run proof should not
   be considered ready just because commands are green. Current baseline:
   `governed_action_composition_packet.v1` checks the first-gated-action and
   learning-loop outputs as typed traceability matrices over existing refs,
   making disconnected evidence a release/adoption blocker without creating a
   workflow engine. `POST /kernel/governed-action-composition` and
   `cognitive-firm-userland composition-packet` expose the same read-only
   checker for adopter-built surfaces and terminal preflights.
   Adoption-readiness rows now also classify evidence quality by expected,
   present, and missing evidence fields, so a required check with a thin JSON
   payload does not become review-ready just because its basic command verdict
   is green.
   `make adoption-onramp-replay` now stages the public repo surface into a
   clean copy and runs the core on-ramp collector from there, so release review
   can distinguish clone-replayable adoption proof from author-local evidence.
   `make adoption-onramp-full-replay` runs the same clean-copy path with
   optional no-cost rows enabled, so reviewers can verify the default
   first-review packet from a clone-like surface before release.

Defer broad durable memory, deeper topology modeling, and team primitives
unless they directly serve those three deliverables. Context packets remain
receipts, not a memory product; proposal/timeline surfaces remain projections,
not BPM.

## Cross-Disciplinary Pull-Forwards

These candidates translate ideas from control, risk, formal methods,
organizational learning, and human factors into existing kernel surfaces. They
should extend the current primitives rather than create parallel subsystems.

| Candidate | Existing kernel surface | Public-grade next step |
|---|---|---|
| Guardrail-constrained policy promotion | action-impact rows, offline policy-evaluation reports, governance-change proposals, approved learning events | Thin slice shipped: policy-promotion packets join the offline report, guardrails, authority diff, optional formal-verification refs, and a draft governance-change payload. |
| Risk-adjusted action learning | action-impact, externality tags, accountability cases, outcome links | Thin slice shipped in the governance failure benchmark: a locally better action is blocked because externality and review-burden guardrails dominate. |
| Organizational immune response | damage signals, accountability cases, routine reviews, approved learning-event retirement | Thin slices shipped: damage signals can be shaped into accountability-case requests for accountable review without giving the detector authority to mutate policy; repeated warning-level damage of one kind, or any critical damage signal, can now compile into observer-only learning-transition candidates for mandate/accountability/routine review without quarantining, blocking, rerouting, or creating cases. |
| Policy proof obligations | formal-verification records, governed-run attestation bundles, package authority diffs | Thin slice shipped: governance-change review packets surface `proof_obligations` for policy/provider/adapter-shaped proposals and separate formal-verification refs from generic evidence without running checkers or approving changes. |
| Typed command effects | command surface, authority domains, kernel service, userland CLI | Thin slice shipped: command suggestions can expose declared authority effects (`decision_class` / `resource_class`), validate them against authority domains or the T1 single-authority fallback, and optionally trace whether a source role escalates to the resolved authority for that typed effect without executing, scheduling, or approving commands; unavailable authority-domain configuration is reported as `not_evaluated`. |
| Attention allocation learning | userland attention router, human-work sessions, action-impact, authority domains | Thin slice shipped: `GET /kernel/learning-transition-candidates?source=attention` and `cognitive-firm-userland learning-candidates --source attention` compile the routed L1 attention feed into observer-only candidates for unrouted signals, stale actionable signals, and repeated pressure on a role/signal class. They can trigger review of authority domains, memberships, mandates, route policy, or receipt discipline, but they do not reroute, page, assign, close, or schedule work. |
| Replayable decision log | run checkpoints, policy decisions, action attestations, outcome links, governed-run bundles | Thin slice shipped: `make decision-log-replay-demo` rebuilds safe and blocked policy-review packets from action-impact logs, wraps the replay in a completed run with checkpoints, records a verified action attestation and outcome verdict, and validates a governed-run bundle without changing live routing policy. |
| Operator-burden accounting | governed-run operator summaries, human-work pressure, action-impact review burden, bundle counts | Thin slice shipped: `governed_run_operator_summary.v1` can include an `operator_burden_projection.v1` over existing evidence so runbooks show estimated human touchpoints, missing receipts, stale pressure, review-required action-impact rows, and accountability/approval counts without assigning work, scheduling review, approving policy, or optimizing routes. The agent-fleet audit demo and `field_pilot_operator_burden_compile.py` now also emit `operator_burden_field_pilot_summary.v1` so pilots can compare baseline-vs-pilot burden and projection undercount without turning the summary into a workload optimizer. |
| Human-speed envelope | human-work bottleneck classes, risk tiers, deployment classes, policy decisions, accountability cases | Thin slice shipped: `GET /kernel/human-speed-envelope` and `cognitive-firm-userland speed-envelope` return `human_speed_envelope.v1`, classifying proposed work into agent speed, sampled review, batched human review, gate-before-action, or accountable closure from explicit facts without authorizing, dispatching, scheduling, sampling, or approving anything. The kernel-service smoke now asserts the route and exports `human_speed_envelope_counts` in adoption evidence JSON. |
| Context packet receipts | work-discovery pre-work projection, approved learning events, outcome links, routine reviews, governed-run bundles | Thin slice shipped: work discovery returns a citeable context-packet digest over the exact refs/query shown before work. Treat it like a chain-of-custody evidence bag: receipt only, not a plan or memory oracle. |
| Learning-use receipts | learning-event encounters, action attestations, outcome links | Thin slice shipped: `applied` requires work/evidence/context evidence, while `ignored` and `deferred` require reasons. Captured context packets can be checked with `verify_learning_event_context_packet_use(...)`, which verifies digest integrity and that the packet basis includes the target learning event without replaying logs, authorizing work, or writing state. This borrows the clinical-audit pattern: guideline deviations are allowed but must be explainable. |
| Structured cue/topology matching | learning-event metadata, multi-agent trace attribution, state-surface inventory | Thin slice shipped: replay and work-discovery context accept exact `cue_signature`, `resource_ref`, and `topology_ref` filters over learning-event metadata, include them in the context-packet basis, and allow non-role substrates to ask what learning applies without vector recall authority. |
| Human-reviewed agent output | human-work sessions, structured receipts, action attestations, provenance timeline | Thin slice shipped: `POST /kernel/human-work/{session_id}/receipt` and `cognitive-firm-userland receipt` record bounded human review receipts that can cite agent-output and action-attestation refs without becoming approval gates or workflow stages. |
| Human-work pressure learning | human-work sessions, strategy findings, learning-transition candidates | Thin slice shipped: `GET /kernel/human-work-pressure` and `cognitive-firm-userland human-pressure` expose repeated A2H bottlenecks as observer-only review signals; `GET /kernel/learning-transition-candidates?source=human_work` and `cognitive-firm-userland learning-candidates --source human_work` compile whole-firm pressure into review candidates with human-work source refs. Access/labor/cognition pressure can suggest source repair, tooling, or mandate review; taste, safety, relationship, and authority work remains intentionally human. |

Research anchors for the v0.4 memory/context direction: Reflexion
(arXiv:2303.11366), Generative Agents (arXiv:2304.03442), MemGPT
(arXiv:2310.08560), and Voyager (arXiv:2305.16291) all demonstrate useful
feedback/retrieval/skill/context compounding patterns. The kernel translation
is deliberately narrower: refs, digests, provenance, encounters, outcomes, and
review lifecycles rather than runtime memory or retrieval authority.

## Runtime Integration Roadmap

The public system boundary is maintained in
[`system-positioning.md`](system-positioning.md). The engineering conclusion is
simple: keep execution semantics in agent runtimes and wrap them with
governance state.

Near-term pull-forwards:

1. LangGraph adapter pack: lifecycle projection plus interrupt-to-A2H example
   is shipped as a framework-free executable demo; decide later whether to add
   a dependency-bearing adapter package.
2. Adapter conformance tests: no second durable ledger, no tenant policy inside
   the adapter, no role-authority widening.
3. CrewAI / AutoGen / Microsoft Agent Framework examples: minimal
   `started` / `checkpointed` / `state_changed` / `interrupted` projections.
4. Letta adapter example: agent memory stays in Letta; organizational memory
   stays in cognitive-firm events, receipts, and approved learning records.
5. Google ADK example: preserve ADK deployment/runtime semantics while
   projecting organizational authority and human-work pauses into the kernel.
6. Portable attestation bundle for governed runs: first export view shipped;
   broaden evidence joins before treating it as a stable interchange format.
7. A2A/agent-card authority bridge: cards are discovery and routing metadata;
   mandate, role, lease, and capability state decide whether action is allowed.

This roadmap should move only after the existing framework-neutral adapter
contract stays small. A framework-specific package may add examples and tests;
it should not make the public kernel depend on that framework.

## Field Validation Challenge

The public validation path is a bounded firm pilot, not a broad rollout. See
[`field-validation-pilot.md`](field-validation-pilot.md): pick one recurring
decision pipeline, measure the baseline, introduce the kernel primitives, and
compare error, time, cost, rework, human burden, accountability, and learning
events over a pre-registered pilot window.

## T2 Governance Roadmap

- Provider-specific RFC 3161 / Rekor / notary clients for audit manifests and
  release artifacts.
- Production OIDC/SAML provider examples beyond gateway-verified headers.
- Stronger tenant isolation for multi-authority or multi-tenant deployments.
- Enterprise RBAC/SSO admin implementations in tenant app/config layers.
- Backup/restore and migration dry-run gates for durable state.
- Supply-chain attestation for adapters, scripts, and deploy artifacts.
- Dead-letter/retry semantics for external side-effect outboxes.

## Enterprise Multi-Authority Roadmap

The current public baseline supports a single boot authority role and scoped
actor memberships. That is enough for T1 solo and small trusted-team pilots,
but it is not the final enterprise shape. The enterprise path is:

1. Authority domains: shipped for operating-unit, project, tenant,
   resource-class, decision-class, and global scopes.
2. Domain-aware boot check: shipped at the role-scope level. Multiple
  authority roles are allowed only when domains are declared and every
  authority role is scoped. The reusable role-graph validator now enforces
  that non-authority escalation chains terminate at an authority role in both
  package boot checks and the authority-domain CLI. Command-surface matches
  can now declare typed authority effects and validate those effects against
  authority domains, and optional source-role traces now check whether a role's
  escalation chain reaches the authority for the typed decision/resource class.
3. Domain-aware attention routing: shipped for scoped governance signals and
   active actor memberships. App UX for inspecting domain routing remains
   queued.
4. Scoped residual rights: thin slice shipped. Residual-right holder resolution
   now preserves explicit assignments as canonical, then projects a
   source-labeled accountable role from authority domains when the assignment is
   missing. The projection is visible to services and surfaces but does not
   authorize residual decisions or create workflow.
5. Enterprise terminology: replace public `principal`/`operator` wording where
   it means a narrower concept: accountable actor, authority role, member
   human, reviewer, or installation administrator.
6. Migration compatibility: retain `role.principal`,
   `preferences/principal.yaml`, and old CLI defaults as aliases until a
   migration command and compatibility tests prove existing T1 installs do not
   break.

## Human-Agent Governance Roadmap

- Promote embedded human-work `interaction_events` to a standalone
  `HumanAgentInteractionEvent` only if cross-session query pressure appears.
- Field-pilot validation for operator-burden accounting: the no-cost
  agent-fleet audit demo now reports `operator_burden_field_pilot_summary.v1`
  and can write `operator-burden-field-pilot-summary.json`; real pilot folders
  can compile measured `.csv`, `.json`, or `.jsonl` rows through
  `scripts/field_pilot_operator_burden_compile.py`. Both paths check
  baseline-vs-pilot human touchpoints, coordination minutes, rework, missing
  receipts, hidden burden, and projection undercount. External adopters still
  need measured evidence from real pilots before treating a burden policy as
  proven.
- Field-pilot validation for human-speed envelopes: the no-cost field-pilot
  demo now writes `human-speed-envelope-summary.json` with
  `human_speed_field_pilot_summary.v1`, checking chosen-vs-expected speed
  classes, sampled-review coverage, and harm/rework/hidden-burden/residual-risk
  review signals. External adopters still need measured evidence from real
  pilots before treating a speed policy as proven.
- A2H receipt and sampling policy examples by risk tier, bottleneck class, and
  deployment class.
- H2A/A2A conformance cases for interrupt, delegation, handoff, and completion.
- Additional receipt examples for physical-world, private-source, and
  relationship-work cases.

## Recursive Governance Roadmap

- Incident-to-learning replay: damage signal to review to candidate to approved
  learning event.
- Reward-hacking and externality canaries for tenant-owned optimizers.
- Offline policy replay for tenant routing policies before any live optimizer
  changes dispatch authority.

## Adoption Proof Artifacts

These are now part of the public adoption path:

- `docs/field-pilot-selector.md`;
- `docs/blueprints/multi-actor-authority.md`;
- `docs/accountability-speed-envelope.md`;
- `docs/examples/agent-fleet-audit-demo.md`;
- `docs/examples/learning-event-replay.md`;
- `docs/examples/action-intelligence-source-health.md`.

## Adoption And Distribution Direction

The kernel is sound; the current frontier is making it adoptable without an
adopter having to assemble it from a protocol catalog.

Shipped:

- Distribution layer: versioned `distro`/`overlay` packages, a package
  registry, and a transactional git-backed installer. Install enforces a
  kernel-version gate, verifies the governance graph and installed
  adapter/provider policy, and only then commits and tags the target
  (`install/<pkg>/<version>`); a failed or unbootable install leaves the
  target untouched. A component carries a
  composition `op` (`add` / `replace` / `patch`). `rollback` undoes a bad
  install — a clean `git reset` when nothing has run since, or a compensating
  `git revert` forward commit when the org has run. Installing an overlay onto
  a *running* org is governed: it files an authority-diff proposal and is
  blocked if it would widen a role's authority. A package can be installed
  from a git URL (SHA-pinned, content-hashed lockfile), and a distro may
  `extends` a base distro. The `cognitive-firm-distro` CLI ships `list / show /
  install / verify / upgrade / rollback / uninstall / lint`, with
  `install --dry-run` and a package template (`docs/templates/package/`) for
  third-party authoring. The `starter-firm` distro brings up a governed
  organization (principal, lead, analyst, reviewer) with a day-one governance
  loop in a single command, and is bundled in the wheel. See
  [`protocols/distribution.md`](protocols/distribution.md).
- Userland layer: an operator- and member-human-facing layer over the
  kernel — L0 enrollment, L1 attention router, L2 action (operator `needs-me`
  queue, member-human work inbox), L3 inspection/surface-policy, L4 vocabulary
  spine — exposed by the `GET /kernel/attention/{actor_id}` and
  `GET /kernel/vocabulary` kernel-service routes. The `cognitive-firm-userland`
  CLI (`needs-me` / `inbox` / `vocabulary` / `status` / `resolve` /
  `proposals` / `proposal` / `proposal-packet` / `proposal-template` /
  `work-context` / `proposal-from-candidate` / `human-pressure` /
  `learning-candidates` / `receipt` / `learning-use` / `learning-loop` /
  `timeline` / `graph` / `provenance-report` / `approve` / `decline`) and Orbit
  projection panes for `NeedsMePane`, `WorkInboxPane`, and
  `ProvenanceTimelinePane` are shipped over the built-and-tested userland
  logic. Orbit is one supplied visualization; the reusable contract remains the
  service/userland API.
- Extension schemas and the shareable community-package roadmap
  (`docs/community-packages.md`).

Planned, in sequence:

- More projection clients over the userland logic (Orbit panes, terminal
  reports, or adopter-built dashboards for vocabulary, enrollment, and proposal
  review), so a non-technical operator can run a governed organization without
  depending on one bundled UI.
- A shared, hosted package registry beyond local discovery and git-URL fetch,
  with a published third-party authoring and review path
  (`docs/community-packages.md`).
- Open-core distribution: the kernel stays open and self-hostable so the
  filesystem + git inspect/fork/replay invariant holds; a managed hosted
  option serves adopters who will not run infrastructure.

The remaining items are gated on a first validating field pilot: the kernel's
measurable-improvement claim should be demonstrated with one real adopter
before adoption is scaled. The no-cost field-pilot action-impact demo now shows
the expected evidence path from measured pilot rows to a governance review
packet.
