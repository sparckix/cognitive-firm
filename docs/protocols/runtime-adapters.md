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

The cognitive-firm daemon executes governed role-office work: it discovers
tasks, applies mandate and gate policy, dispatches configured agent CLIs and
capability-gated tools, records checkpoints, and routes human interrupts. Its
execution surface is organizational rather than framework-native: graph replay,
crews/flows, provider tracing, deployment hooks, AgentChat semantics, and
long-term agent memory stay with the runtime selected for that job.

Instead, the kernel accepts a small framework-neutral event stream:

```text
external runtime run -> runtime event -> cognitive-firm run checkpoint
```

For the first-party daemon, the external runtime name is
`cognitive_firm_daemon`. For optional framework integrations, the external
framework remains responsible for replay, node execution, native tool calling,
memory, streaming, and provider-specific semantics. cognitive-firm records and
can itself execute the organizational view: which role office owns the work,
what objective it serves, what step was reached, which side effects were
already attempted, and whether the run is active, failed, or closed.

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

## Packaging Runtime Integrations

A framework integration has two parts:

1. **Executable adapter code.** This is ordinary runtime-specific code. For
   LangGraph, it can be a Python package that calls `record_runtime_event` from
   graph lifecycle hooks. For a non-Python runtime, it can be a sidecar process
   or local command that emits the same JSON event shape through the CLI. This
   code is installed by the host platform, not by the organization package
   installer.
2. **Governance package.** This is a `cognitive-firm-distro` overlay. It can
   install roles, mandates, example project charters, extension schemas,
   capability policy, conformance-fixture config, and post-install instructions
   for the adapter.

First-party adapter packs should follow that split. A `langgraph-runtime-adapter`
overlay would make the integration easy to adopt, while the adapter module
itself remains testable and replaceable. The kernel contract stays the same for
LangGraph, LangChain, AutoGen, CrewAI, Letta, a shell script, or a hosted
workflow engine: emit `started`, `checkpointed`, `interrupted`, and
`state_changed` events with stable external run ids.

The bundled `langgraph-runtime-adapter` overlay is the reference adapter-policy
package for this split. It installs an adapter manifest plus
`adapter_conformance/langgraph-runtime-adapter.json`; it does not install
LangGraph or executable adapter code. Review it with:

```bash
cognitive-firm-distro preview-overlay langgraph-runtime-adapter \
  --into <org> \
  --json
```

Then validate the installed manifest/config pair:

```bash
cognitive-firm-adapter-conformance validate-conformance \
  adapter_conformance/langgraph-runtime-adapter.json \
  --manifest adapters/langgraph-runtime-adapter.yaml \
  --evidence-root .
```

## OpenTelemetry Projection

Use `cognitive_firm.orchestration.otel_export` when a deployment wants to send
run/checkpoint state to an observability backend. The projection follows the
OpenTelemetry GenAI vocabulary where it fits and keeps `cognitive_firm.*`
attributes for kernel-specific fields. It is a projection only.

## Tests

Covered by `tests/test_runtime_adapters.py`.
