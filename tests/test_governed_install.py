"""Tests for O3-P1 — the governed overlay install."""

from __future__ import annotations

from pathlib import Path

import pytest

from cognitive_firm.distribution import install, load_manifest
from cognitive_firm.distribution.governed_install import (
    GovernedInstallError,
    apply_approved_install,
    propose_overlay_install,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTER = REPO_ROOT / "distro" / "starter-firm"

# A full role.v1 analyst role whose write scope is widened to everything.
_WIDENED_ANALYST = """\
schema_version: 1
role_id: analyst
role_class: specialist
description: Production specialist with a widened write scope (test overlay).
authorized_paths:
  - "*"
forbidden_paths: []
delegates_to: []
escalates_to:
  - role.lead
budget:
  daily_cap_usd: 25.0
mandate_path: mandates/analyst_mandate.md
"""

# The same role, but with a dangling escalation target — an ungovernable org.
_BROKEN_ANALYST = _WIDENED_ANALYST.replace("role.lead", "role.ghost")


def _overlay(root: Path, name: str, *, dest: str, op: str,
             source_name: str, body: str) -> Path:
    pkg = root / name
    (pkg / "files").mkdir(parents=True)
    (pkg / "files" / source_name).write_text(body)
    (pkg / "package.yaml").write_text(
        f"schema_version: 1\nname: {name}\nversion: 0.1.0\nkind: overlay\n"
        f"description: a governed-install test overlay package\n"
        f"components:\n  - source: {source_name}\n    dest: {dest}\n"
        f"    op: {op}\n"
    )
    return pkg


def _installed_org(tmp_path: Path) -> Path:
    target = tmp_path / "org"
    install(load_manifest(STARTER / "package.yaml"), STARTER, target)
    return target


def test_propose_clean_overlay_is_review_ready(tmp_path):
    target = _installed_org(tmp_path)
    overlay = _overlay(
        tmp_path, "prefs-overlay", dest="preferences/principal.yaml",
        op="replace", source_name="prefs.yaml",
        body="principal_id: x\nreview_cadence: weekly\n",
    )
    proposed = propose_overlay_install(
        overlay_manifest=load_manifest(overlay / "package.yaml"),
        overlay_root=overlay, target_root=target,
        governance_log=tmp_path / "gov.jsonl",
    )
    assert proposed.proposal.status == "review_ready"
    assert proposed.can_proceed
    assert not proposed.diff.expands_authority  # a prefs change touches no role


def test_an_authority_expanding_overlay_is_blocked(tmp_path):
    # The kernel's governance model: a package may not widen a role's write
    # scope. An expanding overlay fails write_scope_preserved -> blocked.
    target = _installed_org(tmp_path)
    overlay = _overlay(
        tmp_path, "widen-overlay", dest="roles/analyst.yaml", op="replace",
        source_name="analyst.yaml", body=_WIDENED_ANALYST,
    )
    proposed = propose_overlay_install(
        overlay_manifest=load_manifest(overlay / "package.yaml"),
        overlay_root=overlay, target_root=target,
        governance_log=tmp_path / "gov.jsonl",
    )
    assert proposed.diff.expands_authority
    assert proposed.proposal.status == "blocked"
    assert not proposed.can_proceed
    assert "Expands authority" in proposed.proposal.expected_behavior_change
    with pytest.raises(GovernedInstallError):
        apply_approved_install(proposed, overlay, target)


def test_an_ungovernable_overlay_is_rejected_before_a_proposal(tmp_path):
    target = _installed_org(tmp_path)
    overlay = _overlay(
        tmp_path, "broken-overlay", dest="roles/analyst.yaml", op="replace",
        source_name="analyst.yaml", body=_BROKEN_ANALYST,
    )
    with pytest.raises(GovernedInstallError):
        propose_overlay_install(
            overlay_manifest=load_manifest(overlay / "package.yaml"),
            overlay_root=overlay, target_root=target,
        )


def test_cli_install_overlay_previews_then_approves(tmp_path):
    from cognitive_firm.distribution.cli import main as distro_main

    target = _installed_org(tmp_path)
    overlay = _overlay(
        tmp_path, "cli-overlay", dest="preferences/principal.yaml",
        op="replace", source_name="prefs.yaml",
        body="principal_id: via_cli\nreview_cadence: weekly\n",
    )
    prefs = target / "preferences" / "principal.yaml"

    # without --approve: a preview — the proposal is filed, nothing installed
    assert distro_main(
        ["install-overlay", str(overlay), "--into", str(target)]
    ) == 0
    assert "via_cli" not in prefs.read_text()

    # with --approve: the overlay is applied
    assert distro_main(
        ["install-overlay", str(overlay), "--into", str(target), "--approve"]
    ) == 0
    assert "via_cli" in prefs.read_text()


def test_apply_approved_install_materializes_and_attests(tmp_path):
    target = _installed_org(tmp_path)
    overlay = _overlay(
        tmp_path, "prefs-overlay", dest="preferences/principal.yaml",
        op="replace", source_name="prefs.yaml",
        body="principal_id: governed\nreview_cadence: weekly\n",
    )
    proposed = propose_overlay_install(
        overlay_manifest=load_manifest(overlay / "package.yaml"),
        overlay_root=overlay, target_root=target,
        governance_log=tmp_path / "gov.jsonl",
    )
    receipt = apply_approved_install(proposed, overlay, target)
    assert receipt.package == "prefs-overlay"
    assert "governed" in (target / "preferences" / "principal.yaml").read_text()
    events = (
        target / ".cognitive-firm" / "distribution-events.jsonl"
    ).read_text()
    assert "package.install_approved" in events
