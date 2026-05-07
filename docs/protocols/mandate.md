# Mandate Protocol

**Status:** production-stable since 2026-04. The kernel verifies the mandate hash each tick.
**Modules:** role yaml in `org/roles/<role_id>.yaml`; prose mandate in `org/mandates/<role_id>_mandate.md`.

The mandate is the **typed authority contract** that defines what a role may do autonomously vs. what requires escalation to the principal. It is the structural primitive that prevents agent-CLI subprocesses from re-negotiating their own scope at runtime.

## Two-file structure

Each role has exactly two mandate files:

### `org/roles/<role_id>.yaml` — the structured part

Schema-governed fields the kernel parses programmatically:

```yaml
schema_version: 1
role_id: research_director
role_class: director
description: >
  One-paragraph summary the principal can read at-a-glance.

authorized_paths:
  - "projects/*/workspace/"
  - "research_areas/"
  - "docs/"
  - "org/sessions/"

forbidden_paths:
  - "org/mandates/"          # cannot modify own mandate
  - "org/roles/"             # cannot modify roles

authorized_models:
  cheap: true
  mid: true
  pro: false                 # off by default; principal-extension authority required

authorized_mcp_capabilities:
  - server: linear
    tools: [list_issues, get_issue, list_projects]
    scope: read_only
    rationale: "describe why this role needs Linear read access"

budget_caps:
  per_action_usd_max: 0.50
  per_session_usd_max: 5.00
  per_day_usd_max: 15.00
  agent_cli_minutes_per_day: 60

cross_family_hygiene:
  required: true
  rule: |
    For any judge-mutator pair, judge family must differ from mutator family.

agent_cli_runtime: claude         # or "codex", "none"

delegates_to: [debate_runner]
escalates_to: [principal]

work_discovery_hooks:
  - discover_open_todos
  - discover_principal_goals
```

The kernel reads this file at every tick and refuses to dispatch any action whose target violates the schema.

### `org/mandates/<role_id>_mandate.md` — the prose part

Free-form discipline the principal authors. Examples of what goes here:

- **RUN-VS-ANALYZE discipline** — "default ANALYZE; escalate to RUN only when a falsifiable hypothesis is on the table."
- **Recursion guards** — "do not produce a new pending gate to execute a resolved gate (the meta-approval loop guard)."
- **Charter-contamination rules** — "do not include ground-truth derivations in the project_charter.md."
- **Cross-family hygiene rules** — beyond the structured `cross_family_hygiene` field above.
- **Damage-signal classes** — what events the role should raise via `cognitive_firm.signals.damage.emit()`.
- **Provenance** — which seam the role rescues, what its origin GP-### is.

The prose mandate is loaded into the agent CLI's context at every tick. Edits to the prose mandate change the **mandate hash**, which the kernel verifies before each dispatch — a stale agent CLI carrying an old mandate cannot dispatch.

## Mandate-hash verification

At every tick, the daemon:

1. Computes `sha256(role_yaml_text + mandate_md_text)`.
2. Compares to the hash recorded at the previous tick.
3. If different, emits a `mandate_drift` cosmetic signal (informational; this is a normal edit-and-restart pattern).
4. Dispatches with the current mandate.

The agent CLI subprocess receives the current mandate text in its context. There is no caching that could allow a stale mandate to govern a new dispatch.

## Authority semantics

The mandate defines four authority levels for any candidate action:

| Level | Authority | Surface |
|-------|-----------|---------|
| **Autonomous** | Role may dispatch without principal review | `authorized_paths` matches + `budget_caps` passes |
| **Gated** | Principal must APPROVE before dispatch | Path or budget exceeds autonomous threshold |
| **Out-of-scope** | Cannot be dispatched at all | `forbidden_paths` matches OR mandate-hash drift |
| **Principal-extension** | Principal explicitly extends authority for one task | Per GP-229 — see `docs/concepts/principal_extension.md` |

The kernel's `task_authorization.authorize_dispatch()` is the deterministic gate that maps every candidate to one of these four levels. The function is pure (no LLM, no network); its output is reproducible from the role config + candidate args.

## Property-based invariants

`tests/test_invariants_property_based.py` runs Hypothesis-driven random inputs against the mandate-enforcement primitives. Seven invariants:

- **I1** Forbidden-paths-take-precedence — `forbidden_paths` overrides any `authorized_paths` match.
- **I2** Authorized-paths-required-for-unattended — a path matching no authorized pattern returns `allowed=False`.
- **I3** Budget-caps-fail-closed — `estimated_cost > single_action_cap_usd` returns `allowed=False` with `required_approval=principal`.
- **I4** Wildcard-pattern-matches-all — `*` authorizes any path (the well-known kernel-bypass case principals must consciously enable).
- **I5** Decision-idempotency — `authorize_dispatch` is a pure function of (role config, candidate args).
- **I6** No-LLM-at-projection — projecting an MCP response on an unregistered (server, tool) returns `mcp_call_failed`; never silently LLM-interpreted.
- **I7** Idempotency-key-determinism — same causality + same payload produces same key.

Each invariant runs ~50-100 randomized examples per test session. 8/8 passing.

## Why the two-file split

The structured/prose split exists because:

- **Structured part is parsable** — the kernel can validate, diff, and enforce it.
- **Prose part is human-readable** — the principal can write nuanced discipline that no schema captures (e.g., "be calibrated about novelty claims; if synthesis-with-formalization is the honest tier, say so").
- **Hash covers both** — drift in either file invalidates the cached mandate, forcing the next tick to read fresh.

This is the same separation that makes legal contracts effective: the boilerplate is structured (party names, dates, dollar amounts) and the substantive obligations are prose. cognitive-firm imports that pattern.

## Threat-model coverage

| Primitive | T1 (single-principal) | T2 (regulated enterprise) |
|-----------|----------------------|---------------------------|
| Two-file mandate (yaml + md) | shipped | shipped |
| Mandate-hash verification each tick | shipped | shipped |
| `authorized_paths` / `forbidden_paths` | shipped | shipped |
| Budget caps (per-action, session, day) | shipped | shipped |
| `authorized_mcp_capabilities` (Phase 2) | shipped | shipped |
| Property-based invariants test suite | shipped | shipped |
| Mandate version control via git | shipped | shipped |
| Mandate signing (cryptographic, beyond git commit signing) | not needed | **queued** Phase 3 if needed |
| Multi-principal mandate (joint signing) | not needed | **queued** if multi-principal mode lands |
| EU AI Act deploy-gate (mandate field `t2_deployment: bool`) | not needed | **queued** task #206 |
