# A2A — Agent-to-Agent Protocol

**Status:** shipped for single-principal governance kernels at T1; remote-adapter work remains queued for T2 deployments.
**Module:** `cognitive_firm.orchestration.agent_channels` + `cognitive_firm.orchestration.artifact_dependencies` + `cognitive_firm.orchestration.a2a_projection`
**Tests:** 38 across `tests/test_obligation_lifecycle.py` (18) + `tests/test_artifact_dependencies.py` (14) + downstream MCP integration.

A2A defines how role offices communicate with each other inside cognitive-firm. The kernel records every message as a durable JSON envelope; coordination authority (gates, claims) lives elsewhere; this protocol is for typed communication and dependency tracking.

## Message envelope

Every A2A message is an `AgentMessage` (frozen dataclass) with the following fields:

| Field | Type | Purpose |
|-------|------|---------|
| `schema_version` | int | Currently 1. Increments on breaking change. |
| `message_id` | str | UUID-derived; `msg_<32hex>`. |
| `thread_id` | str | Defaults to `message_id`; replies share the originator's thread. |
| `kind` | enum | One of seven performatives, see below. |
| `from_role` | str | Sender role id, validated against `org/roles/`. |
| `to_role` | str | Receiver role id, validated. |
| `subject` | str | Short header. |
| `body` | str | Free-form content. |
| `status` | enum | Envelope state: `open` / `acknowledged` / `closed`. |
| `obligation_state` | enum or null | Work state, distinct from envelope state. See lifecycle below. |
| `parent_obligation_id` | str or null | For saga compensation chains. |
| `created_utc` | str | ISO 8601 timestamp. |
| `causality_id` | str or null | Originating cause for cross-message correlation. |
| `expects_response` | bool | If true, missing response surfaces a damage signal. |
| `expires_utc` | str or null | If past current time, obligation transitions to `expired`. |
| `references` | list[str] | URIs of related messages or files. |
| `artifacts` | list[str] | Paths or content-hashes of attached artifacts. |
| `metadata` | dict | Free-form extensions (channel_policy reason, etc.). |

## Performatives (message kinds)

cognitive-firm ships 7 of FIPA-ACL's ~20 performatives. The seven cover all production traffic to date:

- **`request`** — sender asks the receiver to do work. **Carries an obligation.**
- **`proposal`** — sender suggests an action; receiver may accept or refuse. **Carries an obligation.**
- **`handoff`** — sender transfers an in-flight task to the receiver. **Carries an obligation.**
- **`inform`** — sender shares information with no implied work. No obligation.
- **`clarification`** — sender asks a question or answers one. No obligation by itself.
- **`refusal`** — sender declines an obligation it received. Closes the parent obligation.
- **`status`** — periodic update on an in-flight obligation. No new obligation.

## The obligation lifecycle (Phase A)

The single most-leveraged primitive A2A adds. Standard message protocols conflate "did the receiver read this?" with "did the work get done?" — cognitive-firm separates them.

- **Envelope status** (`open` / `acknowledged` / `closed`) tracks whether the receiver opened the message.
- **Obligation state** tracks whether the work the message obliges has been done.

Only `request`, `proposal`, and `handoff` carry obligations. The other four kinds have `obligation_state = null`.

### State machine

```
        ┌─────────┐
   ─→  │ pending  │
        └────┬────┘
             │
        ┌────┴────────────────────────────┐
        │                                 │
        ▼                                 ▼
   ┌─────────┐                       ┌─────────┐
   │ accepted│                       │ refused │ ← terminal
   └────┬────┘                       └─────────┘
        │
        ▼
   ┌──────────────┐  ←──┐
   │ in_progress  │     │
   └────┬─────────┘     │
        │               │
        ▼               │
   ┌────────────────┐ ──┘
   │ blocked_input  │
   └────┬───────────┘
        │
        ▼
   ┌────────────┐
   │ fulfilled  │ ← terminal
   └────────────┘

Plus: any state → expired (terminal) when expires_utc is past.
```

The legal-transitions table lives in `agent_channels.py:_OBLIGATION_TRANSITIONS`. Illegal transitions raise `ValueError` at `update_obligation_state` time. The "no skip" rule (`pending → fulfilled` is rejected) is what catches "agent claimed done without doing the work" cases.

### Audit

Every state change appends a `agent.obligation.<state>` row to `transitions.jsonl` carrying `from_state`, `to_state`, `parent_obligation_id`. The audit trail records the work-state evolution alongside the envelope-state evolution.

### Why this matters at T1

Without obligation lifecycle, "B is blocked waiting on A" is only inferable from open messages. With it, the manager-role daemon and Orbit can render the structural view directly via `list_blocked_obligations()`.

### Bridge to human work sessions

Some obligations cannot be fulfilled by an agent alone because they require
human access, taste, judgment, relationship work, or non-digitized external
action. In those cases the A2A obligation remains the role-to-role work
contract, and H2A records the human side as a human work session with
`obligation_id=<message_id>`.

When the receiving role asks the human for that work, use the A2H helper
`create_agent_requested_human_work_session(...)`. This records the bounded
deliverable and keeps `agent_followup_required=true`, so the role cannot treat
the human's contribution as equivalent to obligation fulfillment until it is
integrated.

This keeps the boundary clean:

- A2A does not pretend the human interaction is just another agent message.
- H2A does not grant execution authority; it records bounded human work,
  receipts, and whether agent follow-up is required.
- The closing role can query human work sessions by obligation id before
  moving the obligation to `fulfilled`.

### Why this matters at T2

Saga compensation (Phase C, see below) cannot be implemented without obligation state distinct from envelope state. You cannot compensate what you cannot lifecycle.

## Channel policy

`channel_allowed(from_role, to_role)` enforces a conservative local policy. Permitted directions:

1. Self-messages (any role to itself).
2. From any role to `manager` or `principal` (escalation channel).
3. From `manager` to anyone (coordination channel).
4. Receiver appears in sender's `delegates_to` or `escalates_to` (and vice versa).

Anything else raises `ChannelPolicyError`. The policy is intentionally simple:
local channel hygiene, not enterprise RBAC. A control-plane policy compiler can
replace it when adopters need richer authorization.

## Dependency primitive (Phase B): content-addressed artifact promises

Module: `cognitive_firm.orchestration.artifact_dependencies`.

The structurally hardest A2A question is "task B depends on task A's output."
cognitive-firm's answer reuses the local outbox/event adapter
(`transitions.jsonl`) and ships these primitives:

### Producer side

```python
promise_artifact(
    role_id="reviewer",
    task_id="task_validate_X",
    artifact_key="validator.results.X",
    predicate="schema_version >= 2 AND score >= 0.7",
    expires_at_utc="2026-05-14T...",
)
# → emits task.artifact.promised row with deterministic predicate_hash

# … work happens …

fulfill_artifact(
    role_id="reviewer",
    task_id="task_validate_X",
    artifact_key="validator.results.X",
    artifact_path="tenant_workspace/validator/X.json",
    sha256="9af3...",
    predicate="schema_version >= 2 AND score >= 0.7",
    predicate_eval={"schema_version_ge_2": True, "score_ge_0_7": True},
)
# → emits task.artifact.fulfilled with content_hash + per-clause eval
```

### Consumer side

```yaml
# In role yaml (or task yaml)
awaits:
  - artifact_key: validator.results.X
    predicate_hash: p_h7c2
```

The work-discovery scanner calls `is_awaits_satisfied(awaits)` and treats tasks with unsatisfied awaits as non-candidates. Non-satisfied means: no fulfilled row yet, OR any predicate clause evaluated False, OR the matching promise's TTL has expired.

### Predicate-hash drift detection

`predicate_hash(text)` is a stable short hash. A mandate revision that changes the predicate text changes the hash, which means consumers' `awaits` (referencing the old hash) stop matching. Downstream tasks halt until they update — the structural fix for silent stale-success.

### Auxiliary primitives

- `rebuild_artifact_index(log_path)` → `dict[artifact_key, list[offset]]` rebuilt from the log on startup.
- `check_dependency_cycles(awaits_by_task, promises_by_task)` → DFS-based static cycle detection. Returns cycle paths (empty list = clean DAG).
- `artifact_key_concentration(window_hours=168)` → biological-panel calibration nudge: warns when one artifact_key dominates ≥ 70% of recent fulfillments. Trail-reinforcement bias monitor.

## Phase C: saga compensation (shipped)

A saga is a sequence of obligations across roles that must either all succeed or all be undone. cognitive-firm uses the Phase A `parent_obligation_id` as the chain backbone and ships the rollback resolver in `src/cognitive_firm/orchestration/saga_compensation.py` (tests in `tests/test_saga_compensation.py`).

**What Phase C ships:** when an obligation transitions to `refused` or `expired`, the kernel walks the `parent_obligation_id` chain back to the root. For each ancestor in `fulfilled` state, it emits a compensating `request` to the ancestor's original actor, carrying the failed terminal's id as the new `parent_obligation_id`. The compensation request body explains *why* (the downstream chain failed) but does not prescribe *how* — only the original role knows what undoing its action means. The compensations form their own chain, so a refused compensation can itself surface a `saga_compensation_unfulfilled` damage signal for principal review.

Public API:

- `compensate_failed_obligation(role_id, message_id, reason)` → returns the list of compensation messages emitted.
- `list_active_sagas(window_hours)` → returns chains with at least one in-flight compensation; consumed by Orbit.
- `check_compensation_freshness(stale_after_hours=24)` → returns compensation requests stuck in `pending` past their staleness window — these fire `saga_compensation_unfulfilled`.

**Why it matters:** without saga, partial-failure recovery is manual git-revert. Acceptable for T1 (single principal, trusted hardware, low-stakes). Unacceptable for T2 (regulated enterprise, where some actions have external side effects that git cannot revert — Salesforce activity records, money movement, external notifications). T2 reactivation depends on this primitive.

## Agent-card projection

`a2a_projection.AgentCard` projects a role's authorized public surface for compatibility with Google A2A and IBM ACP discovery formats. Cards are **discovery-only, NOT authority** — the authority layer remains role yaml + mandate file. This is the structural difference from Google A2A, which conflates routing with execution authority.

`build_all_agent_cards()` writes one card per role under the configured tenant
workspace's `a2a/agent_cards/` path. External A2A/ACP adapters can import
these cards without granting any execution authority.

## Threat-model coverage

| Primitive | T1 (single-principal) | T2 (regulated enterprise) |
|-----------|----------------------|---------------------------|
| Typed AgentMessage envelope | shipped | shipped |
| 7 performatives | shipped | shipped (FIPA-ACL expansion to 12 deferred) |
| Channel policy (delegation/escalation) | shipped | shipped (RBAC compiler queued) |
| Obligation lifecycle (Phase A) | shipped | shipped |
| Artifact dependencies (Phase B) | shipped | shipped |
| Predicate-hash drift detection | shipped | shipped |
| Saga compensation (Phase C) | shipped (overkill for T1 but exercised) | shipped — load-bearing |
| Remote A2A/ACP adapter | not needed | **queued** — interop |
| Idempotent at-least-once delivery | not needed (single-machine) | **queued** |
| Conformance test suite | local tests shipped | **queued** for remote-adapter interoperability |

## Distance to publishable reference implementation

Per the 2026-05-07 audit panel: ~80-120 agent-hours from local primitive to "submittable as a 2026 A2A reference implementation." Phase A + B + C account for ~40 of those hours and shipped. Remaining ~40-80 hours: remote adapter, performative expansion, idempotent delivery semantics, conformance suite, full spec doc — held until adopter signal.
