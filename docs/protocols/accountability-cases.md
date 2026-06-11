# Accountability Cases

**Status:** lean T2-local primitive.
**Module:** `cognitive_firm.orchestration.accountability_cases`
**Tests:** `tests/test_accountability_cases.py`

Accountability cases are write-side records for authority, recourse, and
closure. They complement the read-only accountability summary.

The summary answers:

```text
What unresolved items need follow-up?
```

An accountability case answers:

```text
Who had the decision right, who owns review, what residual risk was accepted,
what recourse exists, and what evidence closes the case?
```

This is not a blame ledger. It is a disciplined record of accountable closure.

## Why This Exists

Agent systems can act faster than human review. A kernel should not solve that
by forcing every action through a human gate. It should allow agent-speed work
inside bounded, reversible, attested authority envelopes and put humans at the
accountable boundary: irreversible action, residual-risk acceptance, taste,
legitimacy, recourse, and exception handling.

When something crosses that boundary, create an accountability case.

## Record Shape

```json
{
  "case_id": "acct_<id>",
  "created_at_utc": "...",
  "updated_at_utc": "...",
  "trigger_ref": "damage_signal/dmg_1",
  "accountable_role": "role.manager",
  "responsible_actor": "role.engineer | principal | runtime:codex",
  "decision_right_basis": "mandate | gate | policy | principal_directive | tenant_rule",
  "authority_envelope_ref": "org/mandates/engineer_mandate.md",
  "risk_tier": "low | medium | high | irreversible",
  "recourse_path": "reopen | compensate | rollback | escalate | external_review | none",
  "status": "open | under_review | remediated | accepted_risk | escalated | closed",
  "residual_risk_accepted_by": "optional",
  "review_sla": "optional ISO-8601 duration",
  "tenant_id": "optional",
  "project_id": "optional",
  "due_at_utc": "optional",
  "closure_evidence_refs": ["..."],
  "externality_tags": ["..."],
  "operator_burden": "low | medium | high",
  "rationale": "...",
  "metadata": {}
}
```

## Speed Rule

Do not adapt humans to agent speed. Adapt agent autonomy to accountable speed.

Practical rule:

- low-risk, reversible, attested work may run at agent speed;
- high-risk or irreversible work needs an authority envelope, exception route,
  or gate;
- residual-risk acceptance must name a responsible human or role;
- if agent throughput exceeds accountable review capacity, cap, queue, sample,
  sandbox, or split responsibility before increasing autonomy.

## Links To Existing Primitives

An accountability case may be triggered by:

- an A2A obligation;
- a human work session;
- an action attestation;
- a failed run checkpoint;
- an action-impact row;
- a forecast allocation recommendation;
- a damage signal;
- a strategy-office finding;
- a governance-change proposal.

Closure evidence may point to:

- remediation artifacts;
- action attestations;
- evidence reviews;
- human work receipts;
- approved learning events;
- external review refs.

## Resource Projection

`accountability_case_resource(...)` projects a case into the common
[`Resource Envelope`](resource-envelope.md). The accountability JSONL row
remains canonical; the resource view is for review dashboards, admin adapters,
migration checks, and conformance fixtures:

```text
kind: AccountabilityCase
metadata: case id, tenant/project, labels, annotations
spec: trigger, accountable role, responsible actor, decision-right basis,
      authority envelope, risk tier, recourse path, review SLA, due time,
      externality tags, operator burden, rationale
status: lifecycle status, residual-risk acceptor, closure evidence, timestamps
links: trigger, accountable role, responsible actor, authority envelope,
       closure evidence, residual-risk acceptor
```

The CLI can render the same compatibility shape:

```bash
python -m cognitive_firm.orchestration.accountability_cases list --resource
```

## Boundary

Use the accountability summary for visibility. Use accountability cases for
review and closure when an item crosses an accountability boundary.

Do not create cases for every low-risk row. That would turn accountability into
the bottleneck it is meant to govern.
