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
import math
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.outcome_links import predicted_effect_from_dict


ImpactStatus = Literal["planned", "measured", "abandoned", "void"]
OptimizationScope = Literal["local", "project", "system"]
AttributionConfidence = Literal["low", "medium", "high"]
PolicyEvaluationStatus = Literal["blocked", "advisory", "promotable"]
PolicyEvaluationMethod = Literal["replay_match_conservative", "ips_ready", "doubly_robust_ready"]

DEFAULT_ACTION_IMPACT_SUMMARY = ORG_ROOT_DIR / "action_impact" / "action_impact_summary.json"
DEFAULT_POLICY_EVALUATIONS_LOG = ORG_ROOT_DIR / "action_impact" / "policy_evaluations.jsonl"
DEFAULT_POLICY_PROMOTION_PACKETS_LOG = ORG_ROOT_DIR / "action_impact" / "policy_promotion_packets.jsonl"


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
    context_features: dict[str, Any] = field(default_factory=dict)
    action_arm: str | None = None
    logging_policy_id: str | None = None
    logging_policy_probability: float | None = None
    reward: float | None = None
    reward_metric: str | None = None
    delayed_effect_window: str | None = None
    human_review_burden: float | None = None
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


@dataclass(frozen=True)
class OfflinePolicyEvaluationReport:
    """Conservative offline evaluation for a tenant-owned learned policy.

    This is not an optimizer. It is an auditable candidate-policy report over
    logged action-impact rows. Promotion remains a governance or learning-event
    decision outside this primitive.
    """

    evaluation_id: str
    evaluated_at_utc: str
    candidate_policy_id: str
    candidate_policy_ref: str | None
    method: PolicyEvaluationMethod | str
    status: PolicyEvaluationStatus | str
    objective_metric: str | None
    context_keys: list[str]
    n_logged: int
    n_eligible: int
    n_matched: int
    support_coverage: float
    baseline_mean_reward: float | None
    candidate_mean_reward: float | None
    delta_mean_reward: float | None
    candidate_reward_ci95_low: float | None
    candidate_reward_ci95_high: float | None
    negative_externality_rate: float
    human_review_rate: float
    has_logging_propensities: bool
    has_counterfactuals: bool
    has_guardrail_metrics: bool
    promotion_blockers: list[str] = field(default_factory=list)
    guardrail_notes: list[str] = field(default_factory=list)
    matched_action_ids: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def promotion_allowed(self) -> bool:
        return self.status == "promotable" and not self.promotion_blockers

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["promotion_allowed"] = self.promotion_allowed
        return payload


@dataclass(frozen=True)
class PolicyPromotionPacket:
    """Governance-facing packet for a candidate learned policy.

    The packet is a review artifact. It does not apply a policy, approve a
    governance change, or promote a learning event.
    """

    packet_id: str
    created_at_utc: str
    status: Literal["blocked", "advisory", "review_ready"] | str
    candidate_policy_id: str
    candidate_policy_ref: str | None
    evaluation_report: OfflinePolicyEvaluationReport
    proposed_by: str
    target_ref: str
    governance_change_candidate: dict[str, Any]
    guardrail_summary: dict[str, Any]
    authority_diff_ref: str | None = None
    formal_verification_refs: list[str] = field(default_factory=list)
    learning_event_refs: list[str] = field(default_factory=list)
    review_blockers: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evaluation_report"] = self.evaluation_report.as_dict()
        return payload


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
    reward = _maybe_float(payload["reward"] if "reward" in payload else payload.get("actual_impact"))
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
        context_features={
            str(k): v
            for k, v in (payload.get("context_features") or payload.get("context") or {}).items()
        }
        if isinstance(payload.get("context_features") or payload.get("context") or {}, dict)
        else {},
        action_arm=payload.get("action_arm") or payload.get("arm") or payload.get("chosen_arm"),
        logging_policy_id=payload.get("logging_policy_id") or payload.get("behavior_policy_id"),
        logging_policy_probability=_maybe_float(
            payload.get("logging_policy_probability")
            if "logging_policy_probability" in payload
            else payload.get("propensity")
        ),
        reward=reward,
        reward_metric=payload.get("reward_metric") or payload.get("objective_metric") or payload.get("metric"),
        delayed_effect_window=payload.get("delayed_effect_window") or payload.get("outcome_window"),
        human_review_burden=_maybe_float(payload.get("human_review_burden")),
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
                "context_features",
                "context",
                "action_arm",
                "arm",
                "chosen_arm",
                "logging_policy_id",
                "behavior_policy_id",
                "logging_policy_probability",
                "propensity",
                "reward",
                "reward_metric",
                "delayed_effect_window",
                "outcome_window",
                "human_review_burden",
                "guardrail_metrics",
                "externalities",
                "measurement_ref",
                "requires_human_review",
                "notes",
                "verdict",
            }
        },
    )


def evaluate_offline_policy_candidate(
    records: list[ActionImpactRecordView],
    *,
    candidate_policy_id: str,
    candidate_action_by_context: dict[str, str],
    context_keys: list[str],
    candidate_policy_ref: str | None = None,
    objective_metric: str | None = None,
    min_matched: int = 20,
    min_support_coverage: float = 0.25,
    max_negative_externality_rate: float = 0.0,
    max_human_review_rate: float = 0.25,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> OfflinePolicyEvaluationReport:
    """Evaluate a candidate policy by conservative replay over logged rows.

    ``candidate_action_by_context`` maps a stable context signature to the arm
    the candidate policy would choose. The signature is built from
    ``context_keys`` using JSON with sorted keys. A row contributes to the
    candidate estimate only when the candidate arm matches the logged arm.

    This is intentionally stricter than a full off-policy estimator. It gives a
    safe first report from thin logs while preserving propensity and guardrail
    fields for tenant-owned IPS/DR implementations.
    """
    if not candidate_policy_id.strip():
        raise ValueError("candidate_policy_id is required")
    if not context_keys:
        raise ValueError("context_keys is required")
    if min_matched < 1:
        raise ValueError("min_matched must be >= 1")
    if not 0 <= min_support_coverage <= 1:
        raise ValueError("min_support_coverage must be between 0 and 1")

    logged = [
        record
        for record in records
        if record.status == "measured"
        and (objective_metric is None or record.objective_metric == objective_metric)
        and record.reward is not None
    ]
    eligible: list[ActionImpactRecordView] = []
    matched: list[ActionImpactRecordView] = []
    for record in logged:
        if not record.action_arm:
            continue
        signature = context_signature(record.context_features, context_keys)
        if signature is None:
            continue
        candidate_arm = candidate_action_by_context.get(signature)
        if candidate_arm is None:
            continue
        eligible.append(record)
        if candidate_arm == record.action_arm:
            matched.append(record)

    baseline_rewards = [record.reward for record in eligible if record.reward is not None]
    candidate_rewards = [record.reward for record in matched if record.reward is not None]
    baseline_mean = _mean(baseline_rewards)
    candidate_mean = _mean(candidate_rewards)
    delta = (
        None
        if baseline_mean is None or candidate_mean is None
        else candidate_mean - baseline_mean
    )
    ci_low, ci_high = _ci95(candidate_rewards)
    support = len(matched) / len(eligible) if eligible else 0.0
    negative_externality_rate = _negative_externality_rate(matched)
    human_review_rate = _human_review_rate(matched)
    blockers: list[str] = []
    notes: list[str] = []

    if len(eligible) == 0:
        blockers.append("no eligible measured rows for candidate policy")
    if len(matched) < min_matched:
        blockers.append(f"matched rows below threshold: {len(matched)} < {min_matched}")
    if support < min_support_coverage:
        blockers.append(
            f"support coverage below threshold: {support:.3f} < {min_support_coverage:.3f}"
        )
    if delta is None:
        blockers.append("candidate reward delta unavailable")
    elif delta <= 0:
        blockers.append(f"candidate does not beat logged baseline: delta={delta:.3f}")
    if negative_externality_rate > max_negative_externality_rate:
        blockers.append(
            "negative externality rate above threshold: "
            f"{negative_externality_rate:.3f} > {max_negative_externality_rate:.3f}"
        )
    if human_review_rate > max_human_review_rate:
        blockers.append(
            f"human review rate above threshold: {human_review_rate:.3f} > {max_human_review_rate:.3f}"
        )

    has_logging_propensities = all(
        record.logging_policy_probability is not None for record in eligible
    ) if eligible else False
    has_counterfactuals = all(record.counterfactual_action for record in eligible) if eligible else False
    has_guardrails = any(record.guardrail_metrics for record in eligible)
    if not has_logging_propensities:
        notes.append("logging propensities missing or incomplete; report uses replay-match only")
    if not has_counterfactuals:
        notes.append("counterfactual actions missing or incomplete")
    if not has_guardrails:
        notes.append("guardrail metrics missing")

    if blockers:
        status: PolicyEvaluationStatus = "blocked"
    elif ci_low is not None and ci_low <= (baseline_mean or 0):
        status = "advisory"
        notes.append("candidate mean improved, but lower confidence bound does not clear baseline")
    else:
        status = "promotable"

    return OfflinePolicyEvaluationReport(
        evaluation_id=f"ope_{uuid.uuid4().hex[:12]}",
        evaluated_at_utc=_now_iso(),
        candidate_policy_id=candidate_policy_id,
        candidate_policy_ref=candidate_policy_ref,
        method="replay_match_conservative",
        status=status,
        objective_metric=objective_metric,
        context_keys=list(context_keys),
        n_logged=len(logged),
        n_eligible=len(eligible),
        n_matched=len(matched),
        support_coverage=support,
        baseline_mean_reward=baseline_mean,
        candidate_mean_reward=candidate_mean,
        delta_mean_reward=delta,
        candidate_reward_ci95_low=ci_low,
        candidate_reward_ci95_high=ci_high,
        negative_externality_rate=negative_externality_rate,
        human_review_rate=human_review_rate,
        has_logging_propensities=has_logging_propensities,
        has_counterfactuals=has_counterfactuals,
        has_guardrail_metrics=has_guardrails,
        promotion_blockers=blockers,
        guardrail_notes=notes,
        matched_action_ids=[record.action_id for record in matched],
        evidence_refs=evidence_refs or [],
        metadata=metadata or {},
    )


def append_policy_evaluation(
    report: OfflinePolicyEvaluationReport,
    *,
    log_path: Path | None = None,
) -> OfflinePolicyEvaluationReport:
    path = log_path or DEFAULT_POLICY_EVALUATIONS_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report.as_dict(), sort_keys=True) + "\n")
    return report


def list_policy_evaluations(
    *,
    log_path: Path | None = None,
    candidate_policy_id: str | None = None,
    status: PolicyEvaluationStatus | str | None = None,
) -> list[OfflinePolicyEvaluationReport]:
    out: list[OfflinePolicyEvaluationReport] = []
    for row in _read_jsonl(log_path or DEFAULT_POLICY_EVALUATIONS_LOG):
        report = _policy_evaluation_from_mapping(row)
        if candidate_policy_id is not None and report.candidate_policy_id != candidate_policy_id:
            continue
        if status is not None and report.status != status:
            continue
        out.append(report)
    return out


def load_policy_evaluation_from_json(path: Path) -> OfflinePolicyEvaluationReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("policy evaluation JSON must be an object")
    return _policy_evaluation_from_mapping(payload)


def get_policy_evaluation(
    evaluation_id: str,
    *,
    log_path: Path | None = None,
) -> OfflinePolicyEvaluationReport:
    for report in list_policy_evaluations(log_path=log_path):
        if report.evaluation_id == evaluation_id:
            return report
    raise ValueError(f"policy evaluation not found: {evaluation_id}")


def build_policy_promotion_packet(
    report: OfflinePolicyEvaluationReport,
    *,
    proposed_by: str,
    target_ref: str | None = None,
    title: str | None = None,
    rationale: str | None = None,
    expected_behavior_change: str | None = None,
    rollback_plan: str | None = None,
    predicted_effect: dict[str, Any] | None = None,
    authority_diff_ref: str | None = None,
    formal_verification_refs: list[str] | None = None,
    learning_event_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> PolicyPromotionPacket:
    """Build a governance-facing packet from an offline policy report."""
    if not proposed_by.strip():
        raise ValueError("proposed_by is required")
    resolved_target = target_ref or report.candidate_policy_ref or f"policy:{report.candidate_policy_id}"
    review_blockers = list(report.promotion_blockers)
    if report.status == "blocked":
        status = "blocked"
    elif report.status == "advisory":
        status = "advisory"
    else:
        status = "review_ready"
    if not report.has_guardrail_metrics:
        review_blockers.append("guardrail metrics missing")
    if not authority_diff_ref:
        review_blockers.append("authority diff not attached")
    if status == "review_ready" and review_blockers:
        status = "advisory"

    guardrail_summary = {
        "negative_externality_rate": report.negative_externality_rate,
        "human_review_rate": report.human_review_rate,
        "has_guardrail_metrics": report.has_guardrail_metrics,
        "guardrail_notes": list(report.guardrail_notes),
        "support_coverage": report.support_coverage,
        "candidate_reward_ci95_low": report.candidate_reward_ci95_low,
        "candidate_reward_ci95_high": report.candidate_reward_ci95_high,
    }
    source_refs = [
        f"action_impact_policy_evaluation:{report.evaluation_id}",
        *report.evidence_refs,
        *(evidence_refs or []),
    ]
    if authority_diff_ref:
        source_refs.append(authority_diff_ref)
    source_refs.extend(formal_verification_refs or [])
    source_refs.extend(learning_event_refs or [])

    governance_change_candidate = {
        "change_kind": "route_policy_change",
        "title": title or f"Review candidate policy {report.candidate_policy_id}",
        "proposed_by": proposed_by,
        "target_ref": resolved_target,
        "rationale": rationale
        or (
            f"Offline policy evaluation {report.evaluation_id} produced status "
            f"{report.status!r} with delta_mean_reward={report.delta_mean_reward!r}."
        ),
        "source_refs": source_refs,
        "expected_behavior_change": expected_behavior_change
        or "Route matching contexts to the candidate action arms after governance review.",
        "risk_summary": (
            "support_coverage="
            f"{report.support_coverage:.3f}; negative_externality_rate="
            f"{report.negative_externality_rate:.3f}; human_review_rate="
            f"{report.human_review_rate:.3f}; status={report.status}"
        ),
        "rollback_plan": rollback_plan or "Revert to the prior routing policy and keep the evaluation packet as evidence.",
        "metadata": {
            "packet_kind": "policy_promotion_packet",
            "candidate_policy_id": report.candidate_policy_id,
            "policy_evaluation_id": report.evaluation_id,
        },
    }
    if predicted_effect is not None:
        governance_change_candidate["predicted_effect"] = predicted_effect_from_dict(
            predicted_effect
        ).as_dict()

    return PolicyPromotionPacket(
        packet_id=f"ppp_{uuid.uuid4().hex[:12]}",
        created_at_utc=_now_iso(),
        status=status,
        candidate_policy_id=report.candidate_policy_id,
        candidate_policy_ref=report.candidate_policy_ref,
        evaluation_report=report,
        proposed_by=proposed_by,
        target_ref=resolved_target,
        governance_change_candidate=governance_change_candidate,
        guardrail_summary=guardrail_summary,
        authority_diff_ref=authority_diff_ref,
        formal_verification_refs=formal_verification_refs or [],
        learning_event_refs=learning_event_refs or [],
        review_blockers=review_blockers,
        evidence_refs=source_refs,
        metadata=metadata or {},
    )


def append_policy_promotion_packet(
    packet: PolicyPromotionPacket,
    *,
    log_path: Path | None = None,
) -> PolicyPromotionPacket:
    path = log_path or DEFAULT_POLICY_PROMOTION_PACKETS_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(packet.as_dict(), sort_keys=True) + "\n")
    return packet


def get_policy_promotion_packet(
    packet_id: str,
    *,
    log_path: Path | None = None,
) -> PolicyPromotionPacket:
    for packet in list_policy_promotion_packets(log_path=log_path):
        if packet.packet_id == packet_id:
            return packet
    raise ValueError(f"policy promotion packet not found: {packet_id}")


def build_policy_promotion_governance_change_request(
    packet: PolicyPromotionPacket,
    *,
    proposal_id: str | None = None,
    owner_role: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    invariant_checks: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    require_review_ready: bool = True,
) -> dict[str, Any]:
    """Project a policy-promotion packet into a governance-change request.

    This is a composition helper, not an approval or policy writer. It preserves
    the packet as evidence and lets the governance-change protocol decide
    whether the resulting proposal is review-ready.
    """
    if require_review_ready and packet.status != "review_ready":
        raise ValueError(
            "policy promotion packet must be review_ready before opening a "
            f"governance change; got {packet.status!r}"
        )
    candidate = dict(packet.governance_change_candidate)
    packet_ref = f"policy_promotion_packet:{packet.packet_id}"
    source_refs = _string_list(candidate.get("source_refs"))
    if packet_ref not in source_refs:
        source_refs.append(packet_ref)
    candidate_metadata = dict(candidate.get("metadata") or {})
    request_metadata = {
        **candidate_metadata,
        "source_recipe": "policy_promotion_packet_governance_change_request.v1",
        "source_policy_promotion_packet_id": packet.packet_id,
        "source_policy_promotion_packet_ref": packet_ref,
        "candidate_policy_id": packet.candidate_policy_id,
        "policy_evaluation_id": packet.evaluation_report.evaluation_id,
        **(metadata or {}),
    }
    request = {
        "change_kind": candidate.get("change_kind") or "route_policy_change",
        "title": candidate.get("title") or f"Review candidate policy {packet.candidate_policy_id}",
        "proposed_by": candidate.get("proposed_by") or packet.proposed_by,
        "target_ref": candidate.get("target_ref") or packet.target_ref,
        "rationale": candidate.get("rationale") or (
            f"Policy promotion packet {packet.packet_id} requests governance review "
            f"for candidate policy {packet.candidate_policy_id}."
        ),
        "source_refs": source_refs,
        "expected_behavior_change": candidate.get("expected_behavior_change"),
        "predicted_effect": candidate.get("predicted_effect"),
        "risk_summary": candidate.get("risk_summary"),
        "rollback_plan": candidate.get("rollback_plan"),
        "metadata": request_metadata,
    }
    if proposal_id:
        request["proposal_id"] = proposal_id
    if owner_role:
        request["owner_role"] = owner_role
    if tenant_id:
        request["tenant_id"] = tenant_id
    if project_id:
        request["project_id"] = project_id
    if invariant_checks is not None:
        request["invariant_checks"] = invariant_checks
    return request


def list_policy_promotion_packets(
    *,
    log_path: Path | None = None,
    candidate_policy_id: str | None = None,
    status: str | None = None,
) -> list[PolicyPromotionPacket]:
    out: list[PolicyPromotionPacket] = []
    for row in _read_jsonl(log_path or DEFAULT_POLICY_PROMOTION_PACKETS_LOG):
        report_payload = row.pop("evaluation_report")
        report_payload.pop("promotion_allowed", None)
        packet = PolicyPromotionPacket(
            **row,
            evaluation_report=OfflinePolicyEvaluationReport(**report_payload),
        )
        if candidate_policy_id is not None and packet.candidate_policy_id != candidate_policy_id:
            continue
        if status is not None and packet.status != status:
            continue
        out.append(packet)
    return out


def _policy_evaluation_from_mapping(payload: dict[str, Any]) -> OfflinePolicyEvaluationReport:
    row = dict(payload)
    row.pop("promotion_allowed", None)
    return OfflinePolicyEvaluationReport(**row)


def context_signature(context_features: dict[str, Any], context_keys: list[str]) -> str | None:
    if any(key not in context_features for key in context_keys):
        return None
    payload = {key: context_features[key] for key in context_keys}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


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


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _ci95(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    mean = sum(values) / len(values)
    if len(values) == 1:
        return mean, mean
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    margin = 1.96 * math.sqrt(variance / len(values))
    return mean - margin, mean + margin


def _negative_externality_rate(records: list[ActionImpactRecordView]) -> float:
    if not records:
        return 0.0
    count = 0
    for record in records:
        if record.negative_externality_tags or any(value < 0 for value in record.externalities.values()):
            count += 1
    return count / len(records)


def _human_review_rate(records: list[ActionImpactRecordView]) -> float:
    if not records:
        return 0.0
    return sum(1 for record in records if record.requires_human_review) / len(records)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read action-impact state and offline policy reports.")
    subparsers = parser.add_subparsers(dest="command")
    summary_parser = subparsers.add_parser("summary", help="Read a tenant action-impact summary.")
    summary_parser.add_argument("--summary-json", type=Path, default=DEFAULT_ACTION_IMPACT_SUMMARY)

    eval_parser = subparsers.add_parser(
        "evaluate-policy",
        help="Evaluate a candidate policy by conservative replay over action-impact rows.",
    )
    eval_parser.add_argument("--summary-json", type=Path, default=DEFAULT_ACTION_IMPACT_SUMMARY)
    eval_parser.add_argument("--candidate-policy-id", required=True)
    eval_parser.add_argument("--candidate-policy-ref")
    eval_parser.add_argument(
        "--candidate-action-map",
        type=Path,
        required=True,
        help="JSON object mapping context signatures to candidate action arms.",
    )
    eval_parser.add_argument("--context-key", action="append", dest="context_keys", required=True)
    eval_parser.add_argument("--objective-metric")
    eval_parser.add_argument("--min-matched", type=int, default=20)
    eval_parser.add_argument("--min-support-coverage", type=float, default=0.25)
    eval_parser.add_argument("--max-negative-externality-rate", type=float, default=0.0)
    eval_parser.add_argument("--max-human-review-rate", type=float, default=0.25)
    eval_parser.add_argument("--record", action="store_true")
    eval_parser.add_argument("--policy-evaluations-log", type=Path, default=DEFAULT_POLICY_EVALUATIONS_LOG)

    packet_parser = subparsers.add_parser(
        "build-promotion-packet",
        help="Build a governance review packet from an offline policy evaluation.",
    )
    packet_source = packet_parser.add_mutually_exclusive_group(required=True)
    packet_source.add_argument("--evaluation-json", type=Path)
    packet_source.add_argument("--evaluation-id")
    packet_parser.add_argument("--policy-evaluations-log", type=Path, default=DEFAULT_POLICY_EVALUATIONS_LOG)
    packet_parser.add_argument("--proposed-by", required=True)
    packet_parser.add_argument("--target-ref")
    packet_parser.add_argument("--title")
    packet_parser.add_argument("--rationale")
    packet_parser.add_argument("--expected-behavior-change")
    packet_parser.add_argument("--rollback-plan")
    packet_parser.add_argument("--authority-diff-ref")
    packet_parser.add_argument("--formal-verification-ref", action="append", default=[])
    packet_parser.add_argument("--learning-event-ref", action="append", default=[])
    packet_parser.add_argument("--evidence-ref", action="append", default=[])
    packet_parser.add_argument("--record", action="store_true")
    packet_parser.add_argument(
        "--policy-promotion-packets-log",
        type=Path,
        default=DEFAULT_POLICY_PROMOTION_PACKETS_LOG,
    )

    args = parser.parse_args(argv)
    if args.command in {None, "summary"}:
        summary = summary_from_optional_path(args.summary_json)
        print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
        return 0

    if args.command == "evaluate-policy":
        summary = summary_from_optional_path(args.summary_json)
        candidate_action_by_context = json.loads(args.candidate_action_map.read_text(encoding="utf-8"))
        if not isinstance(candidate_action_by_context, dict):
            raise ValueError("candidate action map must be a JSON object")
        report = evaluate_offline_policy_candidate(
            summary.records,
            candidate_policy_id=args.candidate_policy_id,
            candidate_policy_ref=args.candidate_policy_ref,
            candidate_action_by_context={str(k): str(v) for k, v in candidate_action_by_context.items()},
            context_keys=args.context_keys,
            objective_metric=args.objective_metric,
            min_matched=args.min_matched,
            min_support_coverage=args.min_support_coverage,
            max_negative_externality_rate=args.max_negative_externality_rate,
            max_human_review_rate=args.max_human_review_rate,
        )
        if args.record:
            append_policy_evaluation(report, log_path=args.policy_evaluations_log)
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
        return 0

    if args.command == "build-promotion-packet":
        if args.evaluation_json:
            report = load_policy_evaluation_from_json(args.evaluation_json)
        else:
            report = get_policy_evaluation(args.evaluation_id, log_path=args.policy_evaluations_log)
        packet = build_policy_promotion_packet(
            report,
            proposed_by=args.proposed_by,
            target_ref=args.target_ref,
            title=args.title,
            rationale=args.rationale,
            expected_behavior_change=args.expected_behavior_change,
            rollback_plan=args.rollback_plan,
            authority_diff_ref=args.authority_diff_ref,
            formal_verification_refs=args.formal_verification_ref,
            learning_event_refs=args.learning_event_ref,
            evidence_refs=args.evidence_ref,
        )
        if args.record:
            append_policy_promotion_packet(packet, log_path=args.policy_promotion_packets_log)
        print(json.dumps(packet.as_dict(), indent=2, sort_keys=True))
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
