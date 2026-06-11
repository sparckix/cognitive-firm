# Routine Reviews

**Status:** first-party interface shipped.
**Module:** `cognitive_firm.orchestration.routine_reviews`
**Tests:** `tests/test_routine_reviews.py`

The kernel records *approved learning events* — durable changes to future
organizational behavior — but it only ever **adds** them. `learning_events.py`
carries a `status` enum and an optional `review_after_utc` field, but nothing
triggers a review when that date passes and nothing enforces retirement. An
approved routine keeps firing as guidance long after the conditions that
justified it have changed.

A **routine review** is the missing forgetting step. It lays a review schedule
*over* a durable routine and gives the kernel three things it did not have:

- a `review_due_utc` deadline after which a routine is **overdue** for
  re-justification — surfaced as a queryable failure;
- a typed review **outcome** so a review is a recorded decision, not a note;
- an explicit accountable **retire** transition that records who retired the
  routine and why.

The kernel owns the review schedule, the overdue surface, and the typed
transition. The tenant owns the review cadence policy and the judgment of
whether a routine still fits.

## Which Invariant It Serves

Routine reviews complete the **durable learning** invariant
(see [`kernel-invariants.md`](../kernel-invariants.md)): "Learning is not a
retrospective note unless it changes future behavior **or review state**."
Approved learning events covered the first half. Routine reviews add the
review-state half — a routine is only durable learning while it is still being
re-justified.

What fails if this primitive is absent: stale routines accumulate silently.
The kernel can prove a routine was once approved but cannot show that anyone is
still accountable for whether it should keep firing. Organizational memory
becomes monotonic — it only grows — and no surface tells an operator which
routines are overdue for forgetting.

## Routine Review

A routine review is canonical state. Fields:

| Field | Meaning |
|---|---|
| `review_id` | stable id |
| `routine_ref` | opaque reference to the durable routine under review |
| `routine_kind` | `learning_event`, `route_rule`, `mandate_rule`, `charter_rule`, `evidence_standard`, `review_threshold`, `policy_adapter`, `other` |
| `learning_event_id` | typed link when the routine is an approved learning event; required when `routine_kind == learning_event` |
| `review_due_utc` | the deadline after which the routine is overdue |
| `scheduled_by` | role/actor that scheduled the review |
| `status` | `scheduled`, `in_review`, `reviewed`, `retired` |
| `reviewer` | named reviewer once a review starts |
| `outcome` | `reaffirm`, `amend`, `retire`, `escalate` |
| `outcome_rationale`, `outcome_evidence_refs` | recorded review decision |
| `review_cadence` | tenant cadence label (e.g. `P90D`); kernel does not interpret it |
| `next_review_id` | the cadence review scheduled by recording an outcome |
| `retired_at_utc`, `retired_by`, `retirement_reason` | accountable retirement record |

`routine_ref` is generic and opaque: any durable routine can be reviewed. When
the routine is an approved learning event, pass `learning_event_id` as well so
the review is joinable to that surface. The kernel never reads or mutates the
learning event.

## Lifecycle

```text
                   ┌──────────────── retire ───────────────┐
                   │                                       ▼
 scheduled ── start ──▶ in_review ── record-outcome ──▶ reviewed
     │                      │
     └──── retire ──────────┴──────────▶ retired
```

| Status | Meaning |
|---|---|
| `scheduled` | a review is due by `review_due_utc` |
| `in_review` | a named reviewer is re-justifying the routine |
| `reviewed` | a typed outcome was recorded; non-terminal — a cadence review may follow |
| `retired` | accountable terminal state; routine should stop firing |

`reviewed` is terminal for *this* review row but not for the routine: recording
an outcome with `next_review_due_utc` creates a fresh `scheduled` review, so a
routine that should survive stays continuously re-justified on a cadence.
`retire` is reachable from `scheduled` or `in_review` — the accountable role
can retire a routine without a full review. An `outcome="retire"` is a
*recommendation*; the accountable terminal transition is `retire_routine(...)`.

Every transition emits a canonical [`KernelEvent`](kernel-events.md) with verbs
`routine_review.scheduled`, `routine_review.started`,
`routine_review.outcome_recorded`, and `routine_review.retired`.

## Service Flow

```json
POST /kernel/routine-reviews                       { "routine_ref": "...", "routine_kind": "learning_event", "review_due_utc": "...", "scheduled_by": "...", "learning_event_id": "..." }
POST /kernel/routine-reviews/<id>/start            { "reviewer": "..." }
POST /kernel/routine-reviews/<id>/record-outcome   { "outcome": "reaffirm", "reviewer": "...", "rationale": "...", "next_review_due_utc": "..." }
POST /kernel/routine-reviews/<id>/retire           { "retired_by": "...", "reason": "..." }
GET  /kernel/routine-reviews                       ?status=&routine_kind=&learning_event_id=&resource=true
GET  /kernel/routine-reviews/due                   ?resource=true
GET  /kernel/routine-reviews/summary
```

`GET /kernel/routine-reviews/due` is the forgetting-pressure surface: every row
it returns is a routine still firing as guidance that has not been re-justified
by its deadline, ordered most-overdue first.

## Resource Projection

`routine_review_resource(...)` projects a routine review into the common
[`Resource Envelope`](resource-envelope.md). The JSONL row remains canonical;
the projection is for adapters, dashboards, migrations, and conformance
fixtures:

```bash
python -m cognitive_firm.orchestration.routine_reviews list --resource
```

The resource links the routine, the typed learning event when present, outcome
evidence refs, and any cadence follow-up review. It exposes overdue state as a
derived status field; mutations still go through the routine-review lifecycle
functions.

## T1 And T2 Modes

T1 stores routine reviews in a JSONL log and rewrites the projection on each
mutation, which is enough for one host. A T2 deployment puts the same rows
behind the transactional [State Backend](state-backends.md) so the typed
transition is checked inside the mutation transaction. The function contract in
`routine_reviews.py` is identical either way.

## Boundary

The kernel owns the review schedule, the overdue surface, and the typed
`scheduled -> in_review -> reviewed` / `retired` transition. It does **not**
decide the review cadence, judge whether a routine still fits, or apply the
routine change. It does not edit `learning_events.py`; it references a learning
event by id on a separate surface. A future integration where `learning_events`
reads retirement state is out of scope for this primitive.

## Research Anchor

Nelson & Winter, *An Evolutionary Theory of Economic Change*, frame
organizational routines as the firm's persistent memory: routines encode
"how things are done here" and persist because they are cheap to keep running,
not because they are continuously re-justified against current conditions.
That persistence is adaptive while the environment is stable and a liability
once it shifts — the routine keeps firing as guidance after it stops fitting.
A kernel that only records *approved* learning reproduces exactly this failure:
memory grows monotonically. The contribution here is not the idea that routines
go stale; it is making the forgetting step an explicit, accountable, audited
transition with a queryable overdue surface, so re-justification and retirement
become governed organizational state rather than informal drift.
