from __future__ import annotations

import hashlib
import hmac
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.inbound_events import (  # noqa: E402
    ingest_inbound_event,
    list_dead_letters,
    list_inbound_events,
    list_replay_window,
    register_inbound_projection,
)
from cognitive_firm.orchestration.inbound_provider_adapters import (  # noqa: E402
    github_signature,
    ingest_github_webhook,
    ingest_linear_webhook,
    ingest_stripe_webhook,
    linear_signature,
    stripe_signature_header,
)
from cognitive_firm.orchestration.kernel_events import list_kernel_events  # noqa: E402


def _signature(payload: dict, secret: str) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_inbound_event_accepts_signed_projected_payload(tmp_path: Path):
    def projection(payload: dict):
        return "external.issue.updated", f"linear/{payload['id']}", {"state": payload["state"]}

    register_inbound_projection("linear", "issue.updated", projection)
    payload = {"id": "LIN-1", "state": "Done"}
    record = ingest_inbound_event(
        provider="linear",
        event_type="issue.updated",
        external_event_id="evt-1",
        payload=payload,
        signature=_signature(payload, "secret"),
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert record.status == "accepted"
    assert record.signature_valid is True
    assert record.kernel_event_id
    events = list_kernel_events(log_path=tmp_path / "kernel_events.jsonl")
    assert events[0].verb == "external.issue.updated"
    assert events[0].object_ref == "linear/LIN-1"


def test_inbound_event_quarantines_bad_signature(tmp_path: Path):
    record = ingest_inbound_event(
        provider="linear",
        event_type="issue.updated",
        external_event_id="evt-2",
        payload={"id": "LIN-2"},
        signature="sha256=bad",
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert record.status == "quarantined"
    assert record.rejection_reason == "signature verification failed"
    assert list_inbound_events(log_path=tmp_path / "inbound.jsonl") == []
    quarantine = list_inbound_events(log_path=tmp_path / "quarantine.jsonl")
    assert quarantine[0].external_event_id == "evt-2"
    dead_letters = list_dead_letters(log_path=tmp_path / "dead_letters.jsonl")
    assert dead_letters[0].reason == "signature verification failed"
    replay_rows = list_replay_window(log_path=tmp_path / "replay_window.jsonl")
    assert replay_rows[0].external_event_id == "evt-2"


def test_inbound_event_quarantines_duplicate_idempotency_key(tmp_path: Path):
    def projection(payload: dict):
        return "external.issue.updated", f"linear/{payload['id']}", {}

    register_inbound_projection("linear", "issue.duplicate", projection)
    payload = {"id": "LIN-3"}
    first = ingest_inbound_event(
        provider="linear",
        event_type="issue.duplicate",
        external_event_id="evt-3",
        payload=payload,
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )
    second = ingest_inbound_event(
        provider="linear",
        event_type="issue.duplicate",
        external_event_id="evt-3",
        payload=payload,
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert first.status == "accepted"
    assert second.status == "duplicate"
    assert second.rejection_reason == "duplicate idempotency key"


def test_bad_signature_does_not_poison_valid_retry(tmp_path: Path):
    def projection(payload: dict):
        return "external.issue.updated", f"linear/{payload['id']}", {}

    register_inbound_projection("linear", "issue.retry", projection)
    payload = {"id": "LIN-4"}
    bad = ingest_inbound_event(
        provider="linear",
        event_type="issue.retry",
        external_event_id="evt-4",
        payload=payload,
        signature="sha256=bad",
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )
    good = ingest_inbound_event(
        provider="linear",
        event_type="issue.retry",
        external_event_id="evt-4",
        payload=payload,
        signature=_signature(payload, "secret"),
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert bad.status == "quarantined"
    assert good.status == "accepted"


def test_reused_external_event_id_with_different_payload_is_quarantined(tmp_path: Path):
    def projection(payload: dict):
        return "external.issue.updated", f"linear/{payload['id']}", {}

    register_inbound_projection("linear", "issue.conflict", projection)
    first_payload = {"id": "LIN-5", "state": "Todo"}
    second_payload = {"id": "LIN-5", "state": "Done"}
    first = ingest_inbound_event(
        provider="linear",
        event_type="issue.conflict",
        external_event_id="evt-5",
        payload=first_payload,
        signature=_signature(first_payload, "secret"),
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )
    second = ingest_inbound_event(
        provider="linear",
        event_type="issue.conflict",
        external_event_id="evt-5",
        payload=second_payload,
        signature=_signature(second_payload, "secret"),
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert first.status == "accepted"
    assert second.status == "quarantined"
    assert "different payload digest" in str(second.rejection_reason)


def test_projection_exception_is_quarantined(tmp_path: Path):
    def projection(payload: dict):
        raise RuntimeError("missing mapped object")

    register_inbound_projection("linear", "issue.broken", projection)
    payload = {"id": "LIN-6"}
    record = ingest_inbound_event(
        provider="linear",
        event_type="issue.broken",
        external_event_id="evt-6",
        payload=payload,
        signature=_signature(payload, "secret"),
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert record.status == "quarantined"
    assert "projection failed" in str(record.rejection_reason)
    assert list_inbound_events(log_path=tmp_path / "inbound.jsonl") == []


def test_github_webhook_adapter_maps_headers_and_signature(tmp_path: Path):
    def projection(payload: dict):
        issue = payload["issue"]
        return "external.issue.updated", f"github/{issue['number']}", {"state": issue["state"]}

    register_inbound_projection("github", "issues", projection)
    payload = {"action": "closed", "issue": {"number": 42, "state": "closed"}}
    record = ingest_github_webhook(
        headers={
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery-1",
            "X-Hub-Signature-256": github_signature(payload, "secret"),
        },
        payload=payload,
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert record.status == "accepted"
    assert record.provider == "github"
    assert record.event_type == "issues"
    assert record.external_event_id == "delivery-1"
    assert record.projection_object_ref == "github/42"


def test_github_webhook_adapter_verifies_raw_body_when_supplied(tmp_path: Path):
    def projection(payload: dict):
        issue = payload["issue"]
        return "external.issue.updated", f"github/{issue['number']}", {}

    register_inbound_projection("github", "issues.raw", projection)
    payload = {"action": "closed", "issue": {"number": 43, "state": "closed"}}
    raw_body = b'{"issue":{"state":"closed","number":43},"action":"closed"}'
    record = ingest_github_webhook(
        headers={
            "X-GitHub-Event": "issues.raw",
            "X-GitHub-Delivery": "delivery-raw-1",
            "X-Hub-Signature-256": github_signature(payload, "secret", raw_body=raw_body),
        },
        payload=payload,
        raw_body=raw_body,
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert record.status == "accepted"


def test_linear_webhook_adapter_maps_headers_signature_and_timestamp(tmp_path: Path):
    def projection(payload: dict):
        return "external.issue.updated", f"linear/{payload['data']['id']}", {"action": payload["action"]}

    register_inbound_projection("linear", "Issue", projection)
    payload = {
        "action": "update",
        "webhookTimestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        "data": {"id": "LIN-7"},
    }
    record = ingest_linear_webhook(
        headers={
            "Linear-Event": "Issue",
            "Linear-Delivery": "delivery-linear-1",
            "Linear-Signature": linear_signature(payload, "secret"),
        },
        payload=payload,
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert record.status == "accepted"
    assert record.provider == "linear"
    assert record.external_event_id == "delivery-linear-1"
    assert record.projection_object_ref == "linear/LIN-7"


def test_linear_webhook_adapter_quarantines_bad_signature(tmp_path: Path):
    payload = {
        "action": "update",
        "webhookTimestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        "data": {"id": "LIN-8"},
    }

    record = ingest_linear_webhook(
        headers={
            "Linear-Event": "Issue",
            "Linear-Delivery": "delivery-linear-2",
            "Linear-Signature": "bad",
        },
        payload=payload,
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert record.status == "quarantined"
    assert record.metadata["adapter"] == "linear_webhook"


def test_stripe_webhook_adapter_maps_signature_and_event_type(tmp_path: Path):
    def projection(payload: dict):
        return "external.payment.updated", f"stripe/{payload['id']}", {"type": payload["type"]}

    register_inbound_projection("stripe", "payment_intent.succeeded", projection)
    payload = {"id": "evt_1", "type": "payment_intent.succeeded", "data": {"object": {"id": "pi_1"}}}
    record = ingest_stripe_webhook(
        headers={"Stripe-Signature": stripe_signature_header(payload, "secret")},
        payload=payload,
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert record.status == "accepted"
    assert record.provider == "stripe"
    assert record.event_type == "payment_intent.succeeded"
    assert record.projection_object_ref == "stripe/evt_1"


def test_stripe_webhook_adapter_quarantines_bad_signature(tmp_path: Path):
    payload = {"id": "evt_2", "type": "payment_intent.failed"}

    record = ingest_stripe_webhook(
        headers={"Stripe-Signature": "t=1,v1=bad"},
        payload=payload,
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert record.status == "quarantined"
    assert record.metadata["adapter"] == "stripe_webhook"


def test_github_webhook_adapter_quarantines_bad_signature(tmp_path: Path):
    record = ingest_github_webhook(
        headers={
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "delivery-2",
            "X-Hub-Signature-256": "sha256=bad",
        },
        payload={"action": "opened", "issue": {"number": 43}},
        signing_secret="secret",
        log_path=tmp_path / "inbound.jsonl",
        quarantine_path=tmp_path / "quarantine.jsonl",
        kernel_event_log_path=tmp_path / "kernel_events.jsonl",
    )

    assert record.status == "quarantined"
    assert record.rejection_reason == "signature verification failed"
    assert list_inbound_events(log_path=tmp_path / "inbound.jsonl") == []
