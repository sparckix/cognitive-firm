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

    deduped: dict[str, LearningTransitionCandidate] = {}
    for candidate in candidates:
        deduped.setdefault(candidate.candidate_id, candidate)
    ordered = sorted(
        deduped.values(),
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
