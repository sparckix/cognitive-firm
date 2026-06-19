"""Framework-runtime adapter boundary.

The first-party daemon executes governed role-office work. External agent
frameworks may own framework-native execution semantics. cognitive-firm owns
the organizational runtime view. This module accepts framework-neutral runtime
events and records them through run_checkpoints, which in turn writes to the
canonical transition log.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.orchestration.run_checkpoints import (
    CheckpointStatus,
    RunProjection,
    RunState,
    append_checkpoint,
    get_run,
    set_run_state,
    start_run,
)
from cognitive_firm.orchestration.human_work import (
    HumanWorkSession,
    create_agent_requested_human_work_session,
    list_human_work_sessions,
)


RuntimeEventKind = Literal["started", "checkpointed", "state_changed", "interrupted"]
COGNITIVE_FIRM_DAEMON_RUNTIME = "cognitive_firm_daemon"


@dataclass(frozen=True)
class RuntimeRunRef:
    """Stable mapping from external runtime identity to cognitive-firm run."""

    runtime_name: str
    external_run_id: str
    cognitive_run_id: str

    @property
    def idempotency_key(self) -> str:
        return runtime_idempotency_key(self.runtime_name, self.external_run_id)


@dataclass(frozen=True)
class RuntimeEvent:
    """Framework-neutral event emitted by a graph, crew, chat, or agent runtime."""

    runtime_name: str
    external_run_id: str
    kind: RuntimeEventKind
    owner_role: str
    actor: str
    objective: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    step_id: str | None = None
    checkpoint_status: CheckpointStatus | str | None = None
    summary: str | None = None
    payload_ref: str | None = None
    side_effect_key: str | None = None
    state: RunState | str | None = None
    failure_reason: str | None = None
    interrupt_id: str | None = None
    interrupt_summary: str | None = None
    human_actor: str | None = None
    human_deliverable: str | None = None
    resume_ref: str | None = None
    work_mode: str = "judgment"
    bottleneck_class: str = "authority"


def runtime_idempotency_key(runtime_name: str, external_run_id: str) -> str:
    """Return the canonical idempotency key for an external runtime run."""
    if not runtime_name.strip():
        raise ValueError("runtime_name is required")
    if not external_run_id.strip():
        raise ValueError("external_run_id is required")
    return f"runtime:{runtime_name.strip()}:{external_run_id.strip()}"


def start_runtime_run(
    *,
    runtime_name: str,
    external_run_id: str,
    owner_role: str,
    objective: str,
    actor: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> RuntimeRunRef:
    """Create or retrieve the cognitive-firm run for an external runtime run."""
    try:
        projection = _projection_for_external_run(runtime_name, external_run_id, log_path=log_path)
    except KeyError:
        projection = None
    if projection is not None:
        return RuntimeRunRef(
            runtime_name=runtime_name,
            external_run_id=external_run_id,
            cognitive_run_id=projection.run_id,
        )
    projection = start_run(
        owner_role=owner_role,
        objective=objective,
        tenant_id=tenant_id,
        project_id=project_id,
        idempotency_key=runtime_idempotency_key(runtime_name, external_run_id),
        log_path=log_path,
    )
    return RuntimeRunRef(
        runtime_name=runtime_name,
        external_run_id=external_run_id,
        cognitive_run_id=projection.run_id,
    )


def _projection_for_external_run(
    runtime_name: str,
    external_run_id: str,
    *,
    log_path: Path | None = None,
) -> RunProjection:
    key = runtime_idempotency_key(runtime_name, external_run_id)
    matching = [
        projection for projection in _list_runs(log_path=log_path)
        if projection.idempotency_key == key
    ]
    for projection in reversed(matching):
        if projection.state in {"running", "paused"}:
            return projection
    for projection in reversed(matching):
        if projection.idempotency_key == key:
            return projection
    raise KeyError(f"external runtime run not registered: {key}")


def _list_runs(*, log_path: Path | None = None) -> list[RunProjection]:
    from cognitive_firm.orchestration.run_checkpoints import list_runs

    return list_runs(log_path=log_path)


def record_runtime_checkpoint(
    *,
    runtime_name: str,
    external_run_id: str,
    actor: str,
    step_id: str,
    status: CheckpointStatus | str,
    summary: str,
    payload_ref: str | None = None,
    side_effect_key: str | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Record one external runtime step as a cognitive-firm checkpoint."""
    projection = _projection_for_external_run(
        runtime_name,
        external_run_id,
        log_path=log_path,
    )
    return append_checkpoint(
        projection.run_id,
        actor=actor,
        step_id=step_id,
        status=status,
        summary=summary,
        payload_ref=payload_ref,
        side_effect_key=side_effect_key,
        log_path=log_path,
    )


def set_runtime_run_state(
    *,
    runtime_name: str,
    external_run_id: str,
    actor: str,
    state: RunState | str,
    failure_reason: str | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Record the projected state of an external runtime run."""
    projection = _projection_for_external_run(
        runtime_name,
        external_run_id,
        log_path=log_path,
    )
    return set_run_state(
        projection.run_id,
        actor=actor,
        state=state,
        failure_reason=failure_reason,
        log_path=log_path,
    )


def bridge_runtime_interrupt_to_human_work(
    *,
    runtime_name: str,
    external_run_id: str,
    actor: str,
    interrupt_id: str,
    interrupt_summary: str,
    human_actor: str,
    human_deliverable: str,
    resume_ref: str,
    work_mode: str = "judgment",
    bottleneck_class: str = "authority",
    log_path: Path | None = None,
    human_work_log_path: Path | None = None,
) -> dict[str, Any]:
    """Pause a runtime projection and create a bounded human-work request.

    The external runtime owns the resume token and execution state. The kernel
    owns the organizational record: who is waiting on whom and what evidence is
    needed before the runtime resumes.
    """
    projection = _projection_for_external_run(runtime_name, external_run_id, log_path=log_path)
    session_id = _interrupt_session_id(runtime_name, external_run_id, interrupt_id)
    existing = _find_interrupt_session(session_id, log_path=human_work_log_path)
    if existing is None:
        session: HumanWorkSession = create_agent_requested_human_work_session(
            requested_by_role=projection.owner_role,
            human_actor=human_actor,
            objective=interrupt_summary,
            work_mode=work_mode,
            bottleneck_class=bottleneck_class,
            human_deliverable=human_deliverable,
            tenant_id=projection.tenant_id,
            project_id=projection.project_id,
            collaborating_roles=[projection.owner_role],
            artifact_refs=[resume_ref],
            receipt_required=True,
            receipt_type="note",
            agent_followup_ref=resume_ref,
            session_id=session_id,
            metadata={
                "runtime_name": runtime_name,
                "external_run_id": external_run_id,
                "cognitive_run_id": projection.run_id,
                "interrupt_id": interrupt_id,
                "resume_ref": resume_ref,
            },
            log_path=human_work_log_path,
        )
    else:
        session = existing
    set_run_state(
        projection.run_id,
        actor=actor,
        state="paused",
        failure_reason=f"runtime interrupt: {interrupt_id}",
        log_path=log_path,
    )
    append_checkpoint(
        projection.run_id,
        actor=actor,
        step_id=f"interrupt:{interrupt_id}",
        status="started",
        summary=interrupt_summary,
        payload_ref=resume_ref,
        side_effect_key=f"runtime_interrupt:{runtime_name}:{external_run_id}:{interrupt_id}",
        log_path=log_path,
    )
    return {
        "runtime_name": runtime_name,
        "external_run_id": external_run_id,
        "cognitive_run_id": projection.run_id,
        "state": "paused",
        "human_work_session_id": session.session_id,
        "resume_ref": resume_ref,
    }


def record_runtime_event(
    event: RuntimeEvent,
    *,
    log_path: Path | None = None,
    human_work_log_path: Path | None = None,
) -> dict[str, Any]:
    """Record a framework-neutral runtime event.

    This is the single adapter entry point external frameworks should target.
    """
    if event.kind == "started":
        if not event.objective:
            raise ValueError("objective is required for started events")
        ref = start_runtime_run(
            runtime_name=event.runtime_name,
            external_run_id=event.external_run_id,
            owner_role=event.owner_role,
            objective=event.objective,
            actor=event.actor,
            tenant_id=event.tenant_id,
            project_id=event.project_id,
            log_path=log_path,
        )
        return {
            "runtime_name": ref.runtime_name,
            "external_run_id": ref.external_run_id,
            "cognitive_run_id": ref.cognitive_run_id,
            "idempotency_key": ref.idempotency_key,
        }
    if event.kind == "checkpointed":
        if not event.step_id or not event.checkpoint_status or not event.summary:
            raise ValueError("step_id, checkpoint_status, and summary are required for checkpointed events")
        return record_runtime_checkpoint(
            runtime_name=event.runtime_name,
            external_run_id=event.external_run_id,
            actor=event.actor,
            step_id=event.step_id,
            status=event.checkpoint_status,
            summary=event.summary,
            payload_ref=event.payload_ref,
            side_effect_key=event.side_effect_key,
            log_path=log_path,
        )
    if event.kind == "state_changed":
        if not event.state:
            raise ValueError("state is required for state_changed events")
        return set_runtime_run_state(
            runtime_name=event.runtime_name,
            external_run_id=event.external_run_id,
            actor=event.actor,
            state=event.state,
            failure_reason=event.failure_reason,
            log_path=log_path,
        )
    if event.kind == "interrupted":
        missing = [
            label
            for label, value in {
                "interrupt_id": event.interrupt_id,
                "interrupt_summary": event.interrupt_summary,
                "human_actor": event.human_actor,
                "human_deliverable": event.human_deliverable,
                "resume_ref": event.resume_ref,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"{', '.join(missing)} required for interrupted events")
        return bridge_runtime_interrupt_to_human_work(
            runtime_name=event.runtime_name,
            external_run_id=event.external_run_id,
            actor=event.actor,
            interrupt_id=event.interrupt_id or "",
            interrupt_summary=event.interrupt_summary or "",
            human_actor=event.human_actor or "",
            human_deliverable=event.human_deliverable or "",
            resume_ref=event.resume_ref or "",
            work_mode=event.work_mode,
            bottleneck_class=event.bottleneck_class,
            log_path=log_path,
            human_work_log_path=human_work_log_path,
        )
    raise ValueError(f"unsupported runtime event kind: {event.kind}")


def _interrupt_session_id(runtime_name: str, external_run_id: str, interrupt_id: str) -> str:
    digest = hashlib.sha256(
        f"{runtime_name}:{external_run_id}:{interrupt_id}".encode("utf-8")
    ).hexdigest()[:16]
    return f"hws_interrupt_{digest}"


def _find_interrupt_session(
    session_id: str,
    *,
    log_path: Path | None = None,
) -> HumanWorkSession | None:
    for session in list_human_work_sessions(log_path=log_path):
        if session.session_id == session_id:
            return session
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record external runtime events into cognitive-firm.")
    parser.add_argument("--log-path", type=Path)
    parser.add_argument(
        "--human-work-log-path",
        type=Path,
        help="Write human-work sessions created by interrupted events to this JSONL log.",
    )
    parser.add_argument("--event-json", required=True, help="JSON object matching RuntimeEvent fields")
    args = parser.parse_args(argv)

    payload = json.loads(args.event_json)
    event = RuntimeEvent(**payload)
    print(
        json.dumps(
            record_runtime_event(
                event,
                log_path=args.log_path,
                human_work_log_path=args.human_work_log_path,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
