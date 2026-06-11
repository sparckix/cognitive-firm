# Loop Engineering

**Status:** framing and composition guide over shipped primitives.
**Primary demos:** `make adoption-demo`, `make learning-loop-walkthrough`.

Loop engineering is the practice of designing a repeated agent or
human-agent process so that each pass has a goal, state, verification,
escalation, and learning path. Agent runtimes execute loops. cognitive-firm
records when those loops become organizational work.

## Boundary

Use a runtime such as LangGraph, AutoGen, CrewAI, Letta, Temporal, or a custom
service for the inner loop:

- graph execution;
- retries and replay;
- model/tool calls;
- runtime memory;
- tracing and eval dashboards.

Use cognitive-firm around that loop when the organization needs:

- a role or actor with authority to start the loop;
- a mandate that defines the standing loop instructions and limits;
- a bounded goal or work item;
- checkpoints that say what happened;
- action attestations for material outputs or side effects;
- human work sessions for interrupts, review, or object-level work;
- outcome links that record whether the loop helped;
- accountability cases when residual risk or recourse exists;
- approved learning records that change future behavior.

## Composition

A governed loop does not need a new primitive. It is the composition of
existing records:

| Question | cognitive-firm surface |
|---|---|
| Who owned the loop? | role mandate, actor identity, actor membership |
| What was it trying to do? | project charter, work item, principal goal, runtime objective |
| What happened? | run checkpoints, kernel events |
| What did the machine produce or change? | action attestations, audit manifests |
| Where did humans enter? | A2H human-work sessions, receipts, userland inbox |
| Did the loop improve anything measured? | outcome links |
| Who owns unresolved risk? | accountability cases |
| What should change next time? | learning candidates, approved learning events, governance changes |
| Can a reviewer inspect it quickly? | governed-run attestation bundle |

Mandates are the standing instructions for repeated work: what a role may do,
when it must escalate, what evidence it must preserve, and which exits require
review. Goals and work items are loop instances. Runtime events describe the
execution. The governed-run attestation bundle is the compact export view over
the run evidence:

```bash
cognitive-firm-governed-run-bundle <run_id>
```

## Goal-Orchestrating-Goal Shape

When a goal launches or delegates to another goal, treat the delegation as a
state transition rather than hidden prompt context:

```text
goal/work item
  -> runtime run starts
  -> checkpoints and side effects are recorded
  -> human work is requested if the loop hits an authority or judgment boundary
  -> machine actions receive attestations
  -> outcome and accountability records close the loop
  -> approved learning changes later dispatch, review, or authority
```

The important distinction is that a sub-goal may execute inside any runtime,
but organizational closure lives in kernel records. A parent goal should not be
considered closed merely because a child agent returned text; it closes when the
required evidence, receipts, outcome status, and accountable-risk status are
settled or explicitly carried forward.

## Minimal Adoption Test

Do not add cognitive-firm to a loop just because the loop is agentic. Add it
when at least one of these is true:

1. The loop can trigger external side effects.
2. A human must do bounded work, not only click approve.
3. The loop's output changes a repeated organizational routine.
4. The organization needs to know whether the loop improved a measured result.
5. Residual risk needs a named owner and recourse path.
6. A reviewer needs a portable run-evidence export after the run.

If none of these apply, keep the loop inside the runtime.
