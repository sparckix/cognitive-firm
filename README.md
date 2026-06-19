# cognitive-firm

**Orchestrate and govern human + AI work loops with auditable receipts.**

[Identity](#1-identity) · [Who it's for](#2-who-its-for--what-it-solves) · [Architecture](#3-architecture) · [Repository map](#4-repository-map) · [Quickstart](#5-quickstart-local-dev) · [Production](#6-production-deployment) · [Status](#7-status) · [Adoption](#8-adoption) · [License & provenance](#9-license--provenance)

---

## 1. Identity

`cognitive-firm` lets an accountable authority role coordinate persistent AI
agents and human contributors under typed mandates, budget caps, human work
surfaces, and a tenant overlay pattern.

It is not an LLM SDK or a chat client. It is a governed work runtime above
those layers: persistent **role offices** with mandates, inboxes, sessions,
signals, execution routing, and audit trails.

The operating model is concrete: agents take actions with provenance, humans do
bounded work with receipts, role offices exchange obligations, and only typed
state transitions change the organization. A partner call, a restricted-system
check, a code change, a forecast miss, and a governance proposal are different
records because they create different follow-up obligations.

The human-agent work model is deliberately not "human approves every action"
and not "agent autonomy with after-the-fact oversight." Agents can run quickly
inside bounded envelopes. Humans contribute where they are the right actor or
judge. The kernel records the state transitions that make the work reviewable.
Start with [`docs/human-agent-work.md`](docs/human-agent-work.md) for that
theory and its operational mapping.

It was extracted from a live research deployment and rewritten as a reusable
kernel with tests, examples, and local deployment fixtures.

---

## 2. Who it's for & what it solves

### The problem

Agent frameworks such as LangChain, AutoGen, CrewAI, and Letta are strongest
when they model execution graphs, tool calls, memory, and agent interaction.
This kernel focuses on a different layer: durable roles, authority,
accountability, human work, leases, and audit surfaces around those runtimes.

### Why adopt this

Adopt cognitive-firm only when the unit of value is no longer a single agent
run. The repo is for work that repeats across days or weeks, crosses humans
and agents, touches external systems, and needs a durable record of authority,
evidence, outcome, and closure.

Use the simpler stack when the job is simpler:

| If you need... | Use... |
|---|---|
| Model calls, tools, prompts, middleware, and a configurable agent loop | LangChain or another agent SDK |
| Stateful graph execution, persistence, interrupts, replay, and runtime observability | LangGraph or another workflow runtime |
| Traces, evals, debugging, and deployment monitoring | LangSmith or another observability/eval platform |
| SaaS triggers, API glue, process modeling, and workflow-stage automation | n8n, Zapier, BPM, or another workflow automation tool |
| Role authority, claimable production work, bounded human work, action provenance, formal-verification records, outcome links, accountability cases, and approved learning records around those systems | cognitive-firm |

The adoption test is concrete:

1. Will a role be allowed to act repeatedly, not just answer one prompt?
2. Could a bad action require knowing who had authority, what evidence existed,
   which human was asked to do work, and what recourse path existed?
3. Do you need state that survives a model swap, runtime swap, or agent-session
   reset?
4. Would a reviewer need one packet showing run state, attestations,
   authority evidence, production work-item state, temporary write claims,
   governance approvals, human receipts, outcome evidence, unresolved caveats,
   and accountable closure?

If the answer is mostly no, use LangChain/LangGraph directly. If the answer is
yes, use cognitive-firm as the organization layer around those runtimes.

This also covers the useful part of "loop engineering": not the inner graph
loop itself, but the repeated organizational loop around it. The existing
primitives already cover the composition a governed loop needs: mandate,
work item or goal, runtime checkpoints, action attestations, formal
verification records, human-work receipts, outcome links, accountability cases,
and approved learning records.

To inspect the shortest no-cost governed action locally:

```bash
make first-gated-action
```

That command runs one fictional Kettle & Compass workflow: a role-bearing
service actor claims work, opens a run, writes an attested artifact, receives a
bounded human-work receipt, completes a governed exit, records outcome and
accountability closure, and emits a governed-run bundle summary.

For the broader demo suite:

```bash
make adoption-demo
make adoption-onramp-packet
make adoption-readiness-packet
```

Start with the loop, then inspect the evidence:

- `make adoption-demo` exercises the no-cost native workflow, failure
  fixtures, runtime-adapter projection, and governed org-evolution examples.
- `make adoption-onramp-packet` collects the first-review evidence bundle under
  `.cognitive-firm-runs/adoption-onramp/...`.
- `make adoption-readiness-packet` re-renders the latest on-ramp reviewer
  handoff when one exists, or falls back to expected proof gaps on a fresh tree.

The default adoption path is meant to answer four questions: what work happened,
under which role authority, what human or machine evidence closed it, and what
future learning/provenance record can be inspected. It is a bounded harness, not
a planner or workflow engine. If you have a separately produced bounded
live-agent or release-gate result, attach it without letting the collector run
that substrate with
`--result bounded_live_agent_run=/path/to/self-evolving-org-demo.json`. Use the
generated self-evolving report JSON rather than a clipped stdout summary so the
packet can inspect the v0.4 learning-use, context-packet, provenance, and
proposal-review evidence counters, including proposal follow-through that shows
whether at least one proposal reached closed-loop evidence. Those counters must
be present and nonzero for the live-agent row to count as fully reviewable.
Missing optional evidence stays visible as deferred evidence, but a supplied
optional artifact that fails its checks blocks the packet from reporting
`ok: true`.
The same sequence is discoverable without scanning this README:
`cognitive-firm-userland operator-path first_review` returns the three
recommended review commands directly, and
`cognitive-firm-userland commands "first serious review"` finds the same path
from task text.

For concrete wedge reviews, `make agent-fleet-review-packet` writes a persistent
local/subscription agent invocation receipt, governed-run bundle,
operator-burden summary, and Markdown runbook without calling an external
runtime. `make langgraph-adapter-policy-preview` validates the bundled
`langgraph-runtime-adapter` policy overlay against a temporary starter org
without installing LangGraph, applying the overlay, or writing a governance
proposal. The live self-evolving path remains available through
`make self-evolving-org-agent-demo` with `AGENT_PLANNER_COMMAND` set to a
subscription/local agent planner that emits JSON; use
`make self-evolving-org-view` when you want persistent reports and the
human-first company-state view for that fixture.

`make adoption-onramp-replay` copies the public repo surface into an isolated
worktree, excludes `internal/`, local run state, virtualenvs, and `.env`, then
runs the core on-ramp collector from that copy. Use it when you want evidence
that the first-review path is replayable from a clean clone-like surface rather
than depending on author-local state.

`make adoption-onramp-full-replay` runs the same clean-copy replay with the full
no-cost collector, including adapter-policy preview, formal-provider proof pack,
runtime-adapter proof pack, agent-fleet audit, and field-pilot rows.

`make adoption-readiness-packet` emits the read-only reviewer handoff. After
`make adoption-onramp-packet`, it re-renders the latest collected packet from
`.cognitive-firm-runs/adoption-onramp/...`; on a fresh tree it falls back to
the expected proof paths and marks absent rows as missing. Pass observed JSON
outputs directly to `scripts/adoption_readiness_packet.py --result
CHECK_ID=path` when you want to assemble a manual packet. The script never runs
commands, approves release readiness, or writes kernel state. It also reports
expected, present, and missing evidence fields for each check, so a required
green command with a thin JSON payload still blocks adoption review.
See
[`docs/examples/README.md`](docs/examples/README.md) for the example index,
[`docs/examples/governance-failure-benchmark.md`](docs/examples/governance-failure-benchmark.md)
for the failure fixture list and
[`docs/examples/agent-fleet-audit-demo.md`](docs/examples/agent-fleet-audit-demo.md)
for the local agent-invocation audit path, and
[`docs/examples/self-evolving-org-demo.md`](docs/examples/self-evolving-org-demo.md)
for the organization-evolution path.

### Who should adopt this

- **Solo operators** running a research lab, fund, or solo company who need persistent agents with bounded authority.
- **Small teams (1-5 people)** wanting one place where role mandates, budgets, audit trails, and approvals all live as files in git.
- **Researchers** building on top of a system that can be inspected, replayed, and forked rather than reverse-engineered from logs.

### Explicit non-goals

| Out of scope | Why |
|---|---|
| Enterprise RBAC / SSO | Lean multi-actor role membership is supported. Full enterprise IAM administration, SSO provisioning, and tenant isolation remain deployment work. |
| Production compliance certification | The repo ships local audit, evidence, and deploy-gate primitives. It does not certify a regulated deployment or replace tenant legal, compliance, or external-audit work. |
| A model/graph engine | The daemon executes governed role-office work by discovering tasks, dispatching configured CLIs and MCP tools, recording checkpoints, and routing interrupts. It deliberately leaves model inference, graph replay, and node scheduling to the runtime best suited for that job. |
| A chat UI | The system of record is kernel state/logs (`org/` + workspace logs) plus git history. UIs such as Orbit are projections, not the truth. |
| Agentic prompt engineering | Mandates and roles are typed contracts, not prompt templates. |
| Cross-org federation | A single repo / single authority domain is the current unit of governance. |

### Alternatives, briefly

| System family | Best fit | cognitive-firm boundary |
|---|---|---|
| LangGraph, AutoGen, CrewAI, OpenAI Agents SDK, and similar runtimes | Build and run agent graphs, crews, tool loops, handoffs, and interrupts. | Wrap them with durable role authority, human-work receipts, action provenance, outcome links, and governed learning. |
| ReDel-style recursive delegation systems | Let agents choose delegation structures and expose recursion traces. | Import delegation graphs and traces as evidence; use mandates, budgets, depth bounds, and approvals before structural mutation. |
| Self-organizing team systems such as Meta-Team or TheBotCompany-style research prototypes | Explore emergent roles, team evolution, and dynamic task allocation. | Preserve the useful emergence while separating proposal, evaluation, approval, execution, audit, and durable state change. |
| Letta / MemGPT-style memory systems | Maintain agent memory and continuity. | Treat durable organizational memory as reviewed filesystem/git state, not just agent memory. |
| n8n, Zapier, BPM, and SaaS workflow automation | Connect APIs, model process stages, and trigger routine workflows. | Let them execute the process. Gate which role may invoke which capability, under which mandate, with what evidence, outcome, learning, and closure record. |

The intended integration posture is additive: external runtimes execute work;
cognitive-firm records the organizational contract and governed state
transitions around that work.

---

## 3. Architecture

cognitive-firm is a small set of governance protocols and primitives stacked on
a filesystem-backed system of record. Read `docs/PROTOCOLS.md` for the full
spec; this section is the map.

### The protocols

| Layer | Protocol | What it governs | Spec |
|---|---|---|---|
| Human ↔ org | **H2A** (Human-to-Agent) | Telegram + Orbit + CLI surfaces; pace-layered attention discipline; STOP authority | [`docs/protocols/h2a.md`](docs/protocols/h2a.md) |
| Role → human | **A2H** (Agent-to-Human work coordination) | Bounded human work requested by role offices, with deliverables, receipts, and agent follow-up | [`docs/protocols/a2h.md`](docs/protocols/a2h.md) |
| Role ↔ role | **A2A** (Agent-to-Agent) | Typed `AgentMessage` envelopes, obligation lifecycle, content-addressed artifact dependencies, saga compensation | [`docs/protocols/a2a.md`](docs/protocols/a2a.md) |
| Role ↔ external | **MCP** (Model Context Protocol) | Capability-gated outbox-relay dispatch to enterprise systems (Linear, Salesforce, ERPs) | [`docs/protocols/mcp.md`](docs/protocols/mcp.md) |
| Cross-cutting | **Mandate** | Typed authority contracts for what each role may do autonomously vs. by escalation | [`docs/protocols/mandate.md`](docs/protocols/mandate.md) |
| Cross-cutting | **Worker Taxonomy** | Capability, fungibility, state, and transport vocabulary for worker roles | [`docs/protocols/worker-taxonomy.md`](docs/protocols/worker-taxonomy.md) |
| Project / tenant | **Project Charter** | Scope fidelity: core question, out-of-scope boundaries, end states, forecast type, inheritance, and anchor proxies | [`docs/protocols/project-charter.md`](docs/protocols/project-charter.md) |

### The invariants

The primitives serve a small conceptual core. See
[`docs/kernel-invariants.md`](docs/kernel-invariants.md) for the full map.

| Invariant | Meaning | Example surfaces |
|---|---|---|
| Separation | Generation, evaluation, approval, and execution do not silently collapse into one actor. | Role offices, mandates, A2A, Strategy Office. |
| Typed authority | A role or actor has explicit authority before acting. | Mandates, actor identity, actor membership, subject-scope checks, leases, MCP capabilities. |
| Human work as state | Humans can do bounded object-level work, not only approve gates. | H2A, A2H, human work sessions, receipts. |
| Machine provenance | Agent/runtime/tool work is reviewable by producer, policy, inputs, outputs, and digest. | Run checkpoints, runtime adapters, action attestations, audit manifests. |
| Accountable closure | Residual risk has an accountable role, recourse path, and closure evidence. | Accountability cases, accountability summary, org surface. |
| Durable learning | Learning is a reviewed state transition that changes future behavior or review state. | Strategy findings, learning candidates, approved learning events, governance changes. |

### One diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  PRINCIPAL (human)                                              │
│  ↕ H2A: Telegram (mobile) · Orbit (desktop) · CLI               │
│  ↕ A2H: bounded work requests · receipts · follow-up            │
└────────────────────────┬────────────────────────────────────────┘
                         │ approvals + bounded human work
┌────────────────────────▼────────────────────────────────────────┐
│  ROLE OFFICES (research_director, manager, debate_runner, …)   │
│  ↕ A2A: typed envelopes · obligation lifecycle · sagas         │
└────────────────────────┬────────────────────────────────────────┘
                         │ subprocess (env-scrubbed for OAuth)
┌────────────────────────▼────────────────────────────────────────┐
│  AGENT RUNTIMES (Claude Code, codex, future open-source)        │
│  Subscription quota for agent-side · API tokens for tools       │
└────────────────────────┬────────────────────────────────────────┘
                         │ MCP capability-gated outbox-relay
┌────────────────────────▼────────────────────────────────────────┐
│  EXTERNAL SYSTEMS (Linear, Salesforce, ERPs, ticketing)         │
└─────────────────────────────────────────────────────────────────┘

System of record: kernel state/logs (org/ + workspace logs) + git history.
                  Audit trail = git log + receipts/events; UI = projection.
```

---

## 4. Repository map

**New adopter? Start with [`docs/getting-started.md`](docs/getting-started.md)** —
the shortest path from zero to a running governed firm (`pip install` →
`cognitive-firm-distro install` → point the tools at it → run it). The table
below is the full reading order.

> **Reading the docs in Obsidian.** This repository is an [Obsidian](https://obsidian.md)
> vault — open the repo folder as a vault and `README.md` plus everything under
> `docs/` is navigable with working links, backlinks, and graph view. The
> committed `.obsidian/` directory carries the vault config (markdown links,
> relative paths); per-user UI state is gitignored. No setup needed beyond
> opening the folder.

Read in this order if you are new:

| # | Path | What you'll learn |
|---|---|---|
| 1 | `README.md` (this file) | Identity, problem, architecture map |
| 2 | `docs/first-30-minutes.md` | The fastest verified path through setup, smoke, and overlay boundaries |
| 3 | `docs/abstraction-map.md` | Kernel vs app vs runtime vs tenant boundaries |
| 4 | `docs/resource-event-catalog.md` | The adopter-facing object model |
| 5 | `docs/capability-map.md` | The problem-oriented map of implemented kernel surfaces |
| 6 | `docs/blueprints/README.md` | Standard compositions: runtime interrupt, app write, learning loop, small-team membership |
| 7 | `docs/kernel-invariants.md` | The small invariant set that generates the primitive design |
| 8 | `docs/system-positioning.md` | What cognitive-firm owns versus agent runtimes, memory platforms, and automation tools |
| 9 | `docs/theory.md` | Claim map: prior literature, invariants, surfaces, falsifying pressure |
| 10 | `docs/recursive-organization.md` | How the kernel supports organizational learning over time |
| 11 | `docs/human-agent-work.md` | Human-agent work: speed, receipts, follow-up, accountability |
| 12 | `docs/PROTOCOLS.md` | The protocol decomposition with shipped/queued status per primitive |
| 13 | `docs/adopting-cognitive-firm.md` | How to fork the kernel and keep tenant content separate |
| 14 | `docs/field-validation-pilot.md` | How to test the kernel in one real decision pipeline |
| 15 | `docs/field-pilot-selector.md` | How to choose the first recurring decision pipeline |
| 16 | `docs/accountability-speed-envelope.md` | How to choose agent-speed, sampled, gated, or accountable closure paths |
| 17 | `docs/templates/field-pilot/README.md` | Copyable pilot scope, baseline, metrics, and learning-event templates |
| 18 | `docs/reader-checklist.md` | Short understanding, change-review, and adoption checks |
| 19 | `docs/agent-prompts.md` | Paste-ready prompts for using Codex or Claude to inspect the repo |
| 20 | `docs/examples/end-to-end-governance-walkthrough.md` | End-to-end kernel learning loop |
| 21 | `docs/examples/source-coverage-walkthrough.md` | Source-health and source-repair walkthrough |
| 22 | `docs/examples/action-intelligence-source-health.md` | How to repair forecast/action-impact sources before routing work |
| 23 | `docs/examples/learning-event-replay.md` | How approved learning is encountered by later work |
| 24 | `docs/examples/learning-loop-demo.md` | Learning loop narrative and executable check |
| 25 | `docs/examples/a2h-workflow-demo.md` | Agent-requested human-work workflow |
| 26 | `docs/examples/app-service-integration-example.md` | How apps submit intents without becoming the system of record |
| 27 | `docs/protocols/` | Per-protocol and interface specs with threat-model tables where applicable |
| 28 | `docs/organizational_learning_loop.md` | How findings become durable state transitions |
| 29 | `docs/ROADMAP.md` | Public-kernel roadmap |
| 30 | `docs/t1_t2_upgrade_matrix.md` | Deployment-class boundary for T1/T2 adopters |
| 31 | `CHANGELOG.md` | Release history and shipped capability summary |
| 32 | `tenants/example/` | Minimal overlay shape for adopters |
| 33 | `org/README.md` | The system-of-record skeleton: roles, mandates, sessions, signals |
| 33 | `src/cognitive_firm/` | The kernel implementation |
| 34 | `tests/` | The validation surface — shipped behavior is backed here |

### Canonical code boundary

`src/cognitive_firm/` is the source of truth for reusable kernel behavior:
primitives, invariants, schemas, state transitions, adapters, projections,
service routes, and importable helpers. If another program should be able to
rely on the behavior, or if a rule affects authority, auditability, learning,
or state mutation, it belongs in `src/cognitive_firm/` with tests.

`scripts/` is the executable surface around the kernel: CLIs, demos, smoke
harnesses, migrations, and operator workflows. Scripts may seed fixtures,
parse command-line arguments, call external tools, and compose primitives from
`src/cognitive_firm/`, but they should not become a second source of truth for
kernel rules. When script logic becomes reusable, policy-bearing, or shared by
more than one workflow, promote it into `src/cognitive_firm/` and keep the
script as a thin entrypoint.

| Directory | Role |
|---|---|
| `src/cognitive_firm/` | Kernel source of truth: primitives, invariants, schemas, state transitions, adapters, projections, service routes, distribution, userland, and common runtime helpers |
| `org/` | System-of-record skeleton: roles, mandates, sessions, signals, channels, transitions. Treat as a template. |
| `tenants/` | Multi-tenant overlay slot. Reserved for `<tenant_id>/` subdirectories with overlay scripts; real tenants live in private repos. |
| `distro/` | Installable distribution packages. The `starter-firm` distro brings up a runnable governed organization in one action with `cognitive-firm-distro install`. |
| `schemas/` | Typed contracts for mandates, roles, gate payloads, transitions |
| `scripts/` | Thin executable entrypoints, demos, smoke harnesses, migrations, and operator workflows that compose `src/cognitive_firm/`; examples include `agent_daemon.py`, `org_role_preflight.py`, `setup_vps.sh`, `telegram_setup.py`, `operator_console.sh` |
| `deploy/` | systemd units (`agent-daemon.service`, `orbit-sync.service`) for VPS deployment |
| `docs/` | Architecture, protocol specs, concept docs |
| `orbit/` | Desktop dashboard (TLDraw-based pace-layered UI) |

The repository root is also an Obsidian-compatible vault. Open the root folder
in Obsidian to browse the Markdown docs with backlinks, graph view, and
relative links.

---

## 5. Quickstart

### Install

The fast path — install the kernel and its three CLIs from PyPI, then stand up
a governed organization in one command:

```bash
pip install cognitive-firm
cognitive-firm-distro install starter-firm --into ./my-firm
```

`./my-firm` is now a governed firm — its own git repo, verified to boot.
[`docs/getting-started.md`](docs/getting-started.md) is the full
zero-to-running path.

### Local development

Working on the kernel itself? Clone and install it editable:

```bash
git clone https://github.com/sparckix/cognitive-firm ~/cognitive-firm
cd ~/cognitive-firm
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Public verification path
make smoke-public
make smoke-docker
make release-hygiene-check

# Full tag-candidate gate
make release-candidate-check

# Optional bounded live-agent proof, outside the public release gate
make self-evolving-agent-preflight AGENT_RUNTIME=codex AGENT_ADAPTER=codex_exec
make self-evolving-org-agent-demo \
  AGENT_RUNTIME=codex \
  AGENT_ADAPTER=codex_exec \
  SELF_EVOLVING_DEMO_ITERATIONS=1 \
  SELF_EVOLVING_DEMO_BUDGET_UNITS=1 \
  SELF_EVOLVING_PLANNER_PROMPT_MODE=compact

# Configure default authority preferences
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
python -m cognitive_firm.orchestration.org_surface
make kernel-service-smoke
make app-integration-conformance
make app-service-integration-smoke
make source-coverage-walkthrough
make learning-loop-walkthrough
make backup-restore-smoke
make docs-surface-check
```

The dry-run tick discovers candidate work, prints what it would dispatch, and exits without spending budget. If preflight fails, it tells you which mandate or preference file is missing and how to create it.

The public release gate is deterministic and network-free except for the
explicit Docker/container path. Live agent targets are opt-in: they use a local
subscription CLI such as Codex or Claude, write run state under
`.cognitive-firm-runs/`, and route accepted changes through the same governed
mutation, proof, replay, and runbook surfaces as fixture mode.

`.env.example` documents every environment variable the kernel and Orbit
dashboard read. Most variables are optional. Provider API keys are needed only
for model calls made by the kernel itself or by API-backed demos. Subscription
or local agent CLI paths, such as Claude Code or Codex, use their own local auth
unless you explicitly opt into API-key auth for spawned agents.

### Managing organizations and packages

`cognitive-firm-distro` is how you install and manage governed organizations
and packages — a governed organization in one action, rather than assembled by
hand from the protocol catalog:

```bash
cognitive-firm-distro list
cognitive-firm-distro install starter-firm --into ./my-firm
```

`install` is transactional and git-backed: the target becomes its own git
repository, the install lands as a commit tagged
`install/starter-firm/<version>`, and the installer verifies the new
organization's governance graph before committing it. A bad install is
reversible — `cognitive-firm-distro rollback starter-firm --into ./my-firm`.
The `cognitive-firm-distro` CLI also covers `show`, `verify`, `upgrade`,
`uninstall`, and `lint`; a package can be installed from a git URL (SHA-pinned,
recorded in a content-hashed `packages.lock`), and installing an overlay onto a
*running* org files a governed authority-diff proposal — a package may not
widen a role's authority. See
[`docs/protocols/distribution.md`](docs/protocols/distribution.md).

**Building and publishing your own package** — distro or overlay — is covered
in [`docs/community-packages.md`](docs/community-packages.md): the publication
rule (authorship is open, adoption is governed), the step-by-step authoring
loop (`lint` → `--dry-run` → verify install → publish as a git repo, no
central registry), and a roadmap of suggested packages the ecosystem could use. Start
from the template at
[`docs/templates/package/`](docs/templates/package/README.md).

The userland sits above the kernel as the human-facing layer. The
`cognitive-firm-userland` CLI shows what needs a human and the shared
vocabulary:

```bash
cognitive-firm-userland needs-me <actor_id>   # the accountable actor's attention queue
cognitive-firm-userland inbox <actor_id>      # a member-human's bounded work
cognitive-firm-userland vocabulary            # the shared userland glossary
cognitive-firm-userland commands "adoption readiness packet"
cognitive-firm-userland commands "field pilot action impact demo" --role-id role.manager
cognitive-firm-userland status                # plain-language org health
cognitive-firm-userland resolve <gate_id> --option <opt>   # resolve a pending gate
cognitive-firm-userland proposals             # governance changes awaiting review
cognitive-firm-userland proposal <proposal_id> # evidence + invariant detail
cognitive-firm-userland proposal-packet <proposal_id> --markdown
cognitive-firm-userland proposal-template --change-kind route_policy_change
cognitive-firm-userland proposal-from-candidate <candidate_id> --target-ref org/policies/example.md
cognitive-firm-userland work-context --assigned-to role.manager --cue "queue stalls"
cognitive-firm-userland work-context --cue-signature formal_verification.provider_payload --resource-ref formal_provider:trusted_checker --topology-ref state_surface:formal_verifications
cognitive-firm-userland context-packet-verify work-context.json
cognitive-firm-userland human-pressure --agent-counterparty-role role.manager --tenant-id tenant-a
cognitive-firm-userland learning-candidates --source human_work
cognitive-firm-userland lease-acquire governance_change:gcp_1:decision --actor human.principal --role role.principal
cognitive-firm-userland leases --state active
cognitive-firm-userland lease-release <lease_id> --actor human.principal --role role.principal
cognitive-firm-userland decision-profiles # evidence-only procedure recipes
cognitive-firm-userland decision-open --subject-ref governance_change:gcp_1 --decision-class route_policy_change --scope-kind tenant --scope-ref tenant-a --procedure-profile majority --eligibility-basis "reviewer sample" --eligible-role role.reviewer_a --eligible-role role.reviewer_b --eligible-role role.reviewer_c
cognitive-firm-userland decision-position dac_1 --actor-id human.alice --role-id role.reviewer_a --position approve --rationale "reviewed the evidence"
cognitive-firm-userland decision-compute dac_1 # compute recommendation, not authority
cognitive-firm-userland receipt <human_work_session_id> --actor principal --summary "reviewed agent output" --agent-output-ref artifact://draft --action-attestation-ref action_attestation:aat_123
cognitive-firm-userland learning-use <learning_event_id> --role role.manager --cue "queue stalls" --outcome applied --context-packet-ref <ctx_id>
cognitive-firm-userland learning-use <learning_event_id> --role role.manager --cue "queue stalls" --outcome applied --context-packet-json work-context.json
cognitive-firm-userland learning-loop <learning_event_id> # one learning unit's loop state
cognitive-firm-userland timeline --run-id <run_id> # readable provenance timeline
cognitive-firm-userland graph --run-id <run_id> # projection-only provenance graph
cognitive-firm-userland provenance-report --run-id <run_id> --markdown
cognitive-firm-userland approve <proposal_id> # approve a governance change
cognitive-firm-userland decline <proposal_id> # decline a governance change
```

`proposals` / `approve` / `decline` are the governed-install human-review
loop: a governance-change proposal awaits an accountable actor decision, and
`approve` / `decline` each record an attested kernel event.
Terminal write commands such as `approve`, `decline`, `receipt`,
`learning-use`, `proposal-from-candidate`, `decision-open`,
`decision-position`, `decision-compute`, and `decision-route-escalation` accept
`--lease-id` and `--fencing-token` when the service runs in lease-required
mode. `lease-acquire`, `leases`, and `lease-release` close that terminal loop:
they let an operator obtain the fenced mutation evidence, inspect active
claims, and release a claim without adding a workflow engine above the kernel.
`proposal` shows the evidence, rollback, predicted effect, sufficiency, and
invariant checks for one proposal. `proposal-packet` packages the same review
facts with evidence refs, invariant rows, selected provenance, review
questions, and optional Markdown for a portable human handoff.
`proposal-template` prints a service-owned request skeleton for
`POST /kernel/governance-changes`. The service also
exposes `GET /kernel/governance-changes?view=review` as a read-only proposal
review projection for custom surfaces: review state, evidence status, missing
evidence, invariant gaps, and the decision route without a new proposal
lifecycle.
`commands --role-id` keeps command discovery projection-only while tracing
whether that source role's escalation chain reaches the authority domain for a
typed command effect such as `decision_class: policy_change`.
`proposal-from-candidate` turns a learning-transition candidate into a
governance-change proposal through the existing service route. The candidate
contributes rationale and source refs, but the caller must still provide a
target, expected behavior change, risk, rollback, and invariant evidence; weak
requests remain `blocked`.
`work-context` shows the pre-work context packet; `context-packet-verify`
recomputes a captured packet digest without writing state; `learning-use`
records the later auditable receipt for whether that approved learning was
applied, ignored, deferred, or merely encountered. When supplied with
`--context-packet-json`, `learning-use` also verifies that the captured packet
contains the target learning event. `learning-loop` joins one approved learning
event to its context-packet refs, verified packet refs, encounters, outcome
links, routine reviews, overdue review ids, and evidence refs so an operator
can see whether the learning is compounding or still awaiting
measurement/review.
`work-context` can also use exact `cue_signature`, `resource_ref`, and
`topology_ref` filters from learning-event metadata, so tools, verifiers, and
state surfaces can retrieve relevant approved learning without inventing a new
role office or granting semantic memory authority. No-role structured queries
stay learning-only by default; use `--learning-only` on role-scoped context when
you want to suppress matching work candidates.
`human-pressure` surfaces repeated A2H human-work bottlenecks by role and
bottleneck class. It is observer-only: access/labor/cognition pressure can
suggest source repair, tooling, or mandate review, while taste, safety,
relationship, and authority work remains an explicit human boundary. Use
`tenant_id` / `project_id` selectors when inspecting multi-tenant logs.
`learning-candidates --source human_work` compiles whole-firm A2H pressure
groups into observer-only review candidates over existing human-work session
refs. It asks whether repeated pressure should become source repair, tooling,
mandate review, receipt discipline, or an intentionally preserved human
boundary; it does not automate, reroute, or close the work.
`receipt` records bounded human-work receipts, including the common
human-reviewed-agent-output pattern by citing both the agent output and its
action attestation. `timeline` renders the same read-only provenance projection
available through the kernel service. `graph` exposes the same selected records
as event/ref nodes plus projection-only edges, so adopters can build lineage,
network, and "why/what-after" views without creating a second workflow store.
`provenance-report` packages that same selected provenance into a portable
reviewer handoff: coverage status, source counts, caveats, review questions,
high-signal refs, a bounded timeline excerpt, and optional Markdown.
`commands` is a read-only command-surface helper over known Make targets and
Python scripts. It uses exact or separator-normalized matches to suggest
canonical repo commands for a task description, but does not execute commands,
schedule work, or mutate state.

Orbit renders first-party projection panes over these same routes
(`NeedsMePane`, `WorkInboxPane`, and `ProvenanceTimelinePane`). Orbit is one
surface; adopters can build their own dashboards against the service/userland
contract without changing the kernel source of truth.

---

## 6. Production deployment

VPS deployment uses systemd + bidirectional sync (mutagen) so the accountable
administrator can edit mandates from a laptop while the daemon ticks 24/7.

| Step | Path |
|---|---|
| 1. Provision VPS, install dependencies, configure `.env` | `scripts/setup_vps.sh` |
| 2. Configure Telegram bot (mobile pager + STOP) | `scripts/telegram_setup.py` |
| 3. Install + enable systemd unit | `deploy/agent-daemon.service` |
| 4. (Optional) Bidirectional sync laptop ↔ VPS for mandate edits | `deploy/orbit-sync.service` |
| 5. Tail with the operator console | `scripts/operator_console.sh` |

Multi-tenant deployment: keep tenant content in a sibling private repo
(`<tenant>-research-co/tenants/<tenant>/`) with `mandates/`, `roles/`,
`preferences/` overrides. Symlink overlays into `cognitive-firm/org/` via a
tenant setup script when running locally. The public git history and public
Docker image should not contain tenant files.

---

## 7. Status

cognitive-firm has a tested T1 kernel surface and a lean multi-actor authority
path through actor identity, actor membership, subject-scope checks, and
leases. The default boot path still assumes one authority role; the enterprise
multi-authority path is tracked in [`docs/ROADMAP.md`](docs/ROADMAP.md).
Adopters who read the protocol specs can rely on every "shipped" claim being
backed by tests in `tests/` and by the public verification commands:

```bash
make release-candidate-check

# Split form:
make smoke-public
make smoke-docker
make public-claims-check
make release-hygiene-check
make release-diff-audit
```

`smoke-public` uses deterministic fixtures. Optional live-agent demos are
validated separately because they depend on a local subscription CLI, current
login state, and model behavior. A bounded live proof should use a small budget
and inspect the emitted planner receipt, mutation proof, report JSON, and
operator runbook before treating it as release evidence.

### Shipped (T1 tested)

| Primitive | Where | Tests |
|---|---|---|
| Outbox relay (MCP transport) | `src/cognitive_firm/role_extensions/mcp_bridge/` | `tests/test_mcp_outbox_relay.py`, `test_mcp_linear_server.py` |
| MCP transport parser | `src/cognitive_firm/role_extensions/mcp_bridge/transport.py` | `tests/test_mcp_transport.py` |
| Capability tokens for MCP dispatch | `src/cognitive_firm/role_extensions/mcp_bridge/capabilities.py` | `tests/test_mcp_capabilities.py` |
| A2A obligation lifecycle (Phase A) | `src/cognitive_firm/orchestration/agent_channels.py` | `tests/test_obligation_lifecycle.py`, `tests/test_a2a_delegation_command_conformance.py`, `tests/test_a2a_h2a_command_conformance.py` |
| Artifact dependencies (Phase B) | `src/cognitive_firm/orchestration/artifact_dependencies.py` | `tests/test_artifact_dependencies.py` |
| Saga compensation (Phase C) | `src/cognitive_firm/orchestration/saga_compensation.py` | `tests/test_saga_compensation.py`, `tests/test_saga_command_conformance.py` |
| Project charter parser | `src/cognitive_firm/orchestration/project_charter.py` | `tests/test_project_charter.py` |
| Evidence gap state | `src/cognitive_firm/orchestration/evidence_gaps.py` | `tests/test_evidence_gaps.py` |
| Human work sessions + A2H helper | `src/cognitive_firm/orchestration/human_work.py` | `tests/test_human_work.py` |
| Action attestations | `src/cognitive_firm/orchestration/action_attestation.py` | `tests/test_action_attestation.py` |
| Formal verification records and provider proof packs | `src/cognitive_firm/orchestration/formal_verification.py` | `tests/test_formal_verification.py`, `tests/test_formal_provider_bundle_demo.py`, `tests/test_formal_provider_proof_pack_script.py` |
| Governed-run attestation bundle + validation route | `src/cognitive_firm/orchestration/artifact_bundle.py`, `src/cognitive_firm/kernel_service.py` | `tests/test_governed_run_attestation_bundle.py`, `tests/test_kernel_service.py`, `schemas/governed-run-attestation.v1.schema.json` |
| Governed mutation proof chain + validation route | `src/cognitive_firm/orchestration/mutation_proofs.py`, `src/cognitive_firm/kernel_service.py` | `tests/test_mutation_proofs.py`, `tests/test_kernel_service.py`, `tests/test_self_evolving_org_demo.py` |
| Audit integrity manifests | `src/cognitive_firm/orchestration/audit_integrity.py` | `tests/test_audit_integrity.py` |
| Accountability cases | `src/cognitive_firm/orchestration/accountability_cases.py` | `tests/test_accountability_cases.py` |
| Forecast market interface | `src/cognitive_firm/orchestration/forecast_market.py` | `tests/test_forecast_market_interface.py` |
| Action-impact interface | `src/cognitive_firm/orchestration/action_impact.py` | `tests/test_action_impact_interface.py` |
| Intelligence-source coverage | `src/cognitive_firm/orchestration/intelligence_sources.py` | `tests/test_intelligence_sources.py`, `scripts/source_coverage_walkthrough.py` |
| Accountability summary | `src/cognitive_firm/orchestration/accountability.py` | `tests/test_accountability.py` |
| Organization surface read model | `src/cognitive_firm/orchestration/org_surface.py` | `tests/test_org_surface.py` |
| Execution routing contracts | `src/cognitive_firm/orchestration/execution_routing.py` | `tests/test_execution_routing.py`, `tests/test_human_work.py` |
| Run checkpoint interface | `src/cognitive_firm/orchestration/run_checkpoints.py` | `tests/test_run_checkpoints.py` |
| Runtime adapter interface | `src/cognitive_firm/orchestration/runtime_adapters.py` | `tests/test_runtime_adapters.py`, `tests/test_runtime_interrupt_command_conformance.py` |
| Agent runtime invocation receipts and readiness summaries | `src/cognitive_firm/orchestration/agent_runtime_invocation.py` | `tests/test_agent_runtime_invocation.py`, `tests/test_llm_runtime_providers.py`, `tests/test_self_evolving_agent_preflight.py` |
| Multi-agent trace attribution and failure packets | `src/cognitive_firm/orchestration/multi_agent_trace_attribution.py` | `tests/test_multi_agent_trace_attribution.py`, `tests/test_multi_agent_trace_attribution_demo.py`, `tests/test_kernel_service.py` |
| Phase execution overlay | `src/cognitive_firm/orchestration/phase_execution.py` | `tests/test_phase_execution.py`, `tests/test_phase_execution_demo.py`, `tests/test_kernel_service.py` |
| Protocol experiment reports | `src/cognitive_firm/orchestration/protocol_experiments.py` | `tests/test_protocol_experiments.py`, `tests/test_protocol_experiment_demo.py`, `tests/test_kernel_service.py` |
| Capability signals | `src/cognitive_firm/orchestration/capability_signals.py` | `tests/test_capability_signals.py`, `tests/test_capability_signal_demo.py`, `tests/test_kernel_service.py` |
| Adapter conformance reports and manifests | `src/cognitive_firm/orchestration/adapter_conformance.py` | `tests/test_adapter_conformance.py` |
| OpenTelemetry projection | `src/cognitive_firm/orchestration/otel_export.py` | `tests/test_otel_export.py` |
| State backend connectors | `src/cognitive_firm/orchestration/state_backends.py` | `tests/test_state_backends.py` |
| Kernel service boundary | `src/cognitive_firm/kernel_service.py` | `tests/test_kernel_service.py` |
| App integration boundary | `src/cognitive_firm/orchestration/app_integrations.py` | `tests/test_app_integrations.py` |
| Inbound event ingestion | `src/cognitive_firm/orchestration/inbound_events.py` | `tests/test_inbound_events.py` |
| Identity provider adapters | `src/cognitive_firm/identity_providers.py` | `tests/test_identity_providers.py`, `tests/test_kernel_service.py` |
| Identity provisioning | `src/cognitive_firm/identity_provisioning.py` | `tests/test_identity_provisioning.py` |
| Actor identity | `src/cognitive_firm/orchestration/actor_identity.py` | `tests/test_actor_identity.py` |
| Actor membership | `src/cognitive_firm/orchestration/actor_membership.py` | `tests/test_actor_membership.py`, `tests/test_kernel_service.py` |
| Tenant isolation guard | `src/cognitive_firm/orchestration/tenant_isolation.py` | `tests/test_tenant_isolation.py` |
| Resource leases | `src/cognitive_firm/orchestration/leases.py` | `tests/test_leases.py` |
| Kernel event envelope | `src/cognitive_firm/orchestration/kernel_events.py` | `tests/test_kernel_events.py` |
| Resource envelope | `src/cognitive_firm/orchestration/resource_envelope.py` | `tests/test_resource_envelope.py` |
| Provenance timeline, graph, and portable handoff report projections | `src/cognitive_firm/orchestration/provenance_timeline.py`, `src/cognitive_firm/kernel_service.py` | `tests/test_provenance_timeline.py` |
| Policy decisions | `src/cognitive_firm/orchestration/policy_decisions.py` | `tests/test_policy_decisions.py` |
| Decision aggregation cases | `src/cognitive_firm/orchestration/decision_aggregation.py` | `tests/test_decision_aggregation.py`, `tests/test_kernel_service.py` |
| Migration records | `src/cognitive_firm/orchestration/migrations.py` | `tests/test_migrations.py` |
| State surface inventory | `src/cognitive_firm/orchestration/state_surface_inventory.py` | `tests/test_state_surface_inventory.py` |
| Governance change proposals | `src/cognitive_firm/orchestration/governance_changes.py` | `tests/test_governance_changes.py` |
| Learning transition compiler | `src/cognitive_firm/orchestration/learning_transition_compiler.py` | `tests/test_learning_transition_compiler.py` |
| Approved learning events | `src/cognitive_firm/orchestration/learning_events.py` | `tests/test_learning_events.py` |
| Learning-carrier work discovery and pre-work context projection | `src/cognitive_firm/orchestration/work_discovery.py`, `src/cognitive_firm/kernel_service.py` | `tests/test_work_discovery_learning_carriers.py`, `tests/test_kernel_service.py` |
| Operating-unit contracts | `src/cognitive_firm/orchestration/operating_units.py` | `tests/test_operating_units.py` |
| Durable work-item queue | `src/cognitive_firm/orchestration/work_items.py` | `tests/test_work_items.py`, `tests/test_kernel_service.py` |
| Operating-unit dashboard | `src/cognitive_firm/orchestration/operating_unit_surface.py` | `tests/test_operating_unit_surface.py` |
| Outcome links (learning → measured outcome) | `src/cognitive_firm/orchestration/outcome_links.py` | `tests/test_outcome_links.py` |
| Routine reviews (forgetting lifecycle) | `src/cognitive_firm/orchestration/routine_reviews.py` | `tests/test_routine_reviews.py` |
| Governed resource allocation | `src/cognitive_firm/orchestration/resource_allocation.py` | `tests/test_resource_allocation.py` |
| Residual decision rights | `src/cognitive_firm/orchestration/decision_rights.py` | `tests/test_decision_rights.py` |
| Distribution layer (install / verify / rollback / upgrade / lint, `op` composition, `extends`) | `src/cognitive_firm/distribution/` | `tests/test_distribution.py`, `tests/test_rollback.py`, `tests/test_distro_content.py`, `tests/test_overlay_composition.py` |
| Governed overlay install and no-write overlay preview (authority diff, file plan, `package.install_approved`) | `src/cognitive_firm/distribution/governed_install.py` | `tests/test_governed_install.py` |
| Remote packages (git-URL fetch, SHA pin, content-hashed lockfile) | `src/cognitive_firm/distribution/remote_registry.py`, `lockfile.py` | `tests/test_remote_registry.py` |
| Userland — enrollment, attention router, needs-me, work inbox, vocabulary, surface policy | `src/cognitive_firm/userland/` | `tests/test_attention_router.py`, `tests/test_needs_me.py`, `tests/test_work_inbox.py`, `tests/test_vocabulary.py`, `tests/test_enrollment.py`, `tests/test_surface_policy.py` |
| Userland CLI + kernel routes (`needs-me` / `inbox` / `vocabulary` / `commands` / `operator-path` / `status` / `resolve` / `proposals` / `proposal` / `proposal-packet` / `proposal-template` / `proposal-from-candidate` / `work-context` / `context-packet-verify` / `human-pressure` / `learning-candidates` / `lease-acquire` / `leases` / `lease-release` / `decision-profiles` / `decision-cases` / `decision-open` / `decision-position` / `decision-compute` / `decision-route-escalation` / `receipt` / `learning-use` / `learning-loop` / `timeline` / `graph` / `provenance-report` / `approve` / `decline`; `GET /kernel/attention`, `GET /kernel/vocabulary`, `GET /kernel/command-surface`, `GET /kernel/operator-path`, `GET /kernel/governance-change-template`, `GET /kernel/governance-changes`, `GET /kernel/governance-changes?view=review`, `GET /kernel/governance-changes/{id}/review-packet`, `GET /kernel/leases`, `GET /kernel/decision-procedure-profiles`, `GET /kernel/decision-aggregation-cases`, `GET /kernel/learning-transition-candidates`, `GET /kernel/learning-events/{id}/loop`, `GET /kernel/work-discovery`, `POST /kernel/work-discovery/context-packet/verify`, `GET /kernel/human-work-pressure`, `GET /kernel/provenance-timeline`, `GET /kernel/provenance-graph`, `GET /kernel/provenance-report`, `POST /kernel/leases`, `POST /kernel/leases/{id}/release`, `POST /kernel/decision-aggregation-cases`, `POST /kernel/decision-aggregation-cases/{id}/positions`, `POST /kernel/decision-aggregation-cases/{id}/compute`, `POST /kernel/decision-aggregation-cases/{id}/route-escalation`, `POST /kernel/human-work/{id}/receipt`, `POST /kernel/learning-event-encounters`, `POST /kernel/learning-transition-candidates/{candidate_id}/governance-change`, `POST /kernel/governance-changes/{id}/decision`) | `src/cognitive_firm/userland/cli.py`, `src/cognitive_firm/kernel_service.py`; Orbit projection panes under `orbit/src/components/` | `tests/test_userland_cli.py`, `tests/test_kernel_service_userland.py`, `tests/test_governance_changes.py`, `tests/test_learning_events.py`, `tests/test_provenance_timeline.py`; Orbit TypeScript/build smoke |
| Primitive extension schemas | `src/cognitive_firm/orchestration/extension_schemas.py` | `tests/test_extension_schemas.py` |
| EU AI Act deploy gate | `src/cognitive_firm/orchestration/eu_ai_act_deploy_gate.py` | `tests/test_eu_ai_act_deploy_gate.py`; `docs/protocols/eu-ai-act-deploy-gate.md` |
| Property-based invariants (Hypothesis) | `tests/test_invariants_property_based.py` | 8/8 |
| Cross-primitive integration tests | `tests/test_cross_primitive_integration.py` | 3/3 |
| Daemon bug-audit regression | `tests/test_daemon_bug_audit.py` | passing |
| Telegram callback flow | `tests/test_telegram_callback_flow.py` | passing |
| Mandate hash verification | every daemon tick | runtime invariant |
| Telegram pager + STOP | `src/cognitive_firm/notifications/` | provider interface + callback tests |
| Orbit dashboard (TLDraw v2) | `orbit/` | TypeScript check + production build in smoke |

### Queued

- **MCP Phase 3**: supply-chain pinning (digest + signed manifest + revocation feed)
- **MCP Phase 4**: IdP federation
- **A2A remote adapter**: cross-VPS role-to-role messaging

### Deferred (T2 reactivation triggers)

Enterprise SSO administration, signed audit trail with TSA, event-outbox to Postgres, multi-server quorum, observability stack, cold-start recovery from snapshot, and tenant isolation across separate authority domains. Each has an explicit reactivation trigger documented in `docs/PROTOCOLS.md`; the repo should not imply deployment coverage it has not tested.

---

## 8. Adoption

Start with [`docs/adopting-cognitive-firm.md`](docs/adopting-cognitive-firm.md).
The short version: keep the public kernel generic, put organization-specific
roles and project content in a tenant overlay, and inspect the organization
surface before material work.

## 9. License & provenance

**License**: Apache-2.0 (see `LICENSE` and `NOTICE`). Commercial use and modification are permitted; the only requirements are preserving the copyright notice and license terms in derivative works, and stating any significant changes you make. There is no source-availability restriction, no Business Source License, no dual-licensing — just Apache-2.0.

**Contributing**: see `CONTRIBUTING.md`.

**Provenance**: Extracted from a production research apparatus on 2026-05-07. Theoretical grounding (Chandlerian M-form, Holmström informativeness, Tirole incomplete contracts, Nelson & Winter routines) is developed in a companion paper: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6543019
