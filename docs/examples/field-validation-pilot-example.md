# Field Validation Pilot Example

This example shows the smallest useful pilot for an organization evaluating
`cognitive-firm`.

## Workflow

**Pipeline:** product requirement approval.

**Decision:** approve, revise, or reject a product requirements document before
engineering starts.

**Baseline window:** 30 days or 20 PRDs, whichever takes longer.

**Primary metrics:**

- defects found after engineering starts;
- days from request to approved PRD;
- reviewer hours per PRD;
- rework cycles per PRD;
- stakeholder satisfaction after decision;
- number of late source/evidence discoveries.

## Kernel Setup

Create a project charter:

```text
Core Question
Can separated generation/review, pre-registered checks, human-work receipts,
and learning events reduce PRD rework without slowing approval?

Out Of Scope
Roadmap priority, pricing, staffing, and engineering implementation.

End States
Pass: materially lower rework or defect rate with no unacceptable human burden.
Fail: slower cycle time without reliability gain, or participants route around
the kernel.

Forecast Type
Operational pilot outcome.

Inheritance
Use the organization's existing PRD template and approval policy.

Anchor Proxies
Rework cycles, post-approval defects, time to decision, reviewer hours.
```

Create role mandates:

| Role | Authority |
|---|---|
| `role.product_generator` | Draft PRD from request and source material. |
| `role.product_reviewer` | Apply pre-registered checks; cannot approve own draft. |
| `role.source_checker` | Request or perform restricted-source verification. |
| `role.manager` | Decide approve/revise/reject after review record exists. |

## Checks

Pre-register checks before the pilot starts:

1. Every material claim has a source or evidence gap.
2. User/customer segment is named.
3. Non-goals are explicit.
4. Acceptance criteria are testable.
5. Dependencies and risks are named.
6. Reviewer cannot be the drafter.
7. Any private-source check has a human-work receipt.

## Human Work

Use a human work session when the agent cannot do the work itself:

```bash
python -m cognitive_firm.orchestration.human_work create \
  --requested-by role.source_checker \
  --human-actor human.pm_lead \
  --objective "verify customer escalation details in the restricted CRM note" \
  --work-mode source_check \
  --bottleneck-class access \
  --receipt-required \
  --receipt-type note
```

The receipt should say what was checked, where it was checked, whether the PRD
claim matched, and what the agent should do next. It should not paste private
CRM content into the public kernel.

## Accountability

Open an accountability case if the approved PRD later causes a material
failure:

- trigger: post-approval defect, scope miss, or late evidence discovery;
- accountable role: the role that approved the decision;
- recourse path: reopen, rollback, compensate, escalate, or external review;
- closure evidence: corrected PRD, learning event, or accepted residual risk.

## Learning

At pilot close, convert repeated failures into approved learning events:

- a new check;
- a mandate change;
- a better human-work receipt template;
- an integration requirement for the source system;
- a decision to stop using the kernel on this workflow.

The pilot succeeds only if the learning changes future behavior. More logs
without changed review state are not organizational learning.

