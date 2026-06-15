# Execution Routing

**Module:** `cognitive_firm.orchestration.execution_routing`
**Status:** first-party route-contract helper.
**Tests:** `tests/test_execution_routing.py`, `tests/test_human_work.py`

Execution routing converts work-item frontmatter and body text into a compact
route contract for the first-party daemon or a tenant adapter. It exists because
role-bearing runtimes should not silently decide whether a task is ordinary
work, expert review, a scripted run, artifact construction, a human-work
session, or a repeatable experiment loop.

## Boundary

This helper does:

- honor explicit `execution_route`, `route_hint`, or `recommended_route`
  frontmatter;
- infer a conservative route when no explicit route is supplied;
- set default booleans for loop, artifact, API, and external-compute
  permissions;
- name the first artifact the actor should write before executing;
- render a prompt block that a spawned role runtime can inspect.

It does not:

- grant authority;
- acquire leases;
- spend budget;
- choose a model or provider;
- spawn agents;
- execute graph/runtime logic;
- approve a governance change;
- mutate mandates, roles, charters, policies, or tenant files.

The route is execution evidence and runtime guidance. Mandates, leases, policy
decisions, resource envelopes, and approval paths remain the authority layer.

## Routes

| Route | Use |
|---|---|
| `route_only` | Produce only a routing decision or handoff packet. |
| `direct_work` | Ordinary role-office work with no special loop or spend signal. |
| `expert_review` | External-model, adversarial, or specialist review. |
| `synthesis_review` | Architecture, root-cause, literature, or strategy synthesis before execution. |
| `scripted_run` | One-off script, batch, simulation, GPU, SSH, or external-compute orchestration. |
| `artifact_build` | Reusable artifact, schema, contract, template, or harness construction. |
| `joint_work` | Bounded human work alongside a role office. |
| `experiment_loop` | Repeatable candidate search, protocol experiment, A/B, bandit, or gated loop. |
| `docs_records` | Documentation, paper, ledger, manual, runbook, or record synchronization. |

Compatibility aliases exist for older local names, but new tenant-specific
aliases belong in overlays or work-item frontmatter. The public kernel route
names should stay domain-neutral.

## First Artifact

Each inferred route names a `required_first_artifact`. Examples:

- `workspace/execution_route_decision.md` for `direct_work`;
- `workspace/expert_review_packet.md` for `expert_review`;
- `workspace/run_packet.md` for `scripted_run`;
- `workspace/artifact_build_spec.md` for `artifact_build`;
- `workspace/human_work_session.md` for `joint_work`;
- `workspace/preflight_substrate_audit.md` for `experiment_loop`;
- `workspace/doc_edit_plan.md` for `docs_records`.

The first artifact creates an inspectable pause before the runtime spends,
launches loops, or edits shared state. A tenant may override the path in
frontmatter, but the path should still be a reviewable receipt.

## Relationship To Other Protocols

- [Mandates](mandate.md) decide whether the role has typed authority.
- [Leases](leases.md) and [Policy Decisions](policy-decisions.md) decide
  whether the current actor may perform a mutating or exclusive action.
- [A2H](a2h.md) owns bounded human work once a route becomes `joint_work`.
- [Runtime Adapters](runtime-adapters.md) and
  [Agent Runtime Invocation Policy](agent-runtime-invocation.md) own provider
  execution and lifecycle receipts.
- [Phase Execution](phase-execution.md), [Protocol Experiments](protocol-experiments.md),
  and [Capability Signals](capability-signals.md) can emit evidence that later
  changes routing policy through governance.

## Research Anchor

The helper is intentionally lighter than workflow scheduling. Its design is
closer to organization-theory separation of decision premises from execution:
the organization sets bounded decision rules, while actors execute within
those rules and leave receipts. It also reflects the runtime-boundary lesson
from agent orchestration systems: graph runtimes should own graph execution,
while the organization layer should own authority, routing evidence, and
reviewable state.

The practical literature connection for `experiment_loop` is the same
exploration/exploitation family used by the action-impact interface. See
March's "Exploration and Exploitation in Organizational Learning"
<https://doi.org/10.1287/orsc.2.1.71> and contextual-bandit replay work such
as Li, Chu, Langford, and Wang <https://arxiv.org/abs/1003.5956>. Those works
support the kernel posture here: route experiments deliberately, preserve
evidence, and promote learned routing changes only after review.
