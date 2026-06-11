#!/usr/bin/env python3
"""Command-path A2H conformance fixture.

This script exercises the public ``human_work`` CLI rather than importing the
primitive directly. It proves the receipt-before-integration rule through the
same command path an adapter or operator script would use.
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


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-a2h-cli-conformance-") as raw:
        root = Path(raw)
        log_path = root / "human_work.jsonl"

        created = _run_json(
            [
                "create-a2h",
                "--requested-by-role",
                "role.researcher",
                "--human-actor",
                "human.operator",
                "--objective",
                "Check the private source and report whether it supports claim C.",
                "--work-mode",
                "source_check",
                "--bottleneck-class",
                "access",
                "--human-deliverable",
                "bounded source-support claim plus short rationale",
                "--obligation-id",
                "msg_claim_c",
                "--tenant-id",
                "tenant-demo",
                "--project-id",
                "project-claim-review",
                "--interaction-surface",
                "cli",
                "--log-path",
                str(log_path),
            ]
        )
        session_id = str(created["session_id"])

        _run_json(["update-state", session_id, "claimed", "--log-path", str(log_path)])
        _run_json(["update-state", session_id, "in_progress", "--log-path", str(log_path)])
        completed_without_receipt = _run_json(
            [
                "update-state",
                session_id,
                "completed",
                "--completion-summary",
                "Human checked the private source but has not supplied a receipt.",
                "--log-path",
                str(log_path),
            ]
        )

        rejected = _run_cli(
            [
                "update-state",
                session_id,
                "integrated",
                "--integration-ref",
                "artifact://claim-c/integrated",
                "--log-path",
                str(log_path),
            ],
            check=False,
        )
        if rejected.returncode == 0:
            raise SystemExit("receipt-before-integration check did not reject missing receipt")
        if "requires receipt" not in rejected.stderr:
            raise SystemExit(f"unexpected missing-receipt error: {rejected.stderr.strip()}")

        integrated = _run_json(
            [
                "update-state",
                session_id,
                "integrated",
                "--integration-ref",
                "artifact://claim-c/integrated",
                "--receipt",
                "private source supports claim C with caveat: population Y only",
                "--confidence",
                "high",
                "--no-agent-followup-required",
                "--log-path",
                str(log_path),
            ]
        )
        resources = _run_lines(["list", "--log-path", str(log_path), "--resource"])
        if len(resources) != 1:
            raise SystemExit(f"expected one resource row, got {len(resources)}")
        resource = resources[0]
        if resource["kind"] != "HumanWorkSession":
            raise SystemExit(f"unexpected resource kind: {resource['kind']}")
        if resource["status"]["receipt_present"] is not True:
            raise SystemExit("integrated resource did not report receipt_present=true")
        if resource["status"]["state"] != "integrated":
            raise SystemExit(f"unexpected final state: {resource['status']['state']}")

        print(
            json.dumps(
                {
                    "ok": True,
                    "fixture": "a2h_command_conformance",
                    "session_id": session_id,
                    "receipt_before_integration_enforced": True,
                    "completed_without_receipt_state": completed_without_receipt["state"],
                    "final_state": integrated["state"],
                    "resource_kind": resource["kind"],
                    "resource_receipt_present": resource["status"]["receipt_present"],
                },
                sort_keys=True,
            )
        )
    return 0


def _run_json(args: list[str]) -> dict[str, Any]:
    result = _run_cli(args)
    return json.loads(result.stdout)


def _run_lines(args: list[str]) -> list[dict[str, Any]]:
    result = _run_cli(args)
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def _run_cli(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
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
