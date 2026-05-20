# End-to-End Governance Walkthrough

This walkthrough shows how the kernel changes work instead of merely logging
it. The example is intentionally generic.

For executable versions of the two key paths, run:

```bash
make source-coverage-walkthrough
make learning-loop-walkthrough
```

## Scenario

A role office wants to use a claim from a restricted source in a project
decision. The agent cannot inspect that source directly. A human can inspect it,
but the result should still be bounded, reviewable, and integrated by the role
that needed it.

## Flow

1. **Project charter**

   The project records its core question, out-of-scope boundaries, and end
   state. This lets later work be judged against the intended object rather
   than a vague task title.

2. **Evidence gap**

   The role office records a blocking evidence gap:

   ```text
   claim requires restricted-source support
   ```

   The organization surface now shows that material work is blocked by missing
   evidence.

3. **A2H human work request**

   The role office creates an agent-to-human work session:

   ```text
   objective: inspect restricted source and return a bounded support/contradict claim
   deliverable: source note
   receipt_required: true
   receipt_type: note
   ```

   The role remains responsible for integrating the result. The human is not
   turned into a background agent.

4. **Human receipt**

   The human performs the work and records a bounded receipt:

   ```text
   receipt: source supports claim X, but only for population Y
   confidence: medium
   ```

   The private source does not need to be copied into the repo. The kernel
   records the bounded claim, receipt type, and follow-up requirement.

5. **Agent integration**

   The role office reads the completed human-work session and updates the
   evidence gap or artifact. If the receipt is missing, integration is blocked
   unless a waiver or accountability case exists.

6. **Action attestation**

   The role records the machine-side work that used the receipt: producer,
   runtime/tool refs, input/output refs, policy refs, and subject digest.

7. **Organization surface**

   Before the next material step, the org surface shows:

   - no blocking evidence gap if the receipt resolved it;
   - any missing receipt if it did not;
   - any A2H follow-up still waiting on the role;
   - any accountability case if risk was accepted.

8. **Strategy finding**

   If the same bottleneck repeats, the Strategy Office can emit an observer
   finding such as:

   ```text
   repeated restricted-source checks are delaying this project class
   ```

   The finding does not mutate policy by itself.

9. **Learning candidate**

   The learning-transition compiler turns the finding into a reviewable
   candidate:

   ```text
   create a project template requiring restricted-source plan before dispatch
   ```

10. **Approved learning event**

   A human or authorized role approves the candidate. The result becomes a
   durable learning event with before/after state and future application cue.

11. **Source coverage**

   If forecast, action-impact, or other tenant-owned read models are present
   but thin, the intelligence-source projection marks that source as carrying
   debt and emits repair items. The learning-transition compiler can translate
   those repair items into `source_repair` candidates.

## What Changed

An ordinary agent log would say: “agent asked human, human replied, agent used
answer.”

The kernel records:

- why the work was blocked;
- what human work was requested;
- what bounded receipt was returned;
- whether the role integrated it;
- what machine-side action used it;
- whether residual risk was accepted;
- whether source inputs were healthy enough to route future work;
- whether the organization should behave differently next time.

That is the point of the kernel boundary.
