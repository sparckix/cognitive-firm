#!/usr/bin/env python3
"""Command-path saga conformance fixture.

This script exercises the public ``saga_compensation`` CLI instead of calling
the primitive directly for compensation. It proves that a terminal obligation
failure emits compensation requests, exposes an active saga, and clears the
active view after compensation fulfillment.
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

from cognitive_firm.orchestration.agent_channels import (  # noqa: E402
    send_agent_message,
    update_obligation_state,
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-saga-cli-conformance-") as raw:
        root = Path(raw)
        channels_dir = root / "channels"
        roles_dir = root / "roles"
        log_path = root / "transitions.jsonl"
        channels_dir.mkdir()
        roles_dir.mkdir()
        _write_roles(roles_dir)

        step_1 = send_agent_message(
            from_role="alice",
            to_role="bob",
            kind="request",
            subject="step 1 with external side effect",
            body="Write the external side-effect artifact.",
            channels_dir=channels_dir,
            roles_dir=roles_dir,
            transition_log_path=log_path,
        )
        update_obligation_state(
            role_id="bob",
            message_id=step_1.message_id,
            new_state="accepted",
            actor="bob",
            channels_dir=channels_dir,
            transition_log_path=log_path,
        )
        update_obligation_state(
            role_id="bob",
            message_id=step_1.message_id,
            new_state="in_progress",
            actor="bob",
            channels_dir=channels_dir,
            transition_log_path=log_path,
        )
        update_obligation_state(
            role_id="bob",
            message_id=step_1.message_id,
            new_state="fulfilled",
            actor="bob",
            note="external side effect completed",
            channels_dir=channels_dir,
            transition_log_path=log_path,
        )

        step_2 = send_agent_message(
            from_role="bob",
            to_role="carol",
            kind="request",
            subject="step 2 terminal failure",
            body="Consume the side-effect artifact and close the chain.",
            parent_obligation_id=step_1.message_id,
            channels_dir=channels_dir,
            roles_dir=roles_dir,
            transition_log_path=log_path,
        )
        update_obligation_state(
            role_id="carol",
            message_id=step_2.message_id,
            new_state="refused",
            actor="carol",
            note="cannot safely consume the artifact",
            channels_dir=channels_dir,
            transition_log_path=log_path,
        )

        rejected = _run_saga_cli(
            [
                "compensate",
                "--role-id",
                "bob",
                "--message-id",
                step_1.message_id,
                "--channels-dir",
                str(channels_dir),
                "--roles-dir",
                str(roles_dir),
                "--log-path",
                str(log_path),
            ],
            check=False,
        )
        if rejected.returncode == 0:
            raise SystemExit("saga compensation accepted a non-terminal obligation")
        if "terminal-failure" not in rejected.stderr:
            raise SystemExit(f"unexpected non-terminal error: {rejected.stderr.strip()}")

        compensated = _run_json(
            [
                "compensate",
                "--role-id",
                "carol",
                "--message-id",
                step_2.message_id,
                "--reason",
                "step 2 refused; compensate step 1 side effect",
                "--channels-dir",
                str(channels_dir),
                "--roles-dir",
                str(roles_dir),
                "--log-path",
                str(log_path),
            ]
        )
        compensation_requests = compensated["compensation_requests"]
        if len(compensation_requests) != 1:
            raise SystemExit(f"expected one compensation request, got {len(compensation_requests)}")
        compensation = compensation_requests[0]
        if compensation["to_role"] != "bob":
            raise SystemExit(f"unexpected compensation target: {compensation['to_role']}")
        if compensation["parent_obligation_id"] != step_2.message_id:
            raise SystemExit("compensation did not carry saga root as parent obligation")

        active_before = _run_json(
            [
                "active",
                "--channels-dir",
                str(channels_dir),
                "--log-path",
                str(log_path),
            ]
        )
        if len(active_before["active_sagas"]) != 1:
            raise SystemExit(f"expected one active saga, got {active_before['active_sagas']}")

        compensation_id = compensation["message_id"]
        update_obligation_state(
            role_id="bob",
            message_id=compensation_id,
            new_state="accepted",
            actor="bob",
            channels_dir=channels_dir,
            transition_log_path=log_path,
        )
        update_obligation_state(
            role_id="bob",
            message_id=compensation_id,
            new_state="in_progress",
            actor="bob",
            channels_dir=channels_dir,
            transition_log_path=log_path,
        )
        update_obligation_state(
            role_id="bob",
            message_id=compensation_id,
            new_state="fulfilled",
            actor="bob",
            note="side effect compensated",
            channels_dir=channels_dir,
            transition_log_path=log_path,
        )
        active_after = _run_json(
            [
                "active",
                "--channels-dir",
                str(channels_dir),
                "--log-path",
                str(log_path),
            ]
        )
        if active_after["active_sagas"]:
            raise SystemExit("active saga should clear after compensation fulfillment")

        print(
            json.dumps(
                {
                    "ok": True,
                    "fixture": "saga_command_conformance",
                    "terminal_failure_id": step_2.message_id,
                    "non_terminal_compensation_blocked": True,
                    "compensation_requests": len(compensation_requests),
                    "active_saga_visible_before_completion": True,
                    "active_saga_cleared_after_completion": True,
                    "compensation_parent_links_root_failure": True,
                    "compensation_target_role": compensation["to_role"],
                },
                sort_keys=True,
            )
        )
    return 0


def _write_roles(roles_dir: Path) -> None:
    (roles_dir / "alice.yaml").write_text(
        "role_id: alice\n"
        "delegates_to:\n"
        "  - bob\n"
        "escalates_to:\n"
        "  - manager\n",
        encoding="utf-8",
    )
    (roles_dir / "bob.yaml").write_text(
        "role_id: bob\n"
        "delegates_to:\n"
        "  - carol\n"
        "escalates_to:\n"
        "  - alice\n",
        encoding="utf-8",
    )
    (roles_dir / "carol.yaml").write_text(
        "role_id: carol\n"
        "delegates_to:\n"
        "escalates_to:\n"
        "  - bob\n",
        encoding="utf-8",
    )
    (roles_dir / "manager.yaml").write_text(
        "role_id: manager\n"
        "delegates_to:\n"
        "  - alice\n"
        "  - bob\n"
        "  - carol\n"
        "escalates_to:\n",
        encoding="utf-8",
    )


def _run_json(args: list[str]) -> dict[str, Any]:
    result = _run_saga_cli(args)
    return json.loads(result.stdout)


def _run_saga_cli(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_ROOT) if not existing else f"{SRC_ROOT}{os.pathsep}{existing}"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cognitive_firm.orchestration.saga_compensation",
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
            f"saga_compensation CLI failed ({result.returncode}) for {args}: "
            f"{result.stderr.strip()}"
        )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
