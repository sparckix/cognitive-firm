# H2A — Human-to-Agent Protocol

**Status:** implemented on three surfaces (notification channel + Orbit + CLI).
**Modules:** `cognitive_firm.notifications.channels`, `cognitive_firm.notifications.telegram`, `cognitive-firm/orbit/src/components/`, `cognitive_firm.orchestration.chat_handler`, `cognitive_firm.orchestration.human_work`
**Tests:** `tests/test_notification_channels.py`, `tests/test_telegram_callback_flow.py`, `tests/test_human_work.py`; Orbit components have integration tests in their own subtree.

H2A defines how the principal (the human) interacts with role offices. cognitive-firm intentionally provides three surfaces with distinct attention semantics rather than one universal interface, because principal attention is the load-bearing constraint and different signal classes need different cadences.

H2A covers three different interaction types:

- **Decision gates** — the human grants or denies authority.
- **Correction/editing** — the human repairs agent output or state.
- **Joint work** — the human performs bounded work alongside role offices and
  produces or changes an artifact.

The third category is represented by human work sessions in
`cognitive_firm.orchestration.human_work`.

When a role office initiates the human work, use the
[A2H work-coordination pattern](a2h.md). A2H is not a separate authority layer;
it is the standard way to encode an agent-requested human work session with a
named deliverable, receipt, and required follow-up.

## The pace-layered attention model

Following Stewart Brand's pace-layering principle, the H2A protocol assigns each signal class to one of three attention layers:

| Layer | Cadence | Surface | Signal classes |
|-------|---------|---------|----------------|
| **Slow** | weekly | CLI + Orbit governance pane | Mandate edits, role authorization changes, model-economy meta-mandate, principal-extension authority |
| **Working** | hourly | Orbit objective-tree + chat pane | Task-level direction, gate approvals, charter critiques, debate seam shepherding |
| **Fast** | seconds | Notification channel + Orbit damage-feed | Damage signals, gate-pending alerts, STOP authority, agent-CLI utilization caps |

This layering is **not a feature** — it is the structural constraint that prevents principal attention from being consumed by fast-layer noise to the exclusion of slow-layer governance.

## Surface 1: Notification Channel

Modules: `cognitive_firm.notifications.channels` and provider adapters such as
`cognitive_firm.notifications.telegram`.

The kernel emits notification intents. A concrete provider delivers them.
Telegram is the default T1 provider because it supports outbound alerts and
inbound callback buttons, but the protocol boundary is the notification intent,
not Telegram itself.

### Outbound (kernel → principal)

- `push_notification(text, *, gate_id=None, inline_buttons=None, priority=None)` — compatibility API that sends a notification intent through the configured provider. When the provider supports buttons and `gate_id` is provided, it can render inline `APPROVE` / `SKIP` / `STOP` buttons.
- `reply(text)` — lightweight follow-up to a recent inbound message.

### Inbound (principal → kernel)

- `poll_inbound(consume=True)` — provider-specific inbound poll. The Telegram adapter polls `getUpdates` with `allowed_updates=["message", "callback_query"]`. Recognized commands: `STOP`, `PAUSE`, `RESUME`, `STATUS`, `DIRECTIVE <text>`. Free-form text is classified as `DIRECTIVE`. Callback queries from inline buttons carry the original `gate_id` so the kernel can resolve the right gate.

### STOP authority

The principal's STOP is the kernel's hard-stop primitive. When STOP is received:

1. The daemon sets `org/signals/stop.flag`.
2. Every role's tick checks the flag at start; if set, the tick exits cleanly.
3. The agent-CLI subprocess is terminated if mid-dispatch.
4. The kernel records a `principal.stop` transition.

STOP is honored within one tick interval (worst case = the configured tick cadence; default 1800s for SRO, 600s for general daemon). Faster than that requires `RESUME` semantics that don't yet exist.

### What The Notification Channel Is NOT For

- Multi-turn conversation (use Orbit chat pane).
- Mandate editing (use CLI or Orbit governance pane).
- Long-form research direction (use Orbit objective-tree pane).

The discipline is to keep notification messages under 200 words and bounded to
fast-layer signals.

## Surface 2: Orbit (desktop dashboard)

Module: `cognitive-firm/orbit/`. React + TLDraw spatial canvas + backend sync service.

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

### TLDraw spatial canvas

The dashboard's primary surface is a TLDraw spatial canvas where each role is a draggable orb whose position encodes the principal's mental model of that role's relationship to others. This is intentionally **not a hierarchical tree** — the kernel's authority graph is hierarchical (delegates_to / escalates_to in role yaml), but the principal's mental model rarely matches that hierarchy and forcing it produces high-friction UX.

Each orb shows: `role_id`, current obligation state (any `blocked_input` obligations surface visually), recent damage signals, and the role's last successful action.

### Real-time vs polled

The frontend polls the backend at 5s intervals for new chat messages, damage signals, and obligation-state changes. The backend reads from `transitions.jsonl` and `org/sessions/`. WebSocket push is implemented for Orbit-frontend ↔ orbit-sync but not yet wired through to the React layer (queued under future work).

Orbit is an app projection over kernel state. Runtime policy controls whether
the backend accepts writes:

- `ORBIT_SURFACE_MODE=projection_only` disables all mutation endpoints.
- `ORBIT_SURFACE_MODE=kernel_intents` allows typed human intent endpoints.
- Writes require `ORBIT_API_TOKEN` on the backend and the same value exposed to
  the frontend as `VITE_ORBIT_API_TOKEN`.
- Write endpoints call the kernel service at
  `COGNITIVE_FIRM_KERNEL_SERVICE_URL`; Orbit does not directly write gates,
  directives, controls, chat, human-work state, or role utilization config.

### What Orbit is NOT for

- Provider-specific mobile paging.
- Policy ownership, scheduling, forecast scoring, or optimizer control.

## Surface 3: CLI

Direct shell invocation of scripts. Used for:

- Initial deployment (`scripts/setup_vps.sh`)
- Role preflight checks (`scripts/org_role_preflight.py`)
- Daemon dispatch (`scripts/agent_daemon.py`)
- One-shot operator tools

CLI is the slow-layer fallback. Any operation that has a CLI form should also have an Orbit form, but CLI is the source-of-truth interface — Orbit is a projection over CLI primitives.

## Joint Work Sessions

Module: `cognitive_firm.orchestration.human_work`.

Human work sessions record bounded work the human performs as part of a joint
activity with one or more role offices. Examples: source checks, edits,
external actions in restricted systems, relationship work, data entry,
judgment, or taste calls.

The session state machine is:

```text
requested -> claimed -> in_progress -> blocked -> handed_off | completed | abandoned -> integrated
```

Core fields include objective, human actor, requesting role, collaborating
roles, work mode, bottleneck class, artifact references, optional obligation
ID, integration reference, interaction surface, agent counterparty role, human
deliverable, and whether an agent follow-up is required.

Some human work is not digitized: conversations, offline reading, physical
checks, private judgment, or tacit taste. Human work sessions therefore include
observability and receipt fields. The kernel should not pretend to observe
private work directly; it records bounded claims such as `human_attested` or
`unobservable`, optional receipt requirements, confidence, and whether the
claim should be sampled for review.

For mixed or non-digitized work, the session can also carry structured
`interaction_events`: actor, event type, surface, summary, artifact refs,
blocker, and follow-up requirement. This captures "human did actual work with
the agent" without pretending the full private interaction is observable.

Sessions can be linked to A2A obligations through `obligation_id`. This makes
the distinction operational:

- A2A says which role is waiting on which work.
- H2A says which human work session is carrying the non-agent part of the work.
- `agent_followup_required` says whether a role office must consume the human
  result before the obligation can close.

The protocol therefore does not treat the human only as a decision gate. A
human can be an active work producer, with bounded receipts and artifact
references, while the agent remains responsible for integration.

This separates "needs your decision" from "you are doing work." The distinction
matters for bottleneck measurement: authority, taste, relationship, and safety
work may be intentionally human; repeated labor or access bottlenecks may
indicate an automation opportunity.

### Bounded world-contact pattern

Some useful human work is contact with the outside world that the kernel cannot
or should not observe directly. Examples:

- calling a partner and confirming a timeline;
- checking a restricted billing, HR, CRM, or bank system;
- reading a physical or private document;
- making a taste or legitimacy judgment that should not become a transcript.

Use a human work session for these cases. Do not create a separate world-contact
primitive unless the organization later needs an independent lifecycle or query
surface for the claim.

Recommended shape:

```json
{
  "work_mode": "external_action | relationship | source_check | judgment | taste_call",
  "observability": "external_system | human_attested | unobservable",
  "receipt_required": true,
  "receipt_type": "note | external_ref | witness | artifact_ref | none",
  "confidence": "low | medium | high",
  "sample_for_review": false,
  "agent_followup_required": true,
  "metadata": {
    "world_contact_kind": "external_system | human_relationship | physical_world | tacit_judgment | private_reasoning"
  }
}
```

For handoff back to an agent, append an `interaction_event` such as
`world_contact_attested`, `offline_call`, or `external_system_check`. The event
summary should be bounded to what the agent needs next. It should not store
private reasoning, relationship details, or full transcripts by default.

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
    "principal prefers short decision notes with source links",
    "service runs on the organization's private host",
    "..."
  ],
  "ongoing_topics": [
    "customer-import review pending",
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
├── YES → Notification channel (with STOP / APPROVE buttons if provider supports them)
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
| Notification channel facade | shipped | partial — provider identity/audit policy remains deployment-owned |
| Telegram outbound provider | shipped | partial — requires tenant authentication and retention policy |
| Telegram inbound + callback provider | shipped | partial — unauthorized callback audit and identity-backed tests queued |
| STOP authority | shipped in local/provider flow | partial — enterprise STOP requires identity-backed callback coverage |
| Inline gate-approval buttons | shipped | partial — subject attribution and audit hardening queued |
| Orbit dashboard (10 components) | shipped | partial — enterprise RBAC/admin UX queued |
| Cross-day chat persistence | shipped | partial — retention and subject attribution policy remains deployment-owned |
| Self-extending pinned facts | shipped | partial — approval and audit policy remains deployment-owned |
| Human work sessions + interaction events | shipped as filesystem adapter | shipped as logical primitive; identity/audit hardening queued |
| WebSocket push to React | partial (backend ready, frontend polls) | partial |
| Multi-actor Orbit | kernel actor membership shipped | **queued** — enterprise admin UX + audit-of-who-approved-what |
| Mobile-only Orbit | not needed | **queued** if mobile principal cohort emerges |
| Federated SSO (Telegram bot per tenant) | not needed | **queued** |

## What this protocol explicitly does NOT define

- A unified inbox merging Telegram + Orbit messages. Principal experience showed that merging them hurts attention layering.
- A "voice mode" surface. No production demand.
- An asynchronous email surface. Slack / Teams adapters are queued under MCP (treating those as enterprise systems the kernel reaches via MCP, not as an H2A surface).
- A "follow-up reminder" primitive that re-pings the principal if a notification goes unanswered. The principal's attention is sovereign; nagging is excluded by design.
