"""Tests for O3-P1 — the authority-diff."""

from __future__ import annotations

from pathlib import Path

import yaml

from cognitive_firm.distribution.authority_diff import (
    EXPANDS,
    NARROWS,
    UNKNOWN,
    compute_authority_diff,
)


def _role(
    org: Path,
    role_id: str,
    *,
    role_class: str = "specialist",
    paths: list[str] | None = None,
    escalates_to: list[str] | None = None,
    forbidden_paths: list[str] | None = None,
    delegates_to: list[str] | None = None,
    budget: dict | None = None,
) -> None:
    roles = org / "roles"
    roles.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "role_id": role_id,
        "role_class": role_class,
        "authorized_paths": paths or [],
        "escalates_to": escalates_to or [],
    }
    if forbidden_paths is not None:
        data["forbidden_paths"] = forbidden_paths
    if delegates_to is not None:
        data["delegates_to"] = delegates_to
    if budget is not None:
        data["budget"] = budget
    (roles / f"{role_id}.yaml").write_text(yaml.safe_dump(data))


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


# --- F-6: forbidden_paths is authority-bearing -------------------------------


def test_emptying_forbidden_paths_expands(tmp_path):
    # Removing a forbidden-path entry lets the role write where it could not:
    # that is an expansion. (Polarity is inverted vs authorized_paths.)
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "agent", paths=["*"], forbidden_paths=["secrets/"])
    _role(after, "agent", paths=["*"], forbidden_paths=[])
    diff = compute_authority_diff(before, after)
    assert diff.expands_authority
    assert any(
        line.classification == EXPANDS and "forbidden" in line.text.lower()
        for line in diff.lines
    )


def test_adding_forbidden_paths_narrows(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "agent", paths=["*"], forbidden_paths=[])
    _role(after, "agent", paths=["*"], forbidden_paths=["secrets/"])
    diff = compute_authority_diff(before, after)
    assert not diff.expands_authority
    assert any(line.classification == NARROWS for line in diff.lines)


# --- F-6: budget is authority-bearing ----------------------------------------


def test_raising_budget_cap_expands(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "agent", paths=["x/"], budget={"daily_cap_usd": 10.0})
    _role(after, "agent", paths=["x/"], budget={"daily_cap_usd": 50.0})
    diff = compute_authority_diff(before, after)
    assert diff.expands_authority
    assert any(
        line.classification == EXPANDS and "budget" in line.text.lower()
        for line in diff.lines
    )


def test_lowering_budget_cap_narrows(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "agent", paths=["x/"], budget={"daily_cap_usd": 50.0})
    _role(after, "agent", paths=["x/"], budget={"daily_cap_usd": 10.0})
    diff = compute_authority_diff(before, after)
    assert not diff.expands_authority
    assert any(line.classification == NARROWS for line in diff.lines)


# --- F-6: delegates_to is authority-bearing ----------------------------------


def test_adding_a_delegation_edge_expands(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "agent", paths=["x/"], delegates_to=[])
    _role(after, "agent", paths=["x/"], delegates_to=["role.helper"])
    diff = compute_authority_diff(before, after)
    assert diff.expands_authority
    assert any(
        line.classification == EXPANDS and "deleg" in line.text.lower()
        for line in diff.lines
    )


def test_removing_a_delegation_edge_narrows(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "agent", paths=["x/"], delegates_to=["role.helper"])
    _role(after, "agent", paths=["x/"], delegates_to=[])
    diff = compute_authority_diff(before, after)
    assert not diff.expands_authority
    assert any(line.classification == NARROWS for line in diff.lines)


# --- F-7: an add-and-remove path change surfaces its expansion component -----


def test_add_and_remove_path_change_surfaces_expansion(tmp_path):
    # A set that both adds and removes paths cannot be called a pure expand
    # or narrow, but the added paths ARE an expansion. The result must remain
    # gate-blocking (UNKNOWN is fail-closed) AND honestly name the expansion.
    before, after = tmp_path / "b", tmp_path / "a"
    _role(before, "agent", paths=["tickets/"])
    _role(after, "agent", paths=["billing/"])  # drops tickets/, adds billing/
    diff = compute_authority_diff(before, after)
    assert diff.expands_authority  # fail-closed preserved
    line = next(ln for ln in diff.lines if ln.subject == "role:agent")
    assert line.classification == UNKNOWN
    # the rendered text must name the newly added path as an expansion,
    # not merely call the change uninterpretable
    assert "billing/" in line.text
    lowered = line.text.lower()
    assert "add" in lowered or "expand" in lowered or "gains" in lowered
