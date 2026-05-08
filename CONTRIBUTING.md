# Contributing to cognitive-firm

Thanks for considering a contribution. This kernel runs in production for a single-principal research org, so the bar for changes is "does it preserve the invariants" rather than "is it clever." Read this before opening a PR.

## TL;DR

1. Open an issue first for anything beyond a typo or one-line bug fix.
2. Every "shipped" claim in `docs/PROTOCOLS.md` must be backed by a test in `tests/`. New primitives ship with their tests in the same PR.
3. Run the test suite (`pytest tests/`) and the daemon preflight (`python scripts/org_role_preflight.py --role research_director`) before pushing.
4. Don't commit to `main` directly. PRs only.
5. By submitting a PR you are agreeing your contribution is under Apache-2.0 (see `LICENSE`).

## What kind of contributions are welcome

| Kind | Likely to be merged |
|---|---|
| Bug fix with a regression test | yes |
| New MCP server binding (Salesforce, Jira, GitHub, …) following the Linear example in `src/cognitive_firm/role_extensions/mcp_bridge/servers/linear.py` | yes |
| Per-protocol spec clarifications in `docs/protocols/` with a corresponding test that pins the new wording | yes |
| Cross-primitive integration tests under `tests/` | yes |
| Tenant overlay scripts / docs improvements in `tenants/README.md` | yes |
| Performance fix backed by a benchmark | yes |
| New primitive that re-implements something already shipped | no — discuss in an issue first |
| New protocol spec without an adopter signal | no — see "honest scope" in `docs/PROTOCOLS.md` |
| Refactor without a behavior-preserving test | no |
| Adding dependencies for cosmetic gains | no |
| Anything that breaks the invariants below | no |

## Invariants that must hold

These are not stylistic preferences — they are load-bearing contracts that the protocol specs publicly commit to.

### Authority is in the role yaml + mandate, not in code

Authorization decisions read from `org/roles/<role>.yaml` and `org/mandates/<role>_mandate.md`. Any check that hardcodes "if role == 'manager' then …" instead of looking up the mandate field is a regression. The mandate hash is verified each daemon tick.

### The system of record is `org/` + git

Any state that needs to survive a process restart must round-trip through `transitions.jsonl`, the `org/` filesystem, or git history. UIs (Orbit, Telegram) are projections — they read this state, they do not own it.

### One write per logical action — outbox pattern

External side effects (MCP dispatch, agent CLI invocation, Telegram message) are emitted as a request row to `transitions.jsonl` first, then dispatched by a relay. This is what makes crash-mid-dispatch retries safe. Direct side-effect-then-log is forbidden in primitive code.

### No LLM in projection paths

The `project_response` step in MCP transport, the predicate-eval check in artifact dependencies, and the gate-resolution path are deterministic. Adding "let an LLM interpret the response" to any of those is a regression — ambiguous returns are rejected, not interpreted.

### Threat model is honest

Each primitive's threat-model table in `docs/protocols/<protocol>.md` says T1 (single-principal trusted hardware) and T2 (regulated enterprise) status separately. A PR that claims T2 coverage for a primitive must add the corresponding test (e.g. for saga compensation: a test where a fulfilled ancestor refuses compensation and the chain surfaces `saga_compensation_unfulfilled`).

## Workflow

### 1. Open an issue first

Describe the problem, the proposed fix, and which invariant the fix relates to. For new primitives, link the relevant protocol spec section. For bug fixes, link a reproducer.

### 2. Branch

```bash
git checkout -b fix/<short-name>      # for fixes
git checkout -b primitive/<short-name>  # for new primitives
git checkout -b docs/<short-name>     # for spec/doc changes
```

### 3. Implement + test

Tests live in `tests/`, mirror the source path, and use the existing fixture pattern (`isolated_state` for primitives that touch `transitions.jsonl` or `org/channels/`). If your primitive touches multiple existing primitives, add a test under `tests/test_cross_primitive_integration.py`.

### 4. Run preflight

```bash
pytest tests/                                                          # all tests pass
python scripts/org_role_preflight.py --role research_director           # mandate hashes resolve
python scripts/agent_daemon.py --role research_director --tick-once --dry-run  # daemon ticks cleanly
```

### 5. Update docs

If you changed a protocol surface, update the corresponding spec in `docs/protocols/`. If you changed status (queued → shipped, etc.), update both the spec's status table and the README's status table.

### 6. Open the PR

Title: `<area>: <one-line>` (e.g. `mcp: add Salesforce server binding`, `a2a: fix saga walk past max_depth`).

Body: link the issue, describe what changed, list which tests cover the change, note any invariant impact.

## Coding conventions

- **Python**: type hints on all new public functions; `from __future__ import annotations` at the top of new modules; keep imports sorted; no `print` in primitive code (use `logging` with `log = logging.getLogger(__name__)`).
- **No comments that say what code says.** Add a comment only when the *why* is non-obvious — a hidden constraint, a workaround, an invariant. If removing the comment wouldn't confuse a future reader, don't write it.
- **No backwards-compatibility shims** unless explicitly requested. Delete the old code; the test suite is the rollback plan.
- **No emojis in code or comments** unless the file already uses them for damage-signal classification (`orbit/src/components/DamageSignalFeed.tsx`).
- **License headers are not required on new files.** The Apache-2.0 license applies to the whole repo via the top-level `LICENSE` + `NOTICE`. Stale BSL or MIT per-file headers were removed in 2026-05-08.

## Security

Vulnerability reports go to the email in `MAINTAINERS` (when published) — not as public issues. Until that file lands, file an issue with title `SECURITY: <one-line>` and the maintainer will rotate it through a private channel.

## Scope

- The kernel scope is **single-principal governance** (T1). PRs that add multi-principal RBAC, SSO, or signed audit need a paired adopter-signal issue showing concrete demand.
- The kernel scope does **not** include implementing model inference, building an agent runtime, or chat UIs. Those layers live elsewhere; cognitive-firm orchestrates them.
- Tenant-specific content (mandates, real role authorities, principal preferences) does not belong in this repo — see `tenants/README.md` for the overlay pattern.

## License agreement

By submitting a contribution you agree:

1. The contribution is your original work, or you have the right to submit it under Apache-2.0.
2. Your contribution is licensed to the project under Apache-2.0 (see `LICENSE`).
3. You preserve the copyright notice in derivative works.

There is no separate CLA. The Apache-2.0 license itself is the agreement.

## Questions

Open an issue with the `question` label, or read `docs/PROTOCOLS.md` first — most architectural questions have already been answered there.
