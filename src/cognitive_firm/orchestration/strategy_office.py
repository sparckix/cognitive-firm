"""Strategy-review office interface.

The strategy office is an observer primitive over organizational learning
carriers. It reads forecast-market, action-impact, evidence, human-work, and
damage-signal state and emits review findings. It does not route work, change
mandates, or select actions.

The closest ancestor is a general-office alignment audit, not a candidate-level
inverter. An inverter asks how a champion candidate could be falsified. The
strategy office asks whether organizational state is still aligned with
charter, strategy, and learning obligations.

Tenants may bind these findings to a concrete role office. The public kernel
keeps the primitive as a read-model so it can be reused without importing one
tenant's strategy policy.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from cognitive_firm.orchestration.action_impact import (
    DEFAULT_ACTION_IMPACT_SUMMARY,
    ActionImpactSummary,
    summary_from_optional_path as action_impact_summary_from_path,
)
from cognitive_firm.orchestration.forecast_market import (
    DEFAULT_FORECAST_MARKET_ROOT,
    ForecastMarketSummary,
    market_summary_from_optional_path,
)


StrategyFindingKind = Literal[
    "source_health",
    "charter_alignment",
    "forecast_debt",
    "calibration_review",
    "externality_review",
    "human_review",
    "reflexive_insight",
    "maintenance_item",
    "inversion_candidate",
]
StrategySeverity = Literal["info", "warning", "blocking"]
StrategyScope = Literal["local", "project", "system"]
StrategyRecommendation = Literal[
    "observe",
    "repair_source_emitter",
    "repair_project_charter",
    "review_charter_alignment",
    "score_forecast_contracts",
    "review_calibration",
    "review_negative_externality",
    "request_human_review",
    "inspect_reflexive_insight",
    "inspect_maintenance_item",
    "open_inversion_review",
]
StrategyTransitionKind = Literal[
    "none",
    "evidence_gap",
    "project_charter_update",
    "mandate_review",
    "human_work_session",
    "forecast_contract",
    "action_impact_repair",
    "role_review",
]


@dataclass(frozen=True)
class StrategyOfficeFinding:
    finding_id: str
    kind: StrategyFindingKind | str
    severity: StrategySeverity | str
    recommendation: StrategyRecommendation | str
    rationale: str
    object_ref: str | None = None
    scope: StrategyScope | str = "system"
    review_question: str | None = None
    suggested_owner_role: str | None = None
    candidate_transition_kind: StrategyTransitionKind | str = "none"
    source_refs: list[str] = field(default_factory=list)
    promotion_gate: str | None = None
    promotion_evidence_required: list[str] = field(default_factory=list)
    observer_only: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyOfficeReview:
    observer_only: bool = True
    n_findings: int = 0
    n_blocking: int = 0
    n_warning: int = 0
    findings: list[StrategyOfficeFinding] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class StrategyOfficeAdapter(Protocol):
    """Read-only adapter implemented by tenant strategy-office systems."""

    def strategy_review(self) -> StrategyOfficeReview:
        """Return observer findings over organizational learning carriers."""


def build_strategy_review(
    *,
    forecast_summary: ForecastMarketSummary | None = None,
    action_impact_summary: ActionImpactSummary | None = None,
    charter_issues: list[dict[str, Any]] | None = None,
    evidence_gaps: list[dict[str, Any]] | None = None,
    human_work_sessions: list[dict[str, Any]] | None = None,
    recent_damage_signals: list[dict[str, Any]] | None = None,
    failed_runs: list[dict[str, Any]] | None = None,
) -> StrategyOfficeReview:
    """Build observer-only strategy findings from generic kernel read models."""
    forecast_summary = forecast_summary or ForecastMarketSummary(root=None)
    action_impact_summary = action_impact_summary or ActionImpactSummary(root=None)

    findings: list[StrategyOfficeFinding] = []
    findings.extend(_charter_findings(charter_issues or []))
    findings.extend(_evidence_gap_findings(evidence_gaps or []))
    findings.extend(_human_work_findings(human_work_sessions or []))
    findings.extend(_damage_signal_findings(recent_damage_signals or []))
    findings.extend(_failed_run_findings(failed_runs or []))
    findings.extend(_forecast_findings(forecast_summary))
    findings.extend(_action_impact_findings(action_impact_summary))

    return StrategyOfficeReview(
        observer_only=True,
        n_findings=len(findings),
        n_blocking=sum(1 for row in findings if row.severity == "blocking"),
        n_warning=sum(1 for row in findings if row.severity == "warning"),
        findings=findings,
    )


def build_strategy_review_from_paths(
    *,
    forecast_market_summary: Path = DEFAULT_FORECAST_MARKET_ROOT / "global_health.json",
    action_impact_summary: Path = DEFAULT_ACTION_IMPACT_SUMMARY,
) -> StrategyOfficeReview:
    """Load optional summaries from disk and build a strategy-office review."""
    return build_strategy_review(
        forecast_summary=market_summary_from_optional_path(forecast_market_summary),
        action_impact_summary=action_impact_summary_from_path(action_impact_summary),
    )


def _evidence_gap_findings(gaps: list[dict[str, Any]]) -> list[StrategyOfficeFinding]:
    findings: list[StrategyOfficeFinding] = []
    blocking = [gap for gap in gaps if gap.get("severity") == "blocking"]
    if blocking:
        findings.append(
            StrategyOfficeFinding(
                finding_id="blocking_evidence_gaps",
                kind="source_health",
                severity="blocking",
                recommendation="request_human_review",
                rationale=(
                    "Blocking evidence gaps are open. Material downstream work should not "
                    "treat the affected claims as settled."
                ),
                object_ref="evidence_gaps",
                scope="project",
                review_question="Which blocking gap must be closed or explicitly accepted before work proceeds?",
                suggested_owner_role="role.reviewer",
                candidate_transition_kind="evidence_gap",
                source_refs=[str(gap.get("gap_id") or gap.get("target") or "evidence_gap") for gap in blocking[:10]],
                promotion_gate="blocking evidence gap closed, downgraded, or explicitly accepted",
                promotion_evidence_required=["gap status update", "source or adjudication reference"],
                metadata={"n_blocking": len(blocking)},
            )
        )
    return findings


def _human_work_findings(sessions: list[dict[str, Any]]) -> list[StrategyOfficeFinding]:
    findings: list[StrategyOfficeFinding] = []
    followup = [
        row
        for row in sessions
        if row.get("agent_followup_required") and row.get("state") in {"handed_off", "completed"}
    ]
    receipt_waiting = [
        row
        for row in sessions
        if row.get("receipt_required") and not row.get("receipt")
    ]
    if followup:
        findings.append(
            StrategyOfficeFinding(
                finding_id="human_work_agent_followup",
                kind="human_review",
                severity="warning",
                recommendation="request_human_review",
                rationale=(
                    "Human work sessions require agent follow-up. The handoff should be "
                    "integrated before related work is marked complete."
                ),
                object_ref="human_work",
                scope="project",
                review_question="Which role must consume the human handoff and record integration?",
                suggested_owner_role="role.manager",
                candidate_transition_kind="human_work_session",
                source_refs=[str(row.get("session_id") or "human_work") for row in followup[:10]],
                promotion_gate="human handoff integrated or explicitly abandoned",
                promotion_evidence_required=["integration_ref or agent follow-up reference"],
                metadata={"n_followup_required": len(followup)},
            )
        )
    if receipt_waiting:
        findings.append(
            StrategyOfficeFinding(
                finding_id="human_work_receipt_missing",
                kind="source_health",
                severity="warning",
                recommendation="request_human_review",
                rationale=(
                    "Some human work sessions require receipts but have no receipt recorded."
                ),
                object_ref="human_work",
                scope="project",
                review_question="Is the missing receipt blocking, sampled for review, or safely waived?",
                suggested_owner_role="role.reviewer",
                candidate_transition_kind="human_work_session",
                source_refs=[str(row.get("session_id") or "human_work") for row in receipt_waiting[:10]],
                metadata={"n_receipt_waiting": len(receipt_waiting)},
            )
        )
    return findings


def _damage_signal_findings(signals: list[dict[str, Any]]) -> list[StrategyOfficeFinding]:
    if not signals:
        return []
    return [
        StrategyOfficeFinding(
            finding_id="recent_damage_signals",
            kind="source_health",
            severity="warning",
            recommendation="review_charter_alignment",
            rationale="Recent damage signals exist and should be inspected before assuming normal operation.",
            object_ref="damage_signals",
            scope="system",
            review_question="Do recent damage signals require a mandate, route, or source repair?",
            suggested_owner_role="role.manager",
            candidate_transition_kind="mandate_review",
            source_refs=[
                str(row.get("kind") or row.get("signal_id") or "damage_signal")
                for row in signals[:10]
            ],
            metadata={"n_recent": len(signals)},
        )
    ]


def _failed_run_findings(runs: list[dict[str, Any]]) -> list[StrategyOfficeFinding]:
    if not runs:
        return []
    return [
        StrategyOfficeFinding(
            finding_id="failed_runs_present",
            kind="source_health",
            severity="warning",
            recommendation="repair_source_emitter",
            rationale=(
                "Failed run checkpoints are visible. Repeated failures should become "
                "route, mandate, or runtime-adapter repair work rather than background noise."
            ),
            object_ref="run_checkpoints",
            scope="system",
            review_question="Are failed runs concentrated by runtime, owner role, or project?",
            suggested_owner_role="role.manager",
            candidate_transition_kind="role_review",
            source_refs=[str(row.get("run_id") or "run") for row in runs[:10]],
            metadata={"n_failed_runs": len(runs)},
        )
    ]


def _charter_findings(charter_issues: list[dict[str, Any]]) -> list[StrategyOfficeFinding]:
    findings: list[StrategyOfficeFinding] = []
    for idx, issue in enumerate(charter_issues[:10], start=1):
        path = str(issue.get("path") or f"charter_issue_{idx}")
        errors = [str(error) for error in issue.get("errors", [])]
        findings.append(
            StrategyOfficeFinding(
                finding_id=f"charter_alignment_issue_{idx}",
                kind="charter_alignment",
                severity="blocking",
                recommendation="repair_project_charter",
                rationale=(
                    "A project charter is invalid or underspecified. Strategy review cannot "
                    "distinguish aligned work from proxy optimization until the charter is repaired."
                ),
                object_ref=path,
                scope="project",
                review_question="What scope, end-state, or anchor proxy is missing from this charter?",
                suggested_owner_role="role.manager",
                candidate_transition_kind="project_charter_update",
                source_refs=[path],
                promotion_gate="valid project charter before downstream strategic alignment claims",
                promotion_evidence_required=[
                    "valid charter sections",
                    "at least one tenant-defined anchor proxy when scope drift is a material risk",
                ],
                metadata={"errors": errors, "summary": issue.get("summary") or {}},
            )
        )
    return findings


def _forecast_findings(summary: ForecastMarketSummary) -> list[StrategyOfficeFinding]:
    findings: list[StrategyOfficeFinding] = []
    root = summary.root or "forecast_market"

    if summary.n_contracts > 0 and summary.n_decision_use_rows == 0:
        findings.append(
            StrategyOfficeFinding(
                finding_id="forecast_decision_use_missing",
                kind="source_health",
                severity="blocking",
                recommendation="repair_source_emitter",
                rationale=(
                    "Forecast contracts exist, but no decision-use rows are visible. "
                    "The organization cannot measure whether forecasts changed routing."
                ),
                object_ref=root,
                scope="system",
                review_question="Why are forecast recommendations not linked to downstream decisions?",
                suggested_owner_role="role.manager",
                candidate_transition_kind="action_impact_repair",
                source_refs=[root],
                promotion_gate="decision-use rows exist before forecast-routing claims become measured",
                promotion_evidence_required=[
                    "at least one decision-use row",
                    "stable source reference from forecast contract to action-impact record",
                ],
            )
        )

    if summary.n_score_debt > 0:
        findings.append(
            StrategyOfficeFinding(
                finding_id="forecast_score_debt",
                kind="forecast_debt",
                severity="warning",
                recommendation="score_forecast_contracts",
                rationale=(
                    "Resolved forecast contracts without scores weaken calibration and future "
                    "allocation weighting."
                ),
                object_ref=root,
                scope="project",
                review_question="Which resolved forecast contracts need scoring before calibration is trusted?",
                suggested_owner_role="role.manager",
                candidate_transition_kind="role_review",
                source_refs=[root],
                metadata={"n_score_debt": summary.n_score_debt},
            )
        )

    if summary.n_high_confidence_misses > 0:
        findings.append(
            StrategyOfficeFinding(
                finding_id="forecast_high_confidence_misses",
                kind="calibration_review",
                severity="warning",
                recommendation="review_calibration",
                rationale=(
                    "High-confidence misses are strategy-relevant because they can justify "
                    "changing which forecasters or domains receive weight."
                ),
                object_ref=root,
                scope="system",
                review_question="Are high-confidence misses concentrated by role, domain, or contract type?",
                suggested_owner_role="role.reviewer",
                candidate_transition_kind="forecast_contract",
                source_refs=[root],
                metadata={"n_high_confidence_misses": summary.n_high_confidence_misses},
            )
        )

    for idx, item in enumerate(summary.reflexive_insights[:10]):
        findings.append(
            StrategyOfficeFinding(
                finding_id=f"forecast_reflexive_insight_{idx + 1}",
                kind="reflexive_insight",
                severity="info",
                recommendation="inspect_reflexive_insight",
                rationale="Forecast-market state emitted a reflexive insight for review.",
                object_ref=str(item.get("id") or item.get("kind") or root),
                scope=str(item.get("scope") or "project"),
                review_question=str(
                    item.get("review_question")
                    or "Does this insight need to become a durable state transition?"
                ),
                suggested_owner_role="role.reviewer",
                candidate_transition_kind=str(item.get("candidate_transition_kind") or "role_review"),
                source_refs=[root],
                metadata=item,
            )
        )

    for idx, item in enumerate(summary.maintenance_items[:10]):
        findings.append(
            StrategyOfficeFinding(
                finding_id=f"forecast_maintenance_item_{idx + 1}",
                kind="maintenance_item",
                severity="info",
                recommendation="inspect_maintenance_item",
                rationale="Forecast-market state emitted a maintenance item for review.",
                object_ref=str(item.get("id") or item.get("kind") or root),
                scope=str(item.get("scope") or "project"),
                review_question=str(
                    item.get("review_question")
                    or "Does this maintenance item block future learning if left unresolved?"
                ),
                suggested_owner_role="role.manager",
                candidate_transition_kind=str(item.get("candidate_transition_kind") or "role_review"),
                source_refs=[root],
                metadata=item,
            )
        )

    return findings


def _action_impact_findings(summary: ActionImpactSummary) -> list[StrategyOfficeFinding]:
    findings: list[StrategyOfficeFinding] = []
    root = summary.root or "action_impact"

    for record in summary.local_with_negative_externalities[:10]:
        findings.append(
            StrategyOfficeFinding(
                finding_id=f"negative_externality_{record.action_id}",
                kind="externality_review",
                severity="warning",
                recommendation="review_negative_externality",
                rationale=(
                    "A locally optimized action has recorded negative externalities. "
                    "Review before treating the action class as strategy-improving."
                ),
                object_ref=record.action_ref or record.action_id,
                scope=str(record.optimization_scope or "local"),
                review_question=(
                    "Is this local gain still desirable after accounting for the recorded externality?"
                ),
                suggested_owner_role="role.reviewer",
                candidate_transition_kind="role_review",
                source_refs=[record.action_ref] if record.action_ref else [root],
                metadata={
                    "action_id": record.action_id,
                    "objective_metric": record.objective_metric,
                    "externalities": record.externalities,
                    "negative_externality_tags": record.negative_externality_tags,
                },
            )
        )

    for record in summary.review_required[:10]:
        findings.append(
            StrategyOfficeFinding(
                finding_id=f"action_review_required_{record.action_id}",
                kind="human_review",
                severity="warning",
                recommendation="request_human_review",
                rationale="An action-impact record requires human review before reuse.",
                object_ref=record.action_ref or record.action_id,
                scope=str(record.optimization_scope or "project"),
                review_question="What human judgment is required before this action class is reused?",
                suggested_owner_role="role.principal",
                candidate_transition_kind="human_work_session",
                source_refs=[record.action_ref] if record.action_ref else [root],
                metadata={
                    "action_id": record.action_id,
                    "objective_metric": record.objective_metric,
                    "status": record.status,
                },
            )
        )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render observer-only strategy-office findings.")
    parser.add_argument(
        "--forecast-market-summary",
        type=Path,
        default=DEFAULT_FORECAST_MARKET_ROOT / "global_health.json",
    )
    parser.add_argument("--action-impact-summary", type=Path, default=DEFAULT_ACTION_IMPACT_SUMMARY)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    review = build_strategy_review_from_paths(
        forecast_market_summary=args.forecast_market_summary,
        action_impact_summary=args.action_impact_summary,
    )
    if args.json:
        print(json.dumps(review.as_dict(), indent=2, sort_keys=True))
    else:
        for finding in review.findings:
            print(f"- [{finding.severity}] {finding.finding_id}: {finding.rationale}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
