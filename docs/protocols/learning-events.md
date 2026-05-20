# Approved Learning Events

**Module:** `cognitive_firm.orchestration.learning_events`

Approved learning events are the promotion target after a learning-transition
candidate has been reviewed. They record that the organization accepted a
durable change to future behavior.

They are not agent memories, retrospectives, forecast scores, or strategy
findings. Those are carriers. A learning event exists only after approval.

## What It Records

Each `ApprovedLearningEvent` includes:

- `learning_event_id`;
- `learning_unit_kind`;
- `decision_use`;
- `future_application_cue`;
- `approved_by`;
- `approval_ref`;
- `source_carrier_refs`;
- `candidate_ref`;
- `before_state`;
- `after_state`;
- `owner_role`;
- `tenant_id`;
- `project_id`;
- `externality_review_ref`;
- `review_after_utc`;
- `superseded_by`;
- `retirement_reason`;
- `status`;
- `metadata`.

Supported learning-unit kinds are:

- `route_change`;
- `mandate_change`;
- `charter_change`;
- `evidence_standard_change`;
- `review_threshold_change`;
- `routine_change`;
- `policy_adapter_change`.

## Boundary

`learning_events.py` records approved behavior changes. It does not apply the
referenced route, mandate, charter, threshold, routine, or policy-adapter
change. Tenants own those mutations and the approval policy.

The default filesystem adapter writes JSONL records to:

```text
org/learning_events/learning_events.jsonl
```

Active events appear in the organization surface so future work can encounter
the accepted behavior change instead of relying on retrospective prose.

Events have an explicit lifecycle:

- `active`: eligible for replay and organization-surface visibility;
- `superseded`: replaced by a narrower or newer learning event;
- `retired`: intentionally removed from future replay.

Replay is deterministic. `replay_learning_events(...)` filters by role,
tenant/project scope, and lexical cue; it does not use semantic similarity as
authority. A tenant/project replay includes global events unless an event is
explicitly scoped to another tenant or project.

Work discovery also surfaces matching active events as
`learning-event-replay` candidates so roles encounter approved learning before
repeating prior failure modes.

When a caller opts in to learning encounter telemetry, work discovery writes an
idempotent encounter row to:

```text
org/learning_events/learning_encounters.jsonl
```

Encounter outcomes are `encountered`, `applied`, `ignored`, or `deferred`.
Discovery can record `encountered`; tenants or app surfaces can later record a
stronger outcome when a role applies or rejects the learning. Plain discovery
is read-only by default.

## Candidate Promotion

The helper `learning_event_from_candidate(...)` preserves the source candidate
and its evidence references:

```text
LearningTransitionCandidate
-> review / approval
-> ApprovedLearningEvent
-> tenant applies the referenced change through its own authority path
```

This keeps the learning-transition compiler observer-only while still giving
organizational learning a durable promotion object.

## Tests

Covered by `tests/test_learning_events.py`.
