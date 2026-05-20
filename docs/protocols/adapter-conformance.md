# Adapter Conformance

Adapters connect the kernel to apps, runtimes, providers, identity systems, and
tenant overlays. An adapter is supported only when its behavior is testable in
the same shape as the kernel primitives it touches.

## Conformance Matrix

| Adapter family | Must prove |
|---|---|
| App surface | typed intent, actor context, denied-authority case, no direct durable-file write |
| Inbound event | signature or authenticity fixture, idempotency, replay window, dead-letter/quarantine |
| Outbound enterprise system | capability/mandate check, outbox record, provider result projection, retry safety |
| Runtime | start/checkpoint/interrupt/resume/fail mapping, opaque runtime token handling |
| Notification | delivery intent, provider abstraction, failure visibility, no credential leakage |
| Identity provider | authenticated subject facts, actor mapping, membership scope, revocation behavior |
| State backend | append/read, idempotency or transaction boundary, backup/restore or replay semantics |
| Tenant adapter | summary shape, source-health labels, no tenant policy hidden in kernel code |

## Golden Cases

Every adapter should include deterministic fixtures for:

- accepted request;
- denied authority;
- duplicate or retry;
- stale replay or stale lease;
- malformed payload;
- provider failure;
- projection shape.

Live credentials may have optional smoke tests. Public checks should use
fixtures so adopters can run the repo without private accounts.

## Boundary

MCP, webhooks, OAuth, SAML, OIDC, Slack, Linear, GitHub, and graph runtimes own
their transport semantics. The kernel owns organizational authority,
provenance, evidence, accountability, and learning records created by those
transports.
