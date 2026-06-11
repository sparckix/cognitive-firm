"""Tests for O3-P1 — the governed overlay install."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cognitive_firm.distribution import install, load_manifest
from cognitive_firm.distribution.governed_install import (
    GovernedInstallError,
    apply_approved_install,
    preview_overlay_install,
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


# The live analyst role with its forbidden_paths emptied — nothing else
# changed. Pre-fix this produced a zero-line diff and reached review_ready;
# emptying a guardrail expands authority and must block.
_UNGUARDED_ANALYST = """\
schema_version: 1
role_id: analyst
role_class: specialist
description: >
  Production specialist. Performs the organization's analysis and work-product
  tasks, records findings as durable state, and hands completed work to the
  reviewer for accountable closure.
authorized_paths:
  - "projects/"
forbidden_paths: []
delegates_to: []
escalates_to:
  - role.lead
budget:
  daily_cap_usd: 25.00
  session_cap_usd: 15.00
  single_action_cap_usd: 5.00
  warn_threshold_frac: 0.80
  absolute_ceiling_usd: 25.00
mandate_path: mandates/analyst_mandate.md
"""


def test_an_overlay_that_empties_forbidden_paths_is_blocked(tmp_path):
    # F-6: removing forbidden_paths entries widens where a role may write.
    # Such an overlay must fail write_scope_preserved and be blocked, not
    # slip through as a zero-line diff.
    target = _installed_org(tmp_path)
    overlay = _overlay(
        tmp_path, "unguard-overlay", dest="roles/analyst.yaml", op="replace",
        source_name="analyst.yaml", body=_UNGUARDED_ANALYST,
    )
    proposed = propose_overlay_install(
        overlay_manifest=load_manifest(overlay / "package.yaml"),
        overlay_root=overlay, target_root=target,
        governance_log=tmp_path / "gov.jsonl",
    )
    assert not proposed.diff.is_empty
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


def test_preview_overlay_is_no_write_and_reports_file_plan(tmp_path):
    target = _installed_org(tmp_path)
    overlay = _overlay(
        tmp_path, "preview-overlay", dest="preferences/principal.yaml",
        op="replace", source_name="prefs.yaml",
        body="principal_id: preview\nreview_cadence: weekly\n",
    )
    prefs = target / "preferences" / "principal.yaml"
    before = prefs.read_text()

    preview = preview_overlay_install(
        overlay_manifest=load_manifest(overlay / "package.yaml"),
        overlay_root=overlay,
        target_root=target,
    )

    assert preview.status == "review_ready"
    assert preview.can_proceed
    assert not preview.diff.expands_authority
    assert preview.files[0].dest == "preferences/principal.yaml"
    assert preview.files[0].op == "replace"
    assert prefs.read_text() == before
    assert not (target / "governance_changes" / "governance_changes.jsonl").exists()


def test_preview_overlay_blocks_authority_expansion_without_proposal(tmp_path):
    target = _installed_org(tmp_path)
    overlay = _overlay(
        tmp_path, "preview-widen", dest="roles/analyst.yaml", op="replace",
        source_name="analyst.yaml", body=_WIDENED_ANALYST,
    )

    preview = preview_overlay_install(
        overlay_manifest=load_manifest(overlay / "package.yaml"),
        overlay_root=overlay,
        target_root=target,
    )

    assert preview.status == "blocked"
    assert not preview.can_proceed
    assert preview.diff.expands_authority
    assert "roles/analyst.yaml" == preview.files[0].dest
    assert not (target / "governance_changes" / "governance_changes.jsonl").exists()


def test_cli_preview_overlay_json_returns_nonzero_for_blocked(tmp_path, capsys):
    from cognitive_firm.distribution.cli import main as distro_main

    target = _installed_org(tmp_path)
    overlay = _overlay(
        tmp_path, "cli-preview-widen", dest="roles/analyst.yaml", op="replace",
        source_name="analyst.yaml", body=_WIDENED_ANALYST,
    )

    assert distro_main(
        ["preview-overlay", str(overlay), "--into", str(target), "--json"]
    ) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "blocked"
    assert payload["expands_authority"] is True
    assert payload["files"][0]["dest"] == "roles/analyst.yaml"


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
