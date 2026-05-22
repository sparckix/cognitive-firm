"""Tests for O3-P1 — the authority-diff."""

from __future__ import annotations

from pathlib import Path

import yaml

from cognitive_firm.distribution.authority_diff import (
    EXPANDS,
    NARROWS,
    compute_authority_diff,
)


def _role(
    org: Path,
    role_id: str,
    *,
    role_class: str = "specialist",
    paths: list[str] | None = None,
    escalates_to: list[str] | None = None,
) -> None:
    roles = org / "roles"
    roles.mkdir(parents=True, exist_ok=True)
    (roles / f"{role_id}.yaml").write_text(
        yaml.safe_dump(
            {
                "role_id": role_id,
                "role_class": role_class,
                "authorized_paths": paths or [],
                "escalates_to": escalates_to or [],
            }
        )
    )


def test_a_new_role_with_write_access_expands_authority(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "principal", role_class="authority", paths=["*"])
    _role(after, "principal", role_class="authority", paths=["*"])
    _role(after, "clerk", paths=["invoices/"])
    diff = compute_authority_diff(before, after)
    assert diff.expands_authority
    assert any(
        "clerk" in line.text and line.classification == EXPANDS
        for line in diff.lines
    )


def test_widened_write_scope_expands(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "agent", paths=["tickets/"])
    _role(after, "agent", paths=["*"])
    diff = compute_authority_diff(before, after)
    assert diff.expands_authority


def test_narrowed_write_scope_narrows(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "agent", paths=["*"])
    _role(after, "agent", paths=["tickets/"])
    diff = compute_authority_diff(before, after)
    assert not diff.expands_authority
    assert any(line.classification == NARROWS for line in diff.lines)


def test_a_removed_role_narrows(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "principal", paths=["*"])
    _role(before, "temp", paths=["scratch/"])
    _role(after, "principal", paths=["*"])
    diff = compute_authority_diff(before, after)
    assert any(
        "temp" in line.text and line.classification == NARROWS
        for line in diff.lines
    )


def test_role_class_promoted_to_authority_expands(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "agent", role_class="specialist", paths=["x/"])
    _role(after, "agent", role_class="authority", paths=["x/"])
    diff = compute_authority_diff(before, after)
    assert diff.expands_authority


def test_no_change_is_an_empty_diff(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "agent", paths=["x/"])
    _role(after, "agent", paths=["x/"])
    diff = compute_authority_diff(before, after)
    assert diff.is_empty
    assert not diff.expands_authority
    assert "no change" in diff.render().lower()


def test_render_groups_changes_by_classification(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "agent", paths=["*"])
    _role(after, "agent", paths=["tickets/"])  # narrows
    _role(after, "clerk", paths=["invoices/"])  # expands
    rendered = compute_authority_diff(before, after).render()
    assert "Expands authority:" in rendered
    assert "Narrows authority:" in rendered
