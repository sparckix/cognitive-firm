"""Transition-log-backed checkpoints for long-running role-office work.

This module records resumable work as canonical transition events and derives
current run state by replay. It deliberately does not create a second source of
truth: the transition log is the local adapter for the event/outbox substrate.
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.orchestration.transition_log import TRANSITIONS_LOG, append_transition


RunState = Literal["running", "paused", "completed", "failed", "cancelled"]
CheckpointStatus = Literal["started", "completed", "failed", "skipped"]
ACTIVE_STATES = {"running", "paused"}
TERMINAL_STATES = {"completed", "failed", "cancelled"}
VALID_STATES = ACTIVE_STATES | TERMINAL_STATES
VALID_CHECKPOINT_STATUSES = {"started", "completed", "failed", "skipped"}

RUN_STARTED = "run.started"
RUN_CHECKPOINTED = "run.checkpointed"
RUN_STATE_CHANGED = "run.state_changed"


@dataclass(frozen=True)
class RunProjection:
    run_id: str
    owner_role: str
    objective: str
    state: str = "running"
    tenant_id: str | None = None
    project_id: str | None = None
    idempotency_key: str | None = None
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    side_effect_keys: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    latest_event_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "owner_role": self.owner_role,
            "objective": self.objective,
            "state": self.state,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "idempotency_key": self.idempotency_key,
            "checkpoints": self.checkpoints,
            "side_effect_keys": self.side_effect_keys,
            "failure_reason": self.failure_reason,
            "latest_event_id": self.latest_event_id,
        }


def _validate(value: str, allowed: set[str], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"invalid {label} {value!r}; expected one of {sorted(allowed)}")
    return value


def _read_transitions(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _project(rows: list[dict[str, Any]]) -> dict[str, RunProjection]:
    runs: dict[str, RunProjection] = {}
    for row in rows:
        event = row.get("event")
        payload = row.get("payload") or {}
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            continue
        if event == RUN_STARTED:
            runs[run_id] = RunProjection(
                run_id=run_id,
                owner_role=str(payload.get("owner_role") or row.get("role_id") or ""),
                objective=str(payload.get("objective") or ""),
                state="running",
                tenant_id=payload.get("tenant_id"),
                project_id=payload.get("project_id"),
                idempotency_key=payload.get("idempotency_key"),
                latest_event_id=row.get("event_id"),
            )
            continue
        if run_id not in runs:
            continue
        current = runs[run_id]
        if event == RUN_CHECKPOINTED:
            checkpoint = {
                "step_id": payload.get("step_id"),
                "status": payload.get("status"),
                "summary": payload.get("summary"),
                "payload_ref": payload.get("payload_ref"),
                "side_effect_key": payload.get("side_effect_key"),
                "event_id": row.get("event_id"),
                "ts": row.get("ts"),
            }
            checkpoints = [item for item in current.checkpoints if item.get("step_id") != payload.get("step_id")]
            checkpoints.append(checkpoint)
            side_effect_keys = list(current.side_effect_keys)
            side_effect_key = payload.get("side_effect_key")
            if side_effect_key and side_effect_key not in side_effect_keys and payload.get("status") != "skipped":
                side_effect_keys.append(str(side_effect_key))
            runs[run_id] = RunProjection(
                **{
                    **current.as_dict(),
                    "checkpoints": checkpoints,
                    "side_effect_keys": side_effect_keys,
                    "latest_event_id": row.get("event_id"),
                }
            )
        elif event == RUN_STATE_CHANGED:
            runs[run_id] = RunProjection(
                **{
                    **current.as_dict(),
                    "state": str(payload.get("state") or current.state),
                    "failure_reason": payload.get("failure_reason"),
                    "latest_event_id": row.get("event_id"),
                }
            )
    return runs


def list_runs(*, log_path: Path | None = None) -> list[RunProjection]:
    return list(_project(_read_transitions(log_path or TRANSITIONS_LOG)).values())


def get_run(run_id: str, *, log_path: Path | None = None) -> RunProjection:
    runs = _project(_read_transitions(log_path or TRANSITIONS_LOG))
    if run_id not in runs:
        raise KeyError(f"run not found: {run_id}")
    return runs[run_id]


def start_run(
    *,
    owner_role: str,
    objective: str,
    tenant_id: str | None = None,
    project_id: str | None = None,
    idempotency_key: str | None = None,
    run_id: str | None = None,
    log_path: Path | None = None,
) -> RunProjection:
    if not owner_role.strip():
        raise ValueError("owner_role is required")
    if not objective.strip():
        raise ValueError("objective is required")
    if idempotency_key:
        for existing in list_runs(log_path=log_path):
            if existing.idempotency_key == idempotency_key and existing.state in ACTIVE_STATES:
                return existing
    run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
    append_transition(
        event=RUN_STARTED,
        actor=owner_role,
        role_id=owner_role,
        surface="run_checkpoints",
        subject=run_id,
        payload={
            "run_id": run_id,
            "owner_role": owner_role,
            "objective": objective,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "idempotency_key": idempotency_key,
        },
        causality_id=idempotency_key,
        log_path=log_path,
    )
    return get_run(run_id, log_path=log_path)


def append_checkpoint(
    run_id: str,
    *,
    actor: str,
    step_id: str,
    status: CheckpointStatus | str,
    summary: str,
    payload_ref: str | None = None,
    side_effect_key: str | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    status = _validate(str(status), VALID_CHECKPOINT_STATUSES, "checkpoint status")
    projection = get_run(run_id, log_path=log_path)
    if projection.state in TERMINAL_STATES:
        raise ValueError(f"cannot checkpoint terminal run {run_id} in state {projection.state}")
    effective_status = status
    if side_effect_key and side_effect_key in projection.side_effect_keys:
        effective_status = "skipped"
    return append_transition(
        event=RUN_CHECKPOINTED,
        actor=actor,
        role_id=projection.owner_role,
        surface="run_checkpoints",
        subject=run_id,
        payload={
            "run_id": run_id,
            "step_id": step_id,
            "status": effective_status,
            "summary": summary,
            "payload_ref": payload_ref,
            "side_effect_key": side_effect_key,
        },
        causality_id=projection.latest_event_id,
        log_path=log_path,
    )


def set_run_state(
    run_id: str,
    *,
    actor: str,
    state: RunState | str,
    failure_reason: str | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    state = _validate(str(state), VALID_STATES, "state")
    projection = get_run(run_id, log_path=log_path)
    return append_transition(
        event=RUN_STATE_CHANGED,
        actor=actor,
        role_id=projection.owner_role,
        surface="run_checkpoints",
        subject=run_id,
        payload={"run_id": run_id, "state": state, "failure_reason": failure_reason},
        causality_id=projection.latest_event_id,
        log_path=log_path,
    )


def resume_summary(run_id: str, *, log_path: Path | None = None) -> dict[str, Any]:
    projection = get_run(run_id, log_path=log_path)
    return {
        **projection.as_dict(),
        "completed_step_ids": [
            item.get("step_id") for item in projection.checkpoints if item.get("status") == "completed"
        ],
        "failed_step_ids": [
            item.get("step_id") for item in projection.checkpoints if item.get("status") == "failed"
        ],
        "can_resume": projection.state in ACTIVE_STATES or projection.state == "failed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record and inspect transition-log-backed run checkpoints.")
    parser.add_argument("--log-path", type=Path, default=TRANSITIONS_LOG)
    sub = parser.add_subparsers(dest="cmd", required=True)

    start = sub.add_parser("start")
    start.add_argument("--owner-role", required=True)
    start.add_argument("--objective", required=True)
    start.add_argument("--tenant-id")
    start.add_argument("--project-id")
    start.add_argument("--idempotency-key")

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("run_id")
    checkpoint.add_argument("--actor", required=True)
    checkpoint.add_argument("--step-id", required=True)
    checkpoint.add_argument("--status", required=True, choices=sorted(VALID_CHECKPOINT_STATUSES))
    checkpoint.add_argument("--summary", required=True)
    checkpoint.add_argument("--payload-ref")
    checkpoint.add_argument("--side-effect-key")

    state = sub.add_parser("state")
    state.add_argument("run_id")
    state.add_argument("--actor", required=True)
    state.add_argument("--state", required=True, choices=sorted(VALID_STATES))
    state.add_argument("--failure-reason")

    resume = sub.add_parser("resume")
    resume.add_argument("run_id")

    sub.add_parser("list")
    args = parser.parse_args(argv)

    if args.cmd == "start":
        result = start_run(
            owner_role=args.owner_role,
            objective=args.objective,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            idempotency_key=args.idempotency_key,
            log_path=args.log_path,
        ).as_dict()
    elif args.cmd == "checkpoint":
        result = append_checkpoint(
            args.run_id,
            actor=args.actor,
            step_id=args.step_id,
            status=args.status,
            summary=args.summary,
            payload_ref=args.payload_ref,
            side_effect_key=args.side_effect_key,
            log_path=args.log_path,
        )
    elif args.cmd == "state":
        result = set_run_state(
            args.run_id,
            actor=args.actor,
            state=args.state,
            failure_reason=args.failure_reason,
            log_path=args.log_path,
        )
    elif args.cmd == "resume":
        result = resume_summary(args.run_id, log_path=args.log_path)
    else:
        result = [run.as_dict() for run in list_runs(log_path=args.log_path)]
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
