# Kernel Invariants

cognitive-firm is not a catalog of unrelated primitives. The primitives exist
to enforce a small set of organizational invariants.

## Core Invariants

| Invariant | Meaning | Implemented by |
|---|---|---|
| Separation | Generation, evaluation, approval, and execution should not silently collapse into one actor or one prompt. | Role offices, mandates, A2A, Strategy Office, governance-change proposals. |
| Typed authority | A role or actor must have explicit authority before acting. | Mandates, actor identity, identity-provider adapters, subject-scope checks, leases, MCP capabilities. |
| Human work as state | Human contribution is not only approval. It can be bounded object-level work with deliverables, receipts, and follow-up. | H2A, A2H, human work sessions, organization surface. |
| Machine provenance | Machine-side work should be reviewable by producer, runtime, tool, policy, inputs, outputs, and digest. | Action attestations, run checkpoints, runtime adapters, audit manifests. |
| Accountable closure | Residual risk should have an accountable role, decision-right basis, recourse path, and closure evidence. | Accountability cases, accountability summary, org surface. |
| Durable learning | Learning is not a retrospective note unless it changes future behavior or review state. | Strategy Office findings, learning-transition compiler, approved learning events, governance changes. |

## Boundary Rule

Every primitive should answer four questions:

1. Which invariant does it serve?
2. What is the durable source of truth?
3. Which layer owns policy: kernel, app, runtime, or tenant overlay?
4. What failure becomes visible if this primitive is absent?

If a proposed primitive cannot answer those questions, keep it as a tenant
adapter or example until repeated use proves it belongs in the public kernel.

## Recombination Claim

The individual mechanisms are familiar: role separation, event logs, workflow,
identity, provenance, incident closure, and human-computer cooperation all have
large prior literatures. The contribution of this kernel is their composition
around persistent human and agent roles and typed organizational state transitions.

In practical terms, the kernel asks the same questions before and after work:

- Who had authority to act?
- What happened?
- What did the human actually contribute?
- What machine/runtime/tool evidence exists?
- Who owns residual risk and recourse?
- What durable state changed afterward?

That is the adoption bar. New concepts should make those questions easier to
answer, not add vocabulary for its own sake.
