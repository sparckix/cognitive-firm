# Multi-Actor Authority Blueprint

Use this when more than one human or service actor can work inside the same
cognitive-firm deployment.

This is not an enterprise IAM system. External identity providers authenticate
subjects. The kernel records actor identity, scoped membership, authority,
leases, actions, and accountable closure.

## Minimum Scenario

Two humans and two service actors are enough to test the pattern:

| Actor | Example role | Kernel record |
|---|---|---|
| Human A | requester or reviewer | actor identity + membership |
| Human B | approver or accountable owner | actor identity + membership |
| Service A | runtime or agent worker | actor identity + membership |
| Service B | app or connector | actor identity + membership |

## Flow

1. Identity provider authenticates each subject.
2. `actor_identity` maps subject facts to kernel actor IDs.
3. `actor_membership` grants scoped role authority by tenant/project.
4. A service proposes or performs work through the kernel service.
5. The service acquires a lease before a guarded mutation.
6. Human work sessions capture object-level human contribution when needed.
7. Policy decisions, attestations, and accountability cases record authority
   and residual risk.
8. Organization surface and learning transition compiler expose follow-up work.

## Authority Matrix

Fill this before a pilot.

| Action | Human A | Human B | Service A | Service B |
|---|---|---|---|---|
| Create work item | allow/deny | allow/deny | allow/deny | allow/deny |
| Write canonical state | allow/deny | allow/deny | allow/deny | allow/deny |
| Call external system | allow/deny | allow/deny | allow/deny | allow/deny |
| Accept residual risk | allow/deny | allow/deny | allow/deny | allow/deny |
| Close accountability case | allow/deny | allow/deny | allow/deny | allow/deny |
| Approve learning event | allow/deny | allow/deny | allow/deny | allow/deny |

If the table cannot be filled, the workflow is not ready for unattended or
semi-attended agent work.

## Tests To Run

- registered actor can perform an allowed scoped mutation;
- unregistered actor is rejected;
- registered actor outside tenant/project scope is rejected;
- stale lease is rejected;
- duplicate inbound event or retry is idempotent;
- residual-risk acceptance records an accountable owner.

## Failure Signals

- authority is inferred from chat text;
- one shared service credential performs every action;
- humans are asked only for approval, not bounded work;
- accountability cases have no recourse owner;
- app surfaces write files directly instead of submitting typed intents.
