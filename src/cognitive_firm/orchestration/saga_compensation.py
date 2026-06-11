"""GP-232 Phase C — saga compensation primitive.

WHAT THIS PRIMITIVE DOES, IN PLAIN ENGLISH:

When agent A delegates work to agent B, and B's work fails partway through,
A's earlier writes may have already happened. In single-authority trusted-
hardware (T1), git revert is a fine manual recovery. In regulated enterprise
(T2), it is fatal — some of A's writes have external side effects that git
cannot undo (e.g., a Salesforce activity record was created, an external
notification was sent, money moved).

A "saga" is the standard distributed-systems pattern for this: instead of
trying to make all writes atomic (which is impossible across independent
systems), define **compensating actions** that semantically undo each step.
When the saga fails, walk back through the chain firing each compensation.

cognitive-firm's saga primitive sits on top of the Phase A obligation
lifecycle. Phase A shipped `parent_obligation_id` so messages could form a
chain. Phase C ships the resolver: when an obligation hits a terminal
failure state (`refused` or `expired`), walk the parent chain and emit a
compensating `request` to each ancestor that is in `fulfilled` state.

The compensating request says: "you previously fulfilled obligation P; the
chain that depended on you has failed terminally; please undo your action."
The original actor decides how to compensate (the kernel does not specify the
inverse — only the original role knows what undoing its action means in
context).

ARCHITECTURE:

  obligation T (refused/expired)
    │
    │ parent_obligation_id
    ▼
  obligation P (fulfilled) ─→  compensation_request emitted to P's actor
    │
    │ parent_obligation_id
    ▼
  obligation Q (fulfilled) ─→  compensation_request emitted to Q's actor
    │
    │ ...
    └─→ etc.

A compensation_request itself carries `parent_obligation_id` pointing to T
(the failed terminal). This means compensations form their own chain, so a
compensation that itself fails can trigger further compensations of its
ancestors — but only if the principal explicitly enables that recursion via
mandate (the default is one-level compensation only, to avoid runaway saga
recursion).

PUBLIC API:

  compensate_failed_obligation(role_id, message_id) -> list[AgentMessage]
    Walk the chain rooted at message_id (which must be in refused or expired
    state); emit one compensation_request per fulfilled ancestor; return
    the list of compensation messages emitted.

  list_active_sagas() -> list[dict]
    Return every chain that has at least one compensating request in flight.
    Used by Orbit to render saga state to the principal.

DAMAGE SIGNALS:

  saga_compensation_emitted    — informational; record of a compensation chain
                                  starting.
  saga_compensation_unfulfilled — fired when a compensation_request itself
                                  fails to fulfill within its expires_utc;
                                  principal review.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cognitive_firm.orchestration.agent_channels import (
    AgentMessage,
    CHANNELS_DIR,
    _role_inbox,
    read_agent_message,
    send_agent_message,
)
from cognitive_firm.orchestration.transition_log import (
    TRANSITIONS_LOG,
    append_transition,
)


log = logging.getLogger(__name__)


# ── helpers ────────────────────────────────────────────────────────────


def _walk_parent_chain(
    role_id: str,
    starting_message_id: str,
    *,
    max_depth: int = 20,
) -> list[AgentMessage]:
    """Walk parent_obligation_id from the starting message back to the root.

    Returns the chain in order [starting, parent, grandparent, ...]. Stops
    when parent_obligation_id is None or max_depth reached. Stops also if a
    cycle is detected (defensive — chains should never be cyclic in well-
    formed sagas, but principal-edited chains might be).
    """
    chain: list[AgentMessage] = []
    seen: set[str] = set()
    current_id: Optional[str] = starting_message_id
    current_role = role_id

    while current_id and len(chain) < max_depth:
        if current_id in seen:
            log.warning(
                "saga: cycle detected at %s; truncating chain at depth %d",
                current_id, len(chain),
            )
            break
        seen.add(current_id)
        # Search every role's inbox for the message — the parent may live in
        # a different role's inbox than the child.
        msg = _find_message_anywhere(current_id)
        if msg is None:
            log.warning(
                "saga: parent message %s not found; chain truncated", current_id
            )
            break
        chain.append(msg)
        current_id = msg.parent_obligation_id
        current_role = msg.to_role  # next parent is in the next ancestor's inbox

    return chain


def _find_message_anywhere(message_id: str) -> Optional[AgentMessage]:
    """Search every role's inbox for a message_id. Used because parent
    chains cross role boundaries."""
    if not CHANNELS_DIR.exists():
        return None
    for role_dir in CHANNELS_DIR.iterdir():
        if not role_dir.is_dir():
            continue
        candidate = role_dir / "inbox" / f"{message_id}.json"
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                return AgentMessage(**data)
            except Exception:  # noqa: BLE001
                continue
    return None


# ── public API ─────────────────────────────────────────────────────────


def compensate_failed_obligation(
    *,
    role_id: str,
    message_id: str,
    reason: str = "saga compensation triggered by upstream failure",
    enforce_policy: bool = True,
) -> list[AgentMessage]:
    """Trigger saga compensation for a terminally-failed obligation.

    The starting message must be in `refused` or `expired` state. For each
    ancestor in the parent chain that is in `fulfilled` state, emit a
    compensating request to the ancestor's actor. Return the compensations.

    Raises ValueError if the starting obligation is not in a terminal-failure
    state (compensating a fulfilled or in-progress obligation makes no
    semantic sense).
    """
    # role_id is a hint; the message may live in any role's inbox.
    # First try the hinted role, then fall back to cross-role search.
    starter = read_agent_message(role_id=role_id, message_id=message_id)
    if starter is None:
        starter = _find_message_anywhere(message_id)
    if starter is None:
        raise FileNotFoundError(f"obligation message not found: {message_id}")
    if starter.obligation_state not in ("refused", "expired"):
        raise ValueError(
            f"compensation only triggers on terminal-failure obligations "
            f"(refused or expired); {message_id} is in state "
            f"{starter.obligation_state}"
        )

    chain = _walk_parent_chain(role_id, message_id)
    compensations: list[AgentMessage] = []

    # Skip the starter itself (its terminal failure is the trigger, not a
    # compensation target). Walk only ancestors.
    for ancestor in chain[1:]:
        if ancestor.obligation_state != "fulfilled":
            # Only fulfilled ancestors had real side effects to compensate.
            # An ancestor still in_progress / blocked_input doesn't yet have
            # writes the world has seen.
            continue
        body = (
            f"SAGA COMPENSATION REQUEST\n\n"
            f"You previously fulfilled obligation {ancestor.message_id} "
            f"(subject: {ancestor.subject!r}).\n\n"
            f"The downstream chain rooted at {message_id} has terminally "
            f"failed (state: {starter.obligation_state}).\n\n"
            f"Reason: {reason}\n\n"
            f"Please emit a compensating action that semantically undoes "
            f"the effect of obligation {ancestor.message_id}. The kernel "
            f"does not know what 'undo' means for your action; only you do.\n\n"
            f"If compensation is not possible (e.g., an external side effect "
            f"is irreversible), reply with kind=refusal and the kernel will "
            f"surface a saga_compensation_unfulfilled damage signal for "
            f"principal review."
        )
        comp = send_agent_message(
            from_role="manager",
            to_role=ancestor.to_role,
            kind="request",
            subject=f"compensate: {ancestor.subject}",
            body=body,
            parent_obligation_id=message_id,  # chain back to the failure
            metadata={
                "saga_compensation": True,
                "compensating_for_obligation_id": ancestor.message_id,
                "saga_root_failure_id": message_id,
            },
            enforce_policy=enforce_policy,
        )
        compensations.append(comp)

        # Audit row: distinct event class so analytics can find sagas.
        append_transition(
            event="saga.compensation_emitted",
            actor="manager",
            role_id="manager",
            surface="saga_compensation",
            subject=comp.message_id,
            causality_id=message_id,
            payload={
                "compensating_for": ancestor.message_id,
                "compensation_request_id": comp.message_id,
                "saga_root_failure": message_id,
                "ancestor_subject": ancestor.subject,
                "reason": reason,
            },
        )

    return compensations


def list_active_sagas(
    *,
    log_path: Path | None = None,
    window_hours: float = 168.0,
) -> list[dict[str, Any]]:
    """Return active sagas — chains that have a saga.compensation_emitted
    row but no corresponding fulfillment of every compensation in the
    chain. Used by Orbit to render saga state.
    """
    if log_path is None:
        log_path = TRANSITIONS_LOG
    if not log_path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue

    # Group compensation requests by saga_root_failure.
    sagas: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("event") != "saga.compensation_emitted":
            continue
        payload = row.get("payload") or {}
        root = payload.get("saga_root_failure")
        if not root:
            continue
        sagas.setdefault(root, {
            "saga_root_failure": root,
            "compensations": [],
            "started_utc": row.get("ts"),
        })
        sagas[root]["compensations"].append({
            "compensation_request_id": payload.get("compensation_request_id"),
            "compensating_for": payload.get("compensating_for"),
        })

    # Determine which sagas are still active — at least one compensation
    # request whose obligation_state is not fulfilled.
    active: list[dict[str, Any]] = []
    for root, saga in sagas.items():
        any_pending = False
        for c in saga["compensations"]:
            req_id = c.get("compensation_request_id")
            if not req_id:
                continue
            msg = _find_message_anywhere(req_id)
            if msg is None:
                continue
            if msg.obligation_state not in ("fulfilled", "refused"):
                any_pending = True
                break
        if any_pending:
            active.append(saga)
    return active


def check_compensation_freshness(
    *,
    log_path: Path | None = None,
    stale_after_hours: float = 24.0,
) -> list[dict[str, Any]]:
    """Find compensation requests whose obligation has not transitioned
    away from `pending` within `stale_after_hours`. These are the events
    that should fire `saga_compensation_unfulfilled` damage signals.
    """
    if log_path is None:
        log_path = TRANSITIONS_LOG
    cutoff = datetime.now(timezone.utc).timestamp() - stale_after_hours * 3600
    stale: list[dict[str, Any]] = []
    for saga in list_active_sagas(log_path=log_path):
        for c in saga["compensations"]:
            req_id = c.get("compensation_request_id")
            msg = _find_message_anywhere(req_id) if req_id else None
            if msg is None or msg.obligation_state != "pending":
                continue
            try:
                created = datetime.fromisoformat(msg.created_utc).timestamp()
            except Exception:  # noqa: BLE001
                continue
            if created < cutoff:
                stale.append({
                    "compensation_request_id": req_id,
                    "saga_root_failure": saga["saga_root_failure"],
                    "stale_seconds": datetime.now(timezone.utc).timestamp() - created,
                })
    return stale
