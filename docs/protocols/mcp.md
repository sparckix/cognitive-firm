# MCP — Model Context Protocol bridge

**Status:** Phase 1 (outbox-relay) + Phase 1.5 (transport + Linear binding) + Phase 2 (capability tokens) shipped. Phase 3 (supply-chain pinning) + Phase 4 (IdP federation) deferred until concrete adopter demand.
**Module:** `cognitive_firm.role_extensions.mcp_bridge`
**Tests:** 30 across `tests/test_mcp_outbox_relay.py` (6) + `tests/test_mcp_linear_server.py` (7) + `tests/test_mcp_capabilities.py` (15) + `tests/test_mcp_transport.py` (2).
**Design provenance:** the architecture below was selected by a three-panel adversarial review (enterprise-security architect + distributed-systems skeptic + M-Form invariant auditor) before any code was written.

MCP defines how role offices reach external enterprise systems (Linear, Salesforce, ERPs, ticketing, comms) without filesystem-as-truth contortions. The kernel governs **action**, not state — the world's state stays where the world keeps it.

## Core architectural decision

The kernel writes MCP requests once to the transition log; follow-up state is
derived from that log. This is the transactional outbox pattern. Locally,
`transitions.jsonl` is the ordered outbox; an MCP relay reads pending rows,
dispatches allowed calls, and appends a deterministic result row.

## Schema: the three event types

Every MCP call appears in `transitions.jsonl` as exactly one request followed by exactly one response.

### `mcp_call_requested` (the outbox row)

The kernel writes this BEFORE attempting the call. Crash between write and dispatch is recoverable on the next relay tick.

```json
{
  "event": "mcp_call_requested",
  "ts": "2026-05-07T...",
  "actor": "reviewer",
  "role_id": "reviewer",
  "surface": "mcp_bridge",
  "subject": "linear_seam_lookup",
  "causality_id": "obj_customer_import",
  "payload": {
    "server_name": "linear",
    "tool_name": "list_issues",
    "request": {"team": "ENG"},
    "timeout_seconds": 30.0,
    "idempotency_key": "<sha256 of causality_id + canonical(request)>"
  }
}
```

### `mcp_call_dispatched` (success follow-up)

```json
{
  "event": "mcp_call_dispatched",
  "ts": "...",
  "actor": "outbox_relay",
  "role_id": "reviewer",
  "surface": "mcp_bridge",
  "subject": "requested:<event_id>",
  "causality_id": "<event_id of the request>",
  "payload": {
    "requested_event_id": "<event_id of the request>",
    "response": {"<deterministic projection of the server's response>"},
    "rejection": null
  }
}
```

### `mcp_call_failed` (failure follow-up)

Same shape as `mcp_call_dispatched` but with `event = "mcp_call_failed"` and `rejection` carrying the human-readable reason. Common rejections:

- `no projection registered for <server>/<tool>` — server/tool pair lacks a deterministic projection function. **The relay refuses to LLM-interpret the response.** Phase 2 capability check fails.
- `role <X> has no MCP capabilities granted` — capability token check failed.
- `role <X> has no active capability for <server>/<tool>` — role has caps but not for this tool.
- `local de-dup cache hit (already dispatched in this process)` — idempotency safety net.
- Transport-layer errors (timeout, HTTP 5xx, malformed JSON, etc.).

## The three layers

### OS layer (unchanged)

`transitions.jsonl` + git history are the system of record. The kernel does not mirror external state; it records attempted actions. Divergence between cognitive-firm's view and (e.g.) Salesforce's view is **the steady state**, not a damage signal.

### Config layer (extended at Phase 2)

Mandate now carries `authorized_mcp_capabilities`:

```yaml
authorized_mcp_capabilities:
  - server: linear
    tools: [list_issues, get_issue, list_projects]
    scope: read_only
    rationale: |
      Research director cross-references seam IDs against the issue
      tracker. Read-only; no write tools.
```

Each capability is principal-signed (the principal authoring or editing the mandate is the signing event). Capabilities can be:

- **Mandate-lifetime** (`task_id = null`) — granted as long as the mandate references them.
- **Task-bound** (`task_id = <some_task>`) — revoked when the task closes via `revoke_task_capabilities(role_id, task_id)`.
- **Time-bounded** (`expires_at_iso = <ISO timestamp>`) — auto-expire.

The `rationale` field is required at grant time; the kernel refuses empty rationale because the principal must articulate why every capability exists.

### App layer (the relay)

`outbox_relay.dispatch_pending(log_path, max_dispatches=5, transport=None)` reads pending `mcp_call_requested` rows, computes the deterministic idempotency key, performs the capability check, calls the transport, projects the response, and appends the follow-up row. Crash-safe by construction (the request row exists durably before any dispatch attempt). Idempotent on retry (same causality + same payload = same key = server-side or local de-dup).

## Deterministic response projection

Per the M-Form invariant auditor's finding: when an MCP server returns ambiguous data (e.g., `{"status": "pending-review"}`), **something must adjudicate**. If an LLM at the App layer adjudicates and that interpretation flows back into a kernel transition, T2 (deterministic enforcement) has been silently broken — a learned parameter has entered the M-Form's enforcement floor via the transition's *meaning*, not its *signature*.

The fix: every (server, tool) pair must have a registered deterministic projection function:

```python
def _project_list_issues(response: dict) -> ProjectionResult:
    if not isinstance(response, dict) or "result" not in response:
        return ProjectionResult(
            transition_class="mcp_call_failed",
            normalized_payload={},
            rejection_reason="missing 'result' in JSON-RPC response",
        )
    issues = response["result"].get("issues") or []
    summary = [
        {"id": str(it.get("id", "")), "title": str(it.get("title", ""))[:200]}
        for it in issues if isinstance(it, dict)
    ][:100]
    return ProjectionResult(
        transition_class="mcp_call_dispatched",
        normalized_payload={"count": len(summary), "issues": summary},
    )

register_projection("linear", "list_issues", _project_list_issues)
```

Unregistered server/tool pairs are REJECTED with a clear reason. The relay never falls back to LLM interpretation. This is invariant **I6** in the property-based test suite.

## Transport layer

`transport.py` provides `call_mcp_tool(server, tool, request, idempotency_key, timeout)` over:

- **stdio** — for MCP servers that ship as local executables. The transport spawns the executable as a subprocess, writes the JSON-RPC payload to stdin, reads the response from stdout.
- **Streamable HTTP** — for hosted MCP servers. The transport initializes a
  session, sends MCP protocol/version headers, then issues `tools/call`.
- **legacy HTTP JSON-RPC** — for older servers that still expose a simple POST
  endpoint.

Auth tokens live in environment variables, never in `org/`. A mandate edit revoking a capability halts dispatch immediately; a token rotation requires a daemon restart.

## Shipped server bindings

Phase 1.5 ships one server binding as a worked example:

### `linear` (read-only)

```python
LINEAR_SPEC = ServerSpec(
    name="linear",
    transport="streamable_http",
    url="https://mcp.linear.app/mcp",
    auth_env_var="LINEAR_API_KEY",
    timeout_seconds_default=30.0,
)
```

Three projections registered: `list_issues`, `get_issue`, `list_projects`. Write tools (create / update / transition) deferred to Phase 2 because they require capability tokens that the principal has explicitly approved per role.

The Linear projection accepts both direct JSON-RPC result payloads and the
current Streamable HTTP shape where tool output is returned as JSON text inside
`result.content[]`.

### To enable Linear in production

1. Set `LINEAR_API_KEY` in the daemon's env.
2. Add to a role's mandate:
   ```yaml
   authorized_mcp_capabilities:
     - server: linear
       tools: [list_issues, get_issue, list_projects]
       scope: read_only
       rationale: "describe why this role needs Linear read access"
   ```
3. Import the binding once at daemon boot:
   ```python
   from cognitive_firm.role_extensions.mcp_bridge.servers import linear  # noqa
   ```
4. Roles can now emit `mcp_call_requested` rows with `server_name: "linear"`.

Optional live smoke:

```bash
LINEAR_API_KEY=... python scripts/mcp_linear_live_smoke.py --tool list_projects
```

The live smoke is intentionally outside `make smoke-public` because it requires
network access and a tenant-owned credential. It should return
`"transition_class": "mcp_call_dispatched"`.

## Threat-model coverage

| Primitive | T1 (single-principal) | T2 (regulated enterprise) |
|-----------|----------------------|---------------------------|
| Outbox-relay (Phase 1) | shipped | T2-relevant relay checks shipped |
| JSON-RPC transport stdio + HTTP (Phase 1.5) | shipped | T2-relevant transport checks shipped |
| Deterministic projection registry | shipped | T2-relevant projection checks shipped |
| Local de-dup cache | shipped | T2-relevant local idempotency checks shipped |
| Linear server binding (read-only) | shipped | projection fixture shipped; deployment auth remains tenant-owned |
| Capability tokens (Phase 2) | shipped | T2-relevant capability checks shipped |
| Task-scoped capability lifetime | shipped | T2-relevant lifetime checks shipped |
| Server image-digest pinning (Phase 3) | not needed | **queued** — supply-chain |
| Signed tool-manifest hash (Phase 3) | not needed | **queued** |
| Revocation feed for compromised servers (Phase 3) | not needed | **queued** |
| Declared-egress allowlist (Phase 3) | not needed | **queued** |
| Per-call short-lived IdP credentials (Phase 4) | not needed | **queued** |
| Write-capable server bindings | not yet — design pending | **queued** behind capability tokens |

## Phase 3 + Phase 4 — what they would add

**Phase 3 — supply chain.** When a third-party MCP server ships a malicious or
buggy update, what prevents the next call from executing it? The proposed
answer requires:

- **Image digest pin** at the Config layer (not server name; immutable image hash).
- **Signed tool-manifest hash** (the principal-signed contract for what tools the server is approved to expose).
- **Revocation feed** the daemon checks each tick; quarantines any pinned server whose digest is on the feed.
- **Declared-egress allowlist** enforced at the network layer (firewall rules), not the agent layer.

**Phase 4 — IdP federation.** The mandate authorizes "role R may invoke server S under federated identity I"; IdP resolves I → short-lived credential per call. Refresh tokens never live in `org/`. Mandate edits revoke immediately and cannot be replayed.

Both phases are speculative until a concrete enterprise adopter signals interest with a real threat model. Speculatively designing them tends to over-fit the wrong adversary.
