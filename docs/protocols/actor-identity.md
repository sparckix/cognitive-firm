# Actor Identity

**Status:** first-party interface shipped.
**Module:** `cognitive_firm.orchestration.actor_identity`
**Tests:** `tests/test_actor_identity.py`, `tests/test_kernel_service.py`

Actor identity records the organizational actor context attached to kernel
mutations. It is not an authentication provider.

## Boundary

Third-party or tenant-owned systems should authenticate subjects:

- OIDC;
- SAML;
- enterprise IdP;
- device/session controls;
- tenant-specific assurance policy.

The kernel records what matters for organizational accountability:

- `actor_id`;
- `actor_kind`: `human`, `agent`, or `service`;
- `role_id` for the authority context;
- `surface`;
- `auth_subject` and `identity_provider` when supplied by an IdP;
- `session_id`;
- `correlation_id`;
- `tenant_id`;
- `project_id`.

The IdP can say who authenticated. The kernel decides what organizational role
that actor may exercise and records the actor context on mutations.

Actor membership is the companion authority record. Actor identity names the
actor; [Actor Membership](actor-membership.md) grants a role in a tenant or
project scope.

## T1 And T2 Modes

T1 permits unregistered actor context. This is suitable for one trusted host or
a small trusted operator set.

T2 can require registered actors:

```python
from cognitive_firm.orchestration.actor_identity import build_actor_context

context = build_actor_context(
    actor_id="human.alice",
    role_id="role.manager",
    tenant_id="tenant-a",
    identity_log=Path("org/identity/actor_identities.jsonl"),
    enforce_registered=True,
)
```

When `enforce_registered=True`, the kernel verifies:

- the actor exists;
- the actor is active;
- the requested role is allowed if `roles_allowed` is set;
- the requested tenant is allowed if `tenant_ids` is set.

When `enforce_membership=True`, the kernel also requires an active actor
membership for the requested role and scope.

## Service Payload

```json
{
  "actor_context": {
    "actor_id": "human.alice",
    "actor_kind": "human",
    "role_id": "role.manager",
    "surface": "orbit",
    "auth_subject": "oidc:alice",
    "identity_provider": "okta",
    "session_id": "sess_123",
    "correlation_id": "corr_123",
    "tenant_id": "tenant-a",
    "project_id": "project-1"
  }
}
```

## Why First-Party

Accountability is not only login. A governance kernel must know which actor,
under which role, through which surface, touched which resource. That meaning
belongs in the kernel even when authentication is delegated.

## Research Anchors

- [NIST SP 800-63-4](https://pages.nist.gov/800-63-4/) separates identity
  proofing, authentication, and federation assurance levels. The kernel should
  not replace those systems.
- [OAuth 2.0 Token Exchange, RFC 8693](https://www.ietf.org/rfc/rfc8693.html)
  gives a standards path for delegated/impersonation-style token exchange; it
  does not define cognitive-firm role authority.
- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/concepts/semantic-conventions/)
  show the value of stable cross-system attribute names for traces, logs, and
  events.

## T1 / T2

| Concern | T1 | T2 |
|---|---|---|
| Registration | optional | required |
| Authentication | process boundary/shared token | IdP-backed OIDC/SAML |
| Actor fields | accepted from payload | checked against actor registry |
| Role membership | trusted convention | enforced by actor membership and role policy |
