from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts import agent_daemon
from cognitive_firm.orchestration.agent_runtime_invocation import (
    agent_subprocess_env,
    build_agent_invocation,
)


def test_resolve_daemon_roots_defaults_org_and_workspace_under_project(tmp_path: Path) -> None:
    project_root = tmp_path / "demo-firm"

    roots = agent_daemon.resolve_daemon_roots(project_root=project_root)

    assert roots.project_root == project_root.resolve()
    assert roots.org_root == (project_root / "org").resolve()
    assert roots.workspace_root == (project_root / "cognitive_firm_workspace").resolve()


def test_codex_command_uses_target_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "demo-firm"

    cmd = agent_daemon.build_agent_command(
        agent_cli="codex",
        adapter="codex_exec",
        prompt="do governed work",
        project_root=project_root,
    )

    assert cmd[0:2] == ["codex", "exec"]
    assert cmd[cmd.index("--cd") + 1] == str(project_root.resolve())
    assert "--ask-for-approval" not in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"


def test_claude_command_uses_target_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "demo-firm"

    cmd = agent_daemon.build_agent_command(
        agent_cli="claude",
        adapter="claude_print",
        prompt="do governed work",
        project_root=project_root,
    )

    assert cmd[0:2] == ["claude", "--print"]
    assert "--project" not in cmd
    assert cmd[-1] == "do governed work"

    invocation = build_agent_invocation(
        agent_cli="claude",
        adapter="claude_print",
        prompt="do governed work",
        project_root=project_root,
    )
    assert invocation.stdin is None
    assert invocation.prompt_transport == "argv"


def test_agent_command_honors_permission_env_knobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "demo-firm"
    monkeypatch.setenv("COGNITIVE_FIRM_CLAUDE_PERMISSION_MODE", "bypassPermissions")
    monkeypatch.setenv("COGNITIVE_FIRM_CLAUDE_ALLOWED_TOOLS", "Bash(git *),Edit")
    monkeypatch.setenv("COGNITIVE_FIRM_CLAUDE_EXTRA_ARGS", "--model sonnet")

    cmd = agent_daemon.build_agent_command(
        agent_cli="claude",
        adapter="claude_print",
        prompt="do governed work",
        project_root=project_root,
    )

    assert cmd[cmd.index("--permission-mode") + 1] == "bypassPermissions"
    assert cmd[cmd.index("--allowedTools") + 1] == "Bash(git *),Edit"
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[-1] == "do governed work"


def test_codex_command_honors_sandbox_and_bypass_env_knobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "demo-firm"
    monkeypatch.setenv("COGNITIVE_FIRM_CODEX_SANDBOX", "read-only")
    monkeypatch.setenv("COGNITIVE_FIRM_CODEX_MODEL", "gpt-5-codex")

    cmd = agent_daemon.build_agent_command(
        agent_cli="codex",
        adapter="codex_exec",
        prompt="do governed work",
        project_root=project_root,
    )

    assert cmd[cmd.index("--sandbox") + 1] == "read-only"
    assert cmd[cmd.index("--model") + 1] == "gpt-5-codex"
    assert "--dangerously-bypass-approvals-and-sandbox" not in cmd

    monkeypatch.setenv("COGNITIVE_FIRM_CODEX_BYPASS_SANDBOX", "1")
    cmd = agent_daemon.build_agent_command(
        agent_cli="codex",
        adapter="codex_exec",
        prompt="do governed work",
        project_root=project_root,
    )
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert "--sandbox" not in cmd


def test_agent_command_can_force_stdin_prompt_transport_for_wrappers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "demo-firm"
    monkeypatch.setenv("COGNITIVE_FIRM_AGENT_PROMPT_TRANSPORT", "stdin")

    invocation = build_agent_invocation(
        agent_cli="claude",
        adapter="claude_print",
        prompt="do governed work",
        project_root=project_root,
    )

    assert invocation.stdin == "do governed work"
    assert invocation.prompt_transport == "stdin"
    assert invocation.argv[-1] != "do governed work"


def test_agent_subprocess_env_prefers_claude_subscription_auth_by_default() -> None:
    env = {
        "ANTHROPIC_API_KEY": "anthropic",
        "ANTHROPIC_AUTH_TOKEN": "subscription-token",
        "OPENAI_API_KEY": "openai",
        "GEMINI_API_KEY": "gemini",
        "DEEPSEEK_API_KEY": "deepseek",
        "OPENAI_COMPATIBLE_API_KEY": "local",
        "PYTHONPATH": "src:/already/abs",
        "PATH": "/bin",
    }

    subprocess_env = agent_subprocess_env(env, runtime="claude")

    assert "ANTHROPIC_API_KEY" not in subprocess_env
    assert subprocess_env["ANTHROPIC_AUTH_TOKEN"] == "subscription-token"
    assert subprocess_env["OPENAI_API_KEY"] == "openai"
    assert subprocess_env["GEMINI_API_KEY"] == "gemini"
    assert subprocess_env["DEEPSEEK_API_KEY"] == "deepseek"
    assert subprocess_env["OPENAI_COMPATIBLE_API_KEY"] == "local"
    assert os.path.isabs(subprocess_env["PYTHONPATH"].split(os.pathsep)[0])
    assert subprocess_env["PYTHONPATH"].split(os.pathsep)[1] == "/already/abs"


def test_agent_subprocess_env_prefers_codex_subscription_auth_by_default() -> None:
    env = {
        "ANTHROPIC_API_KEY": "anthropic",
        "OPENAI_API_KEY": "openai",
        "OPENAI_BASE_URL": "https://api.openai.test/v1",
        "OPENAI_ORG_ID": "org",
        "GEMINI_API_KEY": "gemini",
        "DEEPSEEK_API_KEY": "deepseek",
        "OPENAI_COMPATIBLE_API_KEY": "local",
        "PATH": "/bin",
    }

    subprocess_env = agent_subprocess_env(env, runtime="codex")

    assert subprocess_env["ANTHROPIC_API_KEY"] == "anthropic"
    assert "OPENAI_API_KEY" not in subprocess_env
    assert "OPENAI_BASE_URL" not in subprocess_env
    assert "OPENAI_ORG_ID" not in subprocess_env
    assert subprocess_env["GEMINI_API_KEY"] == "gemini"
    assert subprocess_env["DEEPSEEK_API_KEY"] == "deepseek"
    assert subprocess_env["OPENAI_COMPATIBLE_API_KEY"] == "local"


def test_agent_subprocess_env_can_allow_api_key_auth() -> None:
    env = {
        "ANTHROPIC_API_KEY": "anthropic",
        "COGNITIVE_FIRM_AGENT_ALLOW_API_KEY_AUTH": "1",
        "PATH": "/bin",
    }

    subprocess_env = agent_subprocess_env(env, runtime="claude")

    assert subprocess_env["ANTHROPIC_API_KEY"] == "anthropic"


def test_agent_subprocess_env_can_scrub_all_model_api_keys() -> None:
    env = {
        "ANTHROPIC_API_KEY": "anthropic",
        "OPENAI_API_KEY": "openai",
        "GEMINI_API_KEY": "gemini",
        "DEEPSEEK_API_KEY": "deepseek",
        "OPENAI_COMPATIBLE_API_KEY": "local",
        "COGNITIVE_FIRM_AGENT_SCRUB_ALL_MODEL_API_KEYS": "1",
        "PATH": "/bin",
    }

    subprocess_env = agent_subprocess_env(env, runtime="claude")

    assert subprocess_env == {
        "COGNITIVE_FIRM_AGENT_SCRUB_ALL_MODEL_API_KEYS": "1",
        "PATH": "/bin",
    }


def test_bootstrap_prompt_reads_target_org_manifest(tmp_path: Path) -> None:
    project_root = tmp_path / "demo-firm"
    org_root = project_root / "org"
    (org_root / "roles").mkdir(parents=True)
    (org_root / "mandates").mkdir(parents=True)
    (org_root / "bootstrap_manifest.yaml").write_text(
        """
required_reads:
  - path: "org/roles/{role_id}.yaml"
    purpose: "role contract"
  - path: "org/mandates/{role_id}_mandate.md"
    purpose: "role mandate"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    prompt = agent_daemon._format_bootstrap_chain_for_prompt(
        role_id="org_evolver",
        project_root=project_root,
        org_root=org_root,
    )

    assert "org/roles/org_evolver.yaml" in prompt
    assert "org/mandates/org_evolver_mandate.md" in prompt


def test_org_root_env_drives_sessions_and_authorization(tmp_path: Path) -> None:
    org_root = tmp_path / "demo-firm" / "org"
    (org_root / "roles").mkdir(parents=True)
    (org_root / "mandates").mkdir(parents=True)
    (org_root / "roles" / "org_evolver.yaml").write_text(
        """
role_id: org_evolver
authorized_paths:
  - org/**
forbidden_paths:
  - .env
budget:
  single_action_cap_usd: 1.0
""".strip()
        + "\n",
        encoding="utf-8",
    )
    mandate_path = org_root / "mandates" / "org_evolver_mandate.md"
    mandate_path.write_text("# Org Evolver Mandate\n", encoding="utf-8")
    code = f"""
import json
from pathlib import Path
from cognitive_firm.sessions.enforce import ensure_session
from cognitive_firm.orchestration.task_authorization import authorize_dispatch

org_root = Path({str(org_root)!r})
session = ensure_session(
    role_id="org_evolver",
    member_id="codex",
    substrate="daemon",
    mandate_path=org_root / "mandates" / "org_evolver_mandate.md",
)
decision = authorize_dispatch(
    role_id="org_evolver",
    candidate_source="principal-goal",
    candidate_text="Update `org/mandates/org_evolver_mandate.md`.",
    metadata={{
        "autonomous_scope_ok": True,
        "estimated_cost_usd": 0.0,
        "declared_paths": ["org/mandates/org_evolver_mandate.md"],
    }},
    unattended=True,
)
print(json.dumps({{
    "session_dir": str(session.directory),
    "authorized": decision.allowed,
    "reason": decision.reason,
}}))
"""
    env = dict(os.environ)
    env["ORG_ROOT"] = str(org_root)
    env["PYTHONPATH"] = "src"

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["session_dir"].startswith(str(org_root / "sessions"))
    assert payload["authorized"] is True, payload["reason"]
