# Learning Loop Demo

This narrative shows how cognitive-firm turns work observations into durable
organizational state without importing tenant policy into the public kernel.

## Scenario

A research project is about to rerun a branch that has failed twice. The role
office should notice the repeated failure, request missing evidence, record any
human work required, and make the future behavior reviewable.

## 1. Project Charter

The tenant starts with a charter:

```yaml
project_id: demo-branch
core_question: Does this branch have independent evidence, or is it repeating a stale route?
out_of_scope:
  - rerunning the same route without a new source
end_states:
  - independent evidence found
  - branch killed
  - human source check requested
forecast_type: branch_allocation
```

The public parser validates the charter shape. Tenant validators can add
domain-specific anchors.

## 2. Evidence Gap

A reviewer finds the branch lacks an external source. That becomes an evidence
gap:

```text
gap_type: missing_source
severity: blocking
target: demo-branch
description: Need an independent source before rerunning this branch.
owner_role: role.research_director
```

Blocking gaps surface in `org_surface` and in work discovery before routine
work.

## 3. Human Work Session

If the missing source is private or non-digitized, the human performs bounded
object-level work:

```text
work_mode: source_check
bottleneck_class: access
objective: inspect restricted source and attest whether it supports the claim
receipt_required: true
observability: attested
```

The kernel records the session and receipt metadata. It does not pretend to
observe the private work directly.

## 4. Organization Surface

Before a role starts material work, the organization surface can show:

- one blocking evidence gap;
- one active or completed human work session;
- any forecast-market debt;
- any action-impact review items;
- any strategy-office findings;
- active approved learning events.

The surface is a projection. It does not apply changes.

The service also exposes a narrower pre-work context projection:

```text
GET /kernel/work-discovery?assigned_to=role.research_director&project_id=demo-branch&cue=same+branch+failure
```

That read joins matching approved learning events to their outcome links and
routine-review state, then returns matching work-discovery candidates plus a
`context_packet` digest over the exact refs/query basis. If the context changes
a concrete work surface, the caller can cite the packet and records that
separately as a learning-event encounter. The read route itself does not write
memory or dispatch work.

## 5. Strategy Finding And Candidate

The strategy-office interface may emit a finding:

```text
source_kind: evidence_gap
severity: blocking
rationale: Branch repeats a stale route without independent evidence.
recommended_transition: evidence_standard_change
```

The learning-transition compiler can turn that into a candidate:

```text
transition_kind: mandate_review
proposed_payload:
  cue: repeated stale route
  change: require independent evidence or explicit kill decision before rerun
```

This is still reviewable, not self-applying.

## 6. Approved Learning Event

After review, the candidate can be promoted:

```text
learning_unit_kind: routine_change
decision_use: Do not rerun a branch after repeated stale-route failure without independent evidence.
future_application_cue: same branch failure repeats
approved_by: role.principal
approval_ref: review/demo-branch-1
```

Future replay uses deterministic role, tenant/project, and cue filters. Tenant
code decides how the actual route, mandate, charter, or policy adapter changes.

## What This Demonstrates

The kernel does not need a generic optimizer to learn. It needs typed carriers,
reviewable transitions, and a visible pre-work surface. Tenants can make this
more opinionated by adding forecast markets, action-impact ledgers, domain
validators, or runtime adapters on top.

## Executable Check

Run:

```bash
make learning-loop-walkthrough
```

The fixture creates a temporary evidence gap, A2H human-work session, human
receipt, action attestation, accountability case, forecast summary, and
action-impact summary. It then builds the organization surface, compiles a
reviewable transition candidate, promotes one approved learning event, and
checks that the event is visible on the final organization surface and replayed
for matching future work.
