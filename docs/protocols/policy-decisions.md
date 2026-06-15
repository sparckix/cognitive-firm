# Policy Decisions

**Status:** local deterministic interface shipped.
**Module:** `cognitive_firm.orchestration.policy_decisions`
**Tests:** `tests/test_policy_decisions.py`,
`tests/test_kernel_service.py::test_kernel_service_evaluates_and_lists_policy_decisions`

Policy decisions record one bounded allow/deny judgment with the request,
matched rule, reason, evidence refs, and policy ref.

This primitive does not replace:

- role mandates;
- `task_authorization`;
- MCP capability checks;
- EU AI Act deploy gates;
- human approvals.

It gives those surfaces a common audit shape when a deployment needs to record
why a bounded action was allowed or denied. Dispatch-like checks should wrap the
existing authorization result rather than reimplementing dispatch policy.

## Request Shape

```json
{
  "action": "runtime.resume",
  "actor_id": "human.principal",
  "role_id": "role.manager",
  "tenant_id": "tenant-a",
  "project_id": "project-a",
  "resource_ref": "runtime://run-1/resume/needs-human",
  "context": {
    "risk_tier": "low"
  }
}
```

## Rule Shape

```json
{
  "rule_id": "allow-low-risk-resume",
  "effect": "allow",
  "reason": "principal may resume this low-risk run",
  "match": {
    "actor_id": "human.principal",
    "context.risk_tier": "low"
  }
}
```

The local evaluator is first-match. If no rule matches, the default effect is
`deny`.

## Boundary

Tenants own policy content. The kernel owns the decision record shape and the
append-only local log.

Use this primitive when the important fact is the decision itself. Do not use it
as a general workflow language.

For existing authorization surfaces, prefer a wrapper such as
`policy_decision_from_authorization(...)` so fields like `required_approval`,
`terminal`, and `matched_paths` are preserved.

## Service Boundary

Policy decisions are available through the local kernel service:

```text
GET  /kernel/policy-decisions
POST /kernel/policy-decisions/evaluate
```

The service route records the same append-only decision row as the Python
primitive. It exists so adopter demos and runtime adapters do not write
canonical policy rows directly when they are already crossing the kernel service
boundary.

## Resource Projection

The JSONL decision row remains canonical state. `policy_decision_resource(...)`
projects a `PolicyDecision` into the common
[Resource Envelope](resource-envelope.md) for adapter, dashboard, migration, and
conformance use.

The projection carries:

- `spec`: request, policy ref, matched rule, source decision, reason, matched
  paths, and evidence refs;
- `status`: effect, `allowed`, match/default status, required approval,
  terminal flag, and decision timestamp;
- `links`: actor, role, target resource, policy, source decision, and evidence
  refs where present.

The CLI evaluator can emit either the canonical decision row or the resource
view:

```bash
python -m cognitive_firm.orchestration.policy_decisions \
  --request-json '{"action":"kernel.mutate","actor_id":"human.alice","resource_ref":"human_work:hws_1"}' \
  --resource
```

## Tests

Covered by `tests/test_policy_decisions.py`.
