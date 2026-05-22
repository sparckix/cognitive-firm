"""L2 (operator face) — the ``needs-me`` presentation model.

An operator's queue is not a raw list (spec §4.5 / review F-11). ``needs-me``
takes the routed signals for one participant, groups them by urgency, orders
each group oldest-first (the most overdue surfaces first), and fronts the whole
thing with one plain-language waiting line. Every item carries exactly one
primary action.

Like the rest of the userland this is a pure function — it holds no state and
derives entirely from L1's :class:`RoutedSignal` output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from cognitive_firm.userland import signal_classes as sc
from cognitive_firm.userland.attention_router import (
    RoutedSignal,
    signals_for_actor,
)

# Urgency display order — most pressing first.
_URGENCY_ORDER = (sc.BLOCKING_NOW, sc.APPROVAL_PENDING, sc.INFO)
_URGENCY_LABEL = {
    sc.BLOCKING_NOW: "blocking now",
    sc.APPROVAL_PENDING: "waiting for your approval",
    sc.INFO: "for your awareness",
}


@dataclass(frozen=True)
class NeedsMeItem:
    """One actionable line in the operator's queue."""

    signal_id: str
    headline: str
    primary_action: str
    urgency: str
    age_seconds: int
    source_ref: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "headline": self.headline,
            "primary_action": self.primary_action,
            "urgency": self.urgency,
            "age_seconds": self.age_seconds,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True)
class NeedsMeGroup:
    """One urgency band of the queue."""

    urgency: str
    label: str
    items: tuple[NeedsMeItem, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "urgency": self.urgency,
            "label": self.label,
            "items": [item.as_dict() for item in self.items],
        }


@dataclass(frozen=True)
class NeedsMeView:
    """The operator's whole ``needs-me`` view for one participant."""

    actor_id: str
    waiting_line: str
    blocking_count: int
    total_count: int
    groups: tuple[NeedsMeGroup, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "waiting_line": self.waiting_line,
            "blocking_count": self.blocking_count,
            "total_count": self.total_count,
            "groups": [group.as_dict() for group in self.groups],
        }


def build_needs_me(
    *, actor_id: str, signals: Iterable[RoutedSignal]
) -> NeedsMeView:
    """Build the ``needs-me`` view for ``actor_id`` from routed signals."""
    mine = signals_for_actor(signals, actor_id)

    buckets: dict[str, list[NeedsMeItem]] = {u: [] for u in _URGENCY_ORDER}
    for signal in mine:
        item = NeedsMeItem(
            signal_id=signal.signal_id,
            headline=signal.headline,
            primary_action=signal.primary_action,
            urgency=signal.urgency,
            age_seconds=signal.age_seconds,
            source_ref=signal.source_ref,
        )
        # An off-taxonomy urgency would otherwise vanish; bucket it as info.
        buckets.setdefault(signal.urgency, buckets[sc.INFO]).append(item)

    groups: list[NeedsMeGroup] = []
    for urgency in _URGENCY_ORDER:
        items = buckets.get(urgency) or []
        if not items:
            continue
        items.sort(key=lambda i: i.age_seconds, reverse=True)  # oldest first
        groups.append(
            NeedsMeGroup(urgency, _URGENCY_LABEL[urgency], tuple(items))
        )

    total = len(mine)
    blocking = len(buckets[sc.BLOCKING_NOW])
    if total == 0:
        waiting_line = "Nothing needs you right now."
    else:
        plural = "s" if total != 1 else ""
        waiting_line = (
            f"The firm is waiting on you: {total} item{plural}, "
            f"{blocking} blocking."
        )
    return NeedsMeView(
        actor_id=actor_id,
        waiting_line=waiting_line,
        blocking_count=blocking,
        total_count=total,
        groups=tuple(groups),
    )
