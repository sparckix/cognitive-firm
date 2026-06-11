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

## Executable Adapter Boundary

An adapter may be a Python package, a local command, a containerized service, or
a hosted API. The conformance question is the same in each case: does the
adapter preserve the kernel boundary?

For executable adapters, a supported integration should document:

- the command, package, image, or endpoint reference;
- version, digest, signature, or public-key trust material where the deployment
  requires it;
- the kernel protocol it writes into (`RuntimeEvent`, MCP outbox/projection,
  inbound event, formal-verification provider payload, state backend, or
  notification provider);
- a deterministic fixture that exercises accepted input, denied authority,
  malformed input, replay/idempotency, provider failure, and projection shape.

The package installer can install the governance policy and conformance
fixtures for an executable adapter. It should not hide executable installation
inside an organization overlay.

## Adapter Manifest

Adapter packs can install a durable adapter manifest under the target
organization, typically in `adapters/<adapter-id>.yaml`. The manifest declares
the external executable or service, the kernel protocol it writes into, and the
conformance checks expected before the adapter is treated as supported.

Minimal shape:

```yaml
schema_version: cognitive-firm-adapter-manifest/v1
adapter_id: langgraph-runtime-adapter
family: runtime
protocol: runtime_event
description: Maps LangGraph lifecycle callbacks into runtime event rows.
executable:
  kind: python_package
  ref: cognitive_firm_langgraph_adapter
  version: 0.1.0
  digest: sha256:...
  install_hint: Install the adapter in the same Python environment as LangGraph.
trust_requirements:
  conformance_fixture: required
conformance_checks:
  - started_event_idempotent
  - interrupt_creates_human_work
evidence_refs:
  - tests/test_runtime_adapters.py
```

Validate a manifest locally:

```bash
cognitive-firm-adapter-conformance validate-manifest adapters/langgraph-runtime-adapter.yaml
```

This validation does not run or install the executable. It only checks that the
manifest is a well-formed declaration over a known adapter family and protocol.
Runtime-specific tests remain ordinary conformance fixtures.

## Conformance Config

Adapter-policy packages can also install a conformance config, usually under
`adapter_conformance/<adapter-id>.json`. The config records the fixture command
and the evidence paths an org expects before treating the external adapter as
supported.

Validate the config by itself:

```bash
cognitive-firm-adapter-conformance validate-conformance \
  adapter_conformance/langgraph-runtime-adapter.json
```

Validate it against the installed adapter manifest and local evidence files:

```bash
cognitive-firm-adapter-conformance validate-conformance \
  adapter_conformance/langgraph-runtime-adapter.json \
  --manifest adapters/langgraph-runtime-adapter.yaml \
  --evidence-root .
```

This catches package drift: mismatched adapter ids, mismatched protocols,
manifest checks missing from the config, or evidence refs that no longer exist.
It still does not execute the adapter. Running the fixture command remains the
adapter author's ordinary test or CI job.

The same config shape applies to provider adapters. For example, the
`leanmill-formal-verification` overlay declares
`protocol=formal_verification_provider_payload` and points its fixture command
at `make formal-provider-bundle-demo`.

Packages do not need a separate lint command for these files.
`cognitive-firm-distro lint <package>` automatically validates any
`files/adapters/*.{yaml,yml,json}` and `files/adapter_conformance/*.{json,yaml,yml}`
files it finds, including manifest/config alignment when both are present.

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
