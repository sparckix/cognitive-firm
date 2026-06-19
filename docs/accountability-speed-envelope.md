# Accountability Speed Envelope

Agent work can move faster than human review. The kernel should not force every
action through the slowest possible gate, and it should not let irreversible
work proceed with only after-the-fact blame.

Use this envelope to choose the right speed.

Executable surfaces:

```bash
cognitive-firm-userland speed-envelope \
  --risk-tier medium \
  --bottleneck-class access \
  --deployment-class internal \
  --repeated-similar
```

```text
GET /kernel/human-speed-envelope?risk_tier=medium&bottleneck_class=access&deployment_class=internal&repeated_similar=true
```

Both return `human_speed_envelope.v1`, a read-only projection with:

- `speed_class`;
- `cadence`;
- `required_record`;
- `receipt_required`;
- `sample_for_review`;
- optional `sample_rate`;
- `gate_required`;
- `accountability_case_recommended`;
- review questions and an explicit non-execution boundary.

The envelope does not authorize work, dispatch work, schedule review, sample
records, or approve policy. It only selects the accountable record shape that
the operator or adapter should use next.

## Speed Classes

| Class | Use when | Pattern | Required record |
|---|---|---|---|
| Agent speed | Reversible, low-risk, bounded scope | let agent proceed inside mandate | transition or attestation |
| Sampled review | Many similar low/moderate-risk actions | proceed, then sample or audit | attestation + sample policy |
| Batched human review | Human judgment matters but per-item review is wasteful | batch decisions with receipts | human work session |
| Gate before action | Irreversible, costly, regulated, or external-facing work | approval before side effect | policy decision or gate |
| Accountable closure | Residual risk has been accepted or harm occurred | owner, recourse, evidence, closure | accountability case |

## Routing Questions

Ask in order:

1. Is the action reversible?
2. Can damage be bounded by tenant/project/resource scope?
3. Does a human possess private context, taste, legal authority, or relationship
   authority the agent does not have?
4. Would a miss create externalities for people outside the workflow?
5. Can the same action be audited by sample instead of reviewed one-by-one?
6. Does a future role need to encounter the outcome as learning?

## Defaults

- reversible local analysis: agent speed;
- external write with clear capability: gate or lease-backed service call;
- private-source check: human work session;
- repeated forecast/action miss: source repair or learning candidate;
- accepted residual risk: accountability case;
- possible optimizer/routing change: offline replay before live policy.

## Failure Signals

- everything becomes a manual approval;
- everything becomes an autonomous action;
- gates have no owner or criterion;
- fast actions leave no provenance;
- slow human work leaves no receipt;
- incidents do not change future routing, review, or authority.

## Research Anchor

- Parasuraman, Sheridan, and Wickens' levels-of-automation model motivates
  treating speed as an allocation of functions, not as a blanket grant of
  authority: <https://doi.org/10.1109/3468.844354>.
- Bainbridge's "Ironies of Automation" motivates preserving accountable human
  skill and avoiding systems where humans only inherit rare, high-stakes
  interventions after automation has removed routine practice:
  <https://doi.org/10.1016/0005-1098(83)90046-8>.
- Suchman's situated-action work motivates keeping human work as bounded,
  context-bearing activity rather than reducing it to a prewritten workflow
  step: <https://en.wikipedia.org/wiki/Lucy_Suchman>.
- The SRE toil frame motivates making repeated manual review visible so the
  organization can distinguish necessary judgment from design debt:
  <https://sre.google/sre-book/eliminating-toil/>.
