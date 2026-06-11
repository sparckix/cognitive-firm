"""Tests for the distribution layer: manifests, installer, registry, CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cognitive_firm.distribution import (
    InstallError,
    ManifestError,
    boot_check,
    check_kernel_compat,
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


def test_verify_install_catches_drifted_adapter_policy(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    receipt = install(manifest, STARTER, tmp_path)
    conformance_dir = tmp_path / "adapter_conformance"
    conformance_dir.mkdir()
    (conformance_dir / "ghost.json").write_text(
        json.dumps(
            {
                "schema_version": "cognitive-firm-adapter-conformance/v1",
                "adapter_id": "ghost-adapter",
                "protocol": "runtime_event",
                "fixture_command": "make ghost-adapter-fixture",
                "required_checks": [
                    {
                        "check_id": "started_event_idempotent",
                        "evidence": "tests/test_runtime_adapters.py",
                    }
                ],
            }
        )
    )

    issues = verify_install(receipt, tmp_path)

    assert any("adapter_conformance/ghost.json" in issue for issue in issues)
    assert any("no matching adapter manifest" in issue for issue in issues)


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


def test_cli_lint_validates_adapter_manifest_and_conformance_config(tmp_path, capsys):
    pkg = tmp_path / "adapter-pkg"
    (pkg / "files" / "adapters").mkdir(parents=True)
    (pkg / "files" / "adapter_conformance").mkdir(parents=True)
    (pkg / "package.yaml").write_text(
        "schema_version: 1\n"
        "name: adapter-pkg\n"
        "version: 0.1.0\n"
        "kind: overlay\n"
        "description: adapter package with invalid declarations\n"
        "components:\n"
        "  - source: adapters\n"
        "    dest: adapters\n"
        "  - source: adapter_conformance\n"
        "    dest: adapter_conformance\n"
    )
    (pkg / "files" / "adapters" / "bad.yaml").write_text(
        "schema_version: cognitive-firm-adapter-manifest/v1\n"
        "adapter_id: bad-adapter\n"
        "family: runtime\n"
        "protocol: runtime_event\n"
        "description: too short\n"
        "executable:\n"
        "  kind: python_package\n"
        "  ref: bad_pkg\n"
        "conformance_checks:\n"
        "  - started_event_idempotent\n"
    )
    (pkg / "files" / "adapter_conformance" / "bad.json").write_text(
        json.dumps(
            {
                "schema_version": "cognitive-firm-adapter-conformance/v1",
                "adapter_id": "other-adapter",
                "protocol": "runtime_event",
                "fixture_command": "make adapter-fixture",
                "required_checks": [
                    {
                        "check_id": "started_event_idempotent",
                        "evidence": "tests/test_runtime_adapters.py",
                    }
                ],
            }
        )
    )

    assert distro_main(["lint", str(pkg)]) == 1
    err = capsys.readouterr().err

    assert "files/adapters/bad.yaml" in err
    assert "description is too short" in err
    assert "files/adapter_conformance/bad.json" in err
    assert "no matching adapter manifest" in err


def test_cli_lint_accepts_langgraph_adapter_policy_package(capsys):
    assert distro_main(["lint", str(REGISTRY / "langgraph-runtime-adapter")]) == 0
    out = capsys.readouterr().out
    assert "lint ok: langgraph-runtime-adapter" in out


def test_cli_lint_validates_formal_verification_trust_policy(tmp_path, capsys):
    pkg = tmp_path / "formal-provider-pkg"
    (pkg / "files" / "formal_verification").mkdir(parents=True)
    (pkg / "package.yaml").write_text(
        "schema_version: 1\n"
        "name: formal-provider-pkg\n"
        "version: 0.1.0\n"
        "kind: overlay\n"
        "description: formal provider package with bad trust policy\n"
        "components:\n"
        "  - source: formal_verification\n"
        "    dest: formal_verification\n"
    )
    (pkg / "files" / "formal_verification" / "trusted_providers.json").write_text(
        json.dumps(
            {
                "schema_version": "formal-verification-trust/v1",
                "trusted_providers": [
                    {
                        "provider": "leanmill",
                        "requires_payload_signature": True,
                    }
                ],
            }
        )
    )

    assert distro_main(["lint", str(pkg)]) == 1
    err = capsys.readouterr().err

    assert "files/formal_verification/trusted_providers.json" in err
    assert "requires payload signatures" in err


def test_install_refuses_bad_formal_verification_trust_policy(tmp_path):
    starter_manifest = load_manifest(STARTER / "package.yaml")
    install(starter_manifest, STARTER, tmp_path)

    pkg = tmp_path / "bad-formal-provider"
    (pkg / "files" / "formal_verification").mkdir(parents=True)
    (pkg / "package.yaml").write_text(
        "schema_version: 1\n"
        "name: bad-formal-provider\n"
        "version: 0.1.0\n"
        "kind: overlay\n"
        "description: bad formal provider package\n"
        "components:\n"
        "  - source: formal_verification\n"
        "    dest: formal_verification\n"
    )
    (pkg / "files" / "formal_verification" / "trusted_providers.json").write_text(
        json.dumps(
            {
                "schema_version": "formal-verification-trust/v1",
                "trusted_providers": [
                    {
                        "provider": "leanmill",
                        "requires_payload_signature": True,
                    }
                ],
            }
        )
    )
    manifest = load_manifest(pkg / "package.yaml")

    with pytest.raises(InstallError, match="requires payload signatures"):
        install(manifest, pkg, tmp_path)

    assert not (tmp_path / "formal_verification" / "trusted_providers.json").exists()


# --- G1: kernel-version gate -------------------------------------------------

def test_install_refuses_incompatible_kernel(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    with pytest.raises(InstallError):
        install(manifest, STARTER, tmp_path, kernel_version="0.0.1")


def test_install_accepts_compatible_kernel(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    receipt = install(manifest, STARTER, tmp_path, kernel_version="0.1.0")
    assert receipt.package == "starter-firm"


def test_check_kernel_compat_directly():
    manifest = load_manifest(STARTER / "package.yaml")
    assert check_kernel_compat(manifest.kernel, "0.1.0") == []
    assert check_kernel_compat(manifest.kernel, "0.0.9") != []


# --- G4/G5: governance-graph boot check --------------------------------------

def test_boot_check_passes_starter_firm(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    install(manifest, STARTER, tmp_path)
    assert boot_check(tmp_path) == []


def test_boot_check_catches_dangling_escalation(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    install(manifest, STARTER, tmp_path)
    lead = tmp_path / "roles" / "lead.yaml"
    lead.write_text(lead.read_text().replace("role.principal", "role.ghost"))
    issues = boot_check(tmp_path)
    assert any("ghost" in issue for issue in issues)


def test_boot_check_catches_missing_authority(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    install(manifest, STARTER, tmp_path)
    principal = tmp_path / "roles" / "principal.yaml"
    principal.write_text(
        principal.read_text().replace(
            "role_class: authority", "role_class: manager"
        )
    )
    assert any("authority" in issue for issue in boot_check(tmp_path))


def test_boot_check_accepts_multiple_authorities_when_domains_scope_them(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    install(manifest, STARTER, tmp_path)
    principal = tmp_path / "roles" / "principal.yaml"
    legal = tmp_path / "roles" / "legal_authority.yaml"
    legal.write_text(
        principal.read_text().replace("role_id: principal", "role_id: legal_authority")
    )
    domains = tmp_path / "authority_domains" / "authority_domains.json"
    domains.parent.mkdir()
    domains.write_text(
        json.dumps(
            {
                "authority_domains": [
                    {
                        "domain_id": "global",
                        "authority_role_id": "role.principal",
                        "scope_kind": "global",
                        "scope_id": "*",
                    },
                    {
                        "domain_id": "tenant_a_legal",
                        "authority_role_id": "role.legal_authority",
                        "scope_kind": "tenant",
                        "scope_id": "tenant-a",
                    },
                ]
            }
        )
    )

    assert boot_check(tmp_path) == []


def test_boot_check_rejects_unscoped_extra_authority(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    install(manifest, STARTER, tmp_path)
    principal = tmp_path / "roles" / "principal.yaml"
    legal = tmp_path / "roles" / "legal_authority.yaml"
    legal.write_text(
        principal.read_text().replace("role_id: principal", "role_id: legal_authority")
    )
    domains = tmp_path / "authority_domains" / "authority_domains.json"
    domains.parent.mkdir()
    domains.write_text(
        json.dumps(
            {
                "authority_domains": [
                    {
                        "domain_id": "global",
                        "authority_role_id": "role.principal",
                        "scope_kind": "global",
                        "scope_id": "*",
                    }
                ]
            }
        )
    )

    assert any("missing authority-domain records" in issue for issue in boot_check(tmp_path))


# --- G11 / R1: transactional, git-backed install -----------------------------

def test_install_creates_git_boundary(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    receipt = install(manifest, STARTER, tmp_path)
    assert (tmp_path / ".git").is_dir()
    assert receipt.commit_sha
    assert receipt.git_tag == "install/starter-firm/0.1.0"
    assert receipt.pre_install_ref is None  # fresh repo, no prior commit


def _write_broken_distro(root: Path) -> Path:
    """A manifest-valid distro whose org cannot boot (no authority role)."""
    pkg = root / "badpkg"
    (pkg / "files" / "roles").mkdir(parents=True)
    (pkg / "package.yaml").write_text(
        "schema_version: 1\nname: badpkg\nversion: 0.1.0\nkind: distro\n"
        "description: a distro with no authority role\n"
        "components:\n  - source: roles\n    dest: roles\n"
    )
    (pkg / "files" / "roles" / "worker.yaml").write_text(
        "schema_version: 1\nrole_id: worker\nrole_class: specialist\n"
        "description: a worker role with no authority above it\n"
        "authorized_paths: []\nforbidden_paths: []\n"
        "delegates_to: []\nescalates_to: []\nbudget: {}\nmandate_path: null\n"
    )
    return pkg


def test_install_is_transactional_on_unbootable_distro(tmp_path):
    pkg = _write_broken_distro(tmp_path)
    manifest = load_manifest(pkg / "package.yaml")
    target = tmp_path / "target"
    with pytest.raises(InstallError):
        install(manifest, pkg, target)
    # the target never existed; a failed install must leave no trace
    assert not target.exists()


def _write_broken_distro_that_patches(root: Path) -> Path:
    """A manifest-valid distro whose org cannot boot, and which (before the
    boot failure) PATCHES a pre-existing JSON file and OVERWRITES a pre-existing
    text file. Used to prove a failed install fully restores the target."""
    pkg = root / "patchpkg"
    (pkg / "files" / "roles").mkdir(parents=True)
    (pkg / "files" / "patches").mkdir(parents=True)
    (pkg / "files" / "overwrites").mkdir(parents=True)
    (pkg / "package.yaml").write_text(
        "schema_version: 1\nname: patchpkg\nversion: 0.1.0\nkind: distro\n"
        "description: a distro that patches files then fails to boot\n"
        "components:\n"
        "  - source: patches/config.json\n    dest: config.json\n    op: patch\n"
        "  - source: overwrites/notes.txt\n    dest: notes.txt\n    op: replace\n"
        "  - source: roles\n    dest: roles\n"
    )
    (pkg / "files" / "roles" / "worker.yaml").write_text(
        "schema_version: 1\nrole_id: worker\nrole_class: specialist\n"
        "description: a worker role with no authority above it\n"
        "authorized_paths: []\nforbidden_paths: []\n"
        "delegates_to: []\nescalates_to: []\nbudget: {}\nmandate_path: null\n"
    )
    (pkg / "files" / "patches" / "config.json").write_text(
        '{"feature": "new-value"}\n'
    )
    (pkg / "files" / "overwrites" / "notes.txt").write_text(
        "content installed by the package\n"
    )
    return pkg


def test_failed_install_restores_patched_file_on_uncommitted_target(tmp_path):
    """G11: a failed install onto an existing-but-uncommitted target must leave
    a patched file byte-identical to before."""
    pkg = _write_broken_distro_that_patches(tmp_path)
    manifest = load_manifest(pkg / "package.yaml")
    target = tmp_path / "target"
    target.mkdir()
    original = '{"feature": "original", "keep": true}\n'
    (target / "config.json").write_text(original)
    (target / "notes.txt").write_text("the adopter's own notes\n")

    with pytest.raises(InstallError):
        install(manifest, pkg, target)

    assert (target / "config.json").read_text() == original


def test_failed_install_restores_overwritten_file_on_uncommitted_target(tmp_path):
    """G11: a failed install onto an existing-but-uncommitted target must leave
    an overwritten file byte-identical to before."""
    pkg = _write_broken_distro_that_patches(tmp_path)
    manifest = load_manifest(pkg / "package.yaml")
    target = tmp_path / "target"
    target.mkdir()
    (target / "config.json").write_text('{"feature": "original"}\n')
    original_notes = "the adopter's own notes\n"
    (target / "notes.txt").write_text(original_notes)

    with pytest.raises(InstallError):
        install(manifest, pkg, target)

    assert (target / "notes.txt").read_text() == original_notes
