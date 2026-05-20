# First 30 Minutes

This path is for a new reader or agent opening the public kernel for the first
time. It verifies the repo, explains the durable boundary, and shows where an
organization would attach its own overlay.

## 0-5: Identify the Boundary

Open the repository root as an Obsidian vault if you prefer a linked-doc view.
The repo ships a minimal `.obsidian/` config that keeps links relative and
starts on `README.md`.

Read:

1. `README.md`
2. `docs/kernel-invariants.md`
3. `docs/abstraction-map.md`
4. `docs/resource-event-catalog.md`
5. `docs/blueprints/README.md`
6. `docs/reader-checklist.md`
7. `docs/recursive-organization.md`
8. `docs/PROTOCOLS.md`
9. `docs/adopting-cognitive-firm.md`

The key distinction: cognitive-firm is a governance kernel, not an agent
runtime. Role offices, mandates, transition events, evidence gaps, human work,
and app projections live here. Tenant-specific research policy, scoring
engines, private evidence, and business systems live in overlays or adapters.

## 5-15: Run the Public Smoke

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
make smoke-public
make docs-surface-check
make smoke-docker
```

`smoke-public` runs the Python test suite, renders the organization surface,
exercises the framework-neutral runtime adapter, checks the kernel service's
SQLite fenced-mutation path, runs deterministic app-integration and app-service
conformance fixtures, checks source-coverage and learning-loop walkthroughs,
verifies a minimal backup/restore path, validates package entry points, checks
the documentation surface, and builds Orbit.
If the build backend from `requirements.txt` is installed, the package check
also builds and inspects a local wheel. It should not require private tenant
files.

If you only want the kernel read model:

```bash
python -m cognitive_firm.orchestration.org_surface
```

## 15-25: Inspect the Kernel Surface

Read:

1. `org/README.md`
2. `src/cognitive_firm/orchestration/README.md`
3. `docs/abstraction-map.md`
4. `docs/resource-event-catalog.md`
5. `docs/blueprints/README.md`
6. `docs/protocols/mcp.md`
7. `docs/protocols/app-integration.md`
8. `docs/protocols/run-checkpoints.md`
9. `docs/protocols/runtime-adapters.md`
10. `docs/protocols/kernel-service.md`
11. `docs/protocols/identity-providers.md`
12. `docs/protocols/actor-identity.md`
13. `docs/protocols/actor-membership.md`
14. `docs/protocols/identity-provisioning.md`
15. `docs/protocols/tenant-isolation.md`
16. `docs/protocols/leases.md`
17. `docs/protocols/state-surface-inventory.md`
18. `docs/protocols/intelligence-sources.md`

The transition log is the local event/outbox adapter. New durable run or
external-action semantics should append canonical transition events and derive
projections from replay, not create a competing source of truth.

If you want to inspect the app-service boundary without starting the daemon:

```bash
cognitive-firm-kernel-service --host 127.0.0.1 --port 8765
```

For a stricter local T2-style check, read `docs/protocols/kernel-service.md`
before enabling registered actors, token authentication, or lease-required
mutation mode.

## 25-30: Inspect the Overlay Example

Read `tenants/example/README.md` and
`tenants/example/walkthrough/README.md`. Then read
`docs/examples/end-to-end-governance-walkthrough.md`.
If you are evaluating an app or dashboard integration, also read
`docs/examples/app-service-integration-example.md`.

The example is deliberately small: one role, one mandate, one preference file,
one project charter, and one end-to-end read-model walkthrough. Real tenants
should live in private repos and symlink or copy only the generic-compatible
overlay into this kernel.

The walkthrough shows how forecast and action-impact read models feed strategy
review and learning-transition candidates without moving tenant policy into the
public kernel.

Run the two executable walkthroughs directly if you want to see the learning
path without reading every test:

```bash
make source-coverage-walkthrough
make learning-loop-walkthrough
```

If you are evaluating adoption in a real organization, read
`docs/field-validation-pilot.md` and `docs/templates/field-pilot/README.md`
next. They turn the kernel into a bounded before/after test on one recurring
decision pipeline.

## Agent Prompt

```text
You are helping me evaluate cognitive-firm. Read README.md, docs/PROTOCOLS.md,
docs/first-30-minutes.md, docs/adopting-cognitive-firm.md,
docs/abstraction-map.md, docs/resource-event-catalog.md,
docs/blueprints/README.md, docs/kernel-invariants.md,
docs/recursive-organization.md, docs/t1_t2_upgrade_matrix.md, org/README.md, and
src/cognitive_firm/orchestration/README.md. Pay special attention to the
kernel service, identity provider adapter, actor identity, actor membership,
identity provisioning, tenant isolation, and lease boundary.
Then explain the kernel/app/tenant boundary, what state is durable, and what I
should customize for my own organization without hard-coding tenant policy into
the kernel.
```
