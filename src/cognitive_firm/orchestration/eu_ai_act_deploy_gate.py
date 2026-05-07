# Licensed under Business Source License 1.1 — see LICENSE-BSL
"""C3 SHIP B — EU AI Act compliance deploy-gate primitive.

WHAT THIS PRIMITIVE DOES, IN PLAIN ENGLISH:

The EU AI Act (effective August 2026) requires high-risk AI systems to
maintain documentation that maps the system's architecture, data sources,
risk-management processes, and human-oversight surfaces to the Act's
articles. Vendors who deploy without this documentation expose themselves
to legal penalties and forced shutdowns.

cognitive-firm originally REJECTED shipping a vendor-published EU AI Act
mapping (per H4 historical analog: enterprise GRC teams rewrite vendor
mappings anyway). The 2026-05-07 GP-230 substrate iter1 (score 92) flipped
that verdict via a catastrophic-exposure argument: deferring mapping until
requested creates an uncapped exposure window in which compliance failure
can go undetected. If a T2 deployment lands before the mapping exists, no
other technical control compensates for the gap.

The fix is NOT to ship a vendor-published mapping. It is to ship the
**deploy-gate primitive** that forces the adopter to author a mapping
before deploying. Concretely:

  1. The mandate gains a typed field: `t2_deployment: bool` (default false).
  2. When `t2_deployment: true`, the kernel pre-deploy gate refuses
     dispatch of the role until `docs/compliance/eu_ai_act_mapping.md`
     exists, is principal-signed for the current mandate hash, and lists
     every authorized_paths root + every authorized_mcp_servers entry
     against the relevant AI Act articles.
  3. The mapping content stays adopter-authored — but its absence becomes
     a deploy-blocker rather than a sales-conversation-blocker.

PUBLIC API:

  check_eu_ai_act_gate(role_yaml: dict, mandate_text: str,
                       mapping_path: Path = ...) -> GateDecision
    Pure function. Reads the role config and the mapping file (if any),
    returns whether dispatch is permitted, and if not, why.

  compute_mandate_hash(role_yaml: dict, mandate_text: str) -> str
    Deterministic hash that the mapping file must reference. A mandate
    edit changes this hash and invalidates the existing mapping signature.

  parse_mapping_signature(mapping_text: str) -> dict | None
    Read the principal-signed front-matter from the mapping file. Returns
    {"mandate_hash": ..., "signed_at": ..., "covers_paths": [...],
     "covers_mcp_servers": [...]} or None if missing/malformed.

DAMAGE SIGNAL CLASSES THIS PRIMITIVE EMITS:

  eu_ai_act_mapping_missing            — t2_deployment: true but no mapping
                                          file exists. Block dispatch.
  eu_ai_act_mapping_stale              — mandate hash drift since last
                                          signing. Block dispatch.
  eu_ai_act_mapping_freshness_review_due — periodic cadence reminder
                                          (default 90 days). Informational;
                                          does not block dispatch.

WHAT THIS PRIMITIVE DOES NOT DO:

- It does NOT author the mapping for the adopter. The kernel is policy-
  agnostic about which AI Act articles apply to which primitives; that
  judgment belongs to the adopter's GRC team.
- It does NOT cryptographically verify the principal's signature beyond
  the mandate-hash match. Cryptographic signing is queued for Phase 3.
- It does NOT distinguish between member-state-specific implementations
  of the AI Act. The mapping is to the Regulation text, not national law.
- It does NOT block dispatch for T1 (single-principal trusted-hardware)
  deployments where t2_deployment is false. Single-principal owners are
  not AI Act subjects unless deploying a high-risk system commercially.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str
    damage_signal: Optional[str] = None  # class name to emit if any


# Default location the principal authors + signs the mapping doc.
def _default_mapping_path(repo_root: Path) -> Path:
    return repo_root / "docs" / "compliance" / "eu_ai_act_mapping.md"


# ── public API ─────────────────────────────────────────────────────────


def compute_mandate_hash(role_yaml: dict, mandate_text: str) -> str:
    """Deterministic hash of the mandate's authorization-relevant fields.

    Authorization-relevant means: anything the AI Act mapping must cover.
    Specifically: authorized_paths, forbidden_paths, authorized_mcp_capabilities,
    authorized_models, budget_caps, the prose mandate text. Other fields
    (description, comments) do NOT change the hash because edits to them
    do not invalidate a compliance mapping.
    """
    relevant_fields = [
        "role_id",
        "authorized_paths",
        "forbidden_paths",
        "authorized_mcp_capabilities",
        "authorized_models",
        "budget_caps",
        "delegates_to",
        "escalates_to",
    ]
    parts: list[str] = []
    for field in relevant_fields:
        v = role_yaml.get(field)
        parts.append(f"{field}={_canonical(v)}")
    parts.append(f"mandate_text={mandate_text.strip()}")
    text = "\n".join(parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _canonical(value) -> str:
    """Deterministic canonical string representation. Sorts keys, recurses."""
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}={_canonical(value[k])}" for k in sorted(value)) + "}"
    if isinstance(value, (list, tuple)):
        # Lists are NOT sorted — order matters for some fields like
        # authorized_paths (precedence is left-to-right).
        return "[" + ",".join(_canonical(v) for v in value) + "]"
    if value is None:
        return "null"
    return str(value)


def parse_mapping_signature(mapping_text: str) -> Optional[dict]:
    """Read the principal-signed front-matter from the mapping file.

    Expected front-matter format (must be at the top of the file):

        <!-- EU_AI_ACT_MAPPING_SIGNATURE
        mandate_hash: a1b2c3d4e5f60718
        signed_at: 2026-05-07T14:30:00Z
        covers_paths: [projects/, research_areas/, docs/]
        covers_mcp_servers: [linear]
        -->

    Returns a dict with the parsed fields, or None if the front-matter is
    missing or malformed.
    """
    match = re.search(
        r"<!--\s*EU_AI_ACT_MAPPING_SIGNATURE\s*\n(.*?)\n-->",
        mapping_text,
        re.DOTALL,
    )
    if not match:
        return None
    body = match.group(1)
    out: dict[str, object] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            items = [x.strip() for x in inner.split(",") if x.strip()] if inner else []
            out[key] = items
        else:
            out[key] = value
    if "mandate_hash" not in out or "signed_at" not in out:
        return None
    return out


def check_eu_ai_act_gate(
    role_yaml: dict,
    mandate_text: str,
    *,
    mapping_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    freshness_review_days: float = 90.0,
    now: Optional[datetime] = None,
) -> GateDecision:
    """The gate check the daemon calls before dispatching a role with
    t2_deployment: true. Returns GateDecision with allowed=True/False
    and a damage_signal class to emit if any.
    """
    now = now or datetime.now(timezone.utc)
    if not bool(role_yaml.get("t2_deployment")):
        return GateDecision(
            allowed=True,
            reason="role is not flagged as t2_deployment; gate does not apply",
        )

    if mapping_path is None:
        if repo_root is None:
            from cognitive_firm.common.paths import REPO_ROOT
            repo_root = REPO_ROOT
        mapping_path = _default_mapping_path(repo_root)

    if not mapping_path.exists():
        return GateDecision(
            allowed=False,
            reason=(
                f"t2_deployment: true but EU AI Act mapping does not exist at "
                f"{mapping_path}. Author + principal-sign the mapping before "
                f"deploying. The kernel does not author the mapping; consult "
                f"the adopter's GRC team for AI-Act-article assignments per "
                f"primitive."
            ),
            damage_signal="eu_ai_act_mapping_missing",
        )

    text = mapping_path.read_text(encoding="utf-8")
    sig = parse_mapping_signature(text)
    if sig is None:
        return GateDecision(
            allowed=False,
            reason=(
                f"mapping at {mapping_path} has no parseable principal "
                f"signature front-matter. Add an HTML comment block at the "
                f"top with EU_AI_ACT_MAPPING_SIGNATURE + mandate_hash + "
                f"signed_at + covers_paths + covers_mcp_servers."
            ),
            damage_signal="eu_ai_act_mapping_missing",
        )

    expected_hash = compute_mandate_hash(role_yaml, mandate_text)
    actual_hash = str(sig.get("mandate_hash", "")).strip()
    if actual_hash != expected_hash:
        return GateDecision(
            allowed=False,
            reason=(
                f"mapping signature is for mandate hash {actual_hash[:12]}…; "
                f"current mandate hash is {expected_hash[:12]}…. Mandate "
                f"has changed since last signing. Re-author and re-sign "
                f"the mapping for the new hash."
            ),
            damage_signal="eu_ai_act_mapping_stale",
        )

    # Coverage check: every authorized_paths root + every MCP server must
    # appear in the mapping's covers_* lists.
    covers_paths = set(sig.get("covers_paths") or [])
    covers_servers = set(sig.get("covers_mcp_servers") or [])

    for path in role_yaml.get("authorized_paths") or []:
        # Match against the path prefix (e.g., "projects/" matches "projects/").
        # Strip wildcards and trailing slashes for the comparison.
        normalized = str(path).rstrip("/*").rstrip("/")
        if not any(c.rstrip("/*").rstrip("/") == normalized for c in covers_paths):
            return GateDecision(
                allowed=False,
                reason=(
                    f"authorized path {path!r} is not covered by the mapping's "
                    f"covers_paths list {sorted(covers_paths)}. Add it + re-sign."
                ),
                damage_signal="eu_ai_act_mapping_stale",
            )

    for cap in role_yaml.get("authorized_mcp_capabilities") or []:
        if not isinstance(cap, dict):
            continue
        server = cap.get("server")
        if server and server not in covers_servers:
            return GateDecision(
                allowed=False,
                reason=(
                    f"authorized MCP server {server!r} is not covered by the "
                    f"mapping's covers_mcp_servers list {sorted(covers_servers)}. "
                    f"Add it + re-sign."
                ),
                damage_signal="eu_ai_act_mapping_stale",
            )

    # Freshness check (informational, does NOT block dispatch).
    signed_at_text = str(sig.get("signed_at", ""))
    freshness_signal: Optional[str] = None
    if signed_at_text:
        try:
            signed_at = datetime.fromisoformat(signed_at_text.replace("Z", "+00:00"))
            if signed_at.tzinfo is None:
                signed_at = signed_at.replace(tzinfo=timezone.utc)
            age_days = (now - signed_at).total_seconds() / 86400.0
            if age_days >= freshness_review_days:
                freshness_signal = "eu_ai_act_mapping_freshness_review_due"
        except Exception:  # noqa: BLE001
            pass

    return GateDecision(
        allowed=True,
        reason=(
            f"mapping signed for current mandate hash {expected_hash[:12]}…; "
            f"covers all authorized paths and MCP servers"
            + (f" (freshness review due: signed >{freshness_review_days} days ago)"
               if freshness_signal else "")
        ),
        damage_signal=freshness_signal,
    )
