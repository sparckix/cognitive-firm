# Approved Learning Events

**Module:** `cognitive_firm.orchestration.learning_events`

Approved learning events are the promotion target after a learning-transition
candidate has been reviewed. They record that the organization accepted a
durable change to future behavior.

They are not agent memories, retrospectives, forecast scores, or strategy
findings. Those are carriers. A learning event exists only after approval.

## Learning Unit Contract

In this kernel, the smallest durable learning unit is an
`ApprovedLearningEvent`: a reviewed behavior change with enough structure to be
replayed, measured, retired, and combined with other approved changes.

A carrier becomes a learning unit only when it answers:

- what future decision or work surface should change (`decision_use`);
- when the change should be encountered again (`future_application_cue`);
- who approved the change and where that approval is recorded (`approved_by`,
  `approval_ref`);
- what evidence or prior units support it (`source_carrier_refs`,
  `derived_from_learning_event_ids`);
- what changed (`before_state`, `after_state`);
- who owns future application or review (`owner_role`);
- when the unit should be reviewed or retired (`review_after_utc`, routine
  reviews).

`action_impact` rows, forecast records, human receipts, accountability cases,
and strategy findings are learning carriers. They are not learning units until
an accountable role approves the future behavior change.

## What It Records

Each `ApprovedLearningEvent` includes:

- `learning_event_id`;
- `learning_unit_kind`;
- `decision_use`;
- `future_application_cue`;
- `approved_by`;
- `approval_ref`;
- `source_carrier_refs`;
- `derived_from_learning_event_ids`;
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

There is no `rejected` status on `ApprovedLearningEvent`. Rejection belongs to
the object that failed review: a learning-transition candidate, governance
proposal, policy-promotion packet, or routine-review recommendation. If a
candidate is rejected, do not mint an approved learning event to remember that
rejection. Keep the rejected carrier/proposal and its evidence as the audit
record. Only approved future-behavior changes become learning events.

Replay is deterministic. `replay_learning_events(...)` filters by role,
tenant/project scope, exact source refs, explicit metadata tags, and lexical
cue; it does not use semantic similarity as authority. A tenant/project replay
includes global events unless an event is explicitly scoped to another tenant
or project.

Exact-ref replay matches refs already recorded on the approved learning unit:
`learning_event:<id>`, `source_carrier_refs`, `candidate_ref`, `approval_ref`,
parent learning-event refs, and externality-review refs. Tag replay matches
explicit `metadata.tag`, `metadata.tags`, `metadata.labels`, or
`metadata.capability_tags` entries. Partial matches are intentionally rejected.

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

The kernel service exposes the same replay boundary for app and agent
surfaces:

```text
GET  /kernel/learning-events
GET  /kernel/learning-events/replay?role=role.manager&tenant_id=tenant-a&cue=...
GET  /kernel/learning-events/replay?source_ref=multi_agent_attribution:packet_1
GET  /kernel/learning-events/replay?tag=trace_attribution
GET  /kernel/learning-events/summary
GET  /kernel/work-discovery?assigned_to=role.manager&tenant_id=tenant-a&cue=...
POST /kernel/learning-event-encounters
```

`GET /kernel/learning-events/replay` is read-only and deterministic. It returns
active approved events that match role, tenant/project scope, exact refs,
explicit tags, and lexical cue.
`GET /kernel/work-discovery` is the broader pre-work context projection. It
returns those same matching events, joins each event to outcome links and
routine-review state, includes matching discovery candidates, and returns a
`context_packet` digest over the exact refs/query basis. It is still read-only;
it does not record a learning encounter.
`POST /kernel/learning-event-encounters` records whether a later work surface
encountered, applied, ignored, or deferred an approved event. The service
rejects encounter telemetry for an unknown learning event id, so usage rows do
not drift away from approved learning state.

## Compounding

Learning compounds when an approved event explicitly derives from prior
approved events. Use `derived_from_learning_event_ids` or
`create_compounded_learning_event(...)` to preserve that lineage:

```text
learning carrier(s)
-> approved learning event A
-> approved learning event B
-> compounded approved learning event C
```

The default compounding helper requires source events to be active. That keeps
new routines from silently building on retired guidance. A caller can override
that for historical or migration cases, but the lineage remains recorded.

Compounding only records the new approved unit. It does not merge routines,
apply route changes, retire parent events, or decide outcome verdicts.

The CLI exposes the same path:

```bash
python -m cognitive_firm.orchestration.learning_events compound \
  --source-learning-event-id learn_source_gate \
  --source-learning-event-id learn_review_gate \
  --learning-unit-kind routine_change \
  --decision-use "Apply both gates for future matching work." \
  --future-application-cue "matching work cue" \
  --approved-by role.manager \
  --approval-ref review/compound-1
```

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

If the candidate implies a structural change to a mandate, role, route,
capability policy, gate, learning policy, project charter, or tenant policy,
use the governance proposal path instead:

```text
LearningTransitionCandidate
-> POST /kernel/learning-transition-candidates/{candidate_id}/governance-change
-> GovernanceChangeProposal
-> approval / decline
-> separate governed mutation if approved
```

This preserves candidate evidence while keeping approved learning events and
structural governance changes distinct.

## Resource Projection

`learning_event_resource(...)` projects an approved learning event into the
common [`Resource Envelope`](resource-envelope.md). The JSONL row remains
canonical; the projection is for adapters, dashboards, migrations, and
conformance fixtures:

```bash
python -m cognitive_firm.orchestration.learning_events list --resource
```

The resource links approval refs, source carriers, candidates, externality
reviews, and parent learning events.

## Learning-Unit Summary

`summarize_learning_events(...)` derives a compact health view over approved
learning units. It joins by typed IDs only:

- learning events for active/superseded/retired state, source carriers, review
  dates, and parent-unit lineage;
- learning-event encounters for whether future work saw, applied, ignored, or
  deferred a unit;
- outcome links for measured verdict coverage;
- routine reviews for overdue review pressure.

The CLI exposes the same read model:

```bash
python -m cognitive_firm.orchestration.learning_events summary
```

The summary owns no facts. It is an operator/adaptor view that helps answer:
"are approved learning units compounding, being encountered, measured, and
reviewed?"

The organization surface consumes the same summary, so the pre-work status view
does not only show active learning events. It also reports compounded units,
encountered units, outcome-link count, overdue routine reviews, and the next
recommended maintenance action:

```bash
python -m cognitive_firm.orchestration.org_surface \
  --learning-events-log org/learning_events/learning_events.jsonl \
  --learning-encounters-log org/learning_events/learning_encounters.jsonl \
  --outcome-links-log org/outcome_links/outcome_links.jsonl \
  --routine-reviews-log org/routine_reviews/routine_reviews.jsonl
```

## Research Anchor

This primitive sits between several established lines of work:

- Argyris and Schon: single-loop learning changes action within existing rules;
  double-loop learning changes governing rules, assumptions, or goals.
- March: learning systems must balance exploitation of known routines with
  exploration of alternatives.
- Crossan, Lane, and White: organizational learning moves from individual and
  group interpretation toward institutionalized practice.
- Nelson and Winter, plus later routine-dynamics work from Feldman and Pentland:
  routines are organizational memory, but they also change through variation,
  selection, retention, and repeated performance.
- Hierarchical reinforcement learning and cognitive-architecture work on
  options/chunking gives the computational analogue: useful experience becomes
  reusable higher-level units only when it has an applicability condition and a
  repeatable effect.
- Recent LLM-agent memory work provides a useful negative boundary. Reflexion
  (arXiv:2303.11366) stores verbal feedback for later trials; Generative Agents
  (arXiv:2304.03442) combines observation, reflection, and retrieval; MemGPT
  (arXiv:2310.08560) treats context as managed memory tiers; Voyager
  (arXiv:2305.16291) compounds skill libraries from execution feedback. The
  kernel does not import those runtime memories. It records approved learning
  units, context refs, encounters, outcomes, and review pressure so a runtime
  or userland surface can decide what to retrieve without making retrieval an
  authority source.

The kernel translation is deliberately narrow: a learning unit is not a note
or model memory; it is an approved, replayable behavior-change record with
evidence, scope, owner, lineage, and review/measurement surfaces.

## Tests

Covered by `tests/test_learning_events.py`.
