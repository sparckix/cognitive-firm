# Example Walkthrough

This walkthrough shows the smallest end-to-end overlay path without private
tenant data. It is meant to be copied into a private tenant repo and adapted.

## Flow

1. A project charter defines the object of work:
   `tenants/example/projects/demo/project_charter.md`.
2. A role creates an evidence gap when a claim is not source-ready.
3. A role creates a human-work session when the principal must do bounded work,
   such as checking a restricted source.
4. A tenant forecast market exposes `forecast_market/global_health.json`.
5. A tenant action-impact ledger exposes `action_impact/action_impact_summary.json`.
6. The organization surface joins those carriers.
7. The strategy office emits observer-only findings.
8. The learning-transition compiler emits reviewable candidates for the next
   durable state change.
9. The accountability summary shows owner/project follow-up.

## Run Locally

From the repository root:

```bash
python -m cognitive_firm.orchestration.evidence_gaps create \
  --gap-type missing_source \
  --target "demo claim" \
  --description "Need a primary source before continuing." \
  --severity blocking \
  --producer role.reviewer \
  --tenant-id example \
  --project-id demo

python -m cognitive_firm.orchestration.human_work create \
  --requested-by role.manager \
  --human-actor principal \
  --objective "verify restricted source for demo claim" \
  --work-mode source_check \
  --bottleneck-class access \
  --tenant-id example \
  --project-id demo \
  --receipt-required \
  --receipt-type note \
  --agent-followup-required

python -m cognitive_firm.orchestration.org_surface \
  --project-root tenants/example \
  --forecast-market-summary tenants/example/walkthrough/forecast_market/global_health.json \
  --action-impact-summary tenants/example/walkthrough/action_impact/action_impact_summary.json

python -m cognitive_firm.orchestration.learning_transition_compiler \
  --project-root tenants/example \
  --forecast-market-summary tenants/example/walkthrough/forecast_market/global_health.json \
  --action-impact-summary tenants/example/walkthrough/action_impact/action_impact_summary.json \
  --json

python -m cognitive_firm.orchestration.accountability \
  --project-root tenants/example \
  --forecast-market-summary tenants/example/walkthrough/forecast_market/global_health.json \
  --action-impact-summary tenants/example/walkthrough/action_impact/action_impact_summary.json \
  --json
```

In a real tenant, route the candidate rows into the tenant's review queue or
issue tracker. Do not let the compiler update governance state directly.

## Boundary

The JSON files here are read-model fixtures. The tenant owns the market,
ledger, scorer, calibration policy, and optimizer policy. The kernel owns the
portable shape and the reviewable transition-candidate boundary.
