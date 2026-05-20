"""Role membership records for multi-principal cognitive-firm deployments."""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR


MembershipStatus = Literal["active", "suspended", "revoked", "expired"]
VALID_STATUSES = {"active", "suspended", "revoked", "expired"}
DEFAULT_ACTOR_MEMBERSHIP_LOG = ORG_ROOT_DIR / "identity" / "actor_memberships.jsonl"


@dataclass(frozen=True)
class ActorMembership:
    assignment_id: str
    actor_id: str
    role_id: str
    granted_by: str
    decision_right_basis: str
    tenant_id: str | None = None
    project_id: str | None = None
    status: MembershipStatus = "active"
    starts_at_utc: str | None = None
    expires_at_utc: str | None = None
    created_at_utc: str = ""
    updated_at_utc: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def grant_actor_membership(
    *,
    actor_id: str,
    role_id: str,
    granted_by: str,
    decision_right_basis: str,
    tenant_id: str | None = None,
    project_id: str | None = None,
    starts_at_utc: str | None = None,
    expires_at_utc: str | None = None,
    metadata: dict[str, Any] | None = None,
    assignment_id: str | None = None,
    log_path: Path | None = None,
) -> ActorMembership:
    """Grant a scoped role membership to a human, agent, or service actor."""
    if not actor_id.strip():
        raise ValueError("actor_id is required")
    if not role_id.strip():
        raise ValueError("role_id is required")
    if not granted_by.strip():
        raise ValueError("granted_by is required")
    if not decision_right_basis.strip():
        raise ValueError("decision_right_basis is required")
    now = _now_iso()
    membership = ActorMembership(
        assignment_id=assignment_id or f"mem_{uuid.uuid4().hex[:12]}",
        actor_id=actor_id,
        role_id=role_id,
        granted_by=granted_by,
        decision_right_basis=decision_right_basis,
        tenant_id=tenant_id,
        project_id=project_id,
        starts_at_utc=starts_at_utc,
        expires_at_utc=expires_at_utc,
        created_at_utc=now,
        updated_at_utc=now,
        metadata=metadata or {},
    )
    _append_jsonl(log_path or DEFAULT_ACTOR_MEMBERSHIP_LOG, membership.as_dict())
    return membership


def list_actor_memberships(
    *,
    actor_id: str | None = None,
    role_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    status: MembershipStatus | str | None = None,
    log_path: Path | None = None,
) -> list[ActorMembership]:
    if status is not None:
        status = _validate_status(str(status))
    out: list[ActorMembership] = []
    for row in _read_jsonl(log_path or DEFAULT_ACTOR_MEMBERSHIP_LOG):
        membership = ActorMembership(**row)
        if actor_id is not None and membership.actor_id != actor_id:
            continue
        if role_id is not None and membership.role_id != role_id:
            continue
        if tenant_id is not None and membership.tenant_id not in {None, tenant_id}:
            continue
        if project_id is not None and membership.project_id not in {None, project_id}:
            continue
        if status is not None and membership.status != status:
            continue
        out.append(membership)
    return out


def actor_has_membership(
    *,
    actor_id: str,
    role_id: str,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
    now: datetime | None = None,
) -> bool:
    """Return whether actor has an active scoped membership for this request."""
    now = now or datetime.now(timezone.utc)
    for membership in list_actor_memberships(
        actor_id=actor_id,
        role_id=role_id,
        tenant_id=tenant_id,
        project_id=project_id,
        status="active",
        log_path=log_path,
    ):
        if _is_temporally_active(membership, now=now):
            return True
    return False


def revoke_actor_membership(
    assignment_id: str,
    *,
    revoked_by: str,
    reason: str,
    log_path: Path | None = None,
) -> ActorMembership:
    if not revoked_by.strip():
        raise ValueError("revoked_by is required")
    if not reason.strip():
        raise ValueError("reason is required")
    path = log_path or DEFAULT_ACTOR_MEMBERSHIP_LOG
    rows = _read_jsonl(path)
    updated: ActorMembership | None = None
    next_rows: list[dict[str, Any]] = []
    for row in rows:
        row = dict(row)
        if row.get("assignment_id") == assignment_id:
            row["status"] = "revoked"
            row["updated_at_utc"] = _now_iso()
            metadata = dict(row.get("metadata") or {})
            metadata["revoked_by"] = revoked_by
            metadata["revocation_reason"] = reason
            row["metadata"] = metadata
            updated = ActorMembership(**row)
        next_rows.append(row)
    if updated is None:
        raise KeyError(f"membership not found: {assignment_id}")
    _write_jsonl(path, next_rows)
    return updated


def _is_temporally_active(membership: ActorMembership, *, now: datetime) -> bool:
    if membership.starts_at_utc:
        start = _parse_dt(membership.starts_at_utc)
        if start and now < start:
            return False
    if membership.expires_at_utc:
        expiry = _parse_dt(membership.expires_at_utc)
        if expiry and now >= expiry:
            return False
    return True


def _parse_dt(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_status(value: str) -> str:
    if value not in VALID_STATUSES:
        raise ValueError(f"invalid status {value!r}; expected one of {sorted(VALID_STATUSES)}")
    return value


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


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage cognitive-firm actor memberships.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    grant = sub.add_parser("grant")
    grant.add_argument("--actor-id", required=True)
    grant.add_argument("--role-id", required=True)
    grant.add_argument("--granted-by", required=True)
    grant.add_argument("--decision-right-basis", required=True)
    grant.add_argument("--tenant-id")
    grant.add_argument("--project-id")
    grant.add_argument("--expires-at-utc")
    grant.add_argument("--log-path", type=Path)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--actor-id")
    list_parser.add_argument("--role-id")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--status")
    list_parser.add_argument("--log-path", type=Path)
    revoke = sub.add_parser("revoke")
    revoke.add_argument("assignment_id")
    revoke.add_argument("--revoked-by", required=True)
    revoke.add_argument("--reason", required=True)
    revoke.add_argument("--log-path", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "grant":
        membership = grant_actor_membership(
            actor_id=args.actor_id,
            role_id=args.role_id,
            granted_by=args.granted_by,
            decision_right_basis=args.decision_right_basis,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            expires_at_utc=args.expires_at_utc,
            log_path=args.log_path,
        )
        print(json.dumps(membership.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "list":
        for membership in list_actor_memberships(
            actor_id=args.actor_id,
            role_id=args.role_id,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            status=args.status,
            log_path=args.log_path,
        ):
            print(json.dumps(membership.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "revoke":
        membership = revoke_actor_membership(
            args.assignment_id,
            revoked_by=args.revoked_by,
            reason=args.reason,
            log_path=args.log_path,
        )
        print(json.dumps(membership.as_dict(), sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
