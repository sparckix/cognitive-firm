"""Tests for the Linear MCP server binding.

Exercises:
  - registration of the server spec + projections on import
  - projection of well-formed list_issues / get_issue / list_projects responses
  - rejection of malformed responses
  - end-to-end relay flow with Linear projection registered (using a fake
    transport that emulates Linear's response shape)

No network calls. The transport is patched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.transition_log import append_transition  # noqa: E402
from cognitive_firm.role_extensions.mcp_bridge import (  # noqa: E402
    dispatch_pending,
    project_response,
    registered_servers,
    get_server_spec,
)
from cognitive_firm.role_extensions.mcp_bridge import outbox_relay  # noqa: E402
from cognitive_firm.role_extensions.mcp_bridge.servers import linear  # noqa: E402,F401  module side-effect: registers


def test_linear_server_registered_on_import():
    assert "linear" in registered_servers()
    spec = get_server_spec("linear")
    assert spec is not None
    assert spec.transport == "http"
    assert spec.auth_env_var == "LINEAR_API_KEY"
    assert spec.url and spec.url.startswith("https://")


def test_list_issues_projection_well_formed():
    response = {
        "jsonrpc": "2.0",
        "id": "abc",
        "result": {
            "issues": [
                {"id": "1", "identifier": "ENG-1", "title": "fix bug", "state": "Todo", "priority": 2},
                {"id": "2", "identifier": "ENG-2", "title": "ship feature", "state": "In Progress"},
            ]
        },
    }
    proj = project_response("linear", "list_issues", response)
    assert proj.transition_class == "mcp_call_dispatched"
    assert proj.normalized_payload["count"] == 2
    titles = [it["title"] for it in proj.normalized_payload["issues"]]
    assert "fix bug" in titles


def test_list_issues_projection_rejects_malformed():
    response = {"jsonrpc": "2.0", "id": "abc"}  # no result
    proj = project_response("linear", "list_issues", response)
    assert proj.transition_class == "mcp_call_failed"
    assert proj.rejection_reason and "missing 'result'" in proj.rejection_reason


def test_get_issue_projection():
    response = {
        "jsonrpc": "2.0",
        "id": "abc",
        "result": {"issue": {"id": "5", "identifier": "ENG-5", "title": "x", "state": "Done", "description": "longer text"}},
    }
    proj = project_response("linear", "get_issue", response)
    assert proj.transition_class == "mcp_call_dispatched"
    assert proj.normalized_payload["identifier"] == "ENG-5"
    assert proj.normalized_payload["description_present"] is True


def test_list_projects_projection():
    response = {
        "jsonrpc": "2.0",
        "id": "abc",
        "result": {"projects": [{"id": "p1", "name": "Q1 plan", "state": "active"}]},
    }
    proj = project_response("linear", "list_projects", response)
    assert proj.transition_class == "mcp_call_dispatched"
    assert proj.normalized_payload["count"] == 1


def test_end_to_end_linear_dispatch_with_fake_transport(tmp_path: Path):
    """The whole pipeline: write request, dispatch via fake transport,
    project response, append follow-up transition."""
    log = tmp_path / "transitions.jsonl"
    rec = append_transition(
        event="mcp_call_requested",
        actor="test",
        role_id=None,  # capability check bypassed — see test_mcp_capabilities
        surface="mcp_bridge",
        subject="linear_demo",
        payload={
            "server_name": "linear",
            "tool_name": "list_issues",
            "request": {"team_id": "ENG"},
            "timeout_seconds": 1.0,
        },
        causality_id="end-to-end-test",
        log_path=log,
    )

    def fake_transport(server, tool, request, key, timeout):
        assert server == "linear"
        assert tool == "list_issues"
        return {
            "jsonrpc": "2.0",
            "id": "x",
            "result": {
                "issues": [
                    {"id": "1", "identifier": "ENG-1", "title": "real-shape issue", "state": "Todo"}
                ]
            },
        }

    appended = dispatch_pending(log_path=log, transport=fake_transport)
    assert len(appended) == 1
    assert appended[0]["event"] == "mcp_call_dispatched"
    payload = appended[0]["payload"]
    assert payload["requested_event_id"] == rec["event_id"]
    assert payload["response"]["count"] == 1
    assert payload["response"]["issues"][0]["title"] == "real-shape issue"


@pytest.fixture(autouse=True)
def _reset_module_state():
    outbox_relay._DEDUP_CACHE.clear()
    yield
    outbox_relay._DEDUP_CACHE.clear()
