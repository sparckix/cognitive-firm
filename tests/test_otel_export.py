from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.otel_export import write_otel_projection  # noqa: E402
from cognitive_firm.orchestration.run_checkpoints import append_checkpoint, start_run  # noqa: E402


def test_run_projection_exports_otel_genai_shape(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    run = start_run(
        owner_role="role.manager",
        objective="run governed workflow",
        tenant_id="tenant-a",
        project_id="project-a",
        idempotency_key="runtime:demo:1",
        log_path=log,
    )
    append_checkpoint(
        run.run_id,
        actor="role.manager",
        step_id="tool.linear.list_projects",
        status="completed",
        summary="listed projects",
        payload_ref="mcp://linear/list_projects/1",
        side_effect_key="linear:list_projects:1",
        log_path=log,
    )

    span = write_otel_projection(output_path=tmp_path / "otel.json", log_path=log)[0]

    payload = span.as_dict()
    assert payload["attributes"]["gen_ai.operation.name"] == "agent_run"
    assert payload["attributes"]["gen_ai.agent.name"] == "role.manager"
    assert payload["attributes"]["cognitive_firm.tenant_id"] == "tenant-a"
    assert payload["events"][0]["attributes"]["cognitive_firm.step_id"] == "tool.linear.list_projects"
    assert payload["status"] == "unset"
    assert (tmp_path / "otel.json").exists()
