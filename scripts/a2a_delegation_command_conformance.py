#!/usr/bin/env python3
"""Command-path A2A delegation/handoff conformance fixture.

This script exercises the kernel-service A2A routes in one hermetic trace:

  role-policy denial -> allowed handoff -> envelope acknowledgement ->
  ordered obligation lifecycle -> loop/depth guard failures.

It proves standalone delegation and handoff invariants without human-work
bridging, runtime execution, scheduling, route synthesis, or workflow ownership.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

sys.path.insert(0, str(SRC_ROOT))

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request  # noqa: E402
from cognitive_firm.orchestration.agent_channels import read_agent_message  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-a2a-delegation-conformance-") as raw:
        root = Path(raw)
        org_dir = root / "org"
        roles_dir = org_dir / "roles"
        channels_dir = org_dir / "channels"
        log_path = root / "transitions.jsonl"
        roles_dir.mkdir(parents=True)
        _write_roles(roles_dir)

        config = KernelServiceConfig(
            org_dir=org_dir,
            transition_log=log_path,
            a2a_max_thread_messages=2,
            a2a_max_parent_depth=2,
        )

        denied_before = _message_file_count(channels_dir)
        denied = dispatch_kernel_request(
            "POST",
            "/kernel/a2a/messages",
            {
                "from_role": "planner",
                "to_role": "observer",
                "kind": "handoff",
                "subject": "Unauthorized handoff",
                "body": "This edge is not present in delegates_to or escalates_to.",
            },
            config=config,
        )
        denied_after = _message_file_count(channels_dir)
        if denied.status == 201:
            raise SystemExit("unlinked role handoff was accepted")
        if "not linked" not in str(denied.payload):
            raise SystemExit(f"unexpected denied-edge payload: {denied.payload}")
        if denied_after != denied_before:
            raise SystemExit("denied handoff wrote a message envelope")

        handoff = _service(
            "POST",
            "/kernel/a2a/messages",
            {
                "from_role": "planner",
                "to_role": "evaluator",
                "kind": "handoff",
                "subject": "Take over source review",
                "body": "Continue the source review from artifact://review/context.",
                "thread_id": "thread-delegation-main",
                "references": ["artifact://review/context"],
                "artifacts": ["artifact://review/draft"],
                "metadata": {"conformance_fixture": "a2a_delegation"},
            },
            config=config,
            expected_status=201,
        )["message"]
        message_id = str(handoff["message_id"])
        if handoff["obligation_state"] != "pending":
            raise SystemExit(f"handoff did not start pending: {handoff}")
        if "receiver is in sender" not in handoff["metadata"].get("channel_policy", ""):
            raise SystemExit(f"unexpected channel policy: {handoff['metadata']}")

        acknowledged = _service(
            "POST",
            f"/kernel/a2a/messages/{message_id}/status",
            {
                "role_id": "evaluator",
                "status": "acknowledged",
                "actor": "agent.evaluator",
                "note": "envelope read; obligation not accepted yet",
            },
            config=config,
        )["message"]
        if acknowledged["status"] != "acknowledged":
            raise SystemExit("message status did not update to acknowledged")
        if acknowledged["obligation_state"] != "pending":
            raise SystemExit("envelope acknowledgement changed obligation state")

        illegal_skip = dispatch_kernel_request(
            "POST",
            f"/kernel/a2a/messages/{message_id}/obligation",
            {
                "role_id": "evaluator",
                "state": "fulfilled",
                "actor": "agent.evaluator",
                "note": "attempted direct completion",
            },
            config=config,
        )
        if illegal_skip.status == 200:
            raise SystemExit("pending -> fulfilled obligation skip was accepted")

        accepted = _set_obligation(config, message_id, "accepted", "handoff accepted")
        in_progress = _set_obligation(config, message_id, "in_progress", "work started")
        fulfilled = _set_obligation(config, message_id, "fulfilled", "handoff completed")
        if fulfilled["message"]["status"] != "acknowledged":
            raise SystemExit("obligation lifecycle changed envelope status")

        terminal_reopen = dispatch_kernel_request(
            "POST",
            f"/kernel/a2a/messages/{message_id}/obligation",
            {
                "role_id": "evaluator",
                "state": "refused",
                "actor": "agent.evaluator",
                "note": "attempted terminal transition",
            },
            config=config,
        )
        if terminal_reopen.status == 200:
            raise SystemExit("terminal obligation transition was accepted")

        inform = _service(
            "POST",
            "/kernel/a2a/messages",
            {
                "from_role": "planner",
                "to_role": "evaluator",
                "kind": "inform",
                "subject": "Context update only",
                "body": "No work is requested by this message.",
                "thread_id": "thread-inform",
            },
            config=config,
            expected_status=201,
        )["message"]
        inform_obligation = dispatch_kernel_request(
            "POST",
            f"/kernel/a2a/messages/{inform['message_id']}/obligation",
            {
                "role_id": "evaluator",
                "state": "accepted",
                "actor": "agent.evaluator",
                "note": "attempted obligation on non-obligating performative",
            },
            config=config,
        )
        if inform_obligation.status == 200:
            raise SystemExit("inform message accepted an obligation transition")

        guard_config = KernelServiceConfig(
            org_dir=org_dir,
            transition_log=log_path,
            a2a_max_thread_messages=1,
            a2a_max_parent_depth=1,
        )
        _service(
            "POST",
            "/kernel/a2a/messages",
            {
                "from_role": "planner",
                "to_role": "evaluator",
                "kind": "request",
                "subject": "Thread guard root",
                "body": "First message in a bounded thread.",
                "thread_id": "thread-guard",
            },
            config=guard_config,
            expected_status=201,
        )
        thread_guard = dispatch_kernel_request(
            "POST",
            "/kernel/a2a/messages",
            {
                "from_role": "planner",
                "to_role": "evaluator",
                "kind": "status",
                "subject": "Thread guard overflow",
                "body": "Second message should exceed the configured thread limit.",
                "thread_id": "thread-guard",
            },
            config=guard_config,
        )
        if thread_guard.status == 201:
            raise SystemExit("thread guard accepted a second message at limit 1")

        root = _service(
            "POST",
            "/kernel/a2a/messages",
            {
                "from_role": "planner",
                "to_role": "evaluator",
                "kind": "request",
                "subject": "Parent-depth root",
                "body": "Root obligation.",
                "thread_id": "thread-depth-root",
            },
            config=guard_config,
            expected_status=201,
        )["message"]
        depth_guard = dispatch_kernel_request(
            "POST",
            "/kernel/a2a/messages",
            {
                "from_role": "evaluator",
                "to_role": "planner",
                "kind": "handoff",
                "subject": "Depth guard child",
                "body": "Child should exceed parent depth limit 1.",
                "thread_id": "thread-depth-child",
                "parent_obligation_id": root["message_id"],
            },
            config=guard_config,
        )
        if depth_guard.status == 201:
            raise SystemExit("parent-depth guard accepted a child at limit 1")

        mirrored = _read_sent_message(channels_dir, "planner", message_id)
        received = read_agent_message(
            role_id="evaluator",
            message_id=message_id,
            channels_dir=channels_dir,
        )
        if mirrored is None or received is None:
            raise SystemExit("sender/receiver message mirrors were not both present")
        if mirrored.obligation_state != "fulfilled" or received.obligation_state != "fulfilled":
            raise SystemExit("sender/receiver mirrors diverged on obligation state")

        event_names = _event_names(log_path)
        _assert_in_order(
            event_names,
            [
                "agent.message.sent",
                "agent.message.acknowledged",
                "agent.obligation.accepted",
                "agent.obligation.in_progress",
                "agent.obligation.fulfilled",
            ],
        )

        print(
            json.dumps(
                {
                    "ok": True,
                    "fixture": "a2a_delegation_command_conformance",
                    "message_id": message_id,
                    "unauthorized_edge_blocked": True,
                    "unauthorized_edge_wrote_no_message": True,
                    "allowed_handoff_policy": handoff["metadata"]["channel_policy"],
                    "handoff_started_pending": True,
                    "envelope_ack_obligation_still_pending": True,
                    "pending_to_fulfilled_blocked": True,
                    "ordered_lifecycle": [
                        accepted["message"]["obligation_state"],
                        in_progress["message"]["obligation_state"],
                        fulfilled["message"]["obligation_state"],
                    ],
                    "terminal_transition_blocked": True,
                    "inform_has_no_obligation": True,
                    "thread_guard_blocked": True,
                    "parent_depth_guard_blocked": True,
                    "mirrors_stay_consistent": True,
                    "boundary": {
                        "synthesizes_route": False,
                        "schedules_work": False,
                        "runs_agent": False,
                        "owns_workflow": False,
                    },
                },
                sort_keys=True,
            )
        )
    return 0


def _write_roles(roles_dir: Path) -> None:
    (roles_dir / "planner.yaml").write_text(
        "role_id: planner\n"
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
        "  - planner\n"
        "  - manager\n",
        encoding="utf-8",
    )
    (roles_dir / "observer.yaml").write_text(
        "role_id: observer\n"
        "delegates_to:\n"
        "escalates_to:\n"
        "  - manager\n",
        encoding="utf-8",
    )
    (roles_dir / "manager.yaml").write_text(
        "role_id: manager\n"
        "delegates_to:\n"
        "  - planner\n"
        "  - evaluator\n"
        "  - observer\n"
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


def _message_file_count(channels_dir: Path) -> int:
    if not channels_dir.exists():
        return 0
    return len(list(channels_dir.glob("*/*/*.json")))


def _read_sent_message(channels_dir: Path, role_id: str, message_id: str) -> Any:
    path = channels_dir / role_id / "sent" / f"{message_id}.json"
    if not path.exists():
        return None
    from cognitive_firm.orchestration.agent_channels import AgentMessage

    return AgentMessage(**json.loads(path.read_text(encoding="utf-8")))


def _event_names(log_path: Path) -> list[str]:
    if not log_path.exists():
        return []
    names: list[str] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            names.append(str(json.loads(line).get("event") or ""))
    return names


def _assert_in_order(event_names: list[str], expected: list[str]) -> None:
    cursor = 0
    for event in event_names:
        if cursor < len(expected) and event == expected[cursor]:
            cursor += 1
    if cursor != len(expected):
        raise SystemExit(
            f"expected events in order {expected}, got {event_names}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
