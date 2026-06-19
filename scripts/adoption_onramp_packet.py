#!/usr/bin/env python3
"""Collect fixed no-cost adoption evidence and render a readiness packet.

This is an operator convenience harness for the first serious repo review. It
runs a fixed set of deterministic proof commands with per-command timeouts,
then feeds their JSON outputs into the existing adoption-readiness packet
builder. It is not a configurable workflow runner, scheduler, release approval,
or kernel state store.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.governed_run_recipes import (  # noqa: E402
    AdoptionReadinessPacketInput,
    build_adoption_readiness_packet,
)


@dataclass(frozen=True)
class CollectionStep:
    check_id: str
    label: str
    args: tuple[str, ...]
    output_name: str
    optional: bool = False


CORE_STEPS: tuple[CollectionStep, ...] = (
    CollectionStep(
        check_id="first_gated_action",
        label="First gated action",
        args=("scripts/native_e2e_demo.py",),
        output_name="first-gated-action.json",
    ),
    CollectionStep(
        check_id="kernel_service_smoke",
        label="Kernel service smoke",
        args=("scripts/kernel_service_smoke.py",),
        output_name="kernel-service-smoke.json",
    ),
    CollectionStep(
        check_id="learning_loop_walkthrough",
        label="Learning loop walkthrough",
        args=("scripts/learning_loop_walkthrough.py",),
        output_name="learning-loop-walkthrough.json",
    ),
)

OPTIONAL_STEPS: tuple[CollectionStep, ...] = (
    CollectionStep(
        check_id="agent_fleet_audit_demo",
        label="Agent-fleet audit demo",
        args=("scripts/agent_fleet_audit_demo.py",),
        output_name="agent-fleet-audit-demo.json",
        optional=True,
    ),
    CollectionStep(
        check_id="field_pilot_action_impact_demo",
        label="Field-pilot action-impact demo",
        args=("scripts/field_pilot_action_impact_demo.py",),
        output_name="field-pilot-action-impact-demo.json",
        optional=True,
    ),
    CollectionStep(
        check_id="formal_provider_proof_pack",
        label="Formal-provider proof pack",
        args=("scripts/formal_provider_proof_pack.py",),
        output_name="formal-provider-proof-pack.json",
        optional=True,
    ),
    CollectionStep(
        check_id="adapter_policy_preview",
        label="Adapter-policy preview",
        args=("scripts/langgraph_adapter_policy_preview.py",),
        output_name="adapter-policy-preview.json",
        optional=True,
    ),
    CollectionStep(
        check_id="runtime_adapter_proof_pack",
        label="Runtime-adapter proof pack",
        args=("scripts/runtime_adapter_proof_pack.py",),
        output_name="runtime-adapter-proof-pack.json",
        optional=True,
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run fixed no-cost adoption proof commands and build an adoption "
            "readiness handoff packet."
        )
    )
    parser.add_argument("--target-label", default="local_adopter")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Directory for result JSON, command logs, and packet files. Defaults "
            "to a timestamped .cognitive-firm-runs/adoption-onramp folder."
        ),
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="Collect only the required fast checks.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=90.0,
        help="Per-command timeout for deterministic proof commands.",
    )
    parser.add_argument(
        "--result",
        action="append",
        default=[],
        metavar="CHECK_ID=PATH",
        help=(
            "Externally produced JSON result to include in the packet without "
            "running it here, for example "
            "bounded_live_agent_run=/tmp/live-agent-result.json. Repeat as needed."
        ),
    )
    parser.add_argument(
        "--include-live-agent",
        action="store_true",
        help="Include the optional live-agent row in the rendered packet as missing unless supplied separately.",
    )
    parser.add_argument(
        "--include-release-gate",
        action="store_true",
        help="Include the release-candidate gate row in the rendered packet as missing unless supplied separately.",
    )
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    steps = list(CORE_STEPS if args.core_only else CORE_STEPS + OPTIONAL_STEPS)

    command_results: list[dict[str, Any]] = []
    observed_results: dict[str, dict[str, Any]] = {}
    for step in steps:
        result = _run_step(
            step,
            output_dir=output_dir,
            timeout_seconds=args.timeout_seconds,
        )
        command_results.append(result)
        if result["status"] == "passed":
            observed = _load_json(Path(result["output_path"]))
            if observed is not None:
                observed_results[step.check_id] = observed

    extra_results, extra_result_records = _load_extra_results(args.result)
    duplicate_ids = sorted(set(observed_results) & set(extra_results))
    if duplicate_ids:
        joined = ", ".join(duplicate_ids)
        raise SystemExit(f"--result duplicates collected check id(s): {joined}")
    observed_results.update(extra_results)
    include_live_agent = (
        args.include_live_agent or "bounded_live_agent_run" in extra_results
    )
    include_release_gate = (
        args.include_release_gate or "release_candidate_check" in extra_results
    )
    evidence_refs = [
        f"file://{Path(result['output_path']).resolve()}"
        for result in command_results
        if result["status"] == "passed"
    ]
    evidence_refs.extend(record["evidence_ref"] for record in extra_result_records)
    packet = build_adoption_readiness_packet(
        AdoptionReadinessPacketInput(
            target_label=args.target_label,
            observed_results=observed_results,
            include_live_agent=include_live_agent,
            include_release_gate=include_release_gate,
            evidence_refs=evidence_refs,
            metadata={
                "collector": "scripts/adoption_onramp_packet.py",
                "output_dir": str(output_dir),
                "core_only": args.core_only,
                "timeout_seconds": args.timeout_seconds,
                "external_results": extra_result_records,
            },
        )
    )
    packet_json_path = output_dir / "adoption-readiness-packet.json"
    packet_md_path = output_dir / "adoption-readiness-packet.md"
    packet_json_path.write_text(
        json.dumps(packet, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    packet_md_path.write_text(packet["markdown"].rstrip() + "\n", encoding="utf-8")

    failed_commands = [
        result for result in command_results if result["status"] != "passed"
    ]
    summary = {
        "schema": "adoption_onramp_collection.v1",
        "target_label": args.target_label,
        "output_dir": str(output_dir),
        "ok": not failed_commands
        and packet["summary"]["ready_for_human_adoption_review"],
        "summary": {
            "commands": len(command_results),
            "passed_commands": len(command_results) - len(failed_commands),
            "failed_commands": len(failed_commands),
            "external_results": len(extra_result_records),
            "observed_checks": packet["summary"]["observed_checks"],
            "failed_checks": packet["summary"]["failed_checks"],
            "warning_checks": packet["summary"]["warning_checks"],
            "required_blockers": packet["summary"]["required_blockers"],
            "evidence_quality_blockers": packet["summary"][
                "evidence_quality_blockers"
            ],
            "optional_evidence_blockers": packet["summary"][
                "optional_evidence_blockers"
            ],
            "composition_blockers": packet["summary"]["composition_blockers"],
            "ready_for_human_adoption_review": packet["summary"][
                "ready_for_human_adoption_review"
            ],
        },
        "packet_path": str(packet_json_path),
        "markdown_path": str(packet_md_path),
        "commands": command_results,
        "external_results": extra_result_records,
        "boundary": {
            "executes_fixed_local_commands": True,
            "does_not_run_external_agents": True,
            "does_not_approve_release": True,
            "does_not_schedule_work": True,
            "does_not_mutate_durable_kernel_state": True,
            "does_not_replace_human_review": True,
            "not_a_workflow_engine": True,
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


def _run_step(
    step: CollectionStep,
    *,
    output_dir: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    output_path = output_dir / step.output_name
    stdout_path = output_dir / f"{step.check_id}.stdout.txt"
    stderr_path = output_dir / f"{step.check_id}.stderr.txt"
    command = [sys.executable, str(ROOT / step.args[0]), "--output", str(output_path)]
    if step.check_id == "agent_fleet_audit_demo":
        command.extend(["--output-dir", str(output_dir / "agent-fleet-runbook")])

    started = time.monotonic()
    status = "passed"
    returncode: int | None = None
    timeout = False
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=_command_env(),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        status = "timed_out"
        timeout = True
        stdout = exc.stdout or ""
        stderr = exc.stderr or f"timed out after {timeout_seconds} seconds"
    else:
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        if completed.returncode != 0:
            status = "failed"
    duration = round(time.monotonic() - started, 4)

    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    if status == "passed" and not output_path.exists():
        status = "failed"
        stderr_path.write_text(
            stderr + f"\nmissing expected output file: {output_path}\n",
            encoding="utf-8",
        )
    return {
        "check_id": step.check_id,
        "label": step.label,
        "status": status,
        "optional": step.optional,
        "returncode": returncode,
        "timeout": timeout,
        "duration_seconds": duration,
        "command": " ".join(command),
        "output_path": str(output_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_extra_results(items: list[str]) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    results: dict[str, dict[str, Any]] = {}
    records: list[dict[str, str]] = []
    for item in items:
        if "=" not in item:
            raise SystemExit("--result must use CHECK_ID=PATH")
        check_id, raw_path = item.split("=", 1)
        check_id = check_id.strip()
        path = Path(raw_path.strip())
        if not check_id:
            raise SystemExit("--result check id cannot be blank")
        if check_id in results:
            raise SystemExit(f"--result provided more than once for {check_id}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise SystemExit(f"cannot read result {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SystemExit(f"cannot parse result {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise SystemExit(f"result {path} must contain a JSON object")
        evidence_ref = f"file://{path.resolve()}"
        results[check_id] = payload
        records.append(
            {
                "check_id": check_id,
                "path": str(path),
                "evidence_ref": evidence_ref,
            }
        )
    return results, records


def _command_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    if env.get("PYTHONPATH"):
        pythonpath = pythonpath + os.pathsep + env["PYTHONPATH"]
    env["PYTHONPATH"] = pythonpath
    return env


def _default_output_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / ".cognitive-firm-runs" / "adoption-onramp" / stamp


if __name__ == "__main__":
    raise SystemExit(main())
