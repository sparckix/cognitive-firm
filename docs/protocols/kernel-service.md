# Kernel Service

**Status:** local service adapter shipped.
**Module:** `cognitive_firm.kernel_service`
**Tests:** `tests/test_kernel_service.py`

The kernel service is a small HTTP boundary over Python kernel functions. It is
not a second backend and not a new source of truth.

Use it when an app surface, script, or local operator wants to call kernel
commands without importing Python modules directly.

## Boundary

The service owns transport:

- HTTP request parsing;
- JSON response envelopes;
- route dispatch;
- process hosting.

The kernel primitives own behavior:

- state transitions;
- validation;
- receipt and accountability invariants;
- organization-surface projection.

This keeps Orbit, Slack/Teams adapters, CLI wrappers, and future dashboards
from reimplementing primitive lifecycle rules.

`GET /kernel/org-surface` and `GET /kernel/accountability-summary` are built
from the service's configured kernel logs: evidence gaps, human work,
forecast/action-impact summaries, governance changes, accountability cases,
approved learning events, learning encounters, outcome links, routine reviews,
and transition/run rows. A service deployment that points those logs at a
tenant workspace gets one coherent projection without replacing the primitive
modules.

## Current Routes

```text
GET  /health
GET  /kernel/org-surface
GET  /kernel/accountability-summary
GET  /kernel/attention/{actor_id}
GET  /kernel/vocabulary
GET  /kernel/command-surface
GET  /kernel/operator-path
GET  /kernel/governance-change-template
GET  /kernel/governance-changes
GET  /kernel/governance-changes/{proposal_id}
GET  /kernel/governance-changes/{proposal_id}/review-packet
POST /kernel/governance-changes
POST /kernel/governance-changes/{proposal_id}/decision
POST /kernel/governance-changes/{proposal_id}/outcome-link
POST /kernel/actors
POST /kernel/memberships
POST /kernel/memberships/{assignment_id}/revoke
GET  /kernel/leases
POST /kernel/leases
POST /kernel/leases/{lease_id}/release
POST /kernel/mutation-events
POST /kernel/governed-run-bundles/build
POST /kernel/governed-run-bundles/validate
POST /kernel/mutation-proofs/build
POST /kernel/mutation-proofs/validate
GET  /kernel/multi-agent-trace-events
POST /kernel/multi-agent-trace-events
GET  /kernel/failure-attribution-packets
POST /kernel/failure-attribution-packets
GET  /kernel/delegation-graph
GET  /kernel/phase-execution-plans
POST /kernel/phase-execution-plans
POST /kernel/phase-execution-plans/{plan_id}/directives
POST /kernel/phase-execution-plans/{plan_id}/verification-feedback
GET  /kernel/protocol-experiments
POST /kernel/protocol-experiments
POST /kernel/protocol-experiments/{experiment_id}/observations
POST /kernel/protocol-experiments/{experiment_id}/reports
GET  /kernel/action-impact/policy-evaluations
POST /kernel/action-impact/policy-evaluations/evaluate
GET  /kernel/action-impact/policy-promotion-packets
POST /kernel/action-impact/policy-promotion-packets
POST /kernel/action-impact/policy-promotion-packets/{packet_id}/governance-change
GET  /kernel/policy-decisions
POST /kernel/policy-decisions/evaluate
GET  /kernel/decision-procedure-profiles
GET  /kernel/decision-aggregation-cases
POST /kernel/decision-aggregation-cases
POST /kernel/decision-aggregation-cases/{case_id}/positions
POST /kernel/decision-aggregation-cases/{case_id}/compute
POST /kernel/decision-aggregation-cases/{case_id}/route-escalation
GET  /kernel/capability-signals
POST /kernel/capability-signals
POST /kernel/capability-signals/{signal_id}/route
POST /kernel/capability-signals/{signal_id}/close
POST /kernel/execution-evidence/route
POST /kernel/governed-action-composition
POST /kernel/human-work
GET  /kernel/human-work-pressure
GET  /kernel/human-speed-envelope
POST /kernel/human-work/{session_id}/state
POST /kernel/human-work/{session_id}/interaction
POST /kernel/human-work/{session_id}/receipt
POST /kernel/accountability-cases
POST /kernel/accountability-cases/from-damage-signal
POST /kernel/accountability-cases/{case_id}/status
GET  /kernel/operating-units
GET  /kernel/operating-units/{unit_id}
GET  /kernel/operating-unit-dashboard
POST /kernel/operating-units
GET  /kernel/runs
GET  /kernel/runs/{run_id}
GET  /kernel/runs/{run_id}/resume
POST /kernel/runs
POST /kernel/runs/{run_id}/checkpoints
POST /kernel/runs/{run_id}/state
GET  /kernel/learning-events
GET  /kernel/learning-events/replay
GET  /kernel/learning-events/summary
GET  /kernel/learning-events/{learning_event_id}/loop
GET  /kernel/work-discovery
POST /kernel/work-discovery/context-packet/verify
POST /kernel/learning-events
GET  /kernel/learning-transition-candidates
POST /kernel/learning-transition-candidates/{candidate_id}/governance-change
POST /kernel/learning-event-encounters
GET  /kernel/outcome-links
GET  /kernel/outcome-links/summary
POST /kernel/outcome-links
POST /kernel/outcome-links/{outcome_link_id}/snapshots
POST /kernel/outcome-links/{outcome_link_id}/verdict
POST /kernel/outcome-links/{outcome_link_id}/void
POST /kernel/outcome-links/{outcome_link_id}/reversal-review
GET  /kernel/agent-invocations
GET  /kernel/action-attestations
GET  /kernel/provenance-timeline
GET  /kernel/provenance-graph
GET  /kernel/provenance-report
POST /kernel/action-attestations
GET  /kernel/formal-verifications
POST /kernel/formal-verifications/provider-payload
GET  /kernel/routine-reviews
GET  /kernel/routine-reviews/due
GET  /kernel/routine-reviews/summary
POST /kernel/routine-reviews
POST /kernel/routine-reviews/{review_id}/start
POST /kernel/routine-reviews/{review_id}/record-outcome
POST /kernel/routine-reviews/{review_id}/retire
GET  /kernel/work-items
GET  /kernel/work-items/{work_id}
POST /kernel/work-items
POST /kernel/work-items/claim-next
POST /kernel/work-items/{work_id}/claim
POST /kernel/work-items/{work_id}/start
POST /kernel/work-items/{work_id}/heartbeat
POST /kernel/work-items/{work_id}/complete
POST /kernel/work-items/{work_id}/fail
POST /kernel/work-items/{work_id}/retire
POST /kernel/work-items/{work_id}/requeue
POST /kernel/a2a/messages
POST /kernel/gates/{gate_id}/resolve
POST /kernel/directives
POST /kernel/controls
POST /kernel/chat/messages
POST /kernel/roles/{role_id}/agent-utilization
GET  /kernel/work-inbox/{actor_id}
```

Read routes for resource-projected primitives can render the common
[`Resource Envelope`](resource-envelope.md) when called with `resource=true`.
For example:

```text
GET /kernel/outcome-links?resource=true
GET /kernel/governance-changes?resource=true
GET /kernel/governance-changes/{proposal_id}?resource=true
GET /kernel/operating-units?resource=true
GET /kernel/operating-units/{unit_id}?resource=true
GET /kernel/learning-events?resource=true
GET /kernel/learning-events/replay?resource=true
GET /kernel/learning-transition-candidates?source=human_work
GET /kernel/learning-transition-candidates?source=attention
GET /kernel/learning-transition-candidates?source=execution
GET /kernel/learning-transition-candidates?source=phase_execution
GET /kernel/learning-transition-candidates?source=protocol_experiment
GET /kernel/routine-reviews?resource=true
GET /kernel/routine-reviews/due?resource=true
GET /kernel/work-items?resource=true
GET /kernel/work-items/{work_id}?resource=true
GET /kernel/multi-agent-trace-events?resource=true
GET /kernel/failure-attribution-packets?resource=true
GET /kernel/delegation-graph?resource=true
GET /kernel/phase-execution-plans?resource=true
GET /kernel/protocol-experiments?resource=true
GET /kernel/decision-aggregation-cases?resource=true
GET /kernel/capability-signals?resource=true
```

Command inspection route:

- `GET /kernel/command-surface?query=...` returns exact or
  separator-normalized matches from the repository's known Make targets and
  Python scripts. It is a suggestion surface for operators, agents, and
  adopter-built tools that need canonical commands for a task description. It
  does not execute commands, schedule work, or mutate kernel state.

  Matches also include projection-only `authority_effects` for selected
  governance-sensitive commands. Each effect declares the command's
  `decision_class` and/or `resource_class`, then reports whether the current
  authority-domain configuration resolves that effect, falls back to the T1
  single-authority rule, or needs a more explicit domain. These effects are
  metadata, not permissions: they do not approve, block, schedule, or run the
  command. If the authority-domain file cannot be loaded, effect validation is
  reported as `not_evaluated` rather than as a T1 fallback. The terminal
  carrier is `cognitive-firm-userland commands "adoption readiness packet"`.
  Passing `role_id=<role>` adds a read-only source-role escalation trace for
  each typed effect, showing whether that role reaches the authority domain
  resolved for the effect.

  The route may also attach `operator_guidance` for a small set of
  first-review commands. For example,
  `cognitive-firm-userland commands "first serious review"` returns the
  recommended review sequence (`make smoke-public`, `make
  adoption-onramp-packet`, `make adoption-readiness-packet`) as ranked
  metadata. This is sequencing guidance over existing commands, not a runner or
  workflow plan.

- `GET /kernel/operator-path?path_id=first_review` returns the same named path
  directly for adopter-built surfaces that do not want fuzzy command matching.
  The terminal carrier is `cognitive-firm-userland operator-path first_review`.
  It includes a short purpose, use-when guidance, and `not_a` boundaries so a
  custom dashboard can present the path without implying a runner. It is still
  projection-only: the route does not execute commands, schedule work, mutate
  kernel state, or approve adoption.

  Research anchor: this borrows the boundary discipline of
  object-capability authority and row-polymorphic effect typing, not their
  runtimes. See Mark S. Miller's
  [Robust Composition thesis](https://www.erights.org/talks/thesis/markm-thesis.pdf)
  for capability-style explicit authority and Daan Leijen's
  [Koka effect-types work](https://www.microsoft.com/en-us/research/publication/koka-programming-with-row-polymorphic-effect-types/)
  for effects declared at program boundaries.

Residual-right holder route:

- `GET /kernel/residual-rights/holder?scope_kind=...&scope_ref=...` returns the
  active explicit residual-right `holder` when one exists and always returns a
  `holder_resolution` read model. If no assignment exists, the resolution can
  project the accountable role from authority domains with
  `source: "authority_domain"` and `projection_only: true`. That projection is
  an adoption/surface affordance only: it does not create a residual-right
  assignment and does not authorize a residual decision. Optional
  `tenant_id`, `project_id`, and `operating_unit_id` query parameters provide
  context for class-scoped authority-domain resolution.

Provenance inspection routes:

- `GET /kernel/provenance-timeline` joins selected run/checkpoint events,
  action attestations, human-work sessions and receipts, governance changes,
  outcome links, routine reviews, approved learning events, and learning-use
  receipts into a readable ordered projection.
- `GET /kernel/provenance-graph` rebuilds the same selected records as
  event/ref nodes and projection-only mention edges. It is for lineage and
  "why/what-after" visualizations, not workflow state.
- `GET /kernel/provenance-report` packages the same selected provenance into a
  portable reviewer handoff with source counts, coverage gaps, caveats, review
  questions, high-signal refs, a bounded timeline excerpt, and Markdown export.
  It is derived from canonical logs and stores no report row.

All three require at least one selector: `run_id`, `ref`, `tenant_id`, or
`tenant_id` plus `project_id`. Project ids are tenant-scoped unless a `run_id`
anchors the query.

Human-work service writes:

- `POST /kernel/human-work` creates ordinary bounded human work or A2H work
  requests.
- `GET /kernel/human-work-pressure` returns observer-only A2H pressure groups
  by role and bottleneck class. It accepts optional
  `agent_counterparty_role`, `tenant_id`, `project_id`, `stale_after_hours`,
  and `concentration_threshold` query parameters. Tenant/project filters are
  applied before pressure is summarized. These groups are review signals, not
  routing decisions: access/labor/cognition pressure can suggest source repair,
  tooling, or mandate review, while taste, safety, relationship, and authority
  work remains an explicit human boundary.
- `GET /kernel/human-speed-envelope` returns `human_speed_envelope.v1`, a
  read-only classification of accountable speed from explicit facts:
  `risk_tier`, `bottleneck_class`, `deployment_class`, `reversible`,
  `external_side_effect`, `repeated_similar`, `private_context`,
  `harm_occurred`, and `residual_risk_accepted`. The output recommends a
  required record shape such as transition/attestation, sample policy,
  human-work receipt, policy decision/gate plus lease, or accountability case.
  It does not authorize, dispatch, schedule, sample, or approve anything.
- `GET /kernel/learning-transition-candidates?source=human_work` compiles
  whole-firm A2H pressure groups into observer-only review candidates. Each
  candidate keeps source refs back to human-work sessions and asks whether
  repeated pressure should become source repair, tooling, mandate review,
  receipt discipline, or an intentionally preserved human boundary. It does
  not automate, reroute, or close human work.
- `GET /kernel/learning-transition-candidates?source=attention` compiles the
  routed L1 attention feed into observer-only candidates for unrouted signals,
  stale actionable signals, and repeated role/signal pressure. It can ask for
  review of authority domains, actor memberships, mandates, route policy, or
  receipt discipline, but does not reroute, page, assign, close, or schedule
  work.
- `POST /kernel/learning-transition-candidates/{candidate_id}/governance-change`
  is exposed in userland as `cognitive-firm-userland proposal-from-candidate`.
  It copies candidate rationale and source refs into a governance proposal but
  leaves target, risk, rollback, and invariant evidence with the caller.
- `POST /kernel/human-work/{session_id}/state` moves the session through the
  lifecycle and enforces receipt-before-integration when configured.
- `POST /kernel/human-work/{session_id}/interaction` appends coordination
  events without storing a full transcript.
- `POST /kernel/human-work/{session_id}/receipt` appends a structured
  `HumanWorkReceipt`: actor, bounded claim, receipt type/ref, subject refs,
  artifact refs, confidence, observability, review flag, and metadata. This is
  the service-native path for "human reviewed this agent output": cite the
  agent output and action-attestation refs as receipt subjects, then let later
  action attestations or outcome links cite the human-work receipt.

`GET /kernel/work-discovery?assigned_to=role.manager&tenant_id=...&cue=...`
is the pre-work context surface for app and agent userland. It joins matching
approved learning events to their outcome links and routine reviews, returns
matching work-discovery candidates when a role/office selector is present, and
includes a `context_packet` digest over the exact refs/query basis. The same
route accepts exact structured filters:
`cue_signature`, repeated `resource_ref`, and repeated `topology_ref`. Those
filters match learning-event metadata and allow tools, verifiers, state
surfaces, or memory shards to retrieve relevant approved learning without
creating a durable role office. No-role structured queries stay learning-only:
they do not pull generic inbox/work-discovery candidates into the packet basis.
The packet is a citeable projection receipt, not a canonical memory store. If
the returned context influences a concrete work surface, the consumer records
telemetry through
`POST /kernel/learning-event-encounters`; the read route does not write that row
automatically.
`POST /kernel/work-discovery/context-packet/verify` is also read-only. It
accepts a captured `context_packet`, recomputes the digest from its embedded
`basis`, checks the `ctx_...` id, and returns issues. This verifies packet
integrity only; it does not replay current logs, authorize a learning-use
receipt, or make the packet a canonical memory store.
`cognitive-firm-userland work-context --assigned-to ... --cue ...` is the
terminal view over the same projection. It prints the `context_packet` so a
later learning-use receipt can cite the exact pre-work context without turning
read discovery into application.
`cognitive-firm-userland work-context --cue-signature ... --resource-ref ...
--topology-ref ...` is the non-role exact-filter form. It is still a read model;
it does not rank, dispatch, or apply work. `--learning-only` remains available
for role-scoped context when the operator wants to suppress work candidates.
`cognitive-firm-userland learning-use ...` records the later
`POST /kernel/learning-event-encounters` receipt.

`POST /kernel/governed-action-composition` is a read-only proof-chain checker
for already captured action/demo output. It accepts `action_label`, `profile`,
`observed_result`, optional `evidence_refs`, and returns
`governed_action_composition_packet.v1`: a typed matrix of required authority,
work, human-work, attestation, outcome, bundle, context-packet, and
learning-use links for the selected profile. The route does not execute
commands, schedule missing work, approve governance, verify row existence, or
write kernel state. `cognitive-firm-userland composition-packet --observed-json
...` is the terminal preflight over the same route.

Learning-use encounter discipline:

- `encountered` can be recorded as a lightweight telemetry row.
- `applied` requires `work_ref`, `evidence_refs`, or `context_packet_ref`.
- `ignored` and `deferred` require `reason`.
- If the request also includes the captured `context_packet` object, the
  service verifies the packet digest and rejects the encounter unless the
  packet basis contains the target `learning_event_id`. This is optional
  stronger validation over a captured projection; it does not persist the
  packet as memory. Accepted rows carry
  `metadata.context_packet_verification=digest_basis_includes_learning_event`
  plus the verified packet digest.

This makes the work-discovery context useful to operators while preserving the
boundary: the service records what was seen and how it was used; it does not
apply learning or execute a workflow.

`GET /kernel/learning-events/{id}/loop` is the one-learning-unit compounding
view. It joins the approved learning event to its learning-use encounters,
context-packet refs, verified context-packet refs, outcome links, routine
reviews, overdue review ids, and evidence refs, then returns a `loop_state`
plus recommendation. It is a read-only projection for operators and
dashboards; it does not promote memory, apply learning, rank work, dispatch
work, or decide whether the lesson remains valid.

`GET /kernel/provenance-timeline?run_id=...` is a read-only operator view over
existing records. The route requires an explicit selector: `run_id`, `ref`,
`tenant_id`, or `tenant_id` plus `project_id`. Project ids are tenant-scoped
unless a `run_id` anchors the query. The route rejects selector-less calls
rather than returning a repository-wide event dump. It orders matching
run/checkpoint events, action attestations, human-work sessions, governance
proposals and approval events, outcome links, routine reviews, approved
learning events, and learning-use receipts. It is meant to answer "why did we
decide this, what evidence existed, and what happened after?" It reports caveats
when links are scope-based or missing, and it does not create tasks, rank next
steps, or mutate workflow state.
Queries by explicit `ref` can anchor on run refs, action-attestation refs,
agent-output refs, context-packet refs, or human-work receipt subject/artifact
refs when those refs are present in the underlying records.
When a run/ref query also has tenant or project scope, globally scoped records
that explicitly cite the ref are included, but records scoped to a different
tenant/project are excluded. Scope-only timelines stay exact and do not collect
global rows by default.
`cognitive-firm-userland timeline --run-id ...` is the terminal view over the
same route. Orbit's `ProvenanceTimelinePane` is a bundled read-only
visualization over this route via the local daemon proxy; custom dashboards can
call the same kernel-service route without changing provenance semantics.

`GET /kernel/provenance-graph?run_id=...` requires the same explicit selectors
and source logs as the timeline route, but returns projection-only `nodes` and
`edges` for custom visualizations. Event nodes are the matched records; ref nodes
are cited or mentioned refs; edges are record-to-mentioned-ref links. The graph
is not causal proof and not workflow state. Stronger semantics still live in the
underlying proposal, attestation, human-work, outcome-link, routine-review, and
learning-use records.
`cognitive-firm-userland graph --run-id ...` is the terminal carrier over this
route.

`GET /kernel/provenance-report?run_id=...` uses the same selectors and source
logs, then returns a portable handoff projection: coverage status, source
counts, caveats, review questions, high-signal refs, a bounded timeline
excerpt, and a Markdown rendering. It is a reviewer/export surface over
timeline and graph records, not a governed-run bundle, approval, or stored
report. `cognitive-firm-userland provenance-report --run-id ... --markdown`
is the terminal carrier for that handoff.

Decision aggregation routes record procedure evidence, not authority:

- `GET /kernel/decision-procedure-profiles` lists built-in profile recipes.
- `POST /kernel/decision-aggregation-cases` accepts either explicit
  `procedure_kind`/`quorum` or a `procedure_profile` shortcut. `case_id` is
  optional when a replayable client needs a stable receipt.
- `POST /kernel/decision-aggregation-cases/{case_id}/positions` records one
  eligible position. `position_id` is optional when the caller needs a stable
  receipt.
- `POST /kernel/decision-aggregation-cases/{case_id}/compute` computes the
  deterministic recommendation. The result still has to be consumed by a
  downstream mandate, policy, approval, accountability, or learning path.
- `POST /kernel/decision-aggregation-cases/{case_id}/route-escalation` turns
  an already-escalated case into a normal routed `CapabilitySignal` plus an
  observer-only learning-transition candidate. This is for quorum failure,
  abstention, recusal, or ties that should be inspected later. It does not
  resolve the decision, override the aggregation result, approve governance, or
  mutate files.
Terminal userland exposes this flow through `decision-profiles`,
`decision-cases`, `decision-open`, `decision-position`, `decision-compute`, and
`decision-route-escalation`.

Accountability routes:

- `POST /kernel/accountability-cases` writes the normal accountability case
  record.
- `POST /kernel/accountability-cases/from-damage-signal` takes a damage-signal
  object plus accountable role and authority-envelope refs, shapes the signal
  into a normal accountability-case request, and writes the same canonical
  case row. It does not clear the damage signal, decide remediation, mutate
  routing, or close the case.

`GET /kernel/governance-change-template` returns a read-only request skeleton
for `POST /kernel/governance-changes`, including required evidence fields and
invariant-check rows. It is an authoring aid only; it records no proposal and
does not relax the evidence-sufficiency gate. The terminal userland exposes
this as `cognitive-firm-userland proposal-template`, while
`cognitive-firm-userland proposal <proposal_id>` renders one existing
proposal's evidence and invariant status.
`GET /kernel/governance-changes?view=review` is the reusable proposal-review
projection for app surfaces and custom dashboards. It summarizes each proposal
into review state, evidence status, missing evidence, failed or unknown
invariants, evidence counts, and the decision route, while preserving the raw
proposal row as canonical state. `GET /kernel/governance-changes/{id}?view=review`
returns the same projection for one proposal. These routes are read-only and do
not decide, rank, or mutate proposals.
`GET /kernel/governance-changes/{id}/review-packet` packages one proposal's
review projection with evidence refs, invariant rows, selected provenance,
review questions, and a Markdown rendering. It is a reviewer handoff, not an
approval, outcome verdict, or second proposal record. The terminal carrier is
`cognitive-firm-userland proposal-packet <proposal_id> --markdown`.

Governance-change creation routes also understand an opt-in deletion-duty
request shape:

```json
{
  "require_deletion_duty": true,
  "retirement_candidate_ref": "org/policies/old-review.md",
  "net_growth_justification": "Required for the workload probe scorer.",
  "deletion_duty_evidence_refs": ["routine_review:review-pruning"]
}
```

When `require_deletion_duty` is true, the service appends a
`deletion_duty_checked` invariant check before running the normal
evidence-sufficiency gate. A structure-adding proposal without either a
retirement candidate or net-growth justification becomes blocked. Omitting the
flag preserves ordinary governance-change behavior.

Governance-change creation also accepts a typed `predicted_effect` compatible
with outcome-link prediction review:

```json
{
  "predicted_effect": {
    "metric_name": "handoff_rework_rate",
    "metric_unit": "ratio",
    "direction": "lower_is_better",
    "threshold": 0.1,
    "review_horizon": "after_next_10_handoffs",
    "expected_verdict": "improved"
  }
}
```

After the proposal has an explicit approval event, clients may call
`POST /kernel/governance-changes/{proposal_id}/outcome-link` to open the normal
outcome-link lifecycle from that prediction. The route carries the proposal's
metric identity and `predicted_effect` into `metadata.predicted_effect`; it does
not record measurements, compute a verdict, apply files, or reverse anything.
Planning-only measurements should use `POST /kernel/outcome-links` directly.

If present, the service validates and stores the prediction on the proposal.
The kernel still does not compute the metric; approved changes should carry the
same prediction into an outcome link for later verdict and routine-review
follow-up.

`POST /kernel/governed-run-bundles/build`,
`POST /kernel/governed-run-bundles/validate`,
`POST /kernel/mutation-proofs/build`, and
`POST /kernel/mutation-proofs/validate` are read-only projection routes even
though they use POST for structured JSON bodies. They do not write kernel
state, acquire leases, or authorize mutation.
`/kernel/mutation-proofs/build` may include `evidence_carrier_refs` to digest
execution evidence refs, such as trace events, capability signals,
learning-transition candidates, phase execution plans, or protocol experiment
reports, into the proof projection.

The execution-evidence POST routes do mutate evidence logs and therefore pass
through the same surface-write policy and lease checks as other kernel
mutations. They import observer-only evidence: trace events, failure
attribution packets, phase directives and verifier feedback, protocol
experiment observations and reports, and capability/abstention routing
signals. They do not approve governance changes or promote policies by
themselves.

`POST /kernel/execution-evidence/route` is the service-side composition route
for a common runtime/adapter condition: "the agent could not or should not
continue." It records a normal `CapabilitySignal`, optionally routes it,
returns the matching observer-only learning-transition candidate, and can draft
a governance-change proposal when the caller supplies
`governance_change_target_ref`. It does not approve the proposal, mutate files,
or run a worker. In lease-required deployments, the route uses one outer lease
on `execution_evidence:route`; it does not require callers to acquire separate
leases for the internal signal/candidate/proposal composition.

`POST /kernel/decision-aggregation-cases/{case_id}/route-escalation` uses the
same evidence-routing path for a narrower kernel condition: an aggregation
case has already computed to `escalated`. This keeps reviewer abstentions,
missing quorum, recusals, and ties visible to learning and governance without
inventing a second approval path.

`POST /kernel/action-impact/policy-promotion-packets/{packet_id}/governance-change`
is the corresponding composition route for offline action-impact evidence. It
projects a `review_ready` `PolicyPromotionPacket` into a
`GovernanceChangeProposal` with `change_kind=route_policy_change` and cites the
packet as evidence. It does not approve the change, apply a policy, choose
actions, or execute a runtime. In lease-required deployments, callers acquire
one lease on
`action_impact:policy_promotion_packet:{packet_id}:governance_change`.

`POST /kernel/action-attestations` and `POST /kernel/learning-events` create
canonical provenance and approved-learning rows. They are mutating service
routes, not read-only proof helpers. Demos and adapters should prefer these
routes over direct JSONL writes when exercising the kernel service boundary.

`GET /kernel/agent-invocations` is a read-only projection over
`ActionAttestation` rows whose `action_type` is `agent_cli_dispatch` and whose
metadata includes `agent_invocation_receipt.v1`. It supports `producer`,
`tenant_id`, `project_id`, `run_id`, `verification_status`, and `limit`
filters. Dashboards, demos, and runtime adapters should use this route when
they need recent local/subscription agent execution receipts without parsing
the full action-attestation ledger.

Run locally:

```bash
cognitive-firm-kernel-service --host 127.0.0.1 --port 8765
```

The service is stdlib-only. A tenant may wrap the same dispatch layer with
FastAPI, a trusted gateway, or a cloud runtime later, but that should remain
an adapter choice.

## Startup Viability

For a startup, the first viable deployment is:

```text
Python kernel functions
-> local kernel service
-> Orbit / CLI / notification surfaces
-> filesystem SourceConnector + Git audit/sync
```

This is appropriate for one accountable authority or a small trusted operator
set on one deployment. Git is audit, rollback, and synchronization. It is not
the runtime message bus.

Move to SQLite, Postgres, or another event backend when multiple active
operators need concurrent writes, stronger leases, or compliance evidence.

## Identity, Attribution, And Leases

Research and standards point to a split boundary:

- Authentication and federation should be delegated to established identity
  providers where possible.
- Actor attribution should be first-party because it is part of the kernel's
  accountability model.
- Leases should be first-party because they protect kernel resources and state
  transitions, not just HTTP sessions.

Practical interpretation:

- use OIDC/SAML/IdP integration for "who authenticated";
- record first-party `actor_id`, `role_id`, `surface`, `session_id`, and
  `correlation_id` on every mutation;
- use actor membership when a deployment needs explicit role/tenant/project
  authority for more than one human, agent, or service;
- add leases as kernel records over mutable resources before allowing
  concurrent multi-operator writes.

Do not let an external IdP decide organizational meaning. It can verify a
subject; the kernel decides whether that subject may act as a role, mutate a
resource, or close an accountability case.

## Research Anchors

- NIST SP 800-63-4: digital identity, identity proofing, authentication, and
  federation guidance.
- OAuth 2.0 / OIDC: delegated authorization and federated login patterns.
- OpenTelemetry semantic conventions: stable cross-service attribute names for
  traces, logs, and events.
- Gray and Cheriton leases: time-bounded control over distributed resources;
  modern variants preserve the same basic idea with fencing and expiry.

## T1 / T2

| Concern | T1 local service | T2 upgrade |
|---|---|---|
| Authentication | local process boundary or shared token | IdP-backed OIDC/SAML |
| Actor attribution | explicit actor strings in payloads/events | canonical `ActorIdentity` records |
| Role membership | trusted convention | scoped `ActorMembership` records |
| Leases | not required for one writer | first-party lease records with expiry/fencing |
| Backend | filesystem SourceConnector | SQLite transactional mutation backend, then Postgres/event store |
| Audit | Git plus local manifests | signed manifests and external timestamping |

## Service Modes

T1 default:

```bash
cognitive-firm-kernel-service
```

Registered-actor mode:

```bash
cognitive-firm-kernel-service --enforce-registered-actors
```

Membership-enforced mode:

```bash
cognitive-firm-kernel-service --enforce-registered-actors --enforce-actor-membership
```

In this mode, a request with `actor_context.role_id` must match an active
membership for the actor and requested tenant/project scope. Bootstrap
memberships through setup scripts, a service actor, or a temporary local
service config before enabling this mode.

Actor and membership administration routes require an identity-admin role in
strict service modes. By default, accepted admin roles are:

- `role.identity_admin`
- `role.owner`
- `role.principal`

This prevents an ordinary registered actor from granting roles or registering
new actors by omitting role context.

Subject-scope mode:

```bash
export COGNITIVE_FIRM_KERNEL_TOKEN=...
export COGNITIVE_FIRM_KERNEL_ACTOR_ID=human.alice
export COGNITIVE_FIRM_KERNEL_ACTOR_KIND=human
export COGNITIVE_FIRM_KERNEL_ROLES_ALLOWED=role.manager,role.reviewer
export COGNITIVE_FIRM_KERNEL_TENANT_IDS=tenant-a
cognitive-firm-kernel-service --require-token --enforce-subject-scope
```

When enabled, authenticated subject role and tenant claims must match the
request `actor_context`. For local bearer-token mode, the scope claims come
from the environment variables above. For production, an identity-provider
adapter should supply the same fields from OIDC, SAML, mTLS, or a trusted
gateway. This is the lean multi-authority isolation guard: the IdP
authenticates the subject, and the kernel rejects cross-role or cross-tenant
mutations before primitive code runs.

Lease-required mode:

```bash
cognitive-firm-kernel-service --enforce-registered-actors --require-leases
```

SQLite fenced-mutation mode:

```bash
cognitive-firm-kernel-service --mutation-backend sqlite --mutation-db cognitive_firm_workspace/kernel_mutations.sqlite3
```

In this mode, `GET /kernel/leases`, `POST /kernel/leases`, and
`POST /kernel/leases/{lease_id}/release` use the configured SQLite mutation
backend instead of the T1 JSONL lease file. `GET /kernel/leases` is a read-only
inspection surface over active, expired, or released claims; callers can filter
by `resource_ref`, `state`, or ask for the generic resource projection with
`resource=true`.
`/kernel/mutation-events` appends an event only when the supplied
`resource_ref`, `lease_id`, actor, and `fencing_token` match an active lease in
the same SQLite transaction. This is the public kernel's lean T2 mutation path.
Primitive-specific routes verify required leases against the configured SQLite
backend, so a SQLite lease does not silently authorize against the JSONL lease
log. Existing JSONL-backed primitive writes can migrate onto fully
transactional mutation events incrementally.
Terminal userland write commands that call primitive-specific routes expose the
same evidence fields as `--lease-id` and `--fencing-token`; read-only
projection commands never require leases. The terminal helpers
`lease-acquire`, `leases`, and `lease-release` expose the same acquire, inspect,
and release loop without adding a scheduler or workflow engine above the
kernel.

Local bearer-token mode:

```bash
export COGNITIVE_FIRM_KERNEL_TOKEN=...
export COGNITIVE_FIRM_KERNEL_ACTOR_ID=human.alice
export COGNITIVE_FIRM_KERNEL_ACTOR_KIND=human
cognitive-firm-kernel-service --require-token
```

The modes are additive. This lets a startup begin with a local service and move
toward multi-operator controls without changing primitive semantics.

## App Surface Writes

Orbit and the Telegram push channel are service clients. Their mutation
endpoints call these kernel routes and then refresh their projections. They do
not own gate resolution, directive/control files, chat appends, human-work
state, or role utilization config.

For local development:

```bash
cognitive-firm-kernel-service --host 127.0.0.1 --port 8765
ORBIT_SURFACE_MODE=kernel_intents COGNITIVE_FIRM_KERNEL_SERVICE_URL=http://127.0.0.1:8765 npm run dev
```

## Verification

```bash
make kernel-service-smoke
make app-integration-conformance
make smoke-public
```

`kernel-service-smoke` exercises the service dispatch path, SQLite lease
acquire, guarded event append, and stale fencing rejection. The app integration
conformance smoke exercises the deterministic Linear MCP projection shape and
signed inbound-event retry/idempotency behavior without requiring network
credentials.
