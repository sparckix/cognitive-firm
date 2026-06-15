from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.capability_signals import (  # noqa: E402
    capability_signal_resource,
    close_capability_signal,
    get_capability_signal,
    learning_candidate_from_capability_signal,
    list_capability_signals,
    record_capability_signal,
    route_capability_signal,
    summarize_capability_signals,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


def test_capability_signal_routes_abstention_without_failure(tmp_path: Path):
    log = tmp_path / "capability_signals.jsonl"
    signal = record_capability_signal(
        signal_kind="abstention",
        severity="warning",
        source_ref="work_item:work_123",
        summary="Worker abstained because source evidence was missing.",
        owner_role="role.evaluator",
        worker_ref="worker://runtime/evaluator-1",
        run_id="run_123",
        work_id="work_123",
        recommended_route="request_evidence",
        counts_as_failure=False,
        evidence_refs=["trace://missing-source-ref"],
        log_path=log,
    )

    assert signal.status == "observed"
    assert signal.counts_as_failure is False

    routed = route_capability_signal(
        signal.signal_id,
        route_kind="request_evidence",
        routed_by="role.manager",
        rationale="The evaluator was right to stop; producer must attach source refs.",
        target_ref="a2h://source-receipt-request",
        log_path=log,
    )
    assert routed.status == "routed"
    assert routed.recommended_route == "request_evidence"
    assert routed.route_target_ref == "a2h://source-receipt-request"

    closed = close_capability_signal(
        signal.signal_id,
        closed_by="role.manager",
        closure_ref="human_work:hws_source_receipt",
        rationale="Source receipt was attached and the work can be retried.",
        log_path=log,
    )
    assert closed.status == "closed"
    assert closed.closure_ref == "human_work:hws_source_receipt"

    replayed = get_capability_signal(signal.signal_id, log_path=log)
    assert replayed.status == "closed"
    resource = capability_signal_resource(replayed).as_dict()
    assert validate_resource(resource) == []
    assert resource["kind"] == "CapabilitySignal"
    assert resource["links"] == [
        {"rel": "run", "href": "run:run_123"},
        {"rel": "work_item", "href": "work_item:work_123"},
    ]
    candidate = learning_candidate_from_capability_signal(replayed)
    assert candidate.transition_kind == "evidence_gap"
    assert candidate.source_kind == "capability_signal"
    assert candidate.object_ref == "work_123"
    assert candidate.suggested_owner_role == "role.evaluator"
    assert candidate.proposed_payload["counts_as_failure"] is False
    assert f"capability_signal:{signal.signal_id}" in candidate.source_refs


def test_capability_signal_summary_counts_open_blocking_routes(tmp_path: Path):
    log = tmp_path / "capability_signals.jsonl"
    first = record_capability_signal(
        signal_kind="insufficient_authority",
        severity="blocking",
        source_ref="authorization:dispatch-1",
        summary="Worker lacks authority for this resource.",
        owner_role="role.executor",
        recommended_route="escalate_to_principal",
        capability_ref="capability://write/protocol",
        log_path=log,
    )
    route_capability_signal(
        first.signal_id,
        route_kind="escalate_to_principal",
        routed_by="role.manager",
        rationale="The mandate does not cover the requested write.",
        log_path=log,
    )
    record_capability_signal(
        signal_kind="overload",
        severity="info",
        source_ref="runtime:worker-pool",
        summary="Worker pool reported temporary overload.",
        owner_role="role.dispatcher",
        recommended_route="reassign_work",
        log_path=log,
    )

    summary = summarize_capability_signals(list_capability_signals(log_path=log))

    assert summary.n_signals == 2
    assert summary.open_signals == 2
    assert summary.blocking_signals == 1
    assert summary.counts_by_kind == {"insufficient_authority": 1, "overload": 1}
    assert summary.counts_by_route == {"escalate_to_principal": 1, "reassign_work": 1}
    authority_candidate = learning_candidate_from_capability_signal(
        get_capability_signal(first.signal_id, log_path=log)
    )
    assert authority_candidate.transition_kind == "role_review"
    assert authority_candidate.severity == "blocking"
    assert authority_candidate.proposed_payload["signal_kind"] == "insufficient_authority"


def test_capability_signal_validates_inputs(tmp_path: Path):
    log = tmp_path / "capability_signals.jsonl"
    try:
        record_capability_signal(
            signal_kind="not_real",
            source_ref="work_item:work_123",
            summary="bad",
            owner_role="role.evaluator",
            log_path=log,
        )
    except ValueError as exc:
        assert "signal_kind" in str(exc)
    else:
        raise AssertionError("expected invalid signal kind to fail")

    signal = record_capability_signal(
        signal_kind="capability_gap",
        source_ref="work_item:work_456",
        summary="Worker lacks the required tool capability.",
        owner_role="role.executor",
        log_path=log,
    )
    try:
        route_capability_signal(
            signal.signal_id,
            route_kind="invent_route",
            routed_by="role.manager",
            rationale="bad route",
            log_path=log,
        )
    except ValueError as exc:
        assert "route_kind" in str(exc)
    else:
        raise AssertionError("expected invalid route to fail")
