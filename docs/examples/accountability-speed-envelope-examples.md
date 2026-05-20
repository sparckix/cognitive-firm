# Accountability Speed Envelope Examples

These examples turn `docs/accountability-speed-envelope.md` into concrete
routing choices.

| Case | Default route | Kernel record |
|---|---|---|
| Local draft cleanup with no external effect | agent speed | transition or action attestation |
| Batch of similar low-risk source checks | sampled review | action attestations plus sample policy |
| Human has private access or relationship context | batched human review | human-work session with receipt |
| External write, legal/regulatory exposure, or irreversible customer impact | gate before action | policy decision or gate plus lease |
| Harm occurred or residual risk was accepted | accountable closure | accountability case |

## Example: Agent Speed

An agent normalizes internal markdown headings. The action is reversible and
bounded to a branch. Record a transition or attestation. Do not create a human
work session.

## Example: Sampled Review

An agent classifies 100 low-risk documents. Sample 10 percent and record the
sample policy. Escalate if the sample error rate crosses the pre-registered
threshold.

## Example: Batched Human Review

A human must check a private source. Create one human-work session with a
bounded deliverable and receipt. Do not model the human as a simple approval
button.

## Example: Gate Before Action

A connector wants to close a customer-facing issue. Require scoped actor
membership, a valid lease, and a policy decision before the external write.

## Example: Accountable Closure

A team accepts a residual risk because delay is more costly than the remaining
uncertainty. Open an accountability case with owner, recourse path, closure
evidence, and review date.

## Failure Signal

If every case takes the same route, the envelope is not being used. The point is
to preserve speed where speed is safe and require accountability where speed
would hide risk.
