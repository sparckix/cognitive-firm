# Worker Taxonomy

**Status:** design vocabulary shipped as code.
**Module:** `cognitive_firm.orchestration.worker_taxonomy`
**Tests:** `tests/test_worker_taxonomy.py`

The worker taxonomy separates worker structure from worker sourcing.

## Axes

| Axis | Values | Meaning |
|---|---|---|
| Capability model | `deterministic_system`, `bare_llm`, `tool_using_agent`, `human` | What the worker can do. Capability does not decide identity or state. |
| Fungibility model | `fungible`, `singular` | Whether the worker can be swapped without changing the governance meaning of the work. |
| State model | `stateless`, `stateful` | Whether the worker should rely on private continuity across tasks. |
| State location | `external_artifacts`, `session_and_artifacts`, `human_context_and_artifacts` | Where continuity is supposed to live. |
| Transport | `api`, `subscription_cli`, `local_process`, `human`, `external_service`, `unspecified` | How the worker is reached or sourced. Transport is orthogonal to worker structure. |

Transport affects cost, quota, latency, and capability. It does not decide
whether a worker is stateless, stateful, fungible, or singular.

## Archetypes

| Archetype | Worker class | Capability | Fungibility | State | Use when |
|---|---|---|---|---|
| `deterministic_gate` | `deterministic` | deterministic system | fungible | stateless | The check should be reproducible and independent of worker identity. |
| `fungible_llm_call` | `llm` | bare LLM | fungible | stateless | Context is fully externalized into the prompt, artifacts, and run state. |
| `fungible_agent_worker` | `agent` | tool-using agent | fungible | stateless | Tool/code execution is needed, but identity continuity is not part of the value. |
| `singular_agent_role` | `agent` | tool-using agent | singular | stateful | Continuity is valuable enough to justify a named role/session. |
| `independent_reviewer` | `governance` | tool-using agent | singular | stateful | Review identity should remain distinct from production identity during a review window. |
| `human_operator` | `operator` | human | singular | stateful | Human judgment, authority, taste, relationship work, or residual-risk ownership is required. |

## Design Rule

Use fungible workers for parallel, bounded, externally specified work. Use
singular identity for management, review, and continuity-heavy work. A worker
can be a tool-using agent and still be fungible if all relevant context is in
external artifacts.

The firm's durable asset is not the model call or CLI session. It is the
externalized state: role mandates, artifacts, receipts, run projections,
attestations, accountability records, and approved learning events.

## Separation Rule

For production/review splits, do not let one persistent identity act as both
the worker and the independent reviewer. Use different roles or a fungible
worker family for production work and a separate governance actor for review.

## Operating Units

Operating units still enforce `worker_roles`; `worker_role_classes` and
`worker_role_archetypes` are explanatory. The class label gives a coarse
worker category. The archetype records the fuller capability/fungibility/state
shape. Authorization remains role- and actor-based.
