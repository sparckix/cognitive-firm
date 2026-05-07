# Licensed under Business Source License 1.1 — see LICENSE-BSL
"""Outbox relay for MCP calls.

Per GP-231 panel verdict (distributed-systems skeptic, 2026-05-07):
the kernel's `transitions.jsonl` is already a durable, ordered, append-only
log. That IS an outbox. The right pattern is to read pending `mcp_call_requested`
rows, dispatch them to the MCP server with a deterministic idempotency key,
and append a follow-up transition (`mcp_call_dispatched` / `mcp_call_failed`).

Crash-safety: if the process dies between the dispatch and the follow-up
transition, the next relay tick re-reads the pending row and retries with
the SAME idempotency key. Server-side idempotency (or our local de-dup
cache) prevents double-write. No 2PC required.

Phase 1 ships the relay with no actual server bindings. The dispatch step
calls a pluggable `_send_mcp_request(server, tool, payload)` which is
stubbed in this phase and replaced with the real MCP client in Phase 1.5.

Schema of an `mcp_call_requested` transition payload:

    {
      "server_name": str,
      "tool_name": str,
      "request": dict,                  # per-tool payload
      "idempotency_key": str,           # canonical: hash(causality_id + sorted(request))
      "timeout_seconds": float,
      "principal_signed_capability_id": Optional[str]   # Phase 2
    }
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

from cognitive_firm.common.paths import REPO_ROOT
from cognitive_firm.orchestration.transition_log import (
    append_transition,
    TRANSITIONS_LOG,
)
from cognitive_firm.role_extensions.mcp_bridge.projections import (
    project_response,
    ProjectionResult,
)


log = logging.getLogger(__name__)

# Local de-dup cache so a crashed-mid-dispatch retry doesn't double-write
# even if the server has no idempotency key support. Cleared per process;
# durable de-dup is server-side responsibility.
_DEDUP_CACHE: set[str] = set()


# ── helpers ────────────────────────────────────────────────────────────


def _read_log(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    out: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    return out


def _idempotency_key(causality_id: Optional[str], request: dict[str, Any]) -> str:
    """Deterministic key from the causal anchor + request payload.

    Same input always yields same key, so a retry of the same logical action
    produces the same key for the server's idempotency check (or our local
    de-dup cache).
    """
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"))
    seed = f"{causality_id or ''}|{canonical}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _is_dispatched(event_id: str, log: list[dict[str, Any]]) -> bool:
    """True if a follow-up `mcp_call_dispatched` or `mcp_call_failed` row
    references the given event_id as causality."""
    for row in log:
        if row.get("event") not in ("mcp_call_dispatched", "mcp_call_failed"):
            continue
        if row.get("payload", {}).get("requested_event_id") == event_id:
            return True
    return False


# ── pluggable transport (stubbed in Phase 1) ──────────────────────────


def _send_mcp_request(
    server_name: str,
    tool_name: str,
    request: dict[str, Any],
    idempotency_key: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Phase 1 stub. Replaced by the real MCP client in Phase 1.5.

    Raises NotImplementedError so any real attempted dispatch in Phase 1
    fails loudly and the relay marks the request as failed with a clear
    reason. Tests inject a fake via the `transport` parameter on
    `dispatch_pending`.
    """
    raise NotImplementedError(
        f"MCP transport not wired (Phase 1.5 deliverable); "
        f"server={server_name} tool={tool_name} key={idempotency_key[:16]}…"
    )


# ── public API ─────────────────────────────────────────────────────────


def pending_count(log_path: Path = TRANSITIONS_LOG) -> int:
    """Return the count of `mcp_call_requested` rows that have no follow-up."""
    log = _read_log(log_path)
    pending = 0
    for row in log:
        if row.get("event") != "mcp_call_requested":
            continue
        if not _is_dispatched(row["event_id"], log):
            pending += 1
    return pending


def dispatch_pending(
    *,
    log_path: Path = TRANSITIONS_LOG,
    max_dispatches: int = 5,
    transport=None,
) -> list[dict[str, Any]]:
    """Read pending mcp_call_requested rows, dispatch them, append follow-ups.

    Returns the list of follow-up transition records appended in this run.

    Args:
        log_path: where to read/write transitions.
        max_dispatches: cap per relay tick so a backlog cannot stall the
            daemon.
        transport: optional (server, tool, request, key, timeout) -> dict
            callable used in tests; defaults to `_send_mcp_request`.
    """
    transport = transport or _send_mcp_request
    log = _read_log(log_path)
    appended: list[dict[str, Any]] = []
    dispatched = 0
    for row in log:
        if dispatched >= max_dispatches:
            break
        if row.get("event") != "mcp_call_requested":
            continue
        if _is_dispatched(row["event_id"], log):
            continue
        payload = row.get("payload") or {}
        server = payload.get("server_name") or ""
        tool = payload.get("tool_name") or ""
        request = payload.get("request") or {}
        idem = payload.get("idempotency_key") or _idempotency_key(
            row.get("causality_id"), request
        )
        timeout = float(payload.get("timeout_seconds") or 30.0)

        if idem in _DEDUP_CACHE:
            log.append(
                _emit_followup(
                    requested_event_id=row["event_id"],
                    actor=row.get("actor", "outbox_relay"),
                    role_id=row.get("role_id"),
                    success=False,
                    response=None,
                    rejection="local de-dup cache hit (already dispatched in this process)",
                    log_path=log_path,
                    appended=appended,
                )
            )
            dispatched += 1
            continue

        try:
            response = transport(server, tool, request, idem, timeout)
        except Exception as exc:  # noqa: BLE001
            log.append(
                _emit_followup(
                    requested_event_id=row["event_id"],
                    actor=row.get("actor", "outbox_relay"),
                    role_id=row.get("role_id"),
                    success=False,
                    response=None,
                    rejection=f"{type(exc).__name__}: {exc}",
                    log_path=log_path,
                    appended=appended,
                )
            )
            dispatched += 1
            continue

        # Project the response deterministically (NO LLM in this path).
        projection: ProjectionResult = project_response(server, tool, response)
        success = projection.transition_class == "mcp_call_dispatched"
        _DEDUP_CACHE.add(idem)
        log.append(
            _emit_followup(
                requested_event_id=row["event_id"],
                actor=row.get("actor", "outbox_relay"),
                role_id=row.get("role_id"),
                success=success,
                response=projection.normalized_payload,
                rejection=projection.rejection_reason,
                log_path=log_path,
                appended=appended,
            )
        )
        dispatched += 1
    return appended


def _emit_followup(
    *,
    requested_event_id: str,
    actor: str,
    role_id: Optional[str],
    success: bool,
    response: Optional[dict[str, Any]],
    rejection: Optional[str],
    log_path: Path,
    appended: list[dict[str, Any]],
) -> dict[str, Any]:
    event = "mcp_call_dispatched" if success else "mcp_call_failed"
    rec = append_transition(
        event=event,
        actor=actor,
        role_id=role_id,
        surface="mcp_bridge",
        subject=f"requested:{requested_event_id}",
        payload={
            "requested_event_id": requested_event_id,
            "response": response or {},
            "rejection": rejection,
        },
        causality_id=requested_event_id,
        log_path=log_path,
    )
    appended.append(rec)
    return rec
