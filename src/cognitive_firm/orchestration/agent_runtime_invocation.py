"""Provider-neutral subprocess invocation policy for role-bearing agents.

The kernel owns the dispatch boundary: which project root is visible, which
permission mode is used, which prompt transport is used, and whether API-key
environment variables are optionally withheld. The CLI still owns model
execution, tool use, auth, and session internals.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

AGENT_ADAPTERS = ("claude_print", "codex_exec")
CLAUDE_API_AUTH_ENV = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
)
CODEX_API_AUTH_ENV = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_ORG_ID",
)
OPTIONAL_MODEL_API_AUTH_ENV = (
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_COMPATIBLE_API_KEY",
)


@dataclass(frozen=True)
class AgentInvocation:
    argv: list[str]
    stdin: str | None
    prompt_transport: str


@dataclass(frozen=True)
class AgentAdapterSpec:
    """Public metadata for a supported role-bearing agent worker shape."""

    adapter: str
    runtime: str | None
    worker_shape: str
    command_family: str
    prompt_transport_default: str
    auth_boundary: str
    continuity: str
    make_env: dict[str, str]
    notes: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "runtime": self.runtime,
            "worker_shape": self.worker_shape,
            "command_family": self.command_family,
            "prompt_transport_default": self.prompt_transport_default,
            "auth_boundary": self.auth_boundary,
            "continuity": self.continuity,
            "make_env": dict(self.make_env),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class AgentRuntimeSlot:
    """One role-bearing runtime slot a demo/adapter expects to spawn."""

    slot_id: str
    role_id: str
    purpose: str
    runtime: str | None
    adapter: str | None = "auto"
    required: bool = True
    timeout_seconds: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "role_id": self.role_id,
            "purpose": self.purpose,
            "runtime": self.runtime,
            "adapter": self.adapter,
            "required": self.required,
            "timeout_seconds": self.timeout_seconds,
        }


AGENT_INVOCATION_RECEIPT_SCHEMA = "agent_invocation_receipt.v1"
AGENT_ADAPTER_SPECS: tuple[AgentAdapterSpec, ...] = (
    AgentAdapterSpec(
        adapter="claude_print",
        runtime="claude",
        worker_shape="subscription_cli",
        command_family="claude --print",
        prompt_transport_default="argv",
        auth_boundary="local Claude Code subscription/OAuth/token state; API-key auth scrubbed by default",
        continuity="daemon may pass --session-id/--resume; planner bridge records receipt but does not own native memory",
        make_env={"AGENT_RUNTIME": "claude", "AGENT_ADAPTER": "claude_print"},
        notes="Use after `claude` local login succeeds; supports Claude Code tool permission flags.",
    ),
    AgentAdapterSpec(
        adapter="codex_exec",
        runtime="codex",
        worker_shape="subscription_cli",
        command_family="codex exec",
        prompt_transport_default="stdin",
        auth_boundary="local Codex subscription/OAuth/token state; OpenAI API-key auth scrubbed by default",
        continuity="Codex exec reports session ids but does not expose daemon resume flags here",
        make_env={"AGENT_RUNTIME": "codex", "AGENT_ADAPTER": "codex_exec"},
        notes="Use after `codex exec` preflight succeeds; sandbox defaults to workspace-write.",
    ),
)
CUSTOM_PLANNER_COMMAND_SPEC = AgentAdapterSpec(
    adapter="custom_planner_command",
    runtime=None,
    worker_shape="local_wrapper",
    command_family="AGENT_PLANNER_COMMAND",
    prompt_transport_default="stdin or {prompt_file}",
    auth_boundary="owned by the wrapper command; cognitive-firm captures command, output, and digests",
    continuity="wrapper-defined; kernel treats output as a bounded planner artifact",
    make_env={"AGENT_PLANNER_COMMAND": "/absolute/path/to/planner {prompt_file}"},
    notes="Any local executable can participate if it emits the planner JSON schema on stdout.",
)
API_MODEL_CALL_SPEC = AgentAdapterSpec(
    adapter="api_model_call",
    runtime=None,
    worker_shape="api_model_call",
    command_family="LLMRuntime",
    prompt_transport_default="request body",
    auth_boundary="provider API keys managed by LLMRuntime",
    continuity="fungible model call; not a persistent local agent CLI",
    make_env={"MODEL_ID": "openai-compatible:<model>"},
    notes="Covers OpenAI, Anthropic, Gemini, DeepSeek, and OpenAI-compatible servers; useful fallback, weaker worker shape.",
)


def list_agent_adapter_specs(*, include_non_cli: bool = True) -> list[dict[str, Any]]:
    """Return the supported worker-shape registry for demos and docs."""

    return [
        spec.as_dict()
        for spec in _agent_adapter_specs(include_non_cli=include_non_cli)
    ]


def get_agent_adapter_spec(adapter: str) -> dict[str, Any] | None:
    for spec in _agent_adapter_specs(include_non_cli=True):
        if spec.adapter == adapter:
            return spec.as_dict()
    return None


def build_agent_runtime_readiness_summary(
    *,
    slots: list[AgentRuntimeSlot],
    preflight_results: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a readiness summary across role-bearing runtime slots.

    This is a read model. It does not execute CLIs, grant authority, or decide
    whether a later work item should run. Callers execute tiny preflights and
    pass their results here so demos/adapters expose one consistent readiness
    surface before a bounded live run.
    """

    rows: list[dict[str, Any]] = []
    missing_required: list[str] = []
    failed_required: list[str] = []
    ready = 0
    configured = 0
    for slot in slots:
        runtime = str(slot.runtime or "").strip()
        configured_slot = bool(runtime)
        if configured_slot:
            configured += 1
        result = dict(preflight_results.get(slot.slot_id) or {})
        ok = bool(result.get("ok"))
        status = str(result.get("status") or ("not_configured" if not configured_slot else "not_run"))
        if ok:
            ready += 1
            status = "ready"
        elif not configured_slot and slot.required:
            missing_required.append(slot.slot_id)
        elif configured_slot and slot.required:
            failed_required.append(slot.slot_id)
        rows.append(
            {
                "slot_id": slot.slot_id,
                "role_id": slot.role_id,
                "purpose": slot.purpose,
                "runtime": runtime or None,
                "adapter": slot.adapter,
                "required": slot.required,
                "timeout_seconds": slot.timeout_seconds,
                "configured": configured_slot,
                "ready": ok,
                "status": status,
                "reason": result.get("reason"),
                "metadata": dict(result.get("metadata") or {}),
            }
        )
    blocking = [*missing_required, *failed_required]
    return {
        "schema": "agent_runtime_readiness_summary.v1",
        "ready": not blocking,
        "status": "ready" if not blocking else "blocked",
        "slots": rows,
        "summary": {
            "slots": len(rows),
            "configured_slots": configured,
            "ready_slots": ready,
            "required_slots": sum(1 for slot in slots if slot.required),
            "missing_required_slots": missing_required,
            "failed_required_slots": failed_required,
        },
    }


def _agent_adapter_specs(*, include_non_cli: bool) -> tuple[AgentAdapterSpec, ...]:
    if include_non_cli:
        return (
            *AGENT_ADAPTER_SPECS,
            CUSTOM_PLANNER_COMMAND_SPEC,
            API_MODEL_CALL_SPEC,
        )
    return AGENT_ADAPTER_SPECS


def infer_agent_adapter(agent_cli: str, requested: str = "auto") -> str:
    """Resolve the runtime adapter for a CLI command."""

    if requested != "auto":
        if requested not in AGENT_ADAPTERS:
            raise ValueError(f"unsupported agent adapter: {requested}")
        return requested
    name = Path(agent_cli).name.lower()
    if name == "codex":
        return "codex_exec"
    return "claude_print"


def infer_subscription_runtime_from_adapter(adapter: str) -> str | None:
    if adapter == "claude_print":
        return "claude"
    if adapter == "codex_exec":
        return "codex"
    return None


def agent_subprocess_env(
    env: Mapping[str, str] | None = None,
    *,
    runtime: str | None = None,
    prefer_subscription_auth: bool | None = None,
    scrub_subscription_auth: bool | None = None,
) -> dict[str, str]:
    """Build an environment for subscription/local agent subprocesses.

    By default, provider API keys are removed for known subscription CLIs so
    Claude/Codex prefer local subscription/OAuth/token state. Token-shaped auth
    such as ``ANTHROPIC_AUTH_TOKEN`` is preserved.
    """

    base = dict(os.environ if env is None else env)
    _absolutize_pythonpath(base)
    if scrub_subscription_auth is not None:
        prefer_subscription_auth = scrub_subscription_auth
    if prefer_subscription_auth is None:
        prefer_subscription_auth = not _truthy(
            base.get("COGNITIVE_FIRM_AGENT_ALLOW_API_KEY_AUTH", "")
        )
    if prefer_subscription_auth:
        runtime_name = (runtime or "").strip().lower()
        if runtime_name == "claude":
            for key in CLAUDE_API_AUTH_ENV:
                base.pop(key, None)
        elif runtime_name == "codex":
            for key in CODEX_API_AUTH_ENV:
                base.pop(key, None)
        if _truthy(base.get("COGNITIVE_FIRM_AGENT_SCRUB_ALL_MODEL_API_KEYS", "")):
            _scrub_all_model_api_keys(base)
    return base


def redact_prompt_text(text: str, prompt: str, replacement: str = "{prompt}") -> str:
    """Redact prompt text from stdout/stderr previews and command metadata."""

    if not text or not prompt:
        return text
    return text.replace(prompt, replacement)


def extract_agent_session_id(runtime: str, stdout: str, stderr: str) -> str | None:
    """Extract a reported CLI session id from captured output when available."""

    text = f"{stdout}\n{stderr}"
    if runtime == "codex":
        match = re.search(
            r"^\s*session id:\s*([A-Za-z0-9_-]+)\s*$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        return match.group(1) if match else None
    if runtime == "claude":
        for pattern in (
            r"^\s*session(?:\s+id)?:\s*([A-Za-z0-9_-]+)\s*$",
            r"^\s*conversation(?:\s+id)?:\s*([A-Za-z0-9_-]+)\s*$",
        ):
            match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1)
    return None


def _absolutize_pythonpath(env: dict[str, str]) -> None:
    pythonpath = env.get("PYTHONPATH")
    if not pythonpath:
        return
    env["PYTHONPATH"] = os.pathsep.join(
        os.path.abspath(part) if part and not os.path.isabs(part) else part
        for part in pythonpath.split(os.pathsep)
    )


def _scrub_all_model_api_keys(base: dict[str, str]) -> None:
    for key in CLAUDE_API_AUTH_ENV + CODEX_API_AUTH_ENV + OPTIONAL_MODEL_API_AUTH_ENV:
        base.pop(key, None)


def build_agent_command(
    *,
    agent_cli: str,
    adapter: str,
    prompt: str,
    project_root: Path | str,
    claude_session_id: str | None = None,
    claude_session_is_new: bool = False,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    return build_agent_invocation(
        agent_cli=agent_cli,
        adapter=adapter,
        prompt=prompt,
        project_root=project_root,
        claude_session_id=claude_session_id,
        claude_session_is_new=claude_session_is_new,
        env=env,
    ).argv


def build_agent_invocation(
    *,
    agent_cli: str,
    adapter: str,
    prompt: str,
    project_root: Path | str,
    claude_session_id: str | None = None,
    claude_session_is_new: bool = False,
    env: Mapping[str, str] | None = None,
) -> AgentInvocation:
    """Build a noninteractive command for a configured role runtime.

    Environment knobs:
    - ``COGNITIVE_FIRM_CLAUDE_PERMISSION_MODE``: Claude Code permission mode.
    - ``COGNITIVE_FIRM_CLAUDE_ALLOWED_TOOLS``: comma/space-separated tool allowlist.
    - ``COGNITIVE_FIRM_CLAUDE_DISALLOWED_TOOLS``: comma/space-separated tool denylist.
    - ``COGNITIVE_FIRM_CLAUDE_ADD_DIRS``: pathsep-separated extra readable dirs.
    - ``COGNITIVE_FIRM_CLAUDE_EXTRA_ARGS``: shlex-split extra Claude args.
    - ``COGNITIVE_FIRM_CODEX_SANDBOX``: Codex sandbox, default workspace-write.
    - ``COGNITIVE_FIRM_CODEX_BYPASS_SANDBOX``: explicit opt-in to Codex bypass flag.
    - ``COGNITIVE_FIRM_CODEX_PROFILE`` / ``COGNITIVE_FIRM_CODEX_MODEL``.
    - ``COGNITIVE_FIRM_CODEX_EXTRA_ARGS``: shlex-split extra Codex args.
    """

    runtime_env = os.environ if env is None else env
    command_project_root = Path(project_root).expanduser().resolve()
    prompt_transport = runtime_env.get(
        "COGNITIVE_FIRM_AGENT_PROMPT_TRANSPORT",
        "auto",
    ).strip().lower()
    if prompt_transport not in {"auto", "argv", "stdin"}:
        raise ValueError(f"unsupported agent prompt transport: {prompt_transport}")
    if adapter == "claude_print":
        resolved_prompt_transport = (
            "argv" if prompt_transport == "auto" else prompt_transport
        )
        permission_mode = runtime_env.get(
            "COGNITIVE_FIRM_CLAUDE_PERMISSION_MODE",
            "acceptEdits",
        )
        cmd = [agent_cli, "--print", "--permission-mode", permission_mode]
        for extra_dir in _split_path_list(
            runtime_env.get("COGNITIVE_FIRM_CLAUDE_ADD_DIRS", "")
        ):
            cmd.extend(["--add-dir", extra_dir])
        allowed_tools = runtime_env.get("COGNITIVE_FIRM_CLAUDE_ALLOWED_TOOLS")
        if allowed_tools:
            cmd.extend(["--allowedTools", allowed_tools])
        disallowed_tools = runtime_env.get("COGNITIVE_FIRM_CLAUDE_DISALLOWED_TOOLS")
        if disallowed_tools:
            cmd.extend(["--disallowedTools", disallowed_tools])
        cmd.extend(shlex.split(runtime_env.get("COGNITIVE_FIRM_CLAUDE_EXTRA_ARGS", "")))
        if claude_session_id:
            if claude_session_is_new:
                cmd.extend(["--session-id", claude_session_id])
            else:
                cmd.extend(["--resume", claude_session_id])
        if resolved_prompt_transport == "argv":
            cmd.append(prompt)
            return AgentInvocation(argv=cmd, stdin=None, prompt_transport="argv")
        return AgentInvocation(argv=cmd, stdin=prompt, prompt_transport="stdin")
    if adapter == "codex_exec":
        resolved_prompt_transport = (
            "stdin" if prompt_transport == "auto" else prompt_transport
        )
        cmd = [agent_cli, "exec", "--cd", str(command_project_root)]
        if runtime_env.get("COGNITIVE_FIRM_CODEX_BYPASS_SANDBOX"):
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            sandbox = runtime_env.get("COGNITIVE_FIRM_CODEX_SANDBOX", "workspace-write")
            cmd.extend(["--sandbox", sandbox])
        profile = runtime_env.get("COGNITIVE_FIRM_CODEX_PROFILE")
        if profile:
            cmd.extend(["--profile", profile])
        model = runtime_env.get("COGNITIVE_FIRM_CODEX_MODEL")
        if model:
            cmd.extend(["--model", model])
        cmd.extend(shlex.split(runtime_env.get("COGNITIVE_FIRM_CODEX_EXTRA_ARGS", "")))
        if resolved_prompt_transport == "argv":
            cmd.append(prompt)
            return AgentInvocation(argv=cmd, stdin=None, prompt_transport="argv")
        cmd.append("-")
        return AgentInvocation(argv=cmd, stdin=prompt, prompt_transport="stdin")
    raise ValueError(f"unsupported agent adapter: {adapter}")


def safe_command_for_receipt(command: list[str], *, prompt: str) -> list[str]:
    """Redact prompt content from command metadata while preserving flags."""

    return ["{prompt}" if arg == prompt else arg for arg in command]


def build_agent_invocation_receipt(
    *,
    command_argv: list[str],
    prompt: str,
    runtime: str | None,
    adapter: str | None,
    prompt_transport: str | None,
    returncode: int | None,
    stdout: str = "",
    stderr: str = "",
    used_prompt_file: bool = False,
    timeout_seconds: int | float | None = None,
    prompt_mode: str | None = None,
    error: str | None = None,
    stdout_preview_chars: int = 1000,
    stderr_preview_chars: int = 1000,
) -> dict[str, Any]:
    """Build a provider-neutral receipt for a spawned agent CLI invocation.

    The receipt is intentionally a local evidence carrier. It does not execute
    the command, grant authority, update run state, approve output, or decide
    whether an action succeeded. Callers can embed the returned dict in daemon
    logs, planner receipts, action-attestation metadata, or governed bundles.
    """

    runtime_name = (runtime or "").strip() or None
    adapter_name = (adapter or "").strip() or None
    safe_argv = safe_command_for_receipt(command_argv, prompt=prompt)
    stdout_text = stdout or ""
    stderr_text = stderr or ""
    receipt: dict[str, Any] = {
        "schema_version": AGENT_INVOCATION_RECEIPT_SCHEMA,
        "runtime": runtime_name,
        "adapter": adapter_name,
        "command_argv": safe_argv,
        "prompt_transport": prompt_transport,
        "prompt_digest": _digest_text(prompt or ""),
        "stdout_digest": _digest_text(stdout_text),
        "stderr_digest": _digest_text(stderr_text),
        "stdout_preview": redact_prompt_text(stdout_text[-stdout_preview_chars:], prompt),
        "stderr_preview": redact_prompt_text(stderr_text[-stderr_preview_chars:], prompt),
        "returncode": returncode,
        "used_prompt_file": used_prompt_file,
    }
    if prompt_mode is not None:
        receipt["prompt_mode"] = prompt_mode
    if timeout_seconds is not None:
        receipt["timeout_seconds"] = timeout_seconds
    if error is not None:
        receipt["error"] = error
    subscription_runtime = (
        infer_subscription_runtime_from_adapter(adapter_name)
        if adapter_name is not None
        else None
    )
    if subscription_runtime is not None:
        session_id = extract_agent_session_id(
            subscription_runtime,
            stdout_text,
            stderr_text,
        )
        if session_id is not None:
            receipt["agent_session_id"] = session_id
    return receipt


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _split_path_list(value: str) -> list[str]:
    if not value:
        return []
    return [part for part in value.split(os.pathsep) if part]


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect cognitive-firm local/subscription agent invocation policy.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    list_parser = sub.add_parser("list-adapters")
    list_parser.add_argument(
        "--cli-only",
        action="store_true",
        help="only show first-party subscription/local CLI adapters",
    )
    args = parser.parse_args(argv)
    if args.cmd == "list-adapters":
        print(
            json.dumps(
                list_agent_adapter_specs(include_non_cli=not args.cli_only),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
