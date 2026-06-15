"""Filesystem-backed task claims.

Claims are a local membrane for trusted single-authority deployments. They
prevent two daemon sessions from claiming the same task at the same time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cognitive_firm.common.paths import ORG_ROOT_DIR


CLAIMS_DIR = ORG_ROOT_DIR / "sessions" / "_claims"


@dataclass(frozen=True)
class TaskClaim:
    task_id: str
    session_id: str
    member_id: str
    role_id: str
    claimed_utc: str
    expires_utc: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _claim_path(task_id: str) -> Path:
    safe = task_id.replace("/", "_").replace(":", "__")
    return CLAIMS_DIR / f"{safe}.json"


def _read_claim(path: Path) -> TaskClaim | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return TaskClaim(
        task_id=str(data["task_id"]),
        session_id=str(data["session_id"]),
        member_id=str(data["member_id"]),
        role_id=str(data["role_id"]),
        claimed_utc=str(data["claimed_utc"]),
        expires_utc=str(data["expires_utc"]),
    )


def _is_expired(claim: TaskClaim) -> bool:
    try:
        expires = datetime.fromisoformat(claim.expires_utc)
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires <= _utc_now()


def claim_task(
    *,
    task_id: str,
    session_id: str,
    member_id: str,
    role_id: str,
    ttl_seconds: int = 6 * 3600,
) -> tuple[bool, TaskClaim | None]:
    """Claim a task, returning ``(claimed, conflicting_claim)``."""
    CLAIMS_DIR.mkdir(parents=True, exist_ok=True)
    path = _claim_path(task_id)
    existing = _read_claim(path)
    if existing and not _is_expired(existing) and existing.session_id != session_id:
        return False, existing

    now = _utc_now()
    claim = TaskClaim(
        task_id=task_id,
        session_id=session_id,
        member_id=member_id,
        role_id=role_id,
        claimed_utc=now.isoformat(timespec="seconds"),
        expires_utc=(now + timedelta(seconds=ttl_seconds)).isoformat(timespec="seconds"),
    )
    path.write_text(json.dumps(claim.__dict__, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True, None


def release_claim(*, task_id: str, session_id: str) -> bool:
    path = _claim_path(task_id)
    existing = _read_claim(path)
    if existing is None:
        return False
    if existing.session_id != session_id:
        return False
    path.unlink()
    return True
