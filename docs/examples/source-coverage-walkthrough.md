# Source Coverage Walkthrough

This walkthrough shows how the kernel treats source health as a first-class
read model without importing tenant scoring policy.

## Scenario

A tenant forecast market has emitted contract rows, but no one has recorded
whether those forecasts changed a real routing decision. Some resolved
contracts are also waiting for score rows.

That is not a tenant-specific research conclusion. It is a generic source
coverage problem: the source exists, but the organization should not treat it
as strong routing evidence until decision-use and scoring debt are repaired.

## Flow

```text
tenant forecast summary
-> organization surface
-> intelligence-source coverage
-> source-improvement backlog
-> learning-transition source_repair candidate
```

## Executable Check

Run:

```bash
make source-coverage-walkthrough
```

The fixture creates a temporary forecast-market summary with:

- two forecast contracts;
- zero decision-use rows;
- one resolved-unscored contract.

The organization surface then exposes:

- `forecast_contracts: 2`;
- `intelligence_source_improvements`;
- `intelligence_source_warning_or_blocking`.

The intelligence-source projection emits repair items:

- `forecast_market.decision_use_missing`;
- `forecast_market.score_debt`.

The learning-transition compiler turns those into reviewable `source_repair`
candidates. It does not apply a repair and it does not score the forecast
market. A tenant adapter or role office owns the actual repair.

## Boundary

The kernel asks whether an admitted source is usable enough for governance:

- Is it canonical state, a read model, a projection, or a tenant-owned ledger?
- Does it have conformance tests?
- Does it carry obvious score, review, decision-use, or externality debt?

The kernel does not decide domain-specific source quality. A research lab,
fund, support team, or sales team can each define its own evidence standards
while still emitting the same generic coverage signals.
