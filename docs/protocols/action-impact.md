# Action Impact Interface

**Module:** `cognitive_firm.orchestration.action_impact`

The action-impact interface lets cognitive-firm consume measured intervention
outcomes without shipping a generic optimizer.

It is designed for tenants that want to connect actions to business impact,
scientific yield, operational throughput, or other measured outcomes. A tenant
may later train bandit or mini-RL policies over these rows, but the public
kernel does not choose actions from reward.

## What It Records

The portable `ActionImpactRecordView` shape includes:

- `action_id`
- `tenant_id`
- `project_id`
- `actor`
- `actor_role`
- `action_kind`
- `decision_stage`
- `action_ref`
- `objective_metric`
- `baseline_action`
- `counterfactual_action`
- `expected_effect`
- `observed_outcome`
- `impact_summary`
- `old_state`
- `new_state`
- `artifact_refs`
- `cost_units`
- `wall_seconds`
- `evaluator_role`
- `independence_boundary`
- `decision_changed_bool`
- `expected_impact`
- `actual_impact`
- `optimization_scope`
- `attribution_confidence`
- `forecast_contract_id`
- `context_features`
- `action_arm`
- `logging_policy_id`
- `logging_policy_probability`
- `reward`
- `reward_metric`
- `delayed_effect_window`
- `human_review_burden`
- `guardrail_metrics`
- `externalities`
- `externality_tags`
- `negative_externality_tags`
- `ignored_or_overridden_reason`
- `measurement_ref`
- `requires_human_review`
- `notes`

Tenants can add richer metadata. The adapter preserves unknown fields under
`metadata`.

## Why It Is Read-Model First

Action-impact loops are tempting because repeated actions can sometimes be
linked to P&L, scientific yield, or another measurable target. They are also
where local optimization risk enters:

- proxy metrics can Goodhart;
- local reward can create negative externalities;
- delayed effects can be misattributed;
- non-digitized human work can disappear from the reward surface;
- the optimizer may exploit a narrow metric while damaging the project.

For that reason, the kernel exposes action-impact state for review and routing.
It does not ship a bandit/RL policy.

## Guardrails

Tenant action-impact implementations should preserve:

- baseline action;
- counterfactual action;
- decision stage;
- old state and new state;
- artifact references;
- cost and time units;
- evaluator role;
- independence boundary;
- decision changed flag;
- externality tags;
- negative externality tags;
- ignored or overridden forecast reason;
- guardrail metrics;
- human review requirement.

For scientific work, tenants should avoid collapsing yield into one scalar when
the bottleneck, next lever, and decision change are the actual learning object.

## Org Surface Integration

The org surface reads an optional action-impact summary and surfaces:

- planned action-impact records;
- records requiring human review;
- local optimizations with negative externalities.

Negative externalities may be numeric (`externalities.trust = -0.4`) or tagged
(`negative_externality_tags = ["operator_load"]`). The tag-only case still
requires review; a tenant should not need a precise scalar before surfacing a
known externality.

## Tenant Boundary

Tenants own:

- metric definitions;
- P&L or scientific-yield attribution;
- reward models;
- bandit/RL training;
- exploration budget;
- domain-specific guardrails;
- promotion criteria from offline model to live policy.

The public kernel owns:

- portable read-model shape;
- org-surface integration;
- tests for adapter normalization;
- documentation of why the optimizer is outside core.

## Mini-RL / Bandit Compatibility

The interface is compatible with tenant bandit or mini-RL systems because it
preserves the fields needed for offline evaluation: baseline action,
counterfactual action, decision stage, expected effect, observed outcome,
decision changed flag, costs, evaluator role, and externality tags. It also
supports contextual-policy fields: context features, chosen action arm, logging
policy id, logging-policy probability, reward, delayed-effect window, and human
review burden.

The kernel does not promote those rows into a live optimizer. A tenant should
only do that after it can show that the logged reward is measurable, delayed
effects are handled, negative externalities are tracked, and offline replay
beats the existing routing policy without increasing review debt.

The kernel includes one conservative helper for this path:
`propose_business_function_policy` in
`cognitive_firm.orchestration.business_function_bandit`. It aggregates logged
arms by context and emits a candidate context-to-arm map only when an arm has
enough support, beats the context baseline, and passes externality and
human-review thresholds. It is a proposer, not a live policy writer.

## Offline Policy Evaluation Reports

The module includes a conservative report primitive for candidate policies:
`OfflinePolicyEvaluationReport`. It evaluates a candidate policy by replaying
logged rows where the candidate policy would have selected the same action arm
as the logged action.

This is intentionally stricter than a full contextual-bandit estimator. It is a
safe first report for thin logs and preserves the fields needed for
tenant-owned IPS, doubly robust, or distributionally robust estimators later.

A report records:

- candidate policy id and optional policy ref;
- context keys used for the replay;
- logged, eligible, and matched row counts;
- support coverage;
- baseline and candidate mean reward;
- an approximate 95% confidence interval for matched candidate reward;
- negative externality rate;
- human-review rate;
- whether logging propensities, counterfactuals, and guardrail metrics are
  present;
- promotion blockers and guardrail notes.

The report can be `blocked`, `advisory`, or `promotable`. `promotable` does not
change a policy by itself. It is evidence for a tenant-owned governance-change,
learning-event, or policy-adapter promotion path.

## Policy Promotion Packets

`PolicyPromotionPacket` is the handoff from offline policy evaluation to
governance review. It joins:

- the `OfflinePolicyEvaluationReport`;
- guardrail and externality summary fields;
- an optional authority-diff reference;
- optional formal-verification and learning-event references;
- a draft governance-change payload.

The packet is not an approval and does not mutate a live policy. A report that
is otherwise promotable is downgraded to `advisory` when required review
evidence, such as an authority diff, is missing. This keeps learned loops in a
proposal role while preserving the evidence a reviewer needs.

CLI:

```bash
cognitive-firm-action-impact evaluate-policy \
  --summary-json org/action_impact/action_impact_summary.json \
  --candidate-policy-id policy.support.enterprise-review \
  --candidate-action-map candidate_actions.json \
  --context-key segment \
  --objective-metric resolution_quality \
  --record
```

Build a governance review packet from a recorded evaluation:

```bash
cognitive-firm-action-impact build-promotion-packet \
  --evaluation-id ope_123 \
  --proposed-by role.governance_reviewer \
  --authority-diff-ref authority-diff://support-enterprise-review \
  --formal-verification-ref formal-verification:fver_policy_boundary \
  --record
```

The `candidate_actions.json` file maps stable context signatures to action
arms. A context signature is JSON with the selected context keys sorted, for
example:

```json
{"{\"segment\":\"enterprise\"}": "senior_review"}
```

## Tests

Covered by `tests/test_action_impact_interface.py`.
