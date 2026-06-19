#!/usr/bin/env python3
"""Command-path A2A/H2A conformance fixture.

This script exercises the kernel-service A2A routes and the public
``human_work`` CLI in one hermetic trace:

  A2A handoff/request -> blocked obligation -> linked A2H human work ->
  receipt-backed integration -> A2A obligation closure.

It proves the seam between role-office delegation and bounded human work
without scheduling actors, running agents, or resuming an external runtime.
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

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request  # noqa: E402
from cognitive_firm.orchestration.agent_channels import list_blocked_obligations  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-a2a-h2a-conformance-") as raw:
        root = Path(raw)
        org_dir = root / "org"
        roles_dir = org_dir / "roles"
        channels_dir = org_dir / "channels"
        log_path = root / "transitions.jsonl"
        human_work_log = root / "human_work.jsonl"
        roles_dir.mkdir(parents=True)
        _write_roles(roles_dir)

        config = KernelServiceConfig(
            org_dir=org_dir,
            transition_log=log_path,
            human_work_log=human_work_log,
        )

        sent = _service(
            "POST",
            "/kernel/a2a/messages",
            {
                "from_role": "researcher",
                "to_role": "evaluator",
                "kind": "handoff",
                "subject": "Evaluate claim C after human source check",
                "body": "Continue only after the human source-check receipt is integrated.",
                "references": ["claim:C"],
                "metadata": {"conformance_fixture": "a2a_h2a"},
            },
            config=config,
            expected_status=201,
        )
        message = sent["message"]
        message_id = str(message["message_id"])
        if message["obligation_state"] != "pending":
            raise SystemExit(f"expected pending A2A obligation, got {message['obligation_state']}")

        illegal = dispatch_kernel_request(
            "POST",
            f"/kernel/a2a/messages/{message_id}/obligation",
            {
                "role_id": "evaluator",
                "state": "fulfilled",
                "actor": "agent.evaluator",
                "note": "attempted skip over accepted/in_progress",
            },
            config=config,
        )
        if illegal.status == 200:
            raise SystemExit("A2A pending -> fulfilled transition was accepted")

        _set_obligation(config, message_id, "accepted", "handoff accepted")
        _set_obligation(config, message_id, "in_progress", "work started")
        blocked = _set_obligation(
            config,
            message_id,
            "blocked_input",
            "waiting for bounded human source-check receipt",
        )
        blocked_rows = list_blocked_obligations("evaluator", channels_dir=channels_dir)
        if [row.message_id for row in blocked_rows] != [message_id]:
            raise SystemExit(f"blocked obligation not visible: {blocked_rows}")

        created_human_work = _run_human_work_json(
            [
                "create-a2h",
                "--requested-by-role",
                "role.evaluator",
                "--human-actor",
                "human.operator",
                "--objective",
                "Check the private source needed before evaluator closes claim C.",
                "--work-mode",
                "source_check",
                "--bottleneck-class",
                "access",
                "--human-deliverable",
                "source support verdict with caveat",
                "--obligation-id",
                message_id,
                "--tenant-id",
                "tenant-demo",
                "--project-id",
                "project-claim-review",
                "--interaction-surface",
                "cli",
                "--log-path",
                str(human_work_log),
            ]
        )
        session_id = str(created_human_work["session_id"])
        _run_human_work_json(["update-state", session_id, "claimed", "--log-path", str(human_work_log)])
        _run_human_work_json(["update-state", session_id, "in_progress", "--log-path", str(human_work_log)])
        _run_human_work_json(
            [
                "update-state",
                session_id,
                "completed",
                "--completion-summary",
                "Human reviewed the source, but receipt is not attached yet.",
                "--log-path",
                str(human_work_log),
            ]
        )

        rejected_integration = _run_human_work(
            [
                "update-state",
                session_id,
                "integrated",
                "--integration-ref",
                f"a2a_message:{message_id}:human-source-check",
                "--log-path",
                str(human_work_log),
            ],
            check=False,
        )
        if rejected_integration.returncode == 0:
            raise SystemExit("A2H integration without receipt was accepted")

        integrated_human_work = _run_human_work_json(
            [
                "update-state",
                session_id,
                "integrated",
                "--integration-ref",
                f"a2a_message:{message_id}:human-source-check",
                "--receipt",
                "Source supports claim C only for population Y.",
                "--confidence",
                "medium",
                "--no-agent-followup-required",
                "--log-path",
                str(human_work_log),
            ]
        )
        if integrated_human_work["obligation_id"] != message_id:
            raise SystemExit("human-work session lost its A2A obligation link")

        _set_obligation(
            config,
            message_id,
            "in_progress",
            f"human receipt integrated via {session_id}",
        )
        fulfilled = _set_obligation(
            config,
            message_id,
            "fulfilled",
            f"closed with human-work receipt {session_id}",
        )
        blocked_after = list_blocked_obligations("evaluator", channels_dir=channels_dir)
        if blocked_after:
            raise SystemExit("blocked obligation should clear after A2A fulfillment")

        print(
            json.dumps(
                {
                    "ok": True,
                    "fixture": "a2a_h2a_command_conformance",
                    "message_id": message_id,
                    "human_work_session": session_id,
                    "pending_to_fulfilled_blocked": True,
                    "blocked_obligation_visible": True,
                    "human_work_obligation_linked": True,
                    "receipt_before_integration_enforced": True,
                    "final_obligation_state": fulfilled["message"]["obligation_state"],
                    "final_human_work_state": integrated_human_work["state"],
                    "blocked_obligation_cleared": True,
                    "blocked_state_seen": blocked["message"]["obligation_state"],
                },
                sort_keys=True,
            )
        )
    return 0


def _write_roles(roles_dir: Path) -> None:
    (roles_dir / "researcher.yaml").write_text(
        "role_id: researcher\n"
        "delegates_to:\n"
        "  - evaluator\n"
        "escalates_to:\n"
        "  - manager\n",
        encoding="utf-8",
    )
    (roles_dir / "evaluator.yaml").write_text(
        "role_id: evaluator\n"
        "delegates_to:\n"
        "escalates_to:\n"
        "  - researcher\n"
        "  - manager\n",
        encoding="utf-8",
    )
    (roles_dir / "manager.yaml").write_text(
        "role_id: manager\n"
        "delegates_to:\n"
        "  - researcher\n"
        "  - evaluator\n"
        "escalates_to:\n",
        encoding="utf-8",
    )


def _service(
    method: str,
    path: str,
    body: dict[str, Any],
    *,
    config: KernelServiceConfig,
    expected_status: int = 200,
) -> dict[str, Any]:
    response = dispatch_kernel_request(method, path, body, config=config)
    if response.status != expected_status:
        raise SystemExit(f"{method} {path} failed ({response.status}): {response.payload}")
    return response.payload


def _set_obligation(
    config: KernelServiceConfig,
    message_id: str,
    state: str,
    note: str,
) -> dict[str, Any]:
    return _service(
        "POST",
        f"/kernel/a2a/messages/{message_id}/obligation",
        {
            "role_id": "evaluator",
            "state": state,
            "actor": "agent.evaluator",
            "note": note,
        },
        config=config,
    )


def _run_human_work_json(args: list[str]) -> dict[str, Any]:
    result = _run_human_work(args)
    return json.loads(result.stdout)


def _run_human_work(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_ROOT) if not existing else f"{SRC_ROOT}{os.pathsep}{existing}"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cognitive_firm.orchestration.human_work",
            *args,
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise SystemExit(
            f"human_work CLI failed ({result.returncode}) for {args}: {result.stderr.strip()}"
        )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
