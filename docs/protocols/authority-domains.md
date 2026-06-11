# Authority Domains

**Status:** first-party interface shipped for T1-compatible multi-authority
routing.
**Module:** `cognitive_firm.orchestration.authority_domains`
**Tests:** `tests/test_authority_domains.py`,
`tests/test_attention_router.py`, `tests/test_distribution.py`,
`tests/test_kernel_service_userland.py`

Authority domains let one deployment route governance interrupts to different
authority roles by scope: tenant, project, operating unit, resource class, or
decision class.

The primitive is deliberately small. It does not implement IAM, SSO, HRIS,
tenant isolation, approval policy, or enterprise admin UX. Those systems can
provision roles, actor identities, and actor memberships. The kernel records
which authority role owns which scope and resolves the relevant authority for a
given signal.

## Problem

The T1 boot rule is intentionally conservative: one role with
`role_class: authority`. That is easy to inspect and safe for solo or small
trusted-team deployments.

Enterprise deployments often need more than one accountable authority role:

- a tenant owner for tenant-scoped policy;
- a project owner for project-scoped approval;
- a department owner for an operating unit;
- a legal/compliance authority for a decision class;
- a global owner for fallback and residual scope.

Without a typed domain record, multiple authority roles create ambiguity. A
governance interrupt may silently go to the wrong actor, or the kernel has to
fall back to a single default authority.

## Record Shape

Authority domains live under:

```text
org/authority_domains/authority_domains.json
```

Accepted JSON shapes:

```json
{
  "authority_domains": [
    {
      "domain_id": "global",
      "authority_role_id": "role.principal",
      "scope_kind": "global",
      "scope_id": "*",
      "description": "Default authority for unscoped decisions"
    },
    {
      "domain_id": "tenant_a_policy",
      "authority_role_id": "role.tenant_a_owner",
      "scope_kind": "tenant",
      "scope_id": "tenant-a",
      "description": "Tenant A policy and governance review"
    }
  ]
}
```

The top-level value may also be a bare list.

Allowed `scope_kind` values:

| Scope kind | Meaning |
|---|---|
| `global` | Fallback authority. Must use `scope_id: "*"` |
| `tenant` | Tenant-scoped authority |
| `project` | Project-scoped authority |
| `operating_unit` | Department, desk, lane, or station authority |
| `resource_class` | Authority over a resource class such as budget or credential |
| `decision_class` | Authority over a decision class such as publication or policy change |

## Resolution

When a governance signal carries scope metadata, the resolver chooses the most
specific matching authority in this order:

```text
operating_unit -> project -> tenant -> decision_class -> resource_class -> global
```

If two domains claim the same scope, resolution fails closed. The signal stays
visible as unroutable instead of being sent to the wrong actor.

## Boot Rule

Without an authority-domain file, `boot_check` keeps the original T1 invariant:
exactly one authority role.

With an authority-domain file:

- multiple authority roles are allowed;
- every authority role must appear in at least one domain;
- every domain must reference an existing `role_class: authority` role;
- duplicate scopes are rejected;
- non-authority escalation chains must still reach an authority role.

This is not full enterprise isolation. It is the first kernel-level routing
primitive that removes the single-authority assumption without weakening the T1
default.

## Interaction With Actor Membership

Authority domains resolve the role. Actor membership resolves which actor
currently holds that role in a tenant/project scope.

Authority is not intrinsically human in the kernel. Actor identities may be
`human`, `agent`, or `service`; a deployment's mandates, policies, and
membership records decide which actor kinds may hold a given authority role. A
regulated deployment may require human final approval for certain decision
classes. A lab or automation-heavy deployment may delegate bounded authority to
an agent or service role.

For example, a tenant-scoped gate with `tenant_id: "tenant-a"` resolves to
`role.tenant_a_owner`, then the attention router selects an active actor
membership for that role and tenant. If no actor holds the role, the signal is
still surfaced with the role and no actor rather than dropped.

The userland attention router exposes this as
`authority_resolver_from_org(org_root, actor_membership_log=...)`. The helper
reads authority domains and actor memberships, then routes a scoped signal to
the resolved role and the first active actor holder in sorted order. If several
actors hold the role, routing remains deterministic; if none do, the role is
still visible so the staffing gap can be handled.

## CLI

Inspect records:

```bash
cognitive-firm-authority-domains --org-root "$ORG_ROOT" list
```

Validate domains against role files:

```bash
cognitive-firm-authority-domains --org-root "$ORG_ROOT" validate
```

Resolve a scoped authority role:

```bash
cognitive-firm-authority-domains --org-root "$ORG_ROOT" resolve \
  --tenant-id tenant-a \
  --decision-class publication
```

The command prints `role.<role_id>` plus active actor holders on success. If
the role resolves but no active actor membership holds it, the actor column is
`NO_ACTIVE_ACTOR`. It exits nonzero when the scope is unresolved or the domain
file is invalid.

Admin and adapter surfaces can read the same records as resource envelopes:

```bash
cognitive-firm-authority-domains --org-root "$ORG_ROOT" list --resource
```

`authority_domain_resource(...)` projects each domain as `kind:
AuthorityDomain` with scope labels, authority-role links, and optional
tenant/project metadata. The JSON authority-domain file remains canonical; the
resource envelope is only a compatibility view.

To include active actor holders from a non-default membership log:

```bash
cognitive-firm-authority-domains --org-root "$ORG_ROOT" resolve \
  --tenant-id tenant-a \
  --actor-membership-log "$ORG_ROOT/identity/actor_memberships.jsonl"
```

## Boundary

Keep outside this primitive:

- enterprise directory administration;
- SCIM/HRIS lifecycle;
- legal approval policy;
- tenant data isolation;
- Slack/Teams routing UX;
- quorum, voting, or committee decision rules.

Those may be adapters, overlays, or app surfaces. The kernel primitive is the
scope-to-authority map and deterministic resolver.
