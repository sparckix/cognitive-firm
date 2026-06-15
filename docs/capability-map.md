# Capability Map

This map is rendered from `state_surface_inventory.py`. It groups kernel
surfaces by the organizational problem they address. It is a map of
implemented and tested interfaces, not a list of product promises.

The `Boundary` column separates kernel governance/state, work substrate,
first-party execution helpers, runtime imports/projections, tenant-owned
inputs, and audit/proof surfaces. This keeps cognitive-firm from
becoming a workflow/BPM system or a replacement agent runtime while still
making the execution substrate visible.

## Authority and access

| Surface | Boundary | Class | Kind | Writer | Tests |
|---|---|---|---|---|---|
| `actor_identity` | kernel governance/state | canonical state | jsonl + resource projection | `register_actor_identity` | tests/test_actor_identity.py, tests/test_kernel_service.py |
| `actor_membership` | kernel governance/state | canonical state | jsonl + resource projection | `grant_actor_membership / revoke_actor_membership` | tests/test_actor_membership.py, tests/test_kernel_service.py |
| `authority_domains` | kernel governance/state | canonical state | json + resource projection | `authority-domain file authoring / distro overlays` | tests/test_authority_domains.py, tests/test_attention_router.py, tests/test_kernel_service_userland.py |
| `leases` | kernel governance/state | canonical state | jsonl + resource projection | `acquire_lease / release_lease` | tests/test_leases.py, tests/test_kernel_service.py |
| `policy_decisions` | kernel governance/state | canonical state | jsonl + resource projection | `evaluate_policy / append_policy_decision` | tests/test_policy_decisions.py |
| `decision_aggregation_cases` | kernel governance/state | canonical state | jsonl + resource projection | `open_decision_aggregation_case / open_decision_aggregation_case_from_profile / record_decision_position / compute_decision_aggregation_case` | tests/test_decision_aggregation.py, tests/test_kernel_service.py |
| `residual_right_assignments` | kernel governance/state | canonical state | jsonl + resource projection | `assign_residual_right` | tests/test_decision_rights.py |
| `residual_decisions` | kernel governance/state | canonical state | jsonl + resource projection | `record_residual_decision / review_residual_decision` | tests/test_decision_rights.py |
| `mcp_outbox` | kernel governance/state | canonical state | event stream | `append_transition and outbox relay` | tests/test_mcp_outbox_relay.py, tests/test_mcp_capabilities.py |

## Human-agent work

| Surface | Boundary | Class | Kind | Writer | Tests |
|---|---|---|---|---|---|
| `human_work` | work substrate | canonical state | jsonl + resource projection | `create_human_work_session / create_agent_requested_human_work_session / update_human_work_state / append_human_work_receipt` | tests/test_human_work.py, tests/test_org_surface.py |
| `work_items` | work substrate | canonical state | jsonl + resource projection | `enqueue_work_item / claim_work_item / complete_work_item / fail_work_item` | tests/test_work_items.py |
| `operating_units` | work substrate | canonical state | jsonl + resource projection | `define_operating_unit / set_operating_unit_status` | tests/test_operating_units.py |
| `operating_unit_surface` | work substrate | read model | projection | `none` | tests/test_operating_unit_surface.py |
| `notifications` | kernel governance/state | projection | projection | `send_notification / push_notification` | tests/test_notification_channels.py |

## Runtime projection

| Surface | Boundary | Class | Kind | Writer | Tests |
|---|---|---|---|---|---|
| `transition_log` | kernel governance/state | canonical state | event stream | `append_transition` | tests/test_run_checkpoints.py, tests/test_mcp_outbox_relay.py |
| `kernel_events` | kernel governance/state | canonical state | event stream | `record_kernel_event / append_kernel_event` | tests/test_kernel_events.py |
| `run_checkpoints` | runtime import/projection | read model | projection | `start_run / append_checkpoint / set_run_state` | tests/test_run_checkpoints.py |
| `runtime_adapters` | runtime import/projection | projection | projection | `record_runtime_event` | tests/test_runtime_adapters.py, tests/test_run_checkpoints.py |
| `multi_agent_trace_attribution` | runtime import/projection | telemetry | jsonl + resource projection | `record_trace_event / create_failure_attribution_packet` | tests/test_multi_agent_trace_attribution.py, tests/test_kernel_service.py |
| `phase_execution` | first-party execution helper | telemetry | jsonl + resource projection | `start_phase_execution_plan / record_phase_directive / record_verification_feedback / learning_candidate_from_phase_execution_plan` | tests/test_phase_execution.py, tests/test_phase_execution_demo.py, tests/test_kernel_service.py |
| `protocol_experiments` | first-party execution helper | telemetry | jsonl + resource projection | `start_protocol_experiment / record_protocol_observation / build_protocol_experiment_report / learning_candidate_from_protocol_experiment_report` | tests/test_protocol_experiments.py, tests/test_protocol_experiment_demo.py, tests/test_kernel_service.py |
| `capability_signals` | first-party execution helper | telemetry | jsonl + resource projection | `record_capability_signal / route_capability_signal / close_capability_signal` | tests/test_capability_signals.py, tests/test_capability_signal_demo.py, tests/test_kernel_service.py |
| `otel_export` | runtime import/projection | projection | projection | `write_otel_projection` | tests/test_otel_export.py |
| `state_backends` | kernel governance/state | canonical state | event stream | `FilesystemStateBackend.append_event / SqliteEventSource.append_event` | tests/test_state_backends.py |

## Evidence and audit

| Surface | Boundary | Class | Kind | Writer | Tests |
|---|---|---|---|---|---|
| `evidence_gaps` | audit/proof | canonical state | jsonl + resource projection | `create_evidence_gap / update_evidence_gap_status` | tests/test_evidence_gaps.py, tests/test_org_surface.py |
| `action_attestation` | audit/proof | canonical state | jsonl + resource projection | `create_action_attestation` | tests/test_action_attestation.py |
| `formal_verification` | audit/proof | canonical state | jsonl | `create_formal_verification` | tests/test_formal_verification.py, tests/test_governed_run_attestation_bundle.py |
| `audit_integrity` | audit/proof | canonical state | artifact | `create_audit_manifest_for_file` | tests/test_audit_integrity.py |
| `governed_run_attestation` | audit/proof | projection | artifact | `build_governed_run_attestation_bundle` | tests/test_governed_run_attestation_bundle.py |
| `accountability_cases` | audit/proof | canonical state | jsonl + resource projection | `create_accountability_case / update_accountability_case_status` | tests/test_accountability_cases.py |
| `accountability` | audit/proof | read model | projection | `none` | tests/test_accountability.py |
| `resource_envelope` | audit/proof | projection | projection | `none` | tests/test_resource_envelope.py |

## Learning and change

| Surface | Boundary | Class | Kind | Writer | Tests |
|---|---|---|---|---|---|
| `strategy_office` | kernel governance/state | read model | projection | `none` | tests/test_strategy_office.py |
| `learning_transition_compiler` | kernel governance/state | read model | projection | `none` | tests/test_learning_transition_compiler.py |
| `learning_events` | kernel governance/state | canonical state | jsonl + resource projection | `create_learning_event / create_compounded_learning_event / learning_event_from_candidate` | tests/test_learning_events.py |
| `learning_event_encounters` | kernel governance/state | telemetry | jsonl | `record_learning_event_encounter` | tests/test_learning_events.py, tests/test_work_discovery_learning_carriers.py |
| `governance_changes` | kernel governance/state | canonical state | jsonl + resource projection | `propose_governance_change / governance_change_from_candidate` | tests/test_governance_changes.py, tests/test_org_surface.py |
| `outcome_links` | audit/proof | canonical state | jsonl + resource projection | `create_outcome_link / record_metric_snapshot / record_verdict / void_outcome_link` | tests/test_outcome_links.py |
| `routine_reviews` | audit/proof | canonical state | jsonl + resource projection | `schedule_routine_review / start_routine_review / record_review_outcome / retire_routine` | tests/test_routine_reviews.py |
| `resource_allocation` | work substrate | canonical state | jsonl | `record_allocation_decision / apply_allocation_decision / revert_allocation_decision` | tests/test_resource_allocation.py |
| `business_function_bandit` | first-party execution helper | projection | projection | `propose_business_function_policy` | tests/test_business_function_bandit.py, tests/test_decision_log_replay_demo.py |

## External and tenant inputs

| Surface | Boundary | Class | Kind | Writer | Tests |
|---|---|---|---|---|---|
| `inbound_events` | kernel governance/state | canonical state | jsonl | `ingest_inbound_event` | tests/test_inbound_events.py |
| `forecast_market` | tenant-owned input | tenant owned ledger | summary read model | `tenant forecast market` | tests/test_forecast_market_interface.py |
| `action_impact` | tenant-owned input | tenant owned ledger | summary read model | `tenant action-impact ledger` | tests/test_action_impact_interface.py |
| `intelligence_sources` | kernel governance/state | read model | projection | `none` | tests/test_intelligence_sources.py, tests/test_org_surface.py |

## Support and compatibility

| Surface | Boundary | Class | Kind | Writer | Tests |
|---|---|---|---|---|---|
| `migrations` | kernel governance/state | canonical state | jsonl | `record_migration` | tests/test_migrations.py |
| `org_surface` | kernel governance/state | read model | projection | `none` | tests/test_org_surface.py |
