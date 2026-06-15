# demos

Runnable demonstrations and harnesses live here. Demo code may seed temporary
firms, orchestrate bounded runs, render reports, and call public kernel APIs.

Do not put reusable primitives, durable state-transition logic, authority
rules, service routes, schemas, or protocol invariants here. If another
program should depend on the behavior, move it to `src/cognitive_firm/` and
leave the demo as a thin client.

Current demo groups:

- `self_evolving_org/`: governed self-evolving organization demo, daemon smoke,
  planner validation, and live agent runtime preflight.
- `governance_carriers/`: small no-cost demos for evidence carriers and
  telemetry primitives.

