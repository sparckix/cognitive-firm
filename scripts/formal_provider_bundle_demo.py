#!/usr/bin/env python3
"""Demonstrate signed formal-verification provider evidence in a governed bundle.

The fixture is deterministic and uses no external checker. It simulates the
provider boundary the same way an adapter would use it:

provider payload -> formal-verification row -> action attestation -> governed-run bundle

One run carries signed, re-runnable, faithfulness-backed LeanMill-style
evidence and passes. A second run records a provider-backed verified row but
omits the trust evidence required by org policy, so the bundle is incomplete.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from cognitive_firm.distribution.signing import generate_keypair
from cognitive_firm.orchestration.action_attestation import digest_text
from cognitive_firm.orchestration.artifact_bundle import (
    build_governed_run_attestation_bundle,
    governed_run_bundle_summary,
    governed_run_bundle_to_dict,
    validate_governed_run_bundle_payload,
)
from cognitive_firm.orchestration.formal_verification import (
    FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
    FORMAL_VERIFICATION_TRUST_POLICY_VERSION,
    TRUSTED_FORMAL_VERIFICATION_PROVIDERS_RELATIVE_PATH,
    configure_trusted_provider,
    create_formal_verification_from_provider_payload,
    sign_provider_payload,
)
from cognitive_firm.orchestration.runtime_adapters import RuntimeEvent, record_runtime_event


def _logs(root: Path) -> dict[str, Path]:
    return {
        "trusted_transitions": root / "trusted" / "transitions.jsonl",
        "trusted_attestations": root / "trusted" / "action_attestations.jsonl",
        "trusted_formal": root / "trusted" / "formal_verifications.jsonl",
        "trusted_authority": root / "trusted" / "org",
        "missing_transitions": root / "missing" / "transitions.jsonl",
        "missing_attestations": root / "missing" / "action_attestations.jsonl",
        "missing_formal": root / "missing" / "formal_verifications.jsonl",
        "missing_authority": root / "missing" / "org",
        "trusted_payload": root / "trusted" / "leanmill_payload.json",
        "missing_payload": root / "missing" / "leanmill_payload_missing_evidence.json",
    }


def _start_and_complete_run(*, transition_log: Path, external_run_id: str, objective: str) -> str:
    transition_log.parent.mkdir(parents=True, exist_ok=True)
    started = record_runtime_event(
        RuntimeEvent(
            runtime_name="native",
            external_run_id=external_run_id,
            kind="started",
            owner_role="role.release_manager",
            actor="role.release_manager",
            objective=objective,
            tenant_id="tenant-formal-demo",
            project_id="project-provider-attestation",
        ),
        log_path=transition_log,
    )
    run_id = str(started["cognitive_run_id"])
    record_runtime_event(
        RuntimeEvent(
            runtime_name="native",
            external_run_id=external_run_id,
            kind="checkpointed",
            owner_role="role.release_manager",
            actor="role.release_manager",
            step_id="formal-provider-check",
            checkpoint_status="completed",
            summary="recorded provider-backed formal-verification evidence",
            payload_ref=f"formal-provider-demo://{external_run_id}/payload",
        ),
        log_path=transition_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="native",
            external_run_id=external_run_id,
            kind="state_changed",
            owner_role="role.release_manager",
            actor="role.release_manager",
            state="completed",
        ),
        log_path=transition_log,
    )
    return run_id


def _provider_payload(*, run_id: str, include_refs: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
        "provider": "leanmill",
        "formal_system": "lean",
        "verifier_ref": "leanmill:certify-demo@fixture",
        "property_class": "workflow_safety",
        "subject_ref": "workflow://release-review-before-send",
        "subject_digest": digest_text("release workflow requires review before send"),
        "claim_ref": "claim://release-review-before-send",
        "certificate_ref": "leanmill://certificates/release-review-before-send",
        "certificate_digest": digest_text("leanmill checked certificate fixture"),
        "verdict": "verified",
        "verification_summary": "Provider emitted a checked workflow-safety invariant.",
        "run_id": run_id,
        "metadata": {"demo": "formal_provider_bundle"},
    }
    if include_refs:
        payload["faithfulness_refs"] = [
            "leanmill://faithfulness/release-review-before-send",
        ]
        payload["checker_evidence_refs"] = [
            "leanmill://kernel-log/release-review-before-send",
        ]
    return payload


def _write_unconfigured_provider_policy(authority_root: Path) -> None:
    path = authority_root / TRUSTED_FORMAL_VERIFICATION_PROVIDERS_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": FORMAL_VERIFICATION_TRUST_POLICY_VERSION,
                "trusted_providers": [
                    {
                        "provider": "leanmill",
                        "trust_basis": "Fixture policy requiring signed, re-runnable, faithfulness-backed evidence.",
                        "public_key_ref": "configure://leanmill-ed25519-public-key",
                        "requires_payload_signature": True,
                        "requires_reverification_refs": True,
                        "requires_faithfulness_refs": True,
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def run_demo(root: Path) -> dict[str, Any]:
    paths = _logs(root)
    for path in paths.values():
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(parents=True, exist_ok=True)

    keypair = generate_keypair()
    configure_trusted_provider(
        provider="leanmill",
        public_key_pem=keypair.public_pem,
        authority_root=paths["trusted_authority"],
        public_key_ref="leanmill://keys/demo",
        trust_basis="Fixture LeanMill key for formal-provider bundle demo.",
    )
    _write_unconfigured_provider_policy(paths["missing_authority"])

    trusted_run_id = _start_and_complete_run(
        transition_log=paths["trusted_transitions"],
        external_run_id="formal-provider-trusted",
        objective="verify release workflow evidence through a signed provider payload",
    )
    trusted_payload = _provider_payload(run_id=trusted_run_id, include_refs=True)
    trusted_payload["metadata"]["provider_payload_signature"] = sign_provider_payload(
        trusted_payload,
        private_key_pem=keypair.private_pem,
    )
    paths["trusted_payload"].write_text(
        json.dumps(trusted_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    trusted_record = create_formal_verification_from_provider_payload(
        trusted_payload,
        log_path=paths["trusted_formal"],
        action_attestation_log_path=paths["trusted_attestations"],
        authority_root=paths["trusted_authority"],
    )
    trusted_bundle = build_governed_run_attestation_bundle(
        trusted_run_id,
        transition_log_path=paths["trusted_transitions"],
        action_attestation_log_path=paths["trusted_attestations"],
        formal_verification_log_path=paths["trusted_formal"],
        authority_root=paths["trusted_authority"],
    )

    missing_run_id = _start_and_complete_run(
        transition_log=paths["missing_transitions"],
        external_run_id="formal-provider-missing-evidence",
        objective="show provider evidence stays caveated when trust requirements are missing",
    )
    missing_payload = _provider_payload(run_id=missing_run_id, include_refs=False)
    paths["missing_payload"].write_text(
        json.dumps(missing_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    missing_record = create_formal_verification_from_provider_payload(
        missing_payload,
        log_path=paths["missing_formal"],
        action_attestation_log_path=paths["missing_attestations"],
    )
    missing_bundle = build_governed_run_attestation_bundle(
        missing_run_id,
        transition_log_path=paths["missing_transitions"],
        action_attestation_log_path=paths["missing_attestations"],
        formal_verification_log_path=paths["missing_formal"],
        authority_root=paths["missing_authority"],
    )

    trusted_payload_bundle = governed_run_bundle_to_dict(trusted_bundle)
    missing_payload_bundle = governed_run_bundle_to_dict(missing_bundle)
    trusted_validation_errors = validate_governed_run_bundle_payload(trusted_payload_bundle)
    missing_validation_errors = validate_governed_run_bundle_payload(missing_payload_bundle)
    trusted_summary = governed_run_bundle_summary(trusted_bundle)
    missing_summary = governed_run_bundle_summary(missing_bundle)

    return {
        "demo": "formal_provider_bundle",
        "fictional_firm": "Northstar Compliance Lab",
        "no_external_calls": True,
        "trusted_provider": {
            "run_id": trusted_run_id,
            "verification_id": trusted_record.verification_id,
            "bundle_verdict": trusted_bundle.verdict,
            "bundle_caveats": trusted_bundle.caveats,
            "signature_verified": bool(
                trusted_record.metadata.get("provider_payload_signature_verified")
            ),
            "formal_verifications": trusted_summary["counts"]["formal_verifications"],
            "bundle_schema_valid": not trusted_validation_errors,
        },
        "missing_provider_evidence": {
            "run_id": missing_run_id,
            "verification_id": missing_record.verification_id,
            "bundle_verdict": missing_bundle.verdict,
            "bundle_caveats": missing_bundle.caveats,
            "formal_verifications": missing_summary["counts"]["formal_verifications"],
            "bundle_schema_valid": not missing_validation_errors,
        },
        "summary": {
            "trusted_bundle": trusted_bundle.verdict,
            "missing_evidence_bundle": missing_bundle.verdict,
            "trusted_schema_errors": trusted_validation_errors,
            "missing_schema_errors": missing_validation_errors,
            "verdict": "passed"
            if (
                trusted_bundle.verdict == "passed"
                and not trusted_bundle.caveats
                and bool(trusted_record.metadata.get("provider_payload_signature_verified"))
                and missing_bundle.verdict == "incomplete"
                and bool(missing_bundle.caveats)
                and not trusted_validation_errors
                and not missing_validation_errors
            )
            else "failed",
        },
        "log_paths": {name: str(path) for name, path in paths.items()},
    }


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "demo": payload["demo"],
        "fictional_firm": payload["fictional_firm"],
        "no_external_calls": payload["no_external_calls"],
        "trusted_provider": payload["trusted_provider"],
        "missing_provider_evidence": payload["missing_provider_evidence"],
        "summary": payload["summary"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a no-cost formal-provider governed-run bundle demo.",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        help="Optional directory to keep generated fixture logs. Defaults to a temp dir.",
    )
    parser.add_argument(
        "--full-json",
        action="store_true",
        help="Print generated log paths in addition to the compact result.",
    )
    args = parser.parse_args(argv)

    if args.workdir:
        payload = run_demo(args.workdir)
    else:
        with tempfile.TemporaryDirectory(prefix="cf-formal-provider-demo-") as raw:
            payload = run_demo(Path(raw))
    output = payload if args.full_json else _compact(payload)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if payload["summary"]["verdict"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
