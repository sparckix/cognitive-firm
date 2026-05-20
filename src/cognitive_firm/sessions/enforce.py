"""Role-session lifecycle helpers for daemon runtimes."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cognitive_firm.common.paths import REPO_ROOT


SESSIONS_DIR = REPO_ROOT / "org" / "sessions"


@dataclass(frozen=True)
class Session:
    session_id: str
    role_id: str
    member_id: str
    substrate: str
    directory: Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_session(
    *,
    role_id: str,
    member_id: str,
    substrate: str,
    mandate_path: Path,
) -> Session:
    """Create a local session record for a daemon invocation."""
    session_id = f"sess_{role_id}_{uuid.uuid4().hex[:10]}"
    directory = SESSIONS_DIR / session_id
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "role_id": role_id,
        "member_id": member_id,
        "substrate": substrate,
        "mandate_path": str(mandate_path),
        "opened_utc": _utc_now(),
    }
    (directory / "session.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return Session(
        session_id=session_id,
        role_id=role_id,
        member_id=member_id,
        substrate=substrate,
        directory=directory,
    )


def require_no_conflict(*args, **kwargs) -> None:
    """Compatibility hook for older daemon code.

    Task-level conflict prevention is handled by ``sessions.claims``. This
    function remains fail-open for session startup because a single principal
    may intentionally run multiple role offices at once.
    """
    return None
