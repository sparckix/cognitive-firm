# Protocol Experiments

**Module:** `cognitive_firm.orchestration.protocol_experiments`
**Status:** alpha telemetry carrier.
**Tests:** `tests/test_protocol_experiments.py`, `tests/test_protocol_experiment_demo.py`

Protocol experiments record bounded evidence about coordination patterns such
as coordinator, sequential, batched sequential, shared, and broadcast. They are
for comparing protocol behavior before proposing a route-policy change.

## Boundary

This carrier does:

- start an experiment with candidate protocols and a baseline;
- record observations with quality, latency, cost, abstention, failure, and
  guardrail counters;
- summarize evidence by protocol;
- block reports when evidence is insufficient or guardrails are violated;
- emit an observer-only governance-change candidate when a candidate protocol
  beats the baseline by the configured threshold;
- project review-ready reports into observer-only `route_policy_change`
  learning-transition candidates;
- expose a resource-envelope projection.

It does not:

- execute agents;
- pick live routing policy;
- mutate protocol definitions;
- approve governance changes;
- replace runtime-specific evaluation harnesses.

Adapters and demo harnesses can emit protocol observations. cognitive-firm
records the evidence and routes any recommended change through governance.

## Experiment

`ProtocolExperiment` is the replayed projection over append-only experiment
events.

Important fields:

- `experiment_id`;
- `objective`;
- `owner_role`;
- `candidate_protocols`;
- `baseline_protocol`;
- `objective_metric`;
- `observations`;
- `reports`.

Experiment statuses are `active`, `reported`, and `blocked`.

## Observations

`ProtocolExperimentObservation` records one measured task outcome for one
candidate protocol.

Important fields:

- `protocol`;
- `task_ref`;
- `quality_score`;
- `latency_units`;
- `cost_units`;
- `abstentions`;
- `failures`;
- `guardrail_violations`;
- `evidence_refs`.

Scores are deliberately simple. Runtimes may use richer local metrics, but the
kernel carrier keeps the governance evidence portable.

## Reports

`ProtocolExperimentReport` summarizes observations and may include a
`governance_change_candidate` with `change_kind=route_policy_change`.

A report is blocked when:

- any candidate has fewer than the required observations;
- the baseline has no observations;
- guardrail violations exceed the configured threshold;
- the best candidate does not beat the baseline by the configured quality
  delta.

When the report is `review_ready`, it is still only evidence. A governance
proposal, approval, and state transition are required before any protocol or
routing behavior changes.

## Learning Candidate Projection

`learning_candidate_from_protocol_experiment_report(...)` projects a
`review_ready` report into a `LearningTransitionCandidate` with
`transition_kind=route_policy_change`.

This projection:

- rejects blocked reports;
- preserves the report, recommended protocol, summaries, and embedded
  governance-change candidate as evidence payload;
- links the protocol experiment and report in `source_refs`;
- remains `observer_only`.

The kernel service includes these candidates under:

```text
GET /kernel/learning-transition-candidates?source=execution
GET /kernel/learning-transition-candidates?source=protocol_experiment
```

Promotion still goes through
`POST /kernel/learning-transition-candidates/{candidate_id}/governance-change`
and the normal evidence sufficiency checks.

## Resource Projection

`protocol_experiment_resource(...)` projects the replayed experiment into the
common resource envelope for dashboards, adapters, and conformance fixtures.

The kernel service exposes write routes for experiment evidence plus read
projections:

```text
POST /kernel/protocol-experiments
POST /kernel/protocol-experiments/{experiment_id}/observations
POST /kernel/protocol-experiments/{experiment_id}/reports
GET /kernel/protocol-experiments
GET /kernel/protocol-experiments?resource=true
```

Reports may include a governance-change candidate, but the candidate is review
evidence only. Promotion still requires the governance-change proposal and
approval path.

## CLI

Inspect experiments:

```bash
cognitive-firm-protocol-experiments list
cognitive-firm-protocol-experiments list --resource
```

## Demo Role

The no-cost demo compares coordinator, sequential, and batched sequential
patterns, emits a review-ready route-policy candidate, promotes that learning
candidate into a governance-change proposal through the kernel service, and
records an approval event:

```bash
make protocol-experiment-demo
```

The demo still does not auto-mutate routing behavior. It proves the evidence
and review path for coordination changes. It is not a competing agent runtime.

## Research Anchor

This primitive borrows the experimental discipline, not the domain assumptions,
from:

- Fisher-style experimental design and the broader design-of-experiments
  tradition: compare protocols under a declared metric and guardrails before
  promotion. A public index is <https://en.wikipedia.org/wiki/Design_of_experiments>.
- March's exploration/exploitation problem in organizational learning:
  <https://doi.org/10.1287/orsc.2.1.71>.
- Contextual-bandit offline evaluation, especially the distinction between
  observed local reward and safe policy promotion. See Li, Chu, Langford, and
  Wang, "A Contextual-Bandit Approach to Personalized News Article
  Recommendation": <https://arxiv.org/abs/1003.5956>.

Those anchors justify the boundary: protocol experiments produce reviewable
evidence and candidates. They do not silently change coordination rules, route
policy, authority, or runtime behavior.
