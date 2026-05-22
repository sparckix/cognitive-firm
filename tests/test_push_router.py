"""Tests for L1 — the userland push router (the push side of the attention layer)."""

from __future__ import annotations

from cognitive_firm.notifications.channels import NotificationIntent
from cognitive_firm.userland import signal_classes as sc
from cognitive_firm.userland.attention_router import (
    AttentionSignal,
    route_signals,
)
from cognitive_firm.userland.push_router import (
    PushResult,
    fast_layer_signals,
    push_routed_signals,
)


class _RecordingSend:
    """Stub send-callable: records every intent it is handed."""

    def __init__(self, *, ok: bool = True) -> None:
        self.intents: list[NotificationIntent] = []
        self._ok = ok

    def __call__(self, intent: NotificationIntent) -> bool:
        self.intents.append(intent)
        return self._ok


def _route(*signals: AttentionSignal):
    return route_signals(
        signals,
        authority_actor_id="operator-1",
        authority_role_id="authority",
    )


def _fast_gov_signal(signal_id: str = "g1") -> AttentionSignal:
    # gate_pending -> governance_interrupt, FAST pace.
    return AttentionSignal(
        signal_id=signal_id,
        kind="gate_pending",
        headline=f"Gate {signal_id}: needs a decision",
        source_ref=f"/gates/{signal_id}.json",
    )


def _fast_accountability_signal(signal_id: str = "case1") -> AttentionSignal:
    # accountability_case -> governance_interrupt, FAST; routes to the
    # authority (governance signals never name a target actor themselves).
    return AttentionSignal(
        signal_id=signal_id,
        kind="accountability_case",
        headline="Accountability case opened",
        source_ref=signal_id,
    )


def _working_signal(actor: str) -> AttentionSignal:
    # a2h_waiting -> work_interrupt, WORKING pace.
    return AttentionSignal(
        signal_id="hws_1",
        kind="a2h_waiting",
        headline="Review the draft",
        source_ref="hws_1",
        target_role_id="analyst",
        target_actor_id=actor,
    )


def _slow_signal() -> AttentionSignal:
    # damage_signal -> informational, SLOW pace.
    return AttentionSignal(
        signal_id="dmg_1",
        kind="damage_signal",
        headline="Damage detected",
        source_ref="dmg_1",
    )


def test_fast_layer_signal_is_pushed_with_headline_as_message():
    routed = _route(_fast_gov_signal("g1"))
    send = _RecordingSend()

    results = push_routed_signals(routed, send=send)

    assert len(send.intents) == 1
    assert send.intents[0].message == "Gate g1: needs a decision"
    assert results == [
        PushResult(signal_id="g1", target_actor_id="operator-1", delivered=True)
    ]


def test_working_and_slow_signals_are_not_pushed():
    routed = _route(_working_signal("analyst-7"), _slow_signal())
    send = _RecordingSend()

    results = push_routed_signals(routed, send=send)

    assert send.intents == []
    assert results == []


def test_only_fast_signals_selected_from_a_mixed_feed():
    routed = _route(
        _fast_gov_signal("g1"),
        _working_signal("analyst-7"),
        _slow_signal(),
        _fast_accountability_signal("case1"),
    )

    fast = fast_layer_signals(routed)

    assert {s.signal_id for s in fast} == {"g1", "case1"}
    assert all(s.pace_layer == sc.FAST for s in fast)


def test_one_push_per_signal_in_input_order():
    routed = _route(
        _fast_gov_signal("g1"),
        _fast_accountability_signal("case1"),
    )
    send = _RecordingSend()

    results = push_routed_signals(routed, send=send)

    assert len(send.intents) == 2
    assert [r.signal_id for r in results] == ["g1", "case1"]
    # Both are governance interrupts, so both page the authority.
    assert [r.target_actor_id for r in results] == ["operator-1", "operator-1"]


def test_fast_signal_with_no_target_participant_is_skipped():
    # A governance signal with no resolvable authority -> target_actor_id None.
    routed = route_signals([_fast_gov_signal("g1")])  # no authority given
    assert routed[0].target_actor_id is None
    send = _RecordingSend()

    results = push_routed_signals(routed, send=send)

    assert send.intents == []
    assert results == []


def test_delivery_failure_is_recorded_not_raised():
    routed = _route(_fast_gov_signal("g1"))
    send = _RecordingSend(ok=False)

    results = push_routed_signals(routed, send=send)

    assert results == [
        PushResult(signal_id="g1", target_actor_id="operator-1", delivered=False)
    ]


def test_carrier_exception_does_not_break_the_push():
    def _exploding_send(intent: NotificationIntent) -> bool:
        raise RuntimeError("carrier down")

    routed = _route(_fast_gov_signal("g1"))

    results = push_routed_signals(routed, send=_exploding_send)

    assert results == [
        PushResult(signal_id="g1", target_actor_id="operator-1", delivered=False)
    ]


def test_priority_reflects_urgency():
    # accountability_case -> blocking_now ; gate_pending -> approval_pending.
    routed = _route(
        _fast_gov_signal("g1"),
        _fast_accountability_signal("case1"),
    )
    send = _RecordingSend()

    push_routed_signals(routed, send=send)

    by_msg = {i.message: i.priority for i in send.intents}
    assert by_msg["Gate g1: needs a decision"] == "high"
    assert by_msg["Accountability case opened"] == "urgent"


def test_default_send_is_the_real_notification_channel():
    # With no signals to push the default callable is never invoked, so this
    # exercises the default-argument path without hitting the network.
    assert push_routed_signals([]) == []
