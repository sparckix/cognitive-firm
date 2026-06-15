# Examples

Examples are runnable proof paths and inspection guides. They should compose
existing kernel primitives rather than introduce private tenant policy or a
second system of record.

## Start Here

| If you want to see... | Run/read | Notes |
|---|---|---|
| The shortest governed action path | [`end-to-end-governance-walkthrough.md`](end-to-end-governance-walkthrough.md) | Good first read after `make first-gated-action`. |
| What an agent fleet did under authority | [`agent-fleet-audit-demo.md`](agent-fleet-audit-demo.md) | No external calls; records invocation receipts and bundle evidence. |
| A runtime pause for human work | [`langgraph-runtime-adapter.md`](langgraph-runtime-adapter.md) | Framework-neutral demo of interrupt, A2H, receipt, and resume evidence. |
| How bad states are caught | [`governance-failure-benchmark.md`](governance-failure-benchmark.md) | Deterministic fault fixture, not a model benchmark. |
| Learning from measured actions | [`decision-log-replay-demo.md`](decision-log-replay-demo.md) and [`field-pilot-action-impact-demo.md`](field-pilot-action-impact-demo.md) | Shows candidate policy review packets, not automatic policy mutation. |
| Self-organizing agents under governance | [`self-evolving-org-demo.md`](self-evolving-org-demo.md) | Uses the kernel paths for A2A, decision aggregation, proposals, learning, proofs, and generated reports. |

## Cost Profile

No-cost deterministic examples are suitable for public smoke and release
candidate checks. Live-agent or API examples are opt-in and should write only
to gitignored run directories such as `.cognitive-firm-runs/`.

| Cost class | Examples |
|---|---|
| No-cost / deterministic | Governance walkthrough, governance failure benchmark, decision-log replay, field-pilot action-impact, formal-provider bundle, agent-fleet audit, self-evolving org fixture. |
| Local service or app boundary | App-service integration, A2H workflow, LangGraph-style runtime adapter. |
| Live optional | Self-evolving org with subscription/local agents or API model calls. |

## Governance-Carrier Demos

Some runnable demos are documented primarily by their protocol page because the
important artifact is a kernel evidence carrier, not a standalone scenario.

| Make target | Protocol |
|---|---|
| `make multi-agent-trace-attribution-demo` | [`multi-agent-trace-attribution.md`](../protocols/multi-agent-trace-attribution.md) |
| `make phase-execution-demo` | [`phase-execution.md`](../protocols/phase-execution.md) |
| `make protocol-experiment-demo` | [`protocol-experiments.md`](../protocols/protocol-experiments.md) |
| `make capability-signal-demo` | [`capability-signals.md`](../protocols/capability-signals.md) |

## Boundary Rule

An example may create concrete fictional workload, receipts, packets, or
reports. It should not put tenant strategy, credentials, private mandates, or
operator-only answer keys into the public kernel or into generated
firm-visible state.

<!-- AUTO-INDEX:START (managed by scripts/gen_folder_index.py — edit prose OUTSIDE this block) -->

## Index

**Sub-folders**

- None

**Documents**

- [a2h-workflow-demo.md](a2h-workflow-demo.md)
- [accountability-speed-envelope-examples.md](accountability-speed-envelope-examples.md)
- [action-intelligence-source-health.md](action-intelligence-source-health.md)
- [agent-fleet-audit-demo.md](agent-fleet-audit-demo.md)
- [app-service-integration-example.md](app-service-integration-example.md)
- [decision-log-replay-demo.md](decision-log-replay-demo.md)
- [end-to-end-governance-walkthrough.md](end-to-end-governance-walkthrough.md)
- [field-pilot-action-impact-demo.md](field-pilot-action-impact-demo.md)
- [field-validation-pilot-example.md](field-validation-pilot-example.md)
- [formal-provider-bundle-demo.md](formal-provider-bundle-demo.md)
- [governance-failure-benchmark.md](governance-failure-benchmark.md)
- [langgraph-runtime-adapter.md](langgraph-runtime-adapter.md)
- [learning-event-replay.md](learning-event-replay.md)
- [learning-loop-demo.md](learning-loop-demo.md)
- [self-evolving-org-demo.md](self-evolving-org-demo.md)
- [source-coverage-walkthrough.md](source-coverage-walkthrough.md)

<sub>0 sub-folder(s), 16 document(s). Auto-generated; re-run `scripts/gen_folder_index.py` after adding files.</sub>

<!-- AUTO-INDEX:END -->
