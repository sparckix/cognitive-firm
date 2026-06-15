from __future__ import annotations

import json
import sys

from demos.self_evolving_org.agent_preflight import (
    main,
    run_live_demo_readiness,
    run_preflight,
)


def test_self_evolving_agent_preflight_accepts_ready_runtime(tmp_path, capsys):
    runtime = tmp_path / "runtime.py"
    runtime.write_text(
        f"""#!{sys.executable}
import json
import sys
prompt = sys.argv[-1]
assert "agent_preflight" in prompt
assert "--permission-mode" in sys.argv
print(json.dumps({{"ok": True, "kind": "agent_preflight"}}))
""",
        encoding="utf-8",
    )
    runtime.chmod(0o755)

    result = run_preflight(
        agent_runtime=str(runtime),
        agent_adapter="claude_print",
        project_root=tmp_path,
        timeout_seconds=5,
    )

    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["metadata"]["prompt_transport"] == "argv"
    assert result["metadata"]["command_argv"][0] == str(runtime)
    assert "agent_preflight" not in json.dumps(result["metadata"]["command_argv"])

    assert main(
        [
            "--agent-runtime",
            str(runtime),
            "--agent-adapter",
            "claude_print",
            "--project-root",
            str(tmp_path),
            "--timeout-seconds",
            "5",
        ]
    ) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True


def test_self_evolving_agent_preflight_summarizes_live_demo_slots(tmp_path, capsys):
    runtime = tmp_path / "runtime.py"
    runtime.write_text(
        f"""#!{sys.executable}
import json
print(json.dumps({{"ok": True, "kind": "agent_preflight"}}))
""",
        encoding="utf-8",
    )
    runtime.chmod(0o755)

    summary = run_live_demo_readiness(
        planner_runtime=str(runtime),
        planner_adapter="claude_print",
        reviewer_runtime=str(runtime),
        reviewer_adapter="claude_print",
        workload_executor_runtime=None,
        project_root=tmp_path,
        timeout_seconds=5,
        reviewer_timeout_seconds=6,
    )

    assert summary["schema"] == "agent_runtime_readiness_summary.v1"
    assert summary["ready"] is True
    slots = {slot["slot_id"]: slot for slot in summary["slots"]}
    assert slots["planner"]["ready"] is True
    assert slots["planner"]["required"] is True
    assert slots["reviewer"]["ready"] is True
    assert slots["reviewer"]["required"] is False
    assert slots["reviewer"]["timeout_seconds"] == 6
    assert slots["workload_executor"]["configured"] is False
    assert slots["workload_executor"]["ready"] is False
    assert summary["summary"]["configured_slots"] == 2
    assert summary["summary"]["ready_slots"] == 2

    assert (
        main(
            [
                "--agent-runtime",
                str(runtime),
                "--agent-adapter",
                "claude_print",
                "--agent-reviewer-runtime",
                str(runtime),
                "--agent-reviewer-adapter",
                "claude_print",
                "--readiness-summary",
                "--project-root",
                str(tmp_path),
                "--timeout-seconds",
                "5",
            ]
        )
        == 0
    )
    printed = json.loads(capsys.readouterr().out)
    assert printed["schema"] == "agent_runtime_readiness_summary.v1"
    assert printed["ready"] is True


def test_self_evolving_agent_preflight_classifies_runtime_init_failure(tmp_path):
    runtime = tmp_path / "runtime.py"
    runtime.write_text(
        f"""#!{sys.executable}
import sys
print("Error: failed to initialize in-process app-server client", file=sys.stderr)
raise SystemExit(1)
""",
        encoding="utf-8",
    )
    runtime.chmod(0o755)

    result = run_preflight(
        agent_runtime=str(runtime),
        agent_adapter="claude_print",
        project_root=tmp_path,
        timeout_seconds=5,
    )
    assert result["ok"] is False
    assert result["status"] == "runtime_failed"
    assert result["reason"] == "agent runtime initialization failed"


def test_self_evolving_agent_preflight_records_timeout(tmp_path):
    runtime = tmp_path / "runtime.py"
    runtime.write_text(
        f"""#!{sys.executable}
import time
time.sleep(10)
""",
        encoding="utf-8",
    )
    runtime.chmod(0o755)

    result = run_preflight(
        agent_runtime=str(runtime),
        agent_adapter="claude_print",
        project_root=tmp_path,
        timeout_seconds=1,
    )
    assert result["ok"] is False
    assert result["status"] == "timed_out"
    assert result["metadata"]["timeout_seconds"] == 1
