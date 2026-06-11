# Identity Provisioning

**Status:** adapter seam shipped.
**Module:** `cognitive_firm.identity_provisioning`
**Tests:** `tests/test_identity_provisioning.py`

Identity provisioning is the bridge from an external directory to kernel-owned
authority records. It is not an IAM admin console.

An IdP authenticates a request. A provisioning adapter can translate directory,
SCIM, HRIS, group, or setup-script facts into:

- actor identity records;
- actor membership records.

The kernel then enforces those records through actor-context resolution and the
kernel service.

## Boundary

The provisioning seam owns:

- loading a tenant-supplied plan;
- registering missing actors;
- granting missing role memberships;
- staying idempotent when replayed.

It does not own:

- login;
- passwordless/mFA/session policy;
- SCIM lifecycle semantics;
- HR approval workflow;
- group-to-role business policy;
- automatic deletion or revocation.

Revocation should be explicit through actor-membership revocation records. A
tenant can add stronger lifecycle policy in its app/config layer.

## Plan Shape

```json
{
  "actors": [
    {
      "actor_id": "human.alice",
      "actor_kind": "human",
      "display_name": "Alice",
      "auth_subject": "oidc:alice",
      "identity_provider": "corp-oidc",
      "roles_allowed": ["role.manager"],
      "tenant_ids": ["tenant-a"]
    }
  ],
  "memberships": [
    {
      "actor_id": "human.alice",
      "role_id": "role.manager",
      "granted_by": "service.provisioner",
      "decision_right_basis": "directory group cf-managers",
      "tenant_id": "tenant-a"
    }
  ]
}
```

Apply a plan:

```bash
cognitive-firm-identity-provisioning provisioning-plan.json
```

## Why This Is Not First-Party IAM

Different organizations already have different identity systems. The kernel
should integrate with those systems. It should receive authenticated subject
facts and compile explicit role authority into records it can enforce.

That keeps the durable organizational question local:

> Which actor may exercise which role in which scope?

while leaving the enterprise identity question external:

> How did this person authenticate, and how was their account provisioned?
