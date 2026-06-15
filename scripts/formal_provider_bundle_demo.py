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

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request
from cognitive_firm.distribution.signing import generate_keypair
from cognitive_firm.orchestration.action_attestation import digest_text
from cognitive_firm.orchestration.formal_verification import (
    FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
    FORMAL_VERIFICATION_TRUST_POLICY_VERSION,
    TRUSTED_FORMAL_VERIFICATION_PROVIDERS_RELATIVE_PATH,
    configure_trusted_provider,
    sign_provider_payload,
)


def _assert_status(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{label} failed with status {actual}; expected {expected}")


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


def _service_config(
    *,
    transition_log: Path,
    action_attestation_log: Path,
    formal_verification_log: Path,
    authority_root: Path,
    ingestion_org_dir: Path | None = None,
) -> KernelServiceConfig:
    return KernelServiceConfig(
        project_root=authority_root,
        org_dir=ingestion_org_dir or authority_root,
        transition_log=transition_log,
        action_attestation_log=action_attestation_log,
        formal_verification_log=formal_verification_log,
    )


def _actor_context() -> dict[str, str]:
    return {
        "actor_id": "role.release_manager",
        "actor_kind": "service",
        "role_id": "role.release_manager",
        "surface": "formal_provider_bundle_demo",
    }


def _start_and_complete_run(*, config: KernelServiceConfig, external_run_id: str, objective: str) -> str:
    actor_context = _actor_context()
    started = dispatch_kernel_request(
        "POST",
        "/kernel/runs",
        {
            "owner_role": "role.release_manager",
            "objective": objective,
            "tenant_id": "tenant-formal-demo",
            "project_id": "project-provider-attestation",
            "idempotency_key": f"formal-provider-demo:{external_run_id}",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(started.status, 201, f"{external_run_id} run start")
    run_id = started.payload["run"]["run_id"]
    checkpoint = dispatch_kernel_request(
        "POST",
        f"/kernel/runs/{run_id}/checkpoints",
        {
            "actor": "role.release_manager",
            "step_id": "formal-provider-check",
            "status": "completed",
            "summary": "recorded provider-backed formal-verification evidence",
            "payload_ref": f"formal-provider-demo://{external_run_id}/payload",
            "side_effect_key": f"formal-provider-demo:{external_run_id}:payload",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(checkpoint.status, 201, f"{external_run_id} checkpoint")
    completed = dispatch_kernel_request(
        "POST",
        f"/kernel/runs/{run_id}/state",
        {
            "actor": "role.release_manager",
            "state": "completed",
            "actor_context": actor_context,
        },
        config=config,
    )
    _assert_status(completed.status, 200, f"{external_run_id} run completion")
    return run_id


def _record_provider_payload(
    config: KernelServiceConfig,
    payload: dict[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    response = dispatch_kernel_request(
        "POST",
        "/kernel/formal-verifications/provider-payload",
        {"payload": payload, "actor_context": _actor_context()},
        config=config,
    )
    _assert_status(response.status, 201, f"{label} formal provider payload")
    return response.payload["formal_verification"]


def _build_bundle(config: KernelServiceConfig, run_id: str, *, label: str) -> dict[str, Any]:
    response = dispatch_kernel_request(
        "POST",
        "/kernel/governed-run-bundles/build",
        {"run_id": run_id, "actor_context": _actor_context()},
        config=config,
    )
    _assert_status(response.status, 200, f"{label} governed-run bundle")
    return response.payload


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
    trusted_config = _service_config(
        transition_log=paths["trusted_transitions"],
        action_attestation_log=paths["trusted_attestations"],
        formal_verification_log=paths["trusted_formal"],
        authority_root=paths["trusted_authority"],
    )
    missing_config = _service_config(
        transition_log=paths["missing_transitions"],
        action_attestation_log=paths["missing_attestations"],
        formal_verification_log=paths["missing_formal"],
        authority_root=paths["missing_authority"],
        ingestion_org_dir=paths["missing_authority"].parent / "no_trust_policy_for_ingestion",
    )

    trusted_run_id = _start_and_complete_run(
        config=trusted_config,
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
    trusted_record = _record_provider_payload(
        trusted_config,
        trusted_payload,
        label="trusted",
    )
    trusted_bundle_response = _build_bundle(trusted_config, trusted_run_id, label="trusted")

    missing_run_id = _start_and_complete_run(
        config=missing_config,
        external_run_id="formal-provider-missing-evidence",
        objective="show provider evidence stays caveated when trust requirements are missing",
    )
    missing_payload = _provider_payload(run_id=missing_run_id, include_refs=False)
    paths["missing_payload"].write_text(
        json.dumps(missing_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    missing_record = _record_provider_payload(
        missing_config,
        missing_payload,
        label="missing-evidence",
    )
    missing_bundle_response = _build_bundle(missing_config, missing_run_id, label="missing-evidence")

    trusted_bundle = trusted_bundle_response["bundle"]
    missing_bundle = missing_bundle_response["bundle"]
    trusted_validation_errors = trusted_bundle_response["validation"]["errors"]
    missing_validation_errors = missing_bundle_response["validation"]["errors"]
    trusted_summary = trusted_bundle_response["summary"]
    missing_summary = missing_bundle_response["summary"]

    return {
        "demo": "formal_provider_bundle",
        "fictional_firm": "Northstar Compliance Lab",
        "no_external_calls": True,
        "trusted_provider": {
            "run_id": trusted_run_id,
            "verification_id": trusted_record["verification_id"],
            "bundle_verdict": trusted_bundle["verdict"],
            "bundle_caveats": trusted_bundle["caveats"],
            "signature_verified": bool(
                trusted_record["metadata"].get("provider_payload_signature_verified")
            ),
            "formal_verifications": trusted_summary["counts"]["formal_verifications"],
            "bundle_schema_valid": not trusted_validation_errors,
        },
        "missing_provider_evidence": {
            "run_id": missing_run_id,
            "verification_id": missing_record["verification_id"],
            "bundle_verdict": missing_bundle["verdict"],
            "bundle_caveats": missing_bundle["caveats"],
            "formal_verifications": missing_summary["counts"]["formal_verifications"],
            "bundle_schema_valid": not missing_validation_errors,
        },
        "summary": {
            "trusted_bundle": trusted_bundle["verdict"],
            "missing_evidence_bundle": missing_bundle["verdict"],
            "trusted_schema_errors": trusted_validation_errors,
            "missing_schema_errors": missing_validation_errors,
            "verdict": "passed"
            if (
                trusted_bundle["verdict"] == "passed"
                and not trusted_bundle["caveats"]
                and bool(trusted_record["metadata"].get("provider_payload_signature_verified"))
                and missing_bundle["verdict"] == "incomplete"
                and bool(missing_bundle["caveats"])
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
