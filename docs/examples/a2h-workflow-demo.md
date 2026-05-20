# A2H Workflow Demo

This demo shows the minimal path from an agent-to-agent obligation to bounded
human work, then back into role-office integration.

## Scenario

A researcher role is reviewing a claim. The source is private, physical, or
behind an account the agent should not access. The researcher needs the
principal to check it and return a bounded claim.

## Flow

```text
A2A request
-> A2H human work session
-> human receipt
-> researcher integration
-> accountability case only if residual risk was accepted
```

## Code Shape

```python
from cognitive_firm.orchestration.agent_channels import send_agent_message
from cognitive_firm.orchestration.human_work import (
    create_agent_requested_human_work_session,
    update_human_work_state,
)

message = send_agent_message(
    from_role="manager",
    to_role="researcher",
    kind="request",
    subject="Verify restricted source",
    body="Claim C depends on a source outside the agent's accessible corpus.",
)

session = create_agent_requested_human_work_session(
    requested_by_role="role.researcher",
    human_actor="principal",
    objective="Check the private source and report whether it supports claim C.",
    work_mode="source_check",
    bottleneck_class="access",
    human_deliverable="source-support claim plus short rationale",
    obligation_id=message.message_id,
    receipt_required=True,
    receipt_type="note",
)

update_human_work_state(session.session_id, "claimed")
update_human_work_state(session.session_id, "in_progress")
update_human_work_state(
    session.session_id,
    "completed",
    completion_summary="The source supports claim C with one caveat.",
    receipt="private-source-note-2026-05-20",
    confidence="high",
)
```

After completion, the organization surface exposes:

- `a2h_waiting_on_human_sessions`: empty for this session after completion;
- `a2h_followup_sessions`: the researcher must integrate the result;
- `a2h_missing_receipt_sessions`: empty if the receipt was supplied;
- `a2h_pressure`: non-empty only if repeated A2H pressure appears for the same
  role and bottleneck class.

The researcher should close the A2A obligation only after the human result is
integrated into the work artifact.

## When To Open An Accountability Case

Do not open an accountability case for every A2H session. Open one when the
human work creates or accepts residual risk:

- irreversible external action;
- recourse owed to another party;
- authority-envelope exception;
- externality-bearing decision;
- high-impact taste, legitimacy, safety, or relationship judgment.

The A2H session records the work. The accountability case records who owns
closure.

## What This Avoids

- The human is not only an approval button.
- The agent does not become the human's manager.
- A private conversation or restricted-system check is not over-logged.
- A role office cannot forget to integrate work it requested from the human.
