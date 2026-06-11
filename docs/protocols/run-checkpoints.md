# Run Checkpoint Interface

**Status:** shipped as a transition-log-backed T1 interface.

This interface is the cognitive-firm parity point with durable execution
runtimes. The first-party daemon executes governed role-office work; external
frameworks may own graph replay. In both cases, cognitive-firm records
long-running role-office work as canonical transition events, then derives
current run state by replaying the transition log.

## Prior Decision

The repo already selected the transactional-outbox pattern for external action:
the kernel writes once to `transitions.jsonl`, and everything else is derived
from it. The local filesystem JSONL file is an adapter. At T2 this becomes a
Postgres outbox or event stream with the same logical events.

Run checkpoints follow the same rule. They do not create a second durable
ledger.

## Event Types

All events use `cognitive_firm.orchestration.transition_log.append_transition`.
Every transition row includes a `kernel_event` envelope, and callers can pass
an `EventSource` to route the same row through the state-backend boundary.

```text
run.started
run.checkpointed
run.state_changed
```

`run.started` records run identity, owner role, objective, tenant/project ids,
and an optional idempotency key.

`run.checkpointed` records a step id, status, summary, optional payload ref, and
optional side-effect key.

`run.state_changed` records terminal or pause state.

## Commands

```bash
python -m cognitive_firm.orchestration.run_checkpoints start \
  --owner-role role.manager \
  --objective "sync reviewed forecast state" \
  --idempotency-key forecast-sync-demo

python -m cognitive_firm.orchestration.run_checkpoints checkpoint run_... \
  --actor role.manager \
  --step-id fetch_source \
  --status completed \
  --summary "source fetched and stored" \
  --payload-ref artifacts/source.json \
  --side-effect-key fetch:source:abc123

python -m cognitive_firm.orchestration.run_checkpoints resume run_...

python -m cognitive_firm.orchestration.run_checkpoints state run_... \
  --actor role.manager \
  --state completed
```

## Service Flow

The kernel service exposes the same transition-log-backed interface for app
and runtime adapters:

```text
POST /kernel/runs
GET  /kernel/runs?state=running&tenant_id=...
GET  /kernel/runs/<run_id>
GET  /kernel/runs/<run_id>/resume
POST /kernel/runs/<run_id>/checkpoints
POST /kernel/runs/<run_id>/state
```

The write routes append `run.*` transition rows; they do not create a second
run store. The read routes rebuild projections from the configured transition
log, so an external runtime, Orbit surface, or CLI sees the same run state.

## Semantics

- Active runs with the same idempotency key project to the existing run.
- Checkpoints are derived from transition replay, not from a separate state
  file.
- Repeated side-effect keys produce a `skipped` checkpoint event.
- Terminal runs reject further checkpoint events.

## LangGraph Boundary

LangGraph owns graph-runtime concerns: node execution, persistence, interrupts,
streaming, and replay. cognitive-firm should remain the governance kernel above
runtimes.

| Concern | Runtime layer | cognitive-firm layer |
|---|---|---|
| graph/node replay | LangGraph or another runtime | out of scope |
| durable run memory | checkpointer | transition-log replay |
| side-effect idempotency | task wrappers and idempotency keys | side-effect keys in checkpoint events |
| human interruption | runtime interrupt | gates, H2A, human work, run state |
| organizational authority | application policy | mandate, role office, tenant policy |

If a tenant uses LangGraph, the role office can run the graph and emit
`run.*` events into cognitive-firm so the organization can inspect progress
without importing runtime-specific semantics into the kernel.
