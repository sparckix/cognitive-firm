# Intelligence Sources

**Module:** `cognitive_firm.orchestration.intelligence_sources`

The intelligence-source projection answers a practical question before a role,
app surface, or operator acts:

> Which kernel-facing sources are carrying useful signals, and which sources
> need repair before their recommendations should be trusted?

It is a read model. It does not collect tenant metrics, mutate state, or decide
policy.

## What It Reads

- state-surface inventory entries;
- forecast-market summary;
- action-impact summary;
- strategy-office findings;
- organization-surface counts.

The projection treats tenant-owned ledgers as inputs with a generic contract.
Tenants still own their forecast scoring, action-impact measurement,
domain-specific metrics, and optimizer policy.

## What It Emits

`IntelligenceCoverage` includes:

- source inventory rows;
- health counts by source and connector family;
- process/input metrics that are safe across tenants;
- source-improvement backlog items.

Health labels are intentionally plain:

- `healthy`: no known coverage issue;
- `thin`: source exists but has no visible rows;
- `debt`: source has an open improvement item;
- `proxy_only`: projection/read model only;
- `unverified`: no conformance test is registered.

## Source Improvements

The built-in repair items cover portable failure modes:

- forecast contracts without decision-use rows;
- resolved forecasts waiting for score rows;
- action-impact rows requiring review;
- local action records with negative externalities;
- strategy findings that have not become approved learning events.

These items can feed the learning-transition compiler or a tenant review queue,
but they are not automatic writes.

## Boundary

This protocol is not a dashboard and not a data warehouse. It is a small
coverage layer over the sources already admitted into the kernel. If an
organization needs richer project, finance, science, sales, or support metrics,
those belong in tenant-owned ledgers that emit the public read-model shapes.

## Tests

Covered by `tests/test_intelligence_sources.py` and `tests/test_org_surface.py`.
