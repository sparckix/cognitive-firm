# Outcome Links

**Status:** first-party interface shipped.
**Module:** `cognitive_firm.orchestration.outcome_links`
**Tests:** `tests/test_outcome_links.py`

The kernel records that learning happened (`learning_events.py`) and that an
approved learning event was *encountered* by future work
(`learning_event_encounters` telemetry, outcomes `encountered | applied |
ignored | deferred`). It does not record whether an approved change actually
*improved a measured outcome*. That makes the kernel's own central validity
claim — that governing a pipeline produces **measurable improvement** —
untestable from kernel records alone.

An **outcome link** is that missing record. It binds a *change* — a learning
event, a governance change, or an accountability case — to a *measured outcome*
on one tenant-defined metric, and carries a tenant verdict on whether the change
worked.

## Which Invariant It Serves

Outcome links serve the **Durable learning** invariant
(see [`kernel-invariants.md`](../kernel-invariants.md)). That invariant states
learning "is not a retrospective note unless it changes future behavior **or
review state**." The kernel could already show that learning was approved and
encountered, but not whether it helped. The outcome link closes that loop: it is
the kernel record that conditions review on the outcome signal, not only on
whether a lesson was seen.

**What fails if absent:** the organization cannot distinguish learning that
helped from learning that was merely logged and obeyed. Stale or actively
harmful routines persist because there is no kernel-visible selection signal,
and the kernel cannot answer "did governing this pipeline make it better?" from
its own data.

## Fields

An `OutcomeLink` is canonical state. Fields:

| Field | Meaning |
|---|---|
| `outcome_link_id` | stable id |
| `change_ref` | generic reference to the change being measured |
| `change_kind` | tenant label (`learning_event`, `governance_change`, `accountability_case`, ...) |
| `learning_event_id` | optional typed reference for the learning-event case |
| `metric_name` / `metric_unit` | tenant-defined metric identity |
| `direction` | optional tenant hint (e.g. `lower_is_better`) — kernel does not interpret it |
| `baseline` | one `MetricSnapshot` taken before the change |
| `post_snapshots` | one or more `MetricSnapshot` rows taken after the change |
| `verdict` | tenant verdict ∈ {improved, no_change, regressed, inconclusive} |
| `verdict_recorded_by` / `verdict_rationale` | who decided and why |
| `void_reason` | reason a link was abandoned |
| `status` | lifecycle state (below) |
| `owner_role`, `tenant_id`, `project_id`, `metadata` | scoping |

A `MetricSnapshot` carries `kind` (`baseline` | `post`), a numeric `value`,
`captured_at_utc`, `captured_by`, and optional `sample_size` / `measurement_ref`
/ `note`. The kernel stores the value verbatim; it does not compute it.

## Lifecycle

```text
open ── record baseline ──▶ measuring ── record verdict ──▶ verdict_recorded
  │                            │
  └──────────── void ──────────┴───────────────▶ voided
```

| Status | Meaning |
|---|---|
| `open` | link created; no measurement yet |
| `measuring` | a baseline (and optionally post snapshots) recorded |
| `verdict_recorded` | terminal; tenant recorded a verdict |
| `voided` | terminal escape; link can no longer yield an informative verdict |

Discipline: a `baseline` snapshot must precede any `post` snapshot — the
change's effect is undefined without a before value. A link has exactly one
baseline; a second is rejected. A verdict is accepted only on a `measuring` link
that already has a baseline and at least one post snapshot. Terminal links
reject all further transitions.

## Service Flow

```json
POST /kernel/outcome-links                       { "change_ref": "...", "change_kind": "...", "metric_name": "...", "metric_unit": "...", "created_by": "..." }
POST /kernel/outcome-links/<id>/snapshots        { "kind": "baseline", "value": 0.40, "captured_by": "..." }
POST /kernel/outcome-links/<id>/verdict          { "verdict": "improved", "recorded_by": "...", "rationale": "..." }
POST /kernel/outcome-links/<id>/void             { "reason": "..." }
GET  /kernel/outcome-links                       ?status=&verdict=&learning_event_id=
GET  /kernel/outcome-links/summary               ?tenant_id=&project_id=
```

Public functions: `create_outcome_link`, `record_metric_snapshot`,
`record_verdict`, `void_outcome_link`, `list_outcome_links`, `get_outcome_link`,
`summarize_outcome_links`. Every public function takes `log_path` and
`kernel_events_log` so deployments and tests can redirect storage.

## Outcome-Link Summary

`summarize_outcome_links(...)` derives the kernel's measurable-improvement read
model: of N governed changes with outcome links, how many improved, regressed,
showed no change, are inconclusive, are still measuring, or are voided.
`verdict_coverage` is the share of non-voided links that reached a verdict — the
kernel's own measure of whether its learning loop is being closed. The summary
owns no facts and can be rebuilt from outcome-link rows at any time.

## Outcome-Link Events

Every transition emits a canonical [`KernelEvent`](kernel-events.md) with verbs
`outcome_link.created`, `outcome_link.snapshot_recorded`,
`outcome_link.verdict_recorded`, and `outcome_link.voided`. The payload carries
the change reference, the metric identity, the status, and snapshot counts.

## T1 And T2 Modes

T1 stores outcome links in a JSONL log and rewrites the row projection on each
mutation. A T2 deployment puts the same rows behind the transactional
[State Backend](state-backends.md) so lifecycle transitions are checked inside
the mutation transaction. The function contract in `outcome_links.py` is
identical either way.

## Boundary

The kernel does **not** compute the metric or decide the verdict. The tenant
owns the metric definition, supplies every snapshot value, and supplies the
verdict and its rationale. The kernel owns the typed record, the lifecycle
discipline (baseline before post, verdict only on a measured link), and the
read-model summary. This mirrors the kernel's existing forecast/action-impact
pattern: kernel owns the interface shape, tenant owns the scoring. If a reviewer
reads outcome linkage as importing tenant policy into the kernel, that is a
definitional disagreement resolved by keeping the metric and verdict
tenant-supplied.

## Research Anchor

This is the Holmström informativeness principle applied to organizational
learning: a control system should condition on the most informative available
signal, and a signal should be incorporated only when it carries information
about whether the action worked. Recording only "was the lesson encountered"
conditions the learning loop on the least informative signal and discards the
outcome signal; the outcome link records what is informative about whether the
change improved the measured outcome. The contribution here is not a metrics
store — it is binding a measured before/after delta and a tenant verdict to a
governed change as durable, auditable kernel state, so organizational learning
becomes selectable rather than merely logged.
