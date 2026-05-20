# Project Charter Protocol

**Status:** protocol spec for tenant/project overlays.
**Kernel module:** `cognitive_firm.orchestration.project_charter`.

The project charter protocol keeps a unit of work aligned with its intended
object as agents, evaluators, and tooling optimize around it. It is a
scope-fidelity protocol, not a labor-routing system and not a project-type
ontology.

The kernel owns the protocol shape. Each tenant owns the actual charters,
anchors, thresholds, examples, and enforcement scripts.

## Purpose

Long-running agentic work drifts when the only durable instruction is a prompt
or task title. The charter gives the organization a small, inspectable contract
that future dispatch, review, forecasting, and audit surfaces can reference
without embedding tenant policy in the kernel.

The protocol answers:

- What question or operational objective is this project actually pursuing?
- What is explicitly out of scope?
- What end states should close or stop the project?
- What forecast, if any, should be tracked before major work starts?
- What prior work is inherited?
- Which deterministic or semi-deterministic anchors show whether the work is
  still touching the intended object?

## Charter Location

Recommended tenant path:

```text
tenants/<tenant_id>/projects/<project_id>/project_charter.md
```

For private deployments, `tenants/<tenant_id>/` may be a symlink to a private
repo. The public kernel should not contain tenant project content.

## Required Sections

### Core Question

The plain-language object of the work. It should be narrow enough that a future
reviewer can say whether a deliverable answered it.

### Out Of Scope

Known adjacent objectives that should not be smuggled into the project. This is
especially important for agents because nearby tasks can look productive while
changing the object of work.

### End States

Concrete conditions that close, pause, or kill the project. End states can be
positive, negative, or administrative.

### Forecast Type

Whether the project needs a forecast before work begins:

- `none` — no forecast needed.
- `directional_forecast` — rough likelihood, expected effort, and routing
  advice are enough.
- `probabilistic_forecast` — calibrated probability, effort estimate, and
  later scoring are required.

Forecasts should inform allocation. They do not replace principal authority or
role mandates.

### Inheritance

Prior artifacts, constraints, ledgers, external commitments, or tenant-specific
state this project inherits. The inheritance list should be explicit enough
that another role can reconstruct context without reading the whole tenant
repo.

### Anchor Proxies

Tenant-defined checks that connect the project to observable artifacts. Anchors
can be tests, checklist IDs, gate IDs, query fingerprints, schema predicates,
or external validation handles.

Good anchors are object-level. They should fail when the project drifts even if
the prose still sounds plausible.

Examples:

```text
anchor: approval_boundary_preserved
type: checklist_id
predicate: vendor onboarding still requires compliance approval above threshold
```

```text
anchor: customer_export_schema_unchanged
type: schema_predicate
predicate: exported account rows include the mandated retention fields
```

```text
anchor: theorem_target_still_present
type: test_id
predicate: formal target remains in the theorem dependency graph
```

## Enforcement

The protocol supports three enforcement levels:

| Level | Use when | Behavior |
|---|---|---|
| Advisory | A tenant has no parser or anchor runner yet | Roles read the charter before dispatch and cite it in review. |
| Parsed | Charter sections can be extracted deterministically | Predispatch can fail on missing sections or changed end states. |
| Anchored | Anchor proxies have executable checks | Predispatch and post-review can block or flag drift against anchors. |

Semantic review is useful for surfacing possible drift, but it should remain
advisory unless paired with tenant-defined anchors.

The public kernel ships the parsed level: `parse_project_charter()`,
`load_project_charter()`, and `validate_project_charter()` validate required
sections, forecast-type values, and basic anchor-proxy shape. Tenant validators
can layer executable anchor checks on top.

## Boundaries

The charter protocol is not:

- a role mandate;
- a permission system;
- a supervisor or labor router;
- a taxonomy of project types;
- a retrieval plan;
- a substitute for evidence review.

Those concerns may reference the charter, but they should not be collapsed into
it.

## Tenant Overlay Rule

Public kernel artifacts may describe the charter format and optional parser
interfaces. Tenant overlays supply:

- project charters;
- domain vocabulary;
- anchor proxy definitions;
- enforcement thresholds;
- evidence files;
- forecast ledgers;
- closure decisions.

If a generic charter tool needs tenant names, scientific terms, customer names,
or domain-specific scoring criteria to make sense, that logic belongs in the
tenant overlay.
