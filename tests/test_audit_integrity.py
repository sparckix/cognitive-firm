from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.audit_integrity import (  # noqa: E402
    attach_external_timestamp,
    build_audit_manifest,
    create_audit_manifest_for_file,
    load_manifest,
    manifest_root_digest,
    verify_audit_manifest,
    verify_audit_manifest_for_file,
)


def test_audit_manifest_verifies_untampered_rows():
    rows = [
        {"event_id": "1", "event": "run.started", "payload": {"n": 1}},
        {"event_id": "2", "event": "run.completed", "payload": {"n": 2}},
    ]
    manifest = build_audit_manifest(rows, source_ref="transitions.jsonl")

    result = verify_audit_manifest(rows, manifest)

    assert result.valid is True
    assert result.checked_rows == 2
    assert manifest.entries[1].previous_chain_digest == manifest.entries[0].chain_digest


def test_audit_manifest_detects_row_tampering():
    rows = [{"event_id": "1", "event": "run.started", "payload": {"n": 1}}]
    manifest = build_audit_manifest(rows, source_ref="transitions.jsonl")
    tampered = [{"event_id": "1", "event": "run.started", "payload": {"n": 99}}]

    result = verify_audit_manifest(tampered, manifest)

    assert result.valid is False
    assert "row digest mismatch at row 0" in result.errors
    assert "chain digest mismatch at row 0" in result.errors


def test_audit_manifest_detects_row_count_mismatch():
    rows = [{"event_id": "1", "event": "a"}]
    manifest = build_audit_manifest(rows, source_ref="transitions.jsonl")

    result = verify_audit_manifest(rows + [{"event_id": "2", "event": "b"}], manifest)

    assert result.valid is False
    assert any("row count mismatch" in error for error in result.errors)


def test_hmac_signature_verification_requires_same_key():
    rows = [{"event_id": "1", "event": "a"}]
    manifest = build_audit_manifest(rows, source_ref="transitions.jsonl", signing_key="secret-a")

    assert verify_audit_manifest(rows, manifest, signing_key="secret-a").valid is True
    wrong_key = verify_audit_manifest(rows, manifest, signing_key="secret-b")
    assert wrong_key.valid is False
    assert "signature mismatch at row 0" in wrong_key.errors


def test_audit_manifest_file_round_trip(tmp_path: Path):
    source = tmp_path / "transitions.jsonl"
    manifest_path = tmp_path / "audit_manifest.json"
    source.write_text(
        json.dumps({"event_id": "1", "event": "a"}) + "\n"
        + json.dumps({"event_id": "2", "event": "b"}) + "\n",
        encoding="utf-8",
    )

    created = create_audit_manifest_for_file(source, manifest_path, signing_key="secret")
    loaded = load_manifest(manifest_path)
    result = verify_audit_manifest_for_file(source, manifest_path, signing_key="secret")

    assert loaded.source_row_count == created.source_row_count == 2
    assert result.valid is True


def test_audit_manifest_can_attach_external_timestamp_reference():
    rows = [{"event_id": "1", "event": "a"}]
    manifest = build_audit_manifest(rows, source_ref="transitions.jsonl")

    stamped = attach_external_timestamp(
        manifest,
        provider_id="rfc3161-tsa",
        proof_ref="s3://audit/transitions.tsr",
        proof_digest="sha256:abc",
        timestamped_at_utc="2026-05-20T00:00:00+00:00",
    )

    assert stamped.external_timestamps[0].root_digest == manifest_root_digest(manifest)
    assert verify_audit_manifest(rows, stamped).valid is True


def test_audit_manifest_detects_external_timestamp_root_mismatch():
    rows = [{"event_id": "1", "event": "a"}]
    manifest = attach_external_timestamp(
        build_audit_manifest(rows, source_ref="transitions.jsonl"),
        provider_id="rekor",
        proof_ref="rekor://entry/1",
    )
    tampered_timestamp = manifest.external_timestamps[0].__class__(
        provider_id="rekor",
        root_digest="sha256:wrong",
        timestamped_at_utc=manifest.external_timestamps[0].timestamped_at_utc,
        proof_ref="rekor://entry/1",
    )
    tampered = manifest.__class__(
        schema_version=manifest.schema_version,
        created_at_utc=manifest.created_at_utc,
        source_ref=manifest.source_ref,
        source_row_count=manifest.source_row_count,
        entries=manifest.entries,
        external_timestamps=[tampered_timestamp],
    )

    result = verify_audit_manifest(rows, tampered)

    assert result.valid is False
    assert any("external timestamp root mismatch" in error for error in result.errors)
