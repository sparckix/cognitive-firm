from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.governance_changes import (  # noqa: E402
    REQUIRED_EVIDENCE_FIELDS,
    REQUIRED_INVARIANTS,
    assess_evidence_sufficiency,
    classify_governance_change_tier,
    deletion_duty_invariant_check,
    InvariantCheck,
    failed_invariants,
    governance_change_from_candidate,
    governance_change_review_packet,
    governance_change_review_projection,
    governance_change_resource,
    list_governance_changes,
    main as governance_changes_main,
    missing_required_invariants,
    propose_governance_change,
    tier_classification_invariant_check,
)
from cognitive_firm.orchestration.learning_transition_compiler import (  # noqa: E402
    LearningTransitionCandidate,
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


def test_governance_change_review_projection_summarizes_review_state(tmp_path: Path):
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

    projection = governance_change_review_projection(proposal)

    assert projection["proposal_id"] == proposal.proposal_id
    assert projection["review_state"] == "awaiting_review"
    assert projection["read_only"] is True
    assert projection["evidence_status"] == "pass"
    assert projection["missing_evidence"] == []
    assert projection["failed_invariants"] == []
    assert projection["missing_required_invariants"] == []
    assert projection["source_ref_count"] == 1
    assert projection["evidence_ref_count"] >= len(REQUIRED_INVARIANTS)
    assert projection["decision_route"].endswith(
        f"/kernel/governance-changes/{proposal.proposal_id}/decision"
    )

    decided = governance_change_review_projection(proposal, decided=True)
    assert decided["review_state"] == "decided"


def test_governance_change_review_packet_exports_handoff(tmp_path: Path):
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
    packet = governance_change_review_packet(
        proposal,
        provenance_report={
            "query": {"ref": f"governance_change:{proposal.proposal_id}"},
            "summary": {"event_count": 1},
            "coverage": {"status": "partial", "gaps": ["no outcome link"]},
            "follow_through": {
                "status": "proposal_only",
                "decision_events": 0,
                "outcome_links": 0,
                "routine_reviews": 0,
                "learning_use_receipts": 0,
                "latest_refs": [f"governance_change:{proposal.proposal_id}"],
                "review_questions": [
                    "What decision, outcome link, or routine review should close this loop?"
                ],
                "read_only": True,
                "projection_only": True,
            },
            "caveats": ["projection-only fixture"],
            "event_excerpt": [],
            "evidence_refs": [],
        },
    )

    assert packet["packet_kind"] == "governance_change_review_handoff"
    assert packet["read_only"] is True
    assert packet["projection_only"] is True
    assert packet["review"]["review_state"] == "awaiting_review"
    assert packet["decision_route"].endswith(
        f"/kernel/governance-changes/{proposal.proposal_id}/decision"
    )
    refs = {row["ref"]: row for row in packet["evidence_refs"]}
    assert "authority_diff:reviewer-write-scope" in refs
    assert "source_refs" in refs["authority_diff:reviewer-write-scope"]["sources"]
    assert any(
        row["ref"] == "tests/write_scope_preserved.txt"
        and "write_scope_preserved" in row["invariants"]
        for row in packet["evidence_refs"]
    )
    assert packet["provenance_report"]["coverage"]["status"] == "partial"
    assert packet["follow_through"]["status"] == "proposal_only"
    assert (
        "What decision, outcome link, or routine review should close this loop?"
        in packet["review_questions"]
    )
    assert any(
        "Do the cited refs support" in question
        for question in packet["review_questions"]
    )
    assert "# Governance Change Review Packet" in packet["markdown"]
    assert "authority_diff:reviewer-write-scope" in packet["markdown"]


def test_governance_change_review_surfaces_formal_proof_obligation(
    tmp_path: Path,
) -> None:
    proposal = propose_governance_change(
        change_kind="route_policy_change",
        title="Review provider routing policy",
        proposed_by="role.governance_reviewer",
        target_ref="policy://support/provider-routing",
        rationale="Measured action-impact rows favor the candidate route.",
        expected_behavior_change="Route provider-sensitive cases to specialist review.",
        risk_summary="Changes a policy adapter but does not grant new authority.",
        rollback_plan="Revert to the prior route policy.",
        source_refs=[
            "action_impact_policy_evaluation:eval_provider_route",
            "formal_verification:fver_provider_route_safety",
        ],
        invariant_checks=_passing_checks(),
        log_path=tmp_path / "governance_changes.jsonl",
    )

    projection = governance_change_review_projection(proposal)
    proof = projection["proof_obligations"]

    assert projection["review_state"] == "awaiting_review"
    assert proof["status"] == "satisfied"
    assert proof["expected"] is True
    assert proof["required"] is False
    assert proof["blocking"] is False
    assert proof["formal_verification_refs"] == [
        "formal_verification:fver_provider_route_safety"
    ]

    packet = governance_change_review_packet(proposal)
    assert packet["proof_obligations"]["status"] == "satisfied"
    assert "## Proof Obligations" in packet["markdown"]
    assert "formal_verification:fver_provider_route_safety" in packet["markdown"]


def test_governance_change_review_warns_when_policy_proof_missing(
    tmp_path: Path,
) -> None:
    proposal = propose_governance_change(
        change_kind="gate_policy_change",
        title="Relax deploy gate",
        proposed_by="role.release_owner",
        target_ref="gate://deploy/high-risk-policy",
        rationale="Pilot data suggests the existing gate is too strict.",
        expected_behavior_change="Allow a narrower reviewer set on low-risk deploys.",
        risk_summary="Touches a high-risk policy gate.",
        rollback_plan="Restore the previous gate policy.",
        source_refs=["pilot:deploy-gate-summary"],
        invariant_checks=_passing_checks(),
        log_path=tmp_path / "governance_changes.jsonl",
    )

    projection = governance_change_review_projection(proposal)
    proof = projection["proof_obligations"]

    assert projection["review_state"] == "awaiting_review"
    assert proof["status"] == "attention"
    assert proof["expected"] is True
    assert proof["required"] is False
    assert proof["blocking"] is False
    assert proof["missing"] == ["formal_verification_ref"]


def test_governance_change_review_blocks_explicit_required_proof(
    tmp_path: Path,
) -> None:
    proposal = propose_governance_change(
        change_kind="tenant_policy_change",
        title="Install verifier policy",
        proposed_by="role.release_owner",
        target_ref="provider://formal-verification/leanmill",
        rationale="Require formal provider payloads for high-risk policy checks.",
        expected_behavior_change="High-risk checks must cite provider proof payloads.",
        risk_summary="Changes tenant verifier trust policy.",
        rollback_plan="Remove the provider trust-policy entry.",
        source_refs=["authority_diff:leanmill-provider"],
        invariant_checks=_passing_checks(),
        metadata={
            "requires_formal_verification": True,
            "formal_proof_obligations": [
                {
                    "obligation_id": "provider_payload_contract",
                    "property_class": "contract",
                    "subject_ref": "provider://formal-verification/leanmill",
                    "required": True,
                }
            ],
        },
        log_path=tmp_path / "governance_changes.jsonl",
    )

    projection = governance_change_review_projection(proposal)
    proof = projection["proof_obligations"]

    assert proposal.status == "review_ready"
    assert projection["review_state"] == "blocked"
    assert proof["status"] == "blocking"
    assert proof["required"] is True
    assert proof["blocking"] is True
    assert proof["missing"] == ["formal_verification_ref"]
    assert proof["obligations"][0]["obligation_id"] == "provider_payload_contract"


def test_governance_change_review_projection_does_not_mark_failed_invariants_passed(
    tmp_path: Path,
):
    log_path = tmp_path / "governance_changes.jsonl"
    checks = _passing_checks()
    failed = checks[0]
    unknown = checks[1]
    checks[0] = InvariantCheck(
        invariant=failed.invariant,
        status="fail",
        rationale="Fixture failure.",
        evidence_refs=["test:failed"],
    )
    checks[1] = InvariantCheck(
        invariant=unknown.invariant,
        status="unknown",
        rationale="Fixture unknown.",
        evidence_refs=["test:unknown"],
    )

    proposal = propose_governance_change(
        change_kind="mandate_change",
        title="Blocked reviewer write scope",
        proposed_by="role.research_director",
        target_ref="org/mandates/reviewer_mandate.md",
        rationale="Repeated scope drift requires review.",
        expected_behavior_change="Reviewer can edit review artifacts only.",
        risk_summary="Narrows reviewer write scope.",
        rollback_plan="Restore previous mandate hash.",
        source_refs=["authority_diff:reviewer-write-scope"],
        invariant_checks=checks,
        log_path=log_path,
    )

    projection = governance_change_review_projection(proposal)

    assert projection["review_state"] == "blocked"
    assert failed.invariant in projection["failed_invariants"]
    assert unknown.invariant in projection["unknown_invariants"]
    assert failed.invariant not in projection["passed_required_invariants"]
    assert unknown.invariant not in projection["passed_required_invariants"]


def test_governance_change_can_carry_typed_predicted_effect(tmp_path: Path):
    log_path = tmp_path / "governance_changes.jsonl"

    proposal = propose_governance_change(
        change_kind="mandate_change",
        title="Tighten handoff mandate",
        proposed_by="role.org_evolver",
        target_ref="org/mandates/evaluator.md",
        rationale="Verifier misses show handoffs need a measured acceptance rule.",
        predicted_effect={
            "metric_name": "handoff_rework_rate",
            "metric_unit": "ratio",
            "direction": "lower_is_better",
            "threshold": 0.1,
            "review_horizon": "after_next_10_handoffs",
            "expected_verdict": "improved",
        },
        risk_summary="Narrows acceptance criteria without expanding authority.",
        rollback_plan="Restore prior evaluator mandate.",
        source_refs=["outcome_link:olink_baseline"],
        invariant_checks=_passing_checks(),
        log_path=log_path,
    )

    assert proposal.status == "review_ready"
    assert proposal.predicted_effect == {
        "metric_name": "handoff_rework_rate",
        "metric_unit": "ratio",
        "direction": "lower_is_better",
        "threshold": 0.1,
        "review_horizon": "after_next_10_handoffs",
        "expected_verdict": "improved",
        "rationale": None,
    }
    assert proposal.expected_behavior_change is None
    assert proposal.evidence_sufficiency is not None
    assert proposal.evidence_sufficiency.status == "pass"

    payload = governance_change_resource(proposal).as_dict()
    assert payload["spec"]["predicted_effect"] == proposal.predicted_effect
    loaded = list_governance_changes(log_path=log_path)[0]
    assert loaded.predicted_effect == proposal.predicted_effect


def test_governance_change_tier_classification_standard_check() -> None:
    tier0 = tier_classification_invariant_check(
        target_ref="org/roles/principal.yaml",
        change_kind="role_change",
    )
    assert tier0.status == "fail"
    assert "tier_0_immutable" in tier0.rationale
    assert "tier_classification:tier_0_immutable" in tier0.evidence_refs

    tier1 = tier_classification_invariant_check(
        target_ref="org/charters/self_evolving_firm.md",
        change_kind="project_charter_change",
    )
    assert tier1.status == "pass"
    assert "principal_explicit_approval" in tier1.rationale

    tier2 = classify_governance_change_tier(
        target_ref="org/policies/review.md",
        change_kind="learning_policy_change",
    )
    assert tier2 == {
        "tier": "tier_2_governed_mutation",
        "required_approval_path": "ordinary_governed_mutation",
        "rationale": "target affects ordinary governed organization structure",
    }


def test_deletion_duty_optional_invariant_check() -> None:
    missing = deletion_duty_invariant_check(
        target_ref="org/roles/new_reviewer.yaml",
        change_kind="role_change",
    )
    assert missing.status == "fail"
    assert "retirement candidate" in missing.rationale
    assert "deletion_duty:missing_retirement_or_justification" in missing.evidence_refs

    retirement = deletion_duty_invariant_check(
        target_ref="org/policies/new_review.md",
        change_kind="learning_policy_change",
        retirement_candidate_ref="org/policies/old_review.md",
    )
    assert retirement.status == "pass"
    assert "retirement_candidate:org/policies/old_review.md" in retirement.evidence_refs

    justified = deletion_duty_invariant_check(
        target_ref="org/decision_models/resource_allocation.md",
        change_kind="tenant_policy_change",
        net_growth_justification="Adds a decision model needed for the workload probe.",
    )
    assert justified.status == "pass"
    assert "net_growth_justification:present" in justified.evidence_refs

    not_applicable = deletion_duty_invariant_check(
        target_ref="org/mandates/evaluator.md",
        change_kind="mandate_change",
    )
    assert not_applicable.status == "pass"
    assert "deletion_duty:not_applicable" in not_applicable.evidence_refs


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


def test_governance_change_from_candidate_preserves_evidence_and_gate(tmp_path: Path):
    candidate = LearningTransitionCandidate(
        candidate_id="ltc_test_candidate",
        transition_kind="mandate_review",
        severity="warning",
        rationale="Verifier failures show the mandate needs clearer evidence requirements.",
        source_kind="multi_agent_failure_attribution",
        object_ref="protocol:handoff-source-refs",
        suggested_owner_role="role.evaluator",
        review_question="Should handoff evidence requirements change?",
        source_refs=["multi_agent_attribution:packet_1"],
        proposed_payload={"diagnostics": {"verifier_failures": 1}},
    )

    proposal = governance_change_from_candidate(
        candidate,
        target_ref="org/mandates/evaluator.md",
        proposed_by="role.evaluator",
        expected_behavior_change="Evaluator mandate now requires source refs before accepting handoffs.",
        risk_summary="Narrows acceptance criteria and does not expand authority.",
        rollback_plan="Restore the previous evaluator mandate text.",
        invariant_checks=_passing_checks(),
        log_path=tmp_path / "governance_changes.jsonl",
    )

    assert proposal.status == "review_ready"
    assert proposal.change_kind == "mandate_change"
    assert proposal.owner_role == "role.evaluator"
    assert "multi_agent_attribution:packet_1" in proposal.source_refs
    assert "protocol:handoff-source-refs" in proposal.source_refs
    assert "learning_transition_candidate:ltc_test_candidate" in proposal.source_refs
    assert proposal.metadata["candidate_id"] == "ltc_test_candidate"
    assert proposal.metadata["candidate_source_kind"] == "multi_agent_failure_attribution"


def test_governance_change_from_candidate_still_blocks_missing_review_evidence(tmp_path: Path):
    candidate = LearningTransitionCandidate(
        candidate_id="ltc_weak_candidate",
        transition_kind="evidence_gap",
        severity="warning",
        rationale="A capability signal indicates missing evidence.",
        source_kind="capability_signal",
        object_ref="work_item:work_1",
        source_refs=["capability_signal:csig_1"],
    )

    proposal = governance_change_from_candidate(
        candidate,
        target_ref="org/policies/learning.md",
        proposed_by="role.evaluator",
        log_path=tmp_path / "governance_changes.jsonl",
    )

    assert proposal.status == "blocked"
    assert proposal.change_kind == "learning_policy_change"
    assert proposal.evidence_sufficiency is not None
    assert proposal.evidence_sufficiency.status == "fail"


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
