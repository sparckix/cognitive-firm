"""EU AI Act deploy-gate primitive tests.

Properties under test:
  - t2_deployment: false → gate trivially passes (T1 is not subject)
  - t2_deployment: true + no mapping file → blocked with damage signal
  - t2_deployment: true + mapping with no signature → blocked
  - t2_deployment: true + signature for stale mandate hash → blocked
  - t2_deployment: true + signature missing a required path → blocked
  - t2_deployment: true + signature missing a required MCP server → blocked
  - t2_deployment: true + complete fresh signature → allowed
  - mandate-hash determinism (same inputs → same hash; different inputs
    → different hash)
  - mandate-hash STABILITY across edits to non-authorization fields
    (e.g., description text changes do NOT invalidate the mapping)
  - freshness signal fires after >= freshness_review_days but does NOT
    block dispatch
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.eu_ai_act_deploy_gate import (  # noqa: E402
    GateDecision,
    check_eu_ai_act_gate,
    compute_mandate_hash,
    parse_mapping_signature,
)


# ── helper: build mapping file ─────────────────────────────────────────


def _write_mapping(tmp_path: Path, signature: dict, body: str = "Mapping body.") -> Path:
    sig_block = "<!-- EU_AI_ACT_MAPPING_SIGNATURE\n"
    for k, v in signature.items():
        if isinstance(v, list):
            sig_block += f"{k}: [{', '.join(v)}]\n"
        else:
            sig_block += f"{k}: {v}\n"
    sig_block += "-->\n"
    path = tmp_path / "docs" / "compliance" / "eu_ai_act_mapping.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sig_block + "\n" + body, encoding="utf-8")
    return path


def _typical_role_yaml() -> dict:
    return {
        "role_id": "research_director",
        "t2_deployment": True,
        "authorized_paths": ["projects/", "research_areas/", "docs/"],
        "forbidden_paths": ["org/mandates/"],
        "authorized_mcp_capabilities": [
            {"server": "linear", "tools": ["list_issues"], "scope": "read_only",
             "rationale": "cross-reference seam IDs"},
        ],
        "authorized_models": {"cheap": True, "mid": True, "pro": False},
        "budget_caps": {"per_action_usd_max": 0.5},
        "delegates_to": ["debate_runner"],
        "escalates_to": ["principal"],
    }


# ── trivial pass: T1 (no t2_deployment flag) ──────────────────────────


def test_t1_role_passes_trivially(tmp_path: Path):
    role = _typical_role_yaml()
    role["t2_deployment"] = False
    decision = check_eu_ai_act_gate(role, "mandate text", repo_root=tmp_path)
    assert decision.allowed is True
    assert "does not apply" in decision.reason


def test_t1_role_passes_when_flag_missing(tmp_path: Path):
    """Default-to-T1 — missing t2_deployment field is treated as false."""
    role = _typical_role_yaml()
    del role["t2_deployment"]
    decision = check_eu_ai_act_gate(role, "mandate text", repo_root=tmp_path)
    assert decision.allowed is True


# ── failure modes ─────────────────────────────────────────────────────


def test_no_mapping_file_blocks_with_damage_signal(tmp_path: Path):
    role = _typical_role_yaml()
    decision = check_eu_ai_act_gate(role, "mandate text", repo_root=tmp_path)
    assert decision.allowed is False
    assert decision.damage_signal == "eu_ai_act_mapping_missing"
    assert "does not exist" in decision.reason


def test_mapping_with_no_signature_blocks(tmp_path: Path):
    role = _typical_role_yaml()
    path = tmp_path / "docs" / "compliance" / "eu_ai_act_mapping.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Mapping body without signature front-matter.", encoding="utf-8")
    decision = check_eu_ai_act_gate(role, "mandate text", repo_root=tmp_path)
    assert decision.allowed is False
    assert decision.damage_signal == "eu_ai_act_mapping_missing"
    assert "no parseable principal signature" in decision.reason


def test_signature_for_stale_mandate_hash_blocks(tmp_path: Path):
    role = _typical_role_yaml()
    _write_mapping(tmp_path, {
        "mandate_hash": "stale_hash_value",
        "signed_at": "2026-05-07T14:30:00Z",
        "covers_paths": role["authorized_paths"],
        "covers_mcp_servers": ["linear"],
    })
    decision = check_eu_ai_act_gate(role, "mandate text", repo_root=tmp_path)
    assert decision.allowed is False
    assert decision.damage_signal == "eu_ai_act_mapping_stale"
    assert "Mandate has changed" in decision.reason


def test_missing_authorized_path_in_coverage_blocks(tmp_path: Path):
    role = _typical_role_yaml()
    expected_hash = compute_mandate_hash(role, "mandate text")
    # covers_paths is missing 'docs/'
    _write_mapping(tmp_path, {
        "mandate_hash": expected_hash,
        "signed_at": "2026-05-07T14:30:00Z",
        "covers_paths": ["projects/", "research_areas/"],
        "covers_mcp_servers": ["linear"],
    })
    decision = check_eu_ai_act_gate(role, "mandate text", repo_root=tmp_path)
    assert decision.allowed is False
    assert decision.damage_signal == "eu_ai_act_mapping_stale"
    assert "docs/" in decision.reason
    assert "not covered" in decision.reason


def test_missing_mcp_server_in_coverage_blocks(tmp_path: Path):
    role = _typical_role_yaml()
    expected_hash = compute_mandate_hash(role, "mandate text")
    # covers_mcp_servers is empty
    _write_mapping(tmp_path, {
        "mandate_hash": expected_hash,
        "signed_at": "2026-05-07T14:30:00Z",
        "covers_paths": role["authorized_paths"],
        "covers_mcp_servers": [],
    })
    decision = check_eu_ai_act_gate(role, "mandate text", repo_root=tmp_path)
    assert decision.allowed is False
    assert "linear" in decision.reason


# ── happy path ─────────────────────────────────────────────────────────


def test_complete_fresh_signature_passes(tmp_path: Path):
    role = _typical_role_yaml()
    expected_hash = compute_mandate_hash(role, "mandate text")
    fresh_signed = datetime.now(timezone.utc).isoformat()
    _write_mapping(tmp_path, {
        "mandate_hash": expected_hash,
        "signed_at": fresh_signed,
        "covers_paths": role["authorized_paths"],
        "covers_mcp_servers": ["linear"],
    })
    decision = check_eu_ai_act_gate(role, "mandate text", repo_root=tmp_path)
    assert decision.allowed is True
    assert decision.damage_signal is None


# ── mandate-hash determinism + stability ──────────────────────────────


def test_mandate_hash_is_deterministic():
    role = _typical_role_yaml()
    h1 = compute_mandate_hash(role, "mandate text")
    h2 = compute_mandate_hash(role, "mandate text")
    assert h1 == h2


def test_mandate_hash_changes_when_authorization_changes():
    role1 = _typical_role_yaml()
    role2 = _typical_role_yaml()
    role2["authorized_paths"] = role1["authorized_paths"] + ["new/path/"]
    h1 = compute_mandate_hash(role1, "mandate text")
    h2 = compute_mandate_hash(role2, "mandate text")
    assert h1 != h2


def test_mandate_hash_stable_against_description_edits():
    """Edits to non-authorization fields (description, etc.) do NOT
    invalidate the compliance mapping. This is the load-bearing
    UX property — adopters edit description text often."""
    role1 = _typical_role_yaml()
    role2 = _typical_role_yaml()
    role1["description"] = "first description"
    role2["description"] = "second description, totally different prose"
    h1 = compute_mandate_hash(role1, "mandate text")
    h2 = compute_mandate_hash(role2, "mandate text")
    assert h1 == h2


def test_mandate_hash_changes_when_prose_mandate_changes():
    role = _typical_role_yaml()
    h1 = compute_mandate_hash(role, "original prose")
    h2 = compute_mandate_hash(role, "EDITED prose with new RUN-VS-ANALYZE rule")
    assert h1 != h2


# ── freshness review (informational, does NOT block) ──────────────────


def test_freshness_signal_fires_for_stale_mapping(tmp_path: Path):
    role = _typical_role_yaml()
    expected_hash = compute_mandate_hash(role, "mandate text")
    old_signed = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    _write_mapping(tmp_path, {
        "mandate_hash": expected_hash,
        "signed_at": old_signed,
        "covers_paths": role["authorized_paths"],
        "covers_mcp_servers": ["linear"],
    })
    decision = check_eu_ai_act_gate(
        role, "mandate text", repo_root=tmp_path,
        freshness_review_days=90.0,
    )
    # Allowed — freshness is informational only.
    assert decision.allowed is True
    assert decision.damage_signal == "eu_ai_act_mapping_freshness_review_due"
    assert "freshness review due" in decision.reason


def test_freshness_signal_does_not_fire_for_recent_mapping(tmp_path: Path):
    role = _typical_role_yaml()
    expected_hash = compute_mandate_hash(role, "mandate text")
    recent = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    _write_mapping(tmp_path, {
        "mandate_hash": expected_hash,
        "signed_at": recent,
        "covers_paths": role["authorized_paths"],
        "covers_mcp_servers": ["linear"],
    })
    decision = check_eu_ai_act_gate(
        role, "mandate text", repo_root=tmp_path,
        freshness_review_days=90.0,
    )
    assert decision.allowed is True
    assert decision.damage_signal is None


# ── parse_mapping_signature direct ────────────────────────────────────


def test_parse_signature_handles_well_formed():
    text = """<!-- EU_AI_ACT_MAPPING_SIGNATURE
mandate_hash: abc123
signed_at: 2026-05-07T14:30:00Z
covers_paths: [projects/, research_areas/]
covers_mcp_servers: [linear, github]
-->

Body content."""
    sig = parse_mapping_signature(text)
    assert sig is not None
    assert sig["mandate_hash"] == "abc123"
    assert sig["covers_paths"] == ["projects/", "research_areas/"]
    assert sig["covers_mcp_servers"] == ["linear", "github"]


def test_parse_signature_returns_none_when_missing():
    text = "no front-matter here, just body content."
    assert parse_mapping_signature(text) is None


def test_parse_signature_returns_none_when_required_field_missing():
    text = """<!-- EU_AI_ACT_MAPPING_SIGNATURE
covers_paths: [x]
-->"""
    # Missing mandate_hash + signed_at.
    assert parse_mapping_signature(text) is None
