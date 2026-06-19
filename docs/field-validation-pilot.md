# Field Validation Pilot

This is a public research challenge for testing whether `cognitive-firm`
improves a real organizational workflow.

The pilot is adapted from an earlier field-test design for the research
apparatus. This version is kernel-neutral: it tests whether the governance
primitives in this repository help a firm make one recurring decision pipeline
more reliable, faster, or cheaper without hiding extra work in human
coordination.

## Core Claim

The kernel should be tested in one real decision pipeline, not in an abstract
organization-wide rollout.

The question is:

> If a firm adds role offices, typed mandates, pre-registered checks, separated
> generation/review paths, human-work receipts, action attestations, and a
> learning loop to one recurring decision pipeline, do measurable outcomes
> improve relative to the pre-pilot baseline?

The pilot is not a proof that every organization should adopt the kernel. It is
a falsifiable adoption test for one workflow.

## Candidate Pipelines

Use [Field Pilot Selector](field-pilot-selector.md) when several workflows are
possible and you need a simple scorecard.

Pick a workflow where:

1. The decision has an observable outcome.
2. The current process mixes generation and self-verification.
3. The decision volume is high enough to measure over time.
4. Errors, delay, or rework are costly enough to matter.
5. The organization can expose enough artifacts to audit the result.

Good candidates:

- investment or acquisition diligence memos;
- market research report production;
- regulatory or compliance review;
- product requirement approval;
- credit underwriting analysis;
- technical architecture review;
- incident postmortem approval.

Avoid first pilots on one-off strategy decisions, highly political executive
decisions, or workflows where outcomes are unknowable for years.

## Minimum Kernel Intervention

The smallest useful pilot should add:

| Kernel primitive | Pilot behavior |
|---|---|
| Project charter | Names the workflow, scope, success metrics, out-of-scope work, and end states. |
| Role mandate | Separates generation, review, approval, and execution authority. |
| Human work session | Records bounded human tasks with receipts instead of treating humans only as gatekeepers. |
| Pre-registered checks | Defines pass/fail or scored checks before each decision artifact is generated. |
| Evidence gaps | Records missing sources, missing comparator data, or unresolved claims as first-class work. |
| Action attestation | Records material agent/tool actions with producer, policy, input, output, and digest. |
| Accountability case | Assigns owner, recourse path, and closure evidence for failures or accepted residual risk. |
| Learning event | Converts recurring failures into approved changes to future behavior. |

The pilot may use Orbit, Telegram, CLI, the kernel service, or a tenant-built
app surface such as Slack, Linear, or GitHub. Those surfaces are projections.
The system of record remains the kernel state and its audit trail.

## Measurement Protocol

### Baseline

Measure the current workflow before changing it.

Minimum baseline window:

- 30 days for high-volume workflows;
- at least 20 completed decisions;
- longer if the workflow is low-volume or seasonal.

Baseline metrics:

- decision error rate;
- time to decision;
- cost per decision;
- rework rate;
- escalation rate;
- human coordination burden;
- decision owner satisfaction;
- downstream incident or exception rate.

When historical outcomes are delayed, use agreed proxies and mark them as
proxies in the project charter.

### Pilot

Run the kernel-backed workflow for 60-90 days, or until the workflow has at
least 20 completed decisions.

Measure the same metrics as baseline, plus:

- gate pass/fail rates;
- evidence-gap creation and closure rates;
- human-work session count, latency, and missing-receipt rate;
- action attestation coverage;
- accountability cases opened and closed;
- approved learning events created from observed failures;
- forecast or action-impact calibration if the tenant uses those primitives.

### Success Criteria

Pre-register success criteria before deployment.

A reasonable first pilot passes if:

- error rate falls by at least 30 percent; or
- time to decision falls by at least 20 percent without worse error rate; or
- severe downstream exceptions fall materially while cost stays flat; and
- human coordination burden does not increase enough to erase the gain.

It fails if:

- the same decisions take longer and are not more reliable;
- review work shifts invisibly to humans;
- role separation collapses in practice;
- evidence gaps pile up without closure;
- learning events are not approved or do not change future behavior;
- participants route around the kernel because it is slower than the old
  process.

## Adoption Frictions

The hard part is usually organizational, not computational.

| Friction | Likely source | What to test |
|---|---|---|
| Separation resistance | Experts dislike review paths that limit discretion. | Does framing review as reputation protection reduce avoidance? |
| Pre-registration resistance | Leaders want flexibility after seeing the work. | Does advisory mode in month one make mandatory gates acceptable in month two? |
| Receipt fatigue | Humans do not want extra administrative work. | Are receipts short enough to be cheaper than future clarification? |
| Tool bypass | People continue work in chat or private docs. | Do app integrations make the governed path the path of least resistance? |
| Accountability discomfort | Failures now have owners and recourse paths. | Does explicit residual-risk acceptance improve closure quality? |

## Deliverables

A completed field-validation pilot should produce:

1. A project charter.
2. Baseline measurement notes.
3. The role mandates used in the pilot.
4. The check library or rubric.
5. A sample decision artifact with audit trail.
6. A summary of human-work sessions and receipts.
7. A summary of action attestations and accountability cases.
8. A learning-event summary showing what changed because of the pilot.
9. A human-speed envelope summary when the pilot uses speed classes, showing
   chosen class, expected class, sampling coverage, rework, hidden burden, harm,
   and residual-risk signals.
10. A final before/after report.

Starter templates live in `docs/templates/field-pilot/`:

- `pilot-scope.md`;
- `baseline-notes.md`;
- `metrics-table.md`;
- `learning-event-summary.md`.

Copy them into a tenant workspace with:

```bash
python scripts/field_pilot_scaffold.py tenants/<tenant>/field-pilots/<pilot-name>
```

For pilots that use action-impact evidence, place a machine-readable summary in
the pilot folder as `action-impact-summary.json` and validate it with:

```bash
python scripts/field_pilot_action_impact_compile.py tenants/<tenant>/field-pilots/<pilot-name> \
  pilot-rows.csv \
  --validate \
  --min-records 30
```

```bash
python scripts/field_pilot_validate.py tenants/<tenant>/field-pilots/<pilot-name> \
  --require-action-impact \
  --min-action-impact-records 30
```

For pilots that measure operator burden, compile the measured baseline/pilot
rows into `operator-burden-field-pilot-summary.json`:

```bash
python scripts/field_pilot_operator_burden_compile.py tenants/<tenant>/field-pilots/<pilot-name> \
  operator-burden-rows.csv \
  --min-baseline-runs 3 \
  --min-pilot-runs 3
```

The output is `operator_burden_field_pilot_summary.v1`, a read-only comparison
of human touchpoints, coordination minutes, rework, missing receipts, hidden
burden, and projection undercount. It is evidence for adoption review, not a
work allocator or routing optimizer.

The no-cost executable example is:

```bash
make field-pilot-action-impact-demo
```

That demo turns measured pilot rows into a candidate route, conservative
offline evaluation, and policy-promotion packet for governance review. It also
writes `human-speed-envelope-summary.json` and reports
`human_speed_field_pilot_summary.v1`, a read-only check of whether observed
speed-class choices matched the accountability envelope and whether sampled
review, harm, rework, hidden burden, or open residual risk needs follow-up.
The summary is evidence for human review; it does not change routing, schedule
review, approve policy, or sample records.

## Open Research Questions

- Which workflows benefit most from governance kernels: high-volume analytical
  work, high-stakes approvals, incident response, or strategic planning?
- How much role separation is enough before the overhead dominates?
- Which app surfaces produce the lowest receipt burden?
- When does human-work recording improve accountability, and when does it
  become performative bureaucracy?
- Can forecast-market and action-impact primitives predict which kernel
  interventions are worth adding before a pilot runs?
- How portable are successful check libraries across firms?
- What is the minimum evidence needed to claim that an organization is learning
  rather than merely logging more artifacts?

## Relationship To This Repository

The pilot is not a separate product. It is a validation protocol for the kernel.

Use:

- [Adopting cognitive-firm](adopting-cognitive-firm.md) for setup boundaries;
- [Field Validation Pilot Example](examples/field-validation-pilot-example.md)
  for a small product-requirement approval pilot;
- [Project Charter](protocols/project-charter.md) for scope;
- [Human-Agent Work](human-agent-work.md) for human work sessions;
- [Action Attestation](protocols/action-attestation.md) for machine-side
  provenance;
- [Accountability Cases](protocols/accountability-cases.md) for failures and
  residual risk;
- [Approved Learning Events](protocols/learning-events.md) for durable changes.
