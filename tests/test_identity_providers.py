from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.identity_providers import (  # noqa: E402
    AuthenticatedSubject,
    HmacJwtVerifier,
    JwtBearerIdentityProvider,
    StaticBearerTokenIdentityProvider,
    TrustedHeaderIdentityProvider,
    create_hs256_jwt,
)


def test_static_bearer_token_identity_provider_authenticates_subject():
    provider = StaticBearerTokenIdentityProvider(
        {
            "secret": AuthenticatedSubject(
                auth_subject="oidc:alice",
                identity_provider="test-idp",
                actor_id="human.alice",
                actor_kind="human",
            )
        }
    )

    subject = provider.authenticate({"Authorization": "Bearer secret"})

    assert subject is not None
    assert subject.actor_id == "human.alice"
    assert subject.identity_provider == "test-idp"
    assert provider.authenticate({"Authorization": "Bearer wrong"}) is None


def test_trusted_header_identity_provider_maps_gateway_verified_subject():
    provider = TrustedHeaderIdentityProvider(provider_id="corp-oidc")

    subject = provider.authenticate(
        {
            "X-Auth-Subject": "oidc:alice",
            "X-Auth-Actor-Id": "human.alice",
            "X-Auth-Actor-Kind": "human",
            "X-Auth-Roles": "role.manager, role.researcher",
            "X-Auth-Tenants": "tenant-a,tenant-b",
            "X-Auth-Claim-Email": "alice@example.com",
        }
    )

    assert subject is not None
    assert subject.auth_subject == "oidc:alice"
    assert subject.identity_provider == "corp-oidc"
    assert subject.actor_id == "human.alice"
    assert subject.actor_kind == "human"
    assert subject.roles_allowed == ["role.manager", "role.researcher"]
    assert subject.tenant_ids == ["tenant-a", "tenant-b"]
    assert subject.claims["email"] == "alice@example.com"
    assert provider.authenticate({}) is None


def test_jwt_bearer_identity_provider_maps_verified_claims():
    token = create_hs256_jwt(
        {
            "sub": "oidc:alice",
            "iss": "https://idp.example",
            "aud": "cognitive-firm",
            "exp": 2_000_000_000,
            "cf_actor_id": "human.alice",
            "cf_actor_kind": "human",
            "cf_roles": ["role.manager"],
            "cf_tenants": ["tenant-a"],
        },
        "secret",
    )
    provider = JwtBearerIdentityProvider(
        verifier=HmacJwtVerifier(
            signing_secret="secret",
            issuer="https://idp.example",
            audience="cognitive-firm",
            now=1_900_000_000,
        ),
        provider_id="corp-oidc",
    )

    subject = provider.authenticate({"Authorization": f"Bearer {token}"})

    assert subject is not None
    assert subject.auth_subject == "oidc:alice"
    assert subject.identity_provider == "corp-oidc"
    assert subject.actor_id == "human.alice"
    assert subject.roles_allowed == ["role.manager"]
    assert subject.tenant_ids == ["tenant-a"]


def test_jwt_bearer_identity_provider_rejects_bad_signature():
    token = create_hs256_jwt({"sub": "oidc:alice", "exp": 2_000_000_000}, "secret")
    provider = JwtBearerIdentityProvider(
        verifier=HmacJwtVerifier(signing_secret="wrong", now=1_900_000_000)
    )

    assert provider.authenticate({"Authorization": f"Bearer {token}"}) is None
