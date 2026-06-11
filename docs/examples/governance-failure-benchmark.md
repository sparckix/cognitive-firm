# Governance Failure Benchmark

This no-cost benchmark exercises cases where a plain runtime may finish a run
while an organization still has a governance problem to resolve.

Run it locally:

```bash
make governance-failure-benchmark
```

For full fixture details:

```bash
PYTHONPATH=src python scripts/governance_failure_benchmark.py --full-json
```

The benchmark uses deterministic temporary logs and makes no model, network,
subscription, or external-service calls.

## Fixtures

| Fixture | Failure mode | Kernel surface |
|---|---|---|
| `unauthorized_write` | A role tries to mutate a forbidden code path. | `task_authorization.authorize_dispatch` |
| `failed_attestation` | An artifact provenance check fails. | Action attestations and governed-run bundle |
| `missing_human_receipt` | Human review is requested but no receipt is recorded. | Human work and governed-run bundle |
| `unresolved_outcome` | A claimed improvement has no outcome verdict. | Outcome links and governed-run bundle |
| `open_accountability_case` | Residual risk exists but closure is not recorded. | Accountability cases and governed-run bundle |
| `formal_refutation` | A formal checker refutes a claimed invariant. | Provider payload, formal verification, and governed-run bundle |
| `missing_referenced_lease` | An action claims a resource lease that is not present. | Lease evidence and governed-run bundle |
| `missing_governance_approval` | A policy mutation claims approval that is not present. | Governance approval evidence and governed-run bundle |
| `local_reward_externality_downgrade` | A locally better action is unsafe to promote because externality and review-burden guardrails dominate. | Action-impact offline evaluation and policy-promotion packet |
| `weakly_evidenced_governance_change` | A recursive self-modification proposal has passing invariant claims but no sufficient review evidence. | Governance-change evidence sufficiency |

Each fixture passes only if the expected block, caveat, or incomplete verdict is
observed.

## Costly Fixtures

Live fixtures can be useful later, but they should stay opt-in. The default
benchmark should remain deterministic so public smoke can run in a fresh clone.

A live lane should be added only when it answers a sharper question, for
example:

- whether a real runtime adapter preserves the same run identity across resume;
- whether an external-system action has a verifiable receipt;
- whether a human-review surface records the receipt before resume;
- whether a formal-checker service returns stable certificate digests and
  counterexample references;
- whether a real observability backend preserves the refs exported by the
  governed-run bundle.

Until then, the no-cost benchmark is the right default. It proves the kernel
surfaces the governance failure without spending tokens or depending on
credentials.
