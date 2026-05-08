# cognitive-firm

**A governance kernel for AI-native research orgs, derived from Chandlerian M-form theory.**

[Identity](#1-identity) · [Who it's for](#2-who-its-for--what-it-solves) · [Architecture](#3-architecture) · [Repository map](#4-repository-map) · [Quickstart](#5-quickstart-local-dev) · [Production](#6-production-deployment) · [Status](#7-status) · [License & provenance](#8-license--provenance)

---

## 1. Identity

`cognitive-firm` lets one principal coordinate persistent AI agents (Claude, Codex, Gemini, future open-source) under typed mandates, deterministic budget caps, real human approval surfaces (Telegram + web dashboard), and a multi-tenant overlay pattern.

It is not an agent framework, an LLM SDK, or a chat client. It is the layer **above** those: persistent **role offices** with their own mandates, inboxes, sessions, signals, and audit trails — the org chart of an AI-native company, made executable.

It was extracted from production use in a working research apparatus that has been running on a Hetzner VPS since April 2026.

---

## 2. Who it's for & what it solves

### The problem

Agent frameworks (LangChain, AutoGen, CrewAI, Letta) treat coordination as a chat-defined concern: roles are personas in prompts, authority is implicit, audit trails are best-effort, and the human is in the loop only when the framework remembers to ask. That works for demos. It does not work for an organization that must run for months with multiple agents acting under principal-bounded authority on real systems (Linear, Salesforce, ERPs, code repos).

### Who should adopt this

- **Single principals** running an AI-native research lab, fund, or solo company who need persistent agents with bounded authority.
- **Small teams (1-5 people)** wanting one place where role mandates, budgets, audit trails, and approvals all live as files in git.
- **Researchers** building on top of a substrate that can be inspected, replayed, and forked rather than reverse-engineered from logs.

### Explicit non-goals

| Out of scope | Why |
|---|---|
| Multi-principal RBAC / SSO | T1 (single-principal, trusted hardware) is the production target today. T2 reactivation triggers documented in `docs/PROTOCOLS.md`. |
| A new agent runtime | We dispatch existing CLIs (Claude Code, `codex`); we do not implement model inference. |
| A chat UI | The system of record is the filesystem + git. UIs (Orbit, Telegram) are projections, not the truth. |
| Agentic prompt engineering | Mandates and roles are typed contracts, not prompt templates. |
| Cross-org federation | A single repo / single principal is the unit of governance. |

### Alternatives, briefly

- **LangGraph / AutoGen / CrewAI**: better fit if your unit of work is one ephemeral graph run. cognitive-firm is for orgs that persist.
- **Letta / MemGPT**: better fit if your problem is agent memory. cognitive-firm assumes the filesystem + git is the memory.
- **n8n / Zapier**: better fit if your problem is glue between SaaS APIs. cognitive-firm gates *which* role may invoke which MCP tool under what mandate.

---

## 3. Architecture

cognitive-firm is **four protocols + four primitives** stacked on a filesystem-backed system of record. Read `docs/PROTOCOLS.md` for the full spec; this section is the map.

### The four protocols

| Layer | Protocol | What it governs | Spec |
|---|---|---|---|
| Human ↔ org | **H2A** (Human-to-Agent) | Telegram + Orbit + CLI surfaces; pace-layered attention discipline; STOP authority | [`docs/protocols/h2a.md`](docs/protocols/h2a.md) |
| Role ↔ role | **A2A** (Agent-to-Agent) | Typed `AgentMessage` envelopes, obligation lifecycle, content-addressed artifact dependencies, saga compensation | [`docs/protocols/a2a.md`](docs/protocols/a2a.md) |
| Role ↔ external | **MCP** (Model Context Protocol) | Capability-gated outbox-relay dispatch to enterprise systems (Linear, Salesforce, ERPs) | [`docs/protocols/mcp.md`](docs/protocols/mcp.md) |
| Cross-cutting | **Mandate** | Typed authority contracts for what each role may do autonomously vs. by escalation | [`docs/protocols/mandate.md`](docs/protocols/mandate.md) |

### The four primitives (load-bearing, not common in agent frameworks)

1. **Persistent role offices.** A role is a YAML file in `org/roles/`, not a chat-defined persona. Its identity, authority, budget, and audit trail outlive any single agent invocation.
2. **Typed mandates with deterministic enforcement.** Per-role daily / session / single-action USD caps + agent-CLI utilization caps + cross-family hygiene. The kernel verifies the mandate hash every tick.
3. **Multi-tenant overlay pattern.** A `tenants/<id>/` directory pattern lets the same kernel host different orgs without contaminating either with the other's instantiation. Tenants live in their own private repos and symlink into the public kernel skeleton.
4. **Pace-layered governance UX** (after Stewart Brand). The dashboard separates slow (mandate config), working (tasks), and fast (damage signals) into distinct attention layers with explicit batch-review discipline.

### One diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  PRINCIPAL (human)                                              │
│  ↕ H2A: Telegram (mobile) · Orbit (desktop) · CLI               │
└────────────────────────┬────────────────────────────────────────┘
                         │ approvals (typed gate resolution)
┌────────────────────────▼────────────────────────────────────────┐
│  ROLE OFFICES (research_director, manager, debate_runner, …)   │
│  ↕ A2A: typed envelopes · obligation lifecycle · sagas         │
└────────────────────────┬────────────────────────────────────────┘
                         │ subprocess (env-scrubbed for OAuth)
┌────────────────────────▼────────────────────────────────────────┐
│  AGENT RUNTIMES (Claude Code, codex, future open-source)        │
│  Subscription quota for agent-side · API tokens for substrate   │
└────────────────────────┬────────────────────────────────────────┘
                         │ MCP capability-gated outbox-relay
┌────────────────────────▼────────────────────────────────────────┐
│  EXTERNAL SYSTEMS (Linear, Salesforce, ERPs, ticketing)         │
└─────────────────────────────────────────────────────────────────┘

System of record: org/ (filesystem) + git history.
                  Audit trail = git log; UI = projection.
```

---

## 4. Repository map

Read in this order if you are new:

| # | Path | What you'll learn |
|---|---|---|
| 1 | `README.md` (this file) | Identity, problem, architecture map |
| 2 | `docs/PROTOCOLS.md` | The four-protocol decomposition with shipped/queued status per primitive |
| 3 | `docs/protocols/{a2a,h2a,mcp,mandate}.md` | Per-protocol specs with threat-model tables |
| 4 | `org/README.md` | The system-of-record skeleton: roles, mandates, sessions, signals |
| 5 | `src/cognitive_firm/` | The kernel implementation |
| 6 | `tests/` | The validation surface — every "shipped" claim is backed here |

| Directory | Role |
|---|---|
| `src/cognitive_firm/` | Kernel: orchestration daemon, supervisor primitives, signals, notifications, role extensions, common runtime helpers |
| `org/` | System-of-record skeleton: roles, mandates, sessions, signals, channels, transitions. Treat as a template. |
| `tenants/` | Multi-tenant overlay slot. Reserved for `<tenant_id>/` subdirectories with overlay scripts; real tenants live in private repos. |
| `schemas/` | Typed contracts for mandates, roles, gate payloads, transitions |
| `scripts/` | `agent_daemon.py` (entrypoint), `org_role_preflight.py` (preflight), `setup_vps.sh`, `telegram_setup.py`, `operator_console.sh` |
| `deploy/` | systemd units (`agent-daemon.service`, `orbit-sync.service`) for VPS deployment |
| `docs/` | Architecture, protocol specs, concept docs |
| `orbit/` | Desktop dashboard (TLDraw-based pace-layered UI) |
| `internal/` | Internal verdict notes (kept in repo for transparency, not part of the public API) |

---

## 5. Quickstart (local dev)

```bash
git clone https://github.com/sparckix/cognitive-firm ~/cognitive-firm
cd ~/cognitive-firm
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure principal preferences
cp org/preferences/templates/principal.yaml org/preferences/principal.yaml
$EDITOR org/preferences/principal.yaml

# Configure environment — copy the template and fill in keys
cp .env.example .env
$EDITOR .env

# (optional) Use Claude Code subscription auth instead of API key
unset ANTHROPIC_API_KEY      # so claude prefers OAuth
claude setup-token

# Smoke test — preflight + one daemon tick in dry-run
python scripts/org_role_preflight.py --role research_director
python scripts/agent_daemon.py --role research_director --tick-once --dry-run
```

The dry-run tick discovers candidate work, prints what it would dispatch, and exits without spending budget. If preflight fails, it tells you which mandate or preference file is missing and how to create it.

`.env.example` documents every environment variable the kernel and Orbit dashboard read, grouped by purpose (LLM keys, agent CLI runtime, Telegram pager, Orbit dashboard, filesystem overrides, daemon polling). All variables are optional except that **at least one of the three LLM API keys is required** for substrate-side LLM work.

---

## 6. Production deployment

VPS deployment uses systemd + bidirectional sync (mutagen) so the principal can edit mandates from a laptop while the daemon ticks 24/7.

| Step | Path |
|---|---|
| 1. Provision VPS, install dependencies, configure `.env` | `scripts/setup_vps.sh` |
| 2. Configure Telegram bot (mobile pager + STOP) | `scripts/telegram_setup.py` |
| 3. Install + enable systemd unit | `deploy/agent-daemon.service` |
| 4. (Optional) Bidirectional sync laptop ↔ VPS for mandate edits | `deploy/orbit-sync.service` |
| 5. Tail with the operator console | `scripts/operator_console.sh` |

Multi-tenant deployment: keep tenant content in a sibling private repo (`<tenant>-research-co/tenants/<tenant>/`) with `mandates/`, `roles/`, `preferences/` overrides. Symlink overlays into `cognitive-firm/org/` via a tenant setup script. The public kernel never sees tenant files.

---

## 7. Status

cognitive-firm is **production-stable for single-principal (T1) deployments**. Adopters who read the protocol specs can rely on every "shipped" claim being backed by tests in `tests/`.

### Shipped (T1 production-stable)

| Primitive | Where | Tests |
|---|---|---|
| Outbox relay (MCP transport) | `src/cognitive_firm/role_extensions/mcp_bridge/` | `tests/test_mcp_outbox_relay.py`, `test_mcp_linear_server.py` |
| Capability tokens for MCP dispatch | `src/cognitive_firm/role_extensions/mcp_bridge/capabilities.py` | `tests/test_mcp_capabilities.py` |
| A2A obligation lifecycle (Phase A) | `src/cognitive_firm/orchestration/agent_channels.py` | `tests/test_obligation_lifecycle.py` |
| Artifact dependencies (Phase B) | `src/cognitive_firm/orchestration/artifact_dependencies.py` | `tests/test_artifact_dependencies.py` |
| Saga compensation (Phase C) | `src/cognitive_firm/orchestration/saga_compensation.py` | `tests/test_saga_compensation.py` |
| EU AI Act deploy gate (C3 SHIP B) | `src/cognitive_firm/orchestration/eu_ai_act_deploy_gate.py` | `tests/test_eu_ai_act_deploy_gate.py` |
| Property-based invariants (Hypothesis) | `tests/test_invariants_property_based.py` | 8/8 |
| Cross-primitive integration tests | `tests/test_cross_primitive_integration.py` | 3/3 |
| Daemon bug-audit regression | `tests/test_daemon_bug_audit.py` | passing |
| Telegram callback flow | `tests/test_telegram_callback_flow.py` | passing |
| Mandate hash verification | every daemon tick | runtime invariant |
| Telegram pager + STOP | `src/cognitive_firm/notifications/` | manual-tested in production |
| Orbit dashboard (TLDraw v2) | `orbit/` | working in production |

### Queued

- **MCP Phase 3**: supply-chain pinning (digest + signed manifest + revocation feed)
- **MCP Phase 4**: IdP federation
- **A2A remote adapter**: cross-VPS role-to-role messaging

### Deferred (T2 reactivation triggers)

Multi-principal RBAC, SSO, signed audit trail with TSA, event-outbox to Postgres, multi-server quorum, observability stack, cold-start recovery from snapshot. Each has an explicit reactivation trigger documented in `docs/PROTOCOLS.md` — the discipline is to ship T1 well rather than to claim T2 coverage that has not been tested.

---

## 8. License & provenance

**License**: Apache-2.0 (see `LICENSE` and `NOTICE`). Commercial use and modification are permitted; the only requirements are preserving the copyright notice and license terms in derivative works, and stating any significant changes you make. There is no source-availability restriction, no Business Source License, no dual-licensing — just Apache-2.0.

**Contributing**: see `CONTRIBUTING.md`.

**Provenance**: Extracted from a parent research apparatus (the "ZTARE" project) on 2026-05-07, after several weeks of single-principal production use on a Hetzner VPS. Theoretical grounding (Chandlerian M-form, Holmström informativeness, Tirole incomplete contracts, Nelson & Winter routines) is developed in a companion paper.

**Not a Claude Code product.** cognitive-firm is independent of Anthropic; Claude is one of several agent runtimes the kernel can dispatch.
