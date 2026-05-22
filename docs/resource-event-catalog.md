# Resource And Event Catalog

This catalog is the adopter-facing object model. It summarizes the durable
surfaces in the kernel without requiring a reader to open every protocol file.
The implementation source is `src/cognitive_firm/orchestration/state_surface_inventory.py`.

## Core State Surfaces

| Resource | Class | Kind | Writer | Reader | Protocol |
|---|---|---|---|---|---|
| `actor_identity` | canonical state | JSONL | `register_actor_identity` | kernel service, audit/accountability | `docs/protocols/actor-identity.md` |
| `actor_membership` | canonical state | JSONL | `grant_actor_membership`, `revoke_actor_membership` | kernel service, actor context | `docs/protocols/actor-membership.md` |
| `leases` | canonical state | JSONL | `acquire_lease`, `release_lease` | kernel service mutation boundary | `docs/protocols/leases.md` |
| `policy_decisions` | canonical state | JSONL | `evaluate_policy`, `append_policy_decision` | audit review | `docs/protocols/policy-decisions.md` |
| `human_work` | canonical state | JSONL | `create_human_work_session`, `update_human_work_state` | A2H, work discovery, org surface | `docs/protocols/a2h.md` |
| `evidence_gaps` | canonical state | JSONL | `create_evidence_gap`, status updates | work discovery, org surface | `docs/protocols/project-charter.md` |
| `action_attestation` | canonical state | JSONL | `create_action_attestation` | review queues, audit surfaces | `docs/protocols/action-attestation.md` |
| `accountability_cases` | canonical state | JSONL | `create_accountability_case`, status updates | review queues, org surface | `docs/protocols/accountability-cases.md` |
| `governance_changes` | canonical state | JSONL | `propose_governance_change` | review queues, org surface | `docs/protocols/governance-changes.md` |
| `learning_events` | canonical state | JSONL | `create_learning_event`, candidate promotion | review queues, org surface | `docs/protocols/learning-events.md` |
| `learning_event_encounters` | telemetry | JSONL | `record_learning_event_encounter` | work discovery, learning replay audits | `docs/protocols/learning-events.md` |
| `operating_units` | canonical state | JSONL | `define_operating_unit`, `set_operating_unit_status` | work items, operating-unit dashboard | `docs/protocols/work-items.md` |
| `work_items` | canonical state | JSONL | `enqueue_work_item`, `claim_work_item`, `complete_work_item`, `fail_work_item` | operating-unit dashboard, kernel event stream | `docs/protocols/work-items.md` |
| `outcome_links` | canonical state | JSONL | `create_outcome_link`, `record_metric_snapshot`, `record_verdict` | outcome-link summary, routine reviews, org surface | `docs/protocols/outcome-links.md` |
| `routine_reviews` | canonical state | JSONL | `schedule_routine_review`, `record_review_outcome`, `retire_routine` | due-review surface, review queues, org surface | `docs/protocols/routine-reviews.md` |
| `resource_allocation` | canonical state | JSONL | `record_allocation_decision`, `apply_allocation_decision`, `revert_allocation_decision` | allocation ledger, operating-unit dashboard, audit review | `docs/protocols/resource-allocation.md` |
| `residual_right_assignments` | canonical state | JSONL | `assign_residual_right` | residual-rights holder lookup, decision-rights summary | `docs/protocols/decision-rights.md` |
| `residual_decisions` | canonical state | JSONL | `record_residual_decision`, `review_residual_decision` | decision-rights summary, governance review | `docs/protocols/decision-rights.md` |

## Event And Projection Surfaces

| Surface | Class | Kind | Purpose | Protocol |
|---|---|---|---|---|
| `transition_log` | canonical state | event stream | legacy local outbox and run-transition stream | `docs/protocols/run-checkpoints.md` |
| `kernel_events` | canonical state | event stream | canonical envelope embedded in the transition stream | `docs/protocols/kernel-events.md` |
| `state_backends` | canonical state | event stream interface | filesystem and SQLite event-source adapters | `docs/protocols/state-backends.md` |
| `runtime_adapters` | projection | projection | external runtime lifecycle into run checkpoints | `docs/protocols/runtime-adapters.md` |
| `inbound_events` | canonical state | JSONL | verified external observations, quarantine, replay window, dead letters | `docs/protocols/inbound-events.md` |
| `mcp_outbox` | canonical state | event stream | capability-gated enterprise-system calls | `docs/protocols/mcp.md` |
| `distribution_events` | canonical state | event stream | typed install/upgrade/rollback events (`package.installed`, `package.rolled_back`) under the target's `.cognitive-firm/distribution-events.jsonl` | `docs/protocols/distribution.md` |
| `org_surface` | read model | projection | human and role-facing health/read model | `docs/PROTOCOLS.md` |
| `strategy_office` | read model | projection | observer-only findings from org-surface state | `docs/protocols/strategy-office.md` |
| `learning_transition_compiler` | read model | projection | proposed learning candidates | `docs/protocols/learning-transition-compiler.md` |
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
