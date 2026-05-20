# Action Intelligence Source-Health Example

This example shows the safe order for using forecast or action-impact signals:
repair source quality before using the signal to route more work.

## Situation

A tenant has forecast and action-impact summaries. The organization surface
shows:

```text
forecast_contracts=20
forecast_score_debt=12
planned_action_impacts=8
action_impacts_requiring_review=5
local_negative_externalities=2
```

The tempting move is to optimize dispatch toward actions with higher apparent
impact. The safer move is to inspect source health first.

## Kernel Behavior

The kernel consumes generic summaries and emits source-improvement candidates:

- forecast decision-use missing;
- forecast score debt;
- action-impact review debt;
- negative externality rows;
- findings not promoted into learning candidates.

These are source-repair items, not optimizer permissions.

## Safe Routing

Use this sequence:

1. Check source health.
2. Repair missing resolution, score, decision-use, or review rows.
3. Review negative externalities and counterfactual notes.
4. Run offline replay of a proposed routing policy.
5. Promote only bounded policy changes through governance review.

## Do Not

- train a live optimizer directly on thin action-impact rows;
- treat a forecast as useful if no decision-use row says how it changed work;
- ignore externalities because the local metric improved;
- let tenant scoring rules become kernel policy.

## Executable Walkthrough

Run:

```bash
PYTHONPATH=src python scripts/source_coverage_walkthrough.py
```

The script creates a source-health view and source-repair candidates from
forecast, action-impact, and learning surfaces.
