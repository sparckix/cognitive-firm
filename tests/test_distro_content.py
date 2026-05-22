"""Tests for distro *content*: the starter-firm governance loop and packaging.

These complement ``test_distribution.py`` (which tests the manifest/installer
machinery). Here we assert the starter-firm distro ships a real, runnable
governance loop (G6) and that the ``distro/`` tree is packaged into the wheel
(G8). Deployment docs (G10) are also checked structurally.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from cognitive_firm.distribution import (
    discover_packages,
    install,
    load_manifest,
    validate_manifest,
    verify_install,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "distro"
STARTER = REGISTRY / "starter-firm"
STARTER_FILES = STARTER / "files"


# --- G6: starter-firm ships a day-one governance loop -----------------------


def test_starter_firm_ships_an_operating_unit():
    units_path = STARTER_FILES / "operating_units" / "operating_units.json"
    assert units_path.is_file(), "starter-firm must ship an operating unit"
    units = json.loads(units_path.read_text())
    assert isinstance(units, list) and units, "operating_units.json is empty"
    for unit in units:
        # Match the generic OperatingUnit shape used by the example tenant.
        for key in (
            "unit_id",
            "unit_kind",
            "display_name",
            "owner_role",
            "allowed_work_kinds",
            "allowed_exits",
            "worker_roles",
        ):
            assert key in unit, f"operating unit missing '{key}'"
        # accountable-closure: every governance-required exit is a declared exit.
        for exit_kind in unit.get("governance_required_for", []):
            assert exit_kind in unit["allowed_exits"], (
                f"governance_required_for '{exit_kind}' not in allowed_exits"
            )


def test_starter_firm_operating_unit_uses_shipped_roles():
    """The operating unit's roles must exist among the distro's roles."""
    units = json.loads(
        (STARTER_FILES / "operating_units" / "operating_units.json").read_text()
    )
    shipped_role_ids = {
        f"role.{yaml.safe_load(p.read_text())['role_id']}"
        for p in (STARTER_FILES / "roles").glob("*.yaml")
    }
    for unit in units:
        referenced = {unit["owner_role"], *unit.get("worker_roles", [])}
        missing = referenced - shipped_role_ids
        assert not missing, f"operating unit references unknown roles: {missing}"


def test_starter_firm_ships_a_project_charter():
    charters = list(
        (STARTER_FILES / "projects").rglob("project_charter.md")
    )
    assert charters, "starter-firm must ship at least one project charter"
    text = charters[0].read_text()
    # Required charter sections per docs/protocols/project-charter.md.
    for section in (
        "## Core Question",
        "## Out Of Scope",
        "## End States",
        "## Forecast Type",
    ):
        assert section in text, f"project charter missing section: {section}"


def test_starter_firm_manifest_installs_loop_components():
    """package.yaml must install the operating unit and project charter."""
    manifest = load_manifest(STARTER / "package.yaml")
    dests = {c.dest for c in manifest.components}
    assert "operating_units" in dests, "manifest does not install operating_units"
    assert "projects" in dests, "manifest does not install projects"
    assert validate_manifest(manifest, STARTER) == []


def test_starter_firm_manifest_has_no_requires_key():
    """`requires` is being removed from the schema; the distro must not use it."""
    raw = yaml.safe_load((STARTER / "package.yaml").read_text())
    assert "requires" not in raw, "starter-firm package.yaml still declares requires"


def test_installed_starter_firm_has_runnable_loop(tmp_path):
    """A fresh install lands the governance-loop files and verifies bootable."""
    manifest = load_manifest(STARTER / "package.yaml")
    receipt = install(manifest, STARTER, tmp_path)
    assert verify_install(receipt, tmp_path) == []

    unit = tmp_path / "operating_units" / "operating_units.json"
    charter = tmp_path / "projects" / "first-project" / "project_charter.md"
    assert unit.is_file(), "operating unit did not land in the installed org"
    assert charter.is_file(), "project charter did not land in the installed org"
    # The installed operating unit is still valid JSON describing a unit.
    units = json.loads(unit.read_text())
    assert units and "allowed_exits" in units[0]


# --- G8: distro/ is packaged into the wheel ---------------------------------


def test_pyproject_packages_distro_as_package_data():
    """pyproject.toml must ship distro/ as a discoverable package with data."""
    text = (REPO_ROOT / "pyproject.toml").read_text()
    assert 'include = ["cognitive_firm*", "distro*"]' in text, (
        "pyproject.toml setuptools find must include distro*"
    )
    assert "distro = [" in text, "pyproject.toml must declare distro package-data"


def test_distro_is_an_importable_package():
    """distro/ needs __init__.py so setuptools ships it as package data."""
    assert (REGISTRY / "__init__.py").is_file(), "distro/__init__.py is missing"


def test_manifest_in_includes_distro_tree():
    manifest_in = REPO_ROOT / "MANIFEST.in"
    assert manifest_in.is_file(), "MANIFEST.in is missing"
    text = manifest_in.read_text()
    assert "distro" in text, "MANIFEST.in does not reference distro/"


# --- G10: single-host deployment topology is documented ---------------------


def test_starter_firm_ships_deploy_doc():
    deploy_doc = STARTER / "DEPLOY.md"
    assert deploy_doc.is_file(), "starter-firm must ship DEPLOY.md"
    text = deploy_doc.read_text()
    # The doc must point at the existing infra, not invent new components.
    assert "docker compose" in text, "DEPLOY.md must cover the docker-compose path"
    assert "setup_vps.sh" in text, "DEPLOY.md must cover the one-VPS path"


def test_deploy_doc_references_existing_systemd_units():
    text = (STARTER / "DEPLOY.md").read_text()
    for unit in ("agent-daemon.service", "orbit-sync.service"):
        assert unit in text, f"DEPLOY.md should reference {unit}"
        assert (REPO_ROOT / "deploy" / unit).is_file(), (
            f"DEPLOY.md references a non-existent unit: {unit}"
        )


def test_distro_registry_still_discovers_starter_firm():
    """The content additions must not break registry discovery."""
    index = discover_packages(REGISTRY)
    assert index.errors == ()
    assert index.get("starter-firm") is not None
