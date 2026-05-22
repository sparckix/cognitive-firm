"""Tests for the O3-P4 third-party authoring loop: ``lint``, ``--dry-run``,
and the package template under ``docs/templates/package/``."""

from __future__ import annotations

from pathlib import Path

import pytest

from cognitive_firm.distribution.cli import main as distro_main

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "distro"
TEMPLATE = REPO_ROOT / "docs" / "templates" / "package"


def _write_package(root: Path, manifest: str, files: dict[str, str]) -> Path:
    """Materialize a package directory with a manifest and files/ contents."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.yaml").write_text(manifest)
    for rel, content in files.items():
        path = root / "files" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return root


_GOOD_MANIFEST = """\
schema_version: 1
name: lint-fixture
version: 0.1.0
kind: overlay
description: A small overlay used as a lint fixture in the authoring tests.
kernel:
  min_version: "0.1.0"
components:
  - source: notes
    dest: notes
    op: add
"""


# --- lint: a clean package --------------------------------------------------

def test_lint_clean_package_passes(tmp_path, capsys):
    pkg = _write_package(
        tmp_path / "pkg", _GOOD_MANIFEST, {"notes/readme.txt": "hello\n"}
    )
    assert distro_main(["lint", str(pkg)]) == 0
    assert "lint ok" in capsys.readouterr().out


def test_lint_accepts_package_yaml_path(tmp_path):
    pkg = _write_package(
        tmp_path / "pkg", _GOOD_MANIFEST, {"notes/readme.txt": "hi\n"}
    )
    assert distro_main(["lint", str(pkg / "package.yaml")]) == 0


def test_lint_resolves_registry_package_by_name():
    # starter-firm is a real, valid package in the bundled registry.
    assert distro_main(["lint", "starter-firm"]) == 0


# --- lint: catches authoring mistakes ---------------------------------------

def test_lint_flags_missing_component_source(tmp_path, capsys):
    # Manifest declares a `notes` component but files/ is empty.
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.yaml").write_text(_GOOD_MANIFEST)
    (pkg / "files").mkdir()
    assert distro_main(["lint", str(pkg)]) == 1
    err = capsys.readouterr().err
    assert "LINT FAILED" in err
    assert "component source missing" in err


def test_lint_flags_bad_op(tmp_path, capsys):
    bad = _GOOD_MANIFEST.replace("op: add", "op: clobber")
    pkg = _write_package(tmp_path / "pkg", bad, {"notes/readme.txt": "x\n"})
    assert distro_main(["lint", str(pkg)]) == 1
    assert "op 'clobber'" in capsys.readouterr().err


def test_lint_flags_bad_kind(tmp_path, capsys):
    bad = _GOOD_MANIFEST.replace("kind: overlay", "kind: widget")
    pkg = _write_package(tmp_path / "pkg", bad, {"notes/readme.txt": "x\n"})
    assert distro_main(["lint", str(pkg)]) == 1
    assert "kind 'widget'" in capsys.readouterr().err


def test_lint_flags_missing_files_dir(tmp_path, capsys):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    manifest = _GOOD_MANIFEST.replace(
        "  - source: notes\n    dest: notes\n    op: add\n", ""
    ) + "  - source: notes\n    dest: notes\n    optional: true\n"
    (pkg / "package.yaml").write_text(manifest)
    assert distro_main(["lint", str(pkg)]) == 1
    assert "no files/ directory" in capsys.readouterr().err


def test_lint_flags_unparseable_manifest(tmp_path, capsys):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "package.yaml").write_text("name: x\n  bad: : indent\n")
    assert distro_main(["lint", str(pkg)]) == 1
    assert "LINT FAILED" in capsys.readouterr().err


def test_lint_unknown_package_returns_2(tmp_path, capsys):
    assert distro_main(["lint", str(tmp_path / "nonexistent")]) == 2
    assert "no package found" in capsys.readouterr().err


# --- install --dry-run ------------------------------------------------------

def test_dry_run_prints_plan_and_writes_nothing(tmp_path, capsys):
    target = tmp_path / "scratch-org"
    rc = distro_main(
        ["install", "starter-firm", "--into", str(target), "--dry-run"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "nothing was written" in out
    # No git repo, no files — the target was never created.
    assert not target.exists()


def test_dry_run_lists_files_with_ops(tmp_path, capsys):
    target = tmp_path / "scratch-org"
    distro_main(
        ["install", "starter-firm", "--into", str(target), "--dry-run"]
    )
    out = capsys.readouterr().out
    assert "roles/principal.yaml" in out
    assert "[add" in out


def test_dry_run_marks_conflicts(tmp_path, capsys):
    target = tmp_path / "scratch-org"
    # Pre-create a file the install would touch.
    (target / "roles").mkdir(parents=True)
    (target / "roles" / "principal.yaml").write_text("stale\n")
    distro_main(
        ["install", "starter-firm", "--into", str(target), "--dry-run"]
    )
    out = capsys.readouterr().out
    assert "CONFLICT" in out
    # The pre-existing file is untouched (dry-run wrote nothing).
    assert (target / "roles" / "principal.yaml").read_text() == "stale\n"
    # No receipt directory was created.
    assert not (target / ".cognitive-firm").exists()


def test_dry_run_unknown_package_returns_2(tmp_path, capsys):
    rc = distro_main(
        ["install", "no-such-pkg", "--into", str(tmp_path / "o"), "--dry-run"]
    )
    assert rc == 2


def test_install_without_dry_run_still_writes(tmp_path):
    # Regression: --dry-run defaults off; a normal install still works.
    target = tmp_path / "real-org"
    assert distro_main(["install", "starter-firm", "--into", str(target)]) == 0
    assert (target / "roles" / "principal.yaml").is_file()


# --- the package template ---------------------------------------------------

def test_template_directory_exists_and_is_structured():
    assert (TEMPLATE / "package.yaml").is_file()
    assert (TEMPLATE / "README.md").is_file()
    assert (TEMPLATE / "files").is_dir()


def test_template_lints_clean():
    # An author who copies the template gets a package that lints clean.
    assert distro_main(["lint", str(TEMPLATE)]) == 0


def test_template_is_not_under_distro_registry():
    # The template must not be indexed as a registry package (it would be a
    # deliberately incomplete one). It lives under docs/, not distro/.
    assert TEMPLATE.is_relative_to(REPO_ROOT / "docs")
    assert not TEMPLATE.is_relative_to(REGISTRY)


def test_registry_list_unaffected_by_template(capsys):
    # `list` over the bundled registry still works and shows starter-firm.
    assert distro_main(["list"]) == 0
    assert "starter-firm" in capsys.readouterr().out
