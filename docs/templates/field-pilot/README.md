# Field Pilot Starter Pack

These templates support the validation protocol in
`docs/field-validation-pilot.md`. Copy them into a tenant overlay before a
pilot starts.

Use the templates in this order:

1. `pilot-scope.md`: choose one recurring decision pipeline and name the kernel
   intervention.
2. `baseline-notes.md`: record the pre-pilot process and metrics.
3. `metrics-table.md`: track baseline and pilot measures in the same shape.
4. `learning-event-summary.md`: summarize what changed after the pilot.

The templates keep the pilot falsifiable: same workflow, same metrics, explicit
burden accounting, and a clear record of which behavior changed.

To copy the pack into a tenant workspace:

```bash
python scripts/field_pilot_scaffold.py tenants/<tenant>/field-pilots/<pilot-name>
```

If the pilot uses action-impact evidence, add `action-impact-summary.json` to
the same folder and validate it:

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

If the pilot uses accountability speed classes, also keep a
`human-speed-envelope-summary.json` beside the action-impact summary. The
public `make field-pilot-action-impact-demo` fixture writes this file and
reports `human_speed_field_pilot_summary.v1`: chosen speed class, expected
class, sampled-review coverage, and review signals for harm, rework, hidden
burden, or open residual risk. The summary is read-only evidence, not a routing
or approval mechanism.

If the pilot measures operator burden, compile measured baseline/pilot rows
into `operator-burden-field-pilot-summary.json`:

```bash
python scripts/field_pilot_operator_burden_compile.py tenants/<tenant>/field-pilots/<pilot-name> \
  operator-burden-rows.csv \
  --min-baseline-runs 3 \
  --min-pilot-runs 3
```

The compiler accepts `.csv`, `.json`, or `.jsonl` rows and reports
`operator_burden_field_pilot_summary.v1`: baseline-vs-pilot human touchpoints,
coordination minutes, rework, missing receipts, hidden burden, and projection
undercount. The summary is adoption evidence only; it does not assign work,
schedule review, approve policy, or optimize routing.
