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
from typing import Any, Callable, Iterable

from cognitive_firm.orchestration.authority_domains import (
    resolve_authority_assignment_from_org,
    resolve_authority_role_from_org,
)
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
    tenant_id: str | None = None
    project_id: str | None = None
    operating_unit_id: str | None = None
    resource_class: str | None = None
    decision_class: str | None = None


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
    authority_resolver: Callable[
        [AttentionSignal], tuple[str | None, str | None]
    ] | None = None,
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
        scoped_authority_role = authority_role_id
        scoped_authority_actor = authority_actor_id
        if authority_resolver is not None:
            scoped_authority_role, scoped_authority_actor = authority_resolver(signal)

        if signal_class == sc.WORK_INTERRUPT and signal.target_actor_id:
            target_role = signal.target_role_id
            target_actor = signal.target_actor_id
        elif signal_class == sc.WORK_INTERRUPT:
            # A work signal with no assigned human (e.g. an a2h_waiting
            # session not yet claimed) must not vanish: signals_for_actor
            # matches on target_actor_id, so a None target reaches no one.
            # Fall back to the authority — assigning unclaimed work is
            # exactly the authority's job.
            target_role = signal.target_role_id or scoped_authority_role
            target_actor = scoped_authority_actor
        else:  # governance + informational -> the authority (operator)
            target_role = scoped_authority_role
            target_actor = scoped_authority_actor
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


def authority_resolver_from_org(
    org_root: Path,
    *,
    actor_membership_log: Path | None = None,
    now: datetime | None = None,
) -> Callable[[AttentionSignal], tuple[str | None, str | None]]:
    """Build a scoped authority resolver backed by org files.

    The resolver returns ``(role_id, actor_id)`` for a normalized signal. If a
    role resolves but several active actors hold it, the first sorted actor id
    is used so routing stays deterministic. If no active actor holds the role,
    the role is still returned and the actor is ``None``.
    """

    def _resolve(signal: AttentionSignal) -> tuple[str | None, str | None]:
        try:
            resolution = resolve_authority_assignment_from_org(
                org_root,
                actor_membership_log=actor_membership_log,
                tenant_id=signal.tenant_id,
                project_id=signal.project_id,
                operating_unit_id=signal.operating_unit_id,
                resource_class=signal.resource_class,
                decision_class=signal.decision_class,
                now=now,
            )
        except (OSError, ValueError, TypeError):
            return None, None
        actor_id = resolution.actor_ids[0] if resolution.actor_ids else None
        return resolution.authority_role_id, actor_id

    return _resolve


def resolve_authority_role(
    org_root: Path,
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    operating_unit_id: str | None = None,
    resource_class: str | None = None,
    decision_class: str | None = None,
) -> str | None:
    """Resolve the authority role_id from roles and optional authority domains.

    Without ``authority_domains/authority_domains.json``, returns a role only
    when exactly one role declares ``role_class: authority``. With authority
    domains, resolves by tenant/project/operating-unit/resource/decision scope
    and falls back to a declared global domain. Ambiguity returns ``None`` so
    governance interrupts are surfaced as unroutable rather than misrouted.
    """
    try:
        return resolve_authority_role_from_org(
            org_root,
            tenant_id=tenant_id,
            project_id=project_id,
            operating_unit_id=operating_unit_id,
            resource_class=resource_class,
            decision_class=decision_class,
        )
    except (OSError, ValueError, TypeError):
        return None


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
                tenant_id=_string_or_none(data.get("tenant_id")),
                project_id=_string_or_none(data.get("project_id")),
                operating_unit_id=_string_or_none(data.get("operating_unit_id")),
                resource_class=_string_or_none(data.get("resource_class")),
                decision_class=_string_or_none(data.get("decision_class")),
            )
        )
    return signals


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
