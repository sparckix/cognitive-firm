"""Provider-specific inbound event adapter helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cognitive_firm.orchestration.inbound_events import InboundEventRecord, ingest_inbound_event


def github_signature(payload: dict[str, Any], signing_secret: str, *, raw_body: bytes | None = None) -> str:
    """Return a GitHub-style ``X-Hub-Signature-256`` fixture value."""

    return "sha256=" + hmac.new(
        signing_secret.encode("utf-8"),
        raw_body or _canonical_json(payload),
        hashlib.sha256,
    ).hexdigest()


def ingest_github_webhook(
    *,
    headers: Mapping[str, str],
    payload: dict[str, Any],
    signing_secret: str,
    raw_body: bytes | None = None,
    actor: str = "external.github",
    log_path: Path | None = None,
    quarantine_path: Path | None = None,
    replay_window_path: Path | None = None,
    dead_letter_path: Path | None = None,
    kernel_event_log_path: Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> InboundEventRecord:
    """Map GitHub webhook headers into the generic inbound-event primitive."""

    event_type = _header(headers, "x-github-event")
    delivery_id = _header(headers, "x-github-delivery")
    signature = _header(headers, "x-hub-signature-256")
    signature_ok = hmac.compare_digest(github_signature(payload, signing_secret, raw_body=raw_body), signature)
    return ingest_inbound_event(
        provider="github",
        event_type=event_type,
        external_event_id=delivery_id,
        payload=payload,
        signature=None if signature_ok else "bad",
        signing_secret=None if signature_ok else "__github_webhook_rejected__",
        actor=actor,
        log_path=log_path,
        quarantine_path=quarantine_path,
        replay_window_path=replay_window_path,
        dead_letter_path=dead_letter_path,
        kernel_event_log_path=kernel_event_log_path,
        metadata={
            "adapter": "github_webhook",
            "headers": {
                "x-github-event": event_type,
                "x-github-delivery": delivery_id,
            },
            **(metadata or {}),
        },
    )


def linear_signature(payload: dict[str, Any], signing_secret: str, *, raw_body: bytes | None = None) -> str:
    """Return a Linear-style ``Linear-Signature`` fixture value.

    Linear signs the raw request body with HMAC-SHA256 and sends a hex digest in
    the ``Linear-Signature`` header. Local fixtures use canonical JSON when
    ``raw_body`` is not supplied.
    """

    return hmac.new(signing_secret.encode("utf-8"), raw_body or _canonical_json(payload), hashlib.sha256).hexdigest()


def ingest_linear_webhook(
    *,
    headers: Mapping[str, str],
    payload: dict[str, Any],
    signing_secret: str,
    raw_body: bytes | None = None,
    actor: str = "external.linear",
    log_path: Path | None = None,
    quarantine_path: Path | None = None,
    replay_window_path: Path | None = None,
    dead_letter_path: Path | None = None,
    kernel_event_log_path: Path | None = None,
    metadata: dict[str, Any] | None = None,
    timestamp_tolerance_seconds: int = 60,
) -> InboundEventRecord:
    """Map Linear webhook headers into the generic inbound-event primitive."""

    event_type = _header(headers, "linear-event")
    delivery_id = _header(headers, "linear-delivery")
    signature = _header(headers, "linear-signature")
    signature_ok = hmac.compare_digest(linear_signature(payload, signing_secret, raw_body=raw_body), signature)
    timestamp_ok = _linear_timestamp_ok(
        payload.get("webhookTimestamp"),
        tolerance_seconds=timestamp_tolerance_seconds,
    )
    if not signature_ok or not timestamp_ok:
        reason = "signature verification failed" if not signature_ok else "webhook timestamp outside tolerance"
        return ingest_inbound_event(
            provider="linear",
            event_type=event_type or "unknown",
            external_event_id=delivery_id or None,
            payload=payload,
            signature="bad",
            signing_secret="__linear_webhook_rejected__",
            actor=actor,
            log_path=log_path,
            quarantine_path=quarantine_path,
            replay_window_path=replay_window_path,
            dead_letter_path=dead_letter_path,
            kernel_event_log_path=kernel_event_log_path,
            metadata={
                "adapter": "linear_webhook",
                "rejection_reason": reason,
                "headers": {
                    "linear-event": event_type,
                    "linear-delivery": delivery_id,
                },
                **(metadata or {}),
            },
        )
    return ingest_inbound_event(
        provider="linear",
        event_type=event_type,
        external_event_id=delivery_id,
        payload=payload,
        signature=None,
        signing_secret=None,
        actor=actor,
        log_path=log_path,
        quarantine_path=quarantine_path,
        replay_window_path=replay_window_path,
        dead_letter_path=dead_letter_path,
        kernel_event_log_path=kernel_event_log_path,
        metadata={
            "adapter": "linear_webhook",
            "headers": {
                "linear-event": event_type,
                "linear-delivery": delivery_id,
            },
            **(metadata or {}),
        },
    )


def stripe_signature_header(
    payload: dict[str, Any],
    signing_secret: str,
    *,
    raw_body: bytes | None = None,
    timestamp: int | None = None,
) -> str:
    """Return a Stripe-style ``Stripe-Signature`` fixture header."""

    timestamp = timestamp or int(datetime.now(timezone.utc).timestamp())
    body = (raw_body or _canonical_json(payload)).decode("utf-8")
    signed_payload = f"{timestamp}.{body}".encode("utf-8")
    signature = hmac.new(signing_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def ingest_stripe_webhook(
    *,
    headers: Mapping[str, str],
    payload: dict[str, Any],
    signing_secret: str,
    raw_body: bytes | None = None,
    actor: str = "external.stripe",
    log_path: Path | None = None,
    quarantine_path: Path | None = None,
    replay_window_path: Path | None = None,
    dead_letter_path: Path | None = None,
    kernel_event_log_path: Path | None = None,
    metadata: dict[str, Any] | None = None,
    timestamp_tolerance_seconds: int = 300,
) -> InboundEventRecord:
    """Map Stripe webhook headers into the generic inbound-event primitive."""

    signature_header = _header(headers, "stripe-signature")
    timestamp, signatures = _parse_stripe_signature_header(signature_header)
    signature_ok = False
    timestamp_ok = False
    if timestamp is not None:
        timestamp_ok = _epoch_seconds_ok(timestamp, tolerance_seconds=timestamp_tolerance_seconds)
        expected = stripe_signature_header(payload, signing_secret, raw_body=raw_body, timestamp=timestamp)
        _, expected_signatures = _parse_stripe_signature_header(expected)
        signature_ok = bool(set(signatures) & set(expected_signatures))
    event_type = str(payload.get("type") or "unknown")
    event_id = str(payload.get("id") or "") or None
    if not signature_ok or not timestamp_ok:
        reason = "signature verification failed" if not signature_ok else "webhook timestamp outside tolerance"
        return ingest_inbound_event(
            provider="stripe",
            event_type=event_type,
            external_event_id=event_id,
            payload=payload,
            signature="bad",
            signing_secret="__stripe_webhook_rejected__",
            actor=actor,
            log_path=log_path,
            quarantine_path=quarantine_path,
            replay_window_path=replay_window_path,
            dead_letter_path=dead_letter_path,
            kernel_event_log_path=kernel_event_log_path,
            metadata={"adapter": "stripe_webhook", "rejection_reason": reason, **(metadata or {})},
        )
    return ingest_inbound_event(
        provider="stripe",
        event_type=event_type,
        external_event_id=event_id,
        payload=payload,
        signature=None,
        signing_secret=None,
        actor=actor,
        log_path=log_path,
        quarantine_path=quarantine_path,
        replay_window_path=replay_window_path,
        dead_letter_path=dead_letter_path,
        kernel_event_log_path=kernel_event_log_path,
        metadata={"adapter": "stripe_webhook", **(metadata or {})},
    )


def _header(headers: Mapping[str, str], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value.strip()
    return ""


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _linear_timestamp_ok(value: object, *, tolerance_seconds: int) -> bool:
    if value is None:
        return True
    try:
        timestamp_ms = int(value)
    except (TypeError, ValueError):
        return False
    received = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    delta = abs((datetime.now(timezone.utc) - received).total_seconds())
    return delta <= tolerance_seconds


def _parse_stripe_signature_header(value: str) -> tuple[int | None, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in value.split(","):
        key, _, raw = part.partition("=")
        key = key.strip()
        raw = raw.strip()
        if key == "t":
            try:
                timestamp = int(raw)
            except ValueError:
                timestamp = None
        elif key == "v1" and raw:
            signatures.append(raw)
    return timestamp, signatures


def _epoch_seconds_ok(value: int, *, tolerance_seconds: int) -> bool:
    received = datetime.fromtimestamp(value, tz=timezone.utc)
    delta = abs((datetime.now(timezone.utc) - received).total_seconds())
    return delta <= tolerance_seconds
