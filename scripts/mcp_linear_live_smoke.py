#!/usr/bin/env python3
"""Optional live smoke for the Linear MCP binding.

This is intentionally not part of the public smoke path. It requires network
access and a tenant-owned LINEAR_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.role_extensions.mcp_bridge import call_mcp_tool, project_response  # noqa: E402
from cognitive_firm.role_extensions.mcp_bridge.servers import linear  # noqa: E402,F401


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an optional live Linear MCP smoke.")
    parser.add_argument("--tool", default="list_projects", choices=["list_projects", "list_issues", "get_issue"])
    parser.add_argument("--arguments-json", default="{}", help="JSON object passed as MCP tool arguments.")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)

    if not os.environ.get("LINEAR_API_KEY"):
        print("LINEAR_API_KEY is required for the live Linear MCP smoke.", file=sys.stderr)
        return 2

    try:
        arguments = json.loads(args.arguments_json)
    except json.JSONDecodeError as exc:
        print(f"--arguments-json is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(arguments, dict):
        print("--arguments-json must decode to a JSON object.", file=sys.stderr)
        return 2

    response = call_mcp_tool(
        "linear",
        args.tool,
        arguments,
        idempotency_key=f"linear-live-smoke-{uuid.uuid4()}",
        timeout_seconds=args.timeout_seconds,
    )
    projection = project_response("linear", args.tool, response)
    payload = {
        "tool": args.tool,
        "transition_class": projection.transition_class,
        "normalized_payload": projection.normalized_payload,
        "rejection_reason": projection.rejection_reason,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if projection.transition_class == "mcp_call_dispatched" else 1


if __name__ == "__main__":
    raise SystemExit(main())
