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
-> conservative offline policy evaluation
-> governance review packet
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
review evidence. A tenant still needs governance approval before any live
routing policy changes.
