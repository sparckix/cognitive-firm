# Agent-Fleet Audit Demo

This no-cost demo shows the narrow adoption wedge:

> What did my local/subscription agent do, under what role authority, with what
> receipt and audit packet?

Run:

```bash
make agent-fleet-audit-demo
```

To keep the inspection artifacts after the command exits:

```bash
PYTHONPATH=src python scripts/agent_fleet_audit_demo.py \
  --output-dir .cognitive-firm-runs/agent-fleet-audit
```

This writes:

- `.cognitive-firm-runs/agent-fleet-audit/agent-fleet-audit-runbook.md`
- `.cognitive-firm-runs/agent-fleet-audit/agent-fleet-audit-runbook.json`
- `.cognitive-firm-runs/agent-fleet-audit/agent-fleet-audit-packet.json`

The fixture does not call Claude, Codex, an API model, a subscription runtime,
the network, or an external service. It simulates one local agent subprocess
dispatch and records the same evidence shape live daemon runs use.

The chain is:

```text
agent invocation receipt
-> runtime checkpoint
-> action attestation
-> governed-run attestation bundle
```

The durable rows in that chain are written through kernel-service routes:
`/kernel/runs`, `/kernel/runs/{run_id}/checkpoints`,
`/kernel/action-attestations`, `/kernel/runs/{run_id}/state`, and
`/kernel/governed-run-bundles/build`. The demo constructs the local
agent-invocation receipt in memory, then submits it as service-visible
evidence; it does not bypass the kernel service to write canonical rows.

The receipt uses `agent_invocation_receipt.v1` from
[`agent-runtime-invocation`](../protocols/agent-runtime-invocation.md). It
records runtime, adapter, redacted command argv, prompt transport, prompt and
stdout/stderr digests, return code, bounded previews, and a native agent
session id when available.

The action attestation embeds that receipt as provenance for the runtime
event. The governed-run bundle then exports the run state, authority snapshot,
attestation ids, evidence hashes, observability refs, verdict, caveats, and
bundle digest.

The optional runbook uses `governed_run_operator_summary.v1` from
[`governed-run-recipes`](../protocols/governed-run-recipes.md). It is an
inspection projection only: the invocation receipt, action attestation, runtime
events, and governed-run bundle remain the source records.

This mirrors real daemon dispatch: `scripts/agent_daemon.py` writes the same
receipt into `agent_cli_dispatch` action-attestation metadata and includes
prompt/stdout/stderr digest refs so the bundle can answer both "which role
acted?" and "what local agent invocation happened?"

Use full JSON when checking the exact carrier:

```bash
PYTHONPATH=src python scripts/agent_fleet_audit_demo.py --full-json
```

Boundary: this is not a new agent runtime. Claude, Codex, or another local
runtime still owns model execution and native tool use. cognitive-firm records
the organizational evidence around the invocation.
