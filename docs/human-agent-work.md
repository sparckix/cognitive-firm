# Human-Agent Work

**Status:** public theory and adoption guide.

This document explains the human-agent work model behind `cognitive-firm`.
Protocol details live in [H2A](protocols/h2a.md), [A2H](protocols/a2h.md),
[A2A](protocols/a2a.md), [Accountability Cases](protocols/accountability-cases.md),
and the [Organizational Learning Loop](organizational_learning_loop.md).

## Thesis

Humans should not be used only as approval buttons, and agents should not be
treated as unmanaged workers. The useful unit is the whole work system:

```text
human judgment, authority, taste, relationship, and recourse
+ agent speed, search, drafting, coding, and monitoring
+ durable kernel state
= accountable work
```

The kernel should not slow every decision down to human speed. It should say:

- what can run at agent speed;
- what needs bounded human work;
- what needs accountable closure.

## The Four Work Modes

### 1. Agent-speed work

Agent-speed work can proceed without immediate human review when it is:

- within mandate;
- bounded by budget and capability policy;
- reversible or sandboxed;
- attested with machine provenance;
- visible through organization-surface state.

Examples: drafting, code edits inside authorized paths, evidence-gap
collection, local test runs, forecast preparation, and read-only analysis.

### 2. Human-gated work

Human-gated work requires a principal or accountable actor to grant authority.

Examples: mandate changes, budget increases, irreversible external effects,
regulated-deployment mapping, and residual-risk acceptance.

### 3. Joint human-agent work

Joint work is object-level work performed with both human and agent
contribution. The human is not merely approving. The human may inspect a
private source, call a partner, make a taste call, or apply domain judgment.
The agent may prepare context, ask for the bounded output, integrate the result,
and continue the work.

The kernel records this through human work sessions and, when initiated by a
role office, the A2H work-coordination pattern.

When the work is not fully observable by the kernel, the session can carry a
structured receipt. The receipt records a bounded human claim with an actor,
summary, receipt type/ref, subject refs, artifact refs, confidence, and review
flag. It does not mechanize the work; it makes the claim visible enough for
integration, sampling, and accountability.

### 4. Accountable closure

Accountable closure is required when ordinary follow-up is not enough. It names
who had the decision right, under which authority envelope, who owns residual
risk, what recourse exists, and what evidence closes the case.

This is recorded as an accountability case.

## Where Work Lives

In this system, work is not only inside a model or a person. It is spread
across:

- role mandates;
- message obligations;
- source connectors;
- logs and receipts;
- forecast and action-impact records;
- human judgment;
- machine attestations;
- accountability cases;
- approved learning events.

The organization learns only when this work changes durable state. A
conversation, review, forecast, or insight does not count by itself. It counts
when it becomes a mandate update, charter update, evidence gap, A2A obligation,
human work session, action attestation, accountability case,
learning-transition candidate, or approved learning event.

## Design Rule

```text
Run at agent speed where work is bounded.
Use human work where humans are the correct sensor, judge, actor, or principal.
Use accountability cases where residual risk or recourse is created.
Translate learning into durable state.
```

This avoids two common failures:

- human bottlenecking, where every agent action waits for approval;
- autonomy theater, where agents move fast and accountability is reconstructed
  after the fact.

## Substitution Check

Before treating a workflow as a special human-agent pattern, ask two questions:

1. If the agent were replaced by a very capable junior employee, what would
   still be true?
2. If the human were replaced by another agent, what would break?

If the first answer explains the whole workflow, the problem is probably
ordinary delegation or workflow design. If the second answer names authority,
taste, relationship, safety, private access, or residual-risk ownership, the
human boundary is material and should be represented as human work or
accountable closure.

## A2H Is Not Agent Management Of Humans

A2H work coordination lets a role office request bounded human work. It does
not make the agent the human's manager.

An A2H request must name:

- the requesting role;
- the human actor;
- the objective;
- the deliverable;
- whether a receipt is required;
- the agent role that must integrate the result;
- the linked A2A obligation, if another role is waiting.

The human may refuse, correct, hand off, or complete the work. The requesting
role remains responsible for integration. In the read models, requested and
in-progress A2H work is "waiting on human"; handed-off or completed A2H work is
"ready for agent follow-up." Receipt-required work cannot be integrated until
the receipt exists.

## When To Automate The Human Boundary

Repeated human-work pressure is a signal, not automatically a bug.

Likely automation candidates:

- repeated `labor` bottlenecks;
- repeated `access` bottlenecks where a source connector is appropriate;
- repeated copy/paste or data-entry work;
- repeated receipt formatting.

Likely human-preserved boundaries:

- authority;
- taste;
- legitimacy;
- relationship work;
- safety review;
- private judgment;
- residual-risk acceptance.

The organization surface exposes A2H pressure by role and bottleneck class so
tenants can decide whether to preserve, batch, sample, delegate, or automate a
boundary.

## How This Maps To The Kernel

| Need | Primitive |
|---|---|
| Role asks role for work | A2A obligation |
| Role asks human for bounded work | A2H work coordination over human work session |
| Human performs object-level work | Human work session |
| Agent/tool/runtime produces artifact | Action attestation |
| Residual risk needs owner and recourse | Accountability case |
| Finding should change future behavior | Learning-transition candidate -> approved learning event |
| Current blockers must surface before work | Organization surface |

## Adoption Checklist

1. Define role mandates and budget envelopes.
2. Decide which human-work bottlenecks are intentionally human.
3. Decide which receipt types are sufficient for each domain.
4. Use structured receipts when human work must be reflected without storing a
   full transcript or pretending the kernel observed it directly.
5. Add A2H requests only when the human deliverable is bounded.
6. Review A2H pressure weekly: preserve, batch, automate, or escalate.
7. Open accountability cases only at residual-risk boundaries.
8. Promote repeated lessons into approved learning events or tenant policy.

## Related Documents

- [A2H — Agent-to-Human Work Coordination](protocols/a2h.md)
- [H2A — Human-to-Agent Protocol](protocols/h2a.md)
- [A2A — Agent-to-Agent Protocol](protocols/a2a.md)
- [Accountability Cases](protocols/accountability-cases.md)
- [Action Attestation](protocols/action-attestation.md)
- [Organizational Learning Loop](organizational_learning_loop.md)
- [A2H Workflow Demo](examples/a2h-workflow-demo.md)
