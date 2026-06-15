from __future__ import annotations

from cognitive_firm.orchestration.mutation_proofs import (
    GOVERNED_MUTATION_PROOF_STAGES,
    build_governed_mutation_proof,
    governed_mutation_proof_to_dict,
    validate_governed_mutation_proof_payload,
)


def test_governed_mutation_proof_builds_valid_digest_and_chain() -> None:
    proof = build_governed_mutation_proof(
        step_id="evaluator_handoff",
        change_kind="mandate_change",
        target_ref="org/mandates/evaluator.md",
        run_id="run_123",
        work_id="work_123",
        proposal_id="gcp_123",
        approval_event_id="evt_123",
        mutation_ref="file://org/mandates/evaluator.md",
        attestation_id="aat_123",
        learning_event_id="learn_123",
        outcome_link_id="olink_123",
        routine_review_id="rrev_123",
        bundle_id="gab_run_123",
        bundle_digest="sha256:" + "a" * 64,
        bundle_verdict="passed",
        commit_sha="abc123",
        evidence_carrier_refs=[
            "phase_execution_plan:pex_123",
            "phase_execution_plan:pex_123",
            "capability_signal:csig_123",
        ],
    )

    payload = governed_mutation_proof_to_dict(proof)

    assert proof.valid is True
    assert proof.validation_errors == []
    assert proof.evidence_carrier_refs == [
        "phase_execution_plan:pex_123",
        "capability_signal:csig_123",
    ]
    assert proof.proof_digest.startswith("sha256:")
    assert [item["stage"] for item in payload["chain"]] == list(
        GOVERNED_MUTATION_PROOF_STAGES
    )
    assert validate_governed_mutation_proof_payload(payload) == []


def test_governed_mutation_proof_rejects_incomplete_evidence() -> None:
    proof = build_governed_mutation_proof(
        step_id="missing_bundle",
        change_kind="role_change",
        target_ref="org/roles/reviewer.yaml",
        run_id="run_123",
        work_id="work_123",
        proposal_id="gcp_123",
        approval_event_id="evt_123",
        mutation_ref="file://org/roles/reviewer.yaml",
        attestation_id="aat_123",
        learning_event_id="learn_123",
        outcome_link_id="olink_123",
        routine_review_id="rrev_123",
        bundle_id=None,
        bundle_digest=None,
        bundle_verdict="incomplete",
        commit_sha="",
        bundle_validation_errors=["missing action attestation"],
    )

    assert proof.valid is False
    assert "bundle validation errors present" in proof.validation_errors
    assert "bundle verdict must be passed" in proof.validation_errors
    assert "bundle_digest must be a sha256 digest" in proof.validation_errors
    assert "commit is required" in proof.validation_errors
    assert any("bundle" in error for error in proof.validation_errors)


def test_governed_mutation_proof_payload_detects_tampering() -> None:
    proof = build_governed_mutation_proof(
        step_id="learning_review",
        change_kind="learning_policy_change",
        target_ref="org/policies/learning-review.md",
        run_id="run_123",
        work_id="work_123",
        proposal_id="gcp_123",
        approval_event_id="evt_123",
        mutation_ref="file://org/policies/learning-review.md",
        attestation_id="aat_123",
        learning_event_id="learn_123",
        outcome_link_id="olink_123",
        routine_review_id="rrev_123",
        bundle_id="gab_run_123",
        bundle_digest="sha256:" + "b" * 64,
        bundle_verdict="passed",
        commit_sha="def456",
    )
    payload = governed_mutation_proof_to_dict(proof)
    payload["chain"][2]["ref"] = "governance_change:tampered"

    errors = validate_governed_mutation_proof_payload(payload)

    assert any("proof_digest mismatch" in error for error in errors)
    assert any("valid flag does not match" in error for error in errors)


def test_governed_mutation_proof_payload_validates_evidence_carrier_refs() -> None:
    proof = build_governed_mutation_proof(
        step_id="learning_review",
        change_kind="learning_policy_change",
        target_ref="org/policies/learning-review.md",
        run_id="run_123",
        work_id="work_123",
        proposal_id="gcp_123",
        approval_event_id="evt_123",
        mutation_ref="file://org/policies/learning-review.md",
        attestation_id="aat_123",
        learning_event_id="learn_123",
        outcome_link_id="olink_123",
        routine_review_id="rrev_123",
        bundle_id="gab_run_123",
        bundle_digest="sha256:" + "b" * 64,
        bundle_verdict="passed",
        commit_sha="def456",
        evidence_carrier_refs=["capability_signal:csig_123"],
    )
    payload = governed_mutation_proof_to_dict(proof)
    payload["evidence_carrier_refs"] = ["capability_signal:csig_123", ""]

    errors = validate_governed_mutation_proof_payload(payload)

    assert any("evidence_carrier_refs must contain non-empty strings" in error for error in errors)
    assert any("proof_digest mismatch" in error for error in errors)
