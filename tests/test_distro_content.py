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
from cognitive_firm.distribution.governed_install import preview_overlay_install
from cognitive_firm.orchestration.adapter_conformance import load_adapter_manifest
from cognitive_firm.orchestration.adapter_conformance import (
    validate_adapter_conformance_config_file,
)
from cognitive_firm.orchestration.worker_taxonomy import WORKER_CLASSES, get_worker_archetype

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "distro"
STARTER = REGISTRY / "starter-firm"
STARTER_FILES = STARTER / "files"
LEANMILL_FORMAL = REGISTRY / "leanmill-formal-verification"
LANGGRAPH_RUNTIME = REGISTRY / "langgraph-runtime-adapter"


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
    """The operating unit's roles and class annotations must be valid."""
    units = json.loads(
        (STARTER_FILES / "operating_units" / "operating_units.json").read_text()
    )
    shipped_role_ids = {
        f"role.{yaml.safe_load(p.read_text())['role_id']}"
        for p in (STARTER_FILES / "roles").glob("*.yaml")
    }
    for unit in units:
        referenced = {unit["owner_role"], *unit.get("worker_roles", [])}
        referenced.update(unit.get("worker_role_classes", {}).keys())
        referenced.update(unit.get("worker_role_archetypes", {}).keys())
        missing = referenced - shipped_role_ids
        assert not missing, f"operating unit references unknown roles: {missing}"
        for role_id, worker_class in unit.get("worker_role_classes", {}).items():
            assert role_id in unit.get("worker_roles", []), (
                f"worker_role_classes references non-worker role: {role_id}"
            )
            assert worker_class in WORKER_CLASSES
        for role_id, archetype_id in unit.get("worker_role_archetypes", {}).items():
            assert role_id in unit.get("worker_roles", []), (
                f"worker_role_archetypes references non-worker role: {role_id}"
            )
            archetype = get_worker_archetype(archetype_id)
            declared_class = unit.get("worker_role_classes", {}).get(role_id)
            if declared_class is not None:
                assert archetype.worker_class == declared_class


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


def test_leanmill_formal_verification_overlay_is_discoverable_and_lintable():
    index = discover_packages(REGISTRY)
    assert index.errors == ()
    entry = index.get("leanmill-formal-verification")
    assert entry is not None
    assert entry.manifest.kind == "overlay"
    assert validate_manifest(entry.manifest, LEANMILL_FORMAL) == []


def test_leanmill_formal_verification_overlay_ships_adapter_manifest():
    manifest_path = (
        LEANMILL_FORMAL
        / "files"
        / "adapters"
        / "leanmill-formal-verification.yaml"
    )
    manifest = load_adapter_manifest(manifest_path)

    assert manifest.adapter_id == "leanmill-formal-verification"
    assert manifest.family == "formal_verification_provider"
    assert manifest.protocol == "formal_verification_provider_payload"
    assert manifest.executable.kind == "repository"
    assert manifest.executable.ref == "leanmill"
    assert "accepts_signed_verified_payload" in manifest.conformance_checks


def test_leanmill_formal_verification_overlay_installs_trust_policy(tmp_path):
    starter_manifest = load_manifest(STARTER / "package.yaml")
    install(starter_manifest, STARTER, tmp_path)
    manifest = load_manifest(LEANMILL_FORMAL / "package.yaml")
    install(manifest, LEANMILL_FORMAL, tmp_path)

    policy_path = tmp_path / "formal_verification" / "trusted_providers.json"
    assert policy_path.is_file()
    policy = json.loads(policy_path.read_text())
    assert policy["schema_version"] == "formal-verification-trust/v1"
    provider = policy["trusted_providers"][0]
    assert provider["provider"] == "leanmill"
    assert provider["public_key_ref"] == "configure://leanmill-ed25519-public-key"
    assert provider["requires_payload_signature"] is True
    assert provider["requires_reverification_refs"] is True
    assert provider["requires_faithfulness_refs"] is True

    adapter_manifest = load_adapter_manifest(
        tmp_path / "adapters" / "leanmill-formal-verification.yaml"
    )
    assert adapter_manifest.adapter_id == "leanmill-formal-verification"

    conformance_path = (
        tmp_path
        / "adapter_conformance"
        / "leanmill-formal-verification.json"
    )
    assert conformance_path.is_file()
    assert (
        validate_adapter_conformance_config_file(
            conformance_path,
            manifest_path=tmp_path / "adapters" / "leanmill-formal-verification.yaml",
            evidence_root=REPO_ROOT,
        )
        == []
    )


def test_leanmill_formal_verification_overlay_previews_as_authority_neutral(tmp_path):
    starter_manifest = load_manifest(STARTER / "package.yaml")
    install(starter_manifest, STARTER, tmp_path)
    manifest = load_manifest(LEANMILL_FORMAL / "package.yaml")

    preview = preview_overlay_install(
        overlay_manifest=manifest,
        overlay_root=LEANMILL_FORMAL,
        target_root=tmp_path,
    )

    assert preview.status == "review_ready"
    assert preview.can_proceed
    assert not preview.diff.expands_authority
    assert {
        file.dest for file in preview.files
    } == {
        "adapters/leanmill-formal-verification.yaml",
        "adapter_conformance/leanmill-formal-verification.json",
        "formal_verification/README.md",
        "formal_verification/trusted_providers.json",
    }


def test_langgraph_runtime_adapter_overlay_is_discoverable_and_lintable():
    index = discover_packages(REGISTRY)
    assert index.errors == ()
    entry = index.get("langgraph-runtime-adapter")
    assert entry is not None
    assert entry.manifest.kind == "overlay"
    assert validate_manifest(entry.manifest, LANGGRAPH_RUNTIME) == []


def test_langgraph_runtime_adapter_overlay_ships_adapter_manifest():
    manifest_path = (
        LANGGRAPH_RUNTIME
        / "files"
        / "adapters"
        / "langgraph-runtime-adapter.yaml"
    )
    manifest = load_adapter_manifest(manifest_path)

    assert manifest.adapter_id == "langgraph-runtime-adapter"
    assert manifest.family == "runtime"
    assert manifest.protocol == "runtime_event"
    assert manifest.executable.kind == "python_package"
    assert manifest.executable.ref == "cognitive_firm_langgraph_adapter"
    assert "interrupt_creates_human_work" in manifest.conformance_checks


def test_langgraph_runtime_adapter_overlay_installs_manifest_and_conformance_config(tmp_path):
    starter_manifest = load_manifest(STARTER / "package.yaml")
    install(starter_manifest, STARTER, tmp_path)
    manifest = load_manifest(LANGGRAPH_RUNTIME / "package.yaml")
    install(manifest, LANGGRAPH_RUNTIME, tmp_path)

    adapter_manifest = load_adapter_manifest(
        tmp_path / "adapters" / "langgraph-runtime-adapter.yaml"
    )
    assert adapter_manifest.adapter_id == "langgraph-runtime-adapter"

    conformance_path = (
        tmp_path
        / "adapter_conformance"
        / "langgraph-runtime-adapter.json"
    )
    assert conformance_path.is_file()
    conformance = json.loads(conformance_path.read_text())
    assert conformance["adapter_id"] == "langgraph-runtime-adapter"
    assert conformance["fixture_command"] == "make langgraph-governance-demo"
    assert {
        check["check_id"] for check in conformance["required_checks"]
    } >= {
        "started_event_idempotent",
        "interrupt_creates_human_work",
        "governed_run_bundle_has_no_caveats",
    }
    assert validate_adapter_conformance_config_file(
        conformance_path,
        manifest_path=tmp_path / "adapters" / "langgraph-runtime-adapter.yaml",
        evidence_root=REPO_ROOT,
    ) == []


def test_langgraph_runtime_adapter_overlay_previews_as_authority_neutral(tmp_path):
    starter_manifest = load_manifest(STARTER / "package.yaml")
    install(starter_manifest, STARTER, tmp_path)
    manifest = load_manifest(LANGGRAPH_RUNTIME / "package.yaml")

    preview = preview_overlay_install(
        overlay_manifest=manifest,
        overlay_root=LANGGRAPH_RUNTIME,
        target_root=tmp_path,
    )

    assert preview.status == "review_ready"
    assert preview.can_proceed
    assert not preview.diff.expands_authority
    assert {file.dest for file in preview.files} == {
        "adapters/langgraph-runtime-adapter.md",
        "adapters/langgraph-runtime-adapter.yaml",
        "adapter_conformance/langgraph-runtime-adapter.json",
    }
