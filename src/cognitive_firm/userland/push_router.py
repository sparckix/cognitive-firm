"""L1 — the userland push router.

The attention router (``attention_router.py``) classifies and routes signals,
but classification alone never reaches a human. This module is the *push* side
of the attention layer: it takes the routed feed and pages a human for the
signals that genuinely cannot wait.

Pace-layer policy (H2A pace model, see ``signal_classes.py``):

  * ``FAST``    — pushed. The firm interrupts the human now.
  * ``WORKING`` — not pushed. Pull-visible in the needs-me / work-inbox feed.
  * ``SLOW``    — not pushed. Pull-visible only.

Only fast-layer signals page. Working/slow signals are surfaced for the human
to pull when they look — this is deliberate: the H2A "no nagging" non-goal
forbids re-pinging things the human will see anyway when they next check in.

The push is best-effort and stateless. Each fast-layer signal that names a
target participant produces exactly one push (one ``NotificationIntent``) with
the signal's headline as the message. A signal with no resolvable target
participant (``target_actor_id is None``) is unroutable and skipped — the
attention router already surfaces such signals; pushing them to nobody would be
a no-op at best.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from cognitive_firm.notifications.channels import (
    NotificationIntent,
    send_notification,
)
from cognitive_firm.userland import signal_classes as sc
from cognitive_firm.userland.attention_router import RoutedSignal


# The notification ``priority`` used for each routed urgency. Fast-layer
# signals are the only ones that reach here, so all of these are attention-
# grabbing; ``blocking_now`` gets the strongest marker.
_PRIORITY_BY_URGENCY: dict[str, str] = {
    sc.BLOCKING_NOW: "urgent",
    sc.APPROVAL_PENDING: "high",
    sc.INFO: "default",
}

# The signal callable contract: takes a NotificationIntent, returns delivered?
SendCallable = Callable[[NotificationIntent], bool]


@dataclass(frozen=True)
class PushResult:
    """Outcome of one attempted push for a single routed signal."""

    signal_id: str
    target_actor_id: str
    delivered: bool


def _intent_for(signal: RoutedSignal) -> NotificationIntent:
    """Build the NotificationIntent for one fast-layer routed signal.

    The headline is the message verbatim — L1 does not re-summarize; the
    adapter that produced the signal already wrote a human-facing headline.
    """
    priority = _PRIORITY_BY_URGENCY.get(signal.urgency, "high")
    return NotificationIntent(
        title=f"[{signal.signal_class}] action: {signal.primary_action}",
        message=signal.headline,
        priority=priority,
        tags=(signal.signal_class, signal.pace_layer),
    )


def fast_layer_signals(
    routed: Iterable[RoutedSignal],
) -> list[RoutedSignal]:
    """The pushable subset: fast-pace signals that name a target participant.

    Working/slow signals are pull-visible only and are excluded here; a
    fast-layer signal with no resolvable ``target_actor_id`` is unroutable and
    cannot be pushed to anyone, so it is excluded too.
    """
    return [
        r
        for r in routed
        if r.pace_layer == sc.FAST and r.target_actor_id is not None
    ]


def push_routed_signals(
    routed: Iterable[RoutedSignal],
    *,
    send: SendCallable | None = None,
) -> list[PushResult]:
    """Push the fast-pace-layer routed signals to their target participants.

    For every fast-layer signal that names a target participant, send one
    notification — the signal's headline as the message — to that participant.
    Working- and slow-layer signals are never pushed (pull-visible only), which
    keeps L1 from nagging the human about things they will see when they next
    look. Returns one ``PushResult`` per attempted push, in input order.

    ``send`` is injectable for testing: it defaults to the real notification
    channel (``notifications.channels.send_notification``); a test can pass a
    stub to record which intents were emitted. Delivery failures are recorded
    (``delivered=False``) but never raised — the kernel logs remain the
    authoritative record; a missed push must not break the firm's tick.
    """
    deliver = send if send is not None else (lambda intent: send_notification(intent))
    results: list[PushResult] = []
    for signal in fast_layer_signals(routed):
        intent = _intent_for(signal)
        try:
            delivered = bool(deliver(intent))
        except Exception:  # noqa: BLE001 — a carrier failure must not break L1
            delivered = False
        results.append(
            PushResult(
                signal_id=signal.signal_id,
                target_actor_id=str(signal.target_actor_id),
                delivered=delivered,
            )
        )
    return results
