"""Tests for distribution-layer rollback, uninstall, and upgrade."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cognitive_firm.distribution import (
    gitops,
    install,
    load_manifest,
    rollback,
    upgrade,
)
from cognitive_firm.distribution.cli import main as distro_main

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTER = REPO_ROOT / "distro" / "starter-firm"


def _events(target: Path) -> list[dict]:
    log = target / ".cognitive-firm" / "distribution-events.jsonl"
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def _seeded_repo(path: Path) -> str:
    """A git repo with one pre-existing commit; returns that commit sha."""
    path.mkdir(parents=True, exist_ok=True)
    gitops.init_repo(path)
    (path / "seed.txt").write_text("pre-existing org content\n")
    gitops.stage_all(path)
    return gitops.commit(path, "seed")


def test_install_emits_kernel_event(tmp_path):
    install(load_manifest(STARTER / "package.yaml"), STARTER, tmp_path)
    assert any(e["verb"] == "package.installed" for e in _events(tmp_path))


def test_rollback_genesis_install(tmp_path):
    install(load_manifest(STARTER / "package.yaml"), STARTER, tmp_path)
    assert (tmp_path / "roles" / "principal.yaml").exists()
    result = rollback(tmp_path, "starter-firm", reason="undo")
    assert result.mode == "clean"
    assert not (tmp_path / "roles" / "principal.yaml").exists()


def test_rollback_clean_restores_prior_state(tmp_path):
    target = tmp_path / "org"
    _seeded_repo(target)
    receipt = install(load_manifest(STARTER / "package.yaml"), STARTER, target)
    assert receipt.pre_install_ref  # there was a prior commit
    result = rollback(target, "starter-firm", reason="not needed")
    assert result.mode == "clean"
    assert not (target / "roles" / "principal.yaml").exists()
    assert (target / "seed.txt").exists()  # the prior org content is back


def test_rollback_compensating_after_the_org_runs(tmp_path):
    target = tmp_path / "org"
    _seeded_repo(target)
    install(load_manifest(STARTER / "package.yaml"), STARTER, target)
    # the org runs: a post-install commit, in a new file
    (target / "log.txt").write_text("the org did some work\n")
    gitops.stage_all(target)
    gitops.commit(target, "post-install work")

    result = rollback(target, "starter-firm", reason="bad install")
    assert result.mode == "compensating"
    assert result.rollback_commit
    assert result.affected_window is not None
    assert not (target / "roles" / "principal.yaml").exists()  # install reverted
    assert (target / "log.txt").exists()  # post-install work preserved
    assert (target / "seed.txt").exists()


def test_rollback_records_event_and_record(tmp_path):
    install(load_manifest(STARTER / "package.yaml"), STARTER, tmp_path)
    rollback(tmp_path, "starter-firm", reason="undo")
    cf = tmp_path / ".cognitive-firm"
    assert (cf / "rollback-starter-firm.json").is_file()
    assert not (cf / "install-starter-firm.json").is_file()
    assert any(e["verb"] == "package.rolled_back" for e in _events(tmp_path))


def test_rollback_missing_package(tmp_path):
    install(load_manifest(STARTER / "package.yaml"), STARTER, tmp_path)
    with pytest.raises(FileNotFoundError):
        rollback(tmp_path, "no-such-package", reason="x")


def test_upgrade_reinstalls_over_existing_org(tmp_path):
    manifest = load_manifest(STARTER / "package.yaml")
    install(manifest, STARTER, tmp_path)
    receipt = upgrade(manifest, STARTER, tmp_path)
    assert receipt.package == "starter-firm"
    assert all(f.action == "overwritten" for f in receipt.files)


def test_cli_install_then_rollback(tmp_path):
    target = tmp_path / "firm"
    assert distro_main(["install", "starter-firm", "--into", str(target)]) == 0
    assert (target / "roles" / "principal.yaml").is_file()
    assert distro_main(["rollback", "starter-firm", "--into", str(target)]) == 0
    assert not (target / "roles" / "principal.yaml").exists()
