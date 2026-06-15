import pytest

from cognitive_firm.orchestration.execution_routing import (
    infer_execution_route,
    render_route_contract,
)


def test_explicit_frontmatter_route_wins():
    route = infer_execution_route(
        frontmatter={"execution_route": "scripted_run"},
        body="ordinary docs work",
    )

    assert route.route == "scripted_run"
    assert route.confidence == "frontmatter"
    assert route.gpu_allowed is True
    assert route.required_first_artifact == "workspace/run_packet.md"


def test_unknown_frontmatter_route_fails_closed():
    with pytest.raises(ValueError, match="unknown execution route"):
        infer_execution_route(frontmatter={"execution_route": "invented_route"})


def test_research_director_role_has_no_special_public_default():
    route = infer_execution_route(
        role_id="research_director",
        body="Please inspect this ordinary work item.",
    )

    assert route.route == "direct_work"
    assert route.confidence == "low"


def test_compatibility_alias_maps_to_generic_joint_work_route():
    route = infer_execution_route(frontmatter={"route_hint": "rd_live"})

    assert route.route == "joint_work"
    assert route.required_first_artifact == "workspace/human_work_session.md"


def test_experiment_loop_detects_candidate_search_without_granting_authority():
    route = infer_execution_route(
        body="Run an A/B test with many candidates for the routing policy.",
    )

    assert route.route == "experiment_loop"
    assert route.experiment_loop_allowed is True
    assert route.live_api_allowed is False
    assert route.gpu_allowed is False
    assert route.required_first_artifact == "workspace/preflight_substrate_audit.md"


def test_artifact_build_detects_reusable_contract_work():
    route = infer_execution_route(
        body="Build a reusable schema and contract for the adapter handoff.",
    )

    assert route.route == "artifact_build"
    assert route.artifact_build_allowed is True
    assert route.substrate_build_allowed is True
    assert route.required_first_artifact == "workspace/artifact_build_spec.md"


def test_synthesis_review_detects_architecture_review():
    route = infer_execution_route(
        body="Do an architecture review and compare approaches before coding.",
    )

    assert route.route == "synthesis_review"
    assert "synthesis" in route.rationale.lower() or "architectural" in route.rationale.lower()


def test_rendered_contract_exposes_route_and_override_rule():
    route = infer_execution_route(frontmatter={"recommended_route": "expert_review"})
    rendered = render_route_contract(route)

    assert "EXECUTION ROUTE CONTRACT" in rendered
    assert "- route: expert_review" in rendered
    assert "- live_api_allowed: true" in rendered
    assert "do not silently switch modes" in rendered
