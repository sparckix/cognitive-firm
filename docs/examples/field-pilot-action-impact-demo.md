# Field-Pilot Action-Impact Demo

This no-cost demo connects the field-validation pilot pack to action-impact
policy review.

Run:

```bash
make field-pilot-action-impact-demo
```

The fixture creates a fictional product-requirement approval pilot, writes an
`action-impact-summary.json` inside the pilot folder, validates that the pilot
has machine-readable evidence, then builds a candidate route and governance
review packet:

```text
field-pilot folder
-> action-impact summary
-> business-function candidate proposal
-> conservative offline policy evaluation
-> policy-promotion packet
```

The demo is intentionally offline. It does not activate a policy or run online
exploration. It proves that a field pilot can carry enough measured action
evidence to propose a routing change for review.

Pilot folders can require machine-readable action-impact evidence with:

```bash
python scripts/field_pilot_validate.py <pilot-dir> \
  --require-action-impact \
  --min-action-impact-records 30
```

For a real pilot, compile measured decision rows into the same summary file:

```bash
python scripts/field_pilot_action_impact_compile.py <pilot-dir> pilot-rows.csv \
  --validate \
  --min-records 30
```

The compiler accepts `.csv`, `.json`, or `.jsonl`. Useful row fields include
`action_id`, `actor`, `objective_metric`, `status`, `context_features`,
`action_arm`, `reward`, `requires_human_review`, `guardrail_metrics`,
`externalities`, and `negative_externality_tags`.
