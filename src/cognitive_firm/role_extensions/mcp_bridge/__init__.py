# Licensed under Business Source License 1.1 — see LICENSE-BSL
"""GP-231 MCP bridge.

The bridge sits at the App layer of the OS / Config / App decomposition.

Architecture (per GP-231 panel verdict 2026-05-07):

  1. The kernel writes ONE transition per attempted MCP action via
     `cognitive_firm.orchestration.transition_log.append_transition`. The
     event class is `mcp_call_requested` with the call's payload. This row
     is the outbox entry; durability is git+jsonl. The kernel writes BEFORE
     the call is dispatched.

  2. `outbox_relay.dispatch_pending` reads pending `mcp_call_requested`
     rows that have not yet been marked dispatched, computes a deterministic
     idempotency key from `causality_id + payload hash`, issues the call
     to the MCP server, and appends a follow-up transition
     (`mcp_call_dispatched` on success, `mcp_call_failed` on error).
     Crash-safe: a process death between the call and the follow-up
     transition is recovered on next relay tick — the call repeats with
     the SAME idempotency key, so the server's idempotency check (or a
     local de-dup cache) prevents double-write.

  3. `projections` holds deterministic response-to-transition-class
     projection functions registered per (server, tool). Ambiguous returns
     that no projection function recognizes are rejected and emit a
     `mcp_response_unprojectable` damage signal — they do NOT flow into
     LLM-interpretation at this layer (that would smuggle a learned
     parameter into the M-Form's enforcement floor, breaking T2).

Phase 1 ships the bare relay + projection registry with no server bindings.
Phase 1.5 wires the first read-only server (Linear). Phase 2 adds capability
tokens at the Config layer. Phase 3 adds supply-chain pinning. Phase 4 adds
IdP federation. See GP-231 seam for the full plan.
"""

from cognitive_firm.role_extensions.mcp_bridge.outbox_relay import (  # noqa: F401
    dispatch_pending,
    pending_count,
)
from cognitive_firm.role_extensions.mcp_bridge.projections import (  # noqa: F401
    register_projection,
    project_response,
    ProjectionResult,
)
from cognitive_firm.role_extensions.mcp_bridge.transport import (  # noqa: F401
    ServerSpec,
    register_server,
    registered_servers,
    get_server_spec,
    call_mcp_tool,
)
