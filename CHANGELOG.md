# Changelog

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
