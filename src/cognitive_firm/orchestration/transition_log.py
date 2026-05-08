"""Canonical local transition log writer for the org runtime.

This is the solo/local projection of the enterprise event outbox. Every
governance mutation should eventually route through this schema. At scale this
becomes a Postgres outbox/event stream; locally it is JSONL.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cognitive_firm.common.paths import REPO_ROOT


TRANSITIONS_LOG = REPO_ROOT / "ztare_workspace" / "transitions.jsonl"


def append_transition(
    *,
    event: str,
    actor: str,
    role_id: str | None = None,
    surface: str,
    subject: str,
    payload: dict[str, Any] | None = None,
    causality_id: str | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Append one canonical org transition and return the record.

    log_path defaults to the module-level TRANSITIONS_LOG, resolved at call
    time (not at function-definition time) so monkeypatching the module
    constant in tests propagates to every call site without the test
    needing to thread log_path through every primitive.
    """
    # Resolve default at call time so monkeypatching TRANSITIONS_LOG works.
    import sys
    if log_path is None:
        log_path = sys.modules[__name__].TRANSITIONS_LOG
    record = {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "actor": actor,
        "role_id": role_id,
        "surface": surface,
        "subject": subject,
        "causality_id": causality_id,
        "payload": payload or {},
    }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
    return record
