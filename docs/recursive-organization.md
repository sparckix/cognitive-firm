# Recursive Organization

This document explains the theory behind cognitive-firm in plain language. It
is not a replacement for the companion paper. It is the short entry point for
people asking what the kernel is trying to make possible.

## The Basic Idea

An organization using agents needs more than task execution. It needs a way to
notice what happened, decide what should change, and make that change visible
to future work.

That is the recursive capability:

```text
do work
-> observe what happened
-> identify a gap, risk, or lesson
-> review it
-> change future behavior
-> do the next work under the changed state
```

Without that loop, agents can produce more output without improving the
organization that directs them.

## What Counts As Learning

In this repo, learning is not a memory entry or a note. Learning means durable
state changed in a way future work must encounter.

Examples:

- a mandate becomes narrower or broader;
- a project charter gets a new boundary;
- an evidence gap blocks a branch until resolved;
- a human-work bottleneck becomes a source-connector task;
- an accountability case changes review policy;
- a forecast miss changes allocation;
- an action-impact row changes routing;
- an approved learning event changes future behavior.

If nothing changes downstream, it may be useful context, but it is not
organizational learning yet.

## Why Recursion Needs Governance

Recursive systems can improve themselves, but they can also reward the wrong
thing, hide externalities, or rewrite their own constraints. The kernel
therefore separates:

- **finding**: what the system noticed;
- **candidate**: what could change;
- **approval**: who has authority to accept the change;
- **application**: what state actually changed;
- **replay**: how future work sees the change.

This separation keeps learning useful without letting every local optimizer
edit the rules of the organization.

## The Six Invariants

The kernel's primitives serve six invariants:

1. **Separation**: generation, evaluation, approval, and execution should not
   silently collapse into one actor.
2. **Typed authority**: a role or actor must have explicit authority before
   acting.
3. **Human work as state**: human contribution can be bounded work with
   deliverables and receipts, not just approval.
4. **Machine provenance**: agent, runtime, and tool actions need reviewable
   evidence.
5. **Accountable closure**: residual risk needs an owner, recourse path, and
   closure evidence.
6. **Durable learning**: a lesson matters when it changes future dispatch,
   review, authority, or allocation.

See [Kernel Invariants](kernel-invariants.md) for the compact map.

## What Makes This Different From Ordinary Agent Logs

An ordinary agent log records what an agent said or did. That is useful, but it
does not automatically change how the organization works.

The kernel records typed organizational state:

- who had authority;
- what work was requested;
- what human or machine evidence exists;
- what is blocked;
- what risk remains;
- what was approved;
- what future work should see.

The point is not more logging. The point is that future work is routed through
state that previous work changed.

## Where Humans Fit

Humans are not just decision gates. They may be the correct actor for a private
source check, partner call, taste judgment, safety review, or residual-risk
acceptance.

The kernel records bounded human work so that:

- the role office can request a concrete deliverable;
- the human can provide a receipt or bounded claim;
- the agent can integrate the result;
- repeated pressure becomes visible;
- the organization can decide whether to preserve, batch, automate, or
  escalate that boundary.

This makes human contribution visible without pretending the kernel directly
observes private or offline work.

## Relation To The Substitution Test

A useful prior test for human-agent work is: if "AI" were replaced by a very
capable junior employee, would the claim still hold? If yes, the claim may be
ordinary delegation, workflow, or principal-agent economics rather than a new
human-AI primitive. A second version replaces the human with another agent and
asks what about the human side remains load-bearing.

That test is still useful here, but it answers a different question. It helps
decide whether a work mode is structurally special. The recursive organization
question is about what happens after any work mode is used:

- what authority was exercised;
- what evidence exists;
- what human or machine work occurred;
- what residual risk remains;
- what future state changed.

The kernel should therefore support both cases. If a workflow is ordinary
delegation, it still needs authority, provenance, and closure. If a workflow is
genuinely human-agent specific, it also needs those same state boundaries plus
clear handling of the human contribution.

## Closure Needs A Clock

Another prior finding is that local review can improve consistency without
creating a stopping rule. A second committee, reviewer, or agent can catch
errors, but it does not by itself decide when to stop, fund, abandon, or ship a
branch. Closure usually needs an external pressure: a budget, deadline, risk
owner, customer need, regulatory requirement, or principal decision.

The kernel reflects that distinction. Separation and review protect quality;
accountable closure names who can stop the loop and on what evidence.

## What Remains Tenant-Owned

The public kernel should stay generic. Tenants own:

- domain-specific scoring;
- forecast-market policy;
- P&L or scientific-yield attribution;
- identity-provider deployment;
- compliance controls;
- private evidence;
- business-system adapters;
- optimizer or bandit policy.

The kernel provides the state boundary those systems can plug into.

## Adoption Test

An organization is using the recursive capability when it can answer:

- What did we learn from recent work?
- Which state object carries that learning?
- Who approved it?
- What future behavior changed?
- Where will the next role office see it?

If the answer is only "it is in a chat log" or "the agent will remember," the
loop is not yet recursive at the organizational level.
