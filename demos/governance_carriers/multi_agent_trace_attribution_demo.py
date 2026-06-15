#!/usr/bin/env python3
"""No-cost demo for multi-agent trace attribution carriers."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.multi_agent_trace_attribution import (  # noqa: E402
    attribution_packet_resource,
    build_delegation_graph,
    create_failure_attribution_packet,
    delegation_graph_resource,
    import_trace_events,
    learning_candidate_from_attribution_packet,
    summarize_delegation_diagnostics,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-trace-attribution-") as raw:
        root = Path(raw)
        events_log = root / "trace_events.jsonl"
        packets_log = root / "attribution_packets.jsonl"
        events = import_trace_events(
            [
                {
                    "event_id": "mate_demo_root",
                    "runtime_name": "recursive_fixture",
                    "external_run_id": "demo-self-evolution-run",
                    "cognitive_run_id": "run_demo_trace",
                    "event_kind": "agent_spawned",
                    "agent_id": "agent.org_evolver",
                    "owner_role": "role.org_evolver",
                    "summary": "org evolver began protocol-improvement review",
                },
                {
                    "event_id": "mate_demo_researcher",
                    "runtime_name": "recursive_fixture",
                    "external_run_id": "demo-self-evolution-run",
                    "cognitive_run_id": "run_demo_trace",
                    "event_kind": "agent_spawned",
                    "agent_id": "agent.researcher",
                    "parent_agent_id": "agent.org_evolver",
                    "summary": "researcher delegated evidence lookup",
                },
                {
                    "event_id": "mate_demo_handoff",
                    "runtime_name": "recursive_fixture",
                    "external_run_id": "demo-self-evolution-run",
                    "cognitive_run_id": "run_demo_trace",
                    "event_kind": "handoff",
                    "agent_id": "agent.researcher",
                    "target_agent_id": "agent.evaluator",
                    "status": "failed",
                    "summary": "handoff lacked source refs for evaluator",
                    "source_refs": ["trace://demo-self-evolution-run/researcher"],
                },
                {
                    "event_id": "mate_demo_abstention",
                    "runtime_name": "recursive_fixture",
                    "external_run_id": "demo-self-evolution-run",
                    "cognitive_run_id": "run_demo_trace",
                    "event_kind": "abstention",
                    "agent_id": "agent.evaluator",
                    "status": "abstained",
                    "summary": "evaluator abstained because evidence refs were missing",
                },
                {
                    "event_id": "mate_demo_verdict",
                    "runtime_name": "recursive_fixture",
                    "external_run_id": "demo-self-evolution-run",
                    "cognitive_run_id": "run_demo_trace",
                    "event_kind": "verifier_verdict",
                    "agent_id": "agent.risk_guardian",
                    "status": "failed",
                    "summary": "risk guardian rejected protocol update without evidence rule",
                },
            ],
            log_path=events_log,
        )
        packet = create_failure_attribution_packet(
            events=events,
            failure_summary="protocol-improvement handoff omitted required source refs",
            proposed_carrier_kind="learning_transition",
            owner_role="role.org_evolver",
            attribution_scope="interaction",
            target_ref="protocol:role-handoff-source-refs",
            proposed_transition_kind="mandate_review",
            log_path=packets_log,
        )
        candidate = learning_candidate_from_attribution_packet(packet)
        graph = build_delegation_graph(events)
        resource_errors = validate_resource(attribution_packet_resource(packet).as_dict())
        resource_errors += validate_resource(delegation_graph_resource(graph).as_dict())
        diagnostics = summarize_delegation_diagnostics(events)

    payload = {
        "demo": "multi_agent_trace_attribution",
        "no_external_calls": True,
        "summary": {
            "trace_events": len(events),
            "packet_status": packet.status,
            "packet_review_ready": packet.review_ready,
            "candidate_id": candidate.candidate_id,
            "candidate_transition_kind": candidate.transition_kind,
            "candidate_observer_only": candidate.observer_only,
            "abstentions": diagnostics.abstentions,
            "failed_handoffs": diagnostics.failed_handoffs,
            "verifier_failures": diagnostics.verifier_failures,
            "graph_nodes": len(graph.nodes),
            "graph_edges": len(graph.edges),
            "graph_max_depth": graph.diagnostics.max_depth,
            "resource_schema_ok": not resource_errors,
            "verdict": "passed" if packet.review_ready and not resource_errors else "failed",
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["summary"]["verdict"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
