# Theory Map

This document is the public claim map for `cognitive-firm`. It is shorter than
the companion paper and more explicit than the narrative docs.

The repository does not claim to invent organization theory, agency theory,
learning theory, or audit. Its claim is narrower: these literatures can be
recombined into a small governance kernel for organizations that coordinate
persistent human and agent roles.

## Claim

Organizations using agents need a durable layer above agent runtimes:

```text
role authority
-> bounded human and machine work
-> provenance
-> accountable closure
-> approved learning
-> future work under changed state
```

The kernel is useful if it makes that loop inspectable, replayable, and
portable across tenants without hard-coding one organization's policy.

## Invariant Map

| Kernel invariant | Prior work it draws from | Kernel surface | Falsifying pressure |
|---|---|---|---|
| Separation | Division of labor, scientific peer review, control systems, principal-agent theory. | Role offices, mandates, A2A, generation/review split. | One actor can generate, approve, execute, and mark success without review. |
| Typed authority | Incomplete contracts, access control, bureaucratic office, command responsibility. | Mandates, actor identity, subject scopes, leases, MCP capabilities. | Agents or app surfaces mutate state without a named authority envelope. |
| Human work as state | Distributed cognition, situated work, operations management, human factors. | A2H, human work sessions, receipts, interaction events. | Humans become hidden labor or approval buttons rather than bounded contributors. |
| Machine provenance | Audit trails, scientific reproducibility, supply-chain provenance, event sourcing. | Action attestations, run checkpoints, kernel events, audit manifests. | A material claim cannot be traced to producer, input, policy, output, and digest. |
| Accountable closure | Corporate governance, safety cases, incident review, legal recourse. | Accountability cases, accountability summary, risk owner, recourse path. | Residual risk exists but no role owns review, recourse, or closure evidence. |
| Durable learning | Organizational routines, double-loop learning, evolutionary economics, postmortems. | Learning candidates, approved learning events, governance-change proposals. | Lessons remain chat/log context and never change future dispatch, review, or authority. |

## Relationship To Agent Frameworks

Agent frameworks coordinate model calls, tools, memory, or graphs. They are
execution substrates. `cognitive-firm` is a governance substrate. A graph run,
chat agent, crew, or custom runtime can project lifecycle events into the
kernel, but it should not become the durable organization record.

## Relationship To Human Organizations

The kernel borrows from ordinary organizations because many problems are not
AI-specific: authority, bounded attention, review, delegation, and recourse.
The AI-specific change is speed and scale. Agents can generate more work than
humans can inspect and can optimize against underspecified review surfaces.
That makes explicit boundaries more important, not less.

## Open Hypotheses

These claims should be tested rather than assumed:

1. A small set of invariant-backed primitives is enough for multiple
   organizations to build useful overlays.
2. Human-work sessions reduce hidden coordination burden more than they add
   administrative overhead.
3. Forecast and action-impact read models improve allocation when tenants own
   the domain-specific scoring policy.
4. Accountability cases improve closure quality without becoming bureaucracy.
5. The field-validation pilot can show measurable improvement in one recurring
   decision pipeline.

## Evidence Standard

The repo is stronger when claims have one of three anchors:

- a shipped primitive with tests;
- a documented tenant or example workflow;
- a field-validation result outside the originating research apparatus.

Anything else should be labeled as roadmap or open hypothesis.
