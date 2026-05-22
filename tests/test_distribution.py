"""Tests for the distribution layer: manifests, installer, registry, CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from cognitive_firm.distribution import (
    ManifestError,
    discover_packages,
    install,
    load_manifest,
    load_receipt,
    validate_manifest,
    verify_install,
)
from cognitive_firm.distribution.cli import main as distro_main
from cognitive_firm.distribution.manifest import Component, PackageManifest

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "distro"
STARTER = REGISTRY / "starter-firm"


def test_starter_firm_manifest_loads_and_is_valid():
    manifest = load_manifest(STARTER / "package.yaml")
    assert manifest.name == "starter-firm"
    assert manifest.kind == "distro"
    assert manifest.components
    assert validate_manifest(manifest, STARTER) == []


def test_validate_manifest_flags_bad_kind(tmp_path):
    bad = PackageManifest(
        name="x",
        version="0.1.0",
        kind="bogus",
        description="a description here",
        components=(Component("roles", "roles"),),
    )
    issues = validate_manifest(bad, tmp_path)
    assert any("kind" in issue for issue in issues)


def test_load_manifest_rejects_path_escape(tmp_path):
    (tmp_path / "files" / "roles").mkdir(parents=True)
    (tmp_path / "package.yaml").write_text(
        "schema_version: 1\nname: evil\nversion: 0.1.0\nkind: overlay\n"
        "description: tries to escape the target\n"
        "components:\n  - source: roles\n    dest: ../../etc\n"
    )
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "package.yaml")


def test_discover_packages_indexes_starter_firm():
    index = discover_packages(REGISTRY)
    assert index.errors == ()
    entry = index.get("starter-firm")
    assert entry is not None
    assert entry.manifest.kind == "distro"
    assert index.of_kind("distro")


def test_install_materializes_a_bootable_org(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    receipt = install(manifest, STARTER, tmp_path)
    assert (tmp_path / "roles" / "principal.yaml").is_file()
    assert (tmp_path / "mandates" / "lead_mandate.md").is_file()
    assert (tmp_path / ".cognitive-firm" / "install-starter-firm.json").is_file()
    assert all(f.action == "created" for f in receipt.files)
    assert verify_install(receipt, tmp_path) == []


def test_install_skips_conflicts_without_force(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    install(manifest, STARTER, tmp_path)
    second = install(manifest, STARTER, tmp_path)
    assert second.skipped_conflicts
    assert all(f.action == "skipped" for f in second.files)
    forced = install(manifest, STARTER, tmp_path, force=True)
    assert all(f.action == "overwritten" for f in forced.files)


def test_verify_install_catches_a_broken_role(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    receipt = install(manifest, STARTER, tmp_path)
    (tmp_path / "roles" / "principal.yaml").write_text("role_id: principal\n")
    issues = verify_install(receipt, tmp_path)
    assert any("principal.yaml" in issue for issue in issues)


def test_load_receipt_roundtrip(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    install(manifest, STARTER, tmp_path)
    receipt = load_receipt(tmp_path, "starter-firm")
    assert receipt.package == "starter-firm"
    assert verify_install(receipt, tmp_path) == []


def test_cli_list_install_and_verify(tmp_path, capsys):
    assert distro_main(["list"]) == 0
    assert "starter-firm" in capsys.readouterr().out

    target = tmp_path / "my-firm"
    assert distro_main(["install", "starter-firm", "--into", str(target)]) == 0
    assert (target / "roles" / "principal.yaml").is_file()

    assert distro_main(["verify", "starter-firm", "--into", str(target)]) == 0
