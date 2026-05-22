"""L2 (member-human face) — the work inbox.

A member-human holds a role *inside* the firm and does bounded work alongside
the agent role-offices. Their userland is not the operator's escalation pager
(spec §4.1) — it is a work environment: a queue of bounded tasks with named
deliverables and a typed way to return a result.

This is a thin projection over the A2H human-work primitive
(`orchestration/human_work.py`): `list_inbox` is a read model, and `claim` /
`submit` are the member-human verbs — each a guarded call to the kernel's
`update_human_work_state` lifecycle, so the kernel's transition invariants and
receipt rules hold unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cognitive_firm.orchestration.human_work import (
    A2H_WAITING_ON_HUMAN_STATES,
    HumanWorkSession,
    list_human_work_sessions,
    update_human_work_state,
)


@dataclass(frozen=True)
class WorkInboxItem:
    """One task in a member-human's inbox — governance-interpretation fields
    only, never raw JSONL."""

    session_id: str
    objective: str
    human_deliverable: str | None
    work_mode: str
    bottleneck_class: str
    state: str
    deadline_utc: str | None
    receipt_required: bool
    receipt_type: str
    requested_by: str

    @classmethod
    def from_session(cls, session: HumanWorkSession) -> "WorkInboxItem":
        return cls(
            session_id=session.session_id,
            objective=session.objective,
            human_deliverable=session.human_deliverable,
            work_mode=session.work_mode,
            bottleneck_class=session.bottleneck_class,
            state=session.state,
            deadline_utc=session.deadline_utc,
            receipt_required=session.receipt_required,
            receipt_type=session.receipt_type,
            requested_by=session.requested_by,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "objective": self.objective,
            "human_deliverable": self.human_deliverable,
            "work_mode": self.work_mode,
            "bottleneck_class": self.bottleneck_class,
            "state": self.state,
            "deadline_utc": self.deadline_utc,
            "receipt_required": self.receipt_required,
            "receipt_type": self.receipt_type,
            "requested_by": self.requested_by,
        }


def _inbox_sort_key(session: HumanWorkSession) -> tuple[int, str, str]:
    # Blocked work first (the firm is stuck on it), then soonest deadline.
    blocked_first = 0 if session.state == "blocked" else 1
    deadline = session.deadline_utc or "9999-12-31"
    return (blocked_first, deadline, session.created_at_utc)


def _require_own_session(
    session_id: str, actor_id: str, log_path: Any
) -> None:
    """A member-human may only act on work assigned to them."""
    mine = list_human_work_sessions(human_actor=actor_id, log_path=log_path)
    if not any(s.session_id == session_id for s in mine):
        raise ValueError(
            f"session {session_id} is not in {actor_id}'s work inbox"
        )


def list_inbox(*, actor_id: str, log_path: Any = None) -> list[WorkInboxItem]:
    """The member-human's open work — assigned to them, not yet terminal,
    blocked-first then soonest-deadline."""
    sessions = list_human_work_sessions(human_actor=actor_id, log_path=log_path)
    active = [s for s in sessions if s.state in A2H_WAITING_ON_HUMAN_STATES]
    active.sort(key=_inbox_sort_key)
    return [WorkInboxItem.from_session(s) for s in active]


def claim(
    *, session_id: str, actor_id: str, log_path: Any = None
) -> WorkInboxItem:
    """Take a task and start on it — moves the session to ``in_progress``.

    Raises ``ValueError`` if the task is not in the actor's inbox or the
    transition is illegal (the kernel enforces the lifecycle).
    """
    _require_own_session(session_id, actor_id, log_path)
    session = update_human_work_state(
        session_id, "in_progress", log_path=log_path
    )
    return WorkInboxItem.from_session(session)


def submit(
    *,
    session_id: str,
    actor_id: str,
    receipt: str,
    completion_summary: str,
    log_path: Any = None,
) -> WorkInboxItem:
    """Return completed work with a typed receipt — moves it to ``completed``.

    The agent role-office then consumes the receipt and integrates the result;
    the receipt-before-integrated invariant is the kernel's, not the userland's.
    """
    _require_own_session(session_id, actor_id, log_path)
    session = update_human_work_state(
        session_id,
        "completed",
        receipt=receipt or None,
        completion_summary=completion_summary,
        log_path=log_path,
    )
    return WorkInboxItem.from_session(session)
