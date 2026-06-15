from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.phase_execution import (  # noqa: E402
    get_phase_execution_plan,
    learning_candidate_from_phase_execution_plan,
    phase_execution_plan_resource,
    record_phase_directive,
    record_verification_feedback,
    start_phase_execution_plan,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


def test_phase_execution_records_directives_and_passed_verification(tmp_path: Path):
    log = tmp_path / "phase_execution.jsonl"
    plan = start_phase_execution_plan(
        objective="draft and verify a protocol update",
        owner_role="role.org_evolver",
        total_budget_units=8,
        max_attempts=2,
        run_id="run_demo",
        work_id="work_demo",
        log_path=log,
    )

    plan = record_phase_directive(
        plan_id=plan.plan_id,
        phase="strategy",
        issued_by="role.org_evolver",
        directive="Compare current handoff protocol against missing-source failures.",
        evidence_refs=["trace://run-demo"],
        budget_units=2,
        log_path=log,
    )
    assert plan.current_phase == "strategy"
    assert plan.directives[0]["phase"] == "strategy"

    plan = record_phase_directive(
        plan_id=plan.plan_id,
        phase="execution",
        issued_by="role.executor",
        directive="Draft a source-ref requirement for evaluator handoffs.",
        output_refs=["artifact://handoff-source-ref-draft"],
        budget_units=3,
        log_path=log,
    )
    assert plan.current_phase == "execution"

    plan = record_verification_feedback(
        plan_id=plan.plan_id,
        verifier_role="role.evaluator",
        verdict="passed",
        rationale="Draft includes before/after behavior and rollback path.",
        evidence_refs=["artifact://handoff-source-ref-draft"],
        log_path=log,
    )
    assert plan.status == "passed"
    assert plan.current_phase == "verification"
    assert plan.remaining_budget_units == 8
    assert plan.feedback[0]["verdict"] == "passed"

    replayed = get_phase_execution_plan(plan.plan_id, log_path=log)
    assert replayed.status == "passed"
    resource = phase_execution_plan_resource(replayed).as_dict()
    assert validate_resource(resource) == []
    assert resource["kind"] == "PhaseExecutionPlan"
    assert resource["links"] == [
        {"rel": "run", "href": "run:run_demo"},
        {"rel": "work_item", "href": "work_item:work_demo"},
    ]


def test_failed_verification_decays_budget_and_returns_to_execution(tmp_path: Path):
    log = tmp_path / "phase_execution.jsonl"
    plan = start_phase_execution_plan(
        objective="repair a missing evidence handoff",
        owner_role="role.org_evolver",
        total_budget_units=10,
        max_attempts=3,
        log_path=log,
    )
    plan = record_phase_directive(
        plan_id=plan.plan_id,
        phase="execution",
        issued_by="role.executor",
        directive="Patch the handoff guidance.",
        log_path=log,
    )
    plan = record_verification_feedback(
        plan_id=plan.plan_id,
        verifier_role="role.evaluator",
        verdict="failed",
        rationale="Patch lacks source refs.",
        evidence_refs=["artifact://failed-review"],
        budget_decay=0.5,
        log_path=log,
    )

    assert plan.status == "active"
    assert plan.current_phase == "execution"
    assert plan.attempts == 1
    assert plan.remaining_budget_units == 5
    assert plan.feedback[0]["retry_budget_before"] == 10
    assert plan.feedback[0]["retry_budget_after"] == 5


def test_repeated_failed_verification_blocks_after_attempt_cap(tmp_path: Path):
    log = tmp_path / "phase_execution.jsonl"
    plan = start_phase_execution_plan(
        objective="repair a brittle protocol",
        owner_role="role.org_evolver",
        total_budget_units=4,
        max_attempts=2,
        log_path=log,
    )
    plan = record_verification_feedback(
        plan_id=plan.plan_id,
        verifier_role="role.evaluator",
        verdict="failed",
        rationale="First repair missing evidence.",
        budget_decay=0.5,
        log_path=log,
    )
    assert plan.status == "active"
    plan = record_verification_feedback(
        plan_id=plan.plan_id,
        verifier_role="role.evaluator",
        verdict="failed",
        rationale="Second repair still missing evidence.",
        budget_decay=0.5,
        log_path=log,
    )
    assert plan.status == "blocked"
    assert plan.attempts == 2
    assert plan.failure_reason == "Second repair still missing evidence."


def test_budget_floor_blocks_retry(tmp_path: Path):
    log = tmp_path / "phase_execution.jsonl"
    plan = start_phase_execution_plan(
        objective="repair a low-budget branch",
        owner_role="role.org_evolver",
        total_budget_units=1,
        max_attempts=5,
        log_path=log,
    )
    plan = record_verification_feedback(
        plan_id=plan.plan_id,
        verifier_role="role.evaluator",
        verdict="failed",
        rationale="Failure consumes remaining review budget.",
        budget_decay=0.4,
        min_remaining_budget_units=0.5,
        log_path=log,
    )
    assert plan.status == "blocked"
    assert plan.remaining_budget_units == 0
    assert plan.feedback[0]["metadata"]["blocked_by_budget_floor"] is True


def test_blocked_phase_execution_projects_learning_candidate(tmp_path: Path):
    log = tmp_path / "phase_execution.jsonl"
    plan = start_phase_execution_plan(
        objective="repair evaluator evidence standard",
        owner_role="role.org_evolver",
        total_budget_units=2,
        max_attempts=1,
        run_id="run_phase_1",
        work_id="work_phase_1",
        metadata={"proposed_transition_kind": "evidence_gap"},
        log_path=log,
    )
    plan = record_phase_directive(
        plan_id=plan.plan_id,
        phase="execution",
        issued_by="role.executor",
        directive="Patch the evaluator handoff.",
        output_refs=["artifact://evaluator-handoff-draft"],
        log_path=log,
    )
    plan = record_verification_feedback(
        plan_id=plan.plan_id,
        verifier_role="role.evaluator",
        verdict="failed",
        rationale="Verification failed because evidence refs were missing.",
        evidence_refs=["artifact://failed-verification"],
        budget_decay=0.5,
        log_path=log,
    )

    candidate = learning_candidate_from_phase_execution_plan(plan)

    assert candidate.source_kind == "phase_execution_plan"
    assert candidate.transition_kind == "evidence_gap"
    assert candidate.severity == "blocking"
    assert candidate.object_ref == "work_phase_1"
    assert f"phase_execution_plan:{plan.plan_id}" in candidate.source_refs
    assert "artifact://evaluator-handoff-draft" in candidate.source_refs
    assert "artifact://failed-verification" in candidate.source_refs
    assert candidate.proposed_payload["attempts"] == 1
    assert candidate.observer_only is True


def test_passed_phase_execution_does_not_project_learning_candidate(tmp_path: Path):
    log = tmp_path / "phase_execution.jsonl"
    plan = start_phase_execution_plan(
        objective="complete a bounded execution loop",
        owner_role="role.executor",
        log_path=log,
    )
    plan = record_verification_feedback(
        plan_id=plan.plan_id,
        verifier_role="role.evaluator",
        verdict="passed",
        rationale="Evidence was sufficient.",
        log_path=log,
    )

    try:
        learning_candidate_from_phase_execution_plan(plan)
    except ValueError as exc:
        assert "not blocked or failed" in str(exc)
    else:
        raise AssertionError("expected passed plan to reject learning-candidate projection")
