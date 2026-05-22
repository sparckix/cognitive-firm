# Roadmap

This roadmap lists public-kernel work that is useful across tenants. It avoids
tenant-specific research policy, scoring systems, and optimizer rules.

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
  operating-unit health dashboard.
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
  `cognitive-firm-distro` CLI ships `list / show / install / verify / upgrade
  / rollback / uninstall / lint`, and the bundled `starter-firm` distro ships a
  day-one governance loop in the wheel.
  - Overlay composition (O3-P2): a component carries an `op` —
    `add` / `replace` / `patch` (RFC 7386 JSON Merge Patch).
  - Governed overlay install (O3-P1): installing an overlay onto a *running*
    org files a governance-change proposal whose `expected_behavior_change` is
    a rendered authority-diff; an overlay that expands a role's write scope (or
    changes authority uninterpretably) fails a required invariant and is
    blocked — a package may not widen authority. An approved install attests a
    `package.install_approved` event.
  - Remote packages (O3-P3): `install <git-url>` fetches a package SHA-pinned,
    recording a content-hashed `.cognitive-firm/packages.lock` that catches a
    moved tag or a force-push.
  - Distro inheritance (O3-P5): a manifest may `extends` a base distro;
    installing it installs the base first, then composes the extender (one
    level).
  - Authoring loop (O3-P4): `lint`, `install --dry-run`, and a package
    template at `docs/templates/package/`.
- Userland layer (`src/cognitive_firm/userland/`): the operator- and
  member-human-facing layer over the kernel, with five layers — L0 enrollment,
  L1 attention router, L2 action (operator `needs-me` queue, member-human work
  inbox), L3 inspection/surface-policy, L4 vocabulary spine. Exposed by two
  kernel-service routes: `GET /kernel/attention/{actor_id}` and
  `GET /kernel/vocabulary`. The `cognitive-firm-userland` CLI ships `needs-me`,
  `inbox`, and `vocabulary`. An Orbit `NeedsMePane` surfaces the operator's
  attention queue. The userland logic is built and tested; the operator CLI and
  the one `NeedsMePane` Orbit pane exist — not every Orbit pane over the
  userland is built yet.
- L3 surface-policy guard: the kernel service refuses a mutation from a
  `projection_only` surface (`KernelServiceConfig.surface_write_modes`).
- Extension schemas (O3-P6): packages register JSON Schemas to validate custom
  primitive payload types, wired into `enqueue_work_item`. Open by default — a
  `kind` with no registered schema is unconstrained.

## Lean T2 Seams

The current lean T2 seams are deliberately small. They show how the kernel can
move beyond trusted single-principal files without claiming full enterprise
governance:

- SQLite event source as the lean state-backend migration target.
- Kernel event envelope embedded in transition rows.
- Runtime adapter conformance fixtures for framework-neutral lifecycle events.
- Runtime interrupt-to-human-work bridge for external HITL pauses.
- OpenTelemetry GenAI-shaped projection for run/checkpoint observability.
- Policy-decision record shape for bounded local allow/deny checks.
- State-surface registration gate for new JSONL-backed primitives.
- Action attestations for machine-side provenance.
- Audit-integrity manifests over JSONL logs, with optional HMAC verification.
- Accountability cases for authority, recourse, residual-risk acceptance, and
  closure evidence.
- Kernel service boundary over the same Python primitives used by CLI and app
  surfaces.
- Actor identity records for first-party actor context over external identity
  providers.
- Actor membership records for scoped role authority across multiple humans,
  agents, or services in one deployment.
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

1. Resource/event model consolidation: keep the resource envelope, kernel event
   envelope, transition rows, JSONL state rows, and mutation events aligned
   under one documented compatibility contract.
2. Public docs consistency pass: keep generated indexes, README claims, and T2
   language aligned with shipped tests.
3. External-connector conformance fixtures: add capability-policy examples for
   read and write tools beyond the shipped Linear/GitHub/Stripe fixtures.

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
- Stronger tenant isolation for multi-principal or multi-tenant deployments.
- Enterprise RBAC/SSO admin implementations in tenant app/config layers.
- Backup/restore and migration dry-run gates for durable state.
- Supply-chain attestation for adapters, scripts, and deploy artifacts.
- Dead-letter/retry semantics for external side-effect outboxes.

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
- Evidence sufficiency checks for proposed governance changes.
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
  kernel-version gate, runs a governance-graph `boot_check`, and only then
  commits and tags the target (`install/<pkg>/<version>`); a failed or
  unbootable install leaves the target untouched. A component carries a
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
  CLI (`needs-me` / `inbox` / `vocabulary`) and an Orbit `NeedsMePane` are
  shipped over the built-and-tested userland logic. Not every Orbit pane over
  the userland is built yet.
- Extension schemas (O3-P6) and the shareable community-package roadmap
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
before adoption is scaled.
