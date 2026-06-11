# Resource Envelope

**Module:** `cognitive_firm.orchestration.resource_envelope`

The resource envelope is the lightweight object shape for kernel resources. It
keeps primitive data portable without requiring the repo to become a Kubernetes
clone.

## Shape

Each resource has:

```text
api_version
kind
metadata
stability
spec
status
links
```

`metadata` includes name, optional resource ID, tenant/project IDs, labels,
annotations, and timestamps.

`stability` is one of:

- `alpha`: shape may change while the primitive is still settling;
- `beta`: shape is expected to hold unless tests or field use expose a gap;
- `stable`: shape is part of the supported public contract.

## Boundary

The envelope is a compatibility convention, not a storage backend. Individual
primitives can keep their own T1 files while exposing resources through this
shape for conformance, documentation, migration, or external adapters.

Current first-party projections:

- `accountability_case_resource(...)` for residual-risk, recourse, and closure
  records;
- `actor_identity_resource(...)` for first-party actor identity records;
- `actor_membership_resource(...)` for scoped role-membership grants;
- `human_work_resource(...)` for A2H/human-work coordination, receipts, and
  follow-up state;
- `lease_resource(...)` for time-bounded mutation-control leases;
- `learning_event_resource(...)` for approved, replayable learning units;
- `operating_unit_resource(...)` for operating-unit contracts;
- `outcome_link_resource(...)` for governed changes tied to tenant-measured
  outcomes and verdicts;
- `policy_decision_resource(...)` for bounded allow/deny audit decisions;
- `residual_right_assignment_resource(...)` for scoped default-decider
  assignments where mandates are silent;
- `residual_decision_resource(...)` for fail-open residual decisions and their
  review outcomes;
- `routine_review_resource(...)` for routine re-justification and retirement
  records;
- `work_item_resource(...)` for durable production work items.

These projections are deliberately downstream of canonical state. Mutations
still go through the primitive APIs and emit kernel events where the primitive
owns an event lifecycle.

## Tests

Covered by `tests/test_resource_envelope.py`.
