# Runtime Adapter Interface

**Status:** shipped as a framework-neutral adapter over run checkpoints.

The cognitive-firm daemon is the first-party governance runtime: it discovers
work, applies mandate and gate policy, dispatches role-bearing agent CLIs,
records transition rows, and feeds organization surfaces. External agent
frameworks own execution semantics when a tenant chooses to use them.

The runtime adapter interface is the boundary between those layers. It lets the
first-party daemon and optional external runtimes project lifecycle state into
the same `run.*` checkpoint surface.

## Why This Exists

The cognitive-firm daemon is intentionally not a graph/node execution engine.
It should not duplicate LangGraph's graph replay, CrewAI's crews/flows,
OpenAI Agents SDK tracing/handoffs, Google ADK deployment hooks, Microsoft
Agent Framework workflows, AutoGen AgentChat, or Letta memory.

Instead, the kernel accepts a small framework-neutral event stream:

```text
external runtime run -> runtime event -> cognitive-firm run checkpoint
```

For the first-party daemon, the external runtime name is
`cognitive_firm_daemon`. For optional framework integrations, the external
framework remains responsible for replay, node execution, tool calling, memory,
streaming, and provider-specific semantics. cognitive-firm records the
organizational view: which role office owns the work, what
objective it serves, what step was reached, which side effects were already
attempted, and whether the run is active, failed, or closed.

## Event Vocabulary

Runtime adapters emit four event kinds:

```text
started
checkpointed
state_changed
interrupted
```

`started` maps `(runtime_name, external_run_id)` to one cognitive-firm run using
the idempotency key:

```text
runtime:<runtime_name>:<external_run_id>
```

The mapping is stable across terminal states. Replaying a `started` event after
the projected run completed returns the original cognitive-firm run rather than
creating a second one. A genuine retry should use a new `external_run_id`.

`checkpointed` records a step id, checkpoint status, summary, optional payload
reference, and optional side-effect key.

`state_changed` records a projected run state: `running`, `paused`,
`completed`, `failed`, or `cancelled`.

`interrupted` records a runtime pause that needs human work. The kernel sets
the projected run state to `paused`, writes an interrupt checkpoint, and creates
an A2H human-work session. The external runtime owns the opaque `resume_ref`.

All events ultimately append canonical `run.*` transition rows via
`run_checkpoints`. Those rows include a `kernel_event` envelope. There is no
second runtime ledger.

## CLI Shape

```bash
python -m cognitive_firm.orchestration.runtime_adapters \
  --event-json '{
    "runtime_name": "langgraph",
    "external_run_id": "thread-1",
    "kind": "started",
    "owner_role": "role.manager",
    "actor": "role.manager",
    "objective": "run graph under governance"
  }'
```

## Runtime Boundary

| Concern | Graph/agent framework | cognitive-firm daemon | cognitive-firm run projection |
|---|---|---|
| graph/node replay | yes | no | no |
| work discovery | app-specific | yes | no |
| mandate and gate policy | app-specific | yes | no |
| tool execution | yes | dispatches agent CLIs and capability-gated MCP when configured | no |
| long-term agent memory | runtime-specific | session continuity hints | durable org state only |
| human interruption | runtime-specific resume token | A2H/H2A human-work session and STOP/PAUSE | paused run plus interrupt checkpoint |
| organizational authority | partial or app-defined | role YAML, mandate, tenant policy | observable projection |
| side-effect idempotency | runtime wrappers | task claims and gate dispatch marks | side-effect keys in checkpoints |
| audit and pre-work visibility | tracing/dashboard | transition rows and notifications | org surface |

## Adapter Rule

Adapters should be thin. The first-party daemon emits `RuntimeEvent` rows when
it dispatches and closes work. External adapters translate native runtime
callbacks into `RuntimeEvent` objects. They should not import tenant policy into
the kernel, and they should not ask an LLM to interpret runtime state before
writing a transition row.

If the framework already has a durable checkpointer, keep using it. The
cognitive-firm checkpoint is the organizational projection, not the execution
checkpoint.

## OpenTelemetry Projection

Use `cognitive_firm.orchestration.otel_export` when a deployment wants to send
run/checkpoint state to an observability backend. The projection follows the
OpenTelemetry GenAI vocabulary where it fits and keeps `cognitive_firm.*`
attributes for kernel-specific fields. It is a projection only.

## Tests

Covered by `tests/test_runtime_adapters.py`.
