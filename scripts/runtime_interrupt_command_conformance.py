#!/usr/bin/env python3
"""Command-path runtime interrupt conformance fixture.

This script exercises the public ``runtime_adapters`` CLI in one hermetic trace:

  external runtime start -> interrupt import -> paused run projection ->
  bounded human-work request -> idempotent interrupt replay.

It proves the adapter seam without executing a graph runtime, resuming a
thread, assigning a human, or owning workflow semantics.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

sys.path.insert(0, str(SRC_ROOT))

from cognitive_firm.orchestration.human_work import list_human_work_sessions  # noqa: E402
from cognitive_firm.orchestration.run_checkpoints import get_run  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-runtime-interrupt-conformance-") as raw:
        root = Path(raw)
        run_log = root / "transitions.jsonl"
        human_work_log = root / "human_work.jsonl"

        checkpoint_before_start = _run_runtime(
            {
                "runtime_name": "langgraph",
                "external_run_id": "thread-interrupt",
                "kind": "checkpointed",
                "owner_role": "role.manager",
                "actor": "role.manager",
                "step_id": "node.before_start",
                "checkpoint_status": "completed",
                "summary": "should not be accepted before started",
            },
            log_path=run_log,
            human_work_log_path=human_work_log,
            check=False,
        )
        if checkpoint_before_start.returncode == 0:
            raise SystemExit("checkpoint before started runtime run was accepted")
        if "external runtime run not registered" not in checkpoint_before_start.stderr:
            raise SystemExit(
                "unexpected checkpoint-before-start error: "
                + checkpoint_before_start.stderr.strip()
            )

        started = _run_runtime_json(
            {
                "runtime_name": "langgraph",
                "external_run_id": "thread-interrupt",
                "kind": "started",
                "owner_role": "role.manager",
                "actor": "role.manager",
                "objective": "pause on external-write approval",
                "tenant_id": "tenant-demo",
                "project_id": "project-runtime-interrupt",
            },
            log_path=run_log,
            human_work_log_path=human_work_log,
        )
        replayed_start = _run_runtime_json(
            {
                "runtime_name": "langgraph",
                "external_run_id": "thread-interrupt",
                "kind": "started",
                "owner_role": "role.manager",
                "actor": "role.manager",
                "objective": "pause on external-write approval",
                "tenant_id": "tenant-demo",
                "project_id": "project-runtime-interrupt",
            },
            log_path=run_log,
            human_work_log_path=human_work_log,
        )
        if replayed_start["cognitive_run_id"] != started["cognitive_run_id"]:
            raise SystemExit("started runtime event was not idempotent")

        missing_interrupt_fields = _run_runtime(
            {
                "runtime_name": "langgraph",
                "external_run_id": "thread-interrupt",
                "kind": "interrupted",
                "owner_role": "role.manager",
                "actor": "role.manager",
                "interrupt_id": "approval-1",
                "interrupt_summary": "Approve external write before resume",
                "resume_ref": "langgraph://thread-interrupt/resume/approval-1",
            },
            log_path=run_log,
            human_work_log_path=human_work_log,
            check=False,
        )
        if missing_interrupt_fields.returncode == 0:
            raise SystemExit("interrupt missing human fields was accepted")
        if "human_actor" not in missing_interrupt_fields.stderr:
            raise SystemExit(
                "unexpected missing-interrupt-field error: "
                + missing_interrupt_fields.stderr.strip()
            )

        interrupted = _run_runtime_json(
            _interrupt_event(),
            log_path=run_log,
            human_work_log_path=human_work_log,
        )
        projection = get_run(started["cognitive_run_id"], log_path=run_log)
        if projection.state != "paused":
            raise SystemExit(f"expected paused run after interrupt, got {projection.state}")
        if projection.failure_reason != "runtime interrupt: approval-1":
            raise SystemExit(f"unexpected failure_reason: {projection.failure_reason}")
        interrupt_checkpoint = _checkpoint_for(projection.as_dict(), "interrupt:approval-1")
        if interrupt_checkpoint.get("status") != "started":
            raise SystemExit(f"unexpected interrupt checkpoint: {interrupt_checkpoint}")
        if interrupt_checkpoint.get("payload_ref") != "langgraph://thread-interrupt/resume/approval-1":
            raise SystemExit("interrupt checkpoint lost resume payload ref")

        sessions = list_human_work_sessions(log_path=human_work_log)
        if len(sessions) != 1:
            raise SystemExit(f"expected one interrupt human-work session, got {len(sessions)}")
        session = sessions[0]
        if interrupted["human_work_session_id"] != session.session_id:
            raise SystemExit("CLI result did not point at the created human-work session")
        if session.requested_by != "role.manager":
            raise SystemExit(f"unexpected requested_by: {session.requested_by}")
        if session.human_actor != "human.principal":
            raise SystemExit(f"unexpected human_actor: {session.human_actor}")
        if session.receipt_required is not True:
            raise SystemExit("runtime interrupt human work must require a receipt")
        if session.agent_followup_required is not True:
            raise SystemExit("runtime interrupt human work must require agent follow-up")
        if session.agent_followup_ref != "langgraph://thread-interrupt/resume/approval-1":
            raise SystemExit("runtime interrupt human work lost resume follow-up ref")
        if session.metadata.get("cognitive_run_id") != started["cognitive_run_id"]:
            raise SystemExit("human work metadata lost cognitive run link")

        replayed_interrupt = _run_runtime_json(
            _interrupt_event(),
            log_path=run_log,
            human_work_log_path=human_work_log,
        )
        replayed_sessions = list_human_work_sessions(log_path=human_work_log)
        replayed_projection = get_run(started["cognitive_run_id"], log_path=run_log)
        if replayed_interrupt["human_work_session_id"] != session.session_id:
            raise SystemExit("replayed interrupt changed human-work session id")
        if len(replayed_sessions) != 1:
            raise SystemExit("replayed interrupt duplicated human-work session")
        if replayed_projection.side_effect_keys.count(
            "runtime_interrupt:langgraph:thread-interrupt:approval-1"
        ) != 1:
            raise SystemExit("replayed interrupt duplicated runtime side-effect key")

        print(
            json.dumps(
                {
                    "ok": True,
                    "fixture": "runtime_interrupt_command_conformance",
                    "run_id": started["cognitive_run_id"],
                    "human_work_session": session.session_id,
                    "checkpoint_before_start_blocked": True,
                    "missing_interrupt_fields_blocked": True,
                    "started_event_idempotent": True,
                    "run_paused_on_interrupt": True,
                    "interrupt_checkpoint_recorded": True,
                    "human_work_receipt_required": session.receipt_required,
                    "human_work_agent_followup_required": session.agent_followup_required,
                    "human_work_resume_ref_preserved": True,
                    "interrupt_replay_reused_human_work": True,
                    "interrupt_side_effect_key_unique": True,
                    "boundary": {
                        "executes_runtime": False,
                        "resumes_runtime": False,
                        "assigns_human": False,
                        "owns_workflow": False,
                    },
                },
                sort_keys=True,
            )
        )
    return 0


def _interrupt_event() -> dict[str, Any]:
    return {
        "runtime_name": "langgraph",
        "external_run_id": "thread-interrupt",
        "kind": "interrupted",
        "owner_role": "role.manager",
        "actor": "role.manager",
        "interrupt_id": "approval-1",
        "interrupt_summary": "Approve external write before resume",
        "human_actor": "human.principal",
        "human_deliverable": "approval note or rejection rationale",
        "resume_ref": "langgraph://thread-interrupt/resume/approval-1",
        "work_mode": "judgment",
        "bottleneck_class": "authority",
    }


def _checkpoint_for(projection: dict[str, Any], step_id: str) -> dict[str, Any]:
    for checkpoint in projection.get("checkpoints") or []:
        if checkpoint.get("step_id") == step_id:
            return dict(checkpoint)
    raise SystemExit(f"checkpoint not found: {step_id}")


def _run_runtime_json(
    event: dict[str, Any],
    *,
    log_path: Path,
    human_work_log_path: Path,
) -> dict[str, Any]:
    result = _run_runtime(
        event,
        log_path=log_path,
        human_work_log_path=human_work_log_path,
    )
    return json.loads(result.stdout)


def _run_runtime(
    event: dict[str, Any],
    *,
    log_path: Path,
    human_work_log_path: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_ROOT) if not existing else f"{SRC_ROOT}{os.pathsep}{existing}"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cognitive_firm.orchestration.runtime_adapters",
            "--log-path",
            str(log_path),
            "--human-work-log-path",
            str(human_work_log_path),
            "--event-json",
            json.dumps(event, sort_keys=True),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise SystemExit(
            "runtime_adapters CLI failed "
            f"({result.returncode}) for {event.get('kind')}: {result.stderr.strip()}"
        )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
