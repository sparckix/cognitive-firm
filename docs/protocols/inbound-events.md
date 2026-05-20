# Inbound Events

**Status:** T1 adapter shipped.
**Module:** `cognitive_firm.orchestration.inbound_events`
**Tests:** `tests/test_inbound_events.py`

Inbound events are webhooks or external event-stream messages entering the
kernel. They are observations, not trusted mutations, until they pass signature
verification, idempotency checks, and deterministic projection.

## Boundary

Use inbound events for:

- webhooks from Linear, GitHub, Stripe, CRMs, ERPs, or document systems;
- AsyncAPI-style message streams;
- CloudEvents-style external notifications.

Do not use inbound events for app surfaces. Apps should submit typed kernel
commands through the kernel service or CLI/module boundary.

## Flow

```text
external event
-> signature check
-> idempotency/conflict check
-> deterministic projection
-> accepted inbound-event record + kernel event
```

Failures go to quarantine:

- missing or invalid signature;
- duplicate idempotency key;
- reused external event id with a different payload digest;
- no registered projection;
- projection exception.

Signature verification happens before dedupe so an invalid spoof cannot poison
a later valid retry for the same external event id.

Each inbound attempt also records a replay-window row. Rejected records write a
dead-letter row with the rejection reason. The default implementation is JSONL;
larger deployments can move the same record shape to a database-backed replay
window and review queue.

## Minimal API

```python
from cognitive_firm.orchestration.inbound_events import (
    ingest_inbound_event,
    register_inbound_projection,
)

def project_issue_updated(payload):
    return "external.issue.updated", f"linear/{payload['id']}", {
        "state": payload.get("state"),
    }

register_inbound_projection("linear", "issue.updated", project_issue_updated)

ingest_inbound_event(
    provider="linear",
    event_type="issue.updated",
    external_event_id="evt_123",
    payload={"id": "LIN-1", "state": "Done"},
    signature="sha256=...",
    signing_secret="tenant-owned-secret",
)
```

## T1 / T2

| Concern | T1 | T2 upgrade |
|---|---|---|
| Signature | optional HMAC check | provider-specific signature schemes, key rotation |
| Idempotency | provider/event/digest key plus JSONL replay-window record | durable replay-window backend |
| Projection | Python function registry | versioned schemas and conformance fixtures |
| Quarantine | JSONL quarantine and dead-letter logs | review queue, alerting, escalation policy |
| Authority | event remains observation | policy decides which accepted events may trigger work |

## Provider Adapters

Provider-specific adapters keep header conventions out of the generic
inbound-event primitive. They should parse provider headers, compute or verify
the provider signature format, and then call `ingest_inbound_event`.

The shipped provider adapters are GitHub, Linear, and Stripe webhook ingestion:

```python
from cognitive_firm.orchestration.inbound_provider_adapters import (
    github_signature,
    ingest_github_webhook,
    ingest_linear_webhook,
    ingest_stripe_webhook,
    linear_signature,
    stripe_signature_header,
)

record = ingest_github_webhook(
    headers={
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": "delivery-1",
        "X-Hub-Signature-256": github_signature(payload, "secret"),
    },
    payload=payload,
    signing_secret="secret",
)
```

The adapter maps GitHub event, delivery, and signature headers into the generic
inbound-event record. The deterministic projection registry still decides
whether the payload becomes a kernel event or goes to quarantine.

Provider adapters accept `raw_body` and should verify signatures against the
exact bytes received from the provider. The canonical JSON signature helpers
exist for local replay fixtures when no raw HTTP body is available.

The Linear adapter maps `Linear-Event`, `Linear-Delivery`, and
`Linear-Signature` into the same primitive and checks the `webhookTimestamp`
freshness field when present.

The Stripe adapter maps `Stripe-Signature` headers with `t=...` and `v1=...`
entries into the same primitive and checks timestamp tolerance. Stripe requires
verification against the raw request body.

## Standards Context

OpenAPI webhooks, AsyncAPI, and CloudEvents are useful event-description
standards. The kernel does not need to own those specs; it needs a stable
ingestion boundary that verifies, deduplicates, quarantines, and projects
external observations into kernel events.
