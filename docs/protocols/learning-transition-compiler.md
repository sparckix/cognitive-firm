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
- source-improvement backlog items exposed by intelligence-source coverage;
- repeated A2H human-work pressure groups.
- repeated or critical damage-signal patterns.
- routed attention signals from the L1 attention router when explicitly
  requested through the service projection.

The organization surface already joins evidence gaps, human work, damage
signals, failed runs, forecast-market state, action-impact state, and invalid
project charters. The compiler consumes that joined surface rather than
inventing a second source of truth.

The kernel service also exposes execution-evidence projections as learning
transition candidates:

- review-ready failure-attribution packets from multi-agent traces;
- open capability signals, including abstentions, evidence gaps, authority
  gaps, tool gaps, budget pressure, overload, and unsafe-request signals.
- blocked/failed phase-execution plans from bounded Strategy -> Execution ->
  Verification loops.
- review-ready protocol-experiment reports for route-policy changes.

Use:

```text
GET /kernel/learning-transition-candidates
GET /kernel/learning-transition-candidates?source=human_work
GET /kernel/learning-transition-candidates?source=attention
GET /kernel/learning-transition-candidates?source=execution
GET /kernel/learning-transition-candidates?source=phase_execution
GET /kernel/learning-transition-candidates?source=protocol_experiment
GET /kernel/learning-transition-candidates?source=capability&include_closed=true
```

`source=all` combines org-surface candidates with execution-evidence
candidates. `source=human_work` filters the org-surface-derived candidates to
A2H pressure groups. `source=attention` compiles the current routed attention
feed into candidates for unrouted governance/work signals, stale actionable
signals, and repeated pressure on one role/signal class. `source=execution`
returns attribution, capability-signal, phase-execution, and
protocol-experiment candidates. Closed capability signals are excluded unless
`include_closed=true` is set.

The userland command mirrors the route:

```bash
cognitive-firm-userland learning-candidates --source human_work
cognitive-firm-userland learning-candidates --source attention
```

Human-work pressure candidates cite the affected `human_work_session:<id>`
refs. Access pressure usually maps to a source-repair candidate; labor or
cognition pressure maps to mandate review; safety or authority pressure maps to
route-policy review. These are review questions only. The compiler does not
automate, reroute, close, or reinterpret bounded human work.

Damage-pattern candidates cite the underlying `damage_signal:*` refs and are
thresholded: repeated warning-level signals of one kind or any critical signal
can become an observer-only `mandate_review` candidate. The candidate can ask
whether an accountability case, mandate review, route-policy review, routine
retirement review, or accepted-risk review is warranted. It does not
quarantine, block, reroute, or create an accountability case.

Attention candidates cite the underlying attention source refs and stay
observer-only. They can suggest that a human review authority domains, actor
memberships, mandate wording, route policy, or receipt discipline, but they do
not reroute, page, assign, close, or schedule work.

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
- `route_policy_change`;
- `action_impact_repair`;
- `source_repair`;
- `role_review`.

These are candidate kinds, not direct writes. A tenant may bind candidates to a
manager inbox, review queue, issue tracker, or private workflow.

## Governance Proposal Promotion

The kernel service can create a governance-change proposal from one candidate:

```text
POST /kernel/learning-transition-candidates/{candidate_id}/governance-change
cognitive-firm-userland proposal-from-candidate <candidate_id> --target-ref <ref>
```

The request must still provide the concrete `target_ref`, expected behavior
change, risk summary, rollback plan, and invariant checks. The candidate
supplies rationale and source refs; it does not make the proposal review-ready
by itself. The normal governance-change evidence sufficiency gate decides
whether the result is `review_ready` or `blocked`.

This route is useful for live agents and review UIs because it preserves the
candidate's source refs and metadata while still forcing the proposal through
the same governance path as any other self-modification request.

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
