# `org/` — Organizational Primitives

This top-level folder houses the structural primitives for an organization that
uses persistent role offices: **roles** (identity and authority), **mandates**
(authorization scope per role), **delegation graph** (who reports to whom),
**tasks** (work packets), **execution routes** (how work should be handled),
**sessions** (per-role audit windows), and generic surfaces that tenant
overlays can bind to project charters, evidence gaps, forecasts, and policy
adapters.

`org/` is domain-general. A travel agency, fintech startup, or scientific
research lab should be able to reuse this skeleton. Tenant-specific language
belongs in role mandates, task bodies, project folders, or backend adapters,
not in the core org primitive.

Kernel rule: `org/` owns mechanisms, not policy. Roles, mandates, claims,
routes, budgets, inboxes, and transitions are the stable kernel surface.
Domain policy is loaded through roles, mandates, preferences, tasks, and
backend adapters. If a generic primitive needs tenant-specific vocabulary to
make sense, it is probably not generic enough.

Human adopters can fork this kernel without adopting any local tenant. The
adoption path is documented in `docs/adopting-cognitive-firm.md`; the short
rule is to keep private roles, project content, evidence, and preferences in a
tenant overlay while promoting only reusable mechanisms back into the kernel.

## Why this is a top-level folder

Org structure is configuration of the organization, distinct from project
content and runtime machinery. Placing it at the root makes roles, mandates,
delegation, tasks, and sessions discoverable for humans and agents.

## Layout

```
org/
├── README.md                  # this file
├── roles/                     # public: persistent role definitions
│   ├── principal.yaml         # root authority (the human)
│   ├── manager.yaml           # operational manager
│   ├── research_director.yaml # external-validity / frontier direction
│   ├── engineer.yaml          # production-code engineer
│   └── reviewer.yaml          # independent reviewer
├── delegation.yaml            # public: cross-role edges + signing authority
├── mandates/                  # templates public; real mandates gitignored
│   ├── README.md
│   ├── templates/
│   ├── manager_mandate.md             # local/private
│   └── research_director_mandate.md   # local/private
├── tasks/                     # work packets + execution-route frontmatter
├── evidence_gaps/             # typed missing-evidence state
├── human_work/                # bounded human work sessions
└── sessions/                  # GITIGNORED: per-role audit windows
    └── <role_id>/<timestamp>/
        ├── transcript.md
        ├── actions.jsonl
        └── spend.json
```

## The primitives

### 1. Role (persistent contract)

Defined in `org/roles/<role_id>.yaml`. A role specifies:
- Identity (role_id, display_name, description)
- Classification (manager / worker / reviewer / specialist)
- Runtimes it can use (CLI agent, hosted model, daemon, human, or service)
- Authorized / forbidden filesystem paths
- Delegation outgoing edges (who this role may invoke)
- Escalation outgoing edges (who this role escalates to)
- Budget caps (daily / session / single-action)
- SLA expectations and failure mode
- Reference to the mandate document that expands the authorization

A role persists indefinitely. A runtime may come and go, but the role
definition is the contract that constrains every runtime acting in that role.

### 2. Mandate (authorization)

Defined locally in `org/mandates/<role_id>_mandate.md`. Real mandates are
gitignored because they contain personal and IP-sensitive context (research
program state, patent portfolio, principal context). Public templates live in
`org/mandates/templates/`. The mandate expands the role YAML with:
- Scope of autonomous action (what the role does without asking)
- Scope of inbox escalation (what needs principal review at leisure)
- Scope of push escalation (what needs immediate principal attention)
- Absolute forbidden actions (what requires explicit written approval)
- Standing context (current research programs, preferences, relationships)

### 3. Session (execution window)

Defined in `org/sessions/<role_id>/<timestamp>/`. Gitignored because
sessions are personal activity logs. Each session contains:
- `transcript.md` — summary of what happened in this window
- `actions.jsonl` — append-only log of significant actions
- `spend.json` — cost telemetry for this session (matches spend_tracker schema)

Sessions enable (a) per-role daily/weekly spend rollups, (b) audit trail
for what a role actually did, (c) cross-session state handoff.

### 4. Task + Execution Route (generic work decomposition)

Defined in `org/tasks/{pending,active,done}/<task_id>.md`. A task says what
the organization wants done. The execution route says how it should be done:

- `route_only` — decide the route and create the next task.
- `direct_work` — a role-bearing agent can do the work directly.
- `expert_review` — use a bounded expert/adversarial review packet.
- `scripted_run` — run a script or external compute job with telemetry.
- `artifact_build` — build a reusable artifact/contract/workflow.
- `experiment_loop` — run a repeatable candidate-search loop after preflight.
- `docs_records` — update documentation, ledgers, manuals, or public/private mirrors.

These route names are intentionally generic. In one tenant, `experiment_loop`
could mean a scientific candidate loop. In another company, it could mean a
pricing A/B loop, and `artifact_build` could mean a supplier onboarding
workflow. The org layer should not know the domain; adapters and mandates bind
the generic route to a local backend.

### 5. Project Charter (tenant scope fidelity)

Project charters are tenant/project artifacts, not public-kernel policy. The
kernel documents the shape: core question, out-of-scope boundaries, end states,
forecast type, inheritance, and anchor proxies. A tenant decides which projects
need charters, which anchors are executable, and which validators can block
dispatch.

Recommended tenant path:

```text
tenants/<tenant_id>/projects/<project_id>/project_charter.md
```

See `docs/protocols/project-charter.md`.

### 6. Organizational Learning Carriers

Durable learning should land in a state object future roles must encounter:
mandate updates, charter updates, evidence gaps, forecast calibration rows,
damage signals, human work sessions, A2A obligations, artifact dependencies,
route changes, or tenant policy adapter changes. Retrospectives and notes are
useful, but they compound only after they alter one of these surfaces.

See `docs/organizational_learning_loop.md`.

### 7. Filesystem State Backend (current dogfood implementation)

The org runtime is currently filesystem-backed. That is a design choice for
inspectability and dogfood velocity, not a claim that every enterprise
deployment should use a shared folder forever.

The active state surfaces are:

- `org/tasks/` — assignable work and task closure.
- `org/channels/` — role-to-role messages.
- `org/sessions/` — session/audit windows and claims.
- `org/signals/` — damage signals.
- tenant workspace gates — principal/executive decisions.
- tenant workspace transition log — append-only transition trail.
- `org/evidence_gaps/` — missing evidence/comparator/adversarial checks.
- `org/human_work/` — bounded human work and integration state.

`cognitive_firm.orchestration.org_surface` reads across these surfaces and
returns a tenant-neutral status brief for humans, agents, and dashboards.

This checkout still contains some inherited workspace path names in code and
examples. Treat those as adapter names, not kernel concepts. New public kernel
docs and tools should prefer tenant-neutral names.

Any daemon only sees the filesystem mounted into its process. If a task exists
on your laptop but the daemon is running on a VPS, the VPS will not see it
until you sync, mount, or otherwise replicate that state.

Deployment choices:

- **Local dogfood:** run daemon on the same checkout where tasks are written.
- **Single VPS:** copy/sync the repo plus private org state to the VPS, run
  daemons there, then sync results back.
- **Shared volume:** mount the same persistent volume into all daemon
  containers.
- **Enterprise backend:** replace the filesystem adapter with Postgres/object
  storage/event outbox while preserving the same logical primitives.

The kernel primitive is not "markdown files." The primitive is durable,
inspectable, claimable work state. Markdown files are the current adapter.

## Relationship to Work Orchestration

Work orchestration tracks work items, stages, gates, and closure. `org/` tracks
structure: roles, mandates, and delegation. These are separate:

- A work item has an `owner_role` pointing into `org/roles/`
- Gate signing authority per gate type is looked up via
  `org/delegation.yaml`
- A session happens whenever a role acts, regardless of which goals
  it touches

## Tenant-Specific Roles

The public kernel defines role and mandate mechanics. A tenant overlay decides
which role offices exist and what domain work they perform.

For example, one tenant might define a research director that reads durable
artifacts, reconstructs the next hostile discriminator, ranks candidate next
moves against `org/preferences/principal.yaml`, writes directives, enforces
checkpoint/telemetry discipline, and escalates overclaim or instrument-risk
signals. Another tenant might define an operations director or compliance
reviewer with the same mandate mechanics but different policy.

The operating philosophy is generic:

```text
operator <-> agent discovers a useful move
-> artifacts record it
-> a role office replays/ranks it
-> a tenant adapter or engineer mechanizes the stable subroutine
```

Exploration may be manual. Durable learning should not remain manual.

## CLI

```
cognitive-firm role list                     # list all roles
cognitive-firm role inspect <role_id>        # show role + mandate + recent sessions
cognitive-firm role delegate <role> <task>   # create a session, attach work
cognitive-firm session list <role_id>        # list this role's sessions
```

## Docker / daemon boot path

For the public setup path, see `docs/first-30-minutes.md` and
`docs/adopting-cognitive-firm.md`.

Before a daemon acts, the boot contract is:

1. `AGENTS.md` — repo-wide constitution loaded by every agent.
2. `org/roles/<role>.yaml` — role scope, budget, path constraints.
3. `org/mandates/<role>_mandate.md` — role-specific authority.
4. `org/preferences/<member>.yaml` — private preference/taste model.

`scripts/org_first_run_setup.py --init-private --skip-smoke` copies public
templates into missing local private mandate/preference files.
`scripts/org_role_preflight.py` checks these exist. `scripts/agent_daemon.py`
also tells the spawned runtime to read them. This matters in Docker because
not every agent host auto-discovers `AGENTS.md` the way Codex/Claude do in an
interactive repo session.

Dry-run a role against the current preferences:

```bash
python scripts/org_role_preflight.py --role <role_id>
python scripts/agent_daemon.py --role <role_id> --tick-once --dry-run
```

Run it continuously:

```bash
docker compose --profile daemons up <role-service>
```

The Docker service is only a process wrapper. It does not grant authority. The
role YAML, private mandate, private preference file, task assignment, and
principal approvals remain the authority surfaces. Full execution also requires
the configured agent runtime inside the container or a host daemon with the
agent CLI already authenticated.

Runtime identity is configurable. Example:

```bash
COGNITIVE_FIRM_MEMBER_ID=codex COGNITIVE_FIRM_AGENT_CLI=codex COGNITIVE_FIRM_AGENT_ADAPTER=codex_exec docker compose --profile daemons up <role-service>
```

Runtime adapter configuration names identify the member/runtime written to
sessions, executable used for task execution, and noninteractive runtime
adapter. Supported adapters today are `claude_print` and `codex_exec`; `auto`
infers from the executable name.

## Companion Paper Connection

This folder is the practical instantiation of the companion paper's role-office
architecture. Key paper claims grounded here:
1. Roles are persistent contracts; runtimes are interchangeable bodies
2. Workers are ephemeral; managers are backed by persistent or session
   runtimes -- the role is always persistent
3. Organizational leverage concentrates in role definition, not worker selection

<!-- AUTO-INDEX:START (managed by scripts/gen_folder_index.py — edit prose OUTSIDE this block) -->

## Index

**Sub-folders**

- [`mandates/`](mandates/) - 3 file(s)
- [`patterns/`](patterns/) - 3 file(s)
- [`preferences/`](preferences/) - 2 file(s)
- [`roles/`](roles/) - 7 file(s)

**Documents**

- [bootstrap_manifest.yaml](bootstrap_manifest.yaml)

<sub>4 sub-folder(s), 1 document(s). Auto-generated; re-run `scripts/gen_folder_index.py` after adding files.</sub>

