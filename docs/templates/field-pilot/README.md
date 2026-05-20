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
