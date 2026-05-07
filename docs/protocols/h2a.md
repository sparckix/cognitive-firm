# H2A — Human-to-Agent Protocol

**Status:** production-stable on three surfaces (Telegram + Orbit + CLI). This spec is the first written-down version; the protocol existed in code for ~6 weeks before this doc.
**Modules:** `cognitive_firm.notifications.telegram`, `cognitive-firm/orbit/src/components/`, `cognitive_firm.orchestration.chat_handler`
**Tests:** 6 in `tests/test_telegram_callback_flow.py`; Orbit components have integration tests in their own subtree.

H2A defines how the principal (the human) interacts with role offices. cognitive-firm intentionally provides three surfaces with distinct attention semantics rather than one universal interface, because principal attention is the load-bearing constraint and different signal classes need different cadences.

## The pace-layered attention model

Following Stewart Brand's pace-layering principle, the H2A protocol assigns each signal class to one of three attention layers:

| Layer | Cadence | Surface | Signal classes |
|-------|---------|---------|----------------|
| **Slow** | weekly | CLI + Orbit governance pane | Mandate edits, role authorization changes, model-economy meta-mandate, principal-extension authority |
| **Working** | hourly | Orbit objective-tree + chat pane | Task-level direction, gate approvals, charter critiques, debate seam shepherding |
| **Fast** | seconds | Telegram + Orbit damage-feed | Damage signals, gate-pending alerts, STOP authority, agent-CLI utilization caps |

This layering is **not a feature** — it is the structural constraint that prevents principal attention from being consumed by fast-layer noise to the exclusion of slow-layer governance.

## Surface 1: Telegram (mobile pager)

Module: `cognitive_firm.notifications.telegram`. Stdlib-only (urllib + json), no third-party dependencies.

### Outbound (kernel → principal)

- `push_notification(text, *, gate_id=None, inline_buttons=None, priority=None)` — pushes a message to the principal's chat. When `gate_id` is provided, renders inline `APPROVE` / `SKIP` / `STOP` buttons that the principal taps; tapping triggers a callback that resolves the gate.
- `reply(text)` — lightweight follow-up to a recent inbound message.

### Inbound (principal → kernel)

- `poll_inbound(consume=True)` — polls the Telegram getUpdates endpoint with `allowed_updates=["message", "callback_query"]`. Recognized commands: `STOP`, `PAUSE`, `RESUME`, `STATUS`, `DIRECTIVE <text>`. Free-form text is classified as `DIRECTIVE`. Callback queries from inline buttons carry the original `gate_id` so the kernel can resolve the right gate (matching the button tap to the gate the kernel was waiting on).

### STOP authority

The principal's STOP is the kernel's hard-stop primitive. When STOP is received:

1. The daemon sets `org/signals/stop.flag`.
2. Every role's tick checks the flag at start; if set, the tick exits cleanly.
3. The agent-CLI subprocess is terminated if mid-dispatch.
4. The kernel records a `principal.stop` transition.

STOP is honored within one tick interval (worst case = the configured tick cadence; default 1800s for SRO, 600s for general daemon). Faster than that requires `RESUME` semantics that don't yet exist.

### What Telegram is NOT for

- Multi-turn conversation (use Orbit chat pane).
- Mandate editing (use CLI or Orbit governance pane).
- Long-form research direction (use Orbit objective-tree pane).

The discipline is to keep Telegram messages under 200 words and bounded to fast-layer signals.

## Surface 2: Orbit (desktop dashboard)

Module: `cognitive-firm/orbit/`. React + TLDraw spatial canvas + Express backend (`orbit-sync.service`).

### Components shipped

| Component | Purpose | Layer |
|-----------|---------|-------|
| `AgentOrb` / `AgentFace` / `AgentTile` | Each role's status surface | working |
| `BatchGateReview` | Approve/skip/stop multiple pending gates at once | working |
| `ChatPane` | Per-role chat with cross-day memory | working |
| `DamageSignalFeed` | Real-time damage-signal stream | fast |
| `FrontierStatePane` | Where the apparatus is on its current frontier | working |
| `GovernancePane` | Mandate edits, role config, authorization changes | slow |
| `MetaConfigPane` | Model-economy + principal-extension authority | slow |
| `ObjectiveTreePane` | Objectives → key results → tasks tree | working |

### TLDraw spatial canvas (per GP-167)

The dashboard's primary surface is a TLDraw spatial canvas where each role is a draggable orb whose position encodes the principal's mental model of that role's relationship to others. This is intentionally **not a hierarchical tree** — the kernel's authority graph is hierarchical (delegates_to / escalates_to in role yaml), but the principal's mental model rarely matches that hierarchy and forcing it produces high-friction UX.

Each orb shows: `role_id`, current obligation state (any `blocked_input` obligations surface visually), recent damage signals, and the role's last successful action.

### Real-time vs polled

The frontend polls the backend at 5s intervals for new chat messages, damage signals, and obligation-state changes. The backend reads from `transitions.jsonl` and `org/sessions/`. WebSocket push is implemented for Orbit-frontend ↔ orbit-sync but not yet wired through to the React layer (queued under future work).

### What Orbit is NOT for

- Hard-stop authority (use Telegram STOP — it works even when laptop is closed).
- Mobile use (Orbit is desktop-only by design; Telegram is the mobile pager).

## Surface 3: CLI

Direct shell invocation of scripts. Used for:

- Initial deployment (`scripts/setup_vps.sh`)
- Role preflight checks (`scripts/org_role_preflight.py`)
- Daemon dispatch (`scripts/agent_daemon.py`)
- One-shot operator tools

CLI is the slow-layer fallback. Any operation that has a CLI form should also have an Orbit form, but CLI is the source-of-truth interface — Orbit is a projection over CLI primitives.

## Persistent conversation state (Phase A of H2A chat)

Module: `cognitive_firm.orchestration.chat_handler`.

Per-role chat persists across days via two mechanisms:

### Cross-day history walkback

```python
read_messages_across_days(role_id, total_limit=20, max_days_back=14)
```

Walks back day-by-day until enough messages collected. The Telegram-style "fresh start each day" failure mode is structurally avoided.

### Self-extending pinned facts

The chat reply prompt includes the role's `conversation_state.json`:

```json
{
  "pinned_facts": [
    "principal cares about scientific discovery + recursive self-improvement",
    "VPS is Hetzner CCX23 at 49.13.160.58",
    "..."
  ],
  "ongoing_topics": [
    "GP-230 absorption verdict pending",
    "..."
  ],
  "last_updated": "2026-05-07T..."
}
```

The role's reply ends with a `STATE_UPDATE:` line containing a one-line JSON object describing what to add to `pinned_facts` / `ongoing_topics`. The handler parses it, merges, and persists. The role thus extends its own memory without requiring principal intervention — but the principal can edit the file directly to remove or correct entries.

This is the cognitive-firm-side mirror of the OpenAI / Anthropic / Google "system prompt + memory" pattern, but persisted in the kernel's filesystem of record rather than in vendor cloud storage.

## Decision tree: which surface for which signal

```
Is the principal's response time-critical (< 1 minute matters)?
├── YES → Telegram (with STOP / APPROVE buttons if action required)
└── NO
    ├── Is it a multi-turn conversation about strategy?
    │   └── Orbit ChatPane (with cross-day persistence)
    ├── Does it need spatial/visual context?
    │   └── Orbit TLDraw canvas
    ├── Is it a configuration change to mandates / roles?
    │   └── Orbit GovernancePane (or CLI)
    └── Is it ops / setup / one-shot tool invocation?
        └── CLI
```

## Threat-model coverage

| Primitive | T1 (single-principal) | T2 (regulated enterprise) |
|-----------|----------------------|---------------------------|
| Telegram outbound | shipped | shipped |
| Telegram inbound + callback | shipped | shipped |
| STOP authority | shipped | shipped |
| Inline gate-approval buttons | shipped | shipped |
| Orbit dashboard (10 components) | shipped | shipped |
| Cross-day chat persistence | shipped | shipped |
| Self-extending pinned facts | shipped | shipped |
| WebSocket push to React | partial (backend ready, frontend polls) | partial |
| Multi-principal Orbit | not needed | **queued** — RBAC + audit-of-who-approved-what |
| Mobile-only Orbit | not needed | **queued** if mobile principal cohort emerges |
| Federated SSO (Telegram bot per tenant) | not needed | **queued** |

## What this protocol explicitly does NOT define

- A unified inbox merging Telegram + Orbit messages. Principal experience showed that merging them hurts attention layering.
- A "voice mode" surface. No production demand.
- An asynchronous email surface. Slack / Teams adapters are queued under MCP (treating those as enterprise systems the kernel reaches via MCP, not as an H2A surface).
- A "follow-up reminder" primitive that re-pings the principal if a Telegram message goes unanswered. The principal's attention is sovereign; nagging is excluded by design.
