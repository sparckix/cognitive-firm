"""Inbound webhook/event ingestion boundary.

Inbound events are external observations. They are not trusted kernel
mutations until signature/idempotency checks pass and a deterministic
projection accepts the payload.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.kernel_events import KernelEvent, record_kernel_event


DEFAULT_INBOUND_EVENTS_LOG = ORG_ROOT_DIR / "inbound_events" / "inbound_events.jsonl"
DEFAULT_QUARANTINE_LOG = ORG_ROOT_DIR / "inbound_events" / "quarantine.jsonl"
DEFAULT_REPLAY_WINDOW_LOG = ORG_ROOT_DIR / "inbound_events" / "replay_window.jsonl"
DEFAULT_DEAD_LETTER_LOG = ORG_ROOT_DIR / "inbound_events" / "dead_letters.jsonl"

ProjectionFn = Callable[[dict[str, Any]], tuple[str, str, dict[str, Any]]]
_PROJECTIONS: dict[tuple[str, str], ProjectionFn] = {}


@dataclass(frozen=True)
class InboundEventRecord:
    inbound_event_id: str
    received_at_utc: str
    provider: str
    event_type: str
    external_event_id: str | None
    idempotency_key: str
    status: str
    signature_valid: bool
    projection_verb: str | None = None
    projection_object_ref: str | None = None
    kernel_event_id: str | None = None
    rejection_reason: str | None = None
    payload_digest: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReplayWindowRecord:
    replay_key: str
    first_seen_at_utc: str
    provider: str
    event_type: str
    external_event_id: str | None
    payload_digest: str
    status: str
    inbound_event_id: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DeadLetterRecord:
    dead_letter_id: str
    created_at_utc: str
    provider: str
    event_type: str
    external_event_id: str | None
    inbound_event_id: str
    reason: str
    payload_digest: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def register_inbound_projection(provider: str, event_type: str, fn: ProjectionFn) -> None:
    key = (_normalize(provider), _normalize(event_type))
    existing = _PROJECTIONS.get(key)
    if existing is not None and existing is not fn:
        raise ValueError(f"inbound projection already registered for {provider}/{event_type}")
    _PROJECTIONS[key] = fn


def ingest_inbound_event(
    *,
    provider: str,
    event_type: str,
    payload: dict[str, Any],
    external_event_id: str | None = None,
    signature: str | None = None,
    signing_secret: str | None = None,
    actor: str = "external.webhook",
    log_path: Path | None = None,
    quarantine_path: Path | None = None,
    replay_window_path: Path | None = None,
    dead_letter_path: Path | None = None,
    kernel_event_log_path: Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> InboundEventRecord:
    if not provider.strip():
        raise ValueError("provider is required")
    if not event_type.strip():
        raise ValueError("event_type is required")
    digest = _payload_digest(payload)
    idempotency_key = _idempotency_key(provider, event_type, external_event_id, digest)
    caller_supplied_log_path = log_path is not None
    log_path = log_path or DEFAULT_INBOUND_EVENTS_LOG
    quarantine_path = quarantine_path or DEFAULT_QUARANTINE_LOG
    replay_window_path = replay_window_path or (
        log_path.parent / "replay_window.jsonl" if caller_supplied_log_path else DEFAULT_REPLAY_WINDOW_LOG
    )
    dead_letter_path = dead_letter_path or (
        log_path.parent / "dead_letters.jsonl" if caller_supplied_log_path else DEFAULT_DEAD_LETTER_LOG
    )
    _record_replay_window(
        provider=provider,
        event_type=event_type,
        external_event_id=external_event_id,
        payload_digest=digest,
        idempotency_key=idempotency_key,
        log_path=replay_window_path,
    )

    signature_valid = verify_signature(payload, signature=signature, signing_secret=signing_secret)
    if not signature_valid:
        record = _record(
                provider=provider,
                event_type=event_type,
                external_event_id=external_event_id,
                idempotency_key=idempotency_key,
                status="quarantined",
                signature_valid=False,
                payload_digest=digest,
                rejection_reason="signature verification failed",
                metadata=metadata,
        )
        return _write_rejected_record(record, quarantine_path=quarantine_path, dead_letter_path=dead_letter_path)

    conflict = _external_event_digest_conflict(
        provider=provider,
        event_type=event_type,
        external_event_id=external_event_id,
        payload_digest=digest,
        paths=(log_path, quarantine_path),
    )
    if conflict:
        record = _record(
                provider=provider,
                event_type=event_type,
                external_event_id=external_event_id,
                idempotency_key=idempotency_key,
                status="quarantined",
                signature_valid=True,
                payload_digest=digest,
                rejection_reason="external event id reused with different payload digest",
                metadata=metadata,
        )
        return _write_rejected_record(record, quarantine_path=quarantine_path, dead_letter_path=dead_letter_path)

    if _seen_verified_idempotency_key(idempotency_key, (log_path, quarantine_path)):
        record = _record(
                provider=provider,
                event_type=event_type,
                external_event_id=external_event_id,
                idempotency_key=idempotency_key,
                status="duplicate",
                signature_valid=True,
                payload_digest=digest,
                rejection_reason="duplicate idempotency key",
                metadata=metadata,
        )
        return _write_rejected_record(record, quarantine_path=quarantine_path, dead_letter_path=dead_letter_path)

    projection = _PROJECTIONS.get((_normalize(provider), _normalize(event_type)))
    if projection is None:
        record = _record(
                provider=provider,
                event_type=event_type,
                external_event_id=external_event_id,
                idempotency_key=idempotency_key,
                status="quarantined",
                signature_valid=True,
                payload_digest=digest,
                rejection_reason="no inbound projection registered",
                metadata=metadata,
        )
        return _write_rejected_record(record, quarantine_path=quarantine_path, dead_letter_path=dead_letter_path)

    try:
        verb, object_ref, projected_payload = projection(payload)
    except Exception as exc:  # noqa: BLE001
        record = _record(
                provider=provider,
                event_type=event_type,
                external_event_id=external_event_id,
                idempotency_key=idempotency_key,
                status="quarantined",
                signature_valid=True,
                payload_digest=digest,
                rejection_reason=f"projection failed: {exc}",
                metadata=metadata,
        )
        return _write_rejected_record(record, quarantine_path=quarantine_path, dead_letter_path=dead_letter_path)
    kernel_event: KernelEvent = record_kernel_event(
        actor=actor,
        verb=verb,
        object_ref=object_ref,
        payload={
            "provider": provider,
            "event_type": event_type,
            "external_event_id": external_event_id,
            "payload_digest": digest,
            "projection": projected_payload,
        },
        subject_ref=external_event_id,
        idempotency_key=idempotency_key,
        log_path=kernel_event_log_path,
    )
    return _write_record(
        _record(
            provider=provider,
            event_type=event_type,
            external_event_id=external_event_id,
            idempotency_key=idempotency_key,
            status="accepted",
            signature_valid=True,
            projection_verb=verb,
            projection_object_ref=object_ref,
            kernel_event_id=kernel_event.event_id,
            payload_digest=digest,
            metadata=metadata,
        ),
        log_path,
    )


def verify_signature(
    payload: dict[str, Any],
    *,
    signature: str | None,
    signing_secret: str | None,
) -> bool:
    if signing_secret is None:
        return True
    if not signature:
        return False
    expected = hmac.new(
        signing_secret.encode("utf-8"),
        _canonical_json(payload),
        hashlib.sha256,
    ).hexdigest()
    normalized = signature.removeprefix("sha256=").strip()
    return hmac.compare_digest(normalized, expected)


def list_inbound_events(*, log_path: Path | None = None) -> list[InboundEventRecord]:
    rows = _read_jsonl(log_path or DEFAULT_INBOUND_EVENTS_LOG)
    return [InboundEventRecord(**row) for row in rows]


def list_replay_window(*, log_path: Path | None = None) -> list[ReplayWindowRecord]:
    rows = _read_jsonl(log_path or DEFAULT_REPLAY_WINDOW_LOG)
    return [ReplayWindowRecord(**row) for row in rows]


def list_dead_letters(*, log_path: Path | None = None) -> list[DeadLetterRecord]:
    rows = _read_jsonl(log_path or DEFAULT_DEAD_LETTER_LOG)
    return [DeadLetterRecord(**row) for row in rows]


def _record(
    *,
    provider: str,
    event_type: str,
    external_event_id: str | None,
    idempotency_key: str,
    status: str,
    signature_valid: bool,
    payload_digest: str,
    projection_verb: str | None = None,
    projection_object_ref: str | None = None,
    kernel_event_id: str | None = None,
    rejection_reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> InboundEventRecord:
    return InboundEventRecord(
        inbound_event_id=f"inb_{uuid.uuid4().hex[:16]}",
        received_at_utc=datetime.now(timezone.utc).isoformat(),
        provider=provider,
        event_type=event_type,
        external_event_id=external_event_id,
        idempotency_key=idempotency_key,
        status=status,
        signature_valid=signature_valid,
        projection_verb=projection_verb,
        projection_object_ref=projection_object_ref,
        kernel_event_id=kernel_event_id,
        rejection_reason=rejection_reason,
        payload_digest=payload_digest,
        metadata=metadata or {},
    )


def _write_record(record: InboundEventRecord, path: Path) -> InboundEventRecord:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.as_dict(), sort_keys=True) + "\n")
    return record


def _write_rejected_record(
    record: InboundEventRecord,
    *,
    quarantine_path: Path,
    dead_letter_path: Path,
) -> InboundEventRecord:
    _write_record(record, quarantine_path)
    _write_jsonl(
        dead_letter_path,
        DeadLetterRecord(
            dead_letter_id=f"dlq_{uuid.uuid4().hex[:16]}",
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            provider=record.provider,
            event_type=record.event_type,
            external_event_id=record.external_event_id,
            inbound_event_id=record.inbound_event_id,
            reason=record.rejection_reason or "rejected",
            payload_digest=record.payload_digest,
            metadata=record.metadata,
        ).as_dict(),
    )
    return record


def _record_replay_window(
    *,
    provider: str,
    event_type: str,
    external_event_id: str | None,
    payload_digest: str,
    idempotency_key: str,
    log_path: Path,
) -> None:
    if _replay_window_seen(idempotency_key, log_path):
        return
    _write_jsonl(
        log_path,
        ReplayWindowRecord(
            replay_key=idempotency_key,
            first_seen_at_utc=datetime.now(timezone.utc).isoformat(),
            provider=provider,
            event_type=event_type,
            external_event_id=external_event_id,
            payload_digest=payload_digest,
            status="seen",
            inbound_event_id="",
        ).as_dict(),
    )


def _write_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _replay_window_seen(key: str, path: Path) -> bool:
    return any(row.get("replay_key") == key for row in _read_jsonl(path))


def _seen_verified_idempotency_key(key: str, paths: tuple[Path, ...]) -> bool:
    for path in paths:
        for row in _read_jsonl(path):
            if row.get("idempotency_key") == key and row.get("signature_valid") is not False:
                return True
    return False


def _external_event_digest_conflict(
    *,
    provider: str,
    event_type: str,
    external_event_id: str | None,
    payload_digest: str,
    paths: tuple[Path, ...],
) -> bool:
    if not external_event_id:
        return False
    normalized_provider = _normalize(provider)
    normalized_event_type = _normalize(event_type)
    for path in paths:
        for row in _read_jsonl(path):
            if row.get("signature_valid") is False:
                continue
            if _normalize(str(row.get("provider") or "")) != normalized_provider:
                continue
            if _normalize(str(row.get("event_type") or "")) != normalized_event_type:
                continue
            if row.get("external_event_id") != external_event_id:
                continue
            if row.get("payload_digest") != payload_digest:
                return True
    return False


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _idempotency_key(provider: str, event_type: str, external_event_id: str | None, digest: str) -> str:
    return hashlib.sha256(f"{provider}|{event_type}|{external_event_id or digest}".encode("utf-8")).hexdigest()


def _payload_digest(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(payload)).hexdigest()


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _normalize(value: str) -> str:
    return value.strip().lower()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect inbound event records.")
    parser.add_argument("--log-path", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    records = list_inbound_events(log_path=args.log_path)
    if args.json:
        print(json.dumps([record.as_dict() for record in records], indent=2, sort_keys=True))
    else:
        for record in records:
            print(f"- {record.provider}/{record.event_type}: {record.status} ({record.external_event_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
