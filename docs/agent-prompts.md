# Agent Prompts

These prompts are for people using their own Codex or Claude session to inspect
or modify this repository. Paste one prompt at a time. Replace bracketed text
with your task.

## 1. Learn The Repo

```text
You are helping me understand the cognitive-firm repository. Read README.md, docs/first-30-minutes.md, docs/PROTOCOLS.md, docs/adopting-cognitive-firm.md, docs/organizational_learning_loop.md, docs/t1_t2_upgrade_matrix.md, org/README.md, src/cognitive_firm/orchestration/README.md, and tests/README.md. Then give me a concise map of the kernel, the app/projection layer, the tenant overlay boundary, and the top five files I should inspect next for [my task].
```

## 2. Check Kernel Boundaries

```text
Inspect the repository as a governance kernel, not as an agent framework. Identify which files are kernel primitives, which files are optional app surfaces, and which files are tenant/config overlays. Flag any place where a proposed change would blur those boundaries. Do not edit files yet.
```

## 3. Run The Clean-Container Smoke

```text
Check whether this repo can be cloned, configured, smoke-tested, and run locally from documented commands. Read Dockerfile, docker-compose.yml, scripts/docker_smoke.sh, deploy/README.md, README.md, and .env.example. Then run the least invasive local smoke tests available and report exact failures before proposing fixes.
```

## 4. Add A Primitive

```text
I want to add [primitive name] to cognitive-firm. First inspect existing primitives in src/cognitive_firm/orchestration/, schemas/, docs/protocols/, and tests/. Propose the smallest kernel-level interface, name what belongs in tenant code instead, then implement only the agreed kernel surface with tests and docs.
```

## 5. Review A Fork Change

```text
Review a change in my cognitive-firm fork. Focus on behavioral regressions, boundary violations between kernel/app/tenant layers, missing tests, stale docs, and deployment breakage. Lead with file/line findings. Do not rewrite the implementation unless I ask.
```

## 6. Human-Agent Work

```text
Inspect the human-agent work support in src/cognitive_firm/orchestration/human_work.py, docs/protocols/h2a.md, orbit/src/server/git-sync.ts, and tests/test_human_work.py. Explain how the repo represents human work as work product rather than only approvals, and identify any gaps for [my use case].
```

## 7. Forecast Or Action Interfaces

```text
Inspect forecast-market and action-impact interfaces in src/cognitive_firm/orchestration/, tests/, README.md, and docs/PROTOCOLS.md. Explain what is deliberately abstract in the kernel, what a tenant implementation must provide, and how an app should consume the read models without owning policy.
```

## 8. Safe Implementation Session

```text
Help me modify my cognitive-firm fork. Before editing, read the nearest README/spec/test files. Preserve existing work. Use the repo's existing patterns. After edits, run focused tests and update any docs whose behavior is now stale.
```

## 9. Multi-Human / SSO Adoption

```text
Help me evaluate cognitive-firm for a small team with more than one human. Read docs/protocols/identity-providers.md, docs/protocols/identity-provisioning.md, docs/protocols/actor-identity.md, docs/protocols/actor-membership.md, docs/protocols/tenant-isolation.md, docs/protocols/kernel-service.md, tests/test_identity_provisioning.py, tests/test_actor_membership.py, and tests/test_kernel_service.py. Explain which parts are first-party kernel authority, which parts should be implemented by my IdP/app/config layer, and the minimal safe setup path.
```
