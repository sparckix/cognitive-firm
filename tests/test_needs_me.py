"""Tests for L2 (operator face) — the needs-me presentation model."""

from __future__ import annotations

from cognitive_firm.userland import signal_classes as sc
from cognitive_firm.userland.attention_router import RoutedSignal
from cognitive_firm.userland.needs_me import build_needs_me


def _routed(
    signal_id: str, urgency: str, *, actor: str = "op", age: int = 0
) -> RoutedSignal:
    return RoutedSignal(
        signal_id=signal_id,
        signal_class=sc.GOVERNANCE_INTERRUPT,
        pace_layer=sc.FAST,
        urgency=urgency,
        target_role_id="principal",
        target_actor_id=actor,
        headline=f"{signal_id} headline",
        primary_action="approve",
        source_ref=f"ref/{signal_id}",
        age_seconds=age,
    )


def test_empty_queue():
    view = build_needs_me(actor_id="op", signals=[])
    assert view.total_count == 0
    assert view.groups == ()
    assert "Nothing needs you" in view.waiting_line


def test_groups_are_ordered_by_urgency():
    view = build_needs_me(
        actor_id="op",
        signals=[
            _routed("i1", sc.INFO),
            _routed("b1", sc.BLOCKING_NOW),
            _routed("a1", sc.APPROVAL_PENDING),
        ],
    )
    assert [g.urgency for g in view.groups] == [
        sc.BLOCKING_NOW,
        sc.APPROVAL_PENDING,
        sc.INFO,
    ]
    assert view.total_count == 3
    assert view.blocking_count == 1
    assert "3 items, 1 blocking" in view.waiting_line


def test_oldest_first_within_a_group():
    view = build_needs_me(
        actor_id="op",
        signals=[
            _routed("new", sc.BLOCKING_NOW, age=10),
            _routed("old", sc.BLOCKING_NOW, age=9999),
        ],
    )
    assert [i.signal_id for i in view.groups[0].items] == ["old", "new"]


def test_filters_to_the_actor():
    view = build_needs_me(
        actor_id="op",
        signals=[
            _routed("mine", sc.BLOCKING_NOW, actor="op"),
            _routed("theirs", sc.BLOCKING_NOW, actor="alice"),
        ],
    )
    assert view.total_count == 1
    assert view.groups[0].items[0].signal_id == "mine"


def test_singular_phrasing_for_one_item():
    view = build_needs_me(
        actor_id="op", signals=[_routed("b1", sc.BLOCKING_NOW)]
    )
    assert "1 item," in view.waiting_line  # singular — no trailing 's'


def test_as_dict_carries_the_structure():
    view = build_needs_me(
        actor_id="op", signals=[_routed("b1", sc.BLOCKING_NOW)]
    )
    payload = view.as_dict()
    assert payload["total_count"] == 1
    assert payload["groups"][0]["items"][0]["signal_id"] == "b1"
    assert payload["groups"][0]["items"][0]["primary_action"] == "approve"
