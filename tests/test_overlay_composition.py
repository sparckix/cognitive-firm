"""Tests for O3-P2 — overlay composition (add / replace / patch)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cognitive_firm.distribution import (
    InstallError,
    ManifestError,
    install,
    load_manifest,
)
from cognitive_firm.distribution.installer import _merge_patch

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTER = REPO_ROOT / "distro" / "starter-firm"


# --- RFC 7386 JSON Merge Patch ----------------------------------------------

def test_merge_patch_adds_and_overrides():
    assert _merge_patch({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
    assert _merge_patch({"a": 1}, {"a": 9}) == {"a": 9}


def test_merge_patch_null_deletes_a_key():
    assert _merge_patch({"a": 1, "b": 2}, {"b": None}) == {"a": 1}


def test_merge_patch_merges_nested_objects():
    assert _merge_patch({"x": {"a": 1}}, {"x": {"b": 2}}) == {
        "x": {"a": 1, "b": 2}
    }


def test_merge_patch_non_object_replaces():
    assert _merge_patch({"a": 1}, [1, 2]) == [1, 2]


# --- manifest op validation -------------------------------------------------

def _overlay(
    root: Path, name: str, *, source_name: str, source_body: str,
    dest: str, op: str,
) -> Path:
    pkg = root / name
    (pkg / "files").mkdir(parents=True)
    (pkg / "files" / source_name).write_text(source_body)
    (pkg / "package.yaml").write_text(
        f"schema_version: 1\nname: {name}\nversion: 0.1.0\nkind: overlay\n"
        f"description: an O3-P2 overlay composition test package\n"
        f"components:\n"
        f"  - source: {source_name}\n    dest: {dest}\n    op: {op}\n"
    )
    return pkg


def test_validate_rejects_an_unknown_op(tmp_path):
    pkg = _overlay(
        tmp_path, "bad", source_name="f.txt", source_body="x",
        dest="notes.txt", op="bogus",
    )
    with pytest.raises(ManifestError):
        load_manifest(pkg / "package.yaml")


# --- replace ----------------------------------------------------------------

def test_replace_overwrites_an_existing_file(tmp_path):
    target = tmp_path / "org"
    install(load_manifest(STARTER / "package.yaml"), STARTER, target)
    overlay = _overlay(
        tmp_path, "prefs-overlay", source_name="prefs.yaml",
        source_body=(
            "principal_id: replaced_by_overlay\nnotification_channel: null\n"
            "default_escalation: principal\nreview_cadence: weekly\n"
        ),
        dest="preferences/principal.yaml", op="replace",
    )
    install(load_manifest(overlay / "package.yaml"), overlay, target)
    prefs = (target / "preferences" / "principal.yaml").read_text()
    assert "replaced_by_overlay" in prefs


# --- patch ------------------------------------------------------------------

def test_patch_merges_into_an_existing_file(tmp_path):
    target = tmp_path / "org"
    install(load_manifest(STARTER / "package.yaml"), STARTER, target)
    overlay = _overlay(
        tmp_path, "prefs-patch", source_name="patch.yaml",
        source_body="review_cadence: daily\n_o3p2_marker: true\n",
        dest="preferences/principal.yaml", op="patch",
    )
    install(load_manifest(overlay / "package.yaml"), overlay, target)
    after = yaml.safe_load(
        (target / "preferences" / "principal.yaml").read_text()
    )
    assert after["_o3p2_marker"] is True
    assert after["review_cadence"] == "daily"
    assert "principal_id" in after  # an original key is preserved


def test_patch_on_a_missing_target_fails(tmp_path):
    target = tmp_path / "org"
    install(load_manifest(STARTER / "package.yaml"), STARTER, target)
    overlay = _overlay(
        tmp_path, "ghost-patch", source_name="p.json",
        source_body=json.dumps({"x": 1}),
        dest="nonexistent/file.json", op="patch",
    )
    with pytest.raises(InstallError):
        install(load_manifest(overlay / "package.yaml"), overlay, target)
