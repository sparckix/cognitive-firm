# Kernel Event Envelope

**Module:** `cognitive_firm.orchestration.kernel_events`

The kernel event envelope is the canonical event contract for newer
primitives. The local event stream is the transition log, and every transition
row embeds this envelope as `kernel_event`. Existing T1 primitives may still
keep local JSONL state records for their own lifecycle, but event/outbox writes
share one kernel-event shape.

## Fields

Each `KernelEvent` includes:

- `event_id`;
- `schema_version`;
- `occurred_at_utc`;
- `recorded_at_utc`;
- `actor`;
- `verb`;
- `object_ref`;
- `subject_ref`;
- `tenant_id`;
- `project_id`;
- `causation_id`;
- `correlation_id`;
- `idempotency_key`;
- `payload`;
- `payload_hash`.

## Boundary

This envelope does not replace every existing primitive-specific adapter. It
defines the small event shape that conformance tests, migrations, projections,
and future T2 backends can rely on.

Current source-of-truth boundary:

- `transition_log.py` is the T1 local event/outbox stream and embeds
  `kernel_event` on each row;
- `kernel_events.py` is the envelope and compatibility adapter, not a second
  default governance ledger;
- `state_backends.py` is the transport boundary for filesystem/SQLite/Postgres
  event sources.

Do not create a second governance event ledger. If a test or migration needs a
raw `KernelEvent` JSONL file, it must pass an explicit path. The default
storage path is the transition stream with embedded `kernel_event`.

Orbit's `event-bus.ts` is also not a governance ledger. It is an optional
projection/broadcast helper for UI experiments. App surfaces submit mutations
through the kernel service; durable local governance events flow through the
transition log with embedded `kernel_event` envelopes.

The helper `event_from_legacy_transition(...)` projects older transition-log
rows into the envelope so the kernel can migrate gradually.

`append_transition(..., event_source=...)` can write the same transition row
through any `EventSource`. This is the migration bridge from plain JSONL to
filesystem/SQLite/Postgres-like event backends while preserving existing row
semantics.

Default local path:

```text
cognitive_firm_workspace/transitions.jsonl
```

## Tests

Covered by `tests/test_kernel_events.py`.
