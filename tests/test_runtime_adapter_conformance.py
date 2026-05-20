from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.run_checkpoints import get_run  # noqa: E402
from cognitive_firm.orchestration.runtime_adapters import RuntimeEvent, record_runtime_event  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "runtime_adapters"


def test_runtime_adapter_conformance_fixture_replays_lifecycle(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    payloads = json.loads((FIXTURES / "langgraph_lifecycle.json").read_text(encoding="utf-8"))

    results = [
        record_runtime_event(RuntimeEvent(**payload), log_path=log)
        for payload in payloads
    ]

    first_run_id = results[0]["cognitive_run_id"]
    replayed_started_id = results[-1]["cognitive_run_id"]
    projection = get_run(first_run_id, log_path=log)

    assert replayed_started_id == first_run_id
    assert projection.state == "completed"
    assert projection.tenant_id == "tenant-demo"
    assert projection.project_id == "project-demo"
    assert projection.checkpoints[0]["step_id"] == "retrieve"
    assert projection.side_effect_keys == ["fetch:source:1"]


def test_runtime_adapter_conformance_rows_embed_kernel_events(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    payload = json.loads((FIXTURES / "langgraph_lifecycle.json").read_text(encoding="utf-8"))[0]

    result = record_runtime_event(RuntimeEvent(**payload), log_path=log)
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    assert rows[0]["payload"]["run_id"] == result["cognitive_run_id"]
    assert rows[0]["kernel_event"]["verb"] == "run.started"
    assert rows[0]["kernel_event"]["tenant_id"] == "tenant-demo"
