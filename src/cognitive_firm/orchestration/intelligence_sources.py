"""Generic intelligence-source coverage for organization surfaces.

This module does not collect tenant metrics. It inventories the kernel-facing
sources that already feed the organization surface and emits repair items when
those sources are missing decision-use, unresolved scoring, review closure, or
conformance coverage.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from cognitive_firm.orchestration.state_surface_inventory import (
    StateSurface,
    list_state_surfaces,
)


SourceHealth = Literal["healthy", "thin", "debt", "proxy_only", "unverified"]
SourceRepairSeverity = Literal["blocking", "warning", "info"]


@dataclass(frozen=True)
class IntelligenceSource:
    source_id: str
    source_kind: str
    connector_family: str
    canonical_ref: str
    writer: str
    reader: str
    tenant_owned: bool = False
    health: SourceHealth | str = "healthy"
    reason: str | None = None
    signal_count: int | None = None
    conformance_tests: list[str] = field(default_factory=list)
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceImprovement:
    improvement_id: str
    source_id: str
    severity: SourceRepairSeverity | str
    issue: str
    recommended_action: str
    owner_hint: str
    source_refs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProcessInputMetric:
    metric_id: str
    source_id: str
    value: int | float
    unit: str
    interpretation: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IntelligenceCoverage:
    n_sources: int
    n_tenant_owned_sources: int
    n_improvements: int
    n_warning_or_blocking_improvements: int
    counts_by_health: dict[str, int] = field(default_factory=dict)
    counts_by_connector_family: dict[str, int] = field(default_factory=dict)
    sources: list[IntelligenceSource] = field(default_factory=list)
    process_input_metrics: list[ProcessInputMetric] = field(default_factory=list)
    improvement_backlog: list[SourceImprovement] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RoutingReadiness:
    ready: bool
    blocking_improvements: list[SourceImprovement] = field(default_factory=list)
    warning_improvements: list[SourceImprovement] = field(default_factory=list)
    rationale: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_intelligence_coverage(
    *,
    state_surfaces: list[StateSurface] | None = None,
    forecast_state: dict[str, Any] | None = None,
    action_impact_state: dict[str, Any] | None = None,
    strategy_review_state: dict[str, Any] | None = None,
    surface_counts: dict[str, int] | None = None,
) -> IntelligenceCoverage:
    """Build a generic coverage projection over kernel-facing sources."""
    surfaces = state_surfaces or list_state_surfaces()
    forecast = forecast_state or {}
    action_impact = action_impact_state or {}
    strategy_review = strategy_review_state or {}
    counts = surface_counts or {}

    signal_counts = _signal_counts(forecast, action_impact, strategy_review, counts)
    improvements = _source_improvements(forecast, action_impact, strategy_review, counts)
    sources = [
        _source_from_surface(
            surface,
            signal_count=signal_counts.get(surface.primitive),
            improvement_source_ids={item.source_id for item in improvements},
        )
        for surface in surfaces
    ]
    metrics = _process_input_metrics(forecast, action_impact, strategy_review, counts)
    warning_or_blocking = [
        item for item in improvements if item.severity in {"blocking", "warning"}
    ]
    return IntelligenceCoverage(
        n_sources=len(sources),
        n_tenant_owned_sources=sum(1 for source in sources if source.tenant_owned),
        n_improvements=len(improvements),
        n_warning_or_blocking_improvements=len(warning_or_blocking),
        counts_by_health=_count_by(sources, "health"),
        counts_by_connector_family=_count_by(sources, "connector_family"),
        sources=sources,
        process_input_metrics=metrics,
        improvement_backlog=improvements,
    )


def routing_readiness_from_coverage(
    coverage: IntelligenceCoverage,
    *,
    source_ids: list[str] | None = None,
    allow_warnings: bool = False,
) -> RoutingReadiness:
    """Decide whether source health is strong enough for routing suggestions.

    This is a conservative gate for allocation or optimizer-like recommendations.
    It does not block ordinary visibility; it blocks using thin/debt-carrying
    sources as routing authority.
    """
    scoped = [
        item
        for item in coverage.improvement_backlog
        if source_ids is None or item.source_id in set(source_ids)
    ]
    source_id_set = set(source_ids) if source_ids is not None else None
    weak_sources = [
        source
        for source in coverage.sources
        if (source_id_set is None or source.source_id in source_id_set)
        and source.health in {"thin", "unverified", "proxy_only"}
    ]
    blocking = [item for item in scoped if item.severity == "blocking"]
    warnings = [item for item in scoped if item.severity == "warning"]
    synthetic_warnings = [
        SourceImprovement(
            improvement_id=f"{source.source_id}.source_health_{source.health}",
            source_id=source.source_id,
            severity="warning",
            issue=f"Source health is {source.health}.",
            recommended_action=source.reason or "Review source health before using this source for routing.",
            owner_hint="adapter owner",
            source_refs=[source.source_id],
        )
        for source in weak_sources
    ]
    warnings = [*warnings, *synthetic_warnings]
    ready = not blocking and (allow_warnings or not warnings)
    if blocking:
        rationale = "blocking source-health improvements must be resolved before routing"
    elif warnings and not allow_warnings:
        rationale = "warning source-health improvements require review before routing"
    else:
        rationale = "source health is sufficient for bounded routing use"
    return RoutingReadiness(
        ready=ready,
        blocking_improvements=blocking,
        warning_improvements=warnings,
        rationale=rationale,
    )


def _source_from_surface(
    surface: StateSurface,
    *,
    signal_count: int | None,
    improvement_source_ids: set[str],
) -> IntelligenceSource:
    health = "healthy"
    reason = None
    if not surface.conformance_tests:
        health = "unverified"
        reason = "No conformance test is registered for this source."
    elif surface.primitive in improvement_source_ids:
        health = "debt"
        reason = "Open source-improvement item exists."
    elif surface.surface_kind == "projection":
        health = "proxy_only"
        reason = "Projection only; mutate the underlying primitive."
    elif surface.tenant_owned and (signal_count is None or signal_count == 0):
        health = "thin"
        reason = "Tenant-owned source is available but currently has no visible rows."

    return IntelligenceSource(
        source_id=surface.primitive,
        source_kind=str(surface.surface_kind),
        connector_family=str(surface.connector_family),
        canonical_ref=surface.default_location,
        writer=surface.writer,
        reader=surface.reader,
        tenant_owned=surface.tenant_owned,
        health=health,
        reason=reason,
        signal_count=signal_count,
        conformance_tests=list(surface.conformance_tests),
        notes=surface.notes,
    )


def _source_improvements(
    forecast: dict[str, Any],
    action_impact: dict[str, Any],
    strategy_review: dict[str, Any],
    counts: dict[str, int],
) -> list[SourceImprovement]:
    items: list[SourceImprovement] = []
    n_contracts = _int(forecast.get("n_contracts"))
    if n_contracts and not _int(forecast.get("n_decision_use_rows")):
        items.append(
            SourceImprovement(
                improvement_id="forecast_market.decision_use_missing",
                source_id="forecast_market",
                severity="blocking",
                issue="Forecast contracts exist, but decision-use rows are missing.",
                recommended_action=(
                    "Emit a decision-use row when a forecast changes, confirms, "
                    "defers, or fails to affect routing."
                ),
                owner_hint="tenant forecast-market adapter",
                source_refs=["forecast_market"],
            )
        )
    if _int(forecast.get("n_score_debt")):
        items.append(
            SourceImprovement(
                improvement_id="forecast_market.score_debt",
                source_id="forecast_market",
                severity="warning",
                issue="Resolved forecasts are waiting for score rows.",
                recommended_action="Score resolved contracts or mark them void with a reason.",
                owner_hint="tenant forecast-market adapter",
                source_refs=["forecast_market"],
            )
        )
    if _int(action_impact.get("n_review_required")):
        items.append(
            SourceImprovement(
                improvement_id="action_impact.review_required",
                source_id="action_impact",
                severity="warning",
                issue="Action-impact records require human review before reuse.",
                recommended_action="Route review-required records into an accountability or learning review queue.",
                owner_hint="tenant action-impact adapter",
                source_refs=["action_impact"],
            )
        )
    if _int(action_impact.get("n_local_with_negative_externalities")):
        items.append(
            SourceImprovement(
                improvement_id="action_impact.negative_externalities",
                source_id="action_impact",
                severity="warning",
                issue="Local action-impact records carry negative externalities.",
                recommended_action="Add a guardrail, externality penalty, or role review before repeating the action class.",
                owner_hint="tenant action-impact adapter",
                source_refs=["action_impact"],
            )
        )
    if (
        _int(strategy_review.get("n_findings"))
        and not _int(counts.get("active_learning_events"))
    ):
        items.append(
            SourceImprovement(
                improvement_id="learning_events.findings_not_promoted",
                source_id="learning_events",
                severity="info",
                issue="Strategy findings exist, but no approved learning events are active.",
                recommended_action="Review learning-transition candidates and approve durable changes when warranted.",
                owner_hint="role.manager",
                source_refs=["strategy_office", "learning_transition_compiler"],
            )
        )
    return items


def _process_input_metrics(
    forecast: dict[str, Any],
    action_impact: dict[str, Any],
    strategy_review: dict[str, Any],
    counts: dict[str, int],
) -> list[ProcessInputMetric]:
    return [
        ProcessInputMetric(
            metric_id="forecast.contracts",
            source_id="forecast_market",
            value=_int(forecast.get("n_contracts")),
            unit="contracts",
            interpretation="Forecast volume visible to the kernel.",
        ),
        ProcessInputMetric(
            metric_id="forecast.decision_use_rows",
            source_id="forecast_market",
            value=_int(forecast.get("n_decision_use_rows")),
            unit="rows",
            interpretation="How often forecasts are tied to an actual routing decision.",
        ),
        ProcessInputMetric(
            metric_id="action_impact.measured_records",
            source_id="action_impact",
            value=_int(action_impact.get("n_measured")),
            unit="records",
            interpretation="Measured interventions visible to the kernel.",
        ),
        ProcessInputMetric(
            metric_id="learning.active_events",
            source_id="learning_events",
            value=_int(counts.get("active_learning_events")),
            unit="events",
            interpretation="Approved behavior changes currently available for reuse.",
        ),
        ProcessInputMetric(
            metric_id="strategy.findings",
            source_id="strategy_office",
            value=_int(strategy_review.get("n_findings")),
            unit="findings",
            interpretation="Observer findings that may require review.",
        ),
    ]


def _signal_counts(
    forecast: dict[str, Any],
    action_impact: dict[str, Any],
    strategy_review: dict[str, Any],
    counts: dict[str, int],
) -> dict[str, int]:
    return {
        "evidence_gaps": _int(counts.get("open_evidence_gaps")),
        "human_work": _int(counts.get("active_human_work_sessions")),
        "forecast_market": _int(forecast.get("n_contracts")),
        "action_impact": _int(action_impact.get("n_total")),
        "org_surface": sum(_int(value) for value in counts.values()),
        "strategy_office": _int(strategy_review.get("n_findings")),
        "learning_events": _int(counts.get("active_learning_events")),
        "accountability_cases": _int(counts.get("open_accountability_cases")),
        "run_checkpoints": _int(counts.get("active_runs")) + _int(counts.get("failed_runs")),
    }


def _count_by(rows: list[IntelligenceSource], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(getattr(row, attr))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render generic intelligence-source coverage.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    coverage = build_intelligence_coverage()
    if args.json:
        print(json.dumps(coverage.as_dict(), indent=2, sort_keys=True))
    else:
        for item in coverage.improvement_backlog:
            print(f"- [{item.severity}] {item.improvement_id}: {item.issue}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
