# Agent Instructions

This repository is the reusable cognitive-firm kernel. Keep tenant-specific
mandates, credentials, strategic context, and runtime state out of the public
kernel. Use `tenants/example/` and `org/*/templates/` as copyable examples.

## Work Filter

For every non-trivial change, ask first:

> Is this actually important for recursive AI governance, or is it work around
> the work?

Prefer changes that improve the executable kernel for recursive organizations:
authority, delegation, governed change, auditability, resource/event surfaces,
human interrupts, and closed-loop execution. If a change mainly adds ceremony,
prose, or orchestration without improving one of those surfaces, tighten it or
defer it.

When editing the kernel:

- After a reset, read the local handover/memory surfaces if present, but keep
  internal strategy and sibling-repo mandates out of the public kernel. Import
  only repo-neutral discipline: canonical-home search, evidence carriers,
  substrate-neutral naming, and integration-seam checks.
- Keep core primitives domain-neutral.
- Keep the kernel firm-general. Do not introduce a primitive, field, fixture, or
  example that only makes sense for one industry, job type, tenant, or current
  project unless it lives in a clearly named overlay/example.
- Do not conflate durable offices with task-local computational roles. In this
  kernel, role offices are authority and accountability envelopes; task-local
  roles, protocols, or delegation patterns may be dynamic inside a mandate.
- Put tenant/app policy in overlays, adapters, or examples.
- Build execution primitives, not only governance description. A protocol should
  have an inspectable artifact, CLI/API surface, test, fixture, or event/resource
  projection whenever feasible.
- Keep the source-of-truth boundary clear. Reusable primitives, invariants,
  schemas, state transitions, adapters, and service routes belong under
  `src/cognitive_firm/`; `scripts/` should stay thin as CLIs, demos, smoke
  harnesses, migrations, and operator entrypoints that compose the kernel.
- Extend the canonical home for an existing capability before creating a
  parallel module. Search the code and docs first, then wire the improvement into
  the established primitive.
- Promote script logic into `src/cognitive_firm/` once it becomes reusable,
  policy-bearing, or required for more than one demo/operator workflow.
- Keep substrate facts in inputs, registries, schemas, or tenant overlays. Core
  modules should use neutral names such as actor, role, unit, work item, resource,
  receipt, artifact, lease, event, policy, and outcome.
- Keep evidence attached to decisions. Governance changes, policy decisions,
  handoffs, and escalation paths should carry source refs, expected behavior
  changes, risks, rollback paths, and machine-checkable status where practical.
- Ground primitives and org patterns in serious source material. When a change
  makes a conceptual claim about symbiotic human/AI organizations, cite or link
  the relevant foundation where practical: organization theory, incomplete
  contracts, decision theory, distributed systems, human-computer interaction,
  human work studies, safety/governance, and current agent literature. Do not
  use citations as decoration; use them to shape the abstraction boundary,
  invariants, tests, and docs.
- For public protocol docs whose primitive depends on a recognizable research
  lineage, add a concise `Research Anchor` section with checkable links. Keep
  it proportional: enough for a reader to verify the foundation, not a literature
  review, and do not overclaim beyond the shipped interface.
- Treat documentation as a map to executable surfaces. Update docs when behavior
  changes, but do not let docs become a substitute for runnable checks.
- Before declaring substantial code done, trace the integration seams and
  cross-run state in your head or with tests: who writes, who reads, what key or
  schema crosses the boundary, and how stale or missing state behaves.
- Run `make smoke-public` before shipping public-facing changes.
- Run `make smoke-docker` when validating clean-container boot.
- Do not commit local `.env`, principal preferences, daemon state, or private
  tenant symlinks.
