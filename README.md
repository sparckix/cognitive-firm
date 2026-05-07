# cognitive-firm

**A governance kernel for AI-native research orgs, derived from Chandlerian M-form theory.**

`cognitive-firm` is a substrate-agnostic kernel that lets one principal coordinate persistent AI agents (Claude, Codex, Gemini, open-source) under typed mandates with deterministic budget caps, real human approval surfaces (Telegram + web dashboard), and a multi-tenant overlay pattern. It was extracted from production use in a working research apparatus that has been running since April 2026.

## What this is, in one paragraph

The kernel separates four layers that most agent frameworks conflate: (1) **roles** as persistent contracts in YAML files, not chat-defined personas; (2) **mandates** as typed authority documents that gate what each role may do autonomously vs what requires escalation; (3) **a daemon** that ticks every N minutes, discovers work, surfaces it for approval, and dispatches the configured agent CLI; (4) **a system of record** that lives on the filesystem with git as the audit trail (any UI is a projection, not the truth). Anything that runs autonomously is bounded by per-role daily/session/single-action USD caps, agent-CLI utilization caps, cross-family hygiene constraints, and the principal's STOP authority via Telegram.

## What is in this repo

- `src/cognitive_firm/` — the kernel: orchestration daemon, supervisor primitives, signals, notifications, role extensions, common runtime helpers.
- `org/` — the system-of-record skeleton: roles, mandates, sessions, signals, channels, transitions. Treat as a template; instantiate by tenant.
- `tenants/` — multi-tenant overlay pattern. The `EXAMPLE` tenant is a starter; real tenants live in their own private repos.
- `schemas/` — typed contracts for mandates, roles, gate payloads, transitions.
- `scripts/` — preflight, the agent daemon entrypoint, health checks.
- `deploy/` — VPS + systemd reference deployment.
- `docs/` — architecture, guides, concept docs.
- `orbit/` — the desktop dashboard (TLDraw-based pace-layered UI).

## 5-minute quickstart

```bash
git clone https://github.com/<your-org>/cognitive-firm ~/cognitive-firm
cd ~/cognitive-firm
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Set up your principal preferences
cp org/preferences/templates/principal.yaml org/preferences/principal.yaml
$EDITOR org/preferences/principal.yaml

# Drop API keys into .env
cp .env.example .env  # or create with: ANTHROPIC_API_KEY=... OPENAI_API_KEY=... GOOGLE_API_KEY=...
$EDITOR .env

# Set up Claude Code subscription auth (skip if you only have API keys)
unset ANTHROPIC_API_KEY  # in this shell, so claude prefers OAuth
claude setup-token

# Smoke test
python scripts/org_role_preflight.py --role research_director
python scripts/agent_daemon.py --role research_director --tick-once --dry-run
```

For VPS deployment + bidirectional sync (mutagen) + tenant overlays, see `deploy/README.md` and `docs/guides/forking_the_kernel.md`.

## Architecture, in one diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  PRINCIPAL (human)                                              │
│  Telegram (mobile pager) ↔ Orbit (desktop dashboard) ↔ CLI      │
└────────────────────────┬────────────────────────────────────────┘
                         │ approvals (typed gate resolution)
┌────────────────────────▼────────────────────────────────────────┐
│  AGENT DAEMON (governance loop)                                 │
│  discover work → propose → wait approval → dispatch → record    │
└────────────────────────┬────────────────────────────────────────┘
                         │ subprocess (env-scrubbed for OAuth)
┌────────────────────────▼────────────────────────────────────────┐
│  AGENT RUNTIME (Claude Code, Codex, future open-source)         │
│  Subscription quota for agent-side work                         │
│  API tokens for substrate-side LLM calls (LLMRuntime)           │
└────────────────────────┬────────────────────────────────────────┘
                         │ filesystem writes
┌────────────────────────▼────────────────────────────────────────┐
│  SYSTEM OF RECORD (org/ + git history)                          │
│  Roles, mandates, sessions, signals, channels, transitions      │
│  Audit trail = git log; UI = projection                         │
└─────────────────────────────────────────────────────────────────┘
```

## Theoretical grounding

cognitive-firm derives from Chandlerian M-form theory: roles, mandates, and the principal-independence invariant come from classical organizational theory rather than security engineering. A companion paper develops the grounding.

Three load-bearing primitives that are not common in agent-framework designs:

1. **Multi-tenant overlay pattern.** A `tenants/<id>/` directory pattern lets the same kernel host different orgs without contaminating either with the other's instantiation.
2. **Pace-layered governance UX** (after Stewart Brand). The dashboard separates slow (mandate config), working (tasks), and fast (damage signals) into distinct attention layers with explicit batch-review discipline.
3. **Substrate-agnostic kernel/policy boundary** with explicit reactivation triggers across enterprise-readiness axes (leases, RBAC/SSO, signed audit, event outbox, multi-server, observability, recovery).

## License

Apache-2.0 (see LICENSE). Commercial use and modification are permitted; the only requirement is preserving the copyright notice + license terms in derivative works.

## Provenance

Extracted from a parent research apparatus (the "ZTARE" project) on 2026-05-07, after several weeks of single-principal production use on a Hetzner VPS.
