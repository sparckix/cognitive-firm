# First 30 Minutes

This path is for a new reader or agent opening the public kernel for the first
time. It verifies the repo, explains the durable boundary, and shows where an
organization would attach its own overlay.

## 0-5: Run One Governed Action

Start with the shortest no-cost proof before reading the whole repo:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
make first-gated-action
```

This runs one fictional Kettle & Compass workflow: a role-bearing service actor
claims work, opens a run, writes an attested artifact, receives a bounded
human-work receipt, completes a governed exit, records outcome and
accountability closure, and emits a governed-run bundle summary.

What to look for in the JSON:

- `authority_snapshot`: which role/mandate authorized the work;
- `work_item`: the claimable work and governed exit;
- `human_work_sessions`: bounded human contribution with receipt state;
- `action_attestations`: machine provenance for the artifact;
- `outcome_links`: measured-outcome placeholder for later verdicts;
- `accountability_cases`: accountable closure for residual risk;
- `bundle_validation.ok`: whether the replayable audit packet validates.

## 5-10: Identify the Boundary

Open the repository root as an Obsidian vault if you prefer a linked-doc view.
The repo ships a minimal `.obsidian/` config that keeps links relative and
starts on `README.md`.

Read first:

1. `README.md`
2. `docs/kernel-invariants.md`
3. `docs/abstraction-map.md`

Then skim as needed:

- `docs/PROTOCOLS.md` for the protocol index;
- `docs/examples/README.md` for runnable proof paths and inspection guides;
- `docs/resource-event-catalog.md` for state surfaces;
- `docs/reader-checklist.md` for an adoption-oriented review checklist;
- `docs/adopting-cognitive-firm.md` for integration patterns;
- `docs/recursive-organization.md` for governed self-organization.

The key distinction: cognitive-firm is a governance kernel, not an agent
runtime. Role offices, mandates, transition events, evidence gaps, human work,
and app projections live here. Tenant-specific research policy, scoring
engines, private evidence, and business systems live in overlays or adapters.

## 10-20: Run the Public Smoke

```bash
make release-candidate-check
```

`release-candidate-check` composes the public, clean-container, and diff-audit
gates:
`smoke-public` runs the Python test suite, renders the organization surface,
exercises the framework-neutral runtime adapter, checks the kernel service's
SQLite fenced-mutation path, runs deterministic app-integration and app-service
conformance fixtures, checks source-coverage and learning-loop walkthroughs,
verifies a minimal backup/restore path, validates package entry points, checks
the documentation surface, and builds Orbit.
`smoke-docker` builds and probes the clean container path.
`release-diff-audit` classifies the current changed paths into review buckets
and fails on unclassified release surfaces. If you are iterating locally and
want the faster split form, run:

```bash
make smoke-public
make docs-surface-check
make smoke-docker
make release-diff-audit
```

The release gate uses deterministic fixtures. Live subscription/local agent
runs are intentionally separate because they depend on local login state and
model output. For a bounded live proof after the deterministic gate is green,
use a one-step budget and compact planner prompt:

```bash
make self-evolving-agent-preflight AGENT_RUNTIME=codex AGENT_ADAPTER=codex_exec
make self-evolving-org-agent-demo \
  AGENT_RUNTIME=codex \
  AGENT_ADAPTER=codex_exec \
  SELF_EVOLVING_DEMO_ITERATIONS=1 \
  SELF_EVOLVING_DEMO_BUDGET_UNITS=1 \
  SELF_EVOLVING_PLANNER_PROMPT_MODE=compact
```

If the live planner returns invalid JSON or times out, the harness records a
rejected planner receipt and stops before applying a governed mutation.

If the build backend from `requirements.txt` is installed, the package check
also builds and inspects a local wheel. It should not require private tenant
files.

If you only want the kernel read model:

```bash
python -m cognitive_firm.orchestration.org_surface
```

If your immediate question is "what did a local/subscription agent invocation
do, under what role authority?", run the no-cost audit wedge and keep the
runbook:

```bash
PYTHONPATH=src python scripts/agent_fleet_audit_demo.py \
  --output-dir .cognitive-firm-runs/agent-fleet-audit
```

Start with
`.cognitive-firm-runs/agent-fleet-audit/agent-fleet-audit-runbook.md`, then
inspect the packet JSON if you need the exact receipt and bundle payload. The
fixture does not call an external runtime; it shows the receipt and bundle
shape used by live daemon dispatch.

If you want the broader suite with failure fixtures and an external-runtime
projection:

```bash
make adoption-demo
```

The demo first runs a fictional Kettle & Compass product-claim workflow using
only native kernel primitives, then runs governance failure fixtures, then
projects a LangGraph-style lifecycle into the kernel. All paths use
deterministic stubs and make no external calls. For an existing run, export a
compact review view with:

```bash
cognitive-firm-governed-run-bundle <run_id> --summary
```

## The Fast Path: Install a Runnable Organization

The smoke above verifies the kernel. To see a *running governed organization*
without assembling one by hand, use the distribution layer:

```bash
cognitive-firm-distro list
cognitive-firm-distro install starter-firm --into ./my-firm
```

This brings up a governed organization — a principal, an operating lead, an
analyst, and a closure reviewer, with mandates and a day-one governance loop —
as its own git repository. The install is transactional: the installer verifies
the organization's governance graph and only then commits it, tagged
`install/starter-firm/<version>`. `cognitive-firm-distro rollback` undoes it.

See [`docs/protocols/distribution.md`](docs/protocols/distribution.md). The
rest of this path inspects the kernel that distro is built on.

## 20-25: Inspect the Kernel Surface

Read in this order only if you need to extend the kernel rather than just adopt
it:

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
projections from replay, not create a second source of truth.

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
