"""Compile learning carriers into reviewable transition candidates.

The compiler is intentionally conservative: it reads organizational surfaces
and emits proposed transitions. It does not update mandates, charters,
forecast contracts, evidence gaps, or human-work sessions by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import REPO_ROOT
from cognitive_firm.orchestration.action_impact import DEFAULT_ACTION_IMPACT_SUMMARY
from cognitive_firm.orchestration.evidence_gaps import DEFAULT_EVIDENCE_GAPS_LOG
from cognitive_firm.orchestration.forecast_market import DEFAULT_FORECAST_MARKET_ROOT
from cognitive_firm.orchestration.human_work import DEFAULT_HUMAN_WORK_LOG
from cognitive_firm.orchestration.org_surface import build_org_surface
from cognitive_firm.orchestration.run_checkpoints import TRANSITIONS_LOG


LearningTransitionKind = Literal[
    "evidence_gap",
    "project_charter_update",
    "mandate_review",
    "human_work_session",
    "forecast_contract",
    "route_policy_change",
    "action_impact_repair",
    "role_review",
    "source_repair",
]


@dataclass(frozen=True)
class LearningTransitionCandidate:
    """A reviewable candidate for changing durable organizational state."""

    candidate_id: str
    transition_kind: LearningTransitionKind | str
    severity: str
    rationale: str
    source_kind: str
    object_ref: str | None = None
    suggested_owner_role: str | None = None
    review_question: str | None = None
    source_refs: list[str] = field(default_factory=list)
    proposed_payload: dict[str, Any] = field(default_factory=dict)
    observer_only: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LearningTransitionPlan:
    """Compiler output: candidates only, never automatic mutation."""

    n_candidates: int
    candidates: list[LearningTransitionCandidate] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def compile_learning_transitions(surface: Any) -> LearningTransitionPlan:
    """Compile an org surface into reviewable transition candidates.

    `surface` may be an `OrgSurface` object or its `as_dict()` payload.
    """
    payload = surface.as_dict() if hasattr(surface, "as_dict") else dict(surface)
    candidates: list[LearningTransitionCandidate] = []
    strategy_candidates = _from_strategy_findings(payload.get("strategy_review_state") or {})
    candidates.extend(strategy_candidates)
    candidates.extend(_from_forecast_contracts(payload.get("forecast_state") or {}))
    candidates.extend(
        _from_action_impacts(
            payload.get("action_impact_state") or {},
            covered_object_refs={candidate.object_ref for candidate in strategy_candidates},
        )
    )
    candidates.extend(_from_source_improvements(payload.get("intelligence_coverage_state") or {}))
    candidates.extend(_from_human_work_pressure(payload.get("a2h_pressure") or []))
    candidates.extend(_from_damage_patterns(payload.get("recent_damage_signals") or []))
    attention_state = payload.get("attention_state") or {}
    if isinstance(attention_state, dict):
        candidates.extend(
            _from_attention_signals(attention_state.get("routed_signals") or [])
        )

    deduped: dict[str, LearningTransitionCandidate] = {}
    for candidate in candidates:
        deduped.setdefault(candidate.candidate_id, candidate)
    ordered = sorted(
        deduped.values(),
        key=lambda item: (_severity_rank(item.severity), item.transition_kind, item.candidate_id),
    )
    return LearningTransitionPlan(n_candidates=len(ordered), candidates=ordered)


def compile_attention_transition_candidates(
    routed_signals: list[dict[str, Any]] | Any,
    *,
    stale_after_seconds: int = 3600,
    repeated_threshold: int = 3,
) -> LearningTransitionPlan:
    """Compile routed attention signals into observer-only review candidates.

    This read model does not reroute attention, mutate policy, or create work.
    It turns visible attention strain into governance-review candidates so a
    human can decide whether authority domains, actor memberships, mandates, or
    receipt discipline need durable change.
    """
    candidates = _from_attention_signals(
        routed_signals,
        stale_after_seconds=stale_after_seconds,
        repeated_threshold=repeated_threshold,
    )
    ordered = sorted(
        {candidate.candidate_id: candidate for candidate in candidates}.values(),
        key=lambda item: (_severity_rank(item.severity), item.transition_kind, item.candidate_id),
    )
    return LearningTransitionPlan(n_candidates=len(ordered), candidates=ordered)


def _from_strategy_findings(strategy_state: dict[str, Any]) -> list[LearningTransitionCandidate]:
    candidates: list[LearningTransitionCandidate] = []
    for finding in strategy_state.get("findings", []):
        if not isinstance(finding, dict):
            continue
        kind = str(finding.get("candidate_transition_kind") or "none")
        if kind == "none":
            continue
        candidates.append(
            _candidate(
                transition_kind=_normalize_transition_kind(kind),
                severity=str(finding.get("severity") or "info"),
                rationale=str(finding.get("rationale") or ""),
                source_kind="strategy_office_finding",
                object_ref=finding.get("object_ref"),
                suggested_owner_role=finding.get("suggested_owner_role"),
                review_question=finding.get("review_question"),
                source_refs=_string_list(finding.get("source_refs") or []),
                proposed_payload={
                    "finding_id": finding.get("finding_id"),
                    "recommendation": finding.get("recommendation"),
                    "promotion_gate": finding.get("promotion_gate"),
                    "promotion_evidence_required": finding.get("promotion_evidence_required") or [],
                    "metadata": finding.get("metadata") or {},
                },
            )
        )
    return candidates


def _from_forecast_contracts(forecast_state: dict[str, Any]) -> list[LearningTransitionCandidate]:
    candidates: list[LearningTransitionCandidate] = []
    for contract in forecast_state.get("contracts", []):
        if not isinstance(contract, dict):
            continue
        rec = contract.get("allocation_recommendation")
        if not isinstance(rec, dict):
            continue
        action = str(rec.get("action") or "")
        transition_kind = {
            "request_evidence": "evidence_gap",
            "request_human_work": "human_work_session",
            "ask_another_independent_agent": "forecast_contract",
            "split_contract": "forecast_contract",
            "kill_branch": "role_review",
            "defer": "role_review",
            "run_now": "role_review",
        }.get(action)
        if transition_kind is None:
            continue
        candidates.append(
            _candidate(
                transition_kind=transition_kind,
                severity="warning" if action in {"kill_branch", "request_evidence"} else "info",
                rationale=str(rec.get("reason") or f"Forecast allocation recommends {action}."),
                source_kind="forecast_allocation_recommendation",
                object_ref=str(contract.get("contract_id") or ""),
                suggested_owner_role="role.manager",
                review_question="Should this forecast recommendation change the next routed action?",
                source_refs=[str(contract.get("contract_id") or "forecast_contract")],
                proposed_payload={
                    "contract_id": contract.get("contract_id"),
                    "allocation_action": action,
                    "voi_proxy": rec.get("voi_proxy"),
                    "p_success": rec.get("p_success"),
                    "expected_value": rec.get("expected_value"),
                    "forecast_spread": rec.get("forecast_spread"),
                },
            )
        )
    return candidates


def _from_action_impacts(
    action_state: dict[str, Any],
    *,
    covered_object_refs: set[str | None] | None = None,
) -> list[LearningTransitionCandidate]:
    candidates: list[LearningTransitionCandidate] = []
    covered_object_refs = covered_object_refs or set()
    for record in action_state.get("review_required", []):
        if not isinstance(record, dict):
            continue
        object_ref = str(record.get("action_ref") or record.get("action_id") or "")
        if object_ref in covered_object_refs:
            continue
        candidates.append(
            _candidate(
                transition_kind="human_work_session",
                severity="warning",
                rationale="An action-impact record requires human review before reuse.",
                source_kind="action_impact_review",
                object_ref=object_ref,
                suggested_owner_role="role.principal",
                review_question="What judgment is required before reusing this action class?",
                source_refs=_string_list(record.get("artifact_refs") or [record.get("action_ref")]),
                proposed_payload={"action_id": record.get("action_id")},
            )
        )
    for record in action_state.get("local_with_negative_externalities", []):
        if not isinstance(record, dict):
            continue
        object_ref = str(record.get("action_ref") or record.get("action_id") or "")
        if object_ref in covered_object_refs:
            continue
        candidates.append(
            _candidate(
                transition_kind="role_review",
                severity="warning",
                rationale="A local action-impact record carries negative externalities.",
                source_kind="action_impact_externality",
                object_ref=object_ref,
                suggested_owner_role="role.reviewer",
                review_question="Should future routing penalize, constrain, or retire this action class?",
                source_refs=_string_list(record.get("artifact_refs") or [record.get("action_ref")]),
                proposed_payload={
                    "action_id": record.get("action_id"),
                    "negative_externality_tags": record.get("negative_externality_tags") or [],
                    "externalities": record.get("externalities") or {},
                },
            )
        )
    return candidates


def _from_source_improvements(coverage_state: dict[str, Any]) -> list[LearningTransitionCandidate]:
    candidates: list[LearningTransitionCandidate] = []
    for item in coverage_state.get("improvement_backlog", []):
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("source_id") or "")
        candidates.append(
            _candidate(
                transition_kind="source_repair",
                severity=str(item.get("severity") or "info"),
                rationale=str(item.get("issue") or item.get("recommended_action") or ""),
                source_kind="intelligence_source_improvement",
                object_ref=source_id,
                suggested_owner_role=str(item.get("owner_hint") or "role.manager"),
                review_question="What source repair would make this signal trustworthy enough for future routing?",
                source_refs=_string_list(item.get("source_refs") or [source_id]),
                proposed_payload={
                    "improvement_id": item.get("improvement_id"),
                    "recommended_action": item.get("recommended_action"),
                },
            )
        )
    return candidates


def _from_human_work_pressure(
    pressure_groups: list[dict[str, Any]],
) -> list[LearningTransitionCandidate]:
    candidates: list[LearningTransitionCandidate] = []
    for group in pressure_groups:
        if not isinstance(group, dict):
            continue
        role = str(group.get("agent_counterparty_role") or "")
        bottleneck = str(group.get("bottleneck_class") or "unknown")
        if not role:
            continue
        session_ids = _string_list(group.get("session_ids") or [])
        active_count = _int_or_zero(group.get("active_count"))
        missing_receipt_count = _int_or_zero(group.get("missing_receipt_count"))
        stale_count = _int_or_zero(group.get("stale_count"))
        transition_kind = _transition_kind_for_a2h_pressure(
            bottleneck=bottleneck,
            active_count=active_count,
            missing_receipt_count=missing_receipt_count,
        )
        candidates.append(
            _candidate(
                transition_kind=transition_kind,
                severity=(
                    "warning"
                    if missing_receipt_count or stale_count or active_count >= 3
                    else "info"
                ),
                rationale=(
                    "Repeated A2H human-work pressure needs review before it "
                    "changes future source, mandate, or routing behavior."
                ),
                source_kind="a2h_pressure",
                object_ref=f"a2h_pressure:{role}:{bottleneck}",
                suggested_owner_role=role,
                review_question=_a2h_pressure_review_question(bottleneck),
                source_refs=[f"human_work_session:{session_id}" for session_id in session_ids],
                proposed_payload={
                    "agent_counterparty_role": role,
                    "bottleneck_class": bottleneck,
                    "active_count": active_count,
                    "waiting_count": _int_or_zero(group.get("waiting_count")),
                    "missing_receipt_count": missing_receipt_count,
                    "stale_count": stale_count,
                    "session_ids": session_ids,
                    "recommendation": group.get("recommendation"),
                    "allowed_next_steps": _a2h_pressure_allowed_next_steps(bottleneck),
                    "boundary": (
                        "observer-only pressure candidate; does not automate, "
                        "reroute, or close human work"
                    ),
                },
            )
        )
    return candidates


def _from_damage_patterns(
    signals: Any,
    *,
    repeated_threshold: int = 2,
) -> list[LearningTransitionCandidate]:
    rows = [
        dict(row)
        for row in _list_or_empty(signals)
        if isinstance(row, dict) and row.get("kind")
    ]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row.get("kind") or "unknown"), []).append(row)

    candidates: list[LearningTransitionCandidate] = []
    for kind, group in groups.items():
        severities = {str(row.get("severity") or "warn").lower() for row in group}
        has_critical = "critical" in severities
        if len(group) < repeated_threshold and not has_critical:
            continue
        source_refs = [_damage_source_ref(row) for row in group]
        candidates.append(
            _candidate(
                transition_kind="mandate_review",
                severity="blocking" if has_critical else "warning",
                rationale=(
                    "Repeated or critical damage signals are accumulating; "
                    "review whether a mandate, route policy, routine, or "
                    "accountability case is warranted."
                ),
                source_kind="damage_pattern",
                object_ref=f"damage_pattern:{kind}",
                suggested_owner_role="role.manager",
                review_question=(
                    "Is this damage pattern a one-off observation, evidence "
                    "for an accountability case, a mandate/route-policy gap, "
                    "or an accepted-risk decision?"
                ),
                source_refs=source_refs,
                proposed_payload={
                    "damage_kind": kind,
                    "signal_count": len(group),
                    "sources": sorted(
                        {
                            str(row.get("source"))
                            for row in group
                            if row.get("source")
                        }
                    ),
                    "severities": sorted(severities),
                    "session_ids": sorted(
                        {
                            str(row.get("session_id"))
                            for row in group
                            if row.get("session_id")
                        }
                    ),
                    "allowed_next_steps": [
                        "accountability_case_review",
                        "mandate_review",
                        "route_policy_review",
                        "routine_retirement_review",
                        "accepted_risk_review",
                    ],
                    "boundary": (
                        "observer-only immune-response candidate; does not "
                        "quarantine, block, reroute, or create an "
                        "accountability case"
                    ),
                },
            )
        )
    return candidates


def _damage_source_ref(row: dict[str, Any]) -> str:
    if row.get("signal_id"):
        return f"damage_signal:{row['signal_id']}"
    timestamp = str(row.get("timestamp_utc") or "").strip()
    source = str(row.get("source") or "unknown_source").strip()
    kind = str(row.get("kind") or "unknown").strip()
    if timestamp:
        return f"damage_signal:{source}:{kind}:{timestamp}"
    return f"damage_signal:{source}:{kind}"


def _transition_kind_for_a2h_pressure(
    *,
    bottleneck: str,
    active_count: int,
    missing_receipt_count: int,
) -> str:
    normalized = bottleneck.lower()
    if missing_receipt_count and active_count < 3:
        return "human_work_session"
    if normalized == "access":
        return "source_repair"
    if normalized in {"authority", "safety"}:
        return "route_policy_change"
    return "mandate_review"


def _a2h_pressure_review_question(bottleneck: str) -> str:
    normalized = bottleneck.lower()
    if normalized in {"access", "labor", "cognition"}:
        return (
            "Should this repeated human-work pressure become source repair, "
            "tooling support, mandate review, or an intentionally preserved "
            "human boundary?"
        )
    if normalized in {"authority", "safety"}:
        return (
            "Should future routing preserve this human boundary, batch review, "
            "or require a stricter escalation policy?"
        )
    return (
        "Should this human-work pressure change future review cadence, "
        "mandate wording, or receipt discipline?"
    )


def _a2h_pressure_allowed_next_steps(bottleneck: str) -> list[str]:
    normalized = bottleneck.lower()
    if normalized in {"access", "labor", "cognition"}:
        return ["source_repair", "tooling_support", "mandate_review", "preserve_boundary"]
    if normalized in {"authority", "safety"}:
        return ["preserve_boundary", "batch_review", "route_policy_review"]
    return ["mandate_review", "receipt_discipline", "preserve_boundary"]


def _from_attention_signals(
    routed_signals: Any,
    *,
    stale_after_seconds: int = 3600,
    repeated_threshold: int = 3,
) -> list[LearningTransitionCandidate]:
    candidates: list[LearningTransitionCandidate] = []
    rows = [_attention_row(row) for row in _list_or_empty(routed_signals)]
    actionable_rows = [
        row
        for row in rows
        if row.get("signal_class") in {"governance_interrupt", "work_interrupt"}
    ]
    for row in actionable_rows:
        signal_id = str(row.get("signal_id") or "")
        source_ref = str(row.get("source_ref") or f"attention_signal:{signal_id}")
        target_actor = str(row.get("target_actor_id") or "")
        target_role = str(row.get("target_role_id") or "")
        signal_class = str(row.get("signal_class") or "")
        urgency = str(row.get("urgency") or "")
        age_seconds = _int_or_zero(row.get("age_seconds"))
        if not target_actor:
            candidates.append(
                _candidate(
                    transition_kind=_attention_unrouted_transition_kind(signal_class),
                    severity="warning" if urgency != "informational" else "info",
                    rationale=(
                        "A routed attention signal has no target actor; review "
                        "authority domains, actor memberships, or assignment "
                        "rules before changing future routing."
                    ),
                    source_kind="attention_unrouted_signal",
                    object_ref=f"attention_signal:{signal_id}",
                    suggested_owner_role=target_role or "role.manager",
                    review_question=(
                        "Who should be accountable for this class of attention "
                        "signal, and is a scoped authority or membership record "
                        "missing?"
                    ),
                    source_refs=[source_ref],
                    proposed_payload={
                        "signal_id": signal_id,
                        "signal_class": signal_class,
                        "urgency": urgency,
                        "pace_layer": row.get("pace_layer"),
                        "primary_action": row.get("primary_action"),
                        "target_role_id": target_role or None,
                        "target_actor_id": None,
                        "headline": row.get("headline"),
                        "boundary": (
                            "observer-only attention candidate; does not "
                            "reroute, page, assign, or close work"
                        ),
                    },
                )
            )
        if age_seconds >= stale_after_seconds and urgency != "informational":
            candidates.append(
                _candidate(
                    transition_kind=_attention_stale_transition_kind(signal_class),
                    severity="warning",
                    rationale=(
                        "A routed attention signal is stale; review whether "
                        "future signals should be batched, sampled, escalated, "
                        "or supported with better receipt discipline."
                    ),
                    source_kind="attention_stale_signal",
                    object_ref=f"attention_signal:{signal_id}",
                    suggested_owner_role=target_role or "role.manager",
                    review_question=(
                        "Is this stale signal a one-off delay, a missing "
                        "receipt, or evidence that the routing policy/mandate "
                        "needs review?"
                    ),
                    source_refs=[source_ref],
                    proposed_payload={
                        "signal_id": signal_id,
                        "signal_class": signal_class,
                        "urgency": urgency,
                        "age_seconds": age_seconds,
                        "stale_after_seconds": stale_after_seconds,
                        "target_role_id": target_role or None,
                        "target_actor_id": target_actor or None,
                        "boundary": (
                            "observer-only attention candidate; does not "
                            "reroute, page, assign, or close work"
                        ),
                    },
                )
            )

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in actionable_rows:
        key = (
            str(row.get("target_role_id") or "unresolved_role"),
            str(row.get("signal_class") or "unknown"),
            str(row.get("urgency") or "unknown"),
        )
        groups.setdefault(key, []).append(row)
    for (target_role, signal_class, urgency), group in groups.items():
        if len(group) < repeated_threshold:
            continue
        source_refs = [
            str(row.get("source_ref") or f"attention_signal:{row.get('signal_id')}")
            for row in group
        ]
        candidates.append(
            _candidate(
                transition_kind=_attention_pressure_transition_kind(signal_class),
                severity="warning" if urgency != "informational" else "info",
                rationale=(
                    "Repeated attention pressure is accumulating for one role "
                    "and signal class; review whether durable routing, mandate, "
                    "or receipt changes are warranted."
                ),
                source_kind="attention_pressure",
                object_ref=f"attention_pressure:{target_role}:{signal_class}:{urgency}",
                suggested_owner_role=None if target_role == "unresolved_role" else target_role,
                review_question=(
                    "Should this repeated attention pressure change future "
                    "routing cadence, mandate wording, staffing/membership, "
                    "or stay intentionally human-reviewed?"
                ),
                source_refs=source_refs,
                proposed_payload={
                    "target_role_id": None if target_role == "unresolved_role" else target_role,
                    "signal_class": signal_class,
                    "urgency": urgency,
                    "signal_count": len(group),
                    "signal_ids": [str(row.get("signal_id") or "") for row in group],
                    "target_actor_ids": sorted(
                        {
                            str(row.get("target_actor_id"))
                            for row in group
                            if row.get("target_actor_id")
                        }
                    ),
                    "primary_actions": sorted(
                        {
                            str(row.get("primary_action"))
                            for row in group
                            if row.get("primary_action")
                        }
                    ),
                    "repeated_threshold": repeated_threshold,
                    "boundary": (
                        "observer-only attention candidate; does not reroute, "
                        "page, assign, or close work"
                    ),
                },
            )
        )
    return candidates


def _attention_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "as_dict"):
        return dict(row.as_dict())
    if isinstance(row, dict):
        return dict(row)
    return {}


def _list_or_empty(payload: Any) -> list[Any]:
    return payload if isinstance(payload, list) else []


def _attention_unrouted_transition_kind(signal_class: str) -> str:
    if signal_class == "work_interrupt":
        return "human_work_session"
    return "route_policy_change"


def _attention_stale_transition_kind(signal_class: str) -> str:
    if signal_class == "work_interrupt":
        return "human_work_session"
    return "mandate_review"


def _attention_pressure_transition_kind(signal_class: str) -> str:
    if signal_class == "work_interrupt":
        return "human_work_session"
    if signal_class == "governance_interrupt":
        return "route_policy_change"
    return "mandate_review"


def _candidate(
    *,
    transition_kind: str,
    severity: str,
    rationale: str,
    source_kind: str,
    object_ref: Any = None,
    suggested_owner_role: Any = None,
    review_question: Any = None,
    source_refs: list[str] | None = None,
    proposed_payload: dict[str, Any] | None = None,
) -> LearningTransitionCandidate:
    payload = {
        "transition_kind": transition_kind,
        "source_kind": source_kind,
        "object_ref": object_ref,
        "source_refs": source_refs or [],
        "proposed_payload": proposed_payload or {},
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return LearningTransitionCandidate(
        candidate_id=f"ltc_{digest}",
        transition_kind=_normalize_transition_kind(transition_kind),
        severity=severity,
        rationale=rationale,
        source_kind=source_kind,
        object_ref=str(object_ref) if object_ref else None,
        suggested_owner_role=str(suggested_owner_role) if suggested_owner_role else None,
        review_question=str(review_question) if review_question else None,
        source_refs=source_refs or [],
        proposed_payload=proposed_payload or {},
    )


def _normalize_transition_kind(kind: str) -> str:
    if kind == "action_impact_repair":
        return "source_repair"
    if kind in {
        "evidence_gap",
        "project_charter_update",
        "mandate_review",
        "human_work_session",
        "forecast_contract",
        "route_policy_change",
        "role_review",
        "source_repair",
    }:
        return kind
    return "role_review"


def _string_list(payload: Any) -> list[str]:
    if isinstance(payload, list):
        return [str(item) for item in payload if item]
    if payload:
        return [str(payload)]
    return []


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _severity_rank(severity: str) -> int:
    return {"blocking": 0, "warning": 1, "info": 2}.get(severity, 3)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile organization-surface findings into reviewable learning transitions."
    )
    parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--evidence-gaps-log", type=Path, default=DEFAULT_EVIDENCE_GAPS_LOG)
    parser.add_argument("--human-work-log", type=Path, default=DEFAULT_HUMAN_WORK_LOG)
    parser.add_argument(
        "--forecast-market-summary",
        type=Path,
        default=DEFAULT_FORECAST_MARKET_ROOT / "global_health.json",
    )
    parser.add_argument("--action-impact-summary", type=Path, default=DEFAULT_ACTION_IMPACT_SUMMARY)
    parser.add_argument("--transitions-log", type=Path, default=TRANSITIONS_LOG)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    plan = compile_learning_transitions(
        build_org_surface(
            project_root=args.project_root,
            evidence_gaps_log=args.evidence_gaps_log,
            human_work_log=args.human_work_log,
            forecast_market_summary=args.forecast_market_summary,
            action_impact_summary=args.action_impact_summary,
            transitions_log=args.transitions_log,
        )
    )
    if args.json:
        print(json.dumps(plan.as_dict(), indent=2, sort_keys=True))
    else:
        for candidate in plan.candidates:
            print(
                f"- [{candidate.severity}] {candidate.candidate_id} "
                f"{candidate.transition_kind}: {candidate.rationale}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
