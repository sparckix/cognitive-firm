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
POST /kernel/governance-changes/{proposal_id}/outcome-link
POST /kernel/learning-transition-candidates/{candidate_id}/governance-change
```

Creation records the proposal and its deterministic evidence checks. A decision
records an approval or decline event; applying the referenced file, policy, or
overlay remains a separate governed mutation.

The candidate-promotion route is a convenience path for review queues. It
copies a learning-transition candidate's rationale and source refs into a
governance-change proposal, then runs the same evidence-sufficiency gate. The
caller must still provide target, expected behavior change, risk, rollback, and
invariant evidence. A weak candidate-promotion request becomes `blocked`, not
approved.

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
  alternatively, a typed `predicted_effect` can carry the falsifiable metric
  contract for the change;
- `risk_summary`: what risk or burden the reviewer should consider;
- `rollback_plan`: how the change can be undone;
- invariant evidence refs: every passing required invariant check must cite at
  least one evidence ref.

The computed `evidence_sufficiency` field records `status`, `missing`,
`rationale`, and the evidence refs gathered from the proposal and invariant
checks.

## Predicted Effects

Governance changes may carry a typed `predicted_effect` using the same contract
as [`Outcome Links`](outcome-links.md):

```json
{
  "metric_name": "handoff_rework_rate",
  "metric_unit": "ratio",
  "direction": "lower_is_better",
  "threshold": 0.1,
  "review_horizon": "after_next_10_handoffs",
  "expected_verdict": "improved",
  "rationale": "handoff rework should fall after the evaluator mandate change"
}
```

The kernel validates the shape and stores it on the proposal. It does not
compute the metric. After the proposal is approved,
`POST /kernel/governance-changes/{proposal_id}/outcome-link` opens a normal
outcome link using the proposal's typed prediction. That route is a convenience
composition over the outcome-link primitive: it carries `predicted_effect` into
`metadata.predicted_effect`, but does not record snapshots, decide the verdict,
or apply the mutation. A later verdict derives `prediction_met`,
`prediction_failed`, or `prediction_inconclusive`, which can feed routine review
and governed reversal.

This lets structural self-modification be proposed with a falsifiable outcome
contract instead of only narrative intent.

## Amendment-Tier Check

`tier_classification_invariant_check(...)` is a standard optional invariant
check for charters that distinguish amendment tiers:

- Tier 0 immutable surfaces, such as kernel invariants or principal-control
  surfaces, fail closed with `tier_0_immutable`.
- Tier 1 surfaces, such as charters, capability definitions, or scoring
  interfaces, pass with a `principal_explicit_approval` required path.
- Tier 2 surfaces, such as ordinary offices, mandates, policies, review
  artifacts, decision models, and learning-unit files, pass with an
  `ordinary_governed_mutation` path.

The check does not approve a proposal and does not replace decision rights. It
adds deterministic tier evidence that reviewers and authority-domain policy can
use before approval. This keeps "who may decide" separate from "how advisory
positions were aggregated."

## Deletion-Duty Check

`deletion_duty_invariant_check(...)` is a standard optional invariant check for
charters that want to resist structural ratchets. A structure-adding proposal
can pass the check by naming a retirement candidate or by explicitly justifying
net growth. If neither is present, the check fails.

This is deliberately opt-in. The kernel does not assume that every tenant must
delete or merge structure whenever it adds an office, policy, route, protocol,
or decision model. A charter that cares about deletion pressure includes this
check as proposal evidence; another charter can omit it.

The check is evidence, not approval. It does not retire anything by itself and
does not replace routine review. Retirement remains a governed state transition
through the forgetting/review lifecycle.

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
