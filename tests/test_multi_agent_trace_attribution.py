from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.multi_agent_trace_attribution import (  # noqa: E402
    attribution_packet_resource,
    build_delegation_graph,
    create_failure_attribution_packet,
    delegation_graph_resource,
    import_trace_events,
    learning_candidate_from_attribution_packet,
    list_failure_attribution_packets,
    list_trace_events,
    summarize_delegation_diagnostics,
    trace_event_resource,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


def test_imports_trace_events_and_projects_reviewable_packet(tmp_path: Path):
    events_log = tmp_path / "trace_events.jsonl"
    packets_log = tmp_path / "packets.jsonl"
    events = import_trace_events(
        [
            {
                "event_id": "mate_root",
                "runtime_name": "redel_fixture",
                "external_run_id": "run-a",
                "cognitive_run_id": "run_cf_a",
                "event_kind": "agent_spawned",
                "agent_id": "agent.root",
                "owner_role": "role.org_evolver",
                "summary": "root agent started",
            },
            {
                "event_id": "mate_child",
                "runtime_name": "redel_fixture",
                "external_run_id": "run-a",
                "cognitive_run_id": "run_cf_a",
                "event_kind": "agent_spawned",
                "agent_id": "agent.researcher",
                "parent_agent_id": "agent.root",
                "summary": "researcher delegated competitor lookup",
            },
            {
                "event_id": "mate_handoff_failed",
                "runtime_name": "redel_fixture",
                "external_run_id": "run-a",
                "cognitive_run_id": "run_cf_a",
                "event_kind": "handoff",
                "agent_id": "agent.researcher",
                "target_agent_id": "agent.evaluator",
                "status": "failed",
                "summary": "evaluator received no source refs",
                "source_refs": ["trace://run-a/researcher"],
            },
            {
                "event_id": "mate_verdict",
                "runtime_name": "redel_fixture",
                "external_run_id": "run-a",
                "cognitive_run_id": "run_cf_a",
                "event_kind": "verifier_verdict",
                "agent_id": "agent.evaluator",
                "status": "failed",
                "summary": "verification failed due missing citation",
            },
        ],
        log_path=events_log,
    )

    packet = create_failure_attribution_packet(
        events=events,
        failure_summary="researcher-to-evaluator handoff lacked source evidence",
        proposed_carrier_kind="learning_transition",
        owner_role="role.org_evolver",
        attribution_scope="interaction",
        target_ref="protocol:handoff-source-refs",
        proposed_transition_kind="mandate_review",
        log_path=packets_log,
    )

    assert len(list_trace_events(log_path=events_log)) == 4
    assert list_failure_attribution_packets(log_path=packets_log)[0].packet_id == packet.packet_id
    assert packet.status == "review_ready"
    assert packet.observer_only is True
    assert packet.diagnostics is not None
    assert packet.diagnostics.failed_handoffs == 1
    assert packet.diagnostics.verifier_failures == 1
    assert packet.local_findings
    assert packet.cross_agent_evidence

    candidate = learning_candidate_from_attribution_packet(packet)
    assert candidate.transition_kind == "mandate_review"
    assert candidate.source_kind == "multi_agent_failure_attribution"
    assert candidate.observer_only is True
    assert f"multi_agent_attribution:{packet.packet_id}" in candidate.source_refs
    assert candidate.proposed_payload["diagnostics"]["failed_handoffs"] == 1

    assert validate_resource(trace_event_resource(events[0]).as_dict()) == []
    resource = attribution_packet_resource(packet).as_dict()
    assert validate_resource(resource) == []
    assert resource["kind"] == "FailureAttributionPacket"
    assert resource["status"]["review_ready"] is True


def test_builds_delegation_graph_resource_from_trace_events(tmp_path: Path):
    events = import_trace_events(
        [
            {
                "event_id": "mate_graph_root",
                "runtime_name": "graph_fixture",
                "external_run_id": "run-graph",
                "cognitive_run_id": "run_cf_graph",
                "event_kind": "agent_spawned",
                "agent_id": "agent.root",
                "owner_role": "role.org_evolver",
            },
            {
                "event_id": "mate_graph_child",
                "runtime_name": "graph_fixture",
                "external_run_id": "run-graph",
                "cognitive_run_id": "run_cf_graph",
                "event_kind": "agent_spawned",
                "agent_id": "agent.researcher",
                "parent_agent_id": "agent.root",
            },
            {
                "event_id": "mate_graph_handoff",
                "runtime_name": "graph_fixture",
                "external_run_id": "run-graph",
                "cognitive_run_id": "run_cf_graph",
                "event_kind": "handoff",
                "agent_id": "agent.researcher",
                "target_agent_id": "agent.evaluator",
                "status": "failed",
                "summary": "evaluator received no evidence refs",
            },
        ],
        log_path=tmp_path / "graph_events.jsonl",
    )

    graph = build_delegation_graph(events)

    assert graph.runtime_name == "graph_fixture"
    assert graph.external_run_id == "run-graph"
    assert graph.cognitive_run_id == "run_cf_graph"
    assert graph.observer_only is True
    assert graph.diagnostics.failed_handoffs == 1
    assert graph.diagnostics.n_edges == 2
    assert [node["agent_id"] for node in graph.nodes] == [
        "agent.evaluator",
        "agent.researcher",
        "agent.root",
    ]
    assert [node["agent_id"] for node in graph.nodes if node["root"]] == ["agent.root"]
    failed_edges = [edge for edge in graph.edges if edge["failed"]]
    assert failed_edges == [
        {
            "source_agent_id": "agent.researcher",
            "target_agent_id": "agent.evaluator",
            "event_count": 1,
            "event_ids": ["mate_graph_handoff"],
            "event_kinds": ["handoff"],
            "statuses": ["failed"],
            "failed": True,
        }
    ]

    resource = delegation_graph_resource(graph).as_dict()
    assert validate_resource(resource) == []
    assert resource["kind"] == "DelegationGraph"
    assert resource["status"]["diagnostics"]["failed_handoffs"] == 1
    assert {"rel": "run", "href": "run:run_cf_graph"} in resource["links"]


def test_diagnostics_detect_undercommitment_and_overcommitment(tmp_path: Path):
    under_events = import_trace_events(
        [
            {
                "runtime_name": "recursive_fixture",
                "external_run_id": "under",
                "event_kind": "agent_spawned",
                "agent_id": "agent.a",
            },
            {
                "runtime_name": "recursive_fixture",
                "external_run_id": "under",
                "event_kind": "agent_spawned",
                "agent_id": "agent.b",
                "parent_agent_id": "agent.a",
            },
            {
                "runtime_name": "recursive_fixture",
                "external_run_id": "under",
                "event_kind": "agent_spawned",
                "agent_id": "agent.c",
                "parent_agent_id": "agent.b",
            },
            {
                "runtime_name": "recursive_fixture",
                "external_run_id": "under",
                "event_kind": "abstention",
                "agent_id": "agent.b",
                "status": "abstained",
                "summary": "delegated because tool was assumed missing",
            },
        ],
        log_path=tmp_path / "under.jsonl",
    )
    under = summarize_delegation_diagnostics(under_events)
    assert under.undercommitment_detected is True
    assert under.abstentions == 1

    over_events = import_trace_events(
        [
            {
                "runtime_name": "recursive_fixture",
                "external_run_id": "over",
                "event_kind": "agent_spawned",
                "agent_id": "agent.root",
            },
            {
                "runtime_name": "recursive_fixture",
                "external_run_id": "over",
                "event_kind": "tool_call",
                "agent_id": "agent.root",
                "summary": "search call 1",
            },
            {
                "runtime_name": "recursive_fixture",
                "external_run_id": "over",
                "event_kind": "tool_call",
                "agent_id": "agent.root",
                "summary": "search call 2",
            },
            {
                "runtime_name": "recursive_fixture",
                "external_run_id": "over",
                "event_kind": "tool_call",
                "agent_id": "agent.root",
                "summary": "search call 3",
            },
        ],
        log_path=tmp_path / "over.jsonl",
    )
    over = summarize_delegation_diagnostics(over_events)
    assert over.overcommitment_detected is True
    assert over.undercommitment_detected is False


def test_governance_change_packets_require_risk_and_rollback(tmp_path: Path):
    events = import_trace_events(
        [
            {
                "runtime_name": "meta_team_fixture",
                "external_run_id": "run-b",
                "event_kind": "handoff",
                "agent_id": "agent.executor",
                "target_agent_id": "agent.risk",
                "status": "failed",
                "summary": "risk check happened after state mutation",
            }
        ],
        log_path=tmp_path / "events.jsonl",
    )

    blocked = create_failure_attribution_packet(
        events=events,
        failure_summary="risk check happened after mutation",
        proposed_carrier_kind="governance_change",
        owner_role="role.risk_guardian",
        log_path=tmp_path / "packets.jsonl",
    )
    assert blocked.status == "blocked"

    ready = create_failure_attribution_packet(
        events=events,
        failure_summary="risk check happened after mutation",
        proposed_carrier_kind="governance_change",
        owner_role="role.risk_guardian",
        risk_summary="authority check order can allow stale mutation",
        rollback_plan="restore previous protocol file from git commit",
        invariant_evidence_refs=["test://authority-order"],
        log_path=tmp_path / "packets.jsonl",
    )
    assert ready.status == "review_ready"

    rows = [json.loads(line) for line in (tmp_path / "packets.jsonl").read_text().splitlines()]
    assert rows[0]["status"] == "blocked"
    assert rows[1]["status"] == "review_ready"
