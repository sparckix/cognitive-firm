# Resource And Event Catalog

This catalog is the adopter-facing object model. It summarizes the durable
surfaces in the kernel without requiring a reader to open every protocol file.
The implementation source is `src/cognitive_firm/orchestration/state_surface_inventory.py`.

## Core State Surfaces

| Resource | Class | Kind | Writer | Reader | Protocol |
|---|---|---|---|---|---|
| `actor_identity` | canonical state | JSONL + resource projection | `register_actor_identity` | kernel service, audit/accountability, `actor_identity_resource` | `docs/protocols/actor-identity.md` |
| `actor_membership` | canonical state | JSONL + resource projection | `grant_actor_membership`, `revoke_actor_membership` | kernel service, actor context, `actor_membership_resource` | `docs/protocols/actor-membership.md` |
| `authority_domains` | canonical state | JSON + resource projection | authority-domain file authoring, distro overlays | attention routing, kernel service, `authority_domain_resource` | `docs/protocols/authority-domains.md` |
| `leases` | canonical state | JSONL + resource projection | `acquire_lease`, `release_lease` | kernel service mutation boundary, `lease_resource` | `docs/protocols/leases.md` |
| `policy_decisions` | canonical state | JSONL + resource projection | `evaluate_policy`, `append_policy_decision` | audit review, `policy_decision_resource` | `docs/protocols/policy-decisions.md` |
| `decision_aggregation_cases` | canonical state | JSONL + resource projection | `open_decision_aggregation_case`, `open_decision_aggregation_case_from_profile`, `record_decision_position`, `compute_decision_aggregation_case` | governance review, `decision_aggregation_case_resource` | `docs/protocols/decision-aggregation.md` |
| `human_work` | canonical state | JSONL + resource projection | `create_human_work_session`, `update_human_work_state`, `append_human_work_receipt` | A2H, structured receipts, work discovery, org surface, `human_work_resource` | `docs/protocols/a2h.md` |
| `evidence_gaps` | canonical state | JSONL + resource projection | `create_evidence_gap`, status updates | work discovery, org surface, `evidence_gap_resource` | `docs/protocols/project-charter.md` |
| `action_attestation` | canonical state | JSONL + resource projection | `create_action_attestation` | review queues, audit surfaces, governed-run bundle, agent-invocation audit read model, `action_attestation_resource` | `docs/protocols/action-attestation.md` |
| `formal_verification` | canonical state | JSONL | `create_formal_verification` | governed-run bundle, audit review | `docs/protocols/formal-verification.md` |
| `accountability_cases` | canonical state | JSONL + resource projection | `create_accountability_case`, status updates | review queues, org surface, `accountability_case_resource` | `docs/protocols/accountability-cases.md` |
| `governance_changes` | canonical state | JSONL + resource projection | `propose_governance_change` | invariant/evidence sufficiency gate, review queues, org surface, `governance_change_resource` | `docs/protocols/governance-changes.md` |
| `learning_events` | canonical state | JSONL + resource projection | `create_learning_event`, `create_compounded_learning_event`, candidate promotion | review queues, org surface, `learning_event_resource`, `summarize_learning_events` | `docs/protocols/learning-events.md` |
| `learning_event_encounters` | telemetry | JSONL | `record_learning_event_encounter` | work discovery, learning replay audits | `docs/protocols/learning-events.md` |
| `operating_units` | canonical state | JSONL + resource projection | `define_operating_unit`, `set_operating_unit_status` | work items, operating-unit dashboard, `operating_unit_resource` | `docs/protocols/work-items.md` |
| `work_items` | canonical state | JSONL + resource projection | `enqueue_work_item`, `claim_work_item`, `complete_work_item`, `fail_work_item` | operating-unit dashboard, kernel event stream, `work_item_resource` | `docs/protocols/work-items.md` |
| `outcome_links` | canonical state | JSONL + resource projection | `create_outcome_link`, `record_metric_snapshot`, `record_verdict` | outcome-link summary, routine reviews, org surface, `outcome_link_resource` | `docs/protocols/outcome-links.md` |
| `routine_reviews` | canonical state | JSONL + resource projection | `schedule_routine_review`, `record_review_outcome`, `retire_routine` | due-review surface, review queues, org surface, `routine_review_resource` | `docs/protocols/routine-reviews.md` |
| `resource_allocation` | canonical state | JSONL | `record_allocation_decision`, `apply_allocation_decision`, `revert_allocation_decision` | allocation ledger, operating-unit dashboard, audit review | `docs/protocols/resource-allocation.md` |
| `residual_right_assignments` | canonical state | JSONL + resource projection | `assign_residual_right` | residual-rights holder lookup, authority-domain holder resolution, decision-rights summary, `residual_right_assignment_resource` | `docs/protocols/decision-rights.md` |
| `residual_decisions` | canonical state | JSONL + resource projection | `record_residual_decision`, `review_residual_decision` | decision-rights summary, governance review, `residual_decision_resource` | `docs/protocols/decision-rights.md` |

## Event And Projection Surfaces

| Surface | Class | Kind | Purpose | Protocol |
|---|---|---|---|---|
| `transition_log` | canonical state | event stream | legacy local outbox and run-transition stream | `docs/protocols/run-checkpoints.md` |
| `run_checkpoints` | read model | projection | run lifecycle interface over `run.*` transition rows | `docs/protocols/run-checkpoints.md` |
| `kernel_events` | canonical state | event stream | canonical envelope embedded in the transition stream | `docs/protocols/kernel-events.md` |
| `state_backends` | canonical state | event stream interface | filesystem and SQLite event-source adapters | `docs/protocols/state-backends.md` |
| `runtime_adapters` | projection | projection | external runtime lifecycle into run checkpoints | `docs/protocols/runtime-adapters.md` |
| `multi_agent_trace_attribution` | telemetry | JSONL + resource projection | runtime-owned multi-agent trace evidence, delegation diagnostics, and failure-attribution carriers | `docs/protocols/multi-agent-trace-attribution.md` |
| `phase_execution` | telemetry | JSONL + resource projection | Strategy -> Execution -> Verification directives, verifier feedback, bounded retry budget decay, and observer-only learning candidates from blocked plans | `docs/protocols/phase-execution.md` |
| `protocol_experiments` | telemetry | JSONL + resource projection | bounded coordination-pattern comparisons, observer-only route-policy candidates, and learning-candidate projection for review-ready reports | `docs/protocols/protocol-experiments.md` |
| `capability_signals` | telemetry | JSONL + resource projection | typed abstention, authority-gap, evidence-gap, and capability-gap routing evidence | `docs/protocols/capability-signals.md` |
| `governed_run_attestation` | projection | artifact + schema | portable export over one run's checkpoints, attestations, formal verifications, human work, outcomes, accountability, linked leases, governance approvals, observability refs, and authority snapshot; validated by `schemas/governed-run-attestation.v1.schema.json` | `docs/protocols/governed-run-attestation.md` |
| `governed_mutation_proof` | projection | artifact | compact ordered proof row for approved state mutation across run, work item, proposal, approval, mutation, attestation, learning, outcome, review, bundle, and git commit refs | `docs/protocols/mutation-proofs.md` |
| `inbound_events` | canonical state | JSONL | verified external observations, quarantine, replay window, dead letters | `docs/protocols/inbound-events.md` |
| `mcp_outbox` | canonical state | event stream | capability-gated enterprise-system calls | `docs/protocols/mcp.md` |
| `distribution_events` | canonical state | event stream | typed install/upgrade/rollback events (`package.installed`, `package.rolled_back`, `package.install_approved`) under the target's `.cognitive-firm/distribution-events.jsonl` | `docs/protocols/distribution.md` |
| `org_surface` | read model | projection | human and role-facing health/read model, including learning-unit summary counts and recent agent invocation audit rows | `docs/PROTOCOLS.md` |
| `strategy_office` | read model | projection | observer-only findings from org-surface state | `docs/protocols/strategy-office.md` |
| `learning_transition_compiler` | read model | projection | proposed learning candidates | `docs/protocols/learning-transition-compiler.md` |
| `business_function_bandit` | projection | projection | conservative context-to-arm candidate proposer over action-impact rows; writes no live policy | `docs/protocols/action-impact.md` |
| `accountability` | read model | projection | joined accountability summary | `docs/protocols/accountability.md` |
| `operating_unit_surface` | read model | projection | production health per operating unit: backlog, claimed, p95, throughput, blockers | `docs/protocols/work-items.md` |
| `intelligence_sources` | read model | projection | source coverage and repair candidates | `docs/protocols/intelligence-sources.md` |

## Tenant-Owned Read Models

| Surface | Class | Kernel expectation | Tenant owns |
|---|---|---|---|
| `forecast_market` | tenant-owned ledger | health/read model consumed by org surface and strategy office | contracts, scoring, calibration, routing policy |
| `action_impact` | tenant-owned ledger | summary read model consumed by org surface and accountability | metric definitions, causal model, optimizer policy |
| `notifications` | projection | delivery intent/projection | provider account, credentials, delivery routing |
| `identity_providers` | projection | authenticated subject facts | IdP configuration, groups, lifecycle administration |

## Support And Compatibility Surfaces

| Surface | Class | Kind | Purpose | Protocol |
|---|---|---|---|---|
| `resource_envelope` | projection | projection | compatibility shape for typed resources | `docs/protocols/resource-envelope.md` |
| `otel_export` | projection | projection | observability export derived from kernel events/run checkpoints | `docs/protocols/otel-export.md` |
| `migrations` | canonical state | JSONL | dry-run-first migration records | `docs/protocols/migrations.md` |
| `audit_integrity` | canonical state | artifact | tamper-evident manifests over JSONL logs | `docs/protocols/audit-integrity.md` |
| `notifications` | projection | projection | delivery intent to attention providers | `docs/protocols/h2a.md` |

## Source-Of-Truth Rule

The code inventory uses the same classes:

- `canonical_state`: durable kernel-owned fact or event stream;
- `read_model`: derived view rebuilt from canonical state or summaries;
- `projection`: UI/provider/runtime rendering or adapter event;
- `telemetry`: optional measurement rows that can be dropped without changing decisions;
- `tenant_owned_ledger`: domain-specific source owned by an overlay.

Only canonical state owns facts. Read models, projections, and telemetry can be
deleted and rebuilt. Tenant-owned ledgers can influence the org surface only
through their generic summary contracts.

Resource envelopes also carry a `stability` label:

- `alpha` for settling shapes;
- `beta` for shapes expected to hold under normal adapter use;
- `stable` for supported public contracts.

## Event Naming Guidance

Use event verbs that state what happened, not what code path ran.

Good:

- `run.started`
- `run.checkpointed`
- `external.issue.updated`
- `human_work.receipt_submitted`
- `learning_event.approved`
- `package.installed`
- `package.rolled_back`
- `package.install_approved`

Avoid:

- `handler_called`
- `callback_done`
- `agent_response`
- `thing_updated`

## When To Add A New Surface

Add a new state surface only when existing surfaces cannot answer:

1. who can write the record;
2. who reads it;
3. what durable obligation or learning transition it creates;
4. how it is tested;
5. whether it is kernel-owned or tenant-owned.

If those answers are tenant-specific, add a tenant adapter or read model instead.
