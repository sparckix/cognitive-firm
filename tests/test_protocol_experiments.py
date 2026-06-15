from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.protocol_experiments import (  # noqa: E402
    build_protocol_experiment_report,
    get_protocol_experiment,
    learning_candidate_from_protocol_experiment_report,
    protocol_experiment_resource,
    record_protocol_observation,
    start_protocol_experiment,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


def test_protocol_experiment_reports_review_ready_candidate(tmp_path: Path):
    log = tmp_path / "protocol_experiments.jsonl"
    experiment = start_protocol_experiment(
        objective="choose a coordination pattern for evidence repairs",
        owner_role="role.org_evolver",
        candidate_protocols=["coordinator", "sequential", "batched_sequential"],
        baseline_protocol="coordinator",
        tenant_id="tenant_demo",
        project_id="project_demo",
        log_path=log,
    )

    for idx, quality in enumerate([0.62, 0.64], start=1):
        record_protocol_observation(
            experiment_id=experiment.experiment_id,
            protocol="coordinator",
            task_ref=f"work://baseline-{idx}",
            quality_score=quality,
            latency_units=4,
            cost_units=4,
            log_path=log,
        )
    for idx, quality in enumerate([0.71, 0.74], start=1):
        record_protocol_observation(
            experiment_id=experiment.experiment_id,
            protocol="sequential",
            task_ref=f"work://sequential-{idx}",
            quality_score=quality,
            latency_units=3,
            cost_units=3,
            log_path=log,
        )
    for idx, quality in enumerate([0.86, 0.88], start=1):
        record_protocol_observation(
            experiment_id=experiment.experiment_id,
            protocol="batched_sequential",
            task_ref=f"work://batched-{idx}",
            quality_score=quality,
            latency_units=2,
            cost_units=2,
            evidence_refs=[f"bundle://batched-{idx}"],
            log_path=log,
        )

    reported = build_protocol_experiment_report(
        experiment_id=experiment.experiment_id,
        proposed_by="role.org_evolver",
        target_ref="protocol://handoff-routing",
        min_quality_delta=0.05,
        log_path=log,
    )

    assert reported.status == "reported"
    report = reported.reports[0]
    assert report["status"] == "review_ready"
    assert report["recommended_protocol"] == "batched_sequential"
    assert report["observer_only"] is True
    assert report["governance_change_candidate"]["change_kind"] == "route_policy_change"
    assert report["governance_change_candidate"]["target_ref"] == "protocol://handoff-routing"
    assert report["protocol_summaries"]["batched_sequential"]["n"] == 2

    resource = protocol_experiment_resource(get_protocol_experiment(experiment.experiment_id, log_path=log)).as_dict()
    assert validate_resource(resource) == []
    assert resource["kind"] == "ProtocolExperiment"
    assert resource["status"]["reports"][0]["status"] == "review_ready"

    candidate = learning_candidate_from_protocol_experiment_report(reported, report)
    assert candidate.source_kind == "protocol_experiment_report"
    assert candidate.transition_kind == "route_policy_change"
    assert candidate.object_ref == "protocol://handoff-routing"
    assert f"protocol_experiment:{experiment.experiment_id}" in candidate.source_refs
    assert f"protocol_experiment_report:{report['report_id']}" in candidate.source_refs
    assert candidate.proposed_payload["recommended_protocol"] == "batched_sequential"
    assert candidate.proposed_payload["governance_change_candidate"]["change_kind"] == (
        "route_policy_change"
    )
    assert candidate.observer_only is True


def test_protocol_experiment_blocks_when_observations_are_insufficient(tmp_path: Path):
    log = tmp_path / "protocol_experiments.jsonl"
    experiment = start_protocol_experiment(
        objective="compare dispatch protocols",
        owner_role="role.evaluator",
        candidate_protocols=["coordinator", "sequential"],
        baseline_protocol="coordinator",
        log_path=log,
    )
    record_protocol_observation(
        experiment_id=experiment.experiment_id,
        protocol="coordinator",
        task_ref="work://baseline",
        quality_score=0.8,
        log_path=log,
    )

    reported = build_protocol_experiment_report(
        experiment_id=experiment.experiment_id,
        proposed_by="role.evaluator",
        target_ref="protocol://dispatch",
        min_observations_per_protocol=2,
        log_path=log,
    )

    assert reported.status == "blocked"
    report = reported.reports[0]
    assert report["status"] == "blocked"
    assert report["recommended_protocol"] is None
    assert report["governance_change_candidate"] == {}
    assert "coordinator has fewer than 2 observations" in report["review_blockers"]
    assert "sequential has fewer than 2 observations" in report["review_blockers"]
    try:
        learning_candidate_from_protocol_experiment_report(reported, report)
    except ValueError as exc:
        assert "not review_ready" in str(exc)
    else:
        raise AssertionError("expected blocked report to reject learning-candidate projection")


def test_protocol_experiment_blocks_on_guardrail_violations(tmp_path: Path):
    log = tmp_path / "protocol_experiments.jsonl"
    experiment = start_protocol_experiment(
        objective="compare risky routing protocols",
        owner_role="role.risk_guardian",
        candidate_protocols=["coordinator", "shared"],
        baseline_protocol="coordinator",
        log_path=log,
    )
    for protocol in ["coordinator", "shared"]:
        record_protocol_observation(
            experiment_id=experiment.experiment_id,
            protocol=protocol,
            task_ref=f"work://{protocol}-1",
            quality_score=0.7,
            guardrail_violations=1 if protocol == "shared" else 0,
            log_path=log,
        )

    reported = build_protocol_experiment_report(
        experiment_id=experiment.experiment_id,
        proposed_by="role.risk_guardian",
        target_ref="protocol://risky-routing",
        min_observations_per_protocol=1,
        max_guardrail_violations=0,
        log_path=log,
    )

    assert reported.status == "blocked"
    assert "guardrail violations exceed threshold" in reported.reports[0]["review_blockers"]


def test_protocol_experiment_validates_inputs(tmp_path: Path):
    log = tmp_path / "protocol_experiments.jsonl"
    experiment = start_protocol_experiment(
        objective="compare dispatch protocols",
        owner_role="role.evaluator",
        candidate_protocols=["coordinator"],
        baseline_protocol="coordinator",
        log_path=log,
    )

    try:
        record_protocol_observation(
            experiment_id=experiment.experiment_id,
            protocol="broadcast",
            task_ref="work://wrong",
            quality_score=0.5,
            log_path=log,
        )
    except ValueError as exc:
        assert "candidate_protocols" in str(exc)
    else:
        raise AssertionError("expected invalid protocol to fail")

    try:
        record_protocol_observation(
            experiment_id=experiment.experiment_id,
            protocol="coordinator",
            task_ref="work://bad-score",
            quality_score=1.2,
            log_path=log,
        )
    except ValueError as exc:
        assert "[0, 1]" in str(exc)
    else:
        raise AssertionError("expected invalid score to fail")
