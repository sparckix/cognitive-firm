from __future__ import annotations

from scripts.public_claims_check import (
    find_forbidden_phrases,
    missing_required_caveats,
)


def test_public_claims_check_flags_marketing_overclaims():
    findings = find_forbidden_phrases(
        "This kernel is production-ready and compliance certified.",
        relpath="README.md",
    )

    assert {finding.phrase for finding in findings} == {
        "production-ready",
        "compliance certified",
    }
    assert all(finding.path == "README.md" for finding in findings)


def test_public_claims_check_allows_normal_enterprise_system_language():
    findings = find_forbidden_phrases(
        "MCP can connect to enterprise systems through adapters.",
        relpath="docs/protocols/mcp.md",
    )

    assert findings == []


def test_public_claims_check_required_caveats_are_present():
    assert missing_required_caveats() == []
