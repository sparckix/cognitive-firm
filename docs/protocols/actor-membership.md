# Actor Membership

**Status:** first-party interface shipped.
**Module:** `cognitive_firm.orchestration.actor_membership`
**Tests:** `tests/test_actor_membership.py`, `tests/test_kernel_service.py`

Actor membership records which organizational role an actor may exercise in a
tenant or project scope. It is the bridge between identity and authority.

Two humans can operate inside the same cognitive-firm deployment when they have
separate actor identities and explicit memberships. This protocol is not a full
enterprise IAM system; it is the kernel record that says this actor may act as
this role in this scope.

## Boundary

Actor identity answers:

- who the actor is;
- whether the actor is human, agent, or service;
- which authenticated subject an external IdP supplied;
- which roles or tenants are broadly allowed.

Actor membership answers:

- which role assignment is active;
- who granted it;
- what decision-right basis justifies it;
- which tenant or project scope it applies to;
- when the assignment starts, expires, or is revoked.

Authentication, lifecycle provisioning, SSO, SCIM, HRIS sync, and enterprise
directory policy remain outside the kernel. Tenant deployments can map those
systems into actor identity and actor membership records.

For directory-driven setup, use [Identity Provisioning](identity-provisioning.md)
to apply idempotent actor and membership plans.

## Record Shape

```json
{
  "assignment_id": "mem_123",
  "actor_id": "human.alice",
  "role_id": "role.manager",
  "granted_by": "human.owner",
  "decision_right_basis": "team operating agreement",
  "tenant_id": "tenant-a",
  "project_id": "project-1",
  "status": "active",
  "starts_at_utc": "2026-05-20T12:00:00+00:00",
  "expires_at_utc": "2026-06-20T12:00:00+00:00",
  "metadata": {}
}
```

`tenant_id` and `project_id` may be omitted for broader assignments. When a
request supplies a tenant or project, a membership with no tenant/project is
treated as broader scope.

## Resource Projection

`actor_membership_resource(...)` projects a grant into the common
[`Resource Envelope`](resource-envelope.md). The membership JSONL row remains
the canonical authority record; the resource view is for admin adapters,
dashboards, migration checks, and conformance fixtures:

```text
kind: ActorMembership
metadata: assignment id, tenant/project, labels, annotations
spec: actor, role, grantor, decision-right basis, start/expiry bounds
status: active/revoked/suspended/expired plus timestamps
links: actor, role, grantor
```

The CLI can render the same compatibility shape:

```bash
python -m cognitive_firm.orchestration.actor_membership list --resource
```

## Service Boundary

The kernel service exposes:

- `POST /kernel/memberships`;
- `POST /kernel/memberships/{assignment_id}/revoke`.

For strict local enforcement, start the service with registered actors and
membership enforcement:

```bash
cognitive-firm-kernel-service \
  --enforce-registered-actors \
  --enforce-actor-membership
```

Bootstrapping is normally done by a setup script, service actor, or a temporary
un-enforced local service config. After bootstrap, role-bearing mutations can
require both a registered actor and an active membership.

In strict kernel-service modes, actor and membership administration routes also
require an identity-admin role such as `role.identity_admin`, `role.owner`, or
`role.principal`.

## T1 / T2

| Concern | T1 | Lean T2 |
|---|---|---|
| Multiple humans | Trusted shared repo process | Explicit actor identities and memberships |
| Role authority | Convention plus mandate review | Membership enforcement by actor/role/tenant/project |
| Provisioning | Local script or manual record | Tenant maps IdP/HRIS/admin workflow into records |
| Revocation | Manual edit or CLI | Revocation record plus service enforcement |
| Enterprise IAM | Out of scope | Adapter boundary, not kernel policy |

## CLI

```bash
cognitive-firm-actor-membership grant \
  --actor-id human.alice \
  --role-id role.manager \
  --granted-by human.owner \
  --decision-right-basis "team operating agreement" \
  --tenant-id tenant-a
```

The CLI writes to `org/identity/actor_memberships.jsonl` by default.
