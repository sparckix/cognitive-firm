# Work Items And Operating Units

**Status:** first-party interface shipped.
**Modules:** `cognitive_firm.orchestration.operating_units`,
`cognitive_firm.orchestration.work_items`,
`cognitive_firm.orchestration.operating_unit_surface`
**Tests:** `tests/test_operating_units.py`, `tests/test_work_items.py`,
`tests/test_operating_unit_surface.py`, `tests/test_kernel_service.py`

The kernel records *decisions* (gates), *human work* (A2H sessions),
*obligations* (A2A), and *residual risk* (accountability cases). None of those
is the recurring unit of **production work** a company actually runs: a
claimable, retryable task that flows through a support desk, a sales-ops queue,
a research-triage lane, a data-cleaning station, a CI lane, or a proof mill.

This protocol adds that production layer without importing any domain policy.

- An **operating unit** is the typed contract for one recurring production
  lane. A tenant may call it a station, desk, lane, or department.
- A **work item** is one durable, claimable unit of work that flows through a
  unit.
- The **operating-unit dashboard** is a read model over both.

The kernel owns the contract and the claim discipline. The tenant owns the
work kinds, the payload schema, and what a finished exit *means*.

## Which Invariant It Serves

Work items extend three existing kernel invariants into the production layer
(see [`kernel-invariants.md`](../kernel-invariants.md)):

- **Typed authority** — only a worker role listed on the operating unit may
  claim its work, and exactly one worker holds a claim at a time, enforced by a
  lease and a monotonic fencing token.
- **Separation** — when a completed work item records both a `producer` and a
  `verifier`, they must differ; generation and evaluation do not collapse into
  one actor.
- **Accountable closure** — a completed work item must land on a *bounded
  exit* the operating unit declared in advance. "done" is never open-ended;
  it is one of a tenant-defined, reviewable set.

## Operating Unit

An operating unit is canonical state. Fields:

```json
{
  "unit_id": "residual_compiler",
  "unit_kind": "transformation_lane",
  "display_name": "Residual Compiler",
  "owner_role": "role.residual_compiler_manager",
  "input_kinds": ["typed_residual", "family_spec", "source_candidate"],
  "allowed_work_kinds": ["canary_propose", "exact_gap_compile", "retire_row"],
  "allowed_exits": ["canary_ready", "exact_gap", "valid_falsifier", "tested_hold", "retired"],
  "worker_roles": ["role.llm_proposer", "role.proof_execution_worker"],
  "sla": {"p95_seconds": 120},
  "operator_required_when": ["policy_change", "ambiguous_target_kind", "budget_escalation"],
  "governance_required_for": ["exact_gap", "family_promotion"],
  "status": "active"
}
```

`define_operating_unit(...)` is idempotent on `unit_id`: redefining replaces
the contract and preserves the original `created_at_utc`. `worker_roles` is the
enforced authority field; an empty list means the unit does not restrict
claimants, which keeps single-principal T1 deployments lightweight. Every entry
in `governance_required_for` must also appear in `allowed_exits`.

`WORKER_CLASSES` is an open, documented vocabulary — `deterministic`, `llm`,
`agent`, `governance`, `operator` — that explains *why* a role is allowed to
touch a unit. The kernel enforces the role, not the class label.

## Work Item

A work item is canonical state. Lifecycle:

```text
queued ── claim ──▶ claimed ── start ──▶ running
  ▲                   │                    │
  │ fail (retryable,   │ complete           │ complete
  │ attempts left)     ▼                    ▼
  └──────────────────▶ done / failed / dead_letter / retired
```

| Status | Meaning |
|---|---|
| `queued` | waiting for a worker |
| `claimed` | held by a worker under a lease |
| `running` | claimed and in progress |
| `done` | completed on a bounded exit |
| `failed` | non-retryable failure |
| `dead_letter` | retryable failure that exhausted `max_attempts`; reviewable |
| `retired` | withdrawn before completion |

Kernel responsibilities:

- claim, heartbeat, expire, and release work safely;
- enforce worker-role authority for claiming;
- keep retries and dead letters reviewable;
- require a bounded exit on completion;
- emit a `KernelEvent` for every transition.

Tenant responsibilities: define work kinds, the payload schema, priority
policy, and the meaning of each exit.

### Claim Discipline

Each claim increments a monotonic `claim_token` and sets `lease_until_utc`.
`complete`, `fail`, `start`, and `heartbeat` require the holder's actor id, a
matching `claim_token`, and an unexpired lease. A queued item, or a claimed
item whose lease has expired, is claimable; reclaiming bumps the token, so a
worker whose lease lapsed cannot complete the item after another worker has
taken it. This is the same fenced-mutation shape as [Leases](leases.md),
specialized to the queue.

### Retries And Dead Letters

A retryable failure with attempts remaining returns the item to `queued`. A
retryable failure that has used all `max_attempts` becomes a `dead_letter` for
operator review. A non-retryable failure goes straight to `failed`.
`requeue_dead_letter(...)` is the only transition out of `dead_letter` and is
meant for an operator who has fixed the underlying cause.

### Work Events

Every transition emits a canonical [`KernelEvent`](kernel-events.md) with verbs
`work_item.enqueued`, `work_item.claimed`, `work_item.started`,
`work_item.heartbeat`, `work_item.completed`, `work_item.failed_retry`,
`work_item.failed`, `work_item.dead_lettered`, `work_item.retired`, and
`work_item.requeued`. The payload carries the unit, the exit, and
producer/verifier provenance. Work events **link to** action attestations
rather than duplicating them: an attestation proves the machine work, the work
event records the organizational transition.

## Operating Unit Dashboard

`build_operating_unit_dashboard(...)` derives production health per unit:
backlog, claimed (with stale claims flagged), throughput over a trailing
window, observed `p95_seconds`, SLA breach, and a single `blocker` string. It
is a read model — it owns no facts and can be rebuilt from work items at any
time.

## Service Flow

```json
POST /kernel/operating-units            { "unit_id": "...", "allowed_work_kinds": [...], "allowed_exits": [...] }
POST /kernel/work-items                 { "unit_id": "...", "kind": "...", "payload": {...}, "idempotency_key": "..." }
POST /kernel/work-items/claim-next      { "unit_id": "...", "actor": "...", "role_id": "..." }
POST /kernel/work-items/<id>/complete   { "actor": "...", "claim_token": 1, "exit_kind": "exact_gap" }
POST /kernel/work-items/<id>/fail       { "actor": "...", "claim_token": 1, "reason": "...", "retryable": true }
GET  /kernel/operating-unit-dashboard
```

Every mutation route runs through the same actor-context, membership, and lease
checks as the rest of the [Kernel Service](kernel-service.md).

## T1 And T2 Modes

T1 stores work items in a JSONL log and holds an exclusive file lock around
every mutation, which is enough for one host. A T2 deployment puts the same
rows behind the transactional [State Backend](state-backends.md) so the claim
and fencing token are checked inside the mutation transaction. The function
contract in `work_items.py` is identical either way; this module deliberately
does **not** ship a second bespoke SQLite store, because the kernel already has
one transactional-mutation seam and a queue should not fork it.

## Boundary

The kernel does not interpret a `payload`, decide a priority policy, or judge
whether an exit counts as value. It runs a generic company that does durable
station work under authority and audit. Domain semantics — proof validation,
ticket triage rules, scoring — stay in the tenant overlay. The kernel only
requires that finished work names an exit the unit declared in advance.

## Research Anchor

Durable work queues with at-least-once delivery, leased claims, and dead-letter
channels are long-settled infrastructure (see Gray & Cheriton's lease model,
cited in [`leases.md`](leases.md), and the dead-letter pattern in enterprise
messaging). The contribution here is not the queue; it is binding the queue to
typed role authority, producer/verifier separation, and tenant-defined bounded
exits, so recurring production work becomes governed organizational state
rather than untyped task execution.
