from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.run_checkpoints import get_run  # noqa: E402
from cognitive_firm.orchestration.human_work import list_human_work_sessions  # noqa: E402
from cognitive_firm.orchestration.runtime_adapters import (  # noqa: E402
    RuntimeEvent,
    record_runtime_event,
    runtime_idempotency_key,
)


def test_runtime_adapter_records_external_run_lifecycle(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"

    start = record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-1",
            kind="started",
            owner_role="role.manager",
            actor="role.manager",
            objective="run graph under governance",
            project_id="demo",
        ),
        log_path=log,
    )

    assert start["idempotency_key"] == runtime_idempotency_key("langgraph", "thread-1")

    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-1",
            kind="checkpointed",
            owner_role="role.manager",
            actor="role.manager",
            step_id="retrieve",
            checkpoint_status="completed",
            summary="retrieved source packet",
            side_effect_key="fetch:source:1",
        ),
        log_path=log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-1",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=log,
    )

    projection = get_run(start["cognitive_run_id"], log_path=log)
    assert projection.idempotency_key == "runtime:langgraph:thread-1"
    assert projection.project_id == "demo"
    assert projection.state == "completed"
    assert projection.checkpoints[0]["step_id"] == "retrieve"


def test_runtime_adapter_idempotent_started_event(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    event = RuntimeEvent(
        runtime_name="openai_agents_sdk",
        external_run_id="run-1",
        kind="started",
        owner_role="role.engineer",
        actor="role.engineer",
        objective="execute coding task",
    )

    first = record_runtime_event(event, log_path=log)
    second = record_runtime_event(event, log_path=log)

    assert second["cognitive_run_id"] == first["cognitive_run_id"]


def test_runtime_adapter_started_event_is_idempotent_after_terminal_state(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    event = RuntimeEvent(
        runtime_name="langgraph",
        external_run_id="terminal-thread",
        kind="started",
        owner_role="role.engineer",
        actor="role.engineer",
        objective="execute once",
    )

    first = record_runtime_event(event, log_path=log)
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="terminal-thread",
            kind="state_changed",
            owner_role="role.engineer",
            actor="role.engineer",
            state="completed",
        ),
        log_path=log,
    )
    replayed = record_runtime_event(event, log_path=log)

    assert replayed["cognitive_run_id"] == first["cognitive_run_id"]


def test_runtime_adapter_rejects_checkpoint_before_start(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"

    try:
        record_runtime_event(
            RuntimeEvent(
                runtime_name="crewai",
                external_run_id="crew-1",
                kind="checkpointed",
                owner_role="role.manager",
                actor="role.manager",
                step_id="plan",
                checkpoint_status="completed",
                summary="planned",
            ),
            log_path=log,
        )
    except KeyError as exc:
        assert "external runtime run not registered" in str(exc)
    else:
        raise AssertionError("expected missing runtime run rejection")


def test_runtime_adapter_interrupt_creates_human_work_and_pauses_run(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    human_work_log = tmp_path / "human_work.jsonl"
    start = record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-hitl",
            kind="started",
            owner_role="role.manager",
            actor="role.manager",
            objective="needs human check",
        ),
        log_path=log,
    )

    from cognitive_firm.orchestration.runtime_adapters import bridge_runtime_interrupt_to_human_work

    result = bridge_runtime_interrupt_to_human_work(
        runtime_name="langgraph",
        external_run_id="thread-hitl",
        actor="role.manager",
        interrupt_id="approval-1",
        interrupt_summary="Approve external write before resume",
        human_actor="human.principal",
        human_deliverable="approval note or rejection rationale",
        resume_ref="langgraph://thread-hitl/resume/approval-1",
        log_path=log,
        human_work_log_path=human_work_log,
    )

    projection = get_run(start["cognitive_run_id"], log_path=log)
    sessions = list_human_work_sessions(log_path=human_work_log)
    assert projection.state == "paused"
    assert result["human_work_session_id"] == sessions[0].session_id
    assert sessions[0].metadata["resume_ref"] == "langgraph://thread-hitl/resume/approval-1"


def test_runtime_adapter_interrupted_event_replay_is_idempotent(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    human_work_log = tmp_path / "human_work.jsonl"
    event = RuntimeEvent(
        runtime_name="langgraph",
        external_run_id="thread-replay",
        kind="interrupted",
        owner_role="role.manager",
        actor="role.manager",
        interrupt_id="approval-1",
        interrupt_summary="Approve external write before resume",
        human_actor="human.principal",
        human_deliverable="approval note or rejection rationale",
        resume_ref="langgraph://thread-replay/resume/approval-1",
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-replay",
            kind="started",
            owner_role="role.manager",
            actor="role.manager",
            objective="needs human check",
        ),
        log_path=log,
    )

    first = record_runtime_event(event, log_path=log, human_work_log_path=human_work_log)
    second = record_runtime_event(event, log_path=log, human_work_log_path=human_work_log)
    sessions = list_human_work_sessions(log_path=human_work_log)

    assert first["human_work_session_id"] == second["human_work_session_id"]
    assert len(sessions) == 1
