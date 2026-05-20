from __future__ import annotations

import hashlib
import hmac
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.inbound_events import ingest_inbound_event, register_inbound_projection  # noqa: E402
from cognitive_firm.orchestration.inbound_provider_adapters import (  # noqa: E402
    github_signature,
    ingest_github_webhook,
    ingest_linear_webhook,
    ingest_stripe_webhook,
    linear_signature,
    stripe_signature_header,
)
from cognitive_firm.role_extensions.mcp_bridge.projections import project_response  # noqa: E402
from cognitive_firm.role_extensions.mcp_bridge.servers import linear as _linear  # noqa: F401, E402


def main() -> int:
    linear = project_response(
        "linear",
        "list_projects",
        {
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "projects": [
                                    {
                                        "id": "proj_1",
                                        "name": "Example Project",
                                        "state": {"name": "Planned"},
                                    }
                                ]
                            }
                        ),
                    }
                ]
            },
        },
    )
    if linear.transition_class != "mcp_call_dispatched":
        raise AssertionError(f"Linear projection rejected fixture: {linear}")

    with tempfile.TemporaryDirectory(prefix="cognitive-firm-app-conformance-") as raw:
        root = Path(raw)
        inbound = root / "inbound.jsonl"
        quarantine = root / "quarantine.jsonl"
        kernel = root / "kernel_events.jsonl"

        event_type = "issue.conformance"

        def projection(payload: dict):
            return "external.issue.updated", f"linear/{payload['id']}", {"state": payload["state"]}

        register_inbound_projection("linear", event_type, projection)
        payload = {"id": "LIN-1", "state": "Done"}
        bad = ingest_inbound_event(
            provider="linear",
            event_type=event_type,
            external_event_id="evt-1",
            payload=payload,
            signature="sha256=bad",
            signing_secret="secret",
            log_path=inbound,
            quarantine_path=quarantine,
            kernel_event_log_path=kernel,
        )
        good = ingest_inbound_event(
            provider="linear",
            event_type=event_type,
            external_event_id="evt-1",
            payload=payload,
            signature=_signature(payload, "secret"),
            signing_secret="secret",
            log_path=inbound,
            quarantine_path=quarantine,
            kernel_event_log_path=kernel,
        )
        duplicate = ingest_inbound_event(
            provider="linear",
            event_type=event_type,
            external_event_id="evt-1",
            payload=payload,
            signature=_signature(payload, "secret"),
            signing_secret="secret",
            log_path=inbound,
            quarantine_path=quarantine,
            kernel_event_log_path=kernel,
        )
        conflict_payload = {"id": "LIN-1", "state": "Canceled"}
        conflict = ingest_inbound_event(
            provider="linear",
            event_type=event_type,
            external_event_id="evt-1",
            payload=conflict_payload,
            signature=_signature(conflict_payload, "secret"),
            signing_secret="secret",
            log_path=inbound,
            quarantine_path=quarantine,
            kernel_event_log_path=kernel,
        )

        def github_projection(payload: dict):
            issue = payload["issue"]
            return "external.issue.updated", f"github/{issue['number']}", {"state": issue["state"]}

        register_inbound_projection("github", "issues", github_projection)
        github_payload = {"action": "closed", "issue": {"number": 7, "state": "closed"}}
        github = ingest_github_webhook(
            headers={
                "X-GitHub-Event": "issues",
                "X-GitHub-Delivery": "delivery-7",
                "X-Hub-Signature-256": github_signature(github_payload, "secret"),
            },
            payload=github_payload,
            signing_secret="secret",
            log_path=inbound,
            quarantine_path=quarantine,
            kernel_event_log_path=kernel,
        )

        def linear_webhook_projection(payload: dict):
            return (
                "external.issue.updated",
                f"linear/{payload['data']['id']}",
                {"action": payload["action"]},
            )

        register_inbound_projection("linear", "Issue", linear_webhook_projection)
        linear_webhook_payload = {
            "action": "update",
            "webhookTimestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "data": {"id": "LIN-2"},
        }
        linear_webhook = ingest_linear_webhook(
            headers={
                "Linear-Event": "Issue",
                "Linear-Delivery": "delivery-linear-2",
                "Linear-Signature": linear_signature(linear_webhook_payload, "secret"),
            },
            payload=linear_webhook_payload,
            signing_secret="secret",
            log_path=inbound,
            quarantine_path=quarantine,
            kernel_event_log_path=kernel,
        )

        def stripe_projection(payload: dict):
            return "external.payment.updated", f"stripe/{payload['id']}", {"type": payload["type"]}

        register_inbound_projection("stripe", "payment_intent.succeeded", stripe_projection)
        stripe_payload = {"id": "evt_1", "type": "payment_intent.succeeded"}
        stripe_webhook = ingest_stripe_webhook(
            headers={"Stripe-Signature": stripe_signature_header(stripe_payload, "secret")},
            payload=stripe_payload,
            signing_secret="secret",
            log_path=inbound,
            quarantine_path=quarantine,
            kernel_event_log_path=kernel,
        )

    if bad.status != "quarantined" or good.status != "accepted":
        raise AssertionError(f"signature retry conformance failed: bad={bad} good={good}")
    if duplicate.status != "duplicate":
        raise AssertionError(f"duplicate conformance failed: {duplicate}")
    if conflict.status != "quarantined":
        raise AssertionError(f"conflict conformance failed: {conflict}")
    if github.status != "accepted":
        raise AssertionError(f"GitHub webhook conformance failed: {github}")
    if linear_webhook.status != "accepted":
        raise AssertionError(f"Linear webhook conformance failed: {linear_webhook}")
    if stripe_webhook.status != "accepted":
        raise AssertionError(f"Stripe webhook conformance failed: {stripe_webhook}")

    print(
        json.dumps(
            {
                "ok": True,
                "linear_projection": linear.transition_class,
                "bad_signature_retry": [bad.status, good.status],
                "duplicate_status": duplicate.status,
                "conflict_status": conflict.status,
                "github_webhook_status": github.status,
                "linear_webhook_status": linear_webhook.status,
                "stripe_webhook_status": stripe_webhook.status,
            },
            sort_keys=True,
        )
    )
    return 0


def _signature(payload: dict, secret: str) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
