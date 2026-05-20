"""Action-impact interface for tenant learning loops.

This is the action-side analogue of the forecast-market interface. The public
kernel defines the portable read-model shape for measured intervention impact.
Tenant overlays own the opinionated implementation: scientific-yield
decomposition, P&L attribution, bandit features, reward models, and optimizer
policy.

The interface is deliberately read-model first. A tenant may train bandits or
mini-RL policies from these records later, but the kernel does not choose
actions from reward.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from cognitive_firm.common.paths import REPO_ROOT


ImpactStatus = Literal["planned", "measured", "abandoned", "void"]
OptimizationScope = Literal["local", "project", "system"]
AttributionConfidence = Literal["low", "medium", "high"]

DEFAULT_ACTION_IMPACT_SUMMARY = REPO_ROOT / "org" / "action_impact" / "action_impact_summary.json"


@dataclass(frozen=True)
class ActionImpactRecordView:
    action_id: str
    action_ref: str
    actor: str
    objective_metric: str
    actor_role: str | None = None
    action_kind: str | None = None
    decision_stage: str | None = None
    baseline_action: str | None = None
    counterfactual_action: str | None = None
    expected_effect: str | None = None
    observed_outcome: str | None = None
    impact_summary: str | None = None
    old_state: str | None = None
    new_state: str | None = None
    artifact_refs: list[str] = field(default_factory=list)
    cost_units: float | None = None
    wall_seconds: float | None = None
    evaluator_role: str | None = None
    independence_boundary: str | None = None
    decision_changed_bool: bool | None = None
    externality_tags: list[str] = field(default_factory=list)
    negative_externality_tags: list[str] = field(default_factory=list)
    ignored_or_overridden_reason: str | None = None
    expected_impact: float | None = None
    actual_impact: float | None = None
    optimization_scope: OptimizationScope | str = "local"
    status: ImpactStatus | str = "planned"
    attribution_confidence: AttributionConfidence | str = "medium"
    tenant_id: str | None = None
    project_id: str | None = None
    forecast_contract_id: str | None = None
    guardrail_metrics: dict[str, float] = field(default_factory=dict)
    externalities: dict[str, float] = field(default_factory=dict)
    measurement_ref: str | None = None
    requires_human_review: bool = False
    notes: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionImpactSummary:
    root: str | None
    n_total: int = 0
    n_planned: int = 0
    n_measured: int = 0
    n_review_required: int = 0
    n_local_with_negative_externalities: int = 0
    mean_actual_impact_by_metric: dict[str, float] = field(default_factory=dict)
    records: list[ActionImpactRecordView] = field(default_factory=list)
    review_required: list[ActionImpactRecordView] = field(default_factory=list)
    local_with_negative_externalities: list[ActionImpactRecordView] = field(default_factory=list)
    guardrail_notes: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ActionImpactAdapter(Protocol):
    """Read-only adapter implemented by tenant action-impact systems."""

    def action_impact_summary(self) -> ActionImpactSummary:
        """Return the generic impact state consumed by the kernel."""


def load_summary_from_json(path: Path) -> ActionImpactSummary:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return summary_from_mapping(payload, root=str(path.parent))


def summary_from_mapping(payload: dict[str, Any], *, root: str | None = None) -> ActionImpactSummary:
    """Normalize a tenant action/yield/P&L summary to the kernel shape."""
    raw_records = payload.get("records") or payload.get("actions") or []
    records = [
        record_from_mapping(row)
        for row in raw_records
        if isinstance(row, dict)
    ]
    if not records and isinstance(payload.get("local_with_negative_externalities"), list):
        records = [
            record_from_mapping(row)
            for row in payload.get("local_with_negative_externalities", [])
            if isinstance(row, dict)
        ]

    review_required = [record for record in records if record.requires_human_review]
    local_negative = [
        record
        for record in records
        if record.optimization_scope == "local"
        and (
            any(value < 0 for value in record.externalities.values())
            or bool(record.negative_externality_tags)
        )
    ]
    measured = [record for record in records if record.status == "measured"]
    planned = [record for record in records if record.status == "planned"]
    means = _metric_means(measured)
    return ActionImpactSummary(
        root=root or payload.get("root"),
        n_total=int(payload.get("n_total") or len(records)),
        n_planned=int(payload.get("n_planned") or len(planned)),
        n_measured=int(payload.get("n_measured") or len(measured)),
        n_review_required=int(payload.get("n_review_required") or len(review_required)),
        n_local_with_negative_externalities=int(
            payload.get("n_local_with_negative_externalities") or len(local_negative)
        ),
        mean_actual_impact_by_metric=payload.get("mean_actual_impact_by_metric") or means,
        records=records,
        review_required=review_required,
        local_with_negative_externalities=local_negative,
        guardrail_notes=[
            row for row in payload.get("guardrail_notes", [])
            if isinstance(row, dict)
        ],
    )


def record_from_mapping(payload: dict[str, Any]) -> ActionImpactRecordView:
    return ActionImpactRecordView(
        action_id=str(payload.get("action_id") or payload.get("id") or ""),
        action_ref=str(payload.get("action_ref") or payload.get("evidence_pointer") or payload.get("ref") or ""),
        actor=str(payload.get("actor") or payload.get("owner") or payload.get("producer") or ""),
        objective_metric=str(payload.get("objective_metric") or payload.get("metric") or payload.get("bottleneck") or ""),
        actor_role=payload.get("actor_role") or payload.get("role"),
        action_kind=payload.get("action_kind") or payload.get("kind"),
        decision_stage=payload.get("decision_stage") or payload.get("stage"),
        baseline_action=payload.get("baseline_action") or payload.get("old_next_action"),
        counterfactual_action=payload.get("counterfactual_action"),
        expected_effect=payload.get("expected_effect"),
        observed_outcome=payload.get("observed_outcome"),
        impact_summary=payload.get("impact_summary") or payload.get("summary"),
        old_state=payload.get("old_state"),
        new_state=payload.get("new_state"),
        artifact_refs=_string_list(payload.get("artifact_refs") or payload.get("artifacts") or []),
        cost_units=_maybe_float(payload.get("cost_units")),
        wall_seconds=_maybe_float(payload.get("wall_seconds")),
        evaluator_role=payload.get("evaluator_role"),
        independence_boundary=payload.get("independence_boundary"),
        decision_changed_bool=_maybe_bool(
            payload.get("decision_changed_bool")
            if "decision_changed_bool" in payload
            else payload.get("decision_changed")
        ),
        externality_tags=_string_list(payload.get("externality_tags") or []),
        negative_externality_tags=_string_list(payload.get("negative_externality_tags") or []),
        ignored_or_overridden_reason=(
            payload.get("ignored_or_overridden_reason")
            or payload.get("ignored_forecast_reason")
        ),
        expected_impact=_maybe_float(payload.get("expected_impact")),
        actual_impact=_maybe_float(
            payload["actual_impact"] if "actual_impact" in payload else payload.get("impact")
        ),
        optimization_scope=str(payload.get("optimization_scope") or "local"),
        status=str(payload.get("status") or ("measured" if payload.get("actual_impact") is not None else "planned")),
        attribution_confidence=str(payload.get("attribution_confidence") or payload.get("confidence") or "medium"),
        tenant_id=payload.get("tenant_id"),
        project_id=payload.get("project_id"),
        forecast_contract_id=payload.get("forecast_contract_id") or payload.get("contract_id"),
        guardrail_metrics=_float_dict(payload.get("guardrail_metrics") or {}),
        externalities=_float_dict(payload.get("externalities") or {}),
        measurement_ref=payload.get("measurement_ref"),
        requires_human_review=bool(_maybe_bool(payload.get("requires_human_review"))),
        notes=payload.get("notes") or payload.get("verdict"),
        metadata={
            str(k): v
            for k, v in payload.items()
            if k not in {
                "action_id",
                "id",
                "action_ref",
                "actor",
                "owner",
                "producer",
                "objective_metric",
                "metric",
                "bottleneck",
                "actor_role",
                "role",
                "action_kind",
                "kind",
                "decision_stage",
                "stage",
                "baseline_action",
                "old_next_action",
                "counterfactual_action",
                "expected_effect",
                "observed_outcome",
                "impact_summary",
                "summary",
                "old_state",
                "new_state",
                "artifact_refs",
                "artifacts",
                "cost_units",
                "wall_seconds",
                "evaluator_role",
                "independence_boundary",
                "decision_changed_bool",
                "decision_changed",
                "externality_tags",
                "negative_externality_tags",
                "ignored_or_overridden_reason",
                "ignored_forecast_reason",
                "expected_impact",
                "actual_impact",
                "impact",
                "optimization_scope",
                "status",
                "attribution_confidence",
                "confidence",
                "tenant_id",
                "project_id",
                "forecast_contract_id",
                "contract_id",
                "guardrail_metrics",
                "externalities",
                "measurement_ref",
                "requires_human_review",
                "notes",
                "verdict",
            }
        },
    )


def empty_summary(*, root: Path | None = None) -> ActionImpactSummary:
    return ActionImpactSummary(root=str(root or DEFAULT_ACTION_IMPACT_SUMMARY.parent))


def summary_from_optional_path(path: Path | None) -> ActionImpactSummary:
    if path is None or not path.exists():
        return empty_summary(root=path.parent if path else None)
    return load_summary_from_json(path)


def _maybe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_dict(payload: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in payload.items():
        parsed = _maybe_float(value)
        if parsed is not None:
            out[str(key)] = parsed
    return out


def _string_list(payload: Any) -> list[str]:
    if isinstance(payload, list):
        return [str(item) for item in payload]
    if payload is None:
        return []
    return [str(payload)]


def _maybe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    if isinstance(value, int):
        return bool(value)
    return None


def _metric_means(records: list[ActionImpactRecordView]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for record in records:
        if record.actual_impact is None:
            continue
        grouped.setdefault(record.objective_metric, []).append(record.actual_impact)
    return {
        metric: sum(values) / len(values)
        for metric, values in grouped.items()
        if values
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read a tenant action-impact summary.")
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_ACTION_IMPACT_SUMMARY)
    args = parser.parse_args(argv)
    summary = summary_from_optional_path(args.summary_json)
    print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
