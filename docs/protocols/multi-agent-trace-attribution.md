# Multi-Agent Trace Attribution

**Module:** `cognitive_firm.orchestration.multi_agent_trace_attribution`
**Status:** alpha evidence carrier.
**Tests:** `tests/test_multi_agent_trace_attribution.py`

Multi-agent trace attribution imports runtime-owned execution traces into
cognitive-firm as review evidence. It is for systems such as recursive
delegation runtimes, team-evolution experiments, phase-based agent teams, or
protocol-test harnesses that already know how they execute work.

The kernel does not execute those agents here. It records what the runtime says
happened, summarizes delegation/failure signals, and emits governed carriers
that can feed existing review paths.

## Boundary

This primitive does:

- record trace events from external or first-party harnesses;
- preserve local-agent and cross-agent evidence;
- summarize recursive-delegation signals such as abstention, failed handoffs,
  verifier failures, overcommitment, and undercommitment;
- project trace events into an observer-only `DelegationGraph`;
- create `FailureAttributionPacket` records;
- project a packet into an observer-only `LearningTransitionCandidate`;
- expose resource-envelope projections for adapters and dashboards.

It does not:

- spawn agents;
- decide delegation structure;
- approve learning or governance changes;
- mutate roles, mandates, charters, protocols, or policies;
- replace run checkpoints, action attestations, outcome links, or governed-run
  bundles.

## Trace Event

`MultiAgentTraceEvent` is one imported event from a runtime-owned trace.

Core fields:

- `event_id`;
- `runtime_name`;
- `external_run_id`;
- `cognitive_run_id`;
- `event_kind`;
- `agent_id`;
- `parent_agent_id`;
- `target_agent_id`;
- `owner_role`;
- `status`;
- `summary`;
- `payload_ref`;
- `token_count`;
- `cost_units`;
- `source_refs`;
- `metadata`.

Supported `event_kind` values are:

- `agent_spawned`;
- `agent_completed`;
- `message`;
- `handoff`;
- `tool_call`;
- `verifier_verdict`;
- `abstention`;
- `delegation_wait`;
- `custom`.

Supported statuses are `observed`, `succeeded`, `failed`, `blocked`,
`abstained`, and `unknown`.

The default filesystem log is:

```text
org/multi_agent_traces/trace_events.jsonl
```

## Failure Attribution Packet

`FailureAttributionPacket` is the governed carrier. It joins local findings,
cross-agent evidence, diagnostics, risk/rollback notes, and a proposed carrier
kind.

Supported proposed carriers:

- `learning_transition`;
- `governance_change`;
- `policy_promotion`;
- `none`.

The packet is review-ready only when it has enough evidence for its proposed
carrier. For example, a governance-change packet also needs risk and rollback
text. A review-ready packet still does not mutate state; it is evidence for a
future learning, governance, or policy-promotion path.

The default filesystem log is:

```text
org/multi_agent_traces/attribution_packets.jsonl
```

## Diagnostics

`summarize_delegation_diagnostics(...)` computes conservative graph-shape
signals:

- `n_events`;
- `n_agents`;
- `n_edges`;
- `max_depth`;
- `abstentions`;
- `failed_handoffs`;
- `verifier_failures`;
- `overcommitment_detected`;
- `undercommitment_detected`;
- `notes`.

These are observability signals, not automatic judgments. They help a reviewer
notice a small graph doing too much work, a long delegation chain doing too
little work, missing authority, failed handoffs, or verifier failures.

## Delegation Graph Projection

`build_delegation_graph(...)` projects trace events into a portable graph:

- `graph_id`;
- `runtime_name`;
- `external_run_id`;
- `cognitive_run_id`;
- `nodes`;
- `edges`;
- `source_event_ids`;
- `diagnostics`;
- `observer_only = true`.

Nodes summarize agent ids, owner roles, root status, event counts, event kinds,
and statuses. Edges summarize source/target agent ids, event ids, event kinds,
statuses, and whether any edge event failed or blocked.

The graph is a read model. It helps Orbit, demos, audits, and runtime adapters
show recursive delegation shape without deciding delegation policy or moving
execution into the kernel.

## Learning Candidate Projection

`learning_candidate_from_attribution_packet(...)` projects a packet into a
`LearningTransitionCandidate` with:

- `source_kind = "multi_agent_failure_attribution"`;
- `observer_only = true`;
- source refs for the attribution packet and each trace event;
- diagnostics and source evidence in `proposed_payload`.

The learning candidate remains a candidate. It becomes organizational learning
only after the approved-learning-event path accepts it.

## Resource Projection

The module exposes:

```text
trace_event_resource(...)
attribution_packet_resource(...)
delegation_graph_resource(...)
```

All return the common resource envelope for adapters, dashboards, conformance
fixtures, and migrations.

The kernel service exposes write routes for imported execution evidence plus
read projections:

```text
POST /kernel/multi-agent-trace-events
GET /kernel/multi-agent-trace-events
GET /kernel/multi-agent-trace-events?resource=true
POST /kernel/failure-attribution-packets
GET /kernel/failure-attribution-packets
GET /kernel/failure-attribution-packets?resource=true
GET /kernel/delegation-graph?runtime_name=<runtime>&external_run_id=<run>
GET /kernel/delegation-graph?runtime_name=<runtime>&external_run_id=<run>&resource=true
```

The POST routes append observer-only evidence carriers. They do not mutate
roles, mandates, protocols, or policy; packets can feed reviewed learning or
governance proposals through the existing approval paths.

Review-ready packets are projected into the service learning-candidate queue:

```text
GET /kernel/learning-transition-candidates?source=attribution
GET /kernel/learning-transition-candidates?source=execution
```

## CLI

Inspect event and packet logs:

```bash
cognitive-firm-multi-agent-traces list-events
cognitive-firm-multi-agent-traces list-packets
cognitive-firm-multi-agent-traces diagnose \
  --runtime-name redel-fixture \
  --external-run-id demo-run
cognitive-firm-multi-agent-traces graph \
  --runtime-name redel-fixture \
  --external-run-id demo-run \
  --resource
```

Use `--resource` on list commands to print resource-envelope projections.

## Demo Role

The self-evolving organization demo can use this primitive to show the next
step beyond deterministic structural changes:

```text
runtime trace
-> trace events
-> failure attribution packet
-> learning transition / governance proposal / policy-promotion carrier
-> approval path
-> state transition
-> outcome link and bundle
```

That keeps cognitive-firm positioned as the governance layer around execution
runtimes, not as a replacement runtime.

## Research Anchor

This primitive is grounded in provenance and distributed execution tracing:

- W3C PROV, for representing activities, agents, entities, and derivation
  without making the provenance graph the source of truth:
  <https://www.w3.org/TR/prov-overview/>.
- OpenTelemetry traces, for importing runtime spans/events as observability
  evidence rather than as authority: <https://opentelemetry.io/docs/concepts/signals/traces/>.
- Lamport's happened-before relation, for why causal ordering matters when
  diagnosing distributed activity: <https://doi.org/10.1145/359545.359563>.
- Pearl-style causal caution, for separating observed association from
  intervention claims. A public book page is
  <https://bayes.cs.ucla.edu/BOOK-2K/>.

The kernel therefore records trace events, delegation graphs, and attribution
packets as observer-only carriers. Structural mutation still requires the
ordinary learning, proposal, approval, proof, and outcome paths.
