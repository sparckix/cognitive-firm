"""First-party actor identity and attribution records.

Authentication can be delegated to an IdP. This module records the
organization-level actor context that cognitive-firm needs for accountable
state changes.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.actor_membership import actor_has_membership
from cognitive_firm.orchestration.resource_envelope import KernelResource, make_resource


ActorKind = Literal["human", "agent", "service"]
VALID_ACTOR_KINDS = {"human", "agent", "service"}
DEFAULT_ACTOR_IDENTITY_LOG = ORG_ROOT_DIR / "identity" / "actor_identities.jsonl"


@dataclass(frozen=True)
class ActorIdentity:
    actor_id: str
    actor_kind: ActorKind
    display_name: str
    auth_subject: str | None = None
    identity_provider: str | None = None
    roles_allowed: list[str] = field(default_factory=list)
    tenant_ids: list[str] = field(default_factory=list)
    status: str = "active"
    created_at_utc: str = ""
    updated_at_utc: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActorContext:
    actor_id: str
    actor_kind: ActorKind
    role_id: str | None = None
    surface: str = "kernel_service"
    auth_subject: str | None = None
    identity_provider: str | None = None
    session_id: str | None = None
    correlation_id: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def register_actor_identity(
    *,
    actor_id: str,
    actor_kind: ActorKind | str,
    display_name: str,
    auth_subject: str | None = None,
    identity_provider: str | None = None,
    roles_allowed: list[str] | None = None,
    tenant_ids: list[str] | None = None,
    status: str = "active",
    metadata: dict[str, Any] | None = None,
    log_path: Path | None = None,
) -> ActorIdentity:
    """Register or replace one actor identity row."""
    if not actor_id.strip():
        raise ValueError("actor_id is required")
    if not display_name.strip():
        raise ValueError("display_name is required")
    kind = _validate_kind(actor_kind)
    now = _now_iso()
    path = log_path or DEFAULT_ACTOR_IDENTITY_LOG
    existing = [row for row in _read_jsonl(path) if row.get("actor_id") != actor_id]
    identity = ActorIdentity(
        actor_id=actor_id,
        actor_kind=kind,  # type: ignore[arg-type]
        display_name=display_name,
        auth_subject=auth_subject,
        identity_provider=identity_provider,
        roles_allowed=roles_allowed or [],
        tenant_ids=tenant_ids or [],
        status=status,
        created_at_utc=now,
        updated_at_utc=now,
        metadata=metadata or {},
    )
    _write_jsonl(path, [*existing, asdict(identity)])
    return identity


def list_actor_identities(
    *,
    actor_kind: ActorKind | str | None = None,
    status: str | None = None,
    log_path: Path | None = None,
) -> list[ActorIdentity]:
    kind = _validate_kind(actor_kind) if actor_kind is not None else None
    out: list[ActorIdentity] = []
    for row in _read_jsonl(log_path or DEFAULT_ACTOR_IDENTITY_LOG):
        identity = ActorIdentity(**row)
        if kind is not None and identity.actor_kind != kind:
            continue
        if status is not None and identity.status != status:
            continue
        out.append(identity)
    return out


def get_actor_identity(actor_id: str, *, log_path: Path | None = None) -> ActorIdentity | None:
    for identity in list_actor_identities(log_path=log_path):
        if identity.actor_id == actor_id:
            return identity
    return None


def actor_identity_resource(identity: ActorIdentity) -> KernelResource:
    """Project an actor identity into the common kernel resource envelope."""
    labels = {
        "actor_kind": identity.actor_kind,
        "status": identity.status,
    }
    if identity.identity_provider:
        labels["identity_provider"] = identity.identity_provider
    links: list[dict[str, str]] = []
    for role_id in identity.roles_allowed:
        links.append({"rel": "allowed_role", "href": role_id})
    for tenant_id in identity.tenant_ids:
        links.append({"rel": "tenant", "href": tenant_id})
    return make_resource(
        kind="ActorIdentity",
        name=identity.actor_id,
        resource_id=identity.actor_id,
        stability="alpha",
        labels=labels,
        annotations={
            key: str(value)
            for key, value in identity.metadata.items()
            if isinstance(key, str) and value is not None
        },
        spec={
            "actor_kind": identity.actor_kind,
            "display_name": identity.display_name,
            "auth_subject": identity.auth_subject,
            "identity_provider": identity.identity_provider,
            "roles_allowed": identity.roles_allowed,
            "tenant_ids": identity.tenant_ids,
        },
        status={
            "status": identity.status,
            "created_at_utc": identity.created_at_utc,
            "updated_at_utc": identity.updated_at_utc,
        },
        links=links,
    )


def build_actor_context(
    *,
    actor_id: str,
    actor_kind: ActorKind | str = "service",
    role_id: str | None = None,
    surface: str = "kernel_service",
    auth_subject: str | None = None,
    identity_provider: str | None = None,
    session_id: str | None = None,
    correlation_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    identity_log: Path | None = None,
    membership_log: Path | None = None,
    enforce_registered: bool = False,
    enforce_membership: bool = False,
) -> ActorContext:
    """Build an actor context for one mutation.

    `enforce_registered=False` keeps T1 lightweight. T2 deployments can require
    prior registration and role membership.
    """
    if not actor_id.strip():
        raise ValueError("actor_id is required")
    kind = _validate_kind(actor_kind)
    identity = get_actor_identity(actor_id, log_path=identity_log)
    if enforce_registered and identity is None:
        raise PermissionError(f"actor is not registered: {actor_id}")
    if identity is not None:
        if identity.status != "active":
            raise PermissionError(f"actor is not active: {actor_id}")
        if auth_subject and identity.auth_subject and identity.auth_subject != auth_subject:
            raise PermissionError(f"authenticated subject cannot act as {actor_id}")
        if (
            identity_provider
            and identity.identity_provider
            and identity.identity_provider != identity_provider
        ):
            raise PermissionError(f"identity provider cannot act as {actor_id}")
        if role_id and identity.roles_allowed and role_id not in identity.roles_allowed:
            raise PermissionError(f"actor {actor_id} is not allowed to act as {role_id}")
        if tenant_id and identity.tenant_ids and tenant_id not in identity.tenant_ids:
            raise PermissionError(f"actor {actor_id} is not allowed in tenant {tenant_id}")
        kind = identity.actor_kind
        auth_subject = auth_subject or identity.auth_subject
        identity_provider = identity_provider or identity.identity_provider
    if enforce_membership and role_id and not actor_has_membership(
        actor_id=actor_id,
        role_id=role_id,
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=membership_log,
    ):
        raise PermissionError(f"actor {actor_id} has no active membership for {role_id}")
    return ActorContext(
        actor_id=actor_id,
        actor_kind=kind,  # type: ignore[arg-type]
        role_id=role_id,
        surface=surface,
        auth_subject=auth_subject,
        identity_provider=identity_provider,
        session_id=session_id,
        correlation_id=correlation_id,
        tenant_id=tenant_id,
        project_id=project_id,
        metadata=metadata or {},
    )


def actor_context_from_payload(
    payload: dict[str, Any],
    *,
    default_actor_id: str = "service.kernel",
    default_actor_kind: ActorKind | str = "service",
    default_surface: str = "kernel_service",
    identity_log: Path | None = None,
    membership_log: Path | None = None,
    enforce_registered: bool = False,
    enforce_membership: bool = False,
) -> ActorContext:
    raw = payload.get("actor_context")
    data = raw if isinstance(raw, dict) else {}
    return build_actor_context(
        actor_id=str(data.get("actor_id") or payload.get("actor_id") or default_actor_id),
        actor_kind=str(data.get("actor_kind") or payload.get("actor_kind") or default_actor_kind),
        role_id=_optional_str(data.get("role_id") or payload.get("role_id")),
        surface=str(data.get("surface") or payload.get("surface") or default_surface),
        auth_subject=_optional_str(data.get("auth_subject") or payload.get("auth_subject")),
        identity_provider=_optional_str(
            data.get("identity_provider") or payload.get("identity_provider")
        ),
        session_id=_optional_str(data.get("session_id") or payload.get("session_id")),
        correlation_id=_optional_str(data.get("correlation_id") or payload.get("correlation_id")),
        tenant_id=_optional_str(data.get("tenant_id") or payload.get("tenant_id")),
        project_id=_optional_str(data.get("project_id") or payload.get("project_id")),
        metadata=dict(data.get("metadata") or {}),
        identity_log=identity_log,
        membership_log=membership_log,
        enforce_registered=enforce_registered,
        enforce_membership=enforce_membership,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_kind(value: ActorKind | str) -> str:
    text = str(value)
    if text not in VALID_ACTOR_KINDS:
        raise ValueError(f"invalid actor_kind {text!r}; expected one of {sorted(VALID_ACTOR_KINDS)}")
    return text


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage cognitive-firm actor identities.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    register = sub.add_parser("register")
    register.add_argument("--actor-id", required=True)
    register.add_argument("--actor-kind", required=True)
    register.add_argument("--display-name", required=True)
    register.add_argument("--auth-subject")
    register.add_argument("--identity-provider")
    register.add_argument("--role", action="append", default=[])
    register.add_argument("--tenant-id", action="append", default=[])
    register.add_argument("--log-path", type=Path)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--actor-kind")
    list_parser.add_argument("--status")
    list_parser.add_argument("--log-path", type=Path)
    list_parser.add_argument("--resource", action="store_true", help="render resource envelopes")
    args = parser.parse_args(argv)
    if args.cmd == "register":
        identity = register_actor_identity(
            actor_id=args.actor_id,
            actor_kind=args.actor_kind,
            display_name=args.display_name,
            auth_subject=args.auth_subject,
            identity_provider=args.identity_provider,
            roles_allowed=args.role,
            tenant_ids=args.tenant_id,
            log_path=args.log_path,
        )
        print(json.dumps(asdict(identity), sort_keys=True))
        return 0
    if args.cmd == "list":
        for identity in list_actor_identities(
            actor_kind=args.actor_kind,
            status=args.status,
            log_path=args.log_path,
        ):
            payload = actor_identity_resource(identity).as_dict() if args.resource else asdict(identity)
            print(json.dumps(payload, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
