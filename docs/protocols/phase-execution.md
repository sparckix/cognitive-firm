# Phase Execution Overlay

**Module:** `cognitive_firm.orchestration.phase_execution`
**Status:** alpha execution overlay.
**Tests:** `tests/test_phase_execution.py`, `tests/test_phase_execution_demo.py`

The phase execution overlay records a thin Strategy -> Execution ->
Verification recipe over existing kernel surfaces. It borrows the useful
manager/verifier separation pattern from long-running agent teams without
making cognitive-firm a general agent runtime.

## Boundary

This overlay does:

- record a bounded phase execution plan;
- record strategy, execution, and verification directives;
- record verifier feedback;
- decay retry budget after failed, blocked, or inconclusive verification;
- block a plan when attempts or budget are exhausted;
- project blocked/failed plans into observer-only learning-transition
  candidates;
- expose a resource-envelope projection.

It does not:

- execute agents;
- own software-development semantics;
- choose models or tools;
- approve governance changes;
- mutate roles, mandates, charters, protocols, or policies.

Runtime adapters, agent harnesses, or deterministic demos can emit phase
records. cognitive-firm records the organizational evidence.

## Plan

`PhaseExecutionPlan` is the replayed projection over append-only phase events.

Important fields:

- `plan_id`;
- `objective`;
- `owner_role`;
- `status`;
- `current_phase`;
- `remaining_budget_units`;
- `max_attempts`;
- `attempts`;
- `run_id`;
- `work_id`;
- `directives`;
- `feedback`.

Plan statuses are `active`, `passed`, `failed`, `blocked`, and `cancelled`.

## Directives

`PhaseDirective` records what a role or runtime intended for one phase.
Supported phases:

- `strategy`;
- `execution`;
- `verification`.

Directives can carry:

- `directive`;
- `issued_by`;
- `budget_units`;
- `evidence_refs`;
- `output_refs`;
- `run_id`;
- `work_id`;
- `metadata`.

## Verification Feedback

`VerificationFeedback` records independent verifier feedback. Verdicts:

- `passed`;
- `failed`;
- `blocked`;
- `inconclusive`.

Failed, blocked, and inconclusive feedback decay `remaining_budget_units` by
`budget_decay`. If attempts reach `max_attempts` or the next budget falls below
the configured floor, the plan becomes `blocked`.

This gives long-running agent work an explicit bounded-loop record:

```text
strategy directive
-> execution directive
-> verification feedback fails
-> retry budget decays
-> execution retry or blocked state
```

## Learning Candidate Projection

Blocked or failed phase plans can be projected into
`LearningTransitionCandidate` rows with
`learning_candidate_from_phase_execution_plan(...)`.

This projection is intentionally narrow:

- passed plans do not create candidates;
- candidates are `observer_only`;
- source refs include the phase plan, run/work refs, directive refs, directive
  evidence/output refs, feedback refs, and verification evidence refs;
- the candidate suggests a review surface such as `evidence_gap`,
  `source_repair`, `mandate_review`, `human_work_session`, or `role_review`;
- no mandate, route, charter, threshold, or policy changes are applied.

The kernel service includes these candidates under the existing execution
carrier stream:

```text
GET /kernel/learning-transition-candidates?source=execution
GET /kernel/learning-transition-candidates?source=phase_execution
```

This closes the execution-to-learning path without turning the overlay into an
agent runtime.

## Resource Projection

`phase_execution_plan_resource(...)` projects the replayed plan into the common
resource envelope for dashboards, adapters, and conformance fixtures.

The kernel service exposes write routes for phase evidence plus read
projections:

```text
POST /kernel/phase-execution-plans
POST /kernel/phase-execution-plans/{plan_id}/directives
POST /kernel/phase-execution-plans/{plan_id}/verification-feedback
GET /kernel/phase-execution-plans
GET /kernel/phase-execution-plans?resource=true
```

These routes record phase directives and verifier feedback. They do not run
agents and do not change mandates or routing policy without a separate
governance proposal.

## CLI

Inspect plans:

```bash
cognitive-firm-phase-execution list
cognitive-firm-phase-execution list --resource
```

## Demo Role

The no-cost demo shows a failed first verification, budget decay, a second
execution directive, and a passed verification:

```bash
make phase-execution-demo
```

This is intentionally small. It is a first-party harness pattern for the
self-evolving organization demo, not a replacement for runtimes such as Codex,
Claude, LangGraph, ReDel, or custom tenant systems.

## Research Anchor

This overlay is grounded in staged work and control-loop traditions, but keeps
their policy content out of the kernel:

- Plan-do-check-act / Shewhart-Deming quality loops, for making verification
  a first-class stage rather than a post-hoc note. See the Deming Institute
  overview: <https://deming.org/explore/pdsa/>.
- Software verification and validation practice, for separating construction
  from independent evidence of fitness. The V-model is a useful public index:
  <https://en.wikipedia.org/wiki/V-model>.
- March's exploration/exploitation framing, for treating retries and route
  experiments as budgeted learning rather than unbounded loops:
  <https://doi.org/10.1287/orsc.2.1.71>.

The shipped primitive is deliberately narrower than those traditions: it records
phase directives, verifier feedback, and budget decay as evidence. It does not
own scheduling, model choice, authority, or routing policy.
