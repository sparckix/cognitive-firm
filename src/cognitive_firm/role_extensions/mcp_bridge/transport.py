"""General-purpose MCP transport for the outbox relay.

MCP (Model Context Protocol) speaks JSON-RPC 2.0 over either:
  - stdio (subprocess; the server is a local executable the kernel spawns)
  - Streamable HTTP (remote HTTP endpoint with session/version headers)
  - legacy HTTP JSON-RPC endpoints where a server still exposes them

This module provides a `call_mcp_tool` function that dispatches to the
appropriate transport given a server registration. Servers are described
by a `ServerSpec` and a registry maps server_name → ServerSpec.

Phase 1 supports stdio, legacy HTTP, and Streamable HTTP. Phase 3 will pin
server images by digest; for now the registry holds an explicit command/url
plus an env-var name for the API token.

Crucially, the transport is **dumb**. It knows how to JSON-RPC; it does
NOT know what any tool means. All semantic interpretation is the
projection's job (and the projection is deterministic — see projections.py).
"""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


log = logging.getLogger(__name__)


# ── server registration ────────────────────────────────────────────────


@dataclass(frozen=True)
class ServerSpec:
    """Description of one MCP server the kernel may dispatch to.

    Phase 1 fields:
      name: stable identifier used in mandate.authorized_mcp_servers
      transport: "stdio" | "http" | "streamable_http"
      command: for stdio, the executable + args (e.g., ["mcp-linear"])
      url: for http, the JSON-RPC endpoint (e.g., "https://mcp.linear.app/rpc")
      auth_env_var: name of the env var holding the bearer token / API key
      timeout_seconds_default: per-call timeout, overridable by request

    Phase 3 will add `image_digest`, `tool_manifest_hash`, `declared_egress`.
    """

    name: str
    transport: str
    command: tuple[str, ...] = field(default_factory=tuple)
    url: Optional[str] = None
    auth_env_var: Optional[str] = None
    timeout_seconds_default: float = 30.0


_SERVER_REGISTRY: dict[str, ServerSpec] = {}


def register_server(spec: ServerSpec) -> None:
    """Register a server. Idempotent for identical re-registration."""
    existing = _SERVER_REGISTRY.get(spec.name)
    if existing is not None and existing != spec:
        raise ValueError(
            f"server {spec.name} already registered with a different spec; "
            f"refusing to overwrite"
        )
    _SERVER_REGISTRY[spec.name] = spec


def registered_servers() -> list[str]:
    return sorted(_SERVER_REGISTRY.keys())


def get_server_spec(name: str) -> Optional[ServerSpec]:
    return _SERVER_REGISTRY.get(name)


# ── general-purpose dispatch ───────────────────────────────────────────


def call_mcp_tool(
    server_name: str,
    tool_name: str,
    request: dict[str, Any],
    idempotency_key: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Dispatch a JSON-RPC tools/call to the named server.

    Returns the parsed JSON-RPC response object. Raises if the server is
    unregistered, the transport fails, or the response is not valid JSON-RPC.
    """
    spec = _SERVER_REGISTRY.get(server_name)
    if spec is None:
        raise LookupError(
            f"server '{server_name}' not registered; "
            f"call register_server(ServerSpec(...)) before dispatch"
        )

    rpc_id = str(uuid.uuid4())
    payload = {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": request,
            "_meta": {"idempotency_key": idempotency_key},
        },
    }

    if spec.transport == "stdio":
        return _stdio_call(spec, payload, timeout_seconds)
    elif spec.transport == "streamable_http":
        return _streamable_http_call(spec, payload, timeout_seconds)
    elif spec.transport == "http":
        return _http_call(spec, payload, timeout_seconds)
    else:
        raise ValueError(f"unsupported transport: {spec.transport}")


# ── stdio transport ────────────────────────────────────────────────────


def _stdio_call(spec: ServerSpec, payload: dict, timeout: float) -> dict[str, Any]:
    if not spec.command:
        raise ValueError(f"stdio server {spec.name} has empty command")
    proc = subprocess.run(
        list(spec.command),
        input=json.dumps(payload).encode("utf-8") + b"\n",
        capture_output=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"stdio server {spec.name} exited {proc.returncode}: "
            f"{proc.stderr.decode('utf-8', errors='replace')[:500]}"
        )
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    # Some servers emit multiple JSON objects (notifications + response);
    # take the last well-formed one.
    last_obj: Optional[dict] = None
    for line in out.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            last_obj = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
    if last_obj is None:
        raise RuntimeError(f"stdio server {spec.name} produced no JSON response")
    return last_obj


# ── http transport ─────────────────────────────────────────────────────


def _http_call(spec: ServerSpec, payload: dict, timeout: float) -> dict[str, Any]:
    if not spec.url:
        raise ValueError(f"http server {spec.name} has empty url")
    headers = {"Content-Type": "application/json"}
    if spec.auth_env_var:
        import os
        token = os.environ.get(spec.auth_env_var)
        if not token:
            raise RuntimeError(
                f"http server {spec.name} requires env var "
                f"{spec.auth_env_var} but it is unset"
            )
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(spec.url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:500] if exc.fp else ""
        raise RuntimeError(
            f"http server {spec.name} returned {exc.code}: {body_text}"
        ) from exc
    return json.loads(data)


def _streamable_http_call(spec: ServerSpec, payload: dict, timeout: float) -> dict[str, Any]:
    """Call a Streamable HTTP MCP endpoint.

    This is intentionally minimal: initialize, send the initialized
    notification when a session is provided, then issue the single tools/call.
    It supports JSON and simple event-stream responses.
    """
    if not spec.url:
        raise ValueError(f"streamable_http server {spec.name} has empty url")
    session_id: str | None = None
    initialize_payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "cognitive-firm", "version": "0.1.0"},
        },
    }
    initialize_response, initialize_headers = _http_jsonrpc_post(
        spec,
        initialize_payload,
        timeout,
        session_id=None,
    )
    session_id = _header_value(initialize_headers, "mcp-session-id")
    if "error" in initialize_response:
        raise RuntimeError(f"streamable_http server {spec.name} initialize failed: {initialize_response['error']}")

    if session_id:
        initialized_payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        _http_jsonrpc_post(spec, initialized_payload, timeout, session_id=session_id)

    response, _ = _http_jsonrpc_post(spec, payload, timeout, session_id=session_id)
    return response


def _http_jsonrpc_post(
    spec: ServerSpec,
    payload: dict[str, Any],
    timeout: float,
    *,
    session_id: str | None,
) -> tuple[dict[str, Any], Mapping[str, str]]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-06-18",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    if spec.auth_env_var:
        import os
        token = os.environ.get(spec.auth_env_var)
        if not token:
            raise RuntimeError(
                f"http server {spec.name} requires env var "
                f"{spec.auth_env_var} but it is unset"
            )
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(spec.url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8", errors="replace")
            response_headers = dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:500] if exc.fp else ""
        raise RuntimeError(
            f"http server {spec.name} returned {exc.code}: {body_text}"
        ) from exc
    return _parse_mcp_http_response(data), response_headers


def _parse_mcp_http_response(data: str) -> dict[str, Any]:
    stripped = data.strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    for line in stripped.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload or payload == "[DONE]":
            continue
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError("MCP HTTP response did not contain a JSON object")


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None
