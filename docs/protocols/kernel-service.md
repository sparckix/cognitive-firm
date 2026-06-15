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
GET  /kernel/governance-changes
GET  /kernel/governance-changes/{proposal_id}
POST /kernel/governance-changes
POST /kernel/governance-changes/{proposal_id}/decision
POST /kernel/governance-changes/{proposal_id}/outcome-link
POST /kernel/actors
POST /kernel/memberships
POST /kernel/memberships/{assignment_id}/revoke
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
POST /kernel/human-work
POST /kernel/human-work/{session_id}/state
POST /kernel/human-work/{session_id}/interaction
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

Accountability routes:

- `POST /kernel/accountability-cases` writes the normal accountability case
  record.
- `POST /kernel/accountability-cases/from-damage-signal` takes a damage-signal
  object plus accountable role and authority-envelope refs, shapes the signal
  into a normal accountability-case request, and writes the same canonical
  case row. It does not clear the damage signal, decide remediation, mutate
  routing, or close the case.

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

In this mode, `/kernel/leases` and `/kernel/leases/{lease_id}/release` use the
configured SQLite mutation backend instead of the T1 JSONL lease file.
`/kernel/mutation-events` appends an event only when the supplied
`resource_ref`, `lease_id`, actor, and `fencing_token` match an active lease in
the same SQLite transaction. This is the public kernel's lean T2 mutation path.
Primitive-specific routes verify required leases against the configured SQLite
backend, so a SQLite lease does not silently authorize against the JSONL lease
log. Existing JSONL-backed primitive writes can migrate onto fully
transactional mutation events incrementally.

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
