#!/usr/bin/env python3
"""Preflight a local/subscription agent runtime before live org-evolution demos."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_attestation import digest_text  # noqa: E402
from cognitive_firm.orchestration.agent_runtime_invocation import (  # noqa: E402
    AgentRuntimeSlot,
    agent_subprocess_env,
    build_agent_invocation,
    build_agent_runtime_readiness_summary,
    infer_agent_adapter,
    infer_subscription_runtime_from_adapter,
    redact_prompt_text,
    safe_command_for_receipt,
)


PREFLIGHT_PROMPT = (
    'Return ONLY this exact JSON object and no prose: {"ok": true, "kind": "agent_preflight"}'
)


def run_preflight(
    *,
    agent_runtime: str,
    agent_adapter: str = "auto",
    project_root: Path | str = ROOT,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Run a tiny no-mutation preflight against a role-bearing agent CLI."""

    adapter = infer_agent_adapter(agent_runtime, requested=agent_adapter)
    invocation = build_agent_invocation(
        agent_cli=agent_runtime,
        adapter=adapter,
        prompt=PREFLIGHT_PROMPT,
        project_root=project_root,
    )
    metadata = {
        "runtime": agent_runtime,
        "adapter": adapter,
        "command_argv": safe_command_for_receipt(invocation.argv, prompt=PREFLIGHT_PROMPT),
        "prompt_transport": invocation.prompt_transport,
        "prompt_digest": digest_text(PREFLIGHT_PROMPT),
        "timeout_seconds": timeout_seconds,
    }
    try:
        result = subprocess.run(
            invocation.argv,
            cwd=Path(project_root),
            input=invocation.stdin,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=agent_subprocess_env(
                runtime=infer_subscription_runtime_from_adapter(adapter),
            ),
        )
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "status": "command_not_found",
            "reason": f"agent runtime command not found: {exc.filename}",
            "metadata": {
                **metadata,
                "returncode": None,
                "stderr_digest": digest_text(str(exc)),
                "stderr_preview": str(exc),
            },
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return {
            "ok": False,
            "status": "timed_out",
            "reason": "agent runtime preflight timed out",
            "metadata": {
                **metadata,
                "returncode": None,
                "stdout_digest": digest_text(stdout),
                "stderr_digest": digest_text(stderr),
                "stdout_preview": redact_prompt_text(stdout[-1000:], PREFLIGHT_PROMPT),
                "stderr_preview": redact_prompt_text(stderr[-1000:], PREFLIGHT_PROMPT),
            },
        }

    failure_reason = _runtime_failure_reason(result.returncode, result.stdout, result.stderr)
    base = {
        "metadata": {
            **metadata,
            "returncode": result.returncode,
            "stdout_digest": digest_text(result.stdout),
            "stderr_digest": digest_text(result.stderr),
            "stdout_preview": redact_prompt_text(result.stdout[-1000:], PREFLIGHT_PROMPT),
            "stderr_preview": redact_prompt_text(result.stderr[-1000:], PREFLIGHT_PROMPT),
        }
    }
    if result.returncode != 0:
        return {
            "ok": False,
            "status": "runtime_failed",
            "reason": failure_reason,
            **base,
        }
    try:
        parsed = _extract_json_object(result.stdout)
    except ValueError as exc:
        return {
            "ok": False,
            "status": "invalid_json",
            "reason": str(exc),
            **base,
        }
    if parsed.get("ok") is not True or parsed.get("kind") != "agent_preflight":
        return {
            "ok": False,
            "status": "wrong_payload",
            "reason": "agent runtime did not return the expected preflight payload",
            "payload": parsed,
            **base,
        }
    return {
        "ok": True,
        "status": "ready",
        "reason": "agent runtime returned expected preflight payload",
        "payload": parsed,
        **base,
    }


def run_live_demo_readiness(
    *,
    planner_runtime: str,
    planner_adapter: str = "auto",
    reviewer_runtime: str | None = None,
    reviewer_adapter: str = "auto",
    workload_executor_runtime: str | None = None,
    workload_executor_adapter: str = "auto",
    project_root: Path | str = ROOT,
    timeout_seconds: int = 30,
    reviewer_timeout_seconds: int | None = None,
    workload_executor_timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Preflight all configured live-agent slots for the self-evolving demo."""

    slots = [
        AgentRuntimeSlot(
            slot_id="planner",
            role_id="role.org_evolver",
            purpose="propose bounded structural mutations",
            runtime=planner_runtime,
            adapter=planner_adapter,
            required=True,
            timeout_seconds=timeout_seconds,
        ),
        AgentRuntimeSlot(
            slot_id="reviewer",
            role_id="role.evaluator,role.risk_guardian,role.learning_steward",
            purpose="emit advisory reviewer positions",
            runtime=reviewer_runtime,
            adapter=reviewer_adapter,
            required=False,
            timeout_seconds=reviewer_timeout_seconds or timeout_seconds,
        ),
        AgentRuntimeSlot(
            slot_id="workload_executor",
            role_id="role.org_evolver",
            purpose="execute visible workload packets before scoring",
            runtime=workload_executor_runtime,
            adapter=workload_executor_adapter,
            required=False,
            timeout_seconds=workload_executor_timeout_seconds or timeout_seconds,
        ),
    ]
    results: dict[str, dict[str, Any]] = {}
    for slot in slots:
        if not slot.runtime:
            continue
        results[slot.slot_id] = run_preflight(
            agent_runtime=slot.runtime,
            agent_adapter=slot.adapter or "auto",
            project_root=project_root,
            timeout_seconds=slot.timeout_seconds or timeout_seconds,
        )
    return build_agent_runtime_readiness_summary(
        slots=slots,
        preflight_results=results,
    )


def _runtime_failure_reason(returncode: int, stdout: str, stderr: str) -> str:
    combined = f"{stdout}\n{stderr}".lower()
    if "not logged in" in combined or "please run /login" in combined:
        return "agent runtime requires local login"
    if "credit balance is too low" in combined or "credit exhausted" in combined:
        return "agent runtime API-key credit is unavailable; check subscription auth"
    if "failed to initialize" in combined and "app-server" in combined:
        return "agent runtime initialization failed"
    return f"agent runtime exited {returncode}"


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("agent runtime did not return a JSON object")
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise ValueError("agent runtime returned JSON that is not an object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preflight a local/subscription agent runtime without mutating state."
    )
    parser.add_argument("--agent-runtime", required=True, help="Agent CLI, e.g. claude or codex.")
    parser.add_argument(
        "--agent-adapter",
        default="auto",
        choices=["auto", "claude_print", "codex_exec"],
    )
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--agent-reviewer-runtime")
    parser.add_argument(
        "--agent-reviewer-adapter",
        default="auto",
        choices=["auto", "claude_print", "codex_exec"],
    )
    parser.add_argument("--reviewer-timeout-seconds", type=int)
    parser.add_argument("--workload-executor-runtime")
    parser.add_argument(
        "--workload-executor-adapter",
        default="auto",
        choices=["auto", "claude_print", "codex_exec"],
    )
    parser.add_argument("--workload-executor-timeout-seconds", type=int)
    parser.add_argument(
        "--readiness-summary",
        action="store_true",
        help="Return an agent_runtime_readiness_summary.v1 across configured slots.",
    )
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.reviewer_timeout_seconds is not None and args.reviewer_timeout_seconds <= 0:
        parser.error("--reviewer-timeout-seconds must be positive")
    if (
        args.workload_executor_timeout_seconds is not None
        and args.workload_executor_timeout_seconds <= 0
    ):
        parser.error("--workload-executor-timeout-seconds must be positive")

    if (
        args.readiness_summary
        or args.agent_reviewer_runtime
        or args.workload_executor_runtime
    ):
        result = run_live_demo_readiness(
            planner_runtime=args.agent_runtime,
            planner_adapter=args.agent_adapter,
            reviewer_runtime=args.agent_reviewer_runtime,
            reviewer_adapter=args.agent_reviewer_adapter,
            workload_executor_runtime=args.workload_executor_runtime,
            workload_executor_adapter=args.workload_executor_adapter,
            project_root=args.project_root,
            timeout_seconds=args.timeout_seconds,
            reviewer_timeout_seconds=args.reviewer_timeout_seconds,
            workload_executor_timeout_seconds=args.workload_executor_timeout_seconds,
        )
    else:
        result = run_preflight(
            agent_runtime=args.agent_runtime,
            agent_adapter=args.agent_adapter,
            project_root=args.project_root,
            timeout_seconds=args.timeout_seconds,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", result.get("ready")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
