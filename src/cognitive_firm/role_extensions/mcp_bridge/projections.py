# Licensed under Business Source License 1.1 — see LICENSE-BSL
"""Deterministic projection functions: MCP response → transition class.

Per GP-231 panel verdict (M-Form auditor, 2026-05-07): when an MCP server
returns ambiguous data, *something* must adjudicate. If the App-layer LLM
adjudicates and the result flows into a kernel transition, T2 (deterministic
enforcement) has been silently broken — a learned parameter has entered the
M-Form's enforcement floor via the transition's *meaning*.

The fix is to require, per (server, tool) pair, a deterministic projection
function with the signature:

    fn(response: dict) -> ProjectionResult

Each function is principal-signed at registration time (the mandate names
the projection_id and the principal accepts that the function is canonical
for that server×tool). Ambiguous returns that the function does not classify
are REJECTED, not LLM-interpreted — they emit a damage signal of class
`mcp_response_unprojectable` and the corresponding transition is marked
failed.

This module is the local registry. Phase 2 will add a manifest-hash check so
the registered function's bytecode hash matches the value in the capability
token; today the registry is in-process only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class ProjectionResult:
    """Outcome of projecting an MCP response into a deterministic class.

    Attributes:
        transition_class: One of the canonical event names — e.g.,
            "mcp_call_dispatched", "mcp_call_failed", "mcp_call_partial".
            The relay uses this to write the follow-up transition.
        normalized_payload: A deterministic, lossy summary of the response
            shaped for inclusion in the transition payload. MUST NOT
            contain LLM judgments — only direct projections of raw fields.
        rejection_reason: If the response could not be projected, the
            reason. transition_class is "mcp_call_failed" in that case.
    """
    transition_class: str
    normalized_payload: dict[str, Any]
    rejection_reason: Optional[str] = None


# Module-level registry. Keyed by (server_name, tool_name). Phase 2 will
# extend this to (server_digest, tool_manifest_hash, tool_name) so a server
# update with a different bytecode invalidates the registration.
_REGISTRY: dict[tuple[str, str], Callable[[dict[str, Any]], ProjectionResult]] = {}


def register_projection(
    server_name: str,
    tool_name: str,
    fn: Callable[[dict[str, Any]], ProjectionResult],
) -> None:
    """Register a deterministic projection function for one (server, tool)."""
    key = (server_name, tool_name)
    if key in _REGISTRY:
        existing = _REGISTRY[key]
        if existing is not fn:
            raise ValueError(
                f"projection already registered for {server_name}/{tool_name}: "
                f"{existing.__module__}.{existing.__name__}; "
                f"refusing to overwrite with "
                f"{fn.__module__}.{fn.__name__}"
            )
        return
    _REGISTRY[key] = fn


def project_response(
    server_name: str,
    tool_name: str,
    response: dict[str, Any],
) -> ProjectionResult:
    """Look up the registered projection for (server, tool) and apply it.

    If no projection is registered, return a rejection. This means the
    relay MUST not accept a server/tool combination that has no projection
    — the absence is a deliberate gate, not an oversight.
    """
    key = (server_name, tool_name)
    fn = _REGISTRY.get(key)
    if fn is None:
        return ProjectionResult(
            transition_class="mcp_call_failed",
            normalized_payload={},
            rejection_reason=(
                f"no projection registered for {server_name}/{tool_name}; "
                f"this server/tool pair is not approved for kernel-recorded "
                f"action — register a deterministic projection before "
                f"granting capability"
            ),
        )
    try:
        return fn(response)
    except Exception as exc:  # noqa: BLE001
        return ProjectionResult(
            transition_class="mcp_call_failed",
            normalized_payload={},
            rejection_reason=f"projection raised {type(exc).__name__}: {exc}",
        )


def registered_projections() -> list[tuple[str, str]]:
    """Return the list of (server, tool) pairs with a registered projection."""
    return sorted(_REGISTRY.keys())
