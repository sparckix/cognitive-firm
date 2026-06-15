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
| `metadata.predicted_effect` | optional typed prediction contract for a governed change |
| `metadata.prediction_review` | derived after verdict; flags whether the prediction was met or should become a reversal candidate |
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

## Prediction-Gated Mutations

Governed structural mutations can attach a typed `predicted_effect` when the
outcome link is created:

```json
{
  "metric_name": "open_org_design_gaps",
  "metric_unit": "count",
  "direction": "lower_is_better",
  "threshold": 1,
  "review_horizon": "next_routine_review",
  "expected_verdict": "improved",
  "rationale": "fewer ambiguous handoffs after this mandate change"
}
```

The kernel validates that the predicted metric matches the outcome link's
`metric_name`, `metric_unit`, and optional `direction`. It does **not** decide
whether snapshots satisfy the threshold. When a tenant records a verdict, the
kernel derives `metadata.prediction_review`:

- `prediction_met` -> continue or reaffirm;
- `prediction_failed` -> file a reversal candidate at routine review;
- `prediction_inconclusive` -> escalate or extend review;
- `awaiting_verdict` -> continue measuring.

This is the composition rule for falsifiable structural learning: a mutation is
not just "approved"; it carries an expected effect, an outcome link, and a later
review implication. Failed predictions do not auto-revert state. They become
governed reversal evidence through the existing routine-review and
governance-change path.

The kernel service exposes this composition directly:

```text
POST /kernel/outcome-links/{outcome_link_id}/reversal-review
```

The route reads a recorded outcome link, requires
`metadata.prediction_review.status == "prediction_failed"` by default, and
schedules a normal routine review with reversal-candidate metadata. It does not
amend, retire, roll back, or otherwise mutate the governed change.

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
GET  /kernel/outcome-links                       ?status=&verdict=&learning_event_id=&resource=true
GET  /kernel/outcome-links/summary               ?tenant_id=&project_id=
```

Public functions: `create_outcome_link`, `record_metric_snapshot`,
`record_verdict`, `void_outcome_link`, `list_outcome_links`, `get_outcome_link`,
`summarize_outcome_links`, `predicted_effect_from_dict`,
`prediction_review_for_outcome_link`, and `outcome_link_resource`. Every public
write function takes `log_path` and `kernel_events_log` so deployments and
tests can redirect storage.

## Outcome-Link Summary

`summarize_outcome_links(...)` derives the kernel's measurable-improvement read
model: of N governed changes with outcome links, how many improved, regressed,
showed no change, are inconclusive, are still measuring, or are voided.
`verdict_coverage` is the share of non-voided links that reached a verdict — the
kernel's own measure of whether its learning loop is being closed. The summary
owns no facts and can be rebuilt from outcome-link rows at any time.

## Resource Projection

`outcome_link_resource(...)` projects an outcome link into the common
[`Resource Envelope`](resource-envelope.md). The JSONL row remains canonical;
the projection is for adapters, dashboards, migrations, and conformance
fixtures:

```bash
python -m cognitive_firm.orchestration.outcome_links list --resource
```

The resource links the governed change, typed learning event when present, and
tenant measurement refs when snapshots carry them. It does not interpret the
metric or verdict.

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

Outcome links are grounded in four related traditions:

- Holmström's informativeness principle in contract theory: a control system
  should condition on informative signals about whether the action worked, not
  only on whether the action happened. A public index for the principle is
  <https://en.wikipedia.org/wiki/Informativeness_principle>.
- Popper's falsifiability criterion: a claim that cannot specify what would
  count against it is weak evidence for learning. `predicted_effect` applies
  that discipline to governed structural change by requiring a metric,
  direction, threshold, and review horizon before the outcome link can test the
  claim. See <https://en.wikipedia.org/wiki/Falsifiability>.
- Campbell's experimenting-society and quasi-experimentation tradition: policy
  and organizational changes should leave inspectable before/after evidence,
  while respecting the limits of field measurement. See Donald Campbell's
  public bibliography and evaluation work at
  <https://en.wikipedia.org/wiki/Donald_T._Campbell>.
- Organizational learning and selection theory: routines need variation,
  selection, and retention, not just accumulation. March's exploration and
  exploitation framing is one anchor:
  <https://doi.org/10.1287/orsc.2.1.71>.

The shipped primitive is narrower than those traditions. It is not a metrics
store, statistical evaluator, or automatic rollback engine. It binds a
tenant-supplied before/after measurement, verdict, and optional falsifiable
prediction to a governed change as durable kernel state. A failed prediction
creates reversal-review evidence; it does not reverse the change by itself.
