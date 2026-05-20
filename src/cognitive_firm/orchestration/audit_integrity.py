"""Tamper-evident audit-chain manifests for JSONL state logs.

This is the lean T2 audit step: produce and verify a chained manifest over a
kernel JSONL log. It does not replace enterprise signing or timestamping, but
it gives adopters a concrete integrity check before those services are wired.
"""

from __future__ import annotations

import argparse
import hmac
import json
import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AUDIT_MANIFEST_SCHEMA_VERSION = 1
SIGNATURE_ALGORITHM = "hmac-sha256"


@dataclass(frozen=True)
class AuditChainEntry:
    index: int
    event_id: str | None
    row_digest: str
    previous_chain_digest: str | None
    chain_digest: str
    signature: str | None = None
    signature_algorithm: str | None = None


@dataclass(frozen=True)
class AuditManifest:
    schema_version: int
    created_at_utc: str
    source_ref: str
    source_row_count: int
    entries: list[AuditChainEntry] = field(default_factory=list)
    external_timestamps: list["ExternalTimestampReference"] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        return out


@dataclass(frozen=True)
class AuditVerificationResult:
    valid: bool
    checked_rows: int
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ExternalTimestampReference:
    provider_id: str
    root_digest: str
    timestamped_at_utc: str
    proof_ref: str
    proof_digest: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hex_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def row_digest(row: dict[str, Any]) -> str:
    return _hex_digest(_canonical_json(row))


def chain_digest(row_hash: str, previous_chain_digest: str | None) -> str:
    body = {
        "previous_chain_digest": previous_chain_digest,
        "row_digest": row_hash,
    }
    return _hex_digest(_canonical_json(body))


def sign_chain_digest(value: str, signing_key: str) -> str:
    signature = hmac.new(signing_key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256)
    return "hmac-sha256:" + signature.hexdigest()


def build_audit_manifest(
    rows: list[dict[str, Any]],
    *,
    source_ref: str,
    signing_key: str | None = None,
    external_timestamps: list[ExternalTimestampReference] | None = None,
) -> AuditManifest:
    entries: list[AuditChainEntry] = []
    previous: str | None = None
    for index, row in enumerate(rows):
        digest = row_digest(row)
        chained = chain_digest(digest, previous)
        signature = sign_chain_digest(chained, signing_key) if signing_key else None
        entries.append(
            AuditChainEntry(
                index=index,
                event_id=str(row.get("event_id")) if row.get("event_id") else None,
                row_digest=digest,
                previous_chain_digest=previous,
                chain_digest=chained,
                signature=signature,
                signature_algorithm=SIGNATURE_ALGORITHM if signature else None,
            )
        )
        previous = chained
    return AuditManifest(
        schema_version=AUDIT_MANIFEST_SCHEMA_VERSION,
        created_at_utc=_now_iso(),
        source_ref=source_ref,
        source_row_count=len(rows),
        entries=entries,
        external_timestamps=external_timestamps or [],
    )


def manifest_root_digest(manifest: AuditManifest) -> str:
    """Return the digest that external timestamp providers should notarize."""
    if manifest.entries:
        return manifest.entries[-1].chain_digest
    return _hex_digest(_canonical_json({"source_ref": manifest.source_ref, "source_row_count": 0}))


def attach_external_timestamp(
    manifest: AuditManifest,
    *,
    provider_id: str,
    proof_ref: str,
    proof_digest: str | None = None,
    timestamped_at_utc: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditManifest:
    """Return a manifest with an external timestamp/transparency-log reference."""
    if not provider_id.strip():
        raise ValueError("provider_id is required")
    if not proof_ref.strip():
        raise ValueError("proof_ref is required")
    timestamp = ExternalTimestampReference(
        provider_id=provider_id,
        root_digest=manifest_root_digest(manifest),
        timestamped_at_utc=timestamped_at_utc or _now_iso(),
        proof_ref=proof_ref,
        proof_digest=proof_digest,
        metadata=metadata or {},
    )
    return AuditManifest(
        schema_version=manifest.schema_version,
        created_at_utc=manifest.created_at_utc,
        source_ref=manifest.source_ref,
        source_row_count=manifest.source_row_count,
        entries=manifest.entries,
        external_timestamps=[*manifest.external_timestamps, timestamp],
    )


def verify_audit_manifest(
    rows: list[dict[str, Any]],
    manifest: AuditManifest,
    *,
    signing_key: str | None = None,
) -> AuditVerificationResult:
    errors: list[str] = []
    if manifest.schema_version != AUDIT_MANIFEST_SCHEMA_VERSION:
        errors.append(f"unsupported schema_version {manifest.schema_version}")
    if manifest.source_row_count != len(rows):
        errors.append(
            f"row count mismatch: manifest={manifest.source_row_count} actual={len(rows)}"
        )
    if len(manifest.entries) != len(rows):
        errors.append(f"entry count mismatch: manifest={len(manifest.entries)} actual={len(rows)}")
    root_digest = manifest_root_digest(manifest)
    for timestamp in manifest.external_timestamps:
        if timestamp.root_digest != root_digest:
            errors.append(
                f"external timestamp root mismatch for {timestamp.provider_id}: "
                f"{timestamp.root_digest}"
            )

    previous: str | None = None
    for index, row in enumerate(rows):
        if index >= len(manifest.entries):
            break
        entry = manifest.entries[index]
        if entry.index != index:
            errors.append(f"index mismatch at row {index}: manifest={entry.index}")
        expected_row_digest = row_digest(row)
        if entry.row_digest != expected_row_digest:
            errors.append(f"row digest mismatch at row {index}")
        expected_chain_digest = chain_digest(expected_row_digest, previous)
        if entry.previous_chain_digest != previous:
            errors.append(f"previous chain mismatch at row {index}")
        if entry.chain_digest != expected_chain_digest:
            errors.append(f"chain digest mismatch at row {index}")
        if signing_key is not None:
            expected_signature = sign_chain_digest(expected_chain_digest, signing_key)
            if entry.signature != expected_signature:
                errors.append(f"signature mismatch at row {index}")
            if entry.signature_algorithm != SIGNATURE_ALGORITHM:
                errors.append(f"signature algorithm mismatch at row {index}")
        previous = expected_chain_digest

    return AuditVerificationResult(valid=not errors, checked_rows=min(len(rows), len(manifest.entries)), errors=errors)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_manifest(path: Path) -> AuditManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = [AuditChainEntry(**entry) for entry in payload.get("entries", [])]
    timestamps = [
        ExternalTimestampReference(**entry)
        for entry in payload.get("external_timestamps", [])
    ]
    return AuditManifest(
        schema_version=int(payload["schema_version"]),
        created_at_utc=str(payload["created_at_utc"]),
        source_ref=str(payload["source_ref"]),
        source_row_count=int(payload["source_row_count"]),
        entries=entries,
        external_timestamps=timestamps,
    )


def write_manifest(manifest: AuditManifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def create_audit_manifest_for_file(
    source_path: Path,
    manifest_path: Path,
    *,
    signing_key: str | None = None,
) -> AuditManifest:
    manifest = build_audit_manifest(
        load_jsonl(source_path),
        source_ref=str(source_path),
        signing_key=signing_key,
    )
    write_manifest(manifest, manifest_path)
    return manifest


def verify_audit_manifest_for_file(
    source_path: Path,
    manifest_path: Path,
    *,
    signing_key: str | None = None,
) -> AuditVerificationResult:
    return verify_audit_manifest(
        load_jsonl(source_path),
        load_manifest(manifest_path),
        signing_key=signing_key,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or verify audit-chain manifests.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--source", type=Path, required=True)
    create_parser.add_argument("--manifest", type=Path, required=True)
    create_parser.add_argument("--signing-key")

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--source", type=Path, required=True)
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--signing-key")

    args = parser.parse_args(argv)
    if args.cmd == "create":
        manifest = create_audit_manifest_for_file(
            args.source,
            args.manifest,
            signing_key=args.signing_key,
        )
        print(json.dumps(manifest.as_dict(), indent=2, sort_keys=True))
        return 0

    if args.cmd == "verify":
        result = verify_audit_manifest_for_file(
            args.source,
            args.manifest,
            signing_key=args.signing_key,
        )
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        return 0 if result.valid else 1

    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
