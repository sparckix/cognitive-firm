# Residual Decision Rights

**Status:** first-party interface shipped.
**Module:** `cognitive_firm.orchestration.decision_rights`
**Tests:** `tests/test_decision_rights.py`

A mandate is a contract, and every contract is incomplete: it cannot enumerate
every situation a role will face. When a mandate is **silent** on a situation,
someone still has to decide. The kernel records *decisions* (gates), *typed
authority* (mandates), and *residual risk* (accountability cases) — but it had
no typed record of **who is the default decider for what the mandate did not
specify**. So "the mandate didn't cover this, so I decided" was an invisible,
unaccountable act.

This protocol adds that record without importing any tenant mandate policy.

- A **residual-right assignment** names, for a scope, which role holds the
  *residual control right* — the default decider when no mandate clause
  applies.
- A **residual decision** is opened by an actor who hit an unspecified
  situation; it cites the scope and records what was decided and why.

The kernel owns the typed assignment, the invocation record, and the review
lifecycle. The tenant owns the actual mandates.

## Which Invariant It Serves

Residual decision rights extend two existing kernel invariants (see
[`kernel-invariants.md`](../kernel-invariants.md)):

- **Typed authority** — the default decider for an unspecified situation is now
  an explicit, named role for a scope rather than whoever happened to act. A
  decision taken by an actor whose role does not match the active holder is
  flagged, so off-mandate authority is visible.
- **Accountable closure** — every residual decision carries a rationale and
  moves through a review. The `promote_to_mandate_clause` outcome is the bridge
  back to a complete contract: it marks a recurring gap as a candidate for a
  new mandate clause.

What fails if this primitive is absent: residual-rights exercise is invisible.
An actor can decide an unspecified matter, and there is no typed record of
whether they were the default decider, why they decided as they did, or whether
the gap should be closed.

## Residual Right Assignment

Canonical state. Fields:

| Field | Meaning |
|---|---|
| `assignment_id` | stable id |
| `scope_kind` | one of `project`, `resource_class`, `decision_class`, `operating_unit` |
| `scope_ref` | the named scope within that kind |
| `holder_role` | the role that holds the residual control right |
| `holder_actor` | optional specific actor |
| `basis` | why this holder — a stated reason is required |
| `assigned_by` | who made the assignment |
| `status` | `active` or `superseded` |

`assign_residual_right(...)` is idempotent on the `(scope_kind, scope_ref)`
pair: assigning a scope that already has an active holder supersedes the prior
assignment, so the current default decider for a scope is always unambiguous.
This is the same redefine-and-supersede shape as operating units.

## Residual Decision

Canonical state. Fields:

| Field | Meaning |
|---|---|
| `decision_id` | stable id |
| `scope_kind` / `scope_ref` | the governing scope |
| `deciding_actor` / `deciding_role` | who exercised the residual right |
| `decision_summary` | what was decided |
| `rationale` | why — required |
| `assignment_id` | the active assignment cited, if any |
| `unauthorized` | computed flag (see below) |
| `status` | `recorded` or `reviewed` |
| `review_outcome` | `endorsed`, `corrected`, `escalated`, `promote_to_mandate_clause` |

### Lifecycle

```text
recorded ── review ──▶ reviewed
                        outcome ∈ {endorsed, corrected,
                                   escalated, promote_to_mandate_clause}
```

A residual decision is reviewed exactly once; a second review is an illegal
transition.

### The `unauthorized` Flag — Fail Open, Make It Visible

At record time the kernel resolves the active residual-right holder for the
scope and compares it to `deciding_role`. If they differ — including the case
where the scope has **no assignment at all** — the decision is **still
recorded** and flagged `unauthorized: true`. The kernel fails *open* here on
purpose: the situation was genuinely unspecified, so rejecting the record would
only erase the evidence. The flag makes the irregularity reviewable instead of
silent.

## Service Flow

```json
POST /kernel/residual-rights                 { "scope_kind": "project", "scope_ref": "proj.atlas", "holder_role": "...", "basis": "...", "assigned_by": "..." }
GET  /kernel/residual-rights/holder          ?scope_kind=project&scope_ref=proj.atlas
POST /kernel/residual-decisions              { "scope_kind": "...", "scope_ref": "...", "deciding_actor": "...", "deciding_role": "...", "decision_summary": "...", "rationale": "..." }
POST /kernel/residual-decisions/<id>/review  { "reviewed_by": "...", "review_outcome": "promote_to_mandate_clause" }
GET  /kernel/decision-rights-summary
```

Every transition emits a canonical [`KernelEvent`](kernel-events.md) with verbs
`residual_right.assigned`, `residual_decision.recorded`, and
`residual_decision.reviewed`.

`summarize_decision_rights(...)` is a read model — it owns no facts and can be
rebuilt at any time. It surfaces scopes with no active assignment, decisions
flagged `unauthorized`, decisions awaiting review, and `promote_to_mandate_clause`
candidates.

## T1 And T2 Modes

T1 stores assignments and decisions in two JSONL logs under
`org/decision_rights/`. A T2 deployment puts the same rows behind the
transactional [State Backend](state-backends.md); the function contract in
`decision_rights.py` is identical either way. Every public function takes an
explicit `log_path` so a deployment or a test can isolate its own world.

## Boundary

The kernel does not author mandates, judge whether a residual decision was
*correct*, or auto-write a mandate clause. It owns the typed assignment, the
invocation record, and the review lifecycle. The tenant owns the actual
mandates and decides what a `promote_to_mandate_clause` candidate becomes. The
kernel only requires that residual-rights exercise names a scope, states a
rationale, and is reviewable.

## Research Anchor

This primitive is grounded in incomplete-contract theory. Grossman, Hart, and
Moore argue that because contracts cannot specify every contingency, what
matters is the allocation of *residual control rights* — the right to decide in
situations the contract left open. Tirole's treatment of incomplete contracts
makes the same point: the cost of an organization is partly the cost of who
decides the unspecified. A mandate is exactly such an incomplete contract. The
contribution here is not the theory; it is giving the residual control right a
typed, scoped, reviewable home in the kernel, so that exercising it becomes
governed organizational state — and so a recurring gap can be promoted back
into the contract.
