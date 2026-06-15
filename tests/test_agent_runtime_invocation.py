from __future__ import annotations

from cognitive_firm.orchestration.agent_runtime_invocation import (
    AGENT_INVOCATION_RECEIPT_SCHEMA,
    AgentRuntimeSlot,
    build_agent_invocation_receipt,
    build_agent_runtime_readiness_summary,
    get_agent_adapter_spec,
    list_agent_adapter_specs,
    main,
)


def test_agent_invocation_receipt_redacts_prompt_and_records_digests() -> None:
    prompt = "secret planner prompt"

    receipt = build_agent_invocation_receipt(
        command_argv=["claude", "--print", prompt],
        prompt=prompt,
        runtime="claude",
        adapter="claude_print",
        prompt_transport="argv",
        returncode=0,
        stdout='{"steps": []}\nsession id: claude-session-1\n',
        stderr=f"warning without {prompt}",
        prompt_mode="compact",
    )

    assert receipt["schema_version"] == AGENT_INVOCATION_RECEIPT_SCHEMA
    assert receipt["runtime"] == "claude"
    assert receipt["adapter"] == "claude_print"
    assert receipt["command_argv"] == ["claude", "--print", "{prompt}"]
    assert receipt["prompt_digest"].startswith("sha256:")
    assert receipt["stdout_digest"].startswith("sha256:")
    assert receipt["stderr_digest"].startswith("sha256:")
    assert prompt not in receipt["stderr_preview"]
    assert "{prompt}" in receipt["stderr_preview"]
    assert receipt["agent_session_id"] == "claude-session-1"


def test_agent_invocation_receipt_preserves_prompt_file_redaction() -> None:
    receipt = build_agent_invocation_receipt(
        command_argv=["/tmp/planner", "{prompt_file}"],
        prompt="prompt text that never appears in argv",
        runtime=None,
        adapter=None,
        prompt_transport=None,
        returncode=None,
        stderr="missing planner",
        used_prompt_file=True,
        error="planner command not found",
    )

    assert receipt["command_argv"] == ["/tmp/planner", "{prompt_file}"]
    assert receipt["used_prompt_file"] is True
    assert receipt["returncode"] is None
    assert receipt["error"] == "planner command not found"
    assert "agent_session_id" not in receipt


def test_agent_adapter_registry_lists_subscription_cli_and_fallback_shapes() -> None:
    specs = {row["adapter"]: row for row in list_agent_adapter_specs()}

    assert specs["claude_print"]["worker_shape"] == "subscription_cli"
    assert specs["claude_print"]["runtime"] == "claude"
    assert specs["codex_exec"]["worker_shape"] == "subscription_cli"
    assert specs["codex_exec"]["prompt_transport_default"] == "stdin"
    assert specs["custom_planner_command"]["worker_shape"] == "local_wrapper"
    assert specs["api_model_call"]["worker_shape"] == "api_model_call"
    assert "DeepSeek" in specs["api_model_call"]["notes"]


def test_agent_adapter_registry_can_filter_to_first_party_cli_shapes() -> None:
    specs = list_agent_adapter_specs(include_non_cli=False)

    assert [row["adapter"] for row in specs] == ["claude_print", "codex_exec"]
    assert all(row["worker_shape"] == "subscription_cli" for row in specs)
    assert get_agent_adapter_spec("custom_planner_command") is not None
    assert get_agent_adapter_spec("missing") is None


def test_agent_adapter_registry_cli_outputs_json(capsys) -> None:
    assert main(["list-adapters", "--cli-only"]) == 0

    out = capsys.readouterr().out
    assert '"adapter": "claude_print"' in out
    assert '"adapter": "codex_exec"' in out
    assert "custom_planner_command" not in out


def test_agent_runtime_readiness_summary_blocks_missing_required_slot() -> None:
    summary = build_agent_runtime_readiness_summary(
        slots=[
            AgentRuntimeSlot(
                slot_id="planner",
                role_id="role.org_evolver",
                purpose="propose mutations",
                runtime=None,
                adapter="auto",
                required=True,
            ),
            AgentRuntimeSlot(
                slot_id="reviewer",
                role_id="role.evaluator",
                purpose="review proposals",
                runtime="claude",
                adapter="claude_print",
                required=False,
                timeout_seconds=30,
            ),
        ],
        preflight_results={
            "reviewer": {
                "ok": True,
                "status": "ready",
                "reason": "ok",
                "metadata": {"prompt_digest": "sha256:" + "a" * 64},
            }
        },
    )

    assert summary["schema"] == "agent_runtime_readiness_summary.v1"
    assert summary["ready"] is False
    assert summary["status"] == "blocked"
    assert summary["summary"] == {
        "slots": 2,
        "configured_slots": 1,
        "ready_slots": 1,
        "required_slots": 1,
        "missing_required_slots": ["planner"],
        "failed_required_slots": [],
    }
    assert summary["slots"][0]["status"] == "not_configured"
    assert summary["slots"][1]["ready"] is True


def test_agent_runtime_readiness_summary_blocks_failed_required_slot() -> None:
    summary = build_agent_runtime_readiness_summary(
        slots=[
            AgentRuntimeSlot(
                slot_id="planner",
                role_id="role.org_evolver",
                purpose="propose mutations",
                runtime="codex",
                adapter="codex_exec",
                required=True,
            )
        ],
        preflight_results={
            "planner": {
                "ok": False,
                "status": "runtime_failed",
                "reason": "not logged in",
            }
        },
    )

    assert summary["ready"] is False
    assert summary["summary"]["failed_required_slots"] == ["planner"]
    assert summary["slots"][0]["status"] == "runtime_failed"
