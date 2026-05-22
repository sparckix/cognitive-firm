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
adopter having to assemble it from a protocol catalog. Planned, in sequence:

- A userland: an operator-facing surface that hides the kernel, so a
  non-technical operator can run a governed organization without reading the
  protocol specs.
- A starter distribution + installer: a day-one runnable example organization
  brought up in a single action, not assembled from the catalog.
- A package / overlay ecosystem: tenant overlays as installable, shareable
  packages with a clear third-party authoring path.
- Open-core distribution: the kernel stays open and self-hostable so the
  filesystem + git inspect/fork/replay invariant holds; a managed hosted
  option serves adopters who will not run infrastructure.

These are gated on a first validating field pilot: the kernel's
measurable-improvement claim should be demonstrated with one real adopter
before adoption is scaled.
