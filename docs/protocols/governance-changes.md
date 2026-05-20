# Governance Change Proposals

**Module:** `cognitive_firm.orchestration.governance_changes`

Governance change proposals are the kernel primitive for governed
self-modification. Agents and role offices may propose changes to mandates,
roles, routes, gates, capability policy, learning policy, or tenant policy, but
the proposal must carry deterministic invariant checks before review.

The module records proposals. It does not apply them.

## Why This Exists

Recursive systems need to improve their own governance without becoming the
judge of their own constraints. A proposal can be useful, but it is not
authority. The kernel therefore separates:

```text
agent or role proposes a governance change
-> deterministic invariant checks are recorded
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

A proposal is `review_ready` only when all required invariants pass and no
recorded invariant fails. Otherwise it is `blocked`.

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
the required invariants and is ready for review." It cannot update a mandate,
rewrite a route, grant a capability, or change tenant policy by itself.

Default local path:

```text
org/governance_changes/governance_changes.jsonl
```

Pending blocked and review-ready proposals appear in the organization surface.

## Tests

Covered by `tests/test_governance_changes.py` and `tests/test_org_surface.py`.
