from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.governance_changes import (  # noqa: E402
    REQUIRED_EVIDENCE_FIELDS,
    REQUIRED_INVARIANTS,
    assess_evidence_sufficiency,
    InvariantCheck,
    failed_invariants,
    governance_change_resource,
    list_governance_changes,
    main as governance_changes_main,
    missing_required_invariants,
    propose_governance_change,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


def _passing_checks() -> list[InvariantCheck]:
    return [
        InvariantCheck(
            invariant=invariant,
            status="pass",
            rationale=f"{invariant} preserved by deterministic guard.",
            evidence_refs=[f"tests/{invariant}.txt"],
        )
        for invariant in sorted(REQUIRED_INVARIANTS)
    ]


def test_governance_change_requires_all_invariants_for_review_ready(tmp_path: Path):
    log_path = tmp_path / "governance_changes.jsonl"

    proposal = propose_governance_change(
        change_kind="mandate_change",
        title="Tighten reviewer write scope",
        proposed_by="role.research_director",
        target_ref="org/mandates/reviewer_mandate.md",
        rationale="Repeated scope drift requires a narrower default write boundary.",
        expected_behavior_change="Reviewer can edit review artifacts only unless escalated.",
        risk_summary="Narrows reviewer write scope; no additional runtime authority.",
        rollback_plan="Restore previous mandate hash.",
        source_refs=["authority_diff:reviewer-write-scope"],
        invariant_checks=_passing_checks(),
        log_path=log_path,
    )

    assert proposal.status == "review_ready"
    assert proposal.review_ready is True
    assert proposal.evidence_sufficiency is not None
    assert proposal.evidence_sufficiency.status == "pass"
    assert missing_required_invariants(proposal.invariant_checks) == []
    assert failed_invariants(proposal.invariant_checks) == []

    proposals = list_governance_changes(status="review_ready", log_path=log_path)
    assert [item.proposal_id for item in proposals] == [proposal.proposal_id]


def test_governance_change_blocks_missing_or_failed_invariants(tmp_path: Path):
    log_path = tmp_path / "governance_changes.jsonl"
    checks = [
        InvariantCheck(
            invariant="principal_independence",
            status="pass",
            rationale="Principal approval remains required.",
        ),
        InvariantCheck(
            invariant="write_scope_preserved",
            status="fail",
            rationale="Proposed route would let a role edit its own mandate.",
        ),
    ]

    proposal = propose_governance_change(
        change_kind="route_policy_change",
        title="Allow role to self-route governance changes",
        proposed_by="role.manager",
        target_ref="org/policies/routing.md",
        rationale="Would reduce review latency.",
        invariant_checks=checks,
        log_path=log_path,
    )

    assert proposal.status == "blocked"
    assert proposal.review_ready is False
    assert "write_scope_preserved" in failed_invariants(proposal.invariant_checks)
    assert "deterministic_enforcement_floor" in missing_required_invariants(proposal.invariant_checks)


def test_governance_change_blocks_insufficient_evidence_even_when_invariants_pass(
    tmp_path: Path,
):
    log_path = tmp_path / "governance_changes.jsonl"

    proposal = propose_governance_change(
        change_kind="learning_policy_change",
        title="Promote candidate learning policy",
        proposed_by="role.learning_office",
        target_ref="org/policies/learning.md",
        rationale="Repeated findings indicate the rule should change.",
        invariant_checks=[
            InvariantCheck(
                invariant=invariant,
                status="pass",
                rationale=f"{invariant} preserved by deterministic guard.",
            )
            for invariant in sorted(REQUIRED_INVARIANTS)
        ],
        log_path=log_path,
    )

    assert proposal.status == "blocked"
    assert proposal.review_ready is False
    assert proposal.evidence_sufficiency is not None
    assert proposal.evidence_sufficiency.status == "fail"
    assert set(REQUIRED_EVIDENCE_FIELDS) <= {
        item.split(":", 1)[0] for item in proposal.evidence_sufficiency.missing
    }


def test_evidence_sufficiency_requires_evidence_on_passing_invariants():
    checks = [
        InvariantCheck(
            invariant=invariant,
            status="pass",
            rationale=f"{invariant} preserved by deterministic guard.",
            evidence_refs=[f"tests/{invariant}.txt"] if invariant != "fail_closed_behavior" else [],
        )
        for invariant in sorted(REQUIRED_INVARIANTS)
    ]

    result = assess_evidence_sufficiency(
        source_refs=["policy_evaluation:eval_1"],
        expected_behavior_change="Route matching requests to the new policy.",
        risk_summary="Low-risk candidate with bounded rollback.",
        rollback_plan="Restore the previous routing policy.",
        invariant_checks=checks,
    )

    assert result.status == "fail"
    assert result.missing == ["invariant_evidence_refs:fail_closed_behavior"]


def test_governance_change_keeps_approval_separate_from_proposal(tmp_path: Path):
    proposal = propose_governance_change(
        change_kind="gate_policy_change",
        title="Add new fail-closed gate",
        proposed_by="role.engineer",
        target_ref="docs/protocols/h2a.md",
        rationale="A new external action needs explicit operator approval.",
        expected_behavior_change="External action now requires an explicit gate.",
        risk_summary="Adds a fail-closed gate; main risk is operator burden.",
        rollback_plan="Remove the gate and restore the previous policy.",
        source_refs=["evidence_gap:external_action_gate"],
        invariant_checks=_passing_checks(),
        log_path=tmp_path / "governance_changes.jsonl",
    )

    assert proposal.approval_ref is None
    assert proposal.status == "review_ready"


def test_governance_change_projects_to_resource_envelope(tmp_path: Path):
    proposal = propose_governance_change(
        change_kind="learning_policy_change",
        title="Promote measured learning policy",
        proposed_by="role.learning_office",
        target_ref="org/policies/learning.md",
        rationale="Measured pilot rows support promoting the candidate policy.",
        expected_behavior_change="Future matching work uses the promoted policy arm.",
        risk_summary="Candidate has bounded scope and no widening authority diff.",
        rollback_plan="Restore prior policy file and invalidate the candidate ref.",
        source_refs=["policy_promotion_packet:packet_1"],
        owner_role="role.principal",
        tenant_id="tenant.example",
        project_id="project.alpha",
        invariant_checks=_passing_checks(),
        metadata={"review_queue": "governance"},
        log_path=tmp_path / "governance_changes.jsonl",
    )

    payload = governance_change_resource(proposal).as_dict()

    assert validate_resource(payload) == []
    assert payload["kind"] == "GovernanceChangeProposal"
    assert payload["metadata"]["name"] == proposal.proposal_id
    assert payload["metadata"]["tenant_id"] == "tenant.example"
    assert payload["metadata"]["project_id"] == "project.alpha"
    assert payload["metadata"]["labels"]["status"] == "review_ready"
    assert payload["metadata"]["labels"]["review_ready"] == "true"
    assert payload["metadata"]["annotations"]["review_queue"] == "governance"
    assert payload["spec"]["change_kind"] == "learning_policy_change"
    assert payload["spec"]["source_refs"] == ["policy_promotion_packet:packet_1"]
    assert payload["status"]["evidence_sufficiency"]["status"] == "pass"
    assert payload["status"]["review_ready"] is True
    assert {"rel": "target", "href": "org/policies/learning.md"} in payload["links"]
    assert {
        "rel": "source",
        "href": "policy_promotion_packet:packet_1",
    } in payload["links"]


def test_governance_change_cli_can_render_resource_envelopes(
    tmp_path: Path,
    capsys,
):
    log_path = tmp_path / "governance_changes.jsonl"
    proposal = propose_governance_change(
        change_kind="gate_policy_change",
        title="Add runtime resume gate",
        proposed_by="role.engineer",
        target_ref="org/policies/runtime_resume.md",
        rationale="Runtime resume now needs a deterministic approval gate.",
        expected_behavior_change="Resume attempts without approval remain blocked.",
        risk_summary="Adds review burden but prevents unreviewed external writes.",
        rollback_plan="Remove the resume gate policy and restore previous route.",
        source_refs=["runtime_adapter:interrupt_fixture"],
        invariant_checks=_passing_checks(),
        log_path=log_path,
    )

    rc = governance_changes_main(["list", "--log-path", str(log_path), "--resource"])

    assert rc == 0
    output = capsys.readouterr().out
    assert '"kind": "GovernanceChangeProposal"' in output
    assert proposal.proposal_id in output
