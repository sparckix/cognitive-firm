"""GP-231 Phase 2 — capability-token primitives for MCP dispatch.

Per `internal/competitive_adoption_verdicts.md` C4 verdict: SHIP a
directory-scoped capability lifetime (skip full per-action capability
grants per H3 historical analog — seL4-style verification overhead
exceeds the marginal safety gain outside high-assurance regimes).

A capability is granted at task-dispatch and revoked at task-close;
mid-task mandate edits queue a "rescope on next task boundary" rather
than mid-task interrupt.

Schema in role yaml:

    authorized_mcp_capabilities:
      - server: linear
        tools: [list_issues, get_issue, list_projects]
        scope: read_only
        rationale: >
          Research director needs read access to Linear for cross-
          referencing seam IDs against issue tracker. No write tools.

The Phase 1.5 outbox-relay calls `is_dispatch_authorized(role_id,
server, tool)` before issuing any MCP call. Unauthorized dispatch
attempts produce `mcp_call_failed` with rejection_reason =
"no active capability for {role}/{server}/{tool}".

Phase 2 ships role-yaml-driven capabilities. Phase 3 will extend to
principal-signed capability tokens with image-digest pinning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class MCPCapability:
    """One principal-authorized capability for a (role, server) pair.

    Attributes:
      role_id: role that holds this capability.
      server_name: which MCP server the capability covers.
      tool_names: frozenset of tool names. {"*"} means all tools on the
        server (read+write); a specific subset means only those tools.
      scope: human-readable label like "read_only" / "create_only" / "full".
        The relay does not interpret this; it is for audit + UI only.
        Tool-level enforcement comes from `tool_names`.
      rationale: free-text reason this capability exists. Required (the
        principal must articulate why granting).
      task_id: if not None, the capability is scoped to one task; expires
        when that task closes. If None, the capability is mandate-lifetime.
      expires_at_iso: optional explicit expiry; None means task-bound or
        mandate-bound per task_id.
      granted_at_iso: ISO timestamp of grant. Set automatically.
    """

    role_id: str
    server_name: str
    tool_names: frozenset[str]
    scope: str = "read_only"
    rationale: str = ""
    task_id: Optional[str] = None
    expires_at_iso: Optional[str] = None
    granted_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# Module-level registry. Keyed by role_id. Phase 3 will move this to a
# principal-signed file under org/.
_REGISTRY: dict[str, list[MCPCapability]] = {}


def grant_capability(cap: MCPCapability) -> None:
    """Add a capability to the registry. Idempotent on identical re-add."""
    if not cap.rationale.strip():
        raise ValueError("MCPCapability.rationale is required and may not be empty")
    if not cap.tool_names:
        raise ValueError("MCPCapability.tool_names may not be empty")
    existing = _REGISTRY.setdefault(cap.role_id, [])
    if cap not in existing:
        existing.append(cap)


def revoke_capability(cap: MCPCapability) -> bool:
    """Remove a capability from the registry. Returns True if removed."""
    existing = _REGISTRY.get(cap.role_id, [])
    if cap in existing:
        existing.remove(cap)
        return True
    return False


def revoke_task_capabilities(role_id: str, task_id: str) -> int:
    """Revoke all capabilities scoped to one task. Returns count revoked.

    Called when a task closes — this is the directory-scoped capability
    lifetime in action.
    """
    existing = _REGISTRY.get(role_id, [])
    n_before = len(existing)
    _REGISTRY[role_id] = [c for c in existing if c.task_id != task_id]
    return n_before - len(_REGISTRY[role_id])


def is_dispatch_authorized(
    role_id: str,
    server_name: str,
    tool_name: str,
    *,
    now: Optional[datetime] = None,
) -> tuple[bool, Optional[str]]:
    """Check whether the role has an active capability for (server, tool).

    Returns (authorized, reason_if_not). The relay calls this before
    issuing any MCP call. Unauthorized → mcp_call_failed with the reason.
    """
    now = now or datetime.now(timezone.utc)
    caps = _REGISTRY.get(role_id, [])
    if not caps:
        return False, f"role {role_id} has no MCP capabilities granted"
    for c in caps:
        if c.server_name != server_name:
            continue
        if c.expires_at_iso:
            try:
                exp = datetime.fromisoformat(c.expires_at_iso)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if now >= exp:
                    continue  # expired
            except Exception:  # noqa: BLE001
                continue  # malformed expiry → treat as expired
        if "*" in c.tool_names or tool_name in c.tool_names:
            return True, None
    return (
        False,
        f"role {role_id} has no active capability for {server_name}/{tool_name} "
        f"(check authorized_mcp_capabilities in role yaml)",
    )


def list_role_capabilities(role_id: str) -> list[MCPCapability]:
    """Return all capabilities currently held by a role."""
    return list(_REGISTRY.get(role_id, []))


def clear_all_capabilities() -> None:
    """Test helper. Clears the entire registry."""
    _REGISTRY.clear()


def load_capabilities_from_role_yaml(role_id: str, role_data: dict) -> int:
    """Read `authorized_mcp_capabilities` from a parsed role yaml and
    register each. Returns the number of capabilities registered.

    Expected shape (in role yaml):

        authorized_mcp_capabilities:
          - server: linear
            tools: [list_issues, get_issue]
            scope: read_only
            rationale: "research director cross-references seam IDs"

    Missing or empty list is fine (zero MCP capabilities).
    """
    raw = role_data.get("authorized_mcp_capabilities") or []
    if not isinstance(raw, list):
        return 0
    n = 0
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        server = entry.get("server")
        tools = entry.get("tools") or []
        scope = entry.get("scope", "read_only")
        rationale = entry.get("rationale", "")
        if not server or not isinstance(tools, list) or not tools:
            continue
        cap = MCPCapability(
            role_id=role_id,
            server_name=str(server),
            tool_names=frozenset(str(t) for t in tools),
            scope=str(scope),
            rationale=str(rationale),
            task_id=None,           # mandate-lifetime by default
            expires_at_iso=None,
        )
        try:
            grant_capability(cap)
            n += 1
        except ValueError:
            continue  # skip malformed (e.g. empty rationale)
    return n
