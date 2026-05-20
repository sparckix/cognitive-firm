"""Canonical kernel event envelope.

This is the small event contract that newer primitives should be able to
export, even when their local T1 adapter is still a JSONL file.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cognitive_firm.common.paths import WORKSPACE_DIR


KERNEL_EVENT_SCHEMA_VERSION = 1
DEFAULT_KERNEL_EVENTS_LOG = WORKSPACE_DIR / "transitions.jsonl"


@dataclass(frozen=True)
class KernelEvent:
    event_id: str
    schema_version: int
    occurred_at_utc: str
    recorded_at_utc: str
    actor: str
    verb: str
    object_ref: str
    subject_ref: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    causation_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    payload_hash: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_kernel_event(
    *,
    actor: str,
    verb: str,
    object_ref: str,
    payload: dict[str, Any] | None = None,
    subject_ref: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    causation_id: str | None = None,
    correlation_id: str | None = None,
    idempotency_key: str | None = None,
    event_id: str | None = None,
    occurred_at_utc: str | None = None,
    recorded_at_utc: str | None = None,
) -> KernelEvent:
    """Create a kernel event envelope without writing it."""
    if not actor.strip():
        raise ValueError("actor is required")
    if not verb.strip():
        raise ValueError("verb is required")
    if not object_ref.strip():
        raise ValueError("object_ref is required")
    body = copy.deepcopy(payload or {})
    now = _now_iso()
    return KernelEvent(
        event_id=event_id or f"kevt_{uuid.uuid4().hex[:16]}",
        schema_version=KERNEL_EVENT_SCHEMA_VERSION,
        occurred_at_utc=occurred_at_utc or now,
        recorded_at_utc=recorded_at_utc or now,
        actor=actor,
        verb=verb,
        object_ref=object_ref,
        subject_ref=subject_ref,
        tenant_id=tenant_id,
        project_id=project_id,
        causation_id=causation_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        payload=body,
        payload_hash=payload_hash(body),
    )


def append_kernel_event(event: KernelEvent, *, log_path: Path | None = None) -> KernelEvent:
    path = log_path or DEFAULT_KERNEL_EVENTS_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        if log_path is None:
            handle.write(json.dumps(transition_row_from_kernel_event(event), sort_keys=True) + "\n")
        else:
            handle.write(json.dumps(event.as_dict(), sort_keys=True) + "\n")
    return event


def record_kernel_event(
    *,
    actor: str,
    verb: str,
    object_ref: str,
    payload: dict[str, Any] | None = None,
    subject_ref: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    causation_id: str | None = None,
    correlation_id: str | None = None,
    idempotency_key: str | None = None,
    log_path: Path | None = None,
) -> KernelEvent:
    event = create_kernel_event(
        actor=actor,
        verb=verb,
        object_ref=object_ref,
        payload=payload,
        subject_ref=subject_ref,
        tenant_id=tenant_id,
        project_id=project_id,
        causation_id=causation_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )
    return append_kernel_event(event, log_path=log_path)


def list_kernel_events(
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    object_ref: str | None = None,
    verb: str | None = None,
    log_path: Path | None = None,
) -> list[KernelEvent]:
    events: list[KernelEvent] = []
    for row in _read_jsonl(log_path or DEFAULT_KERNEL_EVENTS_LOG):
        event = kernel_event_from_row(row)
        if tenant_id is not None and event.tenant_id != tenant_id:
            continue
        if project_id is not None and event.project_id != project_id:
            continue
        if object_ref is not None and event.object_ref != object_ref:
            continue
        if verb is not None and event.verb != verb:
            continue
        events.append(event)
    return events


def kernel_event_from_row(row: dict[str, Any]) -> KernelEvent:
    """Read a raw KernelEvent row, new transition row, or legacy transition row."""

    embedded = row.get("kernel_event")
    if isinstance(embedded, dict):
        return KernelEvent(**embedded)
    raw_required = {
        "event_id",
        "schema_version",
        "occurred_at_utc",
        "recorded_at_utc",
        "actor",
        "verb",
        "object_ref",
        "payload_hash",
    }
    if raw_required.issubset(row):
        return KernelEvent(**row)
    if "event" in row or "subject" in row or "ts" in row:
        return event_from_legacy_transition(row)
    return KernelEvent(**row)


def transition_row_from_kernel_event(event: KernelEvent) -> dict[str, Any]:
    """Represent a KernelEvent on the canonical local transition stream."""

    return {
        "schema_version": 1,
        "event_id": event.event_id,
        "ts": event.occurred_at_utc,
        "event": event.verb,
        "actor": event.actor,
        "role_id": None,
        "surface": "kernel_events",
        "subject": event.object_ref,
        "causality_id": event.causation_id,
        "payload": copy.deepcopy(event.payload),
        "kernel_event": event.as_dict(),
    }


def event_from_legacy_transition(row: dict[str, Any]) -> KernelEvent:
    """Project the older transition-log row shape into the kernel envelope."""
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    return create_kernel_event(
        event_id=str(row.get("event_id") or f"kevt_{uuid.uuid4().hex[:16]}"),
        actor=str(row.get("actor") or "unknown"),
        verb=str(row.get("event") or "transition.recorded"),
        object_ref=str(row.get("subject") or row.get("event") or "unknown"),
        subject_ref=str(row.get("subject")) if row.get("subject") else None,
        tenant_id=row.get("tenant_id") or payload.get("tenant_id"),
        project_id=row.get("project_id") or payload.get("project_id"),
        idempotency_key=row.get("idempotency_key") or payload.get("idempotency_key"),
        causation_id=row.get("causality_id") or row.get("causation_id"),
        correlation_id=row.get("correlation_id"),
        occurred_at_utc=str(row.get("ts") or row.get("occurred_at_utc") or _now_iso()),
        recorded_at_utc=str(row.get("recorded_at_utc") or row.get("ts") or _now_iso()),
        payload=payload,
    )


def payload_hash(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect kernel event envelopes.")
    parser.add_argument("--log-path", type=Path)
    parser.add_argument("--tenant-id")
    parser.add_argument("--project-id")
    parser.add_argument("--object-ref")
    parser.add_argument("--verb")
    args = parser.parse_args(argv)
    events = list_kernel_events(
        tenant_id=args.tenant_id,
        project_id=args.project_id,
        object_ref=args.object_ref,
        verb=args.verb,
        log_path=args.log_path,
    )
    print(json.dumps([event.as_dict() for event in events], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
