# Licensed under Business Source License 1.1 — see LICENSE-BSL
"""Concrete MCP server bindings.

Each module in this package registers ONE MCP server's spec + projections
when imported. To enable a server, the kernel imports it (typically via
mandate-driven discovery in cognitive_firm.role_extensions.mcp_bridge.bootstrap).

Phase 1.5 ships only `linear` (read-only). Phase 2 will add write-capable
servers behind capability tokens.
"""
