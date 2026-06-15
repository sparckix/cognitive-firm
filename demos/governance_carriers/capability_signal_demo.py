#!/usr/bin/env python3
"""No-cost demo for typed abstention and capability routing signals."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.capability_signals import (  # noqa: E402
    capability_signal_resource,
    close_capability_signal,
    list_capability_signals,
    record_capability_signal,
    route_capability_signal,
    summarize_capability_signals,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-capability-signals-") as raw:
        log = Path(raw) / "capability_signals.jsonl"
        abstention = record_capability_signal(
            signal_kind="abstention",
            severity="warning",
            source_ref="work_item:work_demo",
            summary="Evaluator declined to verify because the source refs were missing.",
            owner_role="role.evaluator",
            worker_ref="runtime://demo/evaluator",
            run_id="run_capability_demo",
            work_id="work_demo",
            recommended_route="request_evidence",
            counts_as_failure=False,
            evidence_refs=["multi_agent_trace:mate_missing_source"],
            log_path=log,
        )
        routed = route_capability_signal(
            abstention.signal_id,
            route_kind="request_evidence",
            routed_by="role.manager",
            rationale="Missing source refs should route to evidence repair, not task failure.",
            target_ref="human_work:hws_source_receipt_request",
            log_path=log,
        )
        closed = close_capability_signal(
            routed.signal_id,
            closed_by="role.manager",
            closure_ref="human_work:hws_source_receipt",
            rationale="A receipt was attached for the missing source refs.",
            log_path=log,
        )
        authority_gap = record_capability_signal(
            signal_kind="insufficient_authority",
            severity="blocking",
            source_ref="authorization:dispatch-demo",
            summary="Executor cannot write the requested protocol path under its mandate.",
            owner_role="role.executor",
            capability_ref="capability://protocol/write",
            recommended_route="escalate_to_principal",
            counts_as_failure=False,
            log_path=log,
        )
        route_capability_signal(
            authority_gap.signal_id,
            route_kind="escalate_to_principal",
            routed_by="role.manager",
            rationale="The authority gap needs approval or reassignment.",
            target_ref="governance_change:gcp_authority_review",
            log_path=log,
        )
        signals = list_capability_signals(log_path=log)
        summary = summarize_capability_signals(signals)
        resource_errors = [
            error
            for signal in signals
            for error in validate_resource(capability_signal_resource(signal).as_dict())
        ]

    payload = {
        "demo": "capability_signal",
        "no_external_calls": True,
        "summary": {
            "signals": summary.n_signals,
            "open_signals": summary.open_signals,
            "blocking_signals": summary.blocking_signals,
            "closed_abstention": closed.status == "closed",
            "authority_gap_route": authority_gap.recommended_route,
            "abstention_counts_as_failure": abstention.counts_as_failure,
            "resource_schema_ok": not resource_errors,
            "verdict": (
                "passed"
                if summary.n_signals == 2
                and summary.blocking_signals == 1
                and closed.status == "closed"
                and abstention.counts_as_failure is False
                and not resource_errors
                else "failed"
            ),
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["summary"]["verdict"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
