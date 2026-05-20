# LangGraph Runtime Adapter Example

This is a minimal shape for projecting a LangGraph run into cognitive-firm.
LangGraph owns graph execution and checkpoint replay. cognitive-firm owns the
organizational projection.

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

Use this pattern for any external framework with lifecycle hooks. Keep the
adapter thin: translate runtime callbacks to `RuntimeEvent`; do not move tenant
policy or framework state machines into the kernel.
