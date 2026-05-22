"""Tests for L4 — the userland vocabulary spine."""

from __future__ import annotations

import pytest

from cognitive_firm.userland.vocabulary import (
    UnknownTerm,
    all_terms,
    render,
    schema_version,
    term,
)


def test_term_returns_a_defined_entry():
    gate = term("gate")
    assert gate.label == "decision point"
    assert gate.definition
    assert gate.governance_note


def test_unknown_term_raises():
    with pytest.raises(UnknownTerm):
        term("not_a_real_kernel_concept")


def test_render_authorized_paths_worked_case():
    # the spec §1.4 worked case
    assert render("authorized_paths", ["*"]) == (
        "this role can write anywhere in the organization"
    )


def test_render_authorized_paths_scoped():
    assert "projects/" in render("authorized_paths", ["projects/"])


def test_render_authorized_paths_read_only():
    assert "read-only" in render("authorized_paths", [])


def test_render_generic_uses_the_label():
    assert render("role", "lead") == "role: lead"


def test_render_rejects_an_unknown_key():
    with pytest.raises(UnknownTerm):
        render("mystery_field", "x")


def test_all_terms_is_non_empty_and_key_sorted():
    terms = all_terms()
    assert len(terms) >= 10
    assert [t.key for t in terms] == sorted(t.key for t in terms)


def test_schema_version():
    assert schema_version() == 1
