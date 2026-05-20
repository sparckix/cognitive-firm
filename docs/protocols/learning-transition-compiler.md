# Learning Transition Compiler

**Module:** `cognitive_firm.orchestration.learning_transition_compiler`

The learning-transition compiler turns existing learning carriers into
reviewable transition candidates. It is the bridge between "the organization
noticed something" and "an authorized role should decide whether durable state
changes."

It is observer-only. It does not mutate mandates, project charters, evidence
gaps, forecast contracts, human-work sessions, action-impact rows, or routes.

## What It Reads

The compiler reads the generic organization surface:

- strategy-office findings;
- forecast allocation recommendations;
- action-impact records requiring review;
- local actions with negative externalities;
- source-improvement backlog items exposed by intelligence-source coverage.

The organization surface already joins evidence gaps, human work, damage
signals, failed runs, forecast-market state, action-impact state, and invalid
project charters. The compiler consumes that joined surface rather than
inventing a second source of truth.

## What It Emits

Each `LearningTransitionCandidate` includes:

- `candidate_id`;
- `transition_kind`;
- `severity`;
- `rationale`;
- `source_kind`;
- `object_ref`;
- `suggested_owner_role`;
- `review_question`;
- `source_refs`;
- `proposed_payload`;
- `observer_only`.

Supported transition kinds are:

- `evidence_gap`;
- `project_charter_update`;
- `mandate_review`;
- `human_work_session`;
- `forecast_contract`;
- `source_repair`;
- `role_review`.

These are candidate kinds, not direct writes. A tenant may bind candidates to a
manager inbox, review queue, issue tracker, or private workflow.

## Why This Exists

Surfacing primitives is not enough. A role can see many signals and still fail
to convert them into changed future behavior. The compiler provides a narrow,
testable step:

```text
learning carrier -> observer finding -> reviewable transition candidate
                 -> approved learning event
```

This keeps organizational learning explicit without letting an automated
optimizer rewrite governance state.

## Source Connector Boundary

The compiler consumes read models. Storage transport remains a separate
`SourceConnector` concern:

- state backends store kernel events and artifacts;
- MCP connectors reach enterprise systems;
- runtime adapters project execution events;
- notification channels deliver attention intents.

The compiler should not call an ERP, ticketing system, or graph runtime
directly. If a tenant wants a candidate to become an external work item, that
belongs in a tenant adapter with explicit authority.

## Promotion Boundary

Approved candidates can be recorded with
`cognitive_firm.orchestration.learning_events`. That module records the durable
behavior-change event and approval reference. It still does not apply the
referenced route, mandate, charter, routine, threshold, or policy-adapter change.

## Tests

Covered by `tests/test_learning_transition_compiler.py`.
