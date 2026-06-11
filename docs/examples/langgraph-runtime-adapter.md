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

The package installs `adapters/langgraph-runtime-adapter.yaml` and
`adapter_conformance/langgraph-runtime-adapter.json`. It does not install
LangGraph or executable adapter code.

The demo uses the same event vocabulary an external graph runtime would emit:
`started`, `checkpointed`, `interrupted`, and `state_changed`. It does not
require LangGraph as a dependency. It also records the human-review receipt,
an outcome verdict, an accountability closure, and a governed-run attestation
bundle whose final verdict is `passed`. By default it prints a compact summary;
run the script with `--full-json` to inspect every row in the bundle.

```python
from cognitive_firm.orchestration.runtime_adapters import RuntimeEvent, record_runtime_event


def before_graph_run(thread_id: str) -> None:
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id=thread_id,
            kind="started",
            owner_role="role.research_director",
            actor="role.research_director",
            objective="run project-scoped evidence graph",
            project_id="example",
        )
    )


def after_node(thread_id: str, node_name: str, summary: str) -> None:
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id=thread_id,
            kind="checkpointed",
            owner_role="role.research_director",
            actor="role.research_director",
            step_id=f"node.{node_name}",
            checkpoint_status="completed",
            summary=summary,
        )
    )


def after_graph_run(thread_id: str, ok: bool, failure_reason: str | None = None) -> None:
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id=thread_id,
            kind="state_changed",
            owner_role="role.research_director",
            actor="role.research_director",
            state="completed" if ok else "failed",
            failure_reason=failure_reason,
        )
    )
```

For human-in-the-loop pauses, map the runtime interrupt into an A2H work
session while preserving the runtime's opaque resume reference:

```python
def on_interrupt(thread_id: str, interrupt_id: str, resume_ref: str) -> None:
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id=thread_id,
            kind="interrupted",
            owner_role="role.research_director",
            actor="role.research_director",
            interrupt_id=interrupt_id,
            interrupt_summary="Review the graph output before resume",
            human_actor="human.reviewer",
            human_deliverable="approval note or rejection rationale",
            resume_ref=resume_ref,
        )
    )
```

Use this pattern for any external framework with lifecycle hooks. Keep the
adapter thin: translate runtime callbacks to `RuntimeEvent`; do not move tenant
policy or framework state machines into the kernel.

For a no-cost end-to-end path that does not involve any external runtime, run:

```bash
make native-e2e-demo
```

That demo uses a fictional Kettle & Compass product-claim workflow to exercise
the native kernel primitives directly: actor identity, actor membership,
operating unit, work item, run checkpoints, human work, action attestation,
outcome link, accountability case, and governed-run attestation summary.
