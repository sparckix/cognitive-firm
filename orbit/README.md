# Orbit

Orbit is an optional desktop surface for `cognitive-firm`.

It renders role offices, governance state, gates, damage signals, human-work
sessions, and selected organization-surface summaries from the
filesystem-backed kernel. It is not the system of record, a scheduler, or a
policy engine.

## Quick Start

```bash
cd orbit && npm install

# Terminal 1: event bus + org watcher
npm run sync

# Terminal 2: dev server
npm run dev

# Open http://localhost:3000
```

## Architecture Boundary

```
org/ and kernel read models (system of record, git-tracked)
  ├── members/*.yaml        → Agent orbs on canvas
  ├── roles/*.yaml          → Governance pane
  ├── mandates/*.md         → Scope boundaries
  ├── events/*.jsonl        → Event stream (append-only)
  ├── gates/                → Approval queue
  ├── directives/           → Human → agent messages
  └── controls/             → STOP / PAUSE / RESUME
         │
    event bus (WebSocket broadcast, Lamport timestamps, content-based routing)
         │
    Orbit web app (projection)
```

Orbit write behavior is controlled by app-surface policy:

- `ORBIT_SURFACE_MODE=projection_only` disables all mutation endpoints.
- `ORBIT_SURFACE_MODE=kernel_intents` allows typed human intent endpoints such
  as gate resolution, control, directive, chat, and human-work updates.
- Writes require `ORBIT_API_TOKEN` on the backend and the same value exposed to
  the frontend as `VITE_ORBIT_API_TOKEN`.
- Write endpoints call `COGNITIVE_FIRM_KERNEL_SERVICE_URL` and do not mutate
  governance files directly. Start `cognitive-firm-kernel-service` before using
  Orbit in `kernel_intents` mode.

## Surface Principles

1. **Projection, not truth.** The filesystem, protocol modules, and transition
   logs are the durable state.
2. **Boundary-first display.** Surface gates, blocked obligations, evidence
   gaps, damage signals, and review findings before low-value activity.
3. **Human legibility.** Show enough provenance for a human to inspect why a
   state appeared.
4. **Agent legibility.** Human decisions should become durable transitions that
   role offices can read later.
5. **Attention discipline.** Keep fast interrupts separate from slower mandate,
   charter, and strategy review work.

## License

Apache-2.0 — see the top-level `LICENSE` and `NOTICE` files in the cognitive-firm repository.

<!-- AUTO-INDEX:START (managed by scripts/public/gen_folder_index.py — edit prose OUTSIDE this block) -->

## Index

**Sub-folders**

- [`src/`](src/) — 24 file(s)

**Documents**

- [package-lock.json](package-lock.json)
- [package.json](package.json)
- [tsconfig.json](tsconfig.json)

<sub>1 sub-folder(s), 3 document(s). Auto-generated; re-run `gen_folder_index.py` after adding files.</sub>
<!-- AUTO-INDEX:END -->
