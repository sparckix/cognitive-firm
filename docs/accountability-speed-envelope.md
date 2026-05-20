# Accountability Speed Envelope

Agent work can move faster than human review. The kernel should not force every
action through the slowest possible gate, and it should not let irreversible
work proceed with only after-the-fact blame.

Use this envelope to choose the right speed.

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
