# Example Tenant Overlay

This directory shows the smallest useful overlay shape. It is illustrative,
not a production tenant.

Real organizations should keep private roles, mandates, preferences, project
charters, evidence, customer data, and business-system bindings in a private
repo. The public kernel should contain generic protocols and tests.

## Layout

```text
tenants/example/
  mandates/research_director_mandate.md
  preferences/principal.yaml
  projects/demo/project_charter.md
  roles/research_director.yaml
  walkthrough/
```

## Adoption Pattern

1. Copy this directory into a private tenant repo.
2. Replace the mandate with your actual authority boundaries.
3. Replace the principal preferences with your escalation, budget, and
   notification preferences.
4. Add project charters for the real work.
5. Wire tenant-specific forecast, action-impact, and evidence systems through
   read-model adapters instead of modifying kernel primitives.

Then read `walkthrough/README.md` for an end-to-end path that joins a charter,
evidence gap, human work session, forecast summary, action-impact summary,
strategy finding, org surface, and learning-transition candidate.

## Boundary Rule

Tenant overlays may define policy. Kernel modules should define reusable
interfaces and deterministic state transitions.
