# Governance Change Proposals

**Module:** `cognitive_firm.orchestration.governance_changes`

Governance change proposals are the kernel primitive for governed
self-modification. Agents and role offices may propose changes to mandates,
roles, routes, gates, capability policy, learning policy, or tenant policy, but
the proposal must carry deterministic invariant checks and enough structural
evidence before review.

The module records proposals. It does not apply them.

The local kernel service exposes the same primitive for app surfaces and agent
runtimes:

```text
POST /kernel/governance-changes
GET  /kernel/governance-changes
GET  /kernel/governance-changes/{proposal_id}
POST /kernel/governance-changes/{proposal_id}/decision
```

Creation records the proposal and its deterministic evidence checks. A decision
records an approval or decline event; applying the referenced file, policy, or
overlay remains a separate governed mutation.

## Why This Exists

Recursive systems need to improve their own governance without becoming the
judge of their own constraints. A proposal can be useful, but it is not
authority. The kernel therefore separates:

```text
agent or role proposes a governance change
-> deterministic invariant checks are recorded
-> evidence sufficiency is checked
-> proposal becomes blocked or review-ready
-> principal / tenant approval happens elsewhere
-> tenant applies the referenced change through its own authority path
```

## Required Invariants

The default required invariants are:

- `principal_independence`;
- `deterministic_enforcement_floor`;
- `fail_closed_behavior`;
- `write_scope_preserved`;
- `tenant_boundary_preserved`.

A proposal is `review_ready` only when all required invariants pass, no
recorded invariant fails, and evidence sufficiency passes. Otherwise it is
`blocked`.

## Evidence Sufficiency

`assess_evidence_sufficiency(...)` is a structural gate, not a domain-specific
judgment. It prevents a recursive system from changing its own constraints with
only prose and self-asserted invariant results.

A review-ready proposal must include:

- `source_refs`: the artifacts, evaluations, authority diffs, evidence gaps, or
  packets that motivated the change;
- `expected_behavior_change`: what future behavior would change;
- `risk_summary`: what risk or burden the reviewer should consider;
- `rollback_plan`: how the change can be undone;
- invariant evidence refs: every passing required invariant check must cite at
  least one evidence ref.

The computed `evidence_sufficiency` field records `status`, `missing`,
`rationale`, and the evidence refs gathered from the proposal and invariant
checks.

## Proposal Fields

Each `GovernanceChangeProposal` includes:

- `proposal_id`;
- `created_at_utc`;
- `change_kind`;
- `title`;
- `proposed_by`;
- `target_ref`;
- `rationale`;
- `status`;
- `source_refs`;
- `expected_behavior_change`;
- `risk_summary`;
- `rollback_plan`;
- `owner_role`;
- `tenant_id`;
- `project_id`;
- `invariant_checks`;
- `evidence_sufficiency`;
- `approval_ref`;
- `metadata`.

Supported change kinds are:

- `mandate_change`;
- `role_change`;
- `project_charter_change`;
- `route_policy_change`;
- `capability_policy_change`;
- `gate_policy_change`;
- `learning_policy_change`;
- `tenant_policy_change`.

## Boundary

This is a Config-layer primitive. It can say "this proposed change preserved
the required invariants, cites enough structural evidence, and is ready for
review." It cannot update a mandate, rewrite a route, grant a capability, or
change tenant policy by itself.

Default local path:

```text
org/governance_changes/governance_changes.jsonl
```

Pending blocked and review-ready proposals appear in the organization surface.

## Resource Projection

`governance_change_resource(...)` projects a proposal into the common
[Resource Envelope](resource-envelope.md). The JSONL row remains canonical; the
resource shape is for adapters, dashboards, migration checks, and conformance
fixtures that need one object model for governed self-modification state.

The projection includes:

- `metadata`: proposal id, tenant/project scope, labels for change kind,
  proposal status, proposer, target, owner role, and review readiness;
- `spec`: proposed change kind, title, target, rationale, source refs,
  expected behavior change, risk summary, rollback plan, and owner role;
- `status`: proposal status, review-readiness, invariant checks, evidence
  sufficiency result, approval ref, and creation time;
- `links`: target, proposer, owner, approval, source refs, gathered evidence
  refs, and per-invariant evidence refs.

The CLI can render either canonical rows or resource envelopes:

```bash
python -m cognitive_firm.orchestration.governance_changes list --resource
```

## Tests

Covered by `tests/test_governance_changes.py` and `tests/test_org_surface.py`.
