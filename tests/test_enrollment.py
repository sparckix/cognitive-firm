"""Tests for L0 — the userland enrollment layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from cognitive_firm.orchestration.actor_membership import list_actor_memberships
from cognitive_firm.userland.enrollment import EnrollmentError, enroll, preview


def _role(org_root: Path, role_id: str, body: str) -> None:
    roles = org_root / "roles"
    roles.mkdir(parents=True, exist_ok=True)
    (roles / f"{role_id}.yaml").write_text(body)


def test_preview_renders_authority_in_plain_language(tmp_path):
    _role(
        tmp_path,
        "principal",
        "role_id: principal\nrole_class: authority\n"
        "authorized_paths: ['*']\nescalates_to: []\nmandate_path: null\n",
    )
    view = preview(role_id="principal", org_root=tmp_path)
    assert view.role_class == "authority"
    assert any("write anywhere" in s for s in view.statements)
    assert any("escalate to no one" in s for s in view.statements)


def test_preview_for_a_scoped_role(tmp_path):
    _role(
        tmp_path,
        "analyst",
        "role_id: analyst\nrole_class: specialist\n"
        "authorized_paths: ['projects/']\nescalates_to: [role.lead]\n"
        "mandate_path: mandates/analyst_mandate.md\n",
    )
    view = preview(role_id="analyst", org_root=tmp_path)
    assert any("projects/" in s for s in view.statements)
    assert any("role.lead" in s for s in view.statements)


def test_preview_missing_role_raises(tmp_path):
    with pytest.raises(EnrollmentError):
        preview(role_id="ghost", org_root=tmp_path)


def test_enroll_registers_identity_and_grants_membership(tmp_path):
    identity_log = tmp_path / "identities.jsonl"
    membership_log = tmp_path / "memberships.jsonl"
    result = enroll(
        auth_subject="alice@firm.example",
        display_name="Alice",
        role_id="analyst",
        decision_right_basis="hired as the firm's analyst",
        granted_by="principal",
        identity_log=identity_log,
        membership_log=membership_log,
    )
    assert result.role_id == "analyst"
    assert result.assignment_id
    memberships = list_actor_memberships(
        actor_id=result.actor_id, log_path=membership_log
    )
    assert len(memberships) == 1
    assert memberships[0].role_id == "analyst"


def test_enroll_requires_a_decision_right_basis(tmp_path):
    with pytest.raises(EnrollmentError):
        enroll(
            auth_subject="bob@firm.example",
            display_name="Bob",
            role_id="analyst",
            decision_right_basis="",
            granted_by="principal",
            identity_log=tmp_path / "i.jsonl",
            membership_log=tmp_path / "m.jsonl",
        )
