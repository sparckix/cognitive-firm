# cognitive-firm protocols

This index names the four protocols cognitive-firm defines. Each protocol has its own spec under `docs/protocols/`.

The protocols sit on the OS / Config / App layer separation from the companion paper:

```
┌────────────────────────────────────────────────────────────────────┐
│  PRINCIPAL (human)                                                 │
│  ↕ H2A protocol — Telegram, Orbit, CLI                             │
└──────────────────────────┬─────────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────────┐
│  ROLE OFFICES (research_director, manager, debate_runner, …)       │
│  ↕ A2A protocol — typed channels, obligation lifecycle,            │
│                   artifact dependencies                            │
└──────────────────────────┬─────────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────────┐
│  AGENT RUNTIMES (Claude, Codex, Gemini)                            │
│  ↕ MCP protocol — capability-gated tool dispatch                   │
└──────────────────────────┬─────────────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────────────┐
│  EXTERNAL SYSTEMS (Linear, Salesforce, ERPs)                       │
│  ← cognitive-firm reaches via MCP servers                          │
└────────────────────────────────────────────────────────────────────┘

Mandate protocol (orthogonal): typed contract files in org/mandates/*.md
defining what each role may do autonomously vs what requires escalation.
```

## The four protocols

### [A2A — Agent-to-Agent](protocols/a2a.md)

How role offices coordinate with each other inside the kernel. Typed `AgentMessage` envelopes, seven performative kinds (`request`, `proposal`, `handoff`, `inform`, `clarification`, `refusal`, `status`), an **obligation lifecycle** distinct from envelope status (so "B is blocked waiting on A's output" is structurally visible, not inferred), and a **content-addressed artifact-dependency primitive** so "task B requires task A's output X with property Y" is a typed event rather than implicit knowledge.

Status: best-in-class for single-principal governance kernels. Phase A (obligation lifecycle) + Phase B (artifact dependencies) shipped. Phase C (saga compensation) and remote adapter remaining for full publishable parity.

### [H2A — Human-to-Agent](protocols/h2a.md)

How the principal interacts with role offices. Three surfaces: **Telegram** (mobile pager + STOP authority), **Orbit** (desktop dashboard with TLDraw spatial canvas + governance pane + chat pane + damage feed), **CLI** (direct invocation for ops). Each surface has an explicit attention-layer assignment under Stewart Brand's pace-layering principle: slow (mandate config), working (tasks, hourly), fast (damage signals, seconds). The chat surface carries a persistent conversation state per role with cross-day memory and self-extending pinned facts.

Status: surfaces exist + are working in production. Spec is this document — first time it has been written down.

### [MCP — Model Context Protocol](protocols/mcp.md)

How role offices reach external enterprise systems (Linear, Salesforce, ERPs, ticketing). The kernel writes one `mcp_call_requested` row to `transitions.jsonl` (the outbox). An outbox-relay reads pending rows, dispatches via JSON-RPC to the registered MCP server (stdio or HTTP transport), applies a deterministic projection function to map the response into a typed transition class, and appends a follow-up event. **No LLM at projection** — ambiguous returns are rejected, not interpreted.

A capability-token primitive at the Config layer gates which (role, server, tool) tuples are permitted. Capabilities can be mandate-lifetime or task-bound (revoked when the task closes).

Status: Phase 1 (outbox-relay) + Phase 1.5 (transport + Linear binding) + Phase 2 (capability tokens) shipped. Phase 3 (supply-chain pinning: digest + signed manifest + revocation feed) and Phase 4 (IdP federation) deferred until concrete adopter demand.

### [Mandate](protocols/mandate.md)

The typed contract format that defines a role's authority. Each role has a `org/roles/<role_id>.yaml` file (the structured part: authorized_paths, forbidden_paths, budget caps, delegates_to / escalates_to, authorized_mcp_capabilities) and an `org/mandates/<role_id>_mandate.md` file (the prose part: discipline, run-vs-analyze rules, recursion guards, damage-signal classes). The kernel verifies the mandate hash each tick.

Status: production-stable since 2026-04. Schema documented inline in the role yaml + mandate templates.

## Honest scope

These specs describe **what is currently shipped**, not what is aspirational. Where a primitive is queued (Phase C saga, Phase 3 supply-chain) the spec says so explicitly. Adopters who read these docs to understand what they would integrate against can rely on every "shipped" claim being backed by tests in `cognitive-firm/tests/`. Test counts per primitive are listed in each protocol spec.

## Threat-model coverage

Each protocol spec ends with a threat-model table separating **T1** (single-principal, trusted-hardware) from **T2** (regulated enterprise, multi-tenant). Some primitives ship for both; some are queued at one and deferred at the other; some are explicitly out of scope. The discipline is to be honest about which adversary class each primitive defends against rather than to claim universal coverage.
