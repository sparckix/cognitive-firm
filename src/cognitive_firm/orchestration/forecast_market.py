"""Forecast-market interface for tenant implementations.

The public kernel owns the portable lifecycle vocabulary and read-model shape.
Tenant overlays own the concrete market implementation: contract materializers,
forecaster wakeups, resolvers, calibration policy, and domain-specific scoring.

This prevents duplicating mature tenant systems while still letting Orbit,
daemons, and human operators consume a stable kernel-facing surface.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from cognitive_firm.common.paths import REPO_ROOT


ForecastLayer = Literal["macro", "meso", "micro"]
AllocationAction = Literal[
    "run_now",
    "split_contract",
    "ask_another_independent_agent",
    "defer",
    "kill_branch",
    "request_evidence",
    "request_human_work",
]
ForecastLifecycleState = Literal[
    "forecast_requested",
    "forecast_fulfilled",
    "aggregate_ready",
    "resolved_unscored",
    "resolved_scored",
    "voided",
    "malformed",
    "unknown",
]

DEFAULT_FORECAST_MARKET_ROOT = REPO_ROOT / "org" / "forecast_market"


@dataclass(frozen=True)
class ForecastContractView:
    contract_id: str
    layer: ForecastLayer | str
    question: str
    task_type: str | None = None
    objective_resolver: str | None = None
    success_threshold: str | None = None
    horizon: str | None = None
    artifact_paths: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AllocationRecommendation:
    action: AllocationAction | str
    reason: str
    voi_proxy: float | None = None
    p_success: float | None = None
    expected_value: float | None = None
    forecast_spread: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ForecastMarketContractState:
    contract_id: str
    lifecycle_state: ForecastLifecycleState | str
    next_action: str
    contract: ForecastContractView | None = None
    latest_forecast_count: int = 0
    effective_independent_forecaster_count: int | None = None
    aggregate: dict[str, Any] = field(default_factory=dict)
    allocation_recommendation: AllocationRecommendation | None = None
    score: dict[str, Any] = field(default_factory=dict)
    decision_use: dict[str, Any] = field(default_factory=dict)
    externality_summary: dict[str, Any] = field(default_factory=dict)
    artifact_paths: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ForecastMarketSummary:
    root: str | None
    n_contracts: int = 0
    n_awaiting_forecasts: int = 0
    n_aggregate_debt: int = 0
    n_score_debt: int = 0
    n_decision_use_rows: int = 0
    n_score_rows: int = 0
    n_high_confidence_misses: int = 0
    contracts: list[ForecastMarketContractState] = field(default_factory=list)
    reflexive_insights: list[dict[str, Any]] = field(default_factory=list)
    maintenance_items: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ForecastMarketAdapter(Protocol):
    """Read-only adapter implemented by tenant forecast markets."""

    def market_summary(self) -> ForecastMarketSummary:
        """Return the generic market state consumed by the kernel."""

    def contract_state(self, contract_id: str) -> ForecastMarketContractState:
        """Return one contract's generic state."""


def load_summary_from_json(path: Path) -> ForecastMarketSummary:
    """Load an adapter-produced summary JSON into the kernel shape."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return summary_from_mapping(payload, root=str(path.parent))


def summary_from_mapping(payload: dict[str, Any], *, root: str | None = None) -> ForecastMarketSummary:
    """Normalize a tenant summary/read model to the generic kernel shape.

    This accepts both native cognitive-firm summaries and richer tenant payloads
    with fields such as `contract_count`, `resolved_without_score`, or
    `reflexive_insights`.
    """
    rows = payload.get("contracts") or []
    contracts: list[ForecastMarketContractState] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            contracts.append(contract_state_from_mapping(row))

    resolved_without_score = payload.get("resolved_without_score")
    aggregate_missing = payload.get("aggregate_missing")
    awaiting_forecasts = payload.get("awaiting_forecasts")
    decision_use = payload.get("decision_use") or {}
    reliability = payload.get("reliability") or {}
    reflexive = payload.get("reflexive_insights") or {}
    maintenance = payload.get("maintenance_plan") or {}

    return ForecastMarketSummary(
        root=root or payload.get("forecast_pool_root") or payload.get("root"),
        n_contracts=int(payload.get("n_contracts") or payload.get("contract_count") or len(contracts)),
        n_awaiting_forecasts=_count_or_len(awaiting_forecasts, payload.get("n_awaiting_forecasts")),
        n_aggregate_debt=_count_or_len(aggregate_missing, payload.get("n_aggregate_debt")),
        n_score_debt=_count_or_len(resolved_without_score, payload.get("n_score_debt")),
        n_decision_use_rows=int(
            payload.get("n_decision_use_rows")
            or decision_use.get("rows")
            or 0
        ),
        n_score_rows=int(
            payload.get("n_score_rows")
            or reliability.get("score_rows")
            or 0
        ),
        n_high_confidence_misses=int(
            payload.get("n_high_confidence_misses")
            or reliability.get("high_confidence_miss_count")
            or 0
        ),
        contracts=contracts,
        reflexive_insights=_extract_items(reflexive, "insights"),
        maintenance_items=_extract_items(maintenance, "items"),
    )


def contract_state_from_mapping(payload: dict[str, Any]) -> ForecastMarketContractState:
    """Normalize one tenant contract read model."""
    contract_payload = payload.get("contract")
    contract = None
    if isinstance(contract_payload, dict):
        contract = ForecastContractView(
            contract_id=str(payload.get("contract_id") or contract_payload.get("contract_id") or ""),
            layer=str(contract_payload.get("layer") or ""),
            question=str(contract_payload.get("question") or ""),
            task_type=contract_payload.get("task_type"),
            objective_resolver=contract_payload.get("objective_resolver"),
            success_threshold=contract_payload.get("success_threshold"),
            horizon=contract_payload.get("horizon"),
            artifact_paths={
                str(k): str(v)
                for k, v in (contract_payload.get("artifact_paths") or {}).items()
            },
        )

    lifecycle = payload.get("lifecycle") or {}
    forecasts = payload.get("forecasts") or {}
    aggregate = payload.get("aggregate") or {}
    score = payload.get("score") or {}
    decision_use = payload.get("decision_use") or {}
    recommendation = aggregate.get("allocation_recommendation") or payload.get("allocation_recommendation")

    return ForecastMarketContractState(
        contract_id=str(payload.get("contract_id") or (contract.contract_id if contract else "")),
        lifecycle_state=str(lifecycle.get("state") or payload.get("lifecycle_state") or "unknown"),
        next_action=str(lifecycle.get("next_action") or payload.get("next_action") or "unknown"),
        contract=contract,
        latest_forecast_count=int(
            forecasts.get("latest_count")
            if isinstance(forecasts, dict) and forecasts.get("latest_count") is not None
            else payload.get("forecast_count") or 0
        ),
        effective_independent_forecaster_count=_maybe_int(
            (payload.get("effective_independence") or {}).get("effective_n")
        ),
        aggregate=aggregate if isinstance(aggregate, dict) else {},
        allocation_recommendation=_allocation_from_mapping(recommendation),
        score=score if isinstance(score, dict) else {},
        decision_use=decision_use if isinstance(decision_use, dict) else {},
        externality_summary=payload.get("externality_summary") if isinstance(payload.get("externality_summary"), dict) else {},
        artifact_paths=payload.get("artifact_paths") if isinstance(payload.get("artifact_paths"), dict) else {},
        warnings=payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
    )


def empty_summary(*, root: Path | None = None) -> ForecastMarketSummary:
    return ForecastMarketSummary(root=str(root or DEFAULT_FORECAST_MARKET_ROOT))


def market_summary_from_optional_path(path: Path | None) -> ForecastMarketSummary:
    if path is None or not path.exists():
        return empty_summary(root=path)
    return load_summary_from_json(path)


def _allocation_from_mapping(payload: Any) -> AllocationRecommendation | None:
    if not isinstance(payload, dict):
        return None
    return AllocationRecommendation(
        action=str(payload.get("action") or "unknown"),
        reason=str(payload.get("reason") or ""),
        voi_proxy=_maybe_float(payload.get("voi_proxy")),
        p_success=_maybe_float(payload.get("p_success")),
        expected_value=_maybe_float(payload.get("expected_value")),
        forecast_spread=_maybe_float(payload.get("forecast_spread")),
        metadata={
            str(k): v
            for k, v in payload.items()
            if k not in {"action", "reason", "voi_proxy", "p_success", "expected_value", "forecast_spread"}
        },
    )


def _count_or_len(payload: Any, fallback: Any = None) -> int:
    if isinstance(payload, dict) and "count" in payload:
        return int(payload.get("count") or 0)
    if isinstance(payload, list):
        return len(payload)
    if fallback is not None:
        return int(fallback or 0)
    return 0


def _extract_items(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        rows = payload.get(key) or payload.get("items") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def _maybe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _maybe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read a tenant forecast-market summary.")
    parser.add_argument("--summary-json", type=Path)
    args = parser.parse_args(argv)

    summary = market_summary_from_optional_path(args.summary_json)
    print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
