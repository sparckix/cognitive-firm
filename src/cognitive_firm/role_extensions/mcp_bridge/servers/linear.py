"""Linear MCP server binding (Phase 1.5 — read-only).

Why Linear first: Linear ships an official MCP server, the read surface
maps cleanly to the kernel's existing GP-031 / debate-runner notion of
seam tracking, and the supply-chain surface is small (one vendor, one
endpoint, OAuth bearer auth).

Read-only by design in Phase 1.5: only `list_issues`, `get_issue`,
`list_projects` are projected. Write tools (create/update/transition)
are deferred to Phase 2 because they require capability tokens at the
mandate layer (the seam is explicit on this — see GP-231).

Auth: set environment variable LINEAR_API_KEY before the daemon starts.
The transport reads this via ServerSpec.auth_env_var; the kernel never
holds the token in `org/`.

Network: HTTP + JSON-RPC (Linear's MCP server is HTTPS).

To enable in a tenant, add to mandate.authorized_mcp_servers:
    - linear
And import this module once at daemon boot:
    from cognitive_firm.role_extensions.mcp_bridge.servers import linear  # noqa
"""

from __future__ import annotations

from typing import Any

from cognitive_firm.role_extensions.mcp_bridge.projections import (
    ProjectionResult,
    register_projection,
)
from cognitive_firm.role_extensions.mcp_bridge.transport import (
    ServerSpec,
    register_server,
)


# ── server registration ────────────────────────────────────────────────


LINEAR_SPEC = ServerSpec(
    name="linear",
    transport="http",
    url="https://mcp.linear.app/rpc",
    auth_env_var="LINEAR_API_KEY",
    timeout_seconds_default=30.0,
)


# ── projections (deterministic, read-only) ─────────────────────────────


def _project_list_issues(response: dict[str, Any]) -> ProjectionResult:
    """list_issues → mcp_call_dispatched with normalized issue summary.

    Accepts the JSON-RPC response shape:
        {"jsonrpc": "2.0", "id": "...", "result": {"issues": [{...}, ...]}}
    Anything else is rejected as unprojectable.
    """
    if not isinstance(response, dict) or "result" not in response:
        return ProjectionResult(
            transition_class="mcp_call_failed",
            normalized_payload={},
            rejection_reason="missing 'result' in JSON-RPC response",
        )
    result = response.get("result") or {}
    issues = result.get("issues")
    if not isinstance(issues, list):
        return ProjectionResult(
            transition_class="mcp_call_failed",
            normalized_payload={},
            rejection_reason="'issues' is not a list",
        )
    summary = [
        {
            "id": str(it.get("id", "")),
            "identifier": str(it.get("identifier", "")),
            "title": str(it.get("title", ""))[:200],
            "state": str(it.get("state", "")),
            "priority": int(it.get("priority", 0)) if isinstance(it.get("priority"), (int, float)) else None,
        }
        for it in issues if isinstance(it, dict)
    ][:100]
    return ProjectionResult(
        transition_class="mcp_call_dispatched",
        normalized_payload={"count": len(summary), "issues": summary},
    )


def _project_get_issue(response: dict[str, Any]) -> ProjectionResult:
    if not isinstance(response, dict) or "result" not in response:
        return ProjectionResult(
            transition_class="mcp_call_failed",
            normalized_payload={},
            rejection_reason="missing 'result' in JSON-RPC response",
        )
    result = response.get("result") or {}
    issue = result.get("issue") if isinstance(result, dict) else None
    if not isinstance(issue, dict):
        return ProjectionResult(
            transition_class="mcp_call_failed",
            normalized_payload={},
            rejection_reason="'issue' missing or not a dict",
        )
    return ProjectionResult(
        transition_class="mcp_call_dispatched",
        normalized_payload={
            "id": str(issue.get("id", "")),
            "identifier": str(issue.get("identifier", "")),
            "title": str(issue.get("title", ""))[:200],
            "state": str(issue.get("state", "")),
            "description_present": bool(issue.get("description")),
        },
    )


def _project_list_projects(response: dict[str, Any]) -> ProjectionResult:
    if not isinstance(response, dict) or "result" not in response:
        return ProjectionResult(
            transition_class="mcp_call_failed",
            normalized_payload={},
            rejection_reason="missing 'result' in JSON-RPC response",
        )
    result = response.get("result") or {}
    projects = result.get("projects")
    if not isinstance(projects, list):
        return ProjectionResult(
            transition_class="mcp_call_failed",
            normalized_payload={},
            rejection_reason="'projects' is not a list",
        )
    summary = [
        {
            "id": str(p.get("id", "")),
            "name": str(p.get("name", ""))[:200],
            "state": str(p.get("state", "")),
        }
        for p in projects if isinstance(p, dict)
    ][:50]
    return ProjectionResult(
        transition_class="mcp_call_dispatched",
        normalized_payload={"count": len(summary), "projects": summary},
    )


# ── module-load registration ──────────────────────────────────────────


def _register_all() -> None:
    register_server(LINEAR_SPEC)
    register_projection("linear", "list_issues", _project_list_issues)
    register_projection("linear", "get_issue", _project_get_issue)
    register_projection("linear", "list_projects", _project_list_projects)


# Auto-register on import. Idempotent (register_server / register_projection
# both no-op on identical re-registration).
_register_all()
