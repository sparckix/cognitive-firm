"""L0 — the userland enrollment layer.

L0 turns an authenticated subject into a firm-recognized role-holder. It is a
*guided composition* of two existing kernel steps — register an identity, then
grant a scoped role membership — fronted by an **authority preview** so the
operator approves a plain-language statement of what the role can do, never a
YAML diff. It adds no kernel mechanism.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cognitive_firm.orchestration.actor_identity import register_actor_identity
from cognitive_firm.orchestration.actor_membership import grant_actor_membership
from cognitive_firm.userland import vocabulary


class EnrollmentError(ValueError):
    """Raised when an enrollment cannot proceed."""


@dataclass(frozen=True)
class AuthorityPreview:
    """A plain-language statement of what holding a role grants — what the
    operator approves before a membership is granted."""

    role_id: str
    role_class: str | None
    statements: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "role_id": self.role_id,
            "role_class": self.role_class,
            "statements": list(self.statements),
        }


@dataclass(frozen=True)
class EnrollmentResult:
    """The record of one completed enrollment."""

    actor_id: str
    role_id: str
    assignment_id: str
    display_name: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "role_id": self.role_id,
            "assignment_id": self.assignment_id,
            "display_name": self.display_name,
        }


def _load_role(org_root: Path, role_id: str) -> dict[str, Any]:
    role_file = Path(org_root) / "roles" / f"{role_id}.yaml"
    if not role_file.is_file():
        raise EnrollmentError(f"role '{role_id}' not found at {role_file}")
    try:
        data = yaml.safe_load(role_file.read_text())
    except yaml.YAMLError as exc:
        raise EnrollmentError(f"role '{role_id}' does not parse: {exc}") from exc
    if not isinstance(data, dict):
        raise EnrollmentError(f"role '{role_id}' is not a mapping")
    return data


def preview(*, role_id: str, org_root: Path) -> AuthorityPreview:
    """A plain-language statement of what holding ``role_id`` would grant.

    Rendered through the L4 vocabulary, so the operator reads governance
    meaning ("this role can write anywhere"), not raw role YAML.
    """
    role = _load_role(org_root, role_id)
    statements: list[str] = [
        vocabulary.render("authorized_paths", role.get("authorized_paths") or [])
    ]
    escalates_to = role.get("escalates_to") or []
    if escalates_to:
        statements.append(
            "escalates decisions it cannot make to: "
            + ", ".join(str(e) for e in escalates_to)
        )
    else:
        statements.append(
            "this is an authority role — its decisions escalate to no one"
        )
    mandate_path = role.get("mandate_path")
    if mandate_path:
        statements.append(f"its written scope (mandate) is at: {mandate_path}")
    return AuthorityPreview(
        role_id=role_id,
        role_class=role.get("role_class"),
        statements=tuple(statements),
    )


def _actor_id_for(auth_subject: str) -> str:
    """Derive a firm actor id from an authenticated subject.

    Authority is per-actor, so distinct subjects must always get distinct ids.
    A readable slug alone collides — ``a.b@x.com``, ``a-b@x.com`` and
    ``a_b@x.com`` all reduce to the same slug. So the id pairs a readable slug
    with a short, deterministic hash of the *full original* ``auth_subject``;
    the hash disambiguates subjects the slug cannot. Deterministic: the same
    subject always yields the same id.
    """
    slug = "".join(
        c if c.isalnum() else "_" for c in auth_subject.lower()
    ).strip("_")
    digest = hashlib.sha256(auth_subject.encode("utf-8")).hexdigest()[:8]
    return f"human_{slug}_{digest}" if slug else f"human_unknown_{digest}"


def enroll(
    *,
    auth_subject: str,
    display_name: str,
    role_id: str,
    decision_right_basis: str,
    granted_by: str,
    actor_id: str | None = None,
    tenant_id: str | None = None,
    expires_at_utc: str | None = None,
    identity_log: Path | None = None,
    membership_log: Path | None = None,
) -> EnrollmentResult:
    """Register a human identity, then grant the scoped role membership.

    Both are governed kernel events. ``decision_right_basis`` is required —
    authority is never implicit. Raises ``EnrollmentError`` on missing input.
    """
    if not str(auth_subject or "").strip():
        raise EnrollmentError("auth_subject is required")
    if not str(role_id or "").strip():
        raise EnrollmentError("role_id is required")
    if not str(decision_right_basis or "").strip():
        raise EnrollmentError(
            "decision_right_basis is required - authority is never implicit"
        )

    actor_id = actor_id or _actor_id_for(auth_subject)
    register_actor_identity(
        actor_id=actor_id,
        actor_kind="human",
        display_name=display_name,
        auth_subject=auth_subject,
        roles_allowed=[role_id],
        tenant_ids=[tenant_id] if tenant_id else None,
        log_path=identity_log,
    )
    membership = grant_actor_membership(
        actor_id=actor_id,
        role_id=role_id,
        granted_by=granted_by,
        decision_right_basis=decision_right_basis,
        tenant_id=tenant_id,
        expires_at_utc=expires_at_utc,
        log_path=membership_log,
    )
    return EnrollmentResult(
        actor_id=actor_id,
        role_id=role_id,
        assignment_id=membership.assignment_id,
        display_name=display_name,
    )
