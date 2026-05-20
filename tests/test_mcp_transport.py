from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.role_extensions.mcp_bridge.transport import _parse_mcp_http_response  # noqa: E402


def test_parse_mcp_http_response_accepts_json_object():
    parsed = _parse_mcp_http_response('{"jsonrpc":"2.0","id":"1","result":{"ok":true}}')

    assert parsed["result"]["ok"] is True


def test_parse_mcp_http_response_accepts_event_stream_data_line():
    parsed = _parse_mcp_http_response(
        'event: message\n'
        'data: {"jsonrpc":"2.0","id":"1","result":{"ok":true}}\n\n'
    )

    assert parsed["result"]["ok"] is True
