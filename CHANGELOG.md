# Changelog

## v0.3.0 - 2026-06-14

This release candidate makes the kernel materially more executable while
keeping runtime orchestration, tenant policy, and workflow/BPM concerns outside
the reusable core.

Highlights:

- Release gates now include public smoke, clean-container smoke, release
  hygiene, public-claim discipline, and broad diff classification.
- Self-evolving organization proof paths now emit readable report JSON,
  operator runbooks, HTML timelines, mutation proofs, future replay proofs,
  planner receipts, and git receipts under gitignored run directories.
- A bounded live Codex planner proof was run outside the deterministic release
  gate: one subscription/local planner call, one governed approval, one valid
  mutation proof, and one replay-valid proof chain.
- Kernel service adoption was hardened so adopter-facing demos route durable
  rows through service routes instead of writing primitive state directly where
  a route exists.
- New service surfaces cover policy decisions, formal-verification provider
  payload ingestion/listing, and accountability-case status updates.
- First-party governance carriers and thin recipes expanded for agent runtime
  invocation receipts, capability signals, decision aggregation,
  multi-agent trace attribution, mutation proofs, phase execution, protocol
  experiments, and governed-run request shaping.
- Deterministic examples now cover agent-fleet audit trail, decision-log
  replay, field-pilot action impact, formal provider bundles, LangGraph-style
  governance projection, multi-actor authority, and governance failure
  fixtures.
- Public docs clarify the T1/T2 boundary: cognitive-firm governs authority,
  evidence, receipts, outcomes, learning, and bounded mutation around runtimes;
  it is not a replacement agent runtime, BPM product, compliance
  certification, or tenant strategy store.
- Public schema and dashboard shell text were cleaned of legacy
  project-specific naming so the reusable kernel stays tenant-neutral.

Verification before release:

- `make smoke-public`
- `make smoke-docker`
- `make release-diff-audit`

## v0.2.0 - 2026-06-11

This release candidate turns the repository from a protocol-heavy kernel into
a more executable governance surface.

Highlights:

- Governed-run attestation bundles with replayable evidence, caveats, formal
  verification records, action attestations, human-work receipts, outcome
  links, work items, leases, and accountability cases.
- Kernel service routes for runs, operating units, work items, learning events,
  governance-change proposals, outcome links, routine reviews, resource
  allocation, and residual decision rights.
- Governance-change proposals now require structural evidence sufficiency, can
  be exposed as resource envelopes, and can be proposed/approved through the
  service boundary.
- Runtime adapter proof paths for native runs and LangGraph-style projection,
  plus adapter conformance fixtures and package entry points.
- Distribution hardening for starter-firm installs, overlay preview, authority
  diffs, governed install proposals, package signing, lockfiles, rollback, and
  clean-container smoke.
- Action-impact and offline policy-promotion tooling, including fixtures that
  reject locally positive policies when externality or review-burden guardrails
  fail.
- Formal-verification provider payload support with trust policy checks and
  governed-run bundle integration.
- Public examples and smoke scripts for adoption, failure benchmarks, decision
  log replay, field-pilot action impact, formal-provider bundles, A2H command
  conformance, and multi-actor authority.

Verification before release:

- `make smoke-public`
- `make smoke-docker`

## v0.1.0 - Initial release

Initial public release of the reusable cognitive-firm governance kernel.
