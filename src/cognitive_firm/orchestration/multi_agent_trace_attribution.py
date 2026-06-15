"""Multi-agent trace attribution carriers.

This module imports runtime-owned multi-agent traces into cognitive-firm as
review evidence. It does not execute agents, choose delegation structure, or
mutate governance state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.learning_transition_compiler import (
    LearningTransitionCandidate,
)
from cognitive_firm.orchestration.resource_envelope import KernelResource, make_resource


TraceEventKind = Literal[
    "agent_spawned",
    "agent_completed",
    "message",
    "handoff",
    "tool_call",
    "verifier_verdict",
    "abstention",
    "delegation_wait",
    "custom",
]
TraceEventStatus = Literal["observed", "succeeded", "failed", "blocked", "abstained", "unknown"]
AttributionScope = Literal["agent", "interaction", "team"]
CarrierKind = Literal["learning_transition", "governance_change", "policy_promotion", "none"]
AttributionStatus = Literal["draft", "review_ready", "blocked"]

DEFAULT_TRACE_EVENTS_LOG = ORG_ROOT_DIR / "multi_agent_traces" / "trace_events.jsonl"
DEFAULT_ATTRIBUTION_PACKETS_LOG = (
    ORG_ROOT_DIR / "multi_agent_traces" / "attribution_packets.jsonl"
)

VALID_EVENT_KINDS = {
    "agent_spawned",
    "agent_completed",
    "message",
    "handoff",
    "tool_call",
    "verifier_verdict",
    "abstention",
    "delegation_wait",
    "custom",
}
VALID_STATUSES = {"observed", "succeeded", "failed", "blocked", "abstained", "unknown"}
VALID_SCOPES = {"agent", "interaction", "team"}
VALID_CARRIERS = {"learning_transition", "governance_change", "policy_promotion", "none"}


@dataclass(frozen=True)
class MultiAgentTraceEvent:
    """One imported event from a runtime-owned multi-agent trace."""

    event_id: str
    observed_at_utc: str
    runtime_name: str
    external_run_id: str
    event_kind: TraceEventKind | str
    agent_id: str
    status: TraceEventStatus | str = "observed"
    cognitive_run_id: str | None = None
    parent_agent_id: str | None = None
    target_agent_id: str | None = None
    owner_role: str | None = None
    step_id: str | None = None
    summary: str | None = None
    payload_ref: str | None = None
    token_count: int | None = None
    cost_units: float | None = None
    source_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DelegationDiagnostics:
    """Graph-shape and failure-signal summary over imported trace events."""

    n_events: int
    n_agents: int
    n_edges: int
    max_depth: int
    abstentions: int
    failed_handoffs: int
    verifier_failures: int
    overcommitment_detected: bool
    undercommitment_detected: bool
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FailureAttributionPacket:
    """Review carrier for distributed multi-agent failure evidence."""

    packet_id: str
    created_at_utc: str
    runtime_name: str
    external_run_id: str
    attribution_scope: AttributionScope | str
    failure_summary: str
    proposed_carrier_kind: CarrierKind | str
    owner_role: str
    status: AttributionStatus | str = "draft"
    cognitive_run_id: str | None = None
    target_ref: str | None = None
    proposed_transition_kind: str | None = "role_review"
    source_event_ids: list[str] = field(default_factory=list)
    local_findings: list[dict[str, Any]] = field(default_factory=list)
    cross_agent_evidence: list[dict[str, Any]] = field(default_factory=list)
    disagreement_summary: str | None = None
    diagnostics: DelegationDiagnostics | None = None
    risk_summary: str | None = None
    rollback_plan: str | None = None
    invariant_evidence_refs: list[str] = field(default_factory=list)
    observer_only: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def review_ready(self) -> bool:
        return self.status == "review_ready"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["review_ready"] = self.review_ready
        return payload


@dataclass(frozen=True)
class DelegationGraph:
    """Replayable graph projection over runtime-owned trace events."""

    graph_id: str
    runtime_name: str
    external_run_id: str
    cognitive_run_id: str | None
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    source_event_ids: list[str]
    diagnostics: DelegationDiagnostics
    observer_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def record_trace_event(
    *,
    runtime_name: str,
    external_run_id: str,
    event_kind: TraceEventKind | str,
    agent_id: str,
    status: TraceEventStatus | str = "observed",
    cognitive_run_id: str | None = None,
    parent_agent_id: str | None = None,
    target_agent_id: str | None = None,
    owner_role: str | None = None,
    step_id: str | None = None,
    summary: str | None = None,
    payload_ref: str | None = None,
    token_count: int | None = None,
    cost_units: float | None = None,
    source_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    event_id: str | None = None,
    log_path: Path | None = None,
) -> MultiAgentTraceEvent:
    """Append one runtime-owned trace event as evidence."""
    event = MultiAgentTraceEvent(
        event_id=event_id or f"mate_{uuid.uuid4().hex[:12]}",
        observed_at_utc=_now_iso(),
        runtime_name=_required(runtime_name, "runtime_name"),
        external_run_id=_required(external_run_id, "external_run_id"),
        cognitive_run_id=cognitive_run_id,
        event_kind=_validate(event_kind, VALID_EVENT_KINDS, "event_kind"),
        agent_id=_required(agent_id, "agent_id"),
        parent_agent_id=parent_agent_id,
        target_agent_id=target_agent_id,
        owner_role=owner_role,
        step_id=step_id,
        status=_validate(status, VALID_STATUSES, "status"),
        summary=summary,
        payload_ref=payload_ref,
        token_count=token_count,
        cost_units=cost_units,
        source_refs=source_refs or [],
        metadata=metadata or {},
    )
    _append_jsonl(log_path or DEFAULT_TRACE_EVENTS_LOG, event.as_dict())
    return event


def import_trace_events(
    rows: list[dict[str, Any]],
    *,
    log_path: Path | None = None,
) -> list[MultiAgentTraceEvent]:
    """Normalize and record trace events from a runtime adapter fixture."""
    return [
        record_trace_event(
            runtime_name=str(row.get("runtime_name") or ""),
            external_run_id=str(row.get("external_run_id") or ""),
            cognitive_run_id=row.get("cognitive_run_id"),
            event_kind=str(row.get("event_kind") or "custom"),
            agent_id=str(row.get("agent_id") or ""),
            parent_agent_id=row.get("parent_agent_id"),
            target_agent_id=row.get("target_agent_id"),
            owner_role=row.get("owner_role"),
            step_id=row.get("step_id"),
            status=str(row.get("status") or "observed"),
            summary=row.get("summary"),
            payload_ref=row.get("payload_ref"),
            token_count=row.get("token_count"),
            cost_units=row.get("cost_units"),
            source_refs=_string_list(row.get("source_refs") or []),
            metadata=dict(row.get("metadata") or {}),
            event_id=row.get("event_id"),
            log_path=log_path,
        )
        for row in rows
    ]


def list_trace_events(
    *,
    runtime_name: str | None = None,
    external_run_id: str | None = None,
    cognitive_run_id: str | None = None,
    log_path: Path | None = None,
) -> list[MultiAgentTraceEvent]:
    """Read imported trace events, optionally filtered."""
    events: list[MultiAgentTraceEvent] = []
    for row in _read_jsonl(log_path or DEFAULT_TRACE_EVENTS_LOG):
        event = MultiAgentTraceEvent(**row)
        if runtime_name is not None and event.runtime_name != runtime_name:
            continue
        if external_run_id is not None and event.external_run_id != external_run_id:
            continue
        if cognitive_run_id is not None and event.cognitive_run_id != cognitive_run_id:
            continue
        events.append(event)
    return events


def summarize_delegation_diagnostics(
    events: list[MultiAgentTraceEvent | dict[str, Any]]
) -> DelegationDiagnostics:
    """Compute conservative recursive-delegation signals from trace shape."""
    normalized = [_event_from_any(event) for event in events]
    agents: set[str] = set()
    edges: dict[str, set[str]] = {}
    parents: dict[str, str] = {}
    abstentions = 0
    failed_handoffs = 0
    verifier_failures = 0
    notes: list[str] = []
    work_events_by_agent: dict[str, int] = {}

    for event in normalized:
        agents.add(event.agent_id)
        if event.parent_agent_id:
            agents.add(event.parent_agent_id)
            edges.setdefault(event.parent_agent_id, set()).add(event.agent_id)
            parents.setdefault(event.agent_id, event.parent_agent_id)
        if event.target_agent_id:
            agents.add(event.target_agent_id)
            if event.event_kind in {"handoff", "message", "delegation_wait"}:
                edges.setdefault(event.agent_id, set()).add(event.target_agent_id)
                parents.setdefault(event.target_agent_id, event.agent_id)
        if event.event_kind == "abstention" or event.status == "abstained":
            abstentions += 1
        if event.event_kind == "handoff" and event.status in {"failed", "blocked"}:
            failed_handoffs += 1
        if event.event_kind == "verifier_verdict" and event.status in {"failed", "blocked"}:
            verifier_failures += 1
        if event.event_kind in {"tool_call", "message", "agent_completed"}:
            work_events_by_agent[event.agent_id] = work_events_by_agent.get(event.agent_id, 0) + 1

    roots = [agent for agent in agents if agent not in parents]
    max_depth = max((_depth(root, edges) for root in roots), default=1 if agents else 0)
    n_edges = sum(len(children) for children in edges.values())
    overcommitment = len(agents) <= 2 and any(count >= 3 for count in work_events_by_agent.values())
    undercommitment = max_depth >= 3 and any(
        _is_chain(agent, edges, min_depth=3) for agent in roots
    )

    if overcommitment:
        notes.append("small delegation graph with concentrated work events")
    if undercommitment:
        notes.append("long single-child delegation chain detected")
    if abstentions:
        notes.append("abstention events present")
    if failed_handoffs:
        notes.append("failed or blocked handoff events present")
    if verifier_failures:
        notes.append("failed verifier verdicts present")

    return DelegationDiagnostics(
        n_events=len(normalized),
        n_agents=len(agents),
        n_edges=n_edges,
        max_depth=max_depth,
        abstentions=abstentions,
        failed_handoffs=failed_handoffs,
        verifier_failures=verifier_failures,
        overcommitment_detected=overcommitment,
        undercommitment_detected=undercommitment,
        notes=notes,
    )


def build_delegation_graph(
    events: list[MultiAgentTraceEvent | dict[str, Any]],
    *,
    runtime_name: str | None = None,
    external_run_id: str | None = None,
    cognitive_run_id: str | None = None,
) -> DelegationGraph:
    """Project trace events into a portable recursive-delegation graph."""
    normalized = [_event_from_any(event) for event in events]
    if not normalized:
        raise ValueError("events are required")
    runtime = runtime_name or normalized[0].runtime_name
    external_run = external_run_id or normalized[0].external_run_id
    cognitive_run = cognitive_run_id if cognitive_run_id is not None else normalized[0].cognitive_run_id
    scoped = [
        event
        for event in normalized
        if event.runtime_name == runtime
        and event.external_run_id == external_run
        and (cognitive_run is None or event.cognitive_run_id == cognitive_run)
    ]
    if not scoped:
        raise ValueError("no events match the requested graph scope")

    node_events: dict[str, list[MultiAgentTraceEvent]] = {}
    edge_map: dict[tuple[str, str], dict[str, Any]] = {}
    source_event_ids: list[str] = []
    for event in scoped:
        source_event_ids.append(event.event_id)
        for agent_id in (event.agent_id, event.parent_agent_id, event.target_agent_id):
            if agent_id:
                node_events.setdefault(agent_id, []).append(event)
        if event.parent_agent_id:
            _merge_edge(edge_map, event.parent_agent_id, event.agent_id, event)
        if event.target_agent_id and event.event_kind in {"handoff", "message", "delegation_wait"}:
            _merge_edge(edge_map, event.agent_id, event.target_agent_id, event)

    incoming = {target for _, target in edge_map}
    nodes = []
    for agent_id in sorted(node_events):
        rows = node_events[agent_id]
        statuses = sorted({str(row.status) for row in rows})
        event_kinds = sorted({str(row.event_kind) for row in rows})
        nodes.append(
            {
                "agent_id": agent_id,
                "owner_roles": sorted({row.owner_role for row in rows if row.owner_role}),
                "root": agent_id not in incoming,
                "event_count": len(rows),
                "event_kinds": event_kinds,
                "statuses": statuses,
            }
        )
    edges = sorted(edge_map.values(), key=lambda edge: (edge["source_agent_id"], edge["target_agent_id"]))
    graph_id = _graph_id(runtime, external_run, cognitive_run, source_event_ids)
    return DelegationGraph(
        graph_id=graph_id,
        runtime_name=runtime,
        external_run_id=external_run,
        cognitive_run_id=cognitive_run,
        nodes=nodes,
        edges=edges,
        source_event_ids=source_event_ids,
        diagnostics=summarize_delegation_diagnostics(scoped),
    )


def create_failure_attribution_packet(
    *,
    events: list[MultiAgentTraceEvent | dict[str, Any]],
    failure_summary: str,
    proposed_carrier_kind: CarrierKind | str,
    owner_role: str,
    attribution_scope: AttributionScope | str = "interaction",
    runtime_name: str | None = None,
    external_run_id: str | None = None,
    cognitive_run_id: str | None = None,
    target_ref: str | None = None,
    proposed_transition_kind: str | None = "role_review",
    local_findings: list[dict[str, Any]] | None = None,
    cross_agent_evidence: list[dict[str, Any]] | None = None,
    disagreement_summary: str | None = None,
    risk_summary: str | None = None,
    rollback_plan: str | None = None,
    invariant_evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    packet_id: str | None = None,
    log_path: Path | None = None,
) -> FailureAttributionPacket:
    """Create a review carrier from imported trace evidence."""
    normalized = [_event_from_any(event) for event in events]
    if not normalized:
        raise ValueError("events are required")
    runtime = runtime_name or normalized[0].runtime_name
    external_run = external_run_id or normalized[0].external_run_id
    cognitive_run = cognitive_run_id or normalized[0].cognitive_run_id
    source_event_ids = [event.event_id for event in normalized]
    diagnostics = summarize_delegation_diagnostics(normalized)
    inferred_local = local_findings if local_findings is not None else _infer_local_findings(normalized)
    inferred_cross = (
        cross_agent_evidence
        if cross_agent_evidence is not None
        else _infer_cross_agent_evidence(normalized)
    )
    carrier = _validate(proposed_carrier_kind, VALID_CARRIERS, "proposed_carrier_kind")
    status = _packet_status(
        failure_summary=failure_summary,
        proposed_carrier_kind=carrier,
        local_findings=inferred_local,
        cross_agent_evidence=inferred_cross,
        risk_summary=risk_summary,
        rollback_plan=rollback_plan,
    )
    packet = FailureAttributionPacket(
        packet_id=packet_id or _packet_id(
            runtime,
            external_run,
            failure_summary,
            source_event_ids,
        ),
        created_at_utc=_now_iso(),
        runtime_name=runtime,
        external_run_id=external_run,
        cognitive_run_id=cognitive_run,
        attribution_scope=_validate(attribution_scope, VALID_SCOPES, "attribution_scope"),
        failure_summary=_required(failure_summary, "failure_summary"),
        proposed_carrier_kind=carrier,
        proposed_transition_kind=proposed_transition_kind,
        owner_role=_required(owner_role, "owner_role"),
        status=status,
        target_ref=target_ref,
        source_event_ids=source_event_ids,
        local_findings=inferred_local,
        cross_agent_evidence=inferred_cross,
        disagreement_summary=disagreement_summary,
        diagnostics=diagnostics,
        risk_summary=risk_summary,
        rollback_plan=rollback_plan,
        invariant_evidence_refs=invariant_evidence_refs or [],
        metadata=metadata or {},
    )
    _append_jsonl(log_path or DEFAULT_ATTRIBUTION_PACKETS_LOG, packet.as_dict())
    return packet


def list_failure_attribution_packets(
    *,
    status: AttributionStatus | str | None = None,
    log_path: Path | None = None,
) -> list[FailureAttributionPacket]:
    """Read failure-attribution packets, optionally filtered by status."""
    packets: list[FailureAttributionPacket] = []
    for row in _read_jsonl(log_path or DEFAULT_ATTRIBUTION_PACKETS_LOG):
        row = dict(row)
        row.pop("review_ready", None)
        if isinstance(row.get("diagnostics"), dict):
            row["diagnostics"] = DelegationDiagnostics(**row["diagnostics"])
        packet = FailureAttributionPacket(**row)
        if status is not None and packet.status != status:
            continue
        packets.append(packet)
    return packets


def learning_candidate_from_attribution_packet(
    packet: FailureAttributionPacket,
) -> LearningTransitionCandidate:
    """Project a packet into an observer-only learning-transition candidate."""
    transition_kind = packet.proposed_transition_kind or "role_review"
    digest_payload = {
        "packet_id": packet.packet_id,
        "transition_kind": transition_kind,
        "source_event_ids": packet.source_event_ids,
    }
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    severity = "warning" if packet.status == "review_ready" else "info"
    if packet.status == "blocked":
        severity = "blocking"
    return LearningTransitionCandidate(
        candidate_id=f"ltc_{digest}",
        transition_kind=transition_kind,
        severity=severity,
        rationale=packet.failure_summary,
        source_kind="multi_agent_failure_attribution",
        object_ref=packet.target_ref or packet.cognitive_run_id or packet.external_run_id,
        suggested_owner_role=packet.owner_role,
        review_question="Should this multi-agent trace evidence change a future role, protocol, or learning policy?",
        source_refs=[f"multi_agent_attribution:{packet.packet_id}"]
        + [f"multi_agent_trace_event:{event_id}" for event_id in packet.source_event_ids],
        proposed_payload={
            "packet_id": packet.packet_id,
            "runtime_name": packet.runtime_name,
            "external_run_id": packet.external_run_id,
            "cognitive_run_id": packet.cognitive_run_id,
            "attribution_scope": packet.attribution_scope,
            "proposed_carrier_kind": packet.proposed_carrier_kind,
            "diagnostics": packet.diagnostics.as_dict() if packet.diagnostics else {},
            "local_findings": packet.local_findings,
            "cross_agent_evidence": packet.cross_agent_evidence,
            "risk_summary": packet.risk_summary,
            "rollback_plan": packet.rollback_plan,
            "invariant_evidence_refs": packet.invariant_evidence_refs,
        },
        observer_only=True,
    )


def trace_event_resource(event: MultiAgentTraceEvent) -> KernelResource:
    """Project a trace event into the common resource envelope."""
    links = []
    if event.cognitive_run_id:
        links.append({"rel": "run", "href": f"run:{event.cognitive_run_id}"})
    if event.parent_agent_id:
        links.append({"rel": "parent_agent", "href": f"agent:{event.parent_agent_id}"})
    if event.target_agent_id:
        links.append({"rel": "target_agent", "href": f"agent:{event.target_agent_id}"})
    return make_resource(
        kind="MultiAgentTraceEvent",
        name=event.event_id,
        resource_id=event.event_id,
        project_id=event.external_run_id,
        spec={
            "runtime_name": event.runtime_name,
            "external_run_id": event.external_run_id,
            "cognitive_run_id": event.cognitive_run_id,
            "event_kind": event.event_kind,
            "agent_id": event.agent_id,
            "parent_agent_id": event.parent_agent_id,
            "target_agent_id": event.target_agent_id,
            "owner_role": event.owner_role,
            "step_id": event.step_id,
            "summary": event.summary,
            "payload_ref": event.payload_ref,
            "source_refs": event.source_refs,
            "metadata": event.metadata,
        },
        status={
            "status": event.status,
            "token_count": event.token_count,
            "cost_units": event.cost_units,
        },
        links=links,
    )


def attribution_packet_resource(packet: FailureAttributionPacket) -> KernelResource:
    """Project a failure-attribution packet into the common resource envelope."""
    links = [
        {"rel": "trace_event", "href": f"multi_agent_trace_event:{event_id}"}
        for event_id in packet.source_event_ids
    ]
    if packet.cognitive_run_id:
        links.append({"rel": "run", "href": f"run:{packet.cognitive_run_id}"})
    return make_resource(
        kind="FailureAttributionPacket",
        name=packet.packet_id,
        resource_id=packet.packet_id,
        project_id=packet.external_run_id,
        spec={
            "runtime_name": packet.runtime_name,
            "external_run_id": packet.external_run_id,
            "cognitive_run_id": packet.cognitive_run_id,
            "attribution_scope": packet.attribution_scope,
            "failure_summary": packet.failure_summary,
            "proposed_carrier_kind": packet.proposed_carrier_kind,
            "proposed_transition_kind": packet.proposed_transition_kind,
            "owner_role": packet.owner_role,
            "target_ref": packet.target_ref,
            "local_findings": packet.local_findings,
            "cross_agent_evidence": packet.cross_agent_evidence,
            "disagreement_summary": packet.disagreement_summary,
            "risk_summary": packet.risk_summary,
            "rollback_plan": packet.rollback_plan,
            "invariant_evidence_refs": packet.invariant_evidence_refs,
            "metadata": packet.metadata,
        },
        status={
            "status": packet.status,
            "review_ready": packet.review_ready,
            "observer_only": packet.observer_only,
            "diagnostics": packet.diagnostics.as_dict() if packet.diagnostics else {},
        },
        links=links,
    )


def delegation_graph_resource(graph: DelegationGraph) -> KernelResource:
    """Project a delegation graph into the common resource envelope."""
    links = [
        {"rel": "trace_event", "href": f"multi_agent_trace_event:{event_id}"}
        for event_id in graph.source_event_ids
    ]
    if graph.cognitive_run_id:
        links.append({"rel": "run", "href": f"run:{graph.cognitive_run_id}"})
    return make_resource(
        kind="DelegationGraph",
        name=graph.graph_id,
        resource_id=graph.graph_id,
        project_id=graph.external_run_id,
        spec={
            "runtime_name": graph.runtime_name,
            "external_run_id": graph.external_run_id,
            "cognitive_run_id": graph.cognitive_run_id,
            "observer_only": graph.observer_only,
        },
        status={
            "nodes": graph.nodes,
            "edges": graph.edges,
            "diagnostics": graph.diagnostics.as_dict(),
            "source_event_ids": graph.source_event_ids,
        },
        links=links,
    )


def _infer_local_findings(events: list[MultiAgentTraceEvent]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for event in events:
        if event.status in {"failed", "blocked", "abstained"} or event.event_kind == "abstention":
            findings.append(
                {
                    "agent_id": event.agent_id,
                    "event_id": event.event_id,
                    "event_kind": event.event_kind,
                    "status": event.status,
                    "summary": event.summary,
                }
            )
    return findings


def _infer_cross_agent_evidence(events: list[MultiAgentTraceEvent]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for event in events:
        if event.target_agent_id or event.parent_agent_id:
            evidence.append(
                {
                    "event_id": event.event_id,
                    "source_agent_id": event.parent_agent_id or event.agent_id,
                    "target_agent_id": event.target_agent_id or event.agent_id,
                    "event_kind": event.event_kind,
                    "status": event.status,
                    "summary": event.summary,
                }
            )
    return evidence


def _packet_status(
    *,
    failure_summary: str,
    proposed_carrier_kind: str,
    local_findings: list[dict[str, Any]],
    cross_agent_evidence: list[dict[str, Any]],
    risk_summary: str | None,
    rollback_plan: str | None,
) -> str:
    if proposed_carrier_kind == "none":
        return "draft"
    if not failure_summary.strip() or not local_findings:
        return "blocked"
    if proposed_carrier_kind == "governance_change" and (not risk_summary or not rollback_plan):
        return "blocked"
    if proposed_carrier_kind in {"learning_transition", "policy_promotion"} and not cross_agent_evidence:
        return "blocked"
    return "review_ready"


def _event_from_any(event: MultiAgentTraceEvent | dict[str, Any]) -> MultiAgentTraceEvent:
    if isinstance(event, MultiAgentTraceEvent):
        return event
    return MultiAgentTraceEvent(**event)


def _depth(agent: str, edges: dict[str, set[str]], seen: set[str] | None = None) -> int:
    seen = seen or set()
    if agent in seen:
        return 0
    seen.add(agent)
    children = edges.get(agent) or set()
    if not children:
        return 1
    return 1 + max(_depth(child, edges, set(seen)) for child in children)


def _is_chain(agent: str, edges: dict[str, set[str]], *, min_depth: int) -> bool:
    depth = 1
    current = agent
    seen: set[str] = set()
    while True:
        if current in seen:
            return depth >= min_depth
        seen.add(current)
        children = edges.get(current) or set()
        if len(children) != 1:
            return depth >= min_depth
        current = next(iter(children))
        depth += 1


def _merge_edge(
    edge_map: dict[tuple[str, str], dict[str, Any]],
    source_agent_id: str,
    target_agent_id: str,
    event: MultiAgentTraceEvent,
) -> None:
    key = (source_agent_id, target_agent_id)
    edge = edge_map.setdefault(
        key,
        {
            "source_agent_id": source_agent_id,
            "target_agent_id": target_agent_id,
            "event_count": 0,
            "event_ids": [],
            "event_kinds": [],
            "statuses": [],
            "failed": False,
        },
    )
    edge["event_count"] += 1
    edge["event_ids"].append(event.event_id)
    edge["event_kinds"] = sorted(set(edge["event_kinds"] + [str(event.event_kind)]))
    edge["statuses"] = sorted(set(edge["statuses"] + [str(event.status)]))
    if event.status in {"failed", "blocked"}:
        edge["failed"] = True


def _packet_id(runtime_name: str, external_run_id: str, summary: str, source_event_ids: list[str]) -> str:
    payload = {
        "runtime_name": runtime_name,
        "external_run_id": external_run_id,
        "summary": summary,
        "source_event_ids": source_event_ids,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"fatp_{digest}"


def _graph_id(
    runtime_name: str,
    external_run_id: str,
    cognitive_run_id: str | None,
    source_event_ids: list[str],
) -> str:
    payload = {
        "runtime_name": runtime_name,
        "external_run_id": external_run_id,
        "cognitive_run_id": cognitive_run_id,
        "source_event_ids": source_event_ids,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"dgraph_{digest}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required(value: str, field_name: str) -> str:
    if not str(value).strip():
        raise ValueError(f"{field_name} is required")
    return str(value)


def _validate(value: str, allowed: set[str], field_name: str) -> str:
    text = str(value)
    if text not in allowed:
        raise ValueError(f"{field_name} must be one of: {', '.join(sorted(allowed))}")
    return text


def _string_list(payload: Any) -> list[str]:
    if isinstance(payload, list):
        return [str(item) for item in payload if item]
    if payload:
        return [str(payload)]
    return []


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect multi-agent trace attribution carriers.")
    parser.add_argument("--events-log", type=Path, default=DEFAULT_TRACE_EVENTS_LOG)
    parser.add_argument("--packets-log", type=Path, default=DEFAULT_ATTRIBUTION_PACKETS_LOG)
    parser.add_argument("--resource", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list-events")
    sub.add_parser("list-packets")

    diagnose = sub.add_parser("diagnose")
    diagnose.add_argument("--runtime-name")
    diagnose.add_argument("--external-run-id")
    diagnose.add_argument("--cognitive-run-id")

    graph = sub.add_parser("graph")
    graph.add_argument("--runtime-name")
    graph.add_argument("--external-run-id")
    graph.add_argument("--cognitive-run-id")

    args = parser.parse_args(argv)
    if args.cmd == "list-events":
        for event in list_trace_events(log_path=args.events_log):
            payload = trace_event_resource(event).as_dict() if args.resource else event.as_dict()
            print(json.dumps(payload, sort_keys=True))
    elif args.cmd == "list-packets":
        for packet in list_failure_attribution_packets(log_path=args.packets_log):
            payload = attribution_packet_resource(packet).as_dict() if args.resource else packet.as_dict()
            print(json.dumps(payload, sort_keys=True))
    elif args.cmd == "diagnose":
        events = list_trace_events(
            runtime_name=args.runtime_name,
            external_run_id=args.external_run_id,
            cognitive_run_id=args.cognitive_run_id,
            log_path=args.events_log,
        )
        print(json.dumps(summarize_delegation_diagnostics(events).as_dict(), sort_keys=True))
    elif args.cmd == "graph":
        events = list_trace_events(
            runtime_name=args.runtime_name,
            external_run_id=args.external_run_id,
            cognitive_run_id=args.cognitive_run_id,
            log_path=args.events_log,
        )
        graph_projection = build_delegation_graph(
            events,
            runtime_name=args.runtime_name,
            external_run_id=args.external_run_id,
            cognitive_run_id=args.cognitive_run_id,
        )
        payload = delegation_graph_resource(graph_projection).as_dict() if args.resource else graph_projection.as_dict()
        print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
