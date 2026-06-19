# scripts

This directory is the executable surface around the kernel. Files here should be
thin entrypoints: demos, smoke harnesses, migrations, operator workflows, and
small CLIs that compose importable behavior from `src/cognitive_firm/`.

Do not put reusable authority rules, durable state transitions, invariants,
schemas, adapters, projections, or service-route logic here. If a script starts
owning behavior that another program should rely on, move that behavior into
`src/cognitive_firm/` with tests and leave this directory as the invocation
layer.

Scripts may own:

- command-line parsing and printing;
- temporary fixture setup;
- demo sequencing;
- local operator glue;
- smoke-test assertions over public commands.

Scripts should call the kernel, not become a second kernel.

<!-- AUTO-INDEX:START (managed by scripts/gen_folder_index.py — edit prose OUTSIDE this block) -->

## Index

**Sub-folders**

- None

**Documents**

- [a2a_delegation_command_conformance.py](a2a_delegation_command_conformance.py)
- [a2a_h2a_command_conformance.py](a2a_h2a_command_conformance.py)
- [a2h_command_conformance.py](a2h_command_conformance.py)
- [adoption_onramp_packet.py](adoption_onramp_packet.py)
- [adoption_onramp_replay.py](adoption_onramp_replay.py)
- [adoption_readiness_packet.py](adoption_readiness_packet.py)
- [agent_daemon.py](agent_daemon.py)
- [agent_fleet_audit_demo.py](agent_fleet_audit_demo.py)
- [app_integration_conformance.py](app_integration_conformance.py)
- [app_service_integration_smoke.py](app_service_integration_smoke.py)
- [backup_restore_smoke.py](backup_restore_smoke.py)
- [decision_log_replay_demo.py](decision_log_replay_demo.py)
- [docker_smoke.sh](docker_smoke.sh)
- [docs_surface_check.py](docs_surface_check.py)
- [field_pilot_action_impact_compile.py](field_pilot_action_impact_compile.py)
- [field_pilot_action_impact_demo.py](field_pilot_action_impact_demo.py)
- [field_pilot_operator_burden_compile.py](field_pilot_operator_burden_compile.py)
- [field_pilot_scaffold.py](field_pilot_scaffold.py)
- [field_pilot_validate.py](field_pilot_validate.py)
- [field_pilot_validate_smoke.py](field_pilot_validate_smoke.py)
- [formal_provider_bundle_demo.py](formal_provider_bundle_demo.py)
- [formal_provider_proof_pack.py](formal_provider_proof_pack.py)
- [gen_folder_index.py](gen_folder_index.py)
- [governance_failure_benchmark.py](governance_failure_benchmark.py)
- [kernel_conformance_smoke.py](kernel_conformance_smoke.py)
- [kernel_service_smoke.py](kernel_service_smoke.py)
- [langgraph_adapter_policy_preview.py](langgraph_adapter_policy_preview.py)
- [langgraph_governance_demo.py](langgraph_governance_demo.py)
- [learning_loop_walkthrough.py](learning_loop_walkthrough.py)
- [mcp_linear_live_smoke.py](mcp_linear_live_smoke.py)
- [multi_actor_authority_walkthrough.py](multi_actor_authority_walkthrough.py)
- [native_e2e_demo.py](native_e2e_demo.py)
- [operator_console.sh](operator_console.sh)
- [org_role_preflight.py](org_role_preflight.py)
- [package_smoke.py](package_smoke.py)
- [public_claims_check.py](public_claims_check.py)
- [rd_tick_brief.py](rd_tick_brief.py)
- [release_diff_audit.py](release_diff_audit.py)
- [release_hygiene_check.py](release_hygiene_check.py)
- [runtime_adapter_proof_pack.py](runtime_adapter_proof_pack.py)
- [runtime_adapter_smoke.py](runtime_adapter_smoke.py)
- [runtime_interrupt_command_conformance.py](runtime_interrupt_command_conformance.py)
- [saga_command_conformance.py](saga_command_conformance.py)
- [setup_vps.sh](setup_vps.sh)
- [source_coverage_walkthrough.py](source_coverage_walkthrough.py)
- [telegram_setup.py](telegram_setup.py)

<sub>0 sub-folder(s), 46 document(s). Auto-generated; re-run `scripts/gen_folder_index.py` after adding files.</sub>

<!-- AUTO-INDEX:END -->
