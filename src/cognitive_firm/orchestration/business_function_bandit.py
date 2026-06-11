"""Offline business-function policy proposer.

This module is a thin candidate generator over action-impact rows. It does not
run online exploration, write live routing policy, or decide authority. It only
builds a candidate context->arm map that can be evaluated by
``evaluate_offline_policy_candidate`` and then reviewed through governance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from cognitive_firm.orchestration.action_impact import ActionImpactRecordView, context_signature


@dataclass(frozen=True)
class ArmAggregate:
    context_signature: str
    action_arm: str
    n_rows: int
    mean_reward: float
    baseline_mean_reward: float
    delta_mean_reward: float
    negative_externality_rate: float
    human_review_rate: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BusinessFunctionPolicyCandidate:
    candidate_policy_id: str
    objective_metric: str | None
    context_keys: list[str]
    candidate_action_by_context: dict[str, str]
    selected_arms: list[ArmAggregate] = field(default_factory=list)
    rejected_contexts: list[dict[str, Any]] = field(default_factory=list)
    n_logged: int = 0
    n_eligible: int = 0
    n_contexts: int = 0
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "candidate" if self.candidate_action_by_context else "no_candidate"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status
        payload["selected_arms"] = [arm.as_dict() for arm in self.selected_arms]
        return payload


def propose_business_function_policy(
    records: list[ActionImpactRecordView],
    *,
    candidate_policy_id: str,
    context_keys: list[str],
    objective_metric: str | None = None,
    min_context_rows: int = 10,
    min_arm_rows: int = 5,
    min_reward_delta: float = 0.0,
    max_negative_externality_rate: float = 0.0,
    max_human_review_rate: float = 0.25,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> BusinessFunctionPolicyCandidate:
    """Propose a conservative context->arm map from measured rows.

    The function only uses rows with measured rewards, action arms, and the
    requested context keys. A context receives a candidate arm only when an arm
    has enough logged rows, beats the context baseline by ``min_reward_delta``,
    and stays within the negative-externality and human-review thresholds.
    """
    if not candidate_policy_id.strip():
        raise ValueError("candidate_policy_id is required")
    if not context_keys:
        raise ValueError("context_keys is required")
    if min_context_rows < 1:
        raise ValueError("min_context_rows must be >= 1")
    if min_arm_rows < 1:
        raise ValueError("min_arm_rows must be >= 1")
    if not 0 <= max_negative_externality_rate <= 1:
        raise ValueError("max_negative_externality_rate must be between 0 and 1")
    if not 0 <= max_human_review_rate <= 1:
        raise ValueError("max_human_review_rate must be between 0 and 1")

    logged = [
        record
        for record in records
        if record.status == "measured"
        and record.reward is not None
        and record.action_arm
        and (objective_metric is None or record.objective_metric == objective_metric)
    ]
    grouped: dict[str, list[ActionImpactRecordView]] = {}
    for record in logged:
        signature = context_signature(record.context_features, context_keys)
        if signature is None:
            continue
        grouped.setdefault(signature, []).append(record)

    candidate_map: dict[str, str] = {}
    selected: list[ArmAggregate] = []
    rejected: list[dict[str, Any]] = []

    for signature in sorted(grouped):
        context_rows = grouped[signature]
        baseline = _mean([record.reward for record in context_rows if record.reward is not None])
        if baseline is None or len(context_rows) < min_context_rows:
            rejected.append(
                {
                    "context_signature": signature,
                    "reason": "context rows below threshold",
                    "n_rows": len(context_rows),
                    "required": min_context_rows,
                }
            )
            continue

        arms: list[ArmAggregate] = []
        for arm_name, arm_rows in sorted(_group_by_arm(context_rows).items()):
            rewards = [record.reward for record in arm_rows if record.reward is not None]
            mean_reward = _mean(rewards)
            if mean_reward is None:
                continue
            aggregate = ArmAggregate(
                context_signature=signature,
                action_arm=arm_name,
                n_rows=len(arm_rows),
                mean_reward=mean_reward,
                baseline_mean_reward=baseline,
                delta_mean_reward=mean_reward - baseline,
                negative_externality_rate=_negative_externality_rate(arm_rows),
                human_review_rate=_human_review_rate(arm_rows),
            )
            arms.append(aggregate)

        admissible = [
            arm
            for arm in arms
            if arm.n_rows >= min_arm_rows
            and arm.delta_mean_reward > min_reward_delta
            and arm.negative_externality_rate <= max_negative_externality_rate
            and arm.human_review_rate <= max_human_review_rate
        ]
        if not admissible:
            rejected.append(
                {
                    "context_signature": signature,
                    "reason": "no arm passed support, reward, and guardrail thresholds",
                    "n_rows": len(context_rows),
                    "arms": [arm.as_dict() for arm in arms],
                }
            )
            continue

        best = max(admissible, key=lambda arm: (arm.mean_reward, arm.n_rows, arm.action_arm))
        candidate_map[signature] = best.action_arm
        selected.append(best)

    return BusinessFunctionPolicyCandidate(
        candidate_policy_id=candidate_policy_id,
        objective_metric=objective_metric,
        context_keys=list(context_keys),
        candidate_action_by_context=candidate_map,
        selected_arms=selected,
        rejected_contexts=rejected,
        n_logged=len(logged),
        n_eligible=sum(len(rows) for rows in grouped.values()),
        n_contexts=len(grouped),
        evidence_refs=evidence_refs or [],
        metadata=metadata or {},
    )


def _group_by_arm(records: list[ActionImpactRecordView]) -> dict[str, list[ActionImpactRecordView]]:
    grouped: dict[str, list[ActionImpactRecordView]] = {}
    for record in records:
        if record.action_arm:
            grouped.setdefault(record.action_arm, []).append(record)
    return grouped


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


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
