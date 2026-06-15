from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _tree(path: str) -> ast.Module:
    return ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)


def _imported_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}")
    return names


def _called_names(tree: ast.Module) -> set[str]:
    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            calls.add(func.id)
        elif isinstance(func, ast.Attribute):
            calls.add(func.attr)
    return calls


def _mutating_orchestration_imports(tree: ast.Module) -> set[str]:
    mutating_prefixes = (
        "append_",
        "close_",
        "create_",
        "fulfill_",
        "grant_",
        "issue_",
        "propose_",
        "record_",
        "route_",
        "start_",
        "update_",
    )
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if not node.module.startswith("cognitive_firm.orchestration"):
            continue
        for alias in node.names:
            if alias.name.startswith(mutating_prefixes):
                names.add(f"{node.module}.{alias.name}")
    return names


def test_governed_run_recipes_stay_request_builders_not_workflow_engine() -> None:
    """Recipes reduce adoption glue; they must not own execution or state."""

    tree = _tree("src/cognitive_firm/orchestration/governed_run_recipes.py")
    imports = _imported_names(tree)
    calls = _called_names(tree)

    forbidden_imports = {
        "cognitive_firm.kernel_service",
        "cognitive_firm.kernel_service.dispatch_kernel_request",
        "cognitive_firm.orchestration.governance_changes",
        "cognitive_firm.orchestration.learning_events",
        "cognitive_firm.orchestration.outcome_links",
        "cognitive_firm.orchestration.work_items",
    }
    assert imports.isdisjoint(forbidden_imports)

    forbidden_calls = {
        "dispatch_kernel_request",
        "record_kernel_event",
        "propose_governance_change",
        "create_outcome_link",
        "create_learning_event",
        "update_work_item_state",
        "open",
        "write_text",
        "read_text",
        "mkdir",
    }
    assert calls.isdisjoint(forbidden_calls)


def test_service_adoption_smokes_use_kernel_routes_not_primitive_mutators() -> None:
    """Adopter smokes should exercise the service boundary, not bypass it."""

    for path in (
        "scripts/agent_fleet_audit_demo.py",
        "scripts/app_service_integration_smoke.py",
        "scripts/formal_provider_bundle_demo.py",
        "scripts/kernel_service_smoke.py",
        "scripts/langgraph_governance_demo.py",
        "scripts/multi_actor_authority_walkthrough.py",
    ):
        assert _mutating_orchestration_imports(_tree(path)) == set()


def test_field_pilot_action_impact_demo_routes_durable_policy_rows_through_service() -> None:
    for path in (
        "scripts/field_pilot_action_impact_demo.py",
        "scripts/decision_log_replay_demo.py",
    ):
        tree = _tree(path)
        imports = _imported_names(tree)

        assert "cognitive_firm.kernel_service.dispatch_kernel_request" in imports
        assert "cognitive_firm.kernel_service.KernelServiceConfig" in imports
        assert imports.isdisjoint(
            {
                "cognitive_firm.orchestration.action_impact.append_policy_evaluation",
                "cognitive_firm.orchestration.action_impact.append_policy_promotion_packet",
                "cognitive_firm.orchestration.action_impact.build_policy_promotion_packet",
                "cognitive_firm.orchestration.action_impact.evaluate_offline_policy_candidate",
            }
        )
