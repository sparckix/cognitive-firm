# Identity Provider Adapters

**Status:** adapter interface, gateway-header adapter, and JWT adapter seam shipped.
**Module:** `cognitive_firm.identity_providers`
**Tests:** `tests/test_identity_providers.py`, `tests/test_kernel_service.py`

Identity provider adapters authenticate requests to the kernel service. They
are not the source of organizational authority.

## Boundary

An identity provider adapter answers:

> Did this request authenticate, and what subject facts were asserted?

The kernel answers:

> May this actor, under this role, mutate this resource now?

That second question uses [Actor Identity](actor-identity.md),
[Actor Membership](actor-membership.md), [Leases](leases.md), mandates, and
accountability records.

## Interface

```python
class IdentityProviderAdapter(Protocol):
    provider_id: str

    def authenticate(self, headers: Mapping[str, str]) -> AuthenticatedSubject | None:
        ...
```

`AuthenticatedSubject` can carry:

- `auth_subject`;
- `identity_provider`;
- optional `actor_id`;
- optional `actor_kind`;
- optional allowed roles/tenants;
- raw claims.

## Built-In Local Adapter

`StaticBearerTokenIdentityProvider` is a small local/dev adapter:

```python
from cognitive_firm.identity_providers import (
    AuthenticatedSubject,
    StaticBearerTokenIdentityProvider,
)

provider = StaticBearerTokenIdentityProvider({
    "token": AuthenticatedSubject(
        auth_subject="oidc:alice",
        identity_provider="example-idp",
        actor_id="human.alice",
        actor_kind="human",
    )
})
```

For the CLI service:

```bash
export COGNITIVE_FIRM_KERNEL_TOKEN=...
export COGNITIVE_FIRM_KERNEL_ACTOR_ID=human.alice
export COGNITIVE_FIRM_KERNEL_ACTOR_KIND=human
cognitive-firm-kernel-service --require-token
```

This is not a replacement for OIDC/SAML. It is a T1/local adapter and a
conformance shape for stronger providers.

## Gateway-Verified OIDC/SAML/mTLS

`TrustedHeaderIdentityProvider` is the public-kernel adapter for deployments
where an ingress, reverse proxy, or API gateway has already verified OIDC,
SAML, or mTLS identity. It maps trusted headers into `AuthenticatedSubject`:

```python
from cognitive_firm.identity_providers import TrustedHeaderIdentityProvider

provider = TrustedHeaderIdentityProvider(provider_id="corp-oidc")
```

Default headers:

- `X-Auth-Subject`
- `X-Auth-Actor-Id`
- `X-Auth-Actor-Kind`
- `X-Auth-Roles`
- `X-Auth-Tenants`
- `X-Auth-Claim-*`

This adapter must only sit behind a trusted boundary that strips inbound spoofed
headers and injects verified identity headers. Do not expose it directly to the
public internet.

## OIDC / JWT Adapter Seam

`JwtBearerIdentityProvider` maps verified OIDC-style JWT claims into
`AuthenticatedSubject`. JWT verification is pluggable: production deployments
should use a tenant-selected OIDC/JWKS verifier or API gateway library. The
kernel only needs validated claims.

```python
from cognitive_firm.identity_providers import JwtBearerIdentityProvider

provider = JwtBearerIdentityProvider(
    verifier=tenant_oidc_jwks_verifier,
    provider_id="corp-oidc",
)
```

Default claim mapping:

- `sub` -> `auth_subject`
- `cf_actor_id` -> `actor_id`
- `cf_actor_kind` -> `actor_kind`
- `cf_roles` -> `roles_allowed`
- `cf_tenants` -> `tenant_ids`

The repo includes `HmacJwtVerifier` only for deterministic local conformance
fixtures. It is not a production OIDC verifier.

## Third-Party Providers

A tenant should implement OIDC, SAML, mTLS, or API gateway authentication as an
adapter that returns `AuthenticatedSubject`. The adapter should not mutate
kernel state and should not decide role authority directly.

If the tenant wants directory-driven actor setup, use
[Identity Provisioning](identity-provisioning.md) to compile directory facts
into actor identity and actor-membership records. That keeps login/provisioning
outside the kernel and keeps authority enforcement inside the kernel.

For multi-actor deployments, start the kernel service with authenticated
subjects, subject-scope enforcement, and actor-membership enforcement:

```bash
cognitive-firm-kernel-service \
  --require-token \
  --enforce-subject-scope \
  --enforce-registered-actors \
  --enforce-actor-membership
```

or configure the service embedding to set
`KernelServiceConfig(enforce_subject_scope=True, enforce_actor_membership=True)`.
When enabled, the authenticated subject's `roles_allowed` and `tenant_ids` must
match the requested `actor_context`, and the actor must have an active scoped
membership for the requested role.

## Research Anchors

- [NIST SP 800-63-4](https://pages.nist.gov/800-63-4/) frames digital identity
  as identity proofing, authentication, and federation with risk-selected
  assurance levels.
- [OAuth 2.0 Token Exchange, RFC 8693](https://www.ietf.org/rfc/rfc8693.html)
  provides a standards path for delegated subject/token exchange.
- [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html)
  defines the ID-token claim model used by many OIDC providers.
- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/concepts/semantic-conventions/)
  motivate stable attribution fields across services.
