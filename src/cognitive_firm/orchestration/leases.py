"""First-party leases for mutable kernel resources.

Leases are time-bounded write claims. They do not authenticate an actor; they
protect resources from concurrent mutation once a deployment has multiple
operators or writers.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.actor_identity import ActorContext


LeaseState = Literal["active", "released", "expired"]
DEFAULT_LEASES_LOG = ORG_ROOT_DIR / "leases" / "leases.jsonl"
TERMINAL_STATES = {"released", "expired"}


@dataclass(frozen=True)
class LeaseRecord:
    lease_id: str
    resource_ref: str
    held_by_actor_id: str
    held_by_role_id: str | None
    acquired_at_utc: str
    expires_at_utc: str
    state: LeaseState = "active"
    fencing_token: int = 1
    released_at_utc: str | None = None
    purpose: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def acquire_lease(
    *,
    resource_ref: str,
    actor: ActorContext,
    ttl_seconds: int = 300,
    purpose: str = "",
    metadata: dict[str, Any] | None = None,
    log_path: Path | None = None,
) -> LeaseRecord:
    """Acquire a lease for one resource or raise when another active lease holds it."""
    if not resource_ref.strip():
        raise ValueError("resource_ref is required")
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")
    path = log_path or DEFAULT_LEASES_LOG
    with _lease_file_lock(path):
        rows = _read_jsonl(path)
        now = _now()
        active = [
            LeaseRecord(**row)
            for row in rows
            if row.get("resource_ref") == resource_ref
            and row.get("state") == "active"
            and _parse_iso(row.get("expires_at_utc")) > now
        ]
        if active:
            holder = active[-1]
            raise PermissionError(
                f"resource {resource_ref} is leased by {holder.held_by_actor_id} until "
                f"{holder.expires_at_utc}"
            )
        max_token = max(
            [int(row.get("fencing_token") or 0) for row in rows if row.get("resource_ref") == resource_ref],
            default=0,
        )
        lease = LeaseRecord(
            lease_id=f"lease_{uuid.uuid4().hex[:12]}",
            resource_ref=resource_ref,
            held_by_actor_id=actor.actor_id,
            held_by_role_id=actor.role_id,
            acquired_at_utc=now.isoformat(),
            expires_at_utc=(now + timedelta(seconds=ttl_seconds)).isoformat(),
            fencing_token=max_token + 1,
            purpose=purpose,
            metadata=metadata or {},
        )
        _append_jsonl(path, asdict(lease))
        return lease


def release_lease(
    lease_id: str,
    *,
    actor: ActorContext,
    log_path: Path | None = None,
) -> LeaseRecord:
    """Release a lease held by the actor."""
    path = log_path or DEFAULT_LEASES_LOG
    with _lease_file_lock(path):
        rows = _read_jsonl(path)
        updated: LeaseRecord | None = None
        next_rows: list[dict[str, Any]] = []
        for row in rows:
            if row.get("lease_id") == lease_id:
                if row.get("held_by_actor_id") != actor.actor_id:
                    raise PermissionError("only the lease holder can release the lease")
                if row.get("state") in TERMINAL_STATES:
                    updated = LeaseRecord(**row)
                else:
                    row = dict(row)
                    row["state"] = "released"
                    row["released_at_utc"] = _now().isoformat()
                    updated = LeaseRecord(**row)
            next_rows.append(row)
        if updated is None:
            raise KeyError(f"lease not found: {lease_id}")
        _write_jsonl(path, next_rows)
        return updated


def list_leases(
    *,
    resource_ref: str | None = None,
    state: LeaseState | str | None = None,
    log_path: Path | None = None,
) -> list[LeaseRecord]:
    now = _now()
    out: list[LeaseRecord] = []
    for row in _read_jsonl(log_path or DEFAULT_LEASES_LOG):
        lease = LeaseRecord(**row)
        if lease.state == "active" and _parse_iso(lease.expires_at_utc) <= now:
            lease = LeaseRecord(**{**asdict(lease), "state": "expired"})
        if resource_ref is not None and lease.resource_ref != resource_ref:
            continue
        if state is not None and lease.state != state:
            continue
        out.append(lease)
    return out


def verify_lease(
    *,
    resource_ref: str,
    lease_id: str | None,
    actor: ActorContext,
    required: bool = False,
    fencing_token: int | None = None,
    log_path: Path | None = None,
) -> LeaseRecord | None:
    """Verify that a lease authorizes this actor to mutate a resource."""
    if not lease_id:
        if required:
            raise PermissionError(f"lease required for {resource_ref}")
        return None
    matches = [
        lease
        for lease in list_leases(resource_ref=resource_ref, state="active", log_path=log_path)
        if lease.lease_id == lease_id
    ]
    if not matches:
        raise PermissionError(f"active lease not found for {resource_ref}: {lease_id}")
    lease = matches[-1]
    if lease.held_by_actor_id != actor.actor_id:
        raise PermissionError("lease holder does not match actor")
    if fencing_token is not None and lease.fencing_token != fencing_token:
        raise PermissionError("lease fencing token does not match")
    return lease


def lease_summary(lease: LeaseRecord) -> dict[str, Any]:
    return asdict(lease)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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


@contextmanager
def _lease_file_lock(path: Path):
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage cognitive-firm resource leases.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    acquire = sub.add_parser("acquire")
    acquire.add_argument("--resource-ref", required=True)
    acquire.add_argument("--actor-id", required=True)
    acquire.add_argument("--actor-kind", default="service")
    acquire.add_argument("--role-id")
    acquire.add_argument("--surface", default="cli")
    acquire.add_argument("--ttl-seconds", type=int, default=300)
    acquire.add_argument("--purpose", default="")
    acquire.add_argument("--log-path", type=Path)
    release = sub.add_parser("release")
    release.add_argument("lease_id")
    release.add_argument("--actor-id", required=True)
    release.add_argument("--actor-kind", default="service")
    release.add_argument("--role-id")
    release.add_argument("--surface", default="cli")
    release.add_argument("--log-path", type=Path)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--resource-ref")
    list_parser.add_argument("--state")
    list_parser.add_argument("--log-path", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "acquire":
        actor = ActorContext(
            actor_id=args.actor_id,
            actor_kind=args.actor_kind,
            role_id=args.role_id,
            surface=args.surface,
        )
        lease = acquire_lease(
            resource_ref=args.resource_ref,
            actor=actor,
            ttl_seconds=args.ttl_seconds,
            purpose=args.purpose,
            log_path=args.log_path,
        )
        print(json.dumps(lease_summary(lease), sort_keys=True))
        return 0
    if args.cmd == "release":
        actor = ActorContext(
            actor_id=args.actor_id,
            actor_kind=args.actor_kind,
            role_id=args.role_id,
            surface=args.surface,
        )
        lease = release_lease(args.lease_id, actor=actor, log_path=args.log_path)
        print(json.dumps(lease_summary(lease), sort_keys=True))
        return 0
    if args.cmd == "list":
        for lease in list_leases(
            resource_ref=args.resource_ref,
            state=args.state,
            log_path=args.log_path,
        ):
            print(json.dumps(lease_summary(lease), sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
