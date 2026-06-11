from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_attestation import list_action_attestations  # noqa: E402
from cognitive_firm.distribution.signing import generate_keypair  # noqa: E402
from cognitive_firm.orchestration.formal_verification import (  # noqa: E402
    FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
    FORMAL_VERIFICATION_TRUST_POLICY_VERSION,
    TRUSTED_FORMAL_VERIFICATION_PROVIDERS_RELATIVE_PATH,
    configure_trusted_provider,
    create_formal_verification_from_provider_payload,
    create_formal_verification,
    load_formal_verification_trust_policy,
    list_formal_verifications,
    main as formal_verification_main,
    provider_payload_from_dict,
    sign_provider_payload,
    validate_formal_verification_trust_policy_file,
)


def _write_trusted_provider_policy(
    authority_root: Path,
    *,
    provider: str,
    public_key_pem: str,
) -> None:
    path = authority_root / TRUSTED_FORMAL_VERIFICATION_PROVIDERS_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": FORMAL_VERIFICATION_TRUST_POLICY_VERSION,
                "trusted_providers": [
                    {
                        "provider": provider,
                        "trust_basis": "test policy",
                        "public_key_pem": public_key_pem,
                        "requires_payload_signature": True,
                        "requires_reverification_refs": True,
                        "requires_faithfulness_refs": True,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_create_formal_verification_records_certificate_and_action_attestation(tmp_path: Path):
    formal_log = tmp_path / "formal_verifications.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"

    record = create_formal_verification(
        formal_system="lean",
        verifier_ref="lean:4.30.0",
        property_class="policy",
        subject_ref="policy://basel/cet1-threshold",
        subject_digest="sha256:policy",
        claim_ref="claim://cet1-threshold",
        certificate_ref="proofs/basel_threshold.lean#adequate_iff",
        certificate_digest="sha256:proof",
        verdict="verified",
        verification_summary="Lean certificate checks the labelled boundary cases.",
        assumption_refs=["assumption://basis-points-encoding"],
        input_refs=["policy://basel/cet1"],
        output_refs=["proofs/basel_threshold.lean"],
        tenant_id="tenant-bank",
        project_id="project-policy",
        run_id="run_123",
        log_path=formal_log,
        action_attestation_log_path=attestation_log,
    )

    assert record.verification_id.startswith("fver_")
    assert record.action_attestation_id is not None
    assert record.verdict == "verified"

    rows = list_formal_verifications(run_id="run_123", log_path=formal_log)
    assert rows == [record]

    attestations = list_action_attestations(run_id="run_123", log_path=attestation_log)
    assert len(attestations) == 1
    assert attestations[0].verification_status == "verified"
    assert attestations[0].signature_ref == "proofs/basel_threshold.lean#adequate_iff"
    assert attestations[0].transparency_ref == "sha256:proof"
    assert attestations[0].metadata["formal_system"] == "lean"


def test_formal_verification_refuted_maps_to_failed_attestation(tmp_path: Path):
    formal_log = tmp_path / "formal_verifications.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"

    record = create_formal_verification(
        formal_system="smt",
        verifier_ref="z3:4.13",
        property_class="contract",
        subject_ref="contract://shipment-state-machine",
        subject_digest="sha256:contract",
        claim_ref="claim://no-ship-before-paid",
        certificate_ref="z3://counterexample/no-ship-before-paid",
        certificate_digest="sha256:model",
        verdict="refuted",
        verification_summary="SMT found a counterexample.",
        counterexample_ref="z3://model/1",
        run_id="run_456",
        log_path=formal_log,
        action_attestation_log_path=attestation_log,
    )

    assert record.verdict == "refuted"
    attestations = list_action_attestations(run_id="run_456", log_path=attestation_log)
    assert attestations[0].verification_status == "failed"
    assert attestations[0].metadata["formal_verification_verdict"] == "refuted"


def test_provider_payload_creates_record_and_preserves_provider_evidence(tmp_path: Path):
    formal_log = tmp_path / "formal_verifications.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"

    record = create_formal_verification_from_provider_payload(
        {
            "schema_version": FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
            "provider": "leanmill",
            "formal_system": "lean",
            "verifier_ref": "leanmill:certify-demo@abc123",
            "property_class": "workflow_safety",
            "subject_ref": "workflow://release-checklist",
            "subject_digest": "sha256:workflow",
            "claim_ref": "claim://release-requires-review",
            "certificate_ref": "leanmill://certificates/release_requires_review",
            "certificate_digest": "sha256:certificate",
            "verdict": "verified",
            "verification_summary": "LeanMill emitted a checked workflow invariant.",
            "input_refs": ["workflow://release-checklist"],
            "output_refs": ["leanmill://proof/release_requires_review"],
            "faithfulness_refs": ["leanmill://faithfulness/release_requires_review"],
            "checker_evidence_refs": ["leanmill://kernel-log/release_requires_review"],
            "run_id": "run_provider",
            "metadata": {"provider_route": "certify-demo"},
        },
        log_path=formal_log,
        action_attestation_log_path=attestation_log,
    )

    assert record.verdict == "verified"
    assert record.metadata["provider"] == "leanmill"
    assert record.metadata["provider_payload_schema"] == FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION
    assert record.metadata["faithfulness_refs"] == [
        "leanmill://faithfulness/release_requires_review"
    ]
    assert "leanmill://faithfulness/release_requires_review" in record.input_refs
    assert "leanmill://kernel-log/release_requires_review" in record.output_refs

    attestations = list_action_attestations(run_id="run_provider", log_path=attestation_log)
    assert len(attestations) == 1
    assert attestations[0].metadata["provider"] == "leanmill"


def test_signed_provider_payload_verifies_against_installed_policy(tmp_path: Path):
    keypair = generate_keypair()
    authority_root = tmp_path / "org"
    _write_trusted_provider_policy(
        authority_root,
        provider="leanmill",
        public_key_pem=keypair.public_pem,
    )
    formal_log = tmp_path / "formal_verifications.jsonl"
    payload = {
        "schema_version": FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
        "provider": "leanmill",
        "formal_system": "lean",
        "verifier_ref": "leanmill:certify-demo@abc123",
        "property_class": "workflow_safety",
        "subject_ref": "workflow://release-checklist",
        "subject_digest": "sha256:workflow",
        "claim_ref": "claim://release-requires-review",
        "certificate_ref": "leanmill://certificates/release_requires_review",
        "certificate_digest": "sha256:certificate",
        "verdict": "verified",
        "verification_summary": "LeanMill emitted a checked workflow invariant.",
        "faithfulness_refs": ["leanmill://faithfulness/release_requires_review"],
        "checker_evidence_refs": ["leanmill://kernel-log/release_requires_review"],
        "run_id": "run_provider_signed",
        "metadata": {},
    }
    payload["metadata"]["provider_payload_signature"] = sign_provider_payload(
        payload,
        private_key_pem=keypair.private_pem,
    )

    record = create_formal_verification_from_provider_payload(
        payload,
        log_path=formal_log,
        create_attestation=False,
        authority_root=authority_root,
    )

    assert record.metadata["provider_payload_signature_verified"] is True
    assert record.metadata["provider_payload_digest"].startswith("sha256:")


def test_signed_provider_payload_rejects_forged_signature(tmp_path: Path):
    trusted_keypair = generate_keypair()
    attacker_keypair = generate_keypair()
    authority_root = tmp_path / "org"
    _write_trusted_provider_policy(
        authority_root,
        provider="leanmill",
        public_key_pem=trusted_keypair.public_pem,
    )
    payload = {
        "schema_version": FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
        "provider": "leanmill",
        "formal_system": "lean",
        "verifier_ref": "leanmill:certify-demo@abc123",
        "property_class": "workflow_safety",
        "subject_ref": "workflow://release-checklist",
        "subject_digest": "sha256:workflow",
        "claim_ref": "claim://release-requires-review",
        "certificate_ref": "leanmill://certificates/release_requires_review",
        "certificate_digest": "sha256:certificate",
        "verdict": "verified",
        "verification_summary": "LeanMill emitted a checked workflow invariant.",
        "faithfulness_refs": ["leanmill://faithfulness/release_requires_review"],
        "checker_evidence_refs": ["leanmill://kernel-log/release_requires_review"],
        "metadata": {},
    }
    payload["metadata"]["provider_payload_signature"] = sign_provider_payload(
        payload,
        private_key_pem=attacker_keypair.private_pem,
    )

    with pytest.raises(ValueError, match="provider_payload_signature did not verify"):
        create_formal_verification_from_provider_payload(
            payload,
            log_path=tmp_path / "formal_verifications.jsonl",
            create_attestation=False,
            authority_root=authority_root,
        )


def test_configure_trusted_provider_writes_policy_entry(tmp_path: Path):
    keypair = generate_keypair()
    entry = configure_trusted_provider(
        provider="LeanMill",
        public_key_pem=keypair.public_pem,
        authority_root=tmp_path,
        public_key_ref="leanmill://keys/current",
        trust_basis="operator-approved test key",
    )

    assert entry["provider"] == "leanmill"
    assert entry["public_key_ref"] == "leanmill://keys/current"
    assert entry["requires_payload_signature"] is True
    policy_entries = load_formal_verification_trust_policy(tmp_path)
    assert policy_entries == [entry]


def test_configure_trusted_provider_rejects_invalid_public_key(tmp_path: Path):
    with pytest.raises(ValueError, match="cannot load public key"):
        configure_trusted_provider(
            provider="leanmill",
            public_key_pem="not a pem",
            authority_root=tmp_path,
        )


def test_trust_policy_validator_accepts_overlay_key_ref_placeholder():
    policy_path = (
        ROOT
        / "distro"
        / "leanmill-formal-verification"
        / "files"
        / "formal_verification"
        / "trusted_providers.json"
    )

    assert validate_formal_verification_trust_policy_file(policy_path) == []


def test_trust_policy_validator_flags_signature_policy_without_key_or_ref(
    tmp_path: Path,
):
    policy_path = tmp_path / "trusted_providers.json"
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": FORMAL_VERIFICATION_TRUST_POLICY_VERSION,
                "trusted_providers": [
                    {
                        "provider": "leanmill",
                        "requires_payload_signature": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    issues = validate_formal_verification_trust_policy_file(policy_path)

    assert any("requires payload signatures" in issue for issue in issues)


def test_trust_provider_cli_writes_policy_entry(tmp_path: Path, capsys):
    keypair = generate_keypair()
    key_path = tmp_path / "leanmill.pub"
    key_path.write_text(keypair.public_pem, encoding="utf-8")

    assert formal_verification_main(
        [
            "trust-provider",
            "--provider",
            "leanmill",
            "--public-key-file",
            str(key_path),
            "--public-key-ref",
            "leanmill://keys/current",
            "--authority-root",
            str(tmp_path),
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["provider"] == "leanmill"
    assert payload["public_key_ref"] == "leanmill://keys/current"
    policy_entries = load_formal_verification_trust_policy(tmp_path)
    assert policy_entries[0]["public_key_pem"] == keypair.public_pem


def test_provider_payload_requires_supported_schema_version():
    with pytest.raises(ValueError, match="unsupported schema_version"):
        provider_payload_from_dict(
            {
                "schema_version": "formal-verification-provider/v99",
                "provider": "leanmill",
            }
        )


def test_provider_payload_requires_counterexample_for_refutation():
    payload = {
        "schema_version": FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
        "provider": "smt-adapter",
        "formal_system": "smt",
        "verifier_ref": "z3:4.13",
        "property_class": "contract",
        "subject_ref": "contract://shipment",
        "subject_digest": "sha256:subject",
        "claim_ref": "claim://no-ship-before-paid",
        "certificate_ref": "z3://counterexample/no-ship-before-paid",
        "certificate_digest": "sha256:model",
        "verdict": "refuted",
        "verification_summary": "SMT found a counterexample.",
    }

    with pytest.raises(ValueError, match="counterexample_ref is required"):
        provider_payload_from_dict(payload)


def test_provider_payload_cli_creates_record(tmp_path: Path, capsys):
    payload_path = tmp_path / "provider_payload.json"
    formal_log = tmp_path / "formal_verifications.jsonl"
    payload_path.write_text(
        json.dumps(
            {
                "schema_version": FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
                "provider": "alloy-adapter",
                "formal_system": "alloy",
                "verifier_ref": "alloy:6.1",
                "property_class": "schema",
                "subject_ref": "schema://order",
                "subject_digest": "sha256:order",
                "claim_ref": "claim://order-transition-total",
                "certificate_ref": "alloy://instances/order-transition-total",
                "certificate_digest": "sha256:alloy",
                "verdict": "inconclusive",
                "verification_summary": "Bounded search did not settle the property.",
                "run_id": "run_provider_cli",
            }
        ),
        encoding="utf-8",
    )

    assert formal_verification_main(
        [
            "create-from-provider-payload",
            "--payload-json",
            str(payload_path),
            "--log-path",
            str(formal_log),
            "--no-action-attestation",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "run_provider_cli"
    assert payload["metadata"]["provider"] == "alloy-adapter"
    assert len(list_formal_verifications(run_id="run_provider_cli", log_path=formal_log)) == 1


def test_formal_verification_validates_enums(tmp_path: Path):
    with pytest.raises(ValueError, match="invalid formal_system"):
        create_formal_verification(
            formal_system="spreadsheet",
            verifier_ref="tool",
            property_class="policy",
            subject_ref="subject",
            subject_digest="sha256:x",
            claim_ref="claim",
            certificate_ref="cert",
            certificate_digest="sha256:y",
            verdict="verified",
            verification_summary="summary",
            log_path=tmp_path / "formal.jsonl",
            create_attestation=False,
        )


def test_formal_verification_cli_lists_records(tmp_path: Path, capsys):
    formal_log = tmp_path / "formal_verifications.jsonl"
    create_formal_verification(
        formal_system="isabelle",
        verifier_ref="isabelle:2025",
        property_class="workflow_safety",
        subject_ref="workflow://release",
        subject_digest="sha256:workflow",
        claim_ref="claim://review-before-release",
        certificate_ref="isabelle://theory/release",
        certificate_digest="sha256:theory",
        verdict="inconclusive",
        verification_summary="Timeout before proof search completed.",
        run_id="run_cli",
        log_path=formal_log,
        create_attestation=False,
    )

    assert formal_verification_main(["list", "--run-id", "run_cli", "--log-path", str(formal_log)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1
    assert payload[0]["formal_system"] == "isabelle"
    assert payload[0]["verdict"] == "inconclusive"


def test_formal_verification_cli_creates_record(tmp_path: Path, capsys):
    formal_log = tmp_path / "formal_verifications.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"

    assert formal_verification_main([
        "create",
        "--formal-system",
        "lean",
        "--verifier-ref",
        "lean:4.30.0",
        "--property-class",
        "schema",
        "--subject-ref",
        "schema://invoice",
        "--subject-digest",
        "sha256:schema",
        "--claim-ref",
        "claim://invoice-total-nonnegative",
        "--certificate-ref",
        "proofs/invoice.lean#total_nonnegative",
        "--certificate-digest",
        "sha256:proof",
        "--verdict",
        "verified",
        "--verification-summary",
        "Lean checked the schema invariant.",
        "--input-ref",
        "schema://invoice",
        "--output-ref",
        "proofs/invoice.lean",
        "--run-id",
        "run_cli_create",
        "--log-path",
        str(formal_log),
        "--action-attestation-log-path",
        str(attestation_log),
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "run_cli_create"
    assert payload["action_attestation_id"]
    assert len(list_formal_verifications(run_id="run_cli_create", log_path=formal_log)) == 1
