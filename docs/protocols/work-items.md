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
  "unit_id": "research_intake",
  "unit_kind": "analysis_lane",
  "display_name": "Research Intake",
  "owner_role": "role.research_lead",
  "input_kinds": ["question", "source_packet", "decision_request"],
  "allowed_work_kinds": ["triage", "source_check", "draft_summary"],
  "allowed_exits": ["summary_ready", "needs_followup", "escalated", "retired"],
  "worker_roles": ["role.analysis_worker", "role.quality_reviewer"],
  "worker_role_classes": {
    "role.analysis_worker": "agent",
    "role.quality_reviewer": "governance"
  },
  "worker_role_archetypes": {
    "role.analysis_worker": "fungible_agent_worker",
    "role.quality_reviewer": "independent_reviewer"
  },
  "sla": {"p95_seconds": 120},
  "operator_required_when": ["policy_change", "ambiguous_target_kind", "budget_escalation"],
  "governance_required_for": ["escalated"],
  "status": "active"
}
```

`define_operating_unit(...)` is idempotent on `unit_id`: redefining replaces
the contract and preserves the original `created_at_utc`. `worker_roles` is the
enforced authority field; an empty list means the unit does not restrict
claimants, which keeps single-authority T1 deployments lightweight. Every entry
in `governance_required_for` must also appear in `allowed_exits`.

`worker_role_classes` and `worker_role_archetypes` are optional annotations
over `worker_roles`.
`WORKER_CLASSES` is the documented vocabulary — `deterministic`, `llm`,
`agent`, `governance`, `operator` — that explains what kind of worker a role is
expected to be. `worker_role_archetypes` points to the richer taxonomy entry
that also records capability, fungibility, state, and state location. The
kernel enforces the role, not either label.

The worker-class vocabulary is interpreted through the
[Worker Taxonomy](worker-taxonomy.md): capability, fungibility, state, and
transport are separate axes. For example, a tool-using agent may be fungible
when all relevant context is externalized, or singular when its accumulated
session context is part of the work.

`operating_unit_resource(...)` projects the contract into the common
[`Resource Envelope`](resource-envelope.md) for adapters, dashboards,
migrations, and conformance fixtures. The JSONL row remains canonical:

```bash
python -m cognitive_firm.orchestration.operating_units list --resource
```

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

### Resource Projection

`work_item_resource(...)` projects a work item into the common
[`Resource Envelope`](resource-envelope.md). The JSONL row remains canonical;
the resource shape is for adapters, dashboards, migrations, and conformance
fixtures that need a stable object view:

```text
kind: WorkItem
metadata: name/resource_id, tenant/project, labels, annotations
spec: unit, work kind, owner role, priority, attempts budget, payload, idempotency key
status: claim/fencing state, bounded exit, producer/verifier, failure/dead-letter reason
links: operating unit plus artifact/run refs
```

The CLI can render the same projection:

```bash
python -m cognitive_firm.orchestration.work_items list --resource
```

This is part of the resource/event consolidation path. It does not create a
second work-item API or make resource envelopes canonical state.

## Operating Unit Dashboard

`build_operating_unit_dashboard(...)` derives production health per unit:
backlog, claimed (with stale claims flagged), throughput over a trailing
window, observed `p95_seconds`, SLA breach, and a single `blocker` string. It
is a read model — it owns no facts and can be rebuilt from work items at any
time.

## Service Flow

```json
POST /kernel/operating-units            { "unit_id": "...", "allowed_work_kinds": [...], "allowed_exits": [...] }
GET  /kernel/operating-units?tenant_id=...&status=active
GET  /kernel/operating-units/<unit_id>
GET  /kernel/work-items?unit_id=...&status=queued
GET  /kernel/work-items/<id>
POST /kernel/work-items                 { "unit_id": "...", "kind": "...", "payload": {...}, "idempotency_key": "..." }
POST /kernel/work-items/claim-next      { "unit_id": "...", "actor": "...", "role_id": "..." }
POST /kernel/work-items/<id>/complete   { "actor": "...", "claim_token": 1, "exit_kind": "summary_ready" }
POST /kernel/work-items/<id>/fail       { "actor": "...", "claim_token": 1, "reason": "...", "retryable": true }
GET  /kernel/operating-unit-dashboard
```

The operating-unit read routes accept the same filters as
`list_operating_units(...)`: `status`, `tenant_id`, and `project_id`. The
work-item read routes accept the same filters as `list_work_items(...)`:
`unit_id`, `status`, `kind`, `tenant_id`, and `project_id`. Add `resource=true`
to render the common resource envelope for dashboards, adapters, and migration
checks.

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
