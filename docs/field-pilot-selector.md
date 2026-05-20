# Field Pilot Selector

Use this before starting a pilot. The goal is to pick one recurring decision
pipeline where the kernel can be tested against a baseline.

## Selection Rule

Choose the smallest workflow that has:

1. repeated decisions;
2. observable outcomes;
3. costly errors, delays, rework, or escalations;
4. artifacts that can be audited without exposing private content publicly;
5. humans who can give short receipts for bounded work.

Do not start with a whole organization, a one-off strategy choice, or a workflow
where outcomes will not be knowable for years.

## Scorecard

Score each candidate from 0 to 3.

| Criterion | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Decision volume | Rare | Monthly | Weekly | Daily or near-daily |
| Outcome visibility | Unknown | Proxy only | Delayed but measurable | Measurable in pilot window |
| Current pain | Mild | Annoying | Material | Expensive or risky |
| Artifact access | None | Fragmented | Mostly available | Complete enough for audit |
| Human receipt burden | High | Moderate | Low | Already close to existing work |
| Role separability | None | Ambiguous | Mostly separable | Clear generation/review/approval roles |
| Learning reuse | One-off | Weak | Recurring failure classes | Recurring and routable |

Prefer the highest score with the lowest receipt burden. If two candidates tie,
choose the one with cleaner baseline data.

## Output

The selector should produce:

- chosen workflow;
- rejected alternatives and reason;
- baseline window;
- success metrics;
- burden metrics;
- kernel surfaces used;
- kill criteria.

Then scaffold the pilot:

```bash
python scripts/field_pilot_scaffold.py tenants/<tenant>/field-pilots/<pilot-name>
```

## Kill Criteria

Stop or redesign the pilot if:

- no baseline can be reconstructed;
- participants cannot produce lightweight receipts;
- authority still has to be inferred from chat;
- the governed path is slower with no reliability gain;
- learning events are never encountered by later work.
