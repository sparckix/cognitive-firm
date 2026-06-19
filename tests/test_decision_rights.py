from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.kernel_events import list_kernel_events  # noqa: E402
from cognitive_firm.orchestration.authority_domains import AuthorityDomain  # noqa: E402
from cognitive_firm.orchestration.decision_rights import (  # noqa: E402
    assign_residual_right,
    get_residual_decision,
    get_residual_right_assignment,
    get_residual_right_holder,
    list_residual_decisions,
    list_residual_right_assignments,
    main as decision_rights_main,
    record_residual_decision,
    residual_decision_resource,
    residual_right_assignment_resource,
    review_residual_decision,
    resolve_residual_right_holder,
    summarize_decision_rights,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


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


def test_residual_right_assignment_projects_to_resource_envelope(logs: _Logs):
    assignment = _assign(
        logs,
        holder_actor="actor.lead_1",
        tenant_id="tenant-a",
        project_id="project-a",
        metadata={"source": "charter"},
    )

    payload = residual_right_assignment_resource(assignment).as_dict()

    assert validate_resource(payload) == []
    assert payload["kind"] == "ResidualRightAssignment"
    assert payload["metadata"]["name"] == assignment.assignment_id
    assert payload["metadata"]["tenant_id"] == "tenant-a"
    assert payload["metadata"]["project_id"] == "project-a"
    assert payload["metadata"]["labels"]["scope_kind"] == "project"
    assert payload["metadata"]["labels"]["holder_role"] == "role.project_lead"
    assert payload["metadata"]["annotations"]["source"] == "charter"
    assert payload["spec"]["basis"] == "named in the project charter as residual decider"
    assert payload["status"]["status"] == "active"
    assert {"rel": "scope", "href": "project:proj.atlas"} in payload["links"]
    assert {"rel": "holder_actor", "href": "actor.lead_1"} in payload["links"]


def test_residual_right_assignment_resource_reflects_superseded_state(logs: _Logs):
    first = _assign(logs, holder_role="role.project_lead")
    _assign(logs, holder_role="role.deputy_lead")

    superseded = get_residual_right_assignment(first.assignment_id, log_path=logs.assignments)
    assert superseded is not None

    payload = residual_right_assignment_resource(superseded).as_dict()

    assert payload["metadata"]["labels"]["status"] == "superseded"
    assert payload["status"]["status"] == "superseded"


def test_record_decision_under_the_right_holder_is_authorized(logs: _Logs):
    _assign(logs)
    decision = _record(logs)

    assert decision.status == "recorded"
    assert decision.unauthorized is False
    assert decision.assignment_id is not None


def test_residual_decision_projects_to_resource_envelope(logs: _Logs):
    assignment = _assign(logs)
    decision = _record(
        logs,
        tenant_id="tenant-a",
        project_id="project-a",
        metadata={"source": "operator_note"},
    )

    payload = residual_decision_resource(decision).as_dict()

    assert validate_resource(payload) == []
    assert payload["kind"] == "ResidualDecision"
    assert payload["metadata"]["name"] == decision.decision_id
    assert payload["metadata"]["tenant_id"] == "tenant-a"
    assert payload["metadata"]["project_id"] == "project-a"
    assert payload["metadata"]["labels"]["scope_kind"] == "project"
    assert payload["metadata"]["labels"]["deciding_role"] == "role.project_lead"
    assert payload["metadata"]["labels"]["unauthorized"] == "false"
    assert payload["metadata"]["annotations"]["source"] == "operator_note"
    assert payload["spec"]["decision_summary"] == (
        "paused the data import while the schema was ambiguous"
    )
    assert payload["spec"]["assignment_id"] == assignment.assignment_id
    assert payload["status"]["status"] == "recorded"
    assert payload["status"]["unauthorized"] is False
    assert {
        "rel": "residual_right_assignment",
        "href": f"residual_right_assignment:{assignment.assignment_id}",
    } in payload["links"]


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


def test_holder_resolution_prefers_explicit_residual_assignment(logs: _Logs):
    assignment = _assign(logs, holder_role="role.project_lead")
    domains = [
        AuthorityDomain(
            domain_id="project_authority",
            authority_role_id="project_authority",
            scope_kind="project",
            scope_id="proj.atlas",
        )
    ]

    resolution = resolve_residual_right_holder(
        "project",
        "proj.atlas",
        log_path=logs.assignments,
        authority_domains=domains,
    )

    assert resolution.source == "residual_right_assignment"
    assert resolution.holder_role == "role.project_lead"
    assert resolution.assignment_id == assignment.assignment_id
    assert resolution.authority_domain_id is None
    assert resolution.explicit_assignment is True
    assert resolution.authoritative_for_decision_recording is True
    assert resolution.projection_only is False


def test_holder_resolution_projects_authority_domain_when_assignment_missing(
    logs: _Logs,
):
    domains = [
        AuthorityDomain(
            domain_id="policy_decisions",
            authority_role_id="policy_authority",
            scope_kind="decision_class",
            scope_id="policy_change",
        )
    ]

    resolution = resolve_residual_right_holder(
        "decision_class",
        "policy_change",
        log_path=logs.assignments,
        authority_domains=domains,
    )

    assert resolution.source == "authority_domain"
    assert resolution.holder_role == "role.policy_authority"
    assert resolution.assignment_id is None
    assert resolution.authority_domain_id == "policy_decisions"
    assert resolution.authority_scope_kind == "decision_class"
    assert resolution.authority_scope_id == "policy_change"
    assert resolution.explicit_assignment is False
    assert resolution.authoritative_for_decision_recording is False
    assert resolution.projection_only is True
    assert "no active residual-right assignment for scope" in resolution.issues
    assert resolution.as_dict()["resolved"] is True


def test_holder_resolution_reports_unassigned_without_assignment_or_domain(logs: _Logs):
    resolution = resolve_residual_right_holder(
        "resource_class",
        "budget",
        log_path=logs.assignments,
        authority_domains=[],
    )

    assert resolution.source == "unassigned"
    assert resolution.holder_role is None
    assert resolution.resolved is False
    assert resolution.authoritative_for_decision_recording is False
    assert "authority domains were empty" in resolution.issues


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


def test_residual_decision_resource_reflects_review_outcome(logs: _Logs):
    _assign(logs)
    decision = _record(logs, deciding_role="role.stranger")
    reviewed = review_residual_decision(
        decision.decision_id,
        reviewed_by="actor.governance",
        review_outcome="corrected",
        review_notes="role did not hold the residual right",
        log_path=logs.decisions,
        kernel_events_log=logs.events,
    )

    payload = residual_decision_resource(reviewed).as_dict()

    assert payload["metadata"]["labels"]["status"] == "reviewed"
    assert payload["metadata"]["labels"]["unauthorized"] == "true"
    assert payload["metadata"]["labels"]["review_outcome"] == "corrected"
    assert payload["status"]["reviewed_by"] == "actor.governance"
    assert payload["status"]["review_notes"] == "role did not hold the residual right"
    assert {"rel": "reviewed_by", "href": "actor.governance"} in payload["links"]


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


def test_cli_can_render_residual_right_assignment_resources(
    logs: _Logs,
    capsys: pytest.CaptureFixture[str],
):
    assignment = _assign(logs)

    rc = decision_rights_main(
        ["list-assignments", "--log-path", str(logs.assignments), "--resource"]
    )

    assert rc == 0
    payloads = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [payload["kind"] for payload in payloads] == ["ResidualRightAssignment"]
    assert payloads[0]["metadata"]["name"] == assignment.assignment_id
    assert payloads[0]["spec"]["holder_role"] == "role.project_lead"


def test_cli_holder_can_render_authority_resolution(
    logs: _Logs,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    domains = tmp_path / "authority_domains" / "authority_domains.json"
    domains.parent.mkdir(parents=True)
    domains.write_text(
        json.dumps(
            {
                "authority_domains": [
                    {
                        "domain_id": "policy_decisions",
                        "authority_role_id": "role.policy_authority",
                        "scope_kind": "decision_class",
                        "scope_id": "policy_change",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rc = decision_rights_main(
        [
            "holder",
            "--scope-kind",
            "decision_class",
            "--scope-ref",
            "policy_change",
            "--log-path",
            str(logs.assignments),
            "--resolve-authority",
            "--org-root",
            str(tmp_path),
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["holder"] is None
    assert payload["holder_resolution"]["source"] == "authority_domain"
    assert payload["holder_resolution"]["holder_role"] == "role.policy_authority"
    assert payload["holder_resolution"]["projection_only"] is True
    assert payload["boundary"]["authority_domain_fallback"] == "projection_only"


def test_cli_can_render_residual_decision_resources(
    logs: _Logs,
    capsys: pytest.CaptureFixture[str],
):
    _assign(logs)
    decision = _record(logs)

    rc = decision_rights_main(
        ["list-decisions", "--log-path", str(logs.decisions), "--resource"]
    )

    assert rc == 0
    payloads = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [payload["kind"] for payload in payloads] == ["ResidualDecision"]
    assert payloads[0]["metadata"]["name"] == decision.decision_id
    assert payloads[0]["spec"]["deciding_role"] == "role.project_lead"
