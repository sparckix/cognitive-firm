from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.kernel_events import list_kernel_events  # noqa: E402
from cognitive_firm.orchestration.decision_rights import (  # noqa: E402
    assign_residual_right,
    get_residual_decision,
    get_residual_right_assignment,
    get_residual_right_holder,
    list_residual_decisions,
    list_residual_right_assignments,
    record_residual_decision,
    review_residual_decision,
    summarize_decision_rights,
)


class _Logs:
    """Bundle of temp log paths for one isolated decision-rights world."""

    def __init__(self, tmp_path: Path):
        self.assignments = tmp_path / "residual_right_assignments.jsonl"
        self.decisions = tmp_path / "residual_decisions.jsonl"
        self.events = tmp_path / "kernel_events.jsonl"


@pytest.fixture()
def logs(tmp_path: Path) -> _Logs:
    return _Logs(tmp_path)


def _assign(logs: _Logs, **overrides):
    base = dict(
        scope_kind="project",
        scope_ref="proj.atlas",
        holder_role="role.project_lead",
        basis="named in the project charter as residual decider",
        assigned_by="actor.governance",
        log_path=logs.assignments,
        kernel_events_log=logs.events,
    )
    base.update(overrides)
    return assign_residual_right(**base)


def _record(logs: _Logs, **overrides):
    base = dict(
        scope_kind="project",
        scope_ref="proj.atlas",
        deciding_actor="actor.lead_1",
        deciding_role="role.project_lead",
        decision_summary="paused the data import while the schema was ambiguous",
        rationale="the mandate did not specify behavior for malformed input rows",
        log_path=logs.decisions,
        assignments_log=logs.assignments,
        kernel_events_log=logs.events,
    )
    base.update(overrides)
    return record_residual_decision(**base)


def test_assign_and_get_holder(logs: _Logs):
    assignment = _assign(logs)
    assert assignment.status == "active"

    holder = get_residual_right_holder("project", "proj.atlas", log_path=logs.assignments)
    assert holder is not None
    assert holder.holder_role == "role.project_lead"
    assert holder.assignment_id == assignment.assignment_id


def test_assign_requires_a_basis(logs: _Logs):
    with pytest.raises(ValueError, match="basis is required"):
        _assign(logs, basis="")


def test_assign_rejects_unknown_scope_kind(logs: _Logs):
    with pytest.raises(ValueError, match="scope_kind"):
        _assign(logs, scope_kind="galaxy")


def test_reassignment_supersedes_the_prior_assignment(logs: _Logs):
    first = _assign(logs, holder_role="role.project_lead")
    second = _assign(logs, holder_role="role.deputy_lead")

    holder = get_residual_right_holder("project", "proj.atlas", log_path=logs.assignments)
    assert holder is not None
    assert holder.assignment_id == second.assignment_id
    assert holder.holder_role == "role.deputy_lead"

    superseded = get_residual_right_assignment(first.assignment_id, log_path=logs.assignments)
    assert superseded is not None and superseded.status == "superseded"

    active = list_residual_right_assignments(status="active", log_path=logs.assignments)
    assert [a.assignment_id for a in active] == [second.assignment_id]


def test_record_decision_under_the_right_holder_is_authorized(logs: _Logs):
    _assign(logs)
    decision = _record(logs)

    assert decision.status == "recorded"
    assert decision.unauthorized is False
    assert decision.assignment_id is not None


def test_record_decision_under_the_wrong_role_is_flagged_but_recorded(logs: _Logs):
    _assign(logs, holder_role="role.project_lead")
    decision = _record(logs, deciding_role="role.random_contributor")

    assert decision.unauthorized is True
    assert decision.status == "recorded"
    # Failed open: the decision is still persisted for review.
    stored = get_residual_decision(decision.decision_id, log_path=logs.decisions)
    assert stored is not None and stored.unauthorized is True


def test_record_decision_with_no_assignment_is_unauthorized(logs: _Logs):
    decision = _record(logs)
    assert decision.unauthorized is True
    assert decision.assignment_id is None


def test_record_decision_requires_a_rationale(logs: _Logs):
    _assign(logs)
    with pytest.raises(ValueError, match="rationale is required"):
        _record(logs, rationale="")


def test_review_outcomes_including_promote_to_mandate_clause(logs: _Logs):
    _assign(logs)
    endorsed = review_residual_decision(
        _record(logs).decision_id,
        reviewed_by="actor.governance",
        review_outcome="endorsed",
        log_path=logs.decisions,
        kernel_events_log=logs.events,
    )
    assert endorsed.status == "reviewed"
    assert endorsed.review_outcome == "endorsed"

    promoted = review_residual_decision(
        _record(logs).decision_id,
        reviewed_by="actor.governance",
        review_outcome="promote_to_mandate_clause",
        review_notes="this gap recurs; add a clause",
        log_path=logs.decisions,
        kernel_events_log=logs.events,
    )
    assert promoted.review_outcome == "promote_to_mandate_clause"
    assert promoted.review_notes


def test_review_rejects_unknown_outcome(logs: _Logs):
    _assign(logs)
    decision = _record(logs)
    with pytest.raises(ValueError, match="review_outcome"):
        review_residual_decision(
            decision.decision_id,
            reviewed_by="actor.governance",
            review_outcome="vibes",
            log_path=logs.decisions,
            kernel_events_log=logs.events,
        )


def test_review_cannot_happen_twice(logs: _Logs):
    _assign(logs)
    decision = _record(logs)
    review_residual_decision(
        decision.decision_id,
        reviewed_by="actor.governance",
        review_outcome="endorsed",
        log_path=logs.decisions,
        kernel_events_log=logs.events,
    )
    with pytest.raises(ValueError, match="illegal transition"):
        review_residual_decision(
            decision.decision_id,
            reviewed_by="actor.governance",
            review_outcome="corrected",
            log_path=logs.decisions,
            kernel_events_log=logs.events,
        )


def test_review_missing_decision_raises(logs: _Logs):
    with pytest.raises(KeyError, match="not found"):
        review_residual_decision(
            "rd_does_not_exist",
            reviewed_by="actor.governance",
            review_outcome="endorsed",
            log_path=logs.decisions,
            kernel_events_log=logs.events,
        )


def test_list_decisions_filters_by_unauthorized_flag(logs: _Logs):
    _assign(logs)
    _record(logs)  # authorized
    _record(logs, deciding_role="role.stranger")  # unauthorized

    flagged = list_residual_decisions(unauthorized=True, log_path=logs.decisions)
    assert len(flagged) == 1
    assert flagged[0].unauthorized is True

    clean = list_residual_decisions(unauthorized=False, log_path=logs.decisions)
    assert len(clean) == 1 and clean[0].unauthorized is False


def test_summary_read_model(logs: _Logs):
    # Scope with an assignment + an authorized decision awaiting review.
    _assign(logs)
    _record(logs)
    # Scope with NO assignment: an unauthorized decision, later promoted.
    orphan = _record(
        logs,
        scope_kind="decision_class",
        scope_ref="dc.budget_override",
        deciding_role="role.someone",
    )
    review_residual_decision(
        orphan.decision_id,
        reviewed_by="actor.governance",
        review_outcome="promote_to_mandate_clause",
        log_path=logs.decisions,
        kernel_events_log=logs.events,
    )

    summary = summarize_decision_rights(
        log_path=logs.decisions, assignments_log=logs.assignments
    )
    assert summary["active_assignments"] == 1
    assert summary["total_decisions"] == 2
    assert summary["unassigned_scope_count"] == 1
    assert summary["unassigned_scopes"] == [
        {"scope_kind": "decision_class", "scope_ref": "dc.budget_override"}
    ]
    assert summary["unauthorized_decision_count"] == 1
    assert summary["awaiting_review_count"] == 1
    assert summary["promote_to_mandate_candidate_count"] == 1
    assert summary["promote_to_mandate_candidate_ids"] == [orphan.decision_id]


def test_transitions_emit_kernel_events(logs: _Logs):
    assignment = _assign(logs)
    decision = _record(logs)
    review_residual_decision(
        decision.decision_id,
        reviewed_by="actor.governance",
        review_outcome="endorsed",
        log_path=logs.decisions,
        kernel_events_log=logs.events,
    )

    assign_verbs = [
        e.verb
        for e in list_kernel_events(
            object_ref=f"residual_right_assignment:{assignment.assignment_id}",
            log_path=logs.events,
        )
    ]
    assert assign_verbs == ["residual_right.assigned"]

    decision_verbs = [
        e.verb
        for e in list_kernel_events(
            object_ref=f"residual_decision:{decision.decision_id}",
            log_path=logs.events,
        )
    ]
    assert decision_verbs == ["residual_decision.recorded", "residual_decision.reviewed"]
