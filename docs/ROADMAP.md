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

## Shipped Public-Kernel Baseline

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
  conservative offline evaluation, and governance review packet through the
  kernel service. The fixture shows both a review-ready route and a high-reward
  route rejected because externality and review-burden guardrails fail.
- Field-pilot action-impact demo included in `make smoke-public`: a pilot
  folder can carry `action-impact-summary.json`, pass strict pilot validation,
  and produce a policy-promotion packet from measured pilot rows.
- Formal-provider bundle demo included in `make smoke-public`: a signed
  LeanMill-style provider payload is ingested through the kernel service and
  becomes clean governed-run evidence when org trust policy, signature
  verification, checker evidence, and faithfulness refs are present; a
  missing-evidence provider row keeps the bundle incomplete.
- Runtime adapter-policy package: the bundled `langgraph-runtime-adapter`
  overlay installs governance-side adapter and conformance declarations for a
  LangGraph-style runtime. It does not install executable adapter code and
  should preview as authority-neutral before governed install.
- Authority-domain routing helper: `authority_resolver_from_org(...)` connects
  scoped attention signals to authority domains plus active actor memberships,
  preserving the role even when no active actor currently holds it.
- Package metadata smoke included in `make smoke-public`; it builds and
  inspects a local wheel when the build backend from `requirements.txt` is
  installed.
- Mid-level adoption packaging: abstraction map, resource/event catalog,
  blueprint index, and docs-surface check included in `make smoke-public`.
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
  inbox), L3 inspection/surface-policy, L4 vocabulary spine. Exposed by two
  kernel-service routes: `GET /kernel/attention/{actor_id}` and
  `GET /kernel/vocabulary`. The `cognitive-firm-userland` CLI ships `needs-me`,
  `inbox`, `vocabulary`, `status`, `resolve`, and the governed-install
  human-review verbs `proposals` / `approve` / `decline` (over the
  `GET /kernel/governance-changes` and
  `POST /kernel/governance-changes/{id}/decision` routes). An Orbit
  `NeedsMePane` surfaces the operator's
  attention queue. The userland logic is built and tested; the operator CLI and
  the one `NeedsMePane` Orbit pane exist — not every Orbit pane over the
  userland is built yet.
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
   fixture; next add command-path fixtures for interrupt, delegation, handoff,
   human-work follow-up, and saga compensation.
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

## Cross-Disciplinary Pull-Forwards

These candidates translate ideas from control, risk, formal methods,
organizational learning, and human factors into existing kernel surfaces. They
should extend the current primitives rather than create parallel subsystems.

| Candidate | Existing kernel surface | Public-grade next step |
|---|---|---|
| Guardrail-constrained policy promotion | action-impact rows, offline policy-evaluation reports, governance-change proposals, approved learning events | Thin slice shipped: policy-promotion packets join the offline report, guardrails, authority diff, optional formal-verification refs, and a draft governance-change payload. |
| Risk-adjusted action learning | action-impact, externality tags, accountability cases, outcome links | Thin slice shipped in the governance failure benchmark: a locally better action is blocked because externality and review-burden guardrails dominate. |
| Organizational immune response | damage signals, accountability cases, routine reviews, approved learning-event retirement | Thin slice shipped: damage signals can be shaped into accountability-case requests for accountable review without giving the detector authority to mutate policy. Next, surface repeated harm patterns as review candidates only when there are concrete consumers. |
| Policy proof obligations | formal-verification records, governed-run attestation bundles, package authority diffs | Allow a governance-change proposal to cite formal-verification records before a high-risk policy adapter is approved. |
| Attention allocation learning | userland attention router, human-work sessions, action-impact, authority domains | Learn candidate attention-routing improvements from reviewed rows, but route them through governance before activation. |
| Replayable decision log | run checkpoints, policy decisions, action attestations, outcome links, governed-run bundles | Add a demo that rebuilds a candidate policy report and bundle from logs alone. |

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
   authority role is scoped. Deeper validation that each role's escalation
   chain reaches the authority for its own domain remains queued.
3. Domain-aware attention routing: shipped for scoped governance signals and
   active actor memberships. App UX for inspecting domain routing remains
   queued.
4. Scoped residual rights: align residual-right assignments with authority
   domains so incomplete mandates resolve to the correct accountable role.
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
- Operator-burden accounting so governance surfaces do not simply shift work to
  the human.
- Human-speed envelope guidance: what can run at agent speed, what must be
  batched/sampled, and what must stay at accountable human speed.
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
  `proposals` / `approve` / `decline`) and an Orbit `NeedsMePane` are
  shipped over the built-and-tested userland logic. Not every Orbit pane over
  the userland is built yet.
- Extension schemas and the shareable community-package roadmap
  (`docs/community-packages.md`).

Planned, in sequence:

- More Orbit panes over the userland logic (inbox, vocabulary, enrollment), so
  a non-technical operator runs a governed organization fully from the desktop
  surface.
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
