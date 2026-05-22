"""Tests for L3 — kernel-side surface write policy (closes O-Q4)."""

from __future__ import annotations

from cognitive_firm.userland.surface_policy import surface_write_allowed

_MODES = {"orbit": "projection_only", "cli": "read_write"}


def test_reads_are_always_allowed():
    decision = surface_write_allowed(
        surface="orbit", is_mutation=False, modes=_MODES
    )
    assert decision.allowed


def test_projection_only_surface_cannot_mutate():
    decision = surface_write_allowed(
        surface="orbit", is_mutation=True, modes=_MODES
    )
    assert not decision.allowed
    assert "projection-only" in decision.reason


def test_read_write_surface_may_mutate():
    decision = surface_write_allowed(
        surface="cli", is_mutation=True, modes=_MODES
    )
    assert decision.allowed


def test_unknown_surface_defaults_to_write_allowed():
    # the policy denies only what is explicitly restricted
    decision = surface_write_allowed(
        surface="some_new_surface", is_mutation=True, modes=_MODES
    )
    assert decision.allowed


def test_no_modes_means_all_writes_allowed():
    decision = surface_write_allowed(
        surface="orbit", is_mutation=True, modes=None
    )
    assert decision.allowed
