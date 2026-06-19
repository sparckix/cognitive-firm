"""Readable provenance timeline over existing kernel records.

This is a read model, not a workflow engine. It joins refs already carried by
runs, attestations, human work, governance proposals, outcome links, routine
reviews, learning events, and learning-use receipts so operators can inspect
"why did we decide this, what evidence existed, and what happened after?"
without reading raw JSONL.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cognitive_firm.orchestration.action_attestation import list_action_attestations
from cognitive_firm.orchestration.governance_changes import list_governance_changes
from cognitive_firm.orchestration.human_work import list_human_work_sessions
from cognitive_firm.orchestration.kernel_events import list_kernel_events
from cognitive_firm.orchestration.learning_events import (
    list_learning_event_encounters,
    list_learning_events,
)
from cognitive_firm.orchestration.outcome_links import list_outcome_links
from cognitive_firm.orchestration.routine_reviews import list_routine_reviews
from cognitive_firm.orchestration.run_checkpoints import get_run


@dataclass(frozen=True)
class TimelineEvent:
    occurred_at_utc: str
    event_kind: str
    object_ref: str
    summary: str
    source: str
    tenant_id: str | None = None
    project_id: str | None = None
    actor: str | None = None
    related_refs: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProvenanceGraphNode:
    node_id: str
    node_kind: str
    label: str
    source: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProvenanceGraphEdge:
    edge_id: str
    from_ref: str
    to_ref: str
    relation: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_provenance_timeline(
    *,
    run_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    ref: str | None = None,
    transition_log_path: Path | None = None,
    kernel_events_log_path: Path | None = None,
    action_attestation_log_path: Path | None = None,
    human_work_log_path: Path | None = None,
    governance_changes_log_path: Path | None = None,
    outcome_links_log_path: Path | None = None,
    routine_reviews_log_path: Path | None = None,
    learning_events_log_path: Path | None = None,
    learning_encounters_log_path: Path | None = None,
) -> dict[str, Any]:
    """Return an ordered timeline projection for a run, scope, or explicit ref."""
    events: list[TimelineEvent] = []
    caveats: list[str] = []
    refs = _query_refs(run_id=run_id, ref=ref)
    allow_global_scope = bool(refs)
    if run_id:
        try:
            run = get_run(run_id, log_path=transition_log_path)
            tenant_id = tenant_id or run.tenant_id
            project_id = project_id or run.project_id
        except KeyError:
            caveats.append(f"run not found: {run_id}")

    for event in list_kernel_events(
        tenant_id=None if refs else tenant_id,
        project_id=None if refs else project_id,
        log_path=kernel_events_log_path or transition_log_path,
    ):
        if not _matches_scope(
            tenant_id,
            project_id,
            event.tenant_id,
            event.project_id,
            allow_global=allow_global_scope,
        ):
            continue
        if not _matches_refs(
            refs,
            event.object_ref,
            event.subject_ref,
            event.payload,
        ):
            continue
        events.append(TimelineEvent(
            occurred_at_utc=event.occurred_at_utc,
            event_kind=event.verb,
            object_ref=event.object_ref,
            summary=str(event.payload.get("summary") or event.verb),
            source="kernel_events",
            tenant_id=event.tenant_id,
            project_id=event.project_id,
            actor=event.actor,
            related_refs=_related_refs(event.payload),
            payload=event.as_dict(),
        ))

    for attestation in list_action_attestations(
        tenant_id=None if refs else tenant_id,
        project_id=None if refs else project_id,
        run_id=run_id,
        log_path=action_attestation_log_path,
    ):
        if not _matches_scope(
            tenant_id,
            project_id,
            attestation.tenant_id,
            attestation.project_id,
            allow_global=allow_global_scope,
        ):
            continue
        if not _matches_refs(
            refs,
            attestation.attestation_id,
            f"action_attestation:{attestation.attestation_id}",
            attestation.run_id,
            attestation.subject_ref,
            attestation.input_refs,
            attestation.output_refs,
            attestation.metadata,
        ):
            continue
        events.append(TimelineEvent(
            occurred_at_utc=attestation.created_at_utc,
            event_kind="action_attestation",
            object_ref=f"action_attestation:{attestation.attestation_id}",
            summary=(
                f"{attestation.action_type} produced {attestation.subject_ref} "
                f"({attestation.verification_status})"
            ),
            source="action_attestations",
            tenant_id=attestation.tenant_id,
            project_id=attestation.project_id,
            actor=attestation.producer,
            related_refs=_dedupe([
                attestation.attestation_id,
                f"action_attestation:{attestation.attestation_id}",
                attestation.subject_ref,
                attestation.run_id,
                *attestation.input_refs,
                *attestation.output_refs,
            ]),
            payload=asdict(attestation),
        ))

    for session in list_human_work_sessions(
        tenant_id=None if refs else tenant_id,
        project_id=None if refs else project_id,
        log_path=human_work_log_path,
    ):
        if not _matches_scope(
            tenant_id,
            project_id,
            session.tenant_id,
            session.project_id,
            allow_global=allow_global_scope,
        ):
            continue
        receipt_refs = _human_work_receipt_refs(session.work_receipts)
        if not _matches_refs(
            refs,
            session.session_id,
            f"human_work:{session.session_id}",
            session.agent_followup_ref,
            session.integration_ref,
            session.artifact_refs,
            receipt_refs,
            session.metadata,
        ):
            continue
        events.append(TimelineEvent(
            occurred_at_utc=session.updated_at_utc,
            event_kind="human_work",
            object_ref=f"human_work:{session.session_id}",
            summary=f"{session.state}: {session.objective}",
            source="human_work",
            tenant_id=session.tenant_id,
            project_id=session.project_id,
            actor=session.human_actor,
            related_refs=_dedupe([
                session.session_id,
                f"human_work:{session.session_id}",
                session.agent_followup_ref,
                session.integration_ref,
                *session.artifact_refs,
                *receipt_refs,
            ]),
            payload=asdict(session),
        ))

    for proposal in list_governance_changes(
        tenant_id=None if refs else tenant_id,
        project_id=None if refs else project_id,
        log_path=governance_changes_log_path,
    ):
        if not _matches_scope(
            tenant_id,
            project_id,
            proposal.tenant_id,
            proposal.project_id,
            allow_global=allow_global_scope,
        ):
            continue
        if not _matches_refs(
            refs,
            proposal.proposal_id,
            f"governance_change:{proposal.proposal_id}",
            proposal.target_ref,
            proposal.source_refs,
            proposal.approval_ref,
            proposal.metadata,
        ):
            continue
        events.append(TimelineEvent(
            occurred_at_utc=proposal.created_at_utc,
            event_kind="governance_change",
            object_ref=f"governance_change:{proposal.proposal_id}",
            summary=f"{proposal.status}: {proposal.title}",
            source="governance_changes",
            tenant_id=proposal.tenant_id,
            project_id=proposal.project_id,
            actor=proposal.proposed_by,
            related_refs=_dedupe([
                proposal.proposal_id,
                f"governance_change:{proposal.proposal_id}",
                proposal.target_ref,
                proposal.approval_ref,
                *proposal.source_refs,
            ]),
            payload=proposal.as_dict(),
        ))

    for link in list_outcome_links(
        tenant_id=None if refs else tenant_id,
        project_id=None if refs else project_id,
        log_path=outcome_links_log_path,
    ):
        if not _matches_scope(
            tenant_id,
            project_id,
            link.tenant_id,
            link.project_id,
            allow_global=allow_global_scope,
        ):
            continue
        if not _matches_refs(
            refs,
            link.outcome_link_id,
            f"outcome_link:{link.outcome_link_id}",
            link.change_ref,
            link.learning_event_id,
            (
                f"learning_event:{link.learning_event_id}"
                if link.learning_event_id
                else None
            ),
            link.metadata,
        ):
            continue
        verdict = link.verdict or link.status
        events.append(TimelineEvent(
            occurred_at_utc=link.updated_at_utc,
            event_kind="outcome_link",
            object_ref=f"outcome_link:{link.outcome_link_id}",
            summary=f"{link.metric_name}: {verdict}",
            source="outcome_links",
            tenant_id=link.tenant_id,
            project_id=link.project_id,
            actor=link.verdict_recorded_by or link.created_by,
            related_refs=_dedupe([
                link.outcome_link_id,
                f"outcome_link:{link.outcome_link_id}",
                link.change_ref,
                link.learning_event_id,
                (
                    f"learning_event:{link.learning_event_id}"
                    if link.learning_event_id
                    else None
                ),
            ]),
            payload=link.as_dict(),
        ))

    for review in list_routine_reviews(
        tenant_id=None if refs else tenant_id,
        project_id=None if refs else project_id,
        log_path=routine_reviews_log_path,
    ):
        if not _matches_scope(
            tenant_id,
            project_id,
            review.tenant_id,
            review.project_id,
            allow_global=allow_global_scope,
        ):
            continue
        if not _matches_refs(
            refs,
            review.review_id,
            f"routine_review:{review.review_id}",
            review.routine_ref,
            review.learning_event_id,
            (
                f"learning_event:{review.learning_event_id}"
                if review.learning_event_id
                else None
            ),
            review.metadata,
        ):
            continue
        events.append(TimelineEvent(
            occurred_at_utc=review.updated_at_utc,
            event_kind="routine_review",
            object_ref=f"routine_review:{review.review_id}",
            summary=f"{review.status}: {review.routine_ref}",
            source="routine_reviews",
            tenant_id=review.tenant_id,
            project_id=review.project_id,
            actor=review.reviewer or review.scheduled_by,
            related_refs=_dedupe([
                review.review_id,
                f"routine_review:{review.review_id}",
                review.routine_ref,
                review.learning_event_id,
                (
                    f"learning_event:{review.learning_event_id}"
                    if review.learning_event_id
                    else None
                ),
            ]),
            payload=review.as_dict(),
        ))

    for learning in list_learning_events(
        tenant_id=None if refs else tenant_id,
        project_id=None if refs else project_id,
        log_path=learning_events_log_path,
    ):
        if not _matches_scope(
            tenant_id,
            project_id,
            learning.tenant_id,
            learning.project_id,
            allow_global=allow_global_scope,
        ):
            continue
        if not _matches_refs(
            refs,
            learning.learning_event_id,
            f"learning_event:{learning.learning_event_id}",
            learning.approval_ref,
            learning.candidate_ref,
            learning.source_carrier_refs,
            learning.derived_from_learning_event_ids,
            [
                f"learning_event:{learning_event_id}"
                for learning_event_id in learning.derived_from_learning_event_ids
            ],
            learning.metadata,
        ):
            continue
        events.append(TimelineEvent(
            occurred_at_utc=learning.created_at_utc,
            event_kind="learning_event",
            object_ref=f"learning_event:{learning.learning_event_id}",
            summary=f"{learning.status}: {learning.decision_use}",
            source="learning_events",
            tenant_id=learning.tenant_id,
            project_id=learning.project_id,
            actor=learning.approved_by,
            related_refs=_dedupe([
                learning.learning_event_id,
                f"learning_event:{learning.learning_event_id}",
                learning.approval_ref,
                learning.candidate_ref,
                *learning.source_carrier_refs,
                *learning.derived_from_learning_event_ids,
            ]),
            payload=learning.as_dict(),
        ))

    for encounter in list_learning_event_encounters(
        log_path=learning_encounters_log_path,
    ):
        if not _matches_scope(
            tenant_id,
            project_id,
            encounter.tenant_id,
            encounter.project_id,
            allow_global=allow_global_scope,
        ):
            continue
        if not _matches_refs(
            refs,
            encounter.encounter_id,
            f"learning_encounter:{encounter.encounter_id}",
            encounter.learning_event_id,
            f"learning_event:{encounter.learning_event_id}",
            encounter.work_ref,
            encounter.context_packet_ref,
            encounter.evidence_refs,
            encounter.metadata,
        ):
            continue
        events.append(TimelineEvent(
            occurred_at_utc=encounter.encountered_at_utc,
            event_kind="learning_use",
            object_ref=f"learning_encounter:{encounter.encounter_id}",
            summary=(
                f"{encounter.outcome}: {encounter.learning_event_id} "
                f"for {encounter.role}"
            ),
            source="learning_encounters",
            tenant_id=encounter.tenant_id,
            project_id=encounter.project_id,
            actor=encounter.role,
            related_refs=_dedupe([
                encounter.encounter_id,
                f"learning_encounter:{encounter.encounter_id}",
                encounter.learning_event_id,
                f"learning_event:{encounter.learning_event_id}",
                encounter.work_ref,
                encounter.context_packet_ref,
                *encounter.evidence_refs,
            ]),
            payload=encounter.as_dict(),
        ))

    ordered = sorted(
        events,
        key=lambda row: (row.occurred_at_utc or "", row.source, row.object_ref),
    )
    counts: dict[str, int] = {}
    for event in ordered:
        counts[event.source] = counts.get(event.source, 0) + 1
    if not refs and (tenant_id or project_id):
        caveats.append("timeline is scope-based; events may be related by tenant/project only")
    if refs and tenant_id is None and project_id is None:
        caveats.append(
            "ref-only timeline scans visible logs for exact refs; pass tenant_id/project_id to narrow scope"
        )
    if refs and not ordered:
        caveats.append("no records matched the requested run/ref and scope")
    return {
        "query": {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "ref": ref,
        },
        "read_only": True,
        "counts": counts,
        "caveats": caveats,
        "events": [event.as_dict() for event in ordered],
    }


def build_provenance_graph(
    *,
    run_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    ref: str | None = None,
    transition_log_path: Path | None = None,
    kernel_events_log_path: Path | None = None,
    action_attestation_log_path: Path | None = None,
    human_work_log_path: Path | None = None,
    governance_changes_log_path: Path | None = None,
    outcome_links_log_path: Path | None = None,
    routine_reviews_log_path: Path | None = None,
    learning_events_log_path: Path | None = None,
    learning_encounters_log_path: Path | None = None,
) -> dict[str, Any]:
    """Return a projection-only graph over the same records as the timeline.

    This is an adopter-facing read model for custom visualizations and
    "why/what-after" inspection. It owns no workflow state: nodes and edges are
    rebuilt from canonical logs, and edge direction means only "this record
    mentions this ref" unless an underlying record already encodes stronger
    semantics in its own payload.
    """
    timeline = build_provenance_timeline(
        run_id=run_id,
        tenant_id=tenant_id,
        project_id=project_id,
        ref=ref,
        transition_log_path=transition_log_path,
        kernel_events_log_path=kernel_events_log_path,
        action_attestation_log_path=action_attestation_log_path,
        human_work_log_path=human_work_log_path,
        governance_changes_log_path=governance_changes_log_path,
        outcome_links_log_path=outcome_links_log_path,
        routine_reviews_log_path=routine_reviews_log_path,
        learning_events_log_path=learning_events_log_path,
        learning_encounters_log_path=learning_encounters_log_path,
    )
    return _graph_from_timeline(timeline)


def build_provenance_report(
    *,
    run_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    ref: str | None = None,
    event_limit: int = 12,
    transition_log_path: Path | None = None,
    kernel_events_log_path: Path | None = None,
    action_attestation_log_path: Path | None = None,
    human_work_log_path: Path | None = None,
    governance_changes_log_path: Path | None = None,
    outcome_links_log_path: Path | None = None,
    routine_reviews_log_path: Path | None = None,
    learning_events_log_path: Path | None = None,
    learning_encounters_log_path: Path | None = None,
) -> dict[str, Any]:
    """Return a portable reviewer handoff over provenance logs.

    The report is a derived artifact: it stores no state and confers no
    approval. Operators can export it as JSON/Markdown when a human reviewer
    needs the compact "what happened, what evidence, what caveats" view.
    """
    timeline = build_provenance_timeline(
        run_id=run_id,
        tenant_id=tenant_id,
        project_id=project_id,
        ref=ref,
        transition_log_path=transition_log_path,
        kernel_events_log_path=kernel_events_log_path,
        action_attestation_log_path=action_attestation_log_path,
        human_work_log_path=human_work_log_path,
        governance_changes_log_path=governance_changes_log_path,
        outcome_links_log_path=outcome_links_log_path,
        routine_reviews_log_path=routine_reviews_log_path,
        learning_events_log_path=learning_events_log_path,
        learning_encounters_log_path=learning_encounters_log_path,
    )
    graph = _graph_from_timeline(timeline)
    events = list(timeline.get("events", []))
    bounded_limit = min(max(0, int(event_limit)), 50)
    source_counts = dict(timeline.get("counts", {}))
    actor_counts = _actor_counts(events)
    evidence_refs = _report_refs(events)
    follow_through = _report_follow_through(events, source_counts)
    first_event = events[0].get("occurred_at_utc") if events else None
    last_event = events[-1].get("occurred_at_utc") if events else None
    coverage = _report_coverage(source_counts, events)
    summary = {
        "event_count": len(events),
        "first_event_utc": first_event,
        "last_event_utc": last_event,
        "source_counts": source_counts,
        "actor_counts": actor_counts,
        "evidence_ref_count": len(evidence_refs),
        "graph_counts": graph.get("counts", {}),
    }
    report = {
        "query": timeline.get("query", {}),
        "read_only": True,
        "projection_only": True,
        "report_kind": "provenance_handoff",
        "generated_from": ["provenance_timeline", "provenance_graph"],
        "summary": summary,
        "coverage": coverage,
        "follow_through": follow_through,
        "caveats": list(timeline.get("caveats", [])),
        "review_questions": _report_review_questions(
            coverage,
            follow_through=follow_through,
        ),
        "event_excerpt": [
            _event_excerpt(event)
            for event in events[:bounded_limit]
        ],
        "event_excerpt_limit": bounded_limit,
        "evidence_refs": evidence_refs[:50],
    }
    report["markdown"] = _render_provenance_report_markdown(report)
    return report


def _graph_from_timeline(timeline: dict[str, Any]) -> dict[str, Any]:
    nodes: dict[str, ProvenanceGraphNode] = {}
    edges: dict[str, ProvenanceGraphEdge] = {}
    event_object_refs = {
        str(event.get("object_ref"))
        for event in timeline.get("events", [])
        if event.get("object_ref")
    }
    for event in timeline.get("events", []):
        object_ref = str(event.get("object_ref") or "")
        if not object_ref:
            continue
        nodes[object_ref] = ProvenanceGraphNode(
            node_id=object_ref,
            node_kind="event",
            label=str(event.get("summary") or object_ref),
            source=str(event.get("source") or ""),
            tenant_id=event.get("tenant_id"),
            project_id=event.get("project_id"),
            payload={
                "event_kind": event.get("event_kind"),
                "occurred_at_utc": event.get("occurred_at_utc"),
                "actor": event.get("actor"),
            },
        )
        for related_ref in _dedupe([
            str(item)
            for item in event.get("related_refs", [])
            if item and str(item) != object_ref
        ]):
            nodes.setdefault(
                related_ref,
                ProvenanceGraphNode(
                    node_id=related_ref,
                    node_kind="event" if related_ref in event_object_refs else "ref",
                    label=related_ref,
                ),
            )
            relation = (
                "mentions_event"
                if related_ref in event_object_refs
                else "mentions_ref"
            )
            edge = ProvenanceGraphEdge(
                edge_id=_edge_id(object_ref, related_ref, relation),
                from_ref=object_ref,
                to_ref=related_ref,
                relation=relation,
                source=str(event.get("source") or ""),
                payload={"event_kind": event.get("event_kind")},
            )
            edges[edge.edge_id] = edge

    caveats = list(timeline.get("caveats", []))
    caveats.append(
        "graph is a projection over canonical logs; it is not workflow state"
    )
    if edges:
        caveats.append(
            "edge direction means record-to-mentioned-ref, not inferred causality"
        )
    return {
        "query": timeline.get("query", {}),
        "read_only": True,
        "projection_only": True,
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "events": len(timeline.get("events", [])),
            "refs": len([
                node for node in nodes.values() if node.node_kind == "ref"
            ]),
        },
        "caveats": caveats,
        "nodes": [
            node.as_dict()
            for node in sorted(nodes.values(), key=lambda item: item.node_id)
        ],
        "edges": [
            edge.as_dict()
            for edge in sorted(edges.values(), key=lambda item: item.edge_id)
        ],
        "timeline_counts": timeline.get("counts", {}),
    }


def _actor_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        actor = event.get("actor")
        if not actor:
            continue
        text = str(actor)
        counts[text] = counts.get(text, 0) + 1
    return dict(sorted(counts.items()))


def _report_refs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mentions: dict[str, dict[str, Any]] = {}
    for event in events:
        object_ref = str(event.get("object_ref") or "")
        for value in event.get("related_refs", []) or []:
            ref = str(value)
            if not ref or ref == object_ref:
                continue
            row = mentions.setdefault(
                ref,
                {
                    "ref": ref,
                    "ref_kind": _classify_report_ref(ref),
                    "mention_count": 0,
                    "mentioned_by": [],
                },
            )
            row["mention_count"] += 1
            mentioned_by = row["mentioned_by"]
            if object_ref and object_ref not in mentioned_by:
                mentioned_by.append(object_ref)
    rows = list(mentions.values())
    rows.sort(key=lambda item: (-int(item["mention_count"]), item["ref"]))
    for row in rows:
        row["mentioned_by"] = row["mentioned_by"][:8]
    return rows


def _classify_report_ref(ref: str) -> str:
    if ref.startswith(("artifact://", "file://")):
        return "artifact"
    if ref.startswith(("http://", "https://")):
        return "external"
    if ref.startswith("action_attestation:"):
        return "action_attestation"
    if ref.startswith("human_work_receipt:"):
        return "human_work_receipt"
    if ref.startswith("human_work:"):
        return "human_work"
    if ref.startswith("governance_change:"):
        return "governance_change"
    if ref.startswith("learning_encounter:"):
        return "learning_encounter"
    if ref.startswith("learning_event:"):
        return "learning_event"
    if ref.startswith("outcome_link:"):
        return "outcome_link"
    if ref.startswith("routine_review:"):
        return "routine_review"
    if ref.startswith(("run:", "cognitive_run:")):
        return "run"
    if ref.startswith(("policy:", "role:", "mandate:", "org/")):
        return "governance_target"
    return "ref"


def _report_coverage(
    source_counts: dict[str, int],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    checks = {
        "has_events": bool(events),
        "has_kernel_events": source_counts.get("kernel_events", 0) > 0,
        "has_machine_provenance": source_counts.get("action_attestations", 0) > 0,
        "has_human_work": source_counts.get("human_work", 0) > 0,
        "has_governance_change": source_counts.get("governance_changes", 0) > 0,
        "has_outcome_or_review": (
            source_counts.get("outcome_links", 0) > 0
            or source_counts.get("routine_reviews", 0) > 0
        ),
        "has_learning_feedback": (
            source_counts.get("learning_events", 0) > 0
            or source_counts.get("learning_encounters", 0) > 0
        ),
    }
    gaps: list[str] = []
    if not checks["has_events"]:
        gaps.append("no matching provenance records found")
    if events and not checks["has_machine_provenance"]:
        gaps.append("no action attestations found in selected records")
    if events and not checks["has_governance_change"]:
        gaps.append("no governance-change record found in selected records")
    if events and not checks["has_outcome_or_review"]:
        gaps.append("no outcome link or routine review found in selected records")
    return {
        "checks": checks,
        "gaps": gaps,
        "status": "complete_enough_for_review" if not gaps else "partial",
    }


def _report_follow_through(
    events: list[dict[str, Any]],
    source_counts: dict[str, int],
) -> dict[str, Any]:
    """Summarize decision/outcome follow-through from selected records only."""

    decision_events = [
        event
        for event in events
        if str(event.get("source")) == "kernel_events"
        and str(event.get("event_kind") or "").startswith("governance_change.")
    ]
    outcome_events = [
        event for event in events if str(event.get("source")) == "outcome_links"
    ]
    routine_review_events = [
        event for event in events if str(event.get("source")) == "routine_reviews"
    ]
    learning_use_events = [
        event
        for event in events
        if str(event.get("source")) == "learning_encounters"
    ]
    learning_event_rows = [
        event for event in events if str(event.get("source")) == "learning_events"
    ]

    if outcome_events or routine_review_events or learning_use_events:
        status = "closed_loop_observed"
    elif decision_events:
        status = "decision_observed"
    elif source_counts.get("governance_changes", 0) > 0:
        status = "proposal_only"
    elif events:
        status = "evidence_only"
    else:
        status = "no_records"

    latest_refs = _dedupe(
        [
            str(event.get("object_ref") or "")
            for event in [
                *decision_events,
                *outcome_events,
                *routine_review_events,
                *learning_use_events,
                *learning_event_rows,
            ]
            if event.get("object_ref")
        ]
    )[-12:]
    review_questions: list[str] = []
    if status == "closed_loop_observed":
        review_questions.append(
            "Do observed outcomes, reviews, or learning-use receipts support "
            "keeping the change?"
        )
    elif status == "decision_observed":
        review_questions.append(
            "What outcome link or routine review will verify the decided change?"
        )
    elif status in {"proposal_only", "evidence_only"}:
        review_questions.append(
            "What decision, outcome link, or routine review should close this loop?"
        )

    return {
        "status": status,
        "decision_events": len(decision_events),
        "outcome_links": len(outcome_events),
        "routine_reviews": len(routine_review_events),
        "learning_events": len(learning_event_rows),
        "learning_use_receipts": len(learning_use_events),
        "human_work_sessions": int(source_counts.get("human_work", 0)),
        "latest_refs": latest_refs,
        "review_questions": review_questions,
        "read_only": True,
        "projection_only": True,
    }


def _report_review_questions(
    coverage: dict[str, Any],
    *,
    follow_through: dict[str, Any],
) -> list[str]:
    questions = [
        "Do the selected records support the claimed decision or outcome?",
        "Are the cited refs sufficient for a reviewer to reproduce the reasoning?",
    ]
    gaps = coverage.get("gaps", [])
    if any("action attestations" in gap for gap in gaps):
        questions.append("Should machine-produced artifacts carry action attestations?")
    if any("governance-change" in gap for gap in gaps):
        questions.append("Was the decision governed elsewhere, or is a proposal missing?")
    if any("outcome link" in gap for gap in gaps):
        questions.append("What follow-up metric or routine review should close the loop?")
    for question in follow_through.get("review_questions") or []:
        if question not in questions:
            questions.append(str(question))
    return questions


def _event_excerpt(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "occurred_at_utc": event.get("occurred_at_utc"),
        "event_kind": event.get("event_kind"),
        "source": event.get("source"),
        "object_ref": event.get("object_ref"),
        "actor": event.get("actor"),
        "summary": event.get("summary"),
        "related_refs": list(event.get("related_refs", []) or [])[:8],
    }


def _render_provenance_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    query = report.get("query", {})
    lines = [
        "# Provenance Report",
        "",
        "Read-only projection over canonical kernel logs.",
        "",
    ]
    query_bits = [
        f"{key}={value}"
        for key, value in query.items()
        if value is not None
    ]
    if query_bits:
        lines.append(f"Query: {', '.join(query_bits)}")
    lines.append(
        "Events: "
        f"{summary.get('event_count', 0)}"
        f" ({summary.get('first_event_utc')} to {summary.get('last_event_utc')})"
    )
    lines.append(f"Coverage: {report.get('coverage', {}).get('status')}")
    lines.append("")

    follow_through = report.get("follow_through") or {}
    if follow_through:
        lines.extend(["## Follow-Through", ""])
        lines.append(f"- status: {follow_through.get('status')}")
        lines.append(f"- decision events: {follow_through.get('decision_events', 0)}")
        lines.append(f"- outcome links: {follow_through.get('outcome_links', 0)}")
        lines.append(f"- routine reviews: {follow_through.get('routine_reviews', 0)}")
        lines.append(
            f"- learning-use receipts: {follow_through.get('learning_use_receipts', 0)}"
        )
        for ref in follow_through.get("latest_refs") or []:
            lines.append(f"- ref: {ref}")
        lines.append("")

    source_counts = summary.get("source_counts") or {}
    if source_counts:
        lines.extend(["## Source Counts", ""])
        for source, count in sorted(source_counts.items()):
            lines.append(f"- {source}: {count}")
        lines.append("")

    caveats = report.get("caveats") or []
    if caveats:
        lines.extend(["## Caveats", ""])
        for caveat in caveats:
            lines.append(f"- {caveat}")
        lines.append("")

    gaps = report.get("coverage", {}).get("gaps") or []
    if gaps:
        lines.extend(["## Coverage Gaps", ""])
        for gap in gaps:
            lines.append(f"- {gap}")
        lines.append("")

    questions = report.get("review_questions") or []
    if questions:
        lines.extend(["## Review Questions", ""])
        for question in questions:
            lines.append(f"- {question}")
        lines.append("")

    events = report.get("event_excerpt") or []
    if events:
        lines.extend(["## Timeline Excerpt", ""])
        for event in events:
            lines.append(
                "- "
                f"{event.get('occurred_at_utc')} "
                f"{event.get('event_kind')} "
                f"({event.get('source')}): "
                f"{event.get('summary')}"
            )
        lines.append("")

    evidence_refs = report.get("evidence_refs") or []
    if evidence_refs:
        lines.extend(["## High-Signal Refs", ""])
        for row in evidence_refs[:12]:
            lines.append(
                "- "
                f"{row.get('ref')} "
                f"[{row.get('ref_kind')}, mentions={row.get('mention_count')}]"
            )
    return "\n".join(lines).rstrip() + "\n"


def _matches_refs(refs: set[str], *values: Any) -> bool:
    if not refs:
        return True
    return any(_value_mentions_ref(value, refs) for value in values)


def _query_refs(*, run_id: str | None, ref: str | None) -> set[str]:
    refs: set[str] = set()
    for value in (run_id, ref):
        if value:
            refs.update(_expanded_ref(value))
    if run_id:
        refs.update({f"run:{run_id}", f"cognitive_run:{run_id}"})
    return refs


def _expanded_ref(value: str) -> set[str]:
    text = str(value).strip()
    if not text:
        return set()
    return {text}


def _matches_scope(
    tenant_id: str | None,
    project_id: str | None,
    record_tenant_id: str | None,
    record_project_id: str | None,
    *,
    allow_global: bool,
) -> bool:
    """Return whether a record belongs in a scoped timeline projection.

    Exact run/ref timelines may include globally scoped records that cite the
    requested ref. Scope-only timelines stay exact so a tenant/project timeline
    does not collect every global row in the repository.
    """
    if tenant_id is not None and record_tenant_id != tenant_id:
        if not (allow_global and record_tenant_id is None):
            return False
    if project_id is not None and record_project_id != project_id:
        if not (allow_global and record_project_id is None):
            return False
    return True


def _value_mentions_ref(value: Any, refs: set[str]) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value in refs
    if isinstance(value, dict):
        return any(_value_mentions_ref(item, refs) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_value_mentions_ref(item, refs) for item in value)
    return False


def _related_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, str):
        refs.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("_ref") or key.endswith("_id") or key in {"refs", "source_refs"}:
                refs.extend(_related_refs(item))
            elif isinstance(item, (dict, list, tuple, set)):
                refs.extend(_related_refs(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            refs.extend(_related_refs(item))
    return _dedupe(refs)


def _human_work_receipt_refs(receipts: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        for key in ("receipt_id", "receipt_ref"):
            value = receipt.get(key)
            if value:
                refs.append(str(value))
                if key == "receipt_id":
                    refs.append(f"human_work_receipt:{value}")
        refs.extend(_string_refs(receipt.get("subject_refs")))
        refs.extend(_string_refs(receipt.get("artifact_refs")))
        refs.extend(_related_refs(receipt.get("metadata") or {}))
    return _dedupe(refs)


def _string_refs(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        refs: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                refs.append(text)
        return refs
    text = str(value).strip()
    return [text] if text else []


def _edge_id(from_ref: str, to_ref: str, relation: str) -> str:
    digest = hashlib.sha256(
        "|".join([from_ref, relation, to_ref]).encode("utf-8")
    ).hexdigest()[:16]
    return f"pedge_{digest}"


def _dedupe(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value:
            continue
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
