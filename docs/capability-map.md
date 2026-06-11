# Capability Map

This map is rendered from `state_surface_inventory.py`. It groups kernel
surfaces by the organizational problem they address. It is a map of
implemented and tested interfaces, not a list of product promises.

## Authority and access

| Surface | Class | Kind | Writer | Tests |
|---|---|---|---|---|
| `actor_identity` | canonical state | jsonl + resource projection | `register_actor_identity` | tests/test_actor_identity.py, tests/test_kernel_service.py |
| `actor_membership` | canonical state | jsonl + resource projection | `grant_actor_membership / revoke_actor_membership` | tests/test_actor_membership.py, tests/test_kernel_service.py |
| `authority_domains` | canonical state | json + resource projection | `authority-domain file authoring / distro overlays` | tests/test_authority_domains.py, tests/test_attention_router.py, tests/test_kernel_service_userland.py |
| `leases` | canonical state | jsonl + resource projection | `acquire_lease / release_lease` | tests/test_leases.py, tests/test_kernel_service.py |
| `policy_decisions` | canonical state | jsonl + resource projection | `evaluate_policy / append_policy_decision` | tests/test_policy_decisions.py |
| `residual_right_assignments` | canonical state | jsonl + resource projection | `assign_residual_right` | tests/test_decision_rights.py |
| `residual_decisions` | canonical state | jsonl + resource projection | `record_residual_decision / review_residual_decision` | tests/test_decision_rights.py |
| `mcp_outbox` | canonical state | event stream | `append_transition and outbox relay` | tests/test_mcp_outbox_relay.py, tests/test_mcp_capabilities.py |

## Human-agent work

| Surface | Class | Kind | Writer | Tests |
|---|---|---|---|---|
| `human_work` | canonical state | jsonl + resource projection | `create_human_work_session / create_agent_requested_human_work_session / update_human_work_state / append_human_work_receipt` | tests/test_human_work.py, tests/test_org_surface.py |
| `work_items` | canonical state | jsonl + resource projection | `enqueue_work_item / claim_work_item / complete_work_item / fail_work_item` | tests/test_work_items.py |
| `operating_units` | canonical state | jsonl + resource projection | `define_operating_unit / set_operating_unit_status` | tests/test_operating_units.py |
| `operating_unit_surface` | read model | projection | `none` | tests/test_operating_unit_surface.py |
| `notifications` | projection | projection | `send_notification / push_notification` | tests/test_notification_channels.py |

## Runtime projection

| Surface | Class | Kind | Writer | Tests |
|---|---|---|---|---|
| `transition_log` | canonical state | event stream | `append_transition` | tests/test_run_checkpoints.py, tests/test_mcp_outbox_relay.py |
| `kernel_events` | canonical state | event stream | `record_kernel_event / append_kernel_event` | tests/test_kernel_events.py |
| `run_checkpoints` | read model | projection | `start_run / append_checkpoint / set_run_state` | tests/test_run_checkpoints.py |
| `runtime_adapters` | projection | projection | `record_runtime_event` | tests/test_runtime_adapters.py, tests/test_run_checkpoints.py |
| `otel_export` | projection | projection | `write_otel_projection` | tests/test_otel_export.py |
| `state_backends` | canonical state | event stream | `FilesystemStateBackend.append_event / SqliteEventSource.append_event` | tests/test_state_backends.py |

## Evidence and audit

| Surface | Class | Kind | Writer | Tests |
|---|---|---|---|---|
| `evidence_gaps` | canonical state | jsonl + resource projection | `create_evidence_gap / update_evidence_gap_status` | tests/test_evidence_gaps.py, tests/test_org_surface.py |
| `action_attestation` | canonical state | jsonl + resource projection | `create_action_attestation` | tests/test_action_attestation.py |
| `formal_verification` | canonical state | jsonl | `create_formal_verification` | tests/test_formal_verification.py, tests/test_governed_run_attestation_bundle.py |
| `audit_integrity` | canonical state | artifact | `create_audit_manifest_for_file` | tests/test_audit_integrity.py |
| `governed_run_attestation` | projection | artifact | `build_governed_run_attestation_bundle` | tests/test_governed_run_attestation_bundle.py |
| `accountability_cases` | canonical state | jsonl + resource projection | `create_accountability_case / update_accountability_case_status` | tests/test_accountability_cases.py |
| `accountability` | read model | projection | `none` | tests/test_accountability.py |
| `resource_envelope` | projection | projection | `none` | tests/test_resource_envelope.py |

## Learning and change

| Surface | Class | Kind | Writer | Tests |
|---|---|---|---|---|
| `strategy_office` | read model | projection | `none` | tests/test_strategy_office.py |
| `learning_transition_compiler` | read model | projection | `none` | tests/test_learning_transition_compiler.py |
| `learning_events` | canonical state | jsonl + resource projection | `create_learning_event / create_compounded_learning_event / learning_event_from_candidate` | tests/test_learning_events.py |
| `learning_event_encounters` | telemetry | jsonl | `record_learning_event_encounter` | tests/test_learning_events.py, tests/test_work_discovery_learning_carriers.py |
| `governance_changes` | canonical state | jsonl + resource projection | `propose_governance_change` | tests/test_governance_changes.py, tests/test_org_surface.py |
| `outcome_links` | canonical state | jsonl + resource projection | `create_outcome_link / record_metric_snapshot / record_verdict / void_outcome_link` | tests/test_outcome_links.py |
| `routine_reviews` | canonical state | jsonl + resource projection | `schedule_routine_review / start_routine_review / record_review_outcome / retire_routine` | tests/test_routine_reviews.py |
| `resource_allocation` | canonical state | jsonl | `record_allocation_decision / apply_allocation_decision / revert_allocation_decision` | tests/test_resource_allocation.py |
| `business_function_bandit` | projection | projection | `propose_business_function_policy` | tests/test_business_function_bandit.py, tests/test_decision_log_replay_demo.py |

## External and tenant inputs

| Surface | Class | Kind | Writer | Tests |
|---|---|---|---|---|
| `inbound_events` | canonical state | jsonl | `ingest_inbound_event` | tests/test_inbound_events.py |
| `forecast_market` | tenant owned ledger | summary read model | `tenant forecast market` | tests/test_forecast_market_interface.py |
| `action_impact` | tenant owned ledger | summary read model | `tenant action-impact ledger` | tests/test_action_impact_interface.py |
| `intelligence_sources` | read model | projection | `none` | tests/test_intelligence_sources.py, tests/test_org_surface.py |

## Support and compatibility

| Surface | Class | Kind | Writer | Tests |
|---|---|---|---|---|
| `migrations` | canonical state | jsonl | `record_migration` | tests/test_migrations.py |
| `org_surface` | read model | projection | `none` | tests/test_org_surface.py |
