from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.run_checkpoints import (  # noqa: E402
    append_checkpoint,
    get_run,
    resume_summary,
    set_run_state,
    start_run,
)


def test_run_checkpoint_projection_replays_transition_log(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    start = start_run(
        owner_role="role.manager",
        objective="sync external state",
        idempotency_key="sync:demo",
        log_path=log,
    )
    run_id = start.run_id

    append_checkpoint(
        run_id,
        actor="role.manager",
        step_id="fetch",
        status="completed",
        summary="fetched state",
        side_effect_key="fetch:demo",
        log_path=log,
    )

    projection = get_run(run_id, log_path=log)
    assert projection.objective == "sync external state"
    assert projection.checkpoints[0]["step_id"] == "fetch"
    assert projection.side_effect_keys == ["fetch:demo"]
    assert resume_summary(run_id, log_path=log)["completed_step_ids"] == ["fetch"]


def test_active_idempotency_key_returns_existing_run(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    first = start_run(
        owner_role="role.manager",
        objective="first",
        idempotency_key="same",
        log_path=log,
    )
    second = start_run(
        owner_role="role.manager",
        objective="second",
        idempotency_key="same",
        log_path=log,
    )

    assert second.run_id == first.run_id


def test_terminal_idempotency_key_can_start_new_run(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    first = start_run(
        owner_role="role.manager",
        objective="first",
        idempotency_key="same",
        log_path=log,
    )
    set_run_state(first.run_id, actor="role.manager", state="completed", log_path=log)

    second = start_run(
        owner_role="role.manager",
        objective="second",
        idempotency_key="same",
        log_path=log,
    )

    assert second.run_id != first.run_id
    assert second.objective == "second"


def test_repeated_side_effect_key_skips_checkpoint(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    start = start_run(owner_role="role.manager", objective="notify", log_path=log)
    run_id = start.run_id

    append_checkpoint(
        run_id,
        actor="role.manager",
        step_id="send",
        status="completed",
        summary="sent",
        side_effect_key="email:1",
        log_path=log,
    )
    append_checkpoint(
        run_id,
        actor="role.manager",
        step_id="send_retry",
        status="completed",
        summary="retry",
        side_effect_key="email:1",
        log_path=log,
    )

    projection = get_run(run_id, log_path=log)
    assert projection.side_effect_keys == ["email:1"]
    assert projection.checkpoints[-1]["status"] == "skipped"


def test_terminal_run_rejects_checkpoint(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    start = start_run(owner_role="role.manager", objective="closed", log_path=log)
    run_id = start.run_id
    set_run_state(run_id, actor="role.manager", state="completed", log_path=log)

    try:
        append_checkpoint(
            run_id,
            actor="role.manager",
            step_id="late",
            status="completed",
            summary="too late",
            log_path=log,
        )
    except ValueError as exc:
        assert "terminal run" in str(exc)
    else:
        raise AssertionError("expected terminal run checkpoint rejection")
