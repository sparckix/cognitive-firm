#!/usr/bin/env python3
"""Smoke-test the framework-neutral runtime adapter surface."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from cognitive_firm.orchestration.run_checkpoints import get_run
from cognitive_firm.orchestration.runtime_adapters import RuntimeEvent, record_runtime_event


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "transitions.jsonl"
        started = record_runtime_event(
            RuntimeEvent(
                runtime_name="langgraph",
                external_run_id="demo-thread",
                kind="started",
                owner_role="role.example",
                actor="role.example",
                objective="demonstrate external runtime projection",
                project_id="example",
            ),
            log_path=log_path,
        )
        record_runtime_event(
            RuntimeEvent(
                runtime_name="langgraph",
                external_run_id="demo-thread",
                kind="checkpointed",
                owner_role="role.example",
                actor="role.example",
                step_id="node.retrieve",
                checkpoint_status="completed",
                summary="external runtime reached retrieval node",
                side_effect_key="demo:retrieve",
            ),
            log_path=log_path,
        )
        record_runtime_event(
            RuntimeEvent(
                runtime_name="langgraph",
                external_run_id="demo-thread",
                kind="state_changed",
                owner_role="role.example",
                actor="role.example",
                state="completed",
            ),
            log_path=log_path,
        )
        projection = get_run(started["cognitive_run_id"], log_path=log_path)
        print(json.dumps(projection.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
