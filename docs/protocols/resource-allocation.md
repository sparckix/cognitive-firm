# Resource Allocation Across Operating Units

**Status:** first-party interface shipped.
**Modules:** `cognitive_firm.orchestration.resource_allocation`
**Tests:** `tests/test_resource_allocation.py`

The kernel ships operating units — the divisional "M" of Chandler's
multidivisional form — and a read-only operating-unit dashboard. It did not
ship the *general office*: the body that allocates capital across divisions and
holds them to account. Without it, the kernel implements the divisional half of
the M-form but not the office half. Units run to caps that no one decided, a
starved high-yield unit and a saturated low-yield unit cannot be rebalanced
through a governed transition, and capacity drifts silently instead of being a
reviewable decision.

An **allocation decision** is the missing record. It is a durable, governed
statement that a deciding role moved a bounded quantity of a named
`resource_kind` FROM one operating unit (or the reserve pool) TO another, under
an explicit authority basis, with a rationale and optional evidence references.
The **allocation ledger** is a read model that sums applied decisions into a
net position per unit.

## Which Invariant It Serves

Allocation decisions extend two existing kernel invariants to the question of
*where capacity goes* (see [`kernel-invariants.md`](../kernel-invariants.md)):

- **Typed authority** — a reallocation is not a silent config edit. It names a
  `deciding_role`, a `deciding_actor`, and an `authority_basis`, and it only
  affects the ledger after an explicit `apply` transition.
- **Separation** — allocation becomes an accountable, reviewable decision
  distinct from the production work inside any one unit. The general office's
  capital-allocation choice is recorded as governed state, not folded into a
  unit's own operation.

**What fails if absent:** capacity drifts silently. There is no durable record
of who moved how much resource between units, why, or under what authority — so
a misallocation has no accountable owner and cannot be reverted as a governed
act.

## Allocation Decision

An allocation decision is canonical state. Fields:

| Field | Meaning |
|---|---|
| `decision_id` | stable id, `alloc_<hex>` |
| `resource_kind` | tenant-defined string: `budget_usd`, `worker_capacity`, `attention_quota`, … |
| `from_unit` | source operating-unit id, or the `__reserve__` sentinel |
| `to_unit` | destination operating-unit id, or the `__reserve__` sentinel |
| `amount` | positive quantity moved; the kernel never computes it |
| `deciding_role` / `deciding_actor` | the authority that decided the move |
| `authority_basis` | the explicit basis (e.g. a mandate ref) for the decision |
| `rationale` | why the move was made, in the tenant's words |
| `effective_from_utc` / `effective_until_utc` | when the move takes effect; optional end |
| `outcome_link_ids` / `change_refs` | optional evidence references that justified it |
| `status` | `proposed`, `applied`, or `reverted` |
| `applied_at_utc` / `reverted_at_utc` / `reverted_reason` | transition stamps |

`from_unit` and `to_unit` must differ and `amount` must be positive: a decision
moves a bounded quantity between two distinct endpoints. The reserve pool
(`RESERVE_POOL = "__reserve__"`) is the firm's unallocated balance; it is a
valid endpoint but never a registered `OperatingUnit`. The kernel does not
require either endpoint to be a registered unit — an allocation decision is a
governance record, and a tenant may pre-record a move against a unit it is
about to define.

## Lifecycle

```text
record ──▶ proposed ── apply ──▶ applied ── revert ──▶ reverted
                                    │
                                    └── (only an applied decision moves the ledger)
```

| Status | Meaning |
|---|---|
| `proposed` | recorded, not yet committed; does not move the ledger |
| `applied`  | committed by an `apply` transition; contributes to the ledger |
| `reverted` | an applied decision undone by a governed `revert`; no longer in the ledger |

`apply` only accepts a `proposed` decision; `revert` only accepts an `applied`
one. A reverted decision row is kept for audit rather than deleted. Reverting is
itself a governed transition with its own actor and reason.

## The Allocation Ledger

`current_allocation(resource_kind)` is a read model. It walks every *applied*,
non-reverted decision for that resource kind and sums them: a `to_unit` gains
`amount`, a `from_unit` loses `amount`. The result maps each unit id (including
the reserve sentinel, if it appears) to its net position. Proposed and reverted
decisions are ignored. The ledger owns no facts of its own — it can always be
rebuilt from the applied decisions in the log, and the sum of all positions is
always zero because every decision conserves quantity.

`allocation_summary(resource_kind)` adds decision counts by status, the
per-unit ledger with the reserve sentinel excluded, the net moved out of the
reserve pool, and the total allocated to units.

## Service Flow

```json
POST /kernel/allocation-decisions              { "resource_kind": "worker_capacity", "from_unit": "__reserve__", "to_unit": "triage_lane", "amount": 10, "deciding_role": "...", "deciding_actor": "...", "authority_basis": "...", "rationale": "..." }
POST /kernel/allocation-decisions/<id>/apply   { "actor": "..." }
POST /kernel/allocation-decisions/<id>/revert  { "actor": "...", "reason": "..." }
GET  /kernel/allocation-decisions              ?resource_kind=&unit_id=&status=
GET  /kernel/allocation-ledger/<resource_kind>
```

Every transition emits a canonical [`KernelEvent`](kernel-events.md) with verbs
`allocation_decision.proposed`, `allocation_decision.applied`, and
`allocation_decision.reverted`. The payload carries the move and the authority
under which it was decided. Every mutation route runs through the same
actor-context, membership, and lease checks as the rest of the
[Kernel Service](kernel-service.md).

## T1 And T2 Modes

T1 stores decisions in a JSONL log and holds an exclusive file lock around every
status transition, which is enough for one host. A T2 deployment puts the same
rows behind the transactional [State Backend](state-backends.md) so the status
transition is checked inside the mutation transaction. The function contract in
`resource_allocation.py` is identical either way; this module does not fork a
second bespoke store.

## Boundary

The kernel records WHO decided to move HOW MUCH, WHY, and under WHAT authority,
and it projects the resulting ledger. **The kernel does not decide the
amounts.** There is no optimizer, no scoring, and no bandit in this module —
the abstraction map ([`abstraction-map.md`](../abstraction-map.md), "What
Belongs Outside The Kernel") explicitly keeps "optimizer or bandit policy" and
"scoring" in tenant space. The size of a move, and the policy that produced it,
are tenant-owned. The kernel validates only the *shape* of the move: a positive
amount, two distinct endpoints, and a legal status transition. This mirrors the
kernel's existing pattern for forecast and action-impact ledgers, where the
kernel owns the typed record and the tenant owns the metric and the policy.

## Research Anchor

Chandler's analysis of the multidivisional (M-form) enterprise identifies the
*general office* as the form's defining organ: it allocates capital across
semi-autonomous operating divisions and holds them to performance, while
divisions run day-to-day operations. The contribution here is not an allocator —
the kernel deliberately does not optimize. It is making the general office's
capital-allocation *decisions* into typed, reviewable, revertible governed
state, so a reallocation has a named decider, an authority basis, a rationale,
and an auditable ledger rather than being silent drift.
