# State Backends

**Status:** T1 filesystem implementation shipped; lean SQLite event source and
SQLite transactional mutation backend shipped as T2 migration targets.
**Module:** `cognitive_firm.orchestration.state_backends`
**Tests:** `tests/test_state_backends.py`

The cognitive-firm kernel treats storage as a `SourceConnector` boundary.
Kernel primitives should depend on logical event and artifact contracts, not on
a specific database product.

`SourceConnector` is the generic connector label for kernel-adjacent sources:

| Connector family | Purpose |
|---|---|
| `state_backend` | Kernel state transport: events and artifacts. |
| `enterprise_system` | ERP, issue tracker, CRM, or other external system reached through MCP. |
| `runtime` | External execution runtime projected through runtime adapters. |
| `app_surface` | UI or operator surface that submits typed kernel-service requests. |
| `inbound_event` | External webhook/event-stream observation entering quarantine/projection. |
| `notification` | Human-facing notification provider. |
| `identity_provider` | Authenticates request subjects; kernel maps them to actor authority. |
| `tenant_adapter` | Tenant-owned read models or domain ledgers. |

This document defines the `state_backend` family. MCP remains the connector
family for enterprise systems such as Linear, Salesforce, ERPs, and ticketing.

## T1: Filesystem Backend

The default backend is intentionally boring:

- append-only JSONL event streams;
- JSON artifacts under a workspace directory;
- git and local backup as operational recovery;
- one principal or a small trusted operator set.

This is enough for local use, single-host daemons, tenant experiments, and
public examples. It is not a multi-host transactional system.

Git is not the runtime transport. It is the audit, rollback, and sync layer
around the filesystem backend. Live coordination should happen through kernel
commands, app-surface APIs, notification channels, and outboxes; Git records
the durable history of those state changes.

## Lean T2: SQLite Event Source

The smallest T2 step is not a platform rewrite. There are two SQLite adapters:

- `SqliteEventSource` for ordered event append/read;
- `SqliteMutationBackend` for lease-fenced mutation events.

`SqliteEventSource` preserves the append/read contract while moving ordered
events into a database file:

```python
from pathlib import Path
from cognitive_firm.orchestration.state_backends import SqliteEventSource
from cognitive_firm.orchestration.transition_log import append_transition

events = SqliteEventSource(path=Path("kernel_events.sqlite3"))
events.append_event("transitions", {"event": "run.started", "run_id": "run_1"})
rows = events.read_events("transitions")

append_transition(
    event="run.started",
    actor="role.manager",
    surface="run_checkpoints",
    subject="run_1",
    payload={"run_id": "run_1"},
    event_source=events,
)
```

This gives adopters a migration path for:

- stronger local transactional append semantics;
- easier backups and snapshots;
- simpler handoff to Postgres or another hosted event store later.

Each transition row written through this path carries a `kernel_event`
envelope, so consumers can migrate from legacy transition fields to the
canonical event contract without changing the logical stream.

It does not by itself provide enterprise identity, signed audit, RBAC, or
multi-tenant policy. Those remain separate T2 upgrades.

## Transactional Lease Fencing

Use `SqliteMutationBackend` when the mutation and the lease check must be one
transaction:

```python
from pathlib import Path
from cognitive_firm.orchestration.state_backends import SqliteMutationBackend

backend = SqliteMutationBackend(path=Path("kernel_mutations.sqlite3"))
lease = backend.acquire_lease(
    resource_ref="human_work:hws_123",
    actor_id="human.alice",
    role_id="role.manager",
)

backend.guarded_append_event(
    stream="transitions",
    event={"event": "human_work.integrated", "subject": "hws_123"},
    resource_ref="human_work:hws_123",
    lease_id=lease["lease_id"],
    actor_id="human.alice",
    fencing_token=lease["fencing_token"],
)
```

`guarded_append_event(...)` executes `BEGIN IMMEDIATE`, reads the active lease,
checks the actor and fencing token, and appends the event before committing. A
stale lease id, wrong actor, expired lease, or mismatched fencing token aborts
the transaction and no event row is written.

The Postgres version should keep the same shape: lease row and mutation event
in one transaction, with `SELECT ... FOR UPDATE` or an equivalent write lock on
the lease/resource row before inserting the mutation event.

The module also exposes Postgres schema/transaction SQL helpers:

- `postgres_transactional_mutation_schema_sql()`
- `postgres_guarded_append_transaction_sql()`

The module also ships `PostgresMutationBackend`, an optional psycopg-backed
adapter for deployments that provide `psycopg` and a connection string or
connection factory. It preserves the same contract as SQLite and uses
transaction-scoped advisory locking plus row locks for resource fencing.

## Service API Boundary

The public kernel can be driven through Python commands today. A REST or RPC
service is an app/deployment boundary over the same commands, not a different
source of truth. Add it when an adopter needs remote clients, concurrent
operators, or a non-Python app surface. Do not make Orbit, Slack, or a tenant
dashboard reimplement primitive lifecycle rules.

The kernel service can run the SQLite mutation backend:

```bash
cognitive-firm-kernel-service --mutation-backend sqlite
```

In that mode, lease acquisition/release and `/kernel/mutation-events` share the
same SQLite database. Primitive-specific routes also verify required leases
against the configured mutation backend, so deployments do not acquire SQLite
leases and then accidentally authorize writes against the JSONL lease log.

The important boundary is narrower than a full database migration:

- `/kernel/mutation-events` performs lease check and event append in one
  SQLite transaction.
- Existing primitive-specific routes still execute their primitive-owned file
  writes, but use the configured mutation backend for lease verification when
  one is present.
- Moving every primitive write into a single transactional mutation backend is
  a future T2 migration, not a T1 requirement.

## Interface Contract

`SourceConnector`:

- `connector_id`
- `connector_family`

`EventSource`:

- `append_event(stream, event)`
- `read_events(stream)`

`Transactional mutation backend`:

- `acquire_lease(resource_ref, actor_id, ...)`
- `release_lease(lease_id, actor_id)`
- `guarded_append_event(stream, event, resource_ref, lease_id, actor_id, fencing_token)`

`ArtifactSource`:

- `put_artifact(key, payload)`
- `get_artifact(key)`

Adapters must preserve append order within a stream. Consumers should derive
state by replaying events or reading explicit artifacts; they should not infer
kernel state from app caches.

## Boundary Rule

Filesystem, SQLite, Postgres, object stores, and enterprise event streams are
transport choices. They must not change the meaning of roles, mandates,
obligations, human work sessions, forecast read models, action-impact records,
or run checkpoints.
