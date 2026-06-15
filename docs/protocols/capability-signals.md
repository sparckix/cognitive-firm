# Capability Signals

**Module:** `cognitive_firm.orchestration.capability_signals`
**Status:** alpha routing-evidence carrier.
**Tests:** `tests/test_capability_signals.py`, `tests/test_capability_signal_demo.py`

Capability signals record cases where a worker, runtime, role office, or
authorization gate should not proceed with a piece of work as currently
specified. The core distinction is that a grounded abstention or capability gap
is not automatically a task failure.

## Boundary

This carrier does:

- record abstention, insufficient authority, capability gap, evidence gap, tool
  unavailable, budget exceeded, overload, unsafe request, or custom signals;
- record severity and whether the signal counts as failure;
- preserve source, run, work item, capability, threshold, and evidence refs;
- record a selected route such as reassignment, escalation, evidence request,
  capability request, learning candidate, governance change, or no action;
- close the signal with a receipt;
- expose a resource-envelope projection and summary counts.

It does not:

- grant capabilities;
- execute reassignment;
- mutate work items;
- approve governance changes;
- replace A2A refusal or MCP capability checks.

A2A refusal remains the communication-obligation terminal. MCP capability
checks remain the tool-dispatch gate. Capability signals are the portable
work-routing evidence that those and other surfaces can emit.

Service clients can either call the primitive routes directly or use
`POST /kernel/execution-evidence/route` for the common adapter case. That
composition records the signal, routes it, exposes the matching observer-only
learning candidate, and can draft a governance proposal for review. It still
does not approve governance, change files, or retry the runtime.

## Signal

`CapabilitySignal` is the replayed projection over append-only signal events.

Important fields:

- `signal_id`;
- `signal_kind`;
- `severity`;
- `status`;
- `source_ref`;
- `summary`;
- `owner_role`;
- `worker_ref`;
- `run_id`;
- `work_id`;
- `capability_ref`;
- `threshold_ref`;
- `recommended_route`;
- `counts_as_failure`;
- `evidence_refs`.

Supported signal kinds:

- `abstention`;
- `insufficient_authority`;
- `capability_gap`;
- `evidence_gap`;
- `tool_unavailable`;
- `budget_exceeded`;
- `overload`;
- `unsafe_request`;
- `custom`.

Supported routes:

- `reassign_work`;
- `escalate_to_principal`;
- `request_evidence`;
- `request_capability`;
- `open_learning_candidate`;
- `open_governance_change`;
- `no_action`.

## Why This Is Separate From Failure

Failure says the work was attempted and did not satisfy its exit condition. A
capability signal says the current worker or route should not attempt the work
yet, or should not attempt it at all. Examples:

- evaluator abstains because evidence refs are missing;
- runtime lacks the required tool;
- authorization gate detects insufficient authority;
- worker pool reports overload and asks for reassignment;
- request is unsafe and should escalate.

The default `counts_as_failure=false` prevents the system from punishing
appropriate abstention while still making the routing problem visible.

## Resource Projection

`capability_signal_resource(...)` projects the replayed signal into the common
resource envelope for dashboards, adapters, and conformance fixtures.

The kernel service exposes write routes for signal evidence plus read
projections:

```text
POST /kernel/capability-signals
POST /kernel/capability-signals/{signal_id}/route
POST /kernel/capability-signals/{signal_id}/close
GET /kernel/capability-signals
GET /kernel/capability-signals?resource=true
GET /kernel/capability-signals?summary=true
```

These routes make abstention, evidence gaps, authority gaps, and routing
receipts first-class work signals. They do not grant capability or authority by
themselves.

Open signals are projected into the service learning-candidate queue:

```text
GET /kernel/learning-transition-candidates?source=capability
GET /kernel/learning-transition-candidates?source=capability&include_closed=true
```

This lets a truthful abstention become reviewable learning evidence without
treating it as task failure.

## CLI

Inspect signals:

```bash
cognitive-firm-capability-signals list
cognitive-firm-capability-signals list --resource
cognitive-firm-capability-signals summary
```

## Demo Role

The no-cost demo records one evidence-based abstention that routes to evidence
repair and one authority gap that routes to escalation:

```bash
make capability-signal-demo
```

This is a small routing-evidence carrier for agent runtimes and work queues,
not a worker ontology and not a general execution engine.

## Research Anchor

Capability signals sit at the boundary between execution, uncertainty, and
authority:

- Selective prediction / classification with a reject option, for treating a
  grounded abstention as useful information rather than ordinary failure. See
  Chow, "On Optimum Recognition Error and Reject Tradeoff":
  <https://doi.org/10.1109/TIT.1970.1054496>.
- Human-AI interaction guidance, for allowing systems to show uncertainty,
  route to people, and preserve human judgment instead of forcing false
  completion. See Amershi et al., "Guidelines for Human-AI Interaction":
  <https://doi.org/10.1145/3290605.3300233>.
- Backpressure and overload handling in distributed systems, for surfacing
  overload as a routing signal rather than letting queues fail invisibly. A
  public index is <https://en.wikipedia.org/wiki/Back_pressure>.

The kernel records the signal and route recommendation. It does not grant new
authority, capabilities, tools, or budget, and it does not decide that the work
failed unless the caller explicitly marks the signal that way.
