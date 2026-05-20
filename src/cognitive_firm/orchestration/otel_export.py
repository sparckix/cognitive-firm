"""OpenTelemetry GenAI-shaped projection.

The kernel event log remains the source of organizational truth. This module
projects run checkpoints into span-shaped dictionaries that can be exported by a
deployment-specific OpenTelemetry adapter.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cognitive_firm.orchestration.run_checkpoints import RunProjection, list_runs


@dataclass(frozen=True)
class OTelSpanProjection:
    name: str
    span_kind: str
    status: str = "unset"
    start_time: str | None = None
    end_time: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "span_kind": self.span_kind,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "attributes": self.attributes,
            "events": self.events,
        }


def run_to_otel_span(run: RunProjection) -> OTelSpanProjection:
    """Project one run into an OpenTelemetry GenAI-compatible span shape."""
    attrs: dict[str, Any] = {
        "gen_ai.operation.name": "agent_run",
        "gen_ai.agent.name": run.owner_role,
        "cognitive_firm.run_id": run.run_id,
        "cognitive_firm.run.state": run.state,
        "cognitive_firm.objective": run.objective,
    }
    if run.tenant_id:
        attrs["cognitive_firm.tenant_id"] = run.tenant_id
    if run.project_id:
        attrs["cognitive_firm.project_id"] = run.project_id
    if run.idempotency_key:
        attrs["cognitive_firm.idempotency_key"] = run.idempotency_key
    if run.failure_reason:
        attrs["cognitive_firm.failure_reason"] = run.failure_reason

    events = [
        {
            "name": "cognitive_firm.checkpoint",
            "attributes": {
                "cognitive_firm.step_id": checkpoint.get("step_id"),
                "cognitive_firm.checkpoint.status": checkpoint.get("status"),
                "cognitive_firm.checkpoint.summary": checkpoint.get("summary"),
                "cognitive_firm.payload_ref": checkpoint.get("payload_ref"),
                "cognitive_firm.side_effect_key": checkpoint.get("side_effect_key"),
                "cognitive_firm.event_id": checkpoint.get("event_id"),
            },
            "timestamp": checkpoint.get("ts"),
        }
        for checkpoint in run.checkpoints
    ]
    timestamps = [str(item.get("ts")) for item in run.checkpoints if item.get("ts")]
    return OTelSpanProjection(
        name=f"cognitive_firm.run {run.run_id}",
        span_kind="internal",
        status=_span_status(run.state),
        start_time=timestamps[0] if timestamps else None,
        end_time=timestamps[-1] if timestamps and run.state in {"completed", "failed", "cancelled"} else None,
        attributes=attrs,
        events=events,
    )


def _span_status(run_state: str) -> str:
    if run_state == "completed":
        return "ok"
    if run_state in {"failed", "cancelled"}:
        return "error"
    return "unset"


def runs_to_otel_spans(*, log_path: Path | None = None) -> list[OTelSpanProjection]:
    return [run_to_otel_span(run) for run in list_runs(log_path=log_path)]


def write_otel_projection(
    *,
    output_path: Path,
    log_path: Path | None = None,
) -> list[OTelSpanProjection]:
    spans = runs_to_otel_spans(log_path=log_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump([span.as_dict() for span in spans], handle, indent=2, sort_keys=True)
        handle.write("\n")
    return spans


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project run checkpoints to OTel GenAI-shaped spans.")
    parser.add_argument("--log-path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    spans = runs_to_otel_spans(log_path=args.log_path)
    payload = [span.as_dict() for span in spans]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
