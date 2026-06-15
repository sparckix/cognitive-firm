"""Formal verification records for proof/certificate-backed checks.

This primitive records the result of an external formal checker: Lean, SMT,
Isabelle, Coq, Alloy, TLA+, or another tenant-supplied verifier. The kernel
does not run the checker here. It records the certificate, verdict, subject,
assumptions, and optional action-attestation bridge so a governed run can
surface formal evidence alongside ordinary provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.distribution.signing import (
    SigningError,
    sign_message,
    validate_public_key,
    verify_message_signature,
)
from cognitive_firm.orchestration.action_attestation import (
    ActionAttestation,
    create_action_attestation,
)


FormalSystem = Literal["lean", "smt", "isabelle", "coq", "alloy", "tla", "other"]
FormalVerificationVerdict = Literal["verified", "refuted", "inconclusive", "invalid"]
FormalPropertyClass = Literal[
    "policy",
    "schema",
    "contract",
    "evidence_chain",
    "workflow_safety",
    "math",
    "other",
]

VALID_FORMAL_SYSTEMS = {"lean", "smt", "isabelle", "coq", "alloy", "tla", "other"}
VALID_VERDICTS = {"verified", "refuted", "inconclusive", "invalid"}
VALID_PROPERTY_CLASSES = {
    "policy",
    "schema",
    "contract",
    "evidence_chain",
    "workflow_safety",
    "math",
    "other",
}

DEFAULT_FORMAL_VERIFICATION_LOG = ORG_ROOT_DIR / "attestations" / "formal_verifications.jsonl"
FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION = "formal-verification-provider/v1"
FORMAL_VERIFICATION_TRUST_POLICY_VERSION = "formal-verification-trust/v1"
TRUSTED_FORMAL_VERIFICATION_PROVIDERS_RELATIVE_PATH = Path(
    "formal_verification/trusted_providers.json"
)
PROVIDER_PAYLOAD_SIGNATURE_KEY = "provider_payload_signature"
PROVIDER_PAYLOAD_SIGNATURE_VERIFIED_KEY = "provider_payload_signature_verified"
PROVIDER_PAYLOAD_DIGEST_KEY = "provider_payload_digest"
PROVIDER_PAYLOAD_SIGNATURE_KEY_REF = "provider_payload_signature_key_ref"
_SIGNATURE_METADATA_KEYS = {
    PROVIDER_PAYLOAD_SIGNATURE_KEY,
    PROVIDER_PAYLOAD_SIGNATURE_VERIFIED_KEY,
    PROVIDER_PAYLOAD_DIGEST_KEY,
    PROVIDER_PAYLOAD_SIGNATURE_KEY_REF,
}


def formal_verification_trust_policy_path(authority_root: Path | None = None) -> Path:
    root = Path(authority_root) if authority_root is not None else ORG_ROOT_DIR
    return root / TRUSTED_FORMAL_VERIFICATION_PROVIDERS_RELATIVE_PATH


def _load_trust_policy_document(authority_root: Path | None = None) -> dict[str, Any]:
    path = formal_verification_trust_policy_path(authority_root)
    if not path.exists():
        return {
            "schema_version": FORMAL_VERIFICATION_TRUST_POLICY_VERSION,
            "trusted_providers": [],
        }
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"trust policy must be a JSON object: {path}")
    schema_version = raw.get("schema_version")
    if schema_version != FORMAL_VERIFICATION_TRUST_POLICY_VERSION:
        raise ValueError(
            "unsupported formal-verification trust policy "
            f"{schema_version!r}; expected {FORMAL_VERIFICATION_TRUST_POLICY_VERSION!r}"
        )
    entries = raw.get("trusted_providers")
    if not isinstance(entries, list):
        raise ValueError("trusted_providers must be a list")
    return raw


def write_formal_verification_trust_policy(
    policy: dict[str, Any],
    *,
    authority_root: Path | None = None,
) -> Path:
    path = formal_verification_trust_policy_path(authority_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def validate_formal_verification_trust_policy_file(
    path: Path,
    *,
    allow_key_ref_placeholder: bool = True,
) -> list[str]:
    """Return structural issues for a formal-verification trust-policy file.

    Package overlays may ship a provider entry with ``public_key_ref`` but no
    concrete ``public_key_pem``; the actual key is configured in the target org
    after install. Runtime bundle checks still require the concrete key before a
    signed provider row counts as clean evidence.
    """
    path = Path(path)
    if not path.is_file():
        return [f"trust policy not found: {path}"]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"cannot parse trust policy {path}: {exc}"]
    if not isinstance(raw, dict):
        return ["trust policy must be a JSON object"]

    issues: list[str] = []
    schema_version = raw.get("schema_version")
    if schema_version != FORMAL_VERIFICATION_TRUST_POLICY_VERSION:
        issues.append(
            f"schema_version {schema_version!r} != "
            f"{FORMAL_VERIFICATION_TRUST_POLICY_VERSION!r}"
        )
    entries = raw.get("trusted_providers")
    if not isinstance(entries, list):
        return issues + ["trusted_providers must be a list"]

    seen: set[str] = set()
    for index, entry in enumerate(entries):
        label = f"trusted_providers[{index}]"
        if not isinstance(entry, dict):
            issues.append(f"{label} must be a JSON object")
            continue
        provider = entry.get("provider")
        if not isinstance(provider, str) or not provider.strip():
            issues.append(f"{label}.provider is required")
        else:
            normalized = provider.strip().lower()
            if normalized in seen:
                issues.append(f"duplicate provider: {normalized}")
            seen.add(normalized)

        for key in (
            "requires_payload_signature",
            "requires_reverification_refs",
            "requires_faithfulness_refs",
        ):
            if key in entry and not isinstance(entry[key], bool):
                issues.append(f"{label}.{key} must be a boolean")

        public_key_pem = entry.get("public_key_pem")
        public_key_ref = entry.get("public_key_ref")
        if public_key_pem is not None:
            if not isinstance(public_key_pem, str) or not public_key_pem.strip():
                issues.append(f"{label}.public_key_pem must be non-empty when provided")
            else:
                try:
                    validate_public_key(public_key_pem)
                except SigningError as exc:
                    issues.append(f"{label}.public_key_pem is invalid: {exc}")
        if public_key_ref is not None and (
            not isinstance(public_key_ref, str) or not public_key_ref.strip()
        ):
            issues.append(f"{label}.public_key_ref must be non-empty when provided")

        if entry.get("requires_payload_signature"):
            has_key = isinstance(public_key_pem, str) and bool(public_key_pem.strip())
            has_ref = isinstance(public_key_ref, str) and bool(public_key_ref.strip())
            if not has_key and not (allow_key_ref_placeholder and has_ref):
                issues.append(
                    f"{label} requires payload signatures but has no public key "
                    "or public key ref"
                )
    return issues


def configure_trusted_provider(
    *,
    provider: str,
    public_key_pem: str,
    authority_root: Path | None = None,
    public_key_ref: str | None = None,
    trust_basis: str | None = None,
    requires_payload_signature: bool = True,
    requires_reverification_refs: bool = True,
    requires_faithfulness_refs: bool = True,
) -> dict[str, Any]:
    """Add or update one trusted formal-verification provider policy entry."""
    normalized = provider.strip().lower()
    if not normalized:
        raise ValueError("provider is required")
    try:
        validate_public_key(public_key_pem)
    except SigningError as exc:
        raise ValueError(str(exc)) from exc

    policy = _load_trust_policy_document(authority_root)
    entries = policy["trusted_providers"]
    entry = {
        "provider": normalized,
        "trust_basis": trust_basis
        or f"Configured {normalized} Ed25519 provider key for formal verification.",
        "public_key_pem": public_key_pem if public_key_pem.endswith("\n") else public_key_pem + "\n",
        "public_key_ref": public_key_ref or f"configured://{normalized}-ed25519-public-key",
        "requires_payload_signature": requires_payload_signature,
        "requires_reverification_refs": requires_reverification_refs,
        "requires_faithfulness_refs": requires_faithfulness_refs,
    }
    replaced = False
    for index, existing in enumerate(entries):
        if not isinstance(existing, dict):
            raise ValueError("trusted_providers entries must be JSON objects")
        existing_provider = str(existing.get("provider") or "").strip().lower()
        if existing_provider == normalized:
            merged = {**existing, **entry}
            entries[index] = merged
            entry = merged
            replaced = True
            break
    if not replaced:
        entries.append(entry)
    write_formal_verification_trust_policy(policy, authority_root=authority_root)
    return entry


def load_formal_verification_trust_policy(
    authority_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Load org-installed trusted provider entries.

    Trust is org configuration. A package can install this file, but the kernel
    does not import provider code or special-case a checker implementation.
    """
    path = formal_verification_trust_policy_path(authority_root)
    if not path.exists():
        return []
    raw = _load_trust_policy_document(authority_root)
    entries = raw["trusted_providers"]
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("trusted_providers entries must be JSON objects")
        provider = entry.get("provider")
        if not isinstance(provider, str) or not provider.strip():
            raise ValueError("trusted provider entry is missing provider")
        normalized.append({**entry, "provider": provider.strip().lower()})
    return normalized


def trusted_provider_entry(
    provider: str,
    *,
    extra_trusted: set[str] | None = None,
    authority_root: Path | None = None,
) -> dict[str, Any] | None:
    normalized = provider.strip().lower()
    if not normalized:
        return None
    for entry in load_formal_verification_trust_policy(authority_root):
        if entry.get("provider") == normalized:
            return entry
    if extra_trusted and normalized in {
        item.strip().lower() for item in extra_trusted if item.strip()
    }:
        return {
            "provider": normalized,
            "trust_basis": "export-time override",
            "requires_payload_signature": False,
            "requires_reverification_refs": False,
            "requires_faithfulness_refs": False,
        }
    return None


def is_trusted_provider(
    provider: str,
    *,
    extra_trusted: set[str] | None = None,
    authority_root: Path | None = None,
) -> bool:
    """Return whether a provider id is recognized by installed org policy.

    This is a provider-identity policy hook, not a cryptographic proof. A trust
    policy may require signed and re-runnable provider evidence; bundle export
    checks those requirements when evaluating a verified row.
    """
    return (
        trusted_provider_entry(
            provider,
            extra_trusted=extra_trusted,
            authority_root=authority_root,
        )
        is not None
    )


def canonical_provider_payload_bytes(
    payload: FormalVerificationProviderPayload | dict[str, Any],
) -> bytes:
    """Return canonical bytes for provider-payload signing.

    The provider signature covers the normalized payload, excluding signature
    bookkeeping stored in ``metadata``. Adapters should sign these bytes before
    adding ``metadata.provider_payload_signature``.
    """
    provider_payload = (
        provider_payload_from_dict(payload) if isinstance(payload, dict) else payload
    )
    raw = provider_payload.as_dict()
    metadata = raw.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object")
    raw["metadata"] = {
        key: value
        for key, value in metadata.items()
        if key not in _SIGNATURE_METADATA_KEYS
    }
    return json.dumps(
        raw,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def provider_payload_digest(
    payload: FormalVerificationProviderPayload | dict[str, Any],
) -> str:
    return "sha256:" + hashlib.sha256(canonical_provider_payload_bytes(payload)).hexdigest()


def sign_provider_payload(
    payload: FormalVerificationProviderPayload | dict[str, Any],
    *,
    private_key_pem: str,
) -> str:
    """Return an Ed25519 signature for a canonical provider payload."""
    return "ed25519:" + sign_message(
        canonical_provider_payload_bytes(payload),
        private_key_pem,
    )


def _provider_signature_hex(signature: str) -> str:
    raw = signature.strip()
    if raw.startswith("ed25519:"):
        raw = raw.split(":", 1)[1]
    if not raw:
        raise ValueError("provider_payload_signature is empty")
    return raw


def verify_provider_payload_signature(
    payload: FormalVerificationProviderPayload | dict[str, Any],
    *,
    trusted_provider: dict[str, Any],
) -> bool:
    """Verify a provider payload against one trusted-provider policy entry."""
    provider_payload = (
        provider_payload_from_dict(payload) if isinstance(payload, dict) else payload
    )
    metadata = provider_payload.metadata
    signature = metadata.get(PROVIDER_PAYLOAD_SIGNATURE_KEY)
    if not isinstance(signature, str) or not signature.strip():
        raise ValueError("provider_payload_signature is required")
    public_key_pem = trusted_provider.get("public_key_pem")
    if not isinstance(public_key_pem, str) or not public_key_pem.strip():
        raise ValueError("trusted provider policy is missing public_key_pem")
    try:
        return verify_message_signature(
            canonical_provider_payload_bytes(provider_payload),
            _provider_signature_hex(signature),
            public_key_pem,
        )
    except SigningError as exc:
        raise ValueError(str(exc)) from exc


def validate_provider_payload_contract(
    payload: dict[str, Any],
    *,
    authority_root: Path | None = None,
    require_trusted_provider: bool = False,
) -> dict[str, Any]:
    """Validate a provider payload without recording kernel state.

    This is the adapter-facing contract check for external formal checkers. It
    confirms the payload can be parsed, reports the canonical digest the kernel
    will record, and, when org policy is supplied, checks the provider trust
    requirements that determine whether a verified row can later count as clean
    governed-run evidence.
    """
    issues: list[str] = []
    try:
        provider_payload = provider_payload_from_dict(payload)
    except ValueError as exc:
        return {
            "ok": False,
            "issues": [str(exc)],
            "provider": None,
            "schema_version": None,
            "provider_payload_digest": None,
            "trusted_provider": False,
            "signature_status": "not_checked",
            "authority_root": str(authority_root) if authority_root is not None else None,
        }

    digest = provider_payload_digest(provider_payload)
    trusted_entry: dict[str, Any] | None = None
    if authority_root is not None:
        try:
            trusted_entry = trusted_provider_entry(
                provider_payload.provider,
                authority_root=authority_root,
            )
        except ValueError as exc:
            issues.append(str(exc))
    trusted = trusted_entry is not None
    if require_trusted_provider and not trusted:
        issues.append(
            f"provider {provider_payload.provider!r} is not trusted by the supplied authority_root"
        )

    signature = provider_payload.metadata.get(PROVIDER_PAYLOAD_SIGNATURE_KEY)
    signature_status = "not_required"
    if trusted_entry is None:
        if signature is not None:
            signature_status = "present_not_verified_without_trust_policy"
    else:
        requires_signature = bool(trusted_entry.get("requires_payload_signature"))
        if requires_signature or signature is not None:
            try:
                signature_verified = verify_provider_payload_signature(
                    provider_payload,
                    trusted_provider=trusted_entry,
                )
            except ValueError as exc:
                signature_status = "failed"
                issues.append(str(exc))
            else:
                signature_status = "verified" if signature_verified else "failed"
                if not signature_verified:
                    issues.append("provider_payload_signature did not verify")
        if (
            trusted_entry.get("requires_reverification_refs")
            and not provider_payload.checker_evidence_refs
        ):
            issues.append("checker_evidence_refs are required by trusted provider policy")
        if (
            trusted_entry.get("requires_faithfulness_refs")
            and not provider_payload.faithfulness_refs
        ):
            issues.append("faithfulness_refs are required by trusted provider policy")

    return {
        "ok": not issues,
        "issues": issues,
        "provider": provider_payload.provider,
        "schema_version": provider_payload.schema_version,
        "formal_system": provider_payload.formal_system,
        "property_class": provider_payload.property_class,
        "verdict": provider_payload.verdict,
        "subject_ref": provider_payload.subject_ref,
        "claim_ref": provider_payload.claim_ref,
        "certificate_ref": provider_payload.certificate_ref,
        "provider_payload_digest": digest,
        "trusted_provider": trusted,
        "signature_status": signature_status,
        "authority_root": str(authority_root) if authority_root is not None else None,
        "trust_requirements": {
            "requires_payload_signature": bool(
                trusted_entry.get("requires_payload_signature") if trusted_entry else False
            ),
            "requires_reverification_refs": bool(
                trusted_entry.get("requires_reverification_refs") if trusted_entry else False
            ),
            "requires_faithfulness_refs": bool(
                trusted_entry.get("requires_faithfulness_refs") if trusted_entry else False
            ),
        },
        "evidence": {
            "faithfulness_refs": list(provider_payload.faithfulness_refs),
            "checker_evidence_refs": list(provider_payload.checker_evidence_refs),
            "has_counterexample_ref": provider_payload.counterexample_ref is not None,
        },
    }


@dataclass(frozen=True)
class FormalVerification:
    verification_id: str
    created_at_utc: str
    formal_system: FormalSystem
    verifier_ref: str
    property_class: FormalPropertyClass
    subject_ref: str
    subject_digest: str
    claim_ref: str
    certificate_ref: str
    certificate_digest: str
    verdict: FormalVerificationVerdict
    verification_summary: str
    assumption_refs: list[str] = field(default_factory=list)
    input_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    counterexample_ref: str | None = None
    action_attestation_id: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FormalVerificationProviderPayload:
    """Provider-neutral payload accepted from an external checker adapter."""

    schema_version: str
    provider: str
    formal_system: FormalSystem
    verifier_ref: str
    property_class: FormalPropertyClass
    subject_ref: str
    subject_digest: str
    claim_ref: str
    certificate_ref: str
    certificate_digest: str
    verdict: FormalVerificationVerdict
    verification_summary: str
    assumption_refs: list[str] = field(default_factory=list)
    input_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    faithfulness_refs: list[str] = field(default_factory=list)
    checker_evidence_refs: list[str] = field(default_factory=list)
    counterexample_ref: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate(value: str, allowed: set[str], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"invalid {label} {value!r}; expected one of {sorted(allowed)}")
    return value


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _optional_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string when provided")
    return value


def _string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    if any(not item.strip() for item in value):
        raise ValueError(f"{key} must not contain blank strings")
    return list(value)


def provider_payload_from_dict(payload: dict[str, Any]) -> FormalVerificationProviderPayload:
    """Validate and normalize a provider-neutral formal-verification payload."""
    if not isinstance(payload, dict):
        raise ValueError("provider payload must be a JSON object")

    schema_version = _require_text(payload, "schema_version")
    if schema_version != FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION:
        raise ValueError(
            "unsupported schema_version "
            f"{schema_version!r}; expected {FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION!r}"
        )

    provider = _require_text(payload, "provider")
    formal_system = _validate(
        _require_text(payload, "formal_system"),
        VALID_FORMAL_SYSTEMS,
        "formal_system",
    )
    property_class = _validate(
        _require_text(payload, "property_class"),
        VALID_PROPERTY_CLASSES,
        "property_class",
    )
    verdict = _validate(_require_text(payload, "verdict"), VALID_VERDICTS, "verdict")
    counterexample_ref = _optional_text(payload, "counterexample_ref")
    if verdict == "refuted" and counterexample_ref is None:
        raise ValueError("counterexample_ref is required when verdict is refuted")
    if verdict == "verified" and counterexample_ref is not None:
        raise ValueError("counterexample_ref must be omitted when verdict is verified")

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object")

    return FormalVerificationProviderPayload(
        schema_version=schema_version,
        provider=provider,
        formal_system=formal_system,  # type: ignore[arg-type]
        verifier_ref=_require_text(payload, "verifier_ref"),
        property_class=property_class,  # type: ignore[arg-type]
        subject_ref=_require_text(payload, "subject_ref"),
        subject_digest=_require_text(payload, "subject_digest"),
        claim_ref=_require_text(payload, "claim_ref"),
        certificate_ref=_require_text(payload, "certificate_ref"),
        certificate_digest=_require_text(payload, "certificate_digest"),
        verdict=verdict,  # type: ignore[arg-type]
        verification_summary=_require_text(payload, "verification_summary"),
        assumption_refs=_string_list(payload, "assumption_refs"),
        input_refs=_string_list(payload, "input_refs"),
        output_refs=_string_list(payload, "output_refs"),
        faithfulness_refs=_string_list(payload, "faithfulness_refs"),
        checker_evidence_refs=_string_list(payload, "checker_evidence_refs"),
        counterexample_ref=counterexample_ref,
        tenant_id=_optional_text(payload, "tenant_id"),
        project_id=_optional_text(payload, "project_id"),
        run_id=_optional_text(payload, "run_id"),
        metadata=dict(metadata),
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _attestation_status(verdict: str) -> str:
    if verdict == "verified":
        return "verified"
    if verdict in {"refuted", "invalid"}:
        return "failed"
    return "unverified"


def create_formal_verification(
    *,
    formal_system: FormalSystem | str,
    verifier_ref: str,
    property_class: FormalPropertyClass | str,
    subject_ref: str,
    subject_digest: str,
    claim_ref: str,
    certificate_ref: str,
    certificate_digest: str,
    verdict: FormalVerificationVerdict | str,
    verification_summary: str,
    assumption_refs: list[str] | None = None,
    input_refs: list[str] | None = None,
    output_refs: list[str] | None = None,
    counterexample_ref: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    verification_id: str | None = None,
    log_path: Path | None = None,
    action_attestation_log_path: Path | None = None,
    create_attestation: bool = True,
) -> FormalVerification:
    """Record a formal checker verdict and optionally bridge to action attestation."""
    for label, value in {
        "verifier_ref": verifier_ref,
        "subject_ref": subject_ref,
        "subject_digest": subject_digest,
        "claim_ref": claim_ref,
        "certificate_ref": certificate_ref,
        "certificate_digest": certificate_digest,
        "verification_summary": verification_summary,
    }.items():
        if not value.strip():
            raise ValueError(f"{label} is required")

    checked_system = _validate(str(formal_system), VALID_FORMAL_SYSTEMS, "formal_system")
    checked_verdict = _validate(str(verdict), VALID_VERDICTS, "verdict")
    checked_property_class = _validate(
        str(property_class),
        VALID_PROPERTY_CLASSES,
        "property_class",
    )

    action_attestation: ActionAttestation | None = None
    if create_attestation:
        action_attestation = create_action_attestation(
            subject_kind="artifact",
            subject_ref=subject_ref,
            subject_digest=subject_digest,
            producer=verifier_ref,
            action_type="formal_verification",
            runtime_ref=f"formal:{checked_system}",
            tool_ref=verifier_ref,
            input_refs=input_refs or [],
            output_refs=list(dict.fromkeys((output_refs or []) + [certificate_ref])),
            signature_ref=certificate_ref,
            transparency_ref=certificate_digest,
            verification_status=_attestation_status(checked_verdict),
            verification_summary=verification_summary,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            metadata={
                "formal_verification_verdict": checked_verdict,
                "formal_system": checked_system,
                "property_class": checked_property_class,
                "claim_ref": claim_ref,
                "certificate_ref": certificate_ref,
                **(metadata or {}),
            },
            log_path=action_attestation_log_path,
        )

    record = FormalVerification(
        verification_id=verification_id or f"fver_{uuid.uuid4().hex[:12]}",
        created_at_utc=_now_iso(),
        formal_system=checked_system,  # type: ignore[arg-type]
        verifier_ref=verifier_ref,
        property_class=checked_property_class,  # type: ignore[arg-type]
        subject_ref=subject_ref,
        subject_digest=subject_digest,
        claim_ref=claim_ref,
        certificate_ref=certificate_ref,
        certificate_digest=certificate_digest,
        verdict=checked_verdict,  # type: ignore[arg-type]
        verification_summary=verification_summary,
        assumption_refs=assumption_refs or [],
        input_refs=input_refs or [],
        output_refs=output_refs or [],
        counterexample_ref=counterexample_ref,
        action_attestation_id=(
            action_attestation.attestation_id if action_attestation is not None else None
        ),
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=run_id,
        metadata=metadata or {},
    )
    _append_jsonl(log_path or DEFAULT_FORMAL_VERIFICATION_LOG, asdict(record))
    return record


def create_formal_verification_from_provider_payload(
    payload: FormalVerificationProviderPayload | dict[str, Any],
    *,
    log_path: Path | None = None,
    action_attestation_log_path: Path | None = None,
    create_attestation: bool = True,
    authority_root: Path | None = None,
) -> FormalVerification:
    """Create a formal-verification row from a provider-neutral payload.

    Providers keep their own checker internals. This function only accepts the
    normalized certificate evidence the kernel needs to record and bundle.
    """
    provider_payload = (
        provider_payload_from_dict(payload) if isinstance(payload, dict) else payload
    )
    signature_verified = False
    trusted_entry = trusted_provider_entry(
        provider_payload.provider,
        authority_root=authority_root,
    )
    signature = provider_payload.metadata.get(PROVIDER_PAYLOAD_SIGNATURE_KEY)
    if trusted_entry is not None and (
        trusted_entry.get("requires_payload_signature") or signature
    ):
        signature_verified = verify_provider_payload_signature(
            provider_payload,
            trusted_provider=trusted_entry,
        )
        if not signature_verified:
            raise ValueError("provider_payload_signature did not verify")

    metadata = {
        **provider_payload.metadata,
        "provider": provider_payload.provider,
        "provider_payload_schema": provider_payload.schema_version,
        PROVIDER_PAYLOAD_DIGEST_KEY: provider_payload_digest(provider_payload),
        "faithfulness_refs": provider_payload.faithfulness_refs,
        "checker_evidence_refs": provider_payload.checker_evidence_refs,
    }
    if signature is not None:
        metadata[PROVIDER_PAYLOAD_SIGNATURE_VERIFIED_KEY] = signature_verified
        if trusted_entry is not None and trusted_entry.get("public_key_ref"):
            metadata[PROVIDER_PAYLOAD_SIGNATURE_KEY_REF] = trusted_entry["public_key_ref"]
    return create_formal_verification(
        formal_system=provider_payload.formal_system,
        verifier_ref=provider_payload.verifier_ref,
        property_class=provider_payload.property_class,
        subject_ref=provider_payload.subject_ref,
        subject_digest=provider_payload.subject_digest,
        claim_ref=provider_payload.claim_ref,
        certificate_ref=provider_payload.certificate_ref,
        certificate_digest=provider_payload.certificate_digest,
        verdict=provider_payload.verdict,
        verification_summary=provider_payload.verification_summary,
        assumption_refs=provider_payload.assumption_refs,
        input_refs=list(
            dict.fromkeys(provider_payload.input_refs + provider_payload.faithfulness_refs)
        ),
        output_refs=list(
            dict.fromkeys(
                provider_payload.output_refs + provider_payload.checker_evidence_refs
            )
        ),
        counterexample_ref=provider_payload.counterexample_ref,
        tenant_id=provider_payload.tenant_id,
        project_id=provider_payload.project_id,
        run_id=provider_payload.run_id,
        metadata=metadata,
        log_path=log_path,
        action_attestation_log_path=action_attestation_log_path,
        create_attestation=create_attestation,
    )


def list_formal_verifications(
    *,
    formal_system: FormalSystem | str | None = None,
    verdict: FormalVerificationVerdict | str | None = None,
    property_class: FormalPropertyClass | str | None = None,
    subject_ref: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    log_path: Path | None = None,
) -> list[FormalVerification]:
    if formal_system is not None:
        formal_system = _validate(str(formal_system), VALID_FORMAL_SYSTEMS, "formal_system")
    if verdict is not None:
        verdict = _validate(str(verdict), VALID_VERDICTS, "verdict")
    if property_class is not None:
        property_class = _validate(
            str(property_class),
            VALID_PROPERTY_CLASSES,
            "property_class",
        )

    out: list[FormalVerification] = []
    for row in _read_jsonl(log_path or DEFAULT_FORMAL_VERIFICATION_LOG):
        record = FormalVerification(**row)
        if formal_system is not None and record.formal_system != formal_system:
            continue
        if verdict is not None and record.verdict != verdict:
            continue
        if property_class is not None and record.property_class != property_class:
            continue
        if subject_ref is not None and record.subject_ref != subject_ref:
            continue
        if tenant_id is not None and record.tenant_id != tenant_id:
            continue
        if project_id is not None and record.project_id != project_id:
            continue
        if run_id is not None and record.run_id != run_id:
            continue
        out.append(record)
    return out


def formal_verification_summary(record: FormalVerification) -> dict[str, Any]:
    return asdict(record)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage formal verification records.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--formal-system")
    list_parser.add_argument("--verdict")
    list_parser.add_argument("--property-class")
    list_parser.add_argument("--subject-ref")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--run-id")
    list_parser.add_argument("--log-path", type=Path)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--formal-system", required=True)
    create_parser.add_argument("--verifier-ref", required=True)
    create_parser.add_argument("--property-class", required=True)
    create_parser.add_argument("--subject-ref", required=True)
    create_parser.add_argument("--subject-digest", required=True)
    create_parser.add_argument("--claim-ref", required=True)
    create_parser.add_argument("--certificate-ref", required=True)
    create_parser.add_argument("--certificate-digest", required=True)
    create_parser.add_argument("--verdict", required=True)
    create_parser.add_argument("--verification-summary", required=True)
    create_parser.add_argument("--assumption-ref", action="append", default=[])
    create_parser.add_argument("--input-ref", action="append", default=[])
    create_parser.add_argument("--output-ref", action="append", default=[])
    create_parser.add_argument("--counterexample-ref")
    create_parser.add_argument("--tenant-id")
    create_parser.add_argument("--project-id")
    create_parser.add_argument("--run-id")
    create_parser.add_argument("--metadata-json", default="{}")
    create_parser.add_argument("--verification-id")
    create_parser.add_argument("--log-path", type=Path)
    create_parser.add_argument("--action-attestation-log-path", type=Path)
    create_parser.add_argument("--no-action-attestation", action="store_true")

    provider_parser = sub.add_parser("create-from-provider-payload")
    provider_parser.add_argument("--payload-json", required=True, type=Path)
    provider_parser.add_argument("--log-path", type=Path)
    provider_parser.add_argument("--action-attestation-log-path", type=Path)
    provider_parser.add_argument(
        "--authority-root",
        type=Path,
        help="Org root containing formal_verification/trusted_providers.json.",
    )
    provider_parser.add_argument("--no-action-attestation", action="store_true")

    validate_provider_parser = sub.add_parser("validate-provider-payload")
    validate_provider_parser.add_argument("--payload-json", required=True, type=Path)
    validate_provider_parser.add_argument(
        "--authority-root",
        type=Path,
        help="Org root containing formal_verification/trusted_providers.json.",
    )
    validate_provider_parser.add_argument(
        "--require-trusted-provider",
        action="store_true",
        help="Fail unless the payload provider is trusted by the supplied authority root.",
    )

    trust_parser = sub.add_parser("trust-provider")
    trust_parser.add_argument("--provider", required=True)
    trust_parser.add_argument(
        "--authority-root",
        type=Path,
        default=ORG_ROOT_DIR,
        help="Org root containing formal_verification/trusted_providers.json.",
    )
    key_source = trust_parser.add_mutually_exclusive_group(required=True)
    key_source.add_argument("--public-key-file", type=Path)
    key_source.add_argument("--public-key-pem")
    trust_parser.add_argument("--public-key-ref")
    trust_parser.add_argument("--trust-basis")
    trust_parser.add_argument(
        "--allow-unsigned-payloads",
        action="store_true",
        help="Do not require provider_payload_signature_verified for this provider.",
    )
    trust_parser.add_argument(
        "--allow-missing-reverification-refs",
        action="store_true",
        help="Do not require checker_evidence_refs for this provider.",
    )
    trust_parser.add_argument(
        "--allow-missing-faithfulness-refs",
        action="store_true",
        help="Do not require faithfulness_refs for this provider.",
    )

    args = parser.parse_args(argv)
    if args.cmd == "list":
        records = list_formal_verifications(
            formal_system=args.formal_system,
            verdict=args.verdict,
            property_class=args.property_class,
            subject_ref=args.subject_ref,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            run_id=args.run_id,
            log_path=args.log_path,
        )
        print(json.dumps([record.as_dict() for record in records], indent=2, sort_keys=True))
    elif args.cmd == "create":
        metadata = json.loads(args.metadata_json)
        if not isinstance(metadata, dict):
            raise SystemExit("--metadata-json must decode to an object")
        record = create_formal_verification(
            formal_system=args.formal_system,
            verifier_ref=args.verifier_ref,
            property_class=args.property_class,
            subject_ref=args.subject_ref,
            subject_digest=args.subject_digest,
            claim_ref=args.claim_ref,
            certificate_ref=args.certificate_ref,
            certificate_digest=args.certificate_digest,
            verdict=args.verdict,
            verification_summary=args.verification_summary,
            assumption_refs=args.assumption_ref,
            input_refs=args.input_ref,
            output_refs=args.output_ref,
            counterexample_ref=args.counterexample_ref,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            run_id=args.run_id,
            metadata=metadata,
            verification_id=args.verification_id,
            log_path=args.log_path,
            action_attestation_log_path=args.action_attestation_log_path,
            create_attestation=not args.no_action_attestation,
        )
        print(json.dumps(record.as_dict(), indent=2, sort_keys=True))
    elif args.cmd == "create-from-provider-payload":
        with args.payload_json.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        try:
            record = create_formal_verification_from_provider_payload(
                payload,
                log_path=args.log_path,
                action_attestation_log_path=args.action_attestation_log_path,
                create_attestation=not args.no_action_attestation,
                authority_root=args.authority_root,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps(record.as_dict(), indent=2, sort_keys=True))
    elif args.cmd == "validate-provider-payload":
        with args.payload_json.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        result = validate_provider_payload_contract(
            payload,
            authority_root=args.authority_root,
            require_trusted_provider=args.require_trusted_provider,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        if not result["ok"]:
            return 2
    elif args.cmd == "trust-provider":
        public_key_pem = (
            args.public_key_file.read_text(encoding="utf-8")
            if args.public_key_file is not None
            else args.public_key_pem
        )
        try:
            entry = configure_trusted_provider(
                provider=args.provider,
                public_key_pem=public_key_pem,
                authority_root=args.authority_root,
                public_key_ref=args.public_key_ref,
                trust_basis=args.trust_basis,
                requires_payload_signature=not args.allow_unsigned_payloads,
                requires_reverification_refs=not args.allow_missing_reverification_refs,
                requires_faithfulness_refs=not args.allow_missing_faithfulness_refs,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps(entry, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
