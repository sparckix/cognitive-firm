# Decision-Log Replay Demo

The decision-log replay demo is a no-cost fixture for the learned-policy path.
It uses a fictional support desk and deterministic action-impact rows.

Run:

```bash
make decision-log-replay-demo
```

The demo writes fixture logs in a temporary directory, then reconstructs the
decision from those logs:

```text
action-impact rows
-> business-function candidate proposer
-> kernel-service offline policy evaluation route
-> kernel-service governance review packet route
-> run checkpoint + action attestation + outcome verdict
-> governed-run attestation bundle
```

The expected result is one review-ready packet and one blocked packet:

- enterprise support cases are proposed for senior review because the logged
  arm has enough support, improves reward, and does not increase the configured
  externality or review-burden rates;
- renewals auto-send has positive local reward, but is rejected by the
  proposer and blocked by the evaluator because negative-externality and
  human-review rates exceed thresholds.

This is deliberately not an online optimizer. The reusable primitive is
`cognitive_firm.orchestration.business_function_bandit.propose_business_function_policy`.
It only emits a candidate context-to-arm map plus diagnostics. The existing
`action_impact` evaluator and `PolicyPromotionPacket` turn that candidate into
review evidence through `/kernel/action-impact/*` routes, so the demo exercises
the same service boundary an adopter would use.

The demo also wraps the replay in a completed governed run. It records
checkpoints, a verified action attestation over the replayed packet rows, an
outcome link with a verdict, and a governed-run attestation bundle whose schema
validation passes. That proves the conclusion is reconstructable from logs and
portable as a reviewer handoff. A tenant still needs governance approval before
any live routing policy changes.
