# LangGraph-Style Runtime Adapter Example

This is a minimal shape for projecting a LangGraph-style run into
cognitive-firm. The graph runtime owns graph execution, checkpoint replay,
streaming, and resume tokens. cognitive-firm owns the organizational
projection: role ownership, checkpoints, evidence, human-work requests, and
review state.

Run the executable demo:

```bash
make langgraph-governance-demo
```

Install the governance-side adapter-policy package onto an existing governed
organization only after previewing its authority impact:

```bash
cognitive-firm-distro preview-overlay langgraph-runtime-adapter \
  --into <org> \
  --json
```

For a no-cost proof against a temporary starter organization:

```bash
make langgraph-adapter-policy-preview
```

That command installs a temporary `starter-firm`, previews the bundled
`langgraph-runtime-adapter` overlay, validates the adapter manifest and
conformance declaration, and reports whether the overlay widens authority. It
does not install LangGraph, execute a graph, apply the overlay, or write a
governance proposal.

The package installs `adapters/langgraph-runtime-adapter.yaml` and
`adapter_conformance/langgraph-runtime-adapter.json`. It does not install
LangGraph or executable adapter code.

The demo uses the kernel service routes an adopter would call from a runtime
adapter: `POST /kernel/runs`, `POST /kernel/runs/{run_id}/checkpoints`,
`POST /kernel/human-work`, `POST /kernel/action-attestations`,
`POST /kernel/outcome-links`, `POST /kernel/accountability-cases`, and
`POST /kernel/governed-run-bundles/build`. It does not require LangGraph as a
dependency. It also records the human-review receipt, an outcome verdict, an
accountability closure, and a governed-run attestation bundle whose final
verdict is `passed`. By default it prints a compact summary; run the script
with `--full-json` to inspect every row in the bundle.

```python
from cognitive_firm.kernel_service import dispatch_kernel_request


def before_graph_run(thread_id: str) -> str:
    response = dispatch_kernel_request(
        "POST",
        "/kernel/runs",
        {
            "owner_role": "role.research_director",
            "objective": "run project-scoped evidence graph",
            "project_id": "example",
            "idempotency_key": f"langgraph:{thread_id}",
        },
    )
    return response.payload["run"]["run_id"]


def after_node(run_id: str, thread_id: str, node_name: str, summary: str) -> None:
    dispatch_kernel_request(
        "POST",
        f"/kernel/runs/{run_id}/checkpoints",
        {
            "actor": "role.research_director",
            "step_id": f"node.{node_name}",
            "status": "completed",
            "summary": summary,
            "side_effect_key": f"langgraph:{thread_id}:{node_name}",
        },
    )


def after_graph_run(run_id: str, ok: bool, failure_reason: str | None = None) -> None:
    dispatch_kernel_request(
        "POST",
        f"/kernel/runs/{run_id}/state",
        {
            "actor": "role.research_director",
            "state": "completed" if ok else "failed",
            "failure_reason": failure_reason,
        },
    )
```

For human-in-the-loop pauses, map the runtime interrupt into an A2H work
session while preserving the runtime's opaque resume reference:

```python
def on_interrupt(run_id: str, thread_id: str, interrupt_id: str, resume_ref: str) -> None:
    dispatch_kernel_request(
        "POST",
        "/kernel/human-work",
        {
            "coordination_pattern": "a2h_work_request",
            "requested_by": "role.research_director",
            "human_actor": "human.reviewer",
            "objective": "Review the graph output before resume",
            "work_mode": "judgment",
            "bottleneck_class": "authority",
            "human_deliverable": "approval note or rejection rationale",
            "agent_followup_ref": resume_ref,
            "metadata": {
                "runtime_name": "langgraph",
                "external_run_id": thread_id,
                "interrupt_id": interrupt_id,
                "cognitive_run_id": run_id,
            },
        },
    )
```

Use this pattern for any external framework with lifecycle hooks. Keep the
adapter thin: translate runtime callbacks to kernel-service route bodies; do
not move tenant policy or framework state machines into the kernel. The lower
level `RuntimeEvent` primitive remains available for in-process fixtures and
primitive tests, but service routes are the adopter-facing boundary.

For a no-cost end-to-end path that does not involve any external runtime, run:

```bash
make native-e2e-demo
```

That demo uses a fictional Kettle & Compass product-claim workflow to exercise
the native kernel primitives directly: actor identity, actor membership,
operating unit, work item, run checkpoints, human work, action attestation,
outcome link, accountability case, and governed-run attestation summary.
