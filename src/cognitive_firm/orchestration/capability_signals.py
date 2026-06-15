"""Typed capability and abstention signals for work routing.

The kernel distinguishes a worker's grounded abstention from task failure.
This module records "should not do this now" signals and the route selected for
follow-up. It does not grant capabilities, execute reassignment, or mutate
governance state.
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


SignalKind = Literal[
    "abstention",
    "insufficient_authority",
    "capability_gap",
    "evidence_gap",
    "tool_unavailable",
    "budget_exceeded",
    "overload",
    "unsafe_request",
    "custom",
]
SignalSeverity = Literal["info", "warning", "blocking"]
SignalStatus = Literal["observed", "routed", "closed"]
RouteKind = Literal[
    "reassign_work",
    "escalate_to_principal",
    "request_evidence",
    "request_capability",
    "open_learning_candidate",
    "open_governance_change",
    "no_action",
]

VALID_SIGNAL_KINDS = {
    "abstention",
    "insufficient_authority",
    "capability_gap",
    "evidence_gap",
    "tool_unavailable",
    "budget_exceeded",
    "overload",
    "unsafe_request",
    "custom",
}
VALID_SEVERITIES = {"info", "warning", "blocking"}
VALID_STATUSES = {"observed", "routed", "closed"}
VALID_ROUTE_KINDS = {
    "reassign_work",
    "escalate_to_principal",
    "request_evidence",
    "request_capability",
    "open_learning_candidate",
    "open_governance_change",
    "no_action",
}

DEFAULT_CAPABILITY_SIGNALS_LOG = ORG_ROOT_DIR / "capability_signals" / "capability_signals.jsonl"


@dataclass(frozen=True)
class CapabilitySignal:
    signal_id: str
    observed_at_utc: str
    updated_at_utc: str
    signal_kind: SignalKind | str
    severity: SignalSeverity | str
    status: SignalStatus | str
    source_ref: str
    summary: str
    owner_role: str
    worker_ref: str | None = None
    run_id: str | None = None
    work_id: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    capability_ref: str | None = None
    threshold_ref: str | None = None
    recommended_route: RouteKind | str | None = None
    route_target_ref: str | None = None
    route_rationale: str | None = None
    routed_by: str | None = None
    routed_at_utc: str | None = None
    closure_ref: str | None = None
    closed_by: str | None = None
    closed_at_utc: str | None = None
    closure_rationale: str | None = None
    counts_as_failure: bool = False
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilitySignalSummary:
    n_signals: int
    open_signals: int
    blocking_signals: int
    counts_by_kind: dict[str, int]
    counts_by_route: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def record_capability_signal(
    *,
    signal_kind: SignalKind | str,
    source_ref: str,
    summary: str,
    owner_role: str,
    severity: SignalSeverity | str = "warning",
    worker_ref: str | None = None,
    run_id: str | None = None,
    work_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    capability_ref: str | None = None,
    threshold_ref: str | None = None,
    recommended_route: RouteKind | str | None = None,
    route_target_ref: str | None = None,
    counts_as_failure: bool = False,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    signal_id: str | None = None,
    log_path: Path | None = None,
) -> CapabilitySignal:
    """Record one grounded abstention or capability-gap signal."""
    now = _now_iso()
    route = _validate_route(recommended_route) if recommended_route is not None else None
    signal = CapabilitySignal(
        signal_id=signal_id or f"csig_{uuid.uuid4().hex[:12]}",
        observed_at_utc=now,
        updated_at_utc=now,
        signal_kind=_validate(signal_kind, VALID_SIGNAL_KINDS, "signal_kind"),
        severity=_validate(severity, VALID_SEVERITIES, "severity"),
        status="observed",
        source_ref=_required(source_ref, "source_ref"),
        summary=_required(summary, "summary"),
        owner_role=_required(owner_role, "owner_role"),
        worker_ref=worker_ref,
        run_id=run_id,
        work_id=work_id,
        tenant_id=tenant_id,
        project_id=project_id,
        capability_ref=capability_ref,
        threshold_ref=threshold_ref,
        recommended_route=route,
        route_target_ref=route_target_ref,
        counts_as_failure=counts_as_failure,
        evidence_refs=evidence_refs or [],
        metadata=metadata or {},
    )
    _append_event(log_path or DEFAULT_CAPABILITY_SIGNALS_LOG, "capability_signal.recorded", signal.as_dict())
    return signal


def route_capability_signal(
    signal_id: str,
    *,
    route_kind: RouteKind | str,
    routed_by: str,
    rationale: str,
    target_ref: str | None = None,
    log_path: Path | None = None,
) -> CapabilitySignal:
    """Record the selected route for an open capability signal."""
    path = log_path or DEFAULT_CAPABILITY_SIGNALS_LOG
    current = get_capability_signal(signal_id, log_path=path)
    if current.status == "closed":
        raise ValueError(f"cannot route closed signal {signal_id}")
    payload = {
        "signal_id": signal_id,
        "routed_at_utc": _now_iso(),
        "recommended_route": _validate_route(route_kind),
        "route_target_ref": target_ref,
        "route_rationale": _required(rationale, "rationale"),
        "routed_by": _required(routed_by, "routed_by"),
    }
    _append_event(path, "capability_signal.routed", payload)
    return get_capability_signal(signal_id, log_path=path)


def close_capability_signal(
    signal_id: str,
    *,
    closed_by: str,
    closure_ref: str,
    rationale: str,
    log_path: Path | None = None,
) -> CapabilitySignal:
    """Close a routed or observed signal after follow-up has a receipt."""
    path = log_path or DEFAULT_CAPABILITY_SIGNALS_LOG
    current = get_capability_signal(signal_id, log_path=path)
    if current.status == "closed":
        raise ValueError(f"signal is already closed: {signal_id}")
    payload = {
        "signal_id": signal_id,
        "closed_at_utc": _now_iso(),
        "closed_by": _required(closed_by, "closed_by"),
        "closure_ref": _required(closure_ref, "closure_ref"),
        "closure_rationale": _required(rationale, "rationale"),
    }
    _append_event(path, "capability_signal.closed", payload)
    return get_capability_signal(signal_id, log_path=path)


def list_capability_signals(*, log_path: Path | None = None) -> list[CapabilitySignal]:
    return list(_project(_read_events(log_path or DEFAULT_CAPABILITY_SIGNALS_LOG)).values())


def get_capability_signal(signal_id: str, *, log_path: Path | None = None) -> CapabilitySignal:
    signals = _project(_read_events(log_path or DEFAULT_CAPABILITY_SIGNALS_LOG))
    if signal_id not in signals:
        raise KeyError(f"capability signal not found: {signal_id}")
    return signals[signal_id]


def summarize_capability_signals(signals: list[CapabilitySignal]) -> CapabilitySignalSummary:
    by_kind: dict[str, int] = {}
    by_route: dict[str, int] = {}
    open_signals = 0
    blocking = 0
    for signal in signals:
        by_kind[str(signal.signal_kind)] = by_kind.get(str(signal.signal_kind), 0) + 1
        if signal.recommended_route:
            route = str(signal.recommended_route)
            by_route[route] = by_route.get(route, 0) + 1
        if signal.status != "closed":
            open_signals += 1
        if signal.severity == "blocking" and signal.status != "closed":
            blocking += 1
    return CapabilitySignalSummary(
        n_signals=len(signals),
        open_signals=open_signals,
        blocking_signals=blocking,
        counts_by_kind=by_kind,
        counts_by_route=by_route,
    )


def capability_signal_resource(signal: CapabilitySignal) -> KernelResource:
    links = []
    if signal.run_id:
        links.append({"rel": "run", "href": f"run:{signal.run_id}"})
    if signal.work_id:
        links.append({"rel": "work_item", "href": f"work_item:{signal.work_id}"})
    return make_resource(
        kind="CapabilitySignal",
        name=signal.signal_id,
        resource_id=signal.signal_id,
        tenant_id=signal.tenant_id,
        project_id=signal.project_id,
        spec={
            "signal_kind": signal.signal_kind,
            "source_ref": signal.source_ref,
            "summary": signal.summary,
            "owner_role": signal.owner_role,
            "worker_ref": signal.worker_ref,
            "capability_ref": signal.capability_ref,
            "threshold_ref": signal.threshold_ref,
            "counts_as_failure": signal.counts_as_failure,
            "metadata": signal.metadata,
        },
        status={
            "status": signal.status,
            "severity": signal.severity,
            "recommended_route": signal.recommended_route,
            "route_target_ref": signal.route_target_ref,
            "route_rationale": signal.route_rationale,
            "routed_by": signal.routed_by,
            "routed_at_utc": signal.routed_at_utc,
            "closure_ref": signal.closure_ref,
            "closed_by": signal.closed_by,
            "closed_at_utc": signal.closed_at_utc,
            "closure_rationale": signal.closure_rationale,
            "evidence_refs": signal.evidence_refs,
        },
        links=links,
    )


def learning_candidate_from_capability_signal(signal: CapabilitySignal) -> LearningTransitionCandidate:
    """Project an open capability signal into an observer-only learning candidate."""
    transition_kind = _transition_kind_for_signal(signal)
    object_ref = signal.work_id or signal.run_id or signal.source_ref
    source_refs = [f"capability_signal:{signal.signal_id}"] + signal.evidence_refs
    digest_payload = {
        "signal_id": signal.signal_id,
        "transition_kind": transition_kind,
        "object_ref": object_ref,
        "source_refs": source_refs,
    }
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return LearningTransitionCandidate(
        candidate_id=f"ltc_{digest}",
        transition_kind=transition_kind,
        severity=signal.severity,
        rationale=signal.summary,
        source_kind="capability_signal",
        object_ref=object_ref,
        suggested_owner_role=signal.owner_role,
        review_question=_review_question_for_signal(signal),
        source_refs=source_refs,
        proposed_payload={
            "signal_id": signal.signal_id,
            "signal_kind": signal.signal_kind,
            "status": signal.status,
            "worker_ref": signal.worker_ref,
            "run_id": signal.run_id,
            "work_id": signal.work_id,
            "capability_ref": signal.capability_ref,
            "threshold_ref": signal.threshold_ref,
            "recommended_route": signal.recommended_route,
            "route_target_ref": signal.route_target_ref,
            "route_rationale": signal.route_rationale,
            "counts_as_failure": signal.counts_as_failure,
            "closure_ref": signal.closure_ref,
            "metadata": signal.metadata,
        },
        observer_only=True,
    )


def _project(rows: list[dict[str, Any]]) -> dict[str, CapabilitySignal]:
    signals: dict[str, CapabilitySignal] = {}
    for row in rows:
        event = row.get("event")
        payload = dict(row.get("payload") or {})
        signal_id = str(payload.get("signal_id") or "")
        if not signal_id:
            continue
        if event == "capability_signal.recorded":
            signals[signal_id] = CapabilitySignal(**payload)
            continue
        if signal_id not in signals:
            continue
        current = signals[signal_id]
        if event == "capability_signal.routed":
            signals[signal_id] = CapabilitySignal(
                **{
                    **current.as_dict(),
                    "updated_at_utc": row.get("ts") or _now_iso(),
                    "status": "routed",
                    "recommended_route": payload.get("recommended_route"),
                    "route_target_ref": payload.get("route_target_ref"),
                    "route_rationale": payload.get("route_rationale"),
                    "routed_by": payload.get("routed_by"),
                    "routed_at_utc": payload.get("routed_at_utc"),
                }
            )
        elif event == "capability_signal.closed":
            signals[signal_id] = CapabilitySignal(
                **{
                    **current.as_dict(),
                    "updated_at_utc": row.get("ts") or _now_iso(),
                    "status": "closed",
                    "closure_ref": payload.get("closure_ref"),
                    "closed_by": payload.get("closed_by"),
                    "closed_at_utc": payload.get("closed_at_utc"),
                    "closure_rationale": payload.get("closure_rationale"),
                }
            )
    return signals


def _transition_kind_for_signal(signal: CapabilitySignal) -> str:
    if signal.signal_kind == "evidence_gap" or signal.recommended_route == "request_evidence":
        return "evidence_gap"
    if signal.signal_kind in {"insufficient_authority", "unsafe_request"}:
        return "role_review"
    if signal.recommended_route == "open_governance_change":
        return "role_review"
    if signal.recommended_route == "open_learning_candidate":
        return "role_review"
    if signal.signal_kind in {"capability_gap", "tool_unavailable"}:
        return "role_review"
    if signal.signal_kind in {"budget_exceeded", "overload"}:
        return "human_work_session"
    return "role_review"


def _review_question_for_signal(signal: CapabilitySignal) -> str:
    if signal.signal_kind == "evidence_gap" or signal.recommended_route == "request_evidence":
        return "What evidence repair should happen before this work is retried or reused?"
    if signal.signal_kind == "insufficient_authority":
        return "Should authority, routing, or escalation change before similar work is dispatched again?"
    if signal.signal_kind == "capability_gap":
        return "Should future routing require a different capability threshold or worker assignment?"
    if signal.signal_kind == "unsafe_request":
        return "Should future routing block, narrow, or escalate similar requests?"
    if signal.signal_kind in {"budget_exceeded", "overload"}:
        return "Should future work routing adjust budget, capacity, or human coordination before retry?"
    return "Should this capability signal change future routing, evidence requirements, or mandates?"


def _append_event(path: Path, event: str, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "event_id": f"csigevt_{uuid.uuid4().hex[:12]}",
        "event": event,
        "ts": _now_iso(),
        "payload": payload,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _validate(value: str, valid: set[str], label: str) -> str:
    text = str(value).strip()
    if text not in valid:
        raise ValueError(f"{label} must be one of: {', '.join(sorted(valid))}")
    return text


def _validate_route(value: str) -> str:
    return _validate(value, VALID_ROUTE_KINDS, "route_kind")


def _required(value: str | None, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect capability and abstention signals.")
    parser.add_argument("--log", type=Path, default=DEFAULT_CAPABILITY_SIGNALS_LOG)
    parser.add_argument("--resource", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("summary")
    args = parser.parse_args(argv)
    signals = list_capability_signals(log_path=args.log)
    if args.cmd == "list":
        for signal in signals:
            payload = capability_signal_resource(signal).as_dict() if args.resource else signal.as_dict()
            print(json.dumps(payload, sort_keys=True))
    elif args.cmd == "summary":
        print(json.dumps(summarize_capability_signals(signals).as_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
