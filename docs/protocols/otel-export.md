# OpenTelemetry Export

**Status:** projection shape shipped.
**Module:** `cognitive_firm.orchestration.otel_export`
**Tests:** `tests/test_otel_export.py`

The OpenTelemetry projection maps kernel run checkpoints into GenAI-shaped span
dictionaries that a deployment adapter can send to its chosen collector.

The kernel event log and transition rows remain canonical. OpenTelemetry is an
observability projection, not a source of organizational truth.

## What It Projects

For each run, the projection includes:

- `gen_ai.operation.name = agent_run`;
- `gen_ai.agent.name`;
- `cognitive_firm.run_id`;
- run state;
- tenant and project ids when present;
- checkpoint events with step id, status, summary, payload ref, side-effect key,
  and kernel event id.

## Use

```bash
python -m cognitive_firm.orchestration.otel_export \
  --log-path cognitive_firm_workspace/transitions.jsonl \
  --output /tmp/cognitive-firm-otel.json
```

Deployments can translate this JSON shape into an OpenTelemetry SDK exporter
for their chosen collector. The public kernel keeps the dependency optional.

## Boundary

Do not store secrets, full prompts, private source text, or unrestricted tool
payloads in the OTel projection. Record references and digests in the kernel;
let the deployment choose what content, if any, leaves the host.

## Tests

Covered by `tests/test_otel_export.py`.
