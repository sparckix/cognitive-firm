"""Tests for the GP-231 Phase 2 capability-token primitives.

Exercises:
  - capability grant + revocation
  - dispatch authorization with and without active capability
  - directory-scoped (task-bound) capability lifetime
  - explicit expiry via expires_at_iso
  - load_capabilities_from_role_yaml schema parsing
  - end-to-end relay refusal when role lacks capability
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.transition_log import append_transition  # noqa: E402
from cognitive_firm.role_extensions.mcp_bridge import (  # noqa: E402
    MCPCapability,
)
from cognitive_firm.role_extensions.mcp_bridge.capabilities import (  # noqa: E402
    clear_all_capabilities,
    grant_capability,
    is_dispatch_authorized,
    list_role_capabilities,
    load_capabilities_from_role_yaml,
    revoke_capability,
    revoke_task_capabilities,
)
from cognitive_firm.role_extensions.mcp_bridge.projections import (  # noqa: E402
    register_projection,
    ProjectionResult,
)
from cognitive_firm.role_extensions.mcp_bridge.outbox_relay import (  # noqa: E402
    dispatch_pending,
    _DEDUP_CACHE,
)


@pytest.fixture(autouse=True)
def _clean_state():
    clear_all_capabilities()
    _DEDUP_CACHE.clear()
    yield
    clear_all_capabilities()
    _DEDUP_CACHE.clear()


# ── unit: capability grant + check ─────────────────────────────────────


def test_grant_and_check_active_capability():
    cap = MCPCapability(
        role_id="research_director",
        server_name="linear",
        tool_names=frozenset(["list_issues", "get_issue"]),
        scope="read_only",
        rationale="cross-reference seam IDs",
    )
    grant_capability(cap)
    ok, reason = is_dispatch_authorized("research_director", "linear", "list_issues")
    assert ok is True
    assert reason is None


def test_unauthorized_role_rejected():
    ok, reason = is_dispatch_authorized("debate_runner", "linear", "list_issues")
    assert ok is False
    assert "no MCP capabilities" in reason


def test_authorized_role_wrong_tool_rejected():
    grant_capability(
        MCPCapability(
            role_id="research_director",
            server_name="linear",
            tool_names=frozenset(["list_issues"]),
            rationale="read seams only",
        )
    )
    ok, reason = is_dispatch_authorized("research_director", "linear", "create_issue")
    assert ok is False
    assert "no active capability" in reason
    assert "linear/create_issue" in reason


def test_wildcard_tool_capability_authorizes_all_tools():
    grant_capability(
        MCPCapability(
            role_id="principal",
            server_name="linear",
            tool_names=frozenset({"*"}),
            scope="full",
            rationale="principal-level access for emergency operations",
        )
    )
    ok, _ = is_dispatch_authorized("principal", "linear", "anything_at_all")
    assert ok is True


def test_revoke_removes_capability():
    cap = MCPCapability(
        role_id="rd",
        server_name="linear",
        tool_names=frozenset(["list_issues"]),
        rationale="test",
    )
    grant_capability(cap)
    assert is_dispatch_authorized("rd", "linear", "list_issues")[0] is True
    assert revoke_capability(cap) is True
    assert is_dispatch_authorized("rd", "linear", "list_issues")[0] is False


def test_task_scoped_capability_revoked_on_task_close():
    """Directory-scoped capability lifetime — Phase 2 core feature.

    Capability granted at task-dispatch, revoked at task-close.
    """
    cap_a = MCPCapability(
        role_id="rd",
        server_name="linear",
        tool_names=frozenset(["list_issues"]),
        rationale="task A read",
        task_id="task_A",
    )
    cap_b = MCPCapability(
        role_id="rd",
        server_name="linear",
        tool_names=frozenset(["get_issue"]),
        rationale="task B read",
        task_id="task_B",
    )
    cap_persistent = MCPCapability(
        role_id="rd",
        server_name="linear",
        tool_names=frozenset(["list_projects"]),
        rationale="mandate-level cross-reference",
    )
    for c in (cap_a, cap_b, cap_persistent):
        grant_capability(c)

    assert len(list_role_capabilities("rd")) == 3

    # Close task A.
    n = revoke_task_capabilities("rd", "task_A")
    assert n == 1
    remaining = list_role_capabilities("rd")
    assert len(remaining) == 2
    assert all(c.task_id != "task_A" for c in remaining)
    # Task B and persistent are still there.
    assert is_dispatch_authorized("rd", "linear", "get_issue")[0] is True
    assert is_dispatch_authorized("rd", "linear", "list_projects")[0] is True


def test_explicit_expiry_iso_expires_capability():
    """A capability with expires_at_iso in the past should not authorize."""
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    grant_capability(
        MCPCapability(
            role_id="rd",
            server_name="linear",
            tool_names=frozenset(["list_issues"]),
            rationale="expired test",
            expires_at_iso=past,
        )
    )
    ok, _ = is_dispatch_authorized("rd", "linear", "list_issues")
    assert ok is False


def test_explicit_expiry_iso_future_authorizes():
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    grant_capability(
        MCPCapability(
            role_id="rd",
            server_name="linear",
            tool_names=frozenset(["list_issues"]),
            rationale="not yet expired",
            expires_at_iso=future,
        )
    )
    ok, _ = is_dispatch_authorized("rd", "linear", "list_issues")
    assert ok is True


def test_grant_requires_rationale():
    """Principal must articulate why every capability exists."""
    with pytest.raises(ValueError, match="rationale"):
        grant_capability(
            MCPCapability(
                role_id="rd",
                server_name="linear",
                tool_names=frozenset(["list_issues"]),
                rationale="",
            )
        )


def test_grant_requires_non_empty_tools():
    with pytest.raises(ValueError, match="tool_names"):
        grant_capability(
            MCPCapability(
                role_id="rd",
                server_name="linear",
                tool_names=frozenset(),
                rationale="empty tools test",
            )
        )


# ── role-yaml loader ───────────────────────────────────────────────────


def test_load_capabilities_from_role_yaml_well_formed():
    role_data = {
        "role_id": "rd",
        "authorized_mcp_capabilities": [
            {
                "server": "linear",
                "tools": ["list_issues", "get_issue"],
                "scope": "read_only",
                "rationale": "cross-reference seam IDs",
            },
            {
                "server": "github",
                "tools": ["search_code"],
                "scope": "read_only",
                "rationale": "find prior art",
            },
        ],
    }
    n = load_capabilities_from_role_yaml("rd", role_data)
    assert n == 2
    assert is_dispatch_authorized("rd", "linear", "list_issues")[0] is True
    assert is_dispatch_authorized("rd", "github", "search_code")[0] is True


def test_load_capabilities_skips_malformed():
    """Missing rationale → skip (grant_capability raises; loader catches)."""
    role_data = {
        "authorized_mcp_capabilities": [
            {"server": "linear", "tools": ["x"], "rationale": "ok"},
            {"server": "linear", "tools": ["y"], "rationale": ""},  # malformed
            {"server": "linear", "tools": [], "rationale": "no tools"},  # malformed
            "not a dict",  # malformed
        ],
    }
    n = load_capabilities_from_role_yaml("rd", role_data)
    assert n == 1


def test_load_capabilities_handles_missing_field():
    """Role with no authorized_mcp_capabilities at all returns 0."""
    n = load_capabilities_from_role_yaml("rd", {"role_id": "rd"})
    assert n == 0


# ── end-to-end: relay refuses dispatch without capability ──────────────


def test_relay_refuses_dispatch_when_role_lacks_capability(tmp_path: Path):
    """The integration test: role_id present in transition but no capability
    granted → mcp_call_failed with capability rejection reason. NO transport
    call is made."""
    log = tmp_path / "transitions.jsonl"
    # Linear projections may already be registered if the linear server
    # binding was imported earlier in the test session. Use a fresh
    # server name with a fresh projection to avoid collision.
    from cognitive_firm.role_extensions.mcp_bridge.transport import (
        ServerSpec, register_server,
    )
    try:
        register_server(ServerSpec(
            name="cap_test_srv", transport="http", url="http://example/rpc",
        ))
    except ValueError:
        pass  # already registered from a prior test

    append_transition(
        event="mcp_call_requested",
        actor="test",
        role_id="rogue_role",  # no capabilities
        surface="mcp_bridge",
        subject="cap_test",
        payload={
            "server_name": "cap_test_srv",
            "tool_name": "anytool",
            "request": {"team": "ENG"},
            "timeout_seconds": 1.0,
        },
        causality_id="cap-check-1",
        log_path=log,
    )

    transport_calls = []

    def transport(server, tool, request, key, timeout):
        transport_calls.append((server, tool))
        return {"jsonrpc": "2.0", "result": {"issues": []}}

    appended = dispatch_pending(log_path=log, transport=transport)
    assert len(appended) == 1
    assert appended[0]["event"] == "mcp_call_failed"
    rej = appended[0]["payload"].get("rejection", "")
    assert "no MCP capabilities" in rej or "no active capability" in rej
    # And critically: the transport was NEVER called.
    assert len(transport_calls) == 0, (
        "capability check failed-open — transport called despite no capability"
    )


def test_relay_authorizes_dispatch_when_role_has_capability(tmp_path: Path):
    """Sanity: the converse. Role with a granted capability dispatches."""
    log = tmp_path / "transitions.jsonl"
    # Linear projections may already be registered if the linear server
    # binding was imported earlier in the test session. Use a fresh
    # server name with a fresh projection to avoid collision.
    from cognitive_firm.role_extensions.mcp_bridge.transport import (
        ServerSpec, register_server,
    )
    try:
        register_server(ServerSpec(
            name="cap_test_srv", transport="http", url="http://example/rpc",
        ))
    except ValueError:
        pass  # already registered from a prior test

    grant_capability(
        MCPCapability(
            role_id="research_director",
            server_name="linear",
            tool_names=frozenset(["list_issues"]),
            rationale="seam cross-reference",
        )
    )

    append_transition(
        event="mcp_call_requested",
        actor="test",
        role_id="research_director",
        surface="mcp_bridge",
        subject="cap_test",
        payload={
            "server_name": "linear",
            "tool_name": "list_issues",
            "request": {"team": "ENG"},
            "timeout_seconds": 1.0,
        },
        causality_id="cap-check-2",
        log_path=log,
    )

    def transport(server, tool, request, key, timeout):
        return {"jsonrpc": "2.0", "result": {"issues": [{"id": "1", "identifier": "ENG-1", "title": "x", "state": "Todo"}]}}

    appended = dispatch_pending(log_path=log, transport=transport)
    assert len(appended) == 1
    assert appended[0]["event"] == "mcp_call_dispatched"
