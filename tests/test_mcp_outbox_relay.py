"""Tests for the GP-231 MCP outbox-relay primitive.

Three load-bearing properties under test (each one falsifiable):

  1. WRITE-BEFORE-DISPATCH: the kernel writes the `mcp_call_requested`
     transition BEFORE the relay attempts dispatch. Crash between write
     and dispatch is recoverable on next tick.

  2. IDEMPOTENT RETRY: a second dispatch_pending() pass after a transient
     failure re-attempts with the same idempotency key. A successful
     follow-up causes subsequent ticks to skip the request (no double-send).

  3. NO LLM AT PROJECTION: the response is mapped to a transition class by
     a deterministic registered projection. Unregistered server/tool pairs
     are REJECTED with `mcp_call_failed`, not LLM-interpreted. T2 holds.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

# Allow running from cognitive-firm root via `python -m pytest tests/`.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.transition_log import append_transition  # noqa: E402
from cognitive_firm.role_extensions.mcp_bridge import (  # noqa: E402
    dispatch_pending,
    pending_count,
    register_projection,
    project_response,
    ProjectionResult,
)
from cognitive_firm.role_extensions.mcp_bridge import outbox_relay  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────


def _read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def _request_call(
    log_path: Path,
    request: dict,
    server="testsrv",
    tool="testtool",
    causality_id: str = None,
) -> tuple[str, str]:
    """Append a request transition. Returns (event_id, causality_id).

    causality_id defaults to a fresh UUID. Retries of the SAME logical
    action must reuse the causality_id so the idempotency key matches.
    Two requests with different causality_ids represent two intentionally
    distinct actions and produce different idempotency keys.
    """
    cid = causality_id or f"test-{uuid.uuid4().hex[:8]}"
    rec = append_transition(
        event="mcp_call_requested",
        actor="test",
        role_id=None,  # capability check bypassed — these tests are about
                       # the relay mechanics, not the capability layer.
                       # See test_mcp_capabilities.py for capability tests.
        surface="mcp_bridge",
        subject="unit_test",
        payload={
            "server_name": server,
            "tool_name": tool,
            "request": request,
            "timeout_seconds": 1.0,
        },
        causality_id=cid,
        log_path=log_path,
    )
    return rec["event_id"], cid


def _ok_projection(_response: dict) -> ProjectionResult:
    return ProjectionResult(
        transition_class="mcp_call_dispatched",
        normalized_payload={"ok": True},
    )


# ── tests ──────────────────────────────────────────────────────────────


def test_write_before_dispatch(tmp_path: Path):
    """Property 1: kernel writes the request transition BEFORE relay
    attempts dispatch. If the dispatch crashes, the request row is still
    present and recoverable."""
    log = tmp_path / "transitions.jsonl"
    register_projection("testsrv", "testtool", _ok_projection)

    event_id, _ = _request_call(log, {"a": 1})
    rows_before = _read(log)
    assert len(rows_before) == 1
    assert rows_before[0]["event"] == "mcp_call_requested"
    assert rows_before[0]["event_id"] == event_id

    # Now verify pending_count sees it.
    assert pending_count(log) == 1


def test_crash_between_write_and_dispatch_is_recoverable(tmp_path: Path):
    """Property 1 (continued): a process crash AFTER the request row but
    BEFORE the follow-up is recoverable on next tick."""
    log = tmp_path / "transitions.jsonl"
    register_projection("testsrv", "testtool", _ok_projection)
    _request_call(log, {"a": 1})  # noqa: F841

    # Simulate crash: zero dispatches happened, request still pending.
    assert pending_count(log) == 1

    # Next tick recovers.
    def fake_transport(server, tool, request, key, timeout):
        return {"status": "ok"}

    appended = dispatch_pending(log_path=log, transport=fake_transport)
    assert len(appended) == 1
    assert appended[0]["event"] == "mcp_call_dispatched"
    assert pending_count(log) == 0


def test_idempotent_retry_after_transient_failure(tmp_path: Path):
    """Property 2: a transient failure leaves the request pending; the next
    tick retries with the same idempotency key. Once dispatched, subsequent
    ticks do not double-send."""
    log = tmp_path / "transitions.jsonl"
    register_projection("testsrv", "testtool", _ok_projection)
    _, cid = _request_call(log, {"a": 1})

    keys_seen = []

    # First attempt: transient failure.
    def transport_fail(server, tool, request, key, timeout):
        keys_seen.append(key)
        raise ConnectionError("simulated transient")

    appended_1 = dispatch_pending(log_path=log, transport=transport_fail)
    assert len(appended_1) == 1
    assert appended_1[0]["event"] == "mcp_call_failed"

    # Pending count should now be 0 (the request has a failed follow-up,
    # so it is not re-dispatched). The relay's retry semantics are at the
    # OUTER level: the caller (e.g. a workflow daemon) decides whether to
    # write a new mcp_call_requested with the same payload — which would
    # produce the same idempotency key, hitting the de-dup cache.
    assert pending_count(log) == 0

    # Retry of the SAME logical action: same causality_id, same payload →
    # same idempotency key → de-dup hits.
    _request_call(log, {"a": 1}, causality_id=cid)

    def transport_ok(server, tool, request, key, timeout):
        keys_seen.append(key)
        return {"status": "ok"}

    appended_2 = dispatch_pending(log_path=log, transport=transport_ok)
    assert len(appended_2) == 1
    # Same idempotency key as the first failed attempt.
    assert keys_seen[0] == keys_seen[1], (
        "idempotency key must be deterministic across retries"
    )


def test_no_llm_at_projection_unregistered_server_rejects(tmp_path: Path):
    """Property 3: if no projection is registered for (server, tool), the
    response is rejected with mcp_call_failed and a clear reason. The
    relay does NOT fall back to LLM interpretation."""
    log = tmp_path / "transitions.jsonl"
    # Note: NO register_projection call for unknown_server.
    _request_call(log, {"x": 1}, server="unknown_server", tool="unknown_tool")

    def transport_anything(server, tool, request, key, timeout):
        return {"status": "ok", "data": "ambiguous"}

    appended = dispatch_pending(log_path=log, transport=transport_anything)
    assert len(appended) == 1
    rec = appended[0]
    assert rec["event"] == "mcp_call_failed"
    rejection = rec["payload"].get("rejection", "")
    assert "no projection registered" in rejection, (
        f"expected projection-missing rejection, got: {rejection}"
    )


def test_dedup_cache_prevents_double_dispatch_in_same_process(tmp_path: Path):
    """Property 2 (continued): if the same payload is requested twice in the
    same process, the de-dup cache catches it without contacting the
    transport."""
    log = tmp_path / "transitions.jsonl"
    register_projection("testsrv", "testtool", _ok_projection)
    _, cid = _request_call(log, {"b": 2})

    transport_calls = []

    def transport(server, tool, request, key, timeout):
        transport_calls.append(key)
        return {"ok": True}

    dispatch_pending(log_path=log, transport=transport)
    assert len(transport_calls) == 1

    # Re-request — SAME logical action (same causality_id), same payload.
    _request_call(log, {"b": 2}, causality_id=cid)
    dispatch_pending(log_path=log, transport=transport)

    # Transport was called only once; second request hit the de-dup cache.
    assert len(transport_calls) == 1, (
        "de-dup cache must prevent second dispatch with same idempotency key "
        "within the same process lifetime"
    )


def test_pending_count_consistent_after_partial_dispatch(tmp_path: Path):
    """Sanity check: pending_count tracks only mcp_call_requested rows
    without a corresponding follow-up."""
    log = tmp_path / "transitions.jsonl"
    register_projection("testsrv", "testtool", _ok_projection)

    # Three requests with distinct payloads.
    for i in range(3):
        _request_call(log, {"i": i})

    assert pending_count(log) == 3

    def transport(server, tool, request, key, timeout):
        return {"ok": True}

    # Cap dispatch to 2.
    appended = dispatch_pending(log_path=log, max_dispatches=2, transport=transport)
    assert len(appended) == 2
    assert pending_count(log) == 1


# Reset module-level state between tests so independence holds.

@pytest.fixture(autouse=True)
def _reset_module_state():
    outbox_relay._DEDUP_CACHE.clear()
    yield
    outbox_relay._DEDUP_CACHE.clear()
