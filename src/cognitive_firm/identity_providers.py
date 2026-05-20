"""Authentication adapter boundary for kernel service deployments.

Identity providers authenticate a request subject. The kernel still owns actor
context, role authority, leases, and accountability.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class AuthenticatedSubject:
    auth_subject: str
    identity_provider: str
    actor_id: str | None = None
    actor_kind: str | None = None
    roles_allowed: list[str] = field(default_factory=list)
    tenant_ids: list[str] = field(default_factory=list)
    claims: dict[str, object] = field(default_factory=dict)


class IdentityProviderAdapter(Protocol):
    """Adapter for request authentication.

    Implementations may wrap OIDC, SAML, mTLS, signed internal tokens, or a
    local static token for development. They should not decide cognitive-firm
    role authority; they only return authenticated subject facts.
    """

    provider_id: str

    def authenticate(self, headers: Mapping[str, str]) -> AuthenticatedSubject | None:
        """Return the authenticated subject or None when authentication fails."""


class JwtClaimsVerifier(Protocol):
    """Verifies a bearer JWT and returns validated claims.

    Production deployments should back this with the tenant's OIDC/JWKS library
    or API gateway. The kernel only needs validated claims.
    """

    def verify(self, token: str) -> dict[str, Any] | None:
        """Return validated claims or None when verification fails."""


@dataclass(frozen=True)
class StaticBearerTokenIdentityProvider:
    """Small local bearer-token provider for T1/dev deployments.

    This is not an enterprise IdP. It lets the local kernel service require a
    bearer token without pulling in a web framework or OIDC dependency.
    """

    subjects_by_token: dict[str, AuthenticatedSubject]
    provider_id: str = "static_bearer"

    def authenticate(self, headers: Mapping[str, str]) -> AuthenticatedSubject | None:
        header = _get_header(headers, "authorization")
        prefix = "Bearer "
        if not header.startswith(prefix):
            return None
        token = header[len(prefix):].strip()
        return self.subjects_by_token.get(token)


@dataclass(frozen=True)
class JwtBearerIdentityProvider:
    """Bearer-JWT identity adapter with pluggable verification.

    This adapter maps verified OIDC-style claims into ``AuthenticatedSubject``.
    It does not decide cognitive-firm role authority.
    """

    verifier: JwtClaimsVerifier
    provider_id: str = "jwt_bearer"
    subject_claim: str = "sub"
    actor_id_claim: str = "cf_actor_id"
    actor_kind_claim: str = "cf_actor_kind"
    roles_claim: str = "cf_roles"
    tenants_claim: str = "cf_tenants"

    def authenticate(self, headers: Mapping[str, str]) -> AuthenticatedSubject | None:
        header = _get_header(headers, "authorization")
        prefix = "Bearer "
        if not header.startswith(prefix):
            return None
        claims = self.verifier.verify(header[len(prefix):].strip())
        if claims is None:
            return None
        subject = str(claims.get(self.subject_claim) or "").strip()
        if not subject:
            return None
        return AuthenticatedSubject(
            auth_subject=subject,
            identity_provider=self.provider_id,
            actor_id=_blank_to_none(str(claims.get(self.actor_id_claim) or "")),
            actor_kind=_blank_to_none(str(claims.get(self.actor_kind_claim) or "")),
            roles_allowed=_claim_list(claims.get(self.roles_claim)),
            tenant_ids=_claim_list(claims.get(self.tenants_claim)),
            claims=dict(claims),
        )


@dataclass(frozen=True)
class HmacJwtVerifier:
    """Deterministic HS256 verifier for local conformance fixtures.

    This is not a production OIDC verifier. It exists so tests can exercise the
    JWT adapter boundary without network access or a cryptography dependency.
    """

    signing_secret: str
    issuer: str | None = None
    audience: str | None = None
    now: int | None = None

    def verify(self, token: str) -> dict[str, Any] | None:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_raw, payload_raw, signature_raw = parts
        header = _decode_json_segment(header_raw)
        if header.get("alg") != "HS256":
            return None
        signed = f"{header_raw}.{payload_raw}".encode("utf-8")
        expected = hmac.new(self.signing_secret.encode("utf-8"), signed, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_encode(expected), signature_raw):
            return None
        claims = _decode_json_segment(payload_raw)
        now = int(self.now if self.now is not None else time.time())
        if "exp" in claims and now >= int(claims["exp"]):
            return None
        if "nbf" in claims and now < int(claims["nbf"]):
            return None
        if self.issuer is not None and claims.get("iss") != self.issuer:
            return None
        if self.audience is not None:
            audience = claims.get("aud")
            if isinstance(audience, list):
                if self.audience not in audience:
                    return None
            elif audience != self.audience:
                return None
        return claims


@dataclass(frozen=True)
class TrustedHeaderIdentityProvider:
    """Adapter for gateway-verified OIDC/SAML/mTLS deployments.

    Put this behind an ingress, reverse proxy, or API gateway that verifies the
    upstream identity token. The adapter only maps already-verified headers
    into an ``AuthenticatedSubject``; it does not perform cryptographic token
    verification itself.
    """

    provider_id: str = "trusted_header"
    subject_header: str = "x-auth-subject"
    actor_id_header: str = "x-auth-actor-id"
    actor_kind_header: str = "x-auth-actor-kind"
    roles_header: str = "x-auth-roles"
    tenants_header: str = "x-auth-tenants"
    claims_prefix: str = "x-auth-claim-"

    def authenticate(self, headers: Mapping[str, str]) -> AuthenticatedSubject | None:
        subject = _get_header(headers, self.subject_header).strip()
        if not subject:
            return None
        claims: dict[str, object] = {}
        prefix = self.claims_prefix.lower()
        for key, value in headers.items():
            lowered = key.lower()
            if lowered.startswith(prefix):
                claims[lowered[len(prefix):]] = value
        return AuthenticatedSubject(
            auth_subject=subject,
            identity_provider=self.provider_id,
            actor_id=_blank_to_none(_get_header(headers, self.actor_id_header)),
            actor_kind=_blank_to_none(_get_header(headers, self.actor_kind_header)),
            roles_allowed=_csv(_get_header(headers, self.roles_header)),
            tenant_ids=_csv(_get_header(headers, self.tenants_header)),
            claims=claims,
        )


def _get_header(headers: Mapping[str, str], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return ""


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _claim_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _csv(value)
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _blank_to_none(value: str) -> str | None:
    text = value.strip()
    return text or None


def _decode_json_segment(segment: str) -> dict[str, Any]:
    raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JWT segment must decode to an object")
    return payload


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def create_hs256_jwt(claims: dict[str, Any], signing_secret: str) -> str:
    """Create an HS256 JWT for local fixtures."""
    header = {"alg": "HS256", "typ": "JWT"}
    header_raw = _b64url_encode(json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    payload_raw = _b64url_encode(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        signing_secret.encode("utf-8"),
        f"{header_raw}.{payload_raw}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{header_raw}.{payload_raw}.{_b64url_encode(signature)}"
