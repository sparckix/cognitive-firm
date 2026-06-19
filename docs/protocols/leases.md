# Leases

**Status:** first-party interface shipped.
**Module:** `cognitive_firm.orchestration.leases`
**Tests:** `tests/test_leases.py`, `tests/test_kernel_service.py`

Leases are time-bounded write claims over mutable kernel resources.

They answer a concurrency question:

> Is this actor currently allowed to mutate this resource?

They do not answer an identity question:

> Who is this actor?

Use [Actor Identity](actor-identity.md) for actor context. Use leases when a
deployment has concurrent writers or a resource needs explicit mutation
ownership.

## Fields

```json
{
  "lease_id": "lease_...",
  "resource_ref": "human_work:hws_123",
  "held_by_actor_id": "human.alice",
  "held_by_role_id": "role.manager",
  "acquired_at_utc": "...",
  "expires_at_utc": "...",
  "state": "active",
  "fencing_token": 1,
  "purpose": "integrate human-work receipt"
}
```

`fencing_token` increases for each lease on the same resource. Kernel service
routes accept an optional `fencing_token` alongside `lease_id` and reject a
mutation when the token does not match the active lease. The local JSONL
backend also locks the lease log during acquire/release so two local writers do
not both acquire the same resource.

This is a local safety boundary, not a distributed transaction guarantee. A T2
backend should check the lease id and fencing token in the same database
transaction as the mutation.

`SqliteMutationBackend` provides that T2 shape locally: lease rows and mutation
events live in the same SQLite database, and `guarded_append_event(...)` checks
the active lease plus fencing token inside the same transaction that appends
the event. A Postgres backend should preserve the same contract with row locks
and transaction-local mutation writes.

## Resource Projection

`lease_resource(...)` projects a lease into the common
[`Resource Envelope`](resource-envelope.md). The lease JSONL row remains
canonical; the resource view is for adapters, dashboards, migration checks, and
conformance fixtures:

```text
kind: Lease
metadata: lease id, labels, annotations
spec: leased resource, holder actor/role, purpose
status: active/released/expired state, fencing token, acquired/expires/released timestamps
links: leased resource, holder actor, holder role
```

The CLI can render the same compatibility shape:

```bash
python -m cognitive_firm.orchestration.leases list --resource
```

## Service Flow

List or project current claims:

```text
GET /kernel/leases?resource_ref=human_work:hws_123&state=active
GET /kernel/leases?resource=true
```

Acquire:

```json
POST /kernel/leases
{
  "resource_ref": "human_work:hws_123",
  "ttl_seconds": 300,
  "actor_context": {
    "actor_id": "human.alice",
    "actor_kind": "human",
    "role_id": "role.manager"
  }
}
```

Use:

```json
POST /kernel/human-work/hws_123/state
{
  "state": "integrated",
  "lease_id": "lease_...",
  "fencing_token": 1,
  "actor_context": {
    "actor_id": "human.alice",
    "actor_kind": "human",
    "role_id": "role.manager"
  }
}
```

Release:

```json
POST /kernel/leases/lease_.../release
{
  "actor_context": {
    "actor_id": "human.alice",
    "actor_kind": "human",
    "role_id": "role.manager"
  }
}
```

The terminal userland mirrors the same flow without becoming a scheduler:

```bash
cognitive-firm-userland lease-acquire human_work:hws_123 --actor human.alice --role role.manager
cognitive-firm-userland leases --resource-ref human_work:hws_123 --state active
cognitive-firm-userland lease-release lease_... --actor human.alice --role role.manager
```

## T1 And T2 Modes

T1 does not require leases by default. One trusted writer can use filesystem
atomicity and Git recovery.

T2-style deployments can start the kernel service with `--require-leases`.
Every mutation route then requires a valid active lease for its resource.

## Why First-Party

Leases protect kernel resources and lifecycle transitions. A third-party IdP
can authenticate the actor, but it cannot decide whether `human_work:hws_123`
is currently held for integration, or whether an accountability case is locked
for review. That is kernel state.

## Research Anchor

[Gray and Cheriton's lease model](https://www.cs.cmu.edu/afs/cs.cmu.edu/academic/class/15712-s12/www/papers/gray89.pdf)
is the core prior art: a lease is a time-bound contract granting rights to the
holder. The cognitive-firm lease is the same shape applied to organizational
state mutation.

## T1 / T2

| Concern | T1 | T2 |
|---|---|---|
| Required | no | yes for contested resources |
| Expiry | optional safety | mandatory |
| Fencing token | checked by kernel service when supplied | checked transactionally with mutation |
| Backend | JSONL | `SqliteMutationBackend`, then Postgres/event store |
