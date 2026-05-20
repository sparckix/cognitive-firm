# Strategy Office Interface

**Module:** `cognitive_firm.orchestration.strategy_office`

The strategy-office interface is an observer layer over organizational learning
carriers. It reads evidence gaps, human work, damage signals, failed runs,
forecast-market summaries, action-impact summaries, and charter issues, then
emits strategy-review findings without changing routing, mandates, budgets, or
task state.

The closest predecessor is a general-office alignment audit: a separated
review function that asks whether operational success is still aligned with the
charter. An inverter is related but different: it generates falsification tests
against candidate findings inside a tenant loop.

It is a primitive, but not a default new role. Tenants may bind the primitive to
a concrete role office such as a reviewer, manager, research director, or
principal-side strategy review. The public kernel only defines the portable
finding shape and conservative review rules.

## Why This Is Not A New Mandatory Role

A role owns authority. The strategy-office primitive owns a view.

Making it a default role would add burden to every organization and would
smuggle one tenant's policy into the public kernel. Keeping it as an interface
lets different tenants decide whether strategy review is done by a manager,
reviewer, research director, principal, or dedicated office.

## What It Reads

The implementation reads:

- project-charter issues;
- blocking evidence gaps;
- human-work sessions requiring receipts or ready for agent follow-up;
- recent damage signals;
- failed run checkpoints;
- forecast-market summary state;
- forecast decision-use rows;
- forecast score debt;
- high-confidence misses;
- forecast reflexive insights;
- forecast maintenance items;
- action-impact rows requiring human review;
- local actions with negative externalities.

Future tenants can add adapters for trajectory ledgers or domain-specific
ledgers without changing the core interface.

## What It Emits

The portable `StrategyOfficeFinding` shape includes:

- `finding_id`;
- `kind`;
- `severity`;
- `recommendation`;
- `rationale`;
- `object_ref`;
- `scope`;
- `review_question`;
- `suggested_owner_role`;
- `candidate_transition_kind`;
- `source_refs`;
- `promotion_gate`;
- `promotion_evidence_required`;
- `observer_only`;
- `metadata`.

The `observer_only` flag defaults to true. A finding is a review object, not an
instruction to mutate state.

## Design Rationale

The strategy office is best understood as a general-office pattern, not as a
new executor. Its job is exception review:

- detect charter underspecification and alignment-risk surfaces;
- detect when learning carriers are missing or stale;
- detect when human handoffs, evidence gaps, damage signals, or failed runs
  should affect future work;
- ask whether local optimization created project or system externalities;
- notice forecast calibration failures or decision-use gaps;
- convert repeated anomalies into candidate state transitions;
- keep those transitions reviewable by an authorized role.

This is why each finding carries a `review_question`,
`candidate_transition_kind`, and optional promotion evidence. The primitive
should make the next organizational question crisp. It should not answer that
question by silently changing the organization.

## Relationship To Inversion

Inversion can exist at several levels, but it is not the main ancestor of this
interface:

- inner runtime inversion: a tenant loop may run falsification tests on a
  candidate;
- post-hoc review inversion: a reviewer may invert a closure attempt, paper
  draft, or mandate edit;
- strategy-office inversion: the organization asks whether the current
  objective, routing pattern, or learning carrier is the wrong object.

The kernel only owns the organization-level review shape as an observer
finding. Tenant loops own runtime inverter implementations.

## Relationship To General Office Review

General-office review asks whether a project, role, or operating unit is
optimizing a narrow proxy while missing the charter's broader object. In
cognitive-firm, that pattern appears as:

- charter-alignment findings;
- forecast decision-use/source-health findings;
- evidence and human-work source-health findings;
- run-failure and damage-signal findings;
- calibration and scoring debt;
- local optimization externality findings;
- human-review requirements before reusing an action class.

This is a read model over learning carriers, not a live strategic command
center.

## Relationship To Forecasts And Action Impact

Forecast markets answer, "What do we expect before action?"

Action-impact rows answer, "What happened after action?"

The strategy office asks, "What should the organization inspect because those
two surfaces reveal debt, externality, calibration failure, or source-health
gaps?"

This is why the strategy-office interface depends on read models rather than
live policy. If a forecast market has contracts but no decision-use rows, the
right strategy finding is to repair the source emitter, not to optimize harder.

## Tenant Boundary

Tenants own:

- domain-specific strategy policy;
- who reviews findings;
- whether a finding becomes a mandate change, evidence gap, forecast contract,
  human-work session, or task;
- promotion rules from observer finding to live routing;
- any tenant-specific inverter or strategy-office implementation.

The public kernel owns:

- portable finding shape;
- observer-only default;
- conservative findings over generic forecast and action-impact read models;
- conservative findings over evidence gaps, human work, damage signals, and
  failed runs;
- tests for normalization and source-health behavior.

## Tests

Covered by `tests/test_strategy_office.py`.
