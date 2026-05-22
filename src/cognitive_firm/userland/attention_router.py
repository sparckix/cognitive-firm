"""L1 — the userland attention router.

The firm runs autonomously and continuously; it constantly produces moments
that need a *specific* human who is not watching. The attention router is the
participant-routed channel: it takes the raw signals the firm has produced,
classifies each, and resolves which participant it must reach.

The router (`route_signals`) is a pure function over *normalized* signals.
Adapters — one per source — turn raw kernel signals into `AttentionSignal`s;
the router never parses raw kernel JSON. The userland owns no state and reaches
into no kernel internals. See the O1 design, §1.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from cognitive_firm.userland import signal_classes as sc


@dataclass(frozen=True)
class AttentionSignal:
    """A normalized thing that may need a human's attention, before routing.

    One adapter per source (pending gates, A2H sessions, ...) normalizes a raw
    kernel signal into this shape. Work signals carry the participant they
    name; governance signals leave the target fields empty — the router fills
    them with the authority.
    """

    signal_id: str
    kind: str  # a key of _CLASSIFICATION
    headline: str
    source_ref: str
    created_at_utc: str | None = None
    target_role_id: str | None = None
    target_actor_id: str | None = None


@dataclass(frozen=True)
class RoutedSignal:
    """A classified, participant-routed signal — the L1 output."""

    signal_id: str
    signal_class: str
    pace_layer: str
    urgency: str
    target_role_id: str | None
    target_actor_id: str | None
    headline: str
    primary_action: str
    source_ref: str
    age_seconds: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_class": self.signal_class,
            "pace_layer": self.pace_layer,
            "urgency": self.urgency,
            "target_role_id": self.target_role_id,
            "target_actor_id": self.target_actor_id,
            "headline": self.headline,
            "primary_action": self.primary_action,
            "source_ref": self.source_ref,
            "age_seconds": self.age_seconds,
        }


# kind -> (signal_class, urgency, primary_action, pace_layer).
_CLASSIFICATION: dict[str, tuple[str, str, str, str]] = {
    "gate_pending": (
        sc.GOVERNANCE_INTERRUPT, sc.APPROVAL_PENDING, "approve", sc.FAST,
    ),
    "governance_change": (
        sc.GOVERNANCE_INTERRUPT, sc.APPROVAL_PENDING, "review", sc.SLOW,
    ),
    "accountability_case": (
        sc.GOVERNANCE_INTERRUPT, sc.BLOCKING_NOW, "review", sc.FAST,
    ),
    "blocked_obligation": (
        sc.GOVERNANCE_INTERRUPT, sc.BLOCKING_NOW, "review", sc.FAST,
    ),
    "a2h_waiting": (
        sc.WORK_INTERRUPT, sc.BLOCKING_NOW, "claim", sc.WORKING,
    ),
    "damage_signal": (
        sc.INFORMATIONAL, sc.INFO, "none", sc.SLOW,
    ),
}
# An unrecognized signal kind is surfaced, never paged — fail safe, not silent.
_UNKNOWN = (sc.INFORMATIONAL, sc.INFO, "none", sc.SLOW)


def _age_seconds(created_at_utc: str | None, now: datetime) -> int:
    if not created_at_utc:
        return 0
    try:
        created = datetime.fromisoformat(created_at_utc)
    except ValueError:
        return 0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0, int((now - created).total_seconds()))


def route_signals(
    signals: Iterable[AttentionSignal],
    *,
    authority_actor_id: str | None = None,
    authority_role_id: str | None = None,
    now: datetime | None = None,
) -> list[RoutedSignal]:
    """Classify and route normalized signals into ``RoutedSignal``s.

    ``governance_interrupt`` and ``informational`` signals route to the
    authority (the operator); ``work_interrupt`` signals route to the
    member-human the signal names. A ``work_interrupt`` with no named human
    (unassigned work) also falls back to the authority — unassigned work is
    exactly what the authority must see to assign it. A governance signal with
    no resolvable authority is returned with ``target_actor_id=None`` —
    unroutable, surfaced rather than silently dropped.
    """
    now = now or datetime.now(timezone.utc)
    routed: list[RoutedSignal] = []
    for signal in signals:
        signal_class, urgency, action, pace = _CLASSIFICATION.get(
            signal.kind, _UNKNOWN
        )
        if signal_class == sc.WORK_INTERRUPT and signal.target_actor_id:
            target_role = signal.target_role_id
            target_actor = signal.target_actor_id
        elif signal_class == sc.WORK_INTERRUPT:
            # A work signal with no assigned human (e.g. an a2h_waiting
            # session not yet claimed) must not vanish: signals_for_actor
            # matches on target_actor_id, so a None target reaches no one.
            # Fall back to the authority — assigning unclaimed work is
            # exactly the authority's job.
            target_role = signal.target_role_id or authority_role_id
            target_actor = authority_actor_id
        else:  # governance + informational -> the authority (operator)
            target_role = authority_role_id
            target_actor = authority_actor_id
        routed.append(
            RoutedSignal(
                signal_id=signal.signal_id,
                signal_class=signal_class,
                pace_layer=pace,
                urgency=urgency,
                target_role_id=target_role,
                target_actor_id=target_actor,
                headline=signal.headline,
                primary_action=action,
                source_ref=signal.source_ref,
                age_seconds=_age_seconds(signal.created_at_utc, now),
            )
        )
    return routed


def signals_for_actor(
    routed: Iterable[RoutedSignal], actor_id: str
) -> list[RoutedSignal]:
    """Filter routed signals to one participant — the per-actor feed."""
    return [r for r in routed if r.target_actor_id == actor_id]


def resolve_authority_role(org_root: Path) -> str | None:
    """The org's single authority role_id, read from ``roles/*.yaml``.

    Returns None unless exactly one role declares ``role_class: authority`` —
    the same condition ``boot_check`` requires for a governable org, so a
    bootable org always has a resolvable authority.
    """
    roles_dir = Path(org_root) / "roles"
    if not roles_dir.is_dir():
        return None
    authorities: list[str] = []
    for role_file in sorted(roles_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(role_file.read_text())
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and data.get("role_class") == "authority":
            role_id = data.get("role_id")
            if role_id:
                authorities.append(str(role_id))
    return authorities[0] if len(authorities) == 1 else None


def pending_gate_signals(gates_dir: Path) -> list[AttentionSignal]:
    """Adapter: pending gate escalations -> ``AttentionSignal``s.

    Gates live as JSON files under ``<workspace>/gates/pending`` and are not
    part of ``build_org_surface`` (O1 design §6.1), so the router scans the
    directory directly. A malformed gate file is skipped, not fatal.
    """
    gates_dir = Path(gates_dir)
    if not gates_dir.is_dir():
        return []
    signals: list[AttentionSignal] = []
    for gate_file in sorted(gates_dir.glob("*.json")):
        try:
            data = json.loads(gate_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        goal = data.get("goal_name") or data.get("goal_slug") or "a goal"
        description = data.get("gate_description") or "needs a decision"
        signals.append(
            AttentionSignal(
                signal_id=gate_file.stem,
                kind="gate_pending",
                headline=f"Gate: {goal} — {description}",
                source_ref=str(gate_file),
                created_at_utc=data.get("timestamp_utc"),
            )
        )
    return signals
