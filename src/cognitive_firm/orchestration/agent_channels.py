"""Typed local agent-to-agent channel for persistent role offices.

This is not an MCP replacement. MCP exposes tools/context to an LLM host.
This module records durable communications between role-bearing offices
inside a local org runtime. External A2A/ACP/MCP adapters can project into
or out of this channel, but the local governance envelope remains canonical.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.transition_log import append_transition


CHANNELS_DIR = ORG_ROOT_DIR / "channels"
ROLES_DIR = ORG_ROOT_DIR / "roles"
DEFAULT_MAX_THREAD_MESSAGES = 25
DEFAULT_MAX_PARENT_OBLIGATION_DEPTH = 8

MessageKind = Literal[
    "inform",
    "request",
    "proposal",
    "handoff",
    "clarification",
    "refusal",
    "status",
]

MessageStatus = Literal["open", "acknowledged", "closed"]


# GP-232 Phase A — obligation lifecycle distinct from message lifecycle.
#
# message status      = "the envelope's state" (open / acknowledged / closed)
# obligation_state    = "the work's state"     (pending / accepted / in_progress /
#                                                blocked_input / fulfilled /
#                                                refused / expired)
#
# Per the A2A audit panel (2026-05-07): the kernel's existing channel.status
# tracks whether the message was read and replied to; it does NOT track whether
# the work the message obliges has been done. This conflation makes
# "B is blocked-input on A" only inferable from open messages, never
# structurally visible. Phase A adds the missing field.
ObligationState = Literal[
    "pending",         # initial state on a request/proposal/handoff
    "accepted",        # receiver acknowledged the obligation
    "in_progress",     # work has started
    "blocked_input",   # waiting on principal input or another obligation
    "fulfilled",       # work completed successfully
    "refused",         # receiver declined the obligation
    "expired",         # past expires_utc without resolution
]


# Allowed transitions (the state-machine validator below enforces this).
# pending -> accepted | refused | expired
# accepted -> in_progress | refused | expired
# in_progress -> blocked_input | fulfilled | refused | expired
# blocked_input -> in_progress | refused | expired
# fulfilled -> (terminal)
# refused -> (terminal)
# expired -> (terminal)
_OBLIGATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset(["accepted", "refused", "expired"]),
    "accepted": frozenset(["in_progress", "refused", "expired"]),
    "in_progress": frozenset(["blocked_input", "fulfilled", "refused", "expired"]),
    "blocked_input": frozenset(["in_progress", "refused", "expired"]),
    "fulfilled": frozenset(),
    "refused": frozenset(),
    "expired": frozenset(),
}


def validate_obligation_transition(from_state: str, to_state: str) -> tuple[bool, str]:
    """Return (allowed, reason). Used by message updaters to gate state
    transitions; rejects anything not in the legal-transitions table."""
    if from_state not in _OBLIGATION_TRANSITIONS:
        return False, f"unknown from_state: {from_state}"
    if to_state not in _OBLIGATION_TRANSITIONS:
        return False, f"unknown to_state: {to_state}"
    if to_state in _OBLIGATION_TRANSITIONS[from_state]:
        return True, "ok"
    if not _OBLIGATION_TRANSITIONS[from_state]:
        return False, f"{from_state} is terminal — no transitions allowed"
    return (
        False,
        f"illegal transition {from_state} -> {to_state}; "
        f"allowed: {sorted(_OBLIGATION_TRANSITIONS[from_state])}",
    )


# Kinds that carry an obligation by default — request/proposal/handoff oblige
# the receiver to do work; inform/clarification/refusal/status do not. This
# mapping decides whether the message is created with a non-None obligation_state.
_OBLIGATION_KINDS: frozenset[str] = frozenset(["request", "proposal", "handoff"])


@dataclass(frozen=True)
class AgentMessage:
    schema_version: int
    message_id: str
    thread_id: str
    kind: MessageKind
    from_role: str
    to_role: str
    subject: str
    body: str
    status: MessageStatus
    created_utc: str
    causality_id: str | None = None
    expects_response: bool = False
    expires_utc: str | None = None
    references: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    # GP-232 Phase A fields — present on all new messages; older log entries
    # may have None for these (loader treats absence as absence of obligation).
    obligation_state: ObligationState | None = None
    parent_obligation_id: str | None = None  # saga compensation chain


class ChannelPolicyError(PermissionError):
    """Raised when a role attempts a message outside local channel policy."""


def _safe_role(role_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", role_id.strip())
    if not safe:
        raise ValueError("role_id cannot be empty")
    return safe


def _strip_role_ref(value: str) -> str:
    return value.split(".", 1)[1] if value.startswith("role.") else value


def _extract_yaml_list(text: str, key: str) -> list[str]:
    out: list[str] = []
    in_block = False
    base_indent = 0
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if stripped == f"{key}:":
            in_block = True
            base_indent = indent
            continue
        if in_block:
            if indent <= base_indent and not stripped.startswith("- "):
                break
            if stripped.startswith("- "):
                item = stripped[2:].split("#", 1)[0].strip().strip('"').strip("'")
                if item:
                    out.append(item)
    return out


def _role_path(role_id: str, *, roles_dir: Path | None = None) -> Path:
    return (roles_dir or ROLES_DIR) / f"{_safe_role(role_id)}.yaml"


def _role_exists(role_id: str, *, roles_dir: Path | None = None) -> bool:
    return _role_path(role_id, roles_dir=roles_dir).exists()


def _role_links(role_id: str, *, roles_dir: Path | None = None) -> set[str]:
    path = _role_path(role_id, roles_dir=roles_dir)
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    links = set()
    for key in ("delegates_to", "escalates_to"):
        links.update(_strip_role_ref(item) for item in _extract_yaml_list(text, key))
    return links


def channel_allowed(
    from_role: str,
    to_role: str,
    *,
    roles_dir: Path | None = None,
) -> tuple[bool, str]:
    """Conservative local channel policy.

    This is not enterprise RBAC. It prevents obvious side-channel drift until
    the control-plane policy compiler exists.
    """
    sender = _safe_role(from_role)
    receiver = _safe_role(to_role)
    if not _role_exists(sender, roles_dir=roles_dir):
        return False, f"sender role does not exist: {sender}"
    if not _role_exists(receiver, roles_dir=roles_dir):
        return False, f"receiver role does not exist: {receiver}"
    if sender == receiver:
        return True, "self-message"
    if sender == "manager":
        return True, "manager coordination channel"
    if receiver in {"manager", "principal"}:
        return True, "manager/principal escalation channel"
    if receiver in _role_links(sender, roles_dir=roles_dir):
        return True, "receiver is in sender delegates_to/escalates_to"
    if sender in _role_links(receiver, roles_dir=roles_dir):
        return True, "sender is in receiver delegates_to/escalates_to"
    return False, "roles are not linked by delegation/escalation policy"


def _role_inbox(role_id: str, *, channels_dir: Path | None = None) -> Path:
    return (channels_dir or CHANNELS_DIR) / _safe_role(role_id) / "inbox"


def _role_sent(role_id: str, *, channels_dir: Path | None = None) -> Path:
    return (channels_dir or CHANNELS_DIR) / _safe_role(role_id) / "sent"


def _message_path(role_id: str, message_id: str, *, channels_dir: Path | None = None) -> Path:
    return _role_inbox(role_id, channels_dir=channels_dir) / f"{message_id}.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _iter_channel_messages(*, channels_dir: Path | None = None) -> list[dict[str, Any]]:
    root = channels_dir or CHANNELS_DIR
    if not root.exists():
        return []
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for path in root.glob("*/*/*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        message_id = str(data.get("message_id") or "")
        if not message_id or message_id in seen:
            continue
        seen.add(message_id)
        rows.append(data)
    return rows


def _message_by_id(message_id: str, *, channels_dir: Path | None = None) -> dict[str, Any] | None:
    for data in _iter_channel_messages(channels_dir=channels_dir):
        if data.get("message_id") == message_id:
            return data
    return None


def _parent_obligation_depth(parent_obligation_id: str, *, channels_dir: Path | None = None) -> int:
    depth = 0
    current = parent_obligation_id
    seen: set[str] = set()
    while current:
        if current in seen:
            return depth + 1
        seen.add(current)
        depth += 1
        parent = _message_by_id(current, channels_dir=channels_dir)
        if parent is None:
            break
        current = str(parent.get("parent_obligation_id") or "")
    return depth


def enforce_a2a_loop_guard(
    *,
    thread_id: str,
    parent_obligation_id: str | None,
    channels_dir: Path | None = None,
    max_thread_messages: int = DEFAULT_MAX_THREAD_MESSAGES,
    max_parent_depth: int = DEFAULT_MAX_PARENT_OBLIGATION_DEPTH,
) -> None:
    """Reject obviously unbounded local A2A chains before writing a message."""
    if max_thread_messages < 1:
        raise ValueError("max_thread_messages must be >= 1")
    if max_parent_depth < 1:
        raise ValueError("max_parent_depth must be >= 1")
    thread_count = sum(
        1
        for data in _iter_channel_messages(channels_dir=channels_dir)
        if data.get("thread_id") == thread_id
    )
    if thread_count >= max_thread_messages:
        raise ValueError(
            f"A2A thread {thread_id!r} has {thread_count} messages; "
            f"limit is {max_thread_messages}"
        )
    if parent_obligation_id:
        depth = _parent_obligation_depth(parent_obligation_id, channels_dir=channels_dir)
        if depth >= max_parent_depth:
            raise ValueError(
                f"A2A parent obligation chain depth {depth} reaches limit {max_parent_depth}"
            )


def send_agent_message(
    *,
    from_role: str,
    to_role: str,
    kind: MessageKind,
    subject: str,
    body: str,
    expects_response: bool = False,
    thread_id: str | None = None,
    causality_id: str | None = None,
    expires_utc: str | None = None,
    references: list[str] | None = None,
    artifacts: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    enforce_policy: bool = True,
    parent_obligation_id: str | None = None,
    channels_dir: Path | None = None,
    roles_dir: Path | None = None,
    transition_log_path: Path | None = None,
    max_thread_messages: int = DEFAULT_MAX_THREAD_MESSAGES,
    max_parent_depth: int = DEFAULT_MAX_PARENT_OBLIGATION_DEPTH,
) -> AgentMessage:
    """Append one durable A2A-style message to the receiver inbox.

    The same JSON is mirrored into the sender's sent folder for local
    inspectability. Coordination authority still lives in gates/claims; this
    channel is for typed communication and handoff context.
    """
    allowed, policy_reason = channel_allowed(from_role, to_role, roles_dir=roles_dir)
    if enforce_policy and not allowed:
        raise ChannelPolicyError(policy_reason)

    now = datetime.now(timezone.utc).isoformat()
    message_id = f"msg_{uuid.uuid4().hex}"
    resolved_thread_id = thread_id or message_id
    enforce_a2a_loop_guard(
        thread_id=resolved_thread_id,
        parent_obligation_id=parent_obligation_id,
        channels_dir=channels_dir,
        max_thread_messages=max_thread_messages,
        max_parent_depth=max_parent_depth,
    )
    message = AgentMessage(
        schema_version=1,
        message_id=message_id,
        thread_id=resolved_thread_id,
        kind=kind,
        from_role=_safe_role(from_role),
        to_role=_safe_role(to_role),
        subject=subject.strip(),
        body=body.strip(),
        status="open",
        created_utc=now,
        causality_id=causality_id,
        expects_response=expects_response,
        expires_utc=expires_utc,
        references=references or [],
        artifacts=artifacts or [],
        metadata={**(metadata or {}), "channel_policy": policy_reason},
        # GP-232 Phase A: obligation lifecycle defaults to pending for kinds
        # that carry an obligation; None for inform/clarification/refusal/status.
        obligation_state="pending" if kind in _OBLIGATION_KINDS else None,
        parent_obligation_id=parent_obligation_id,
    )
    payload = asdict(message)
    _write_json(
        _role_inbox(message.to_role, channels_dir=channels_dir) / f"{message_id}.json",
        payload,
    )
    _write_json(
        _role_sent(message.from_role, channels_dir=channels_dir) / f"{message_id}.json",
        payload,
    )
    append_transition(
        event="agent.message.sent",
        actor=message.from_role,
        role_id=message.from_role,
        surface="agent_channel",
        subject=message_id,
        causality_id=causality_id or message.thread_id,
        payload={
            "to_role": message.to_role,
            "kind": message.kind,
            "thread_id": message.thread_id,
            "expects_response": message.expects_response,
            "references": message.references,
            "artifacts": message.artifacts,
        },
        log_path=transition_log_path,
    )
    return message


def read_agent_message(*, role_id: str, message_id: str) -> AgentMessage | None:
    path = _message_path(role_id, message_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return AgentMessage(**data)


def list_agent_messages(
    *,
    role_id: str,
    status: MessageStatus | None = "open",
    limit: int = 50,
) -> list[AgentMessage]:
    inbox = _role_inbox(role_id)
    if not inbox.exists():
        return []
    out: list[AgentMessage] = []
    for path in sorted(inbox.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            msg = AgentMessage(**json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if status is None or msg.status == status:
            out.append(msg)
        if len(out) >= limit:
            break
    return out


def update_agent_message_status(
    *,
    role_id: str,
    message_id: str,
    status: MessageStatus,
    actor: str,
    note: str = "",
    channels_dir: Path | None = None,
    transition_log_path: Path | None = None,
) -> AgentMessage:
    path = _message_path(role_id, message_id, channels_dir=channels_dir)
    if not path.exists():
        raise FileNotFoundError(f"agent message not found: {message_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["status"] = status
    data.setdefault("metadata", {})
    data["metadata"]["last_status_note"] = note
    data["metadata"]["last_status_actor"] = actor
    data["metadata"]["last_status_utc"] = datetime.now(timezone.utc).isoformat()
    _write_json(path, data)
    sender_mirror = (
        _role_sent(str(data.get("from_role", "")), channels_dir=channels_dir)
        / f"{message_id}.json"
    )
    if sender_mirror.exists():
        _write_json(sender_mirror, data)
    append_transition(
        event=f"agent.message.{status}",
        actor=actor,
        role_id=role_id,
        surface="agent_channel",
        subject=message_id,
        causality_id=data.get("causality_id") or data.get("thread_id"),
        payload={"note": note, "from_role": data.get("from_role"), "to_role": data.get("to_role")},
        log_path=transition_log_path,
    )
    return AgentMessage(**data)


# ── GP-232 Phase A: obligation lifecycle updates ─────────────────────────


def update_obligation_state(
    *,
    role_id: str,
    message_id: str,
    new_state: ObligationState,
    actor: str,
    note: str = "",
    channels_dir: Path | None = None,
    transition_log_path: Path | None = None,
) -> AgentMessage:
    """Transition the message's obligation_state. Validates the transition
    against the legal-transitions table; raises ValueError on illegal moves.

    The message envelope's `status` field is independent — a request can be
    `acknowledged` (envelope read) while its obligation is still `pending`
    (work not yet accepted).
    """
    path = _message_path(role_id, message_id, channels_dir=channels_dir)
    if not path.exists():
        raise FileNotFoundError(f"agent message not found: {message_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    current = data.get("obligation_state")
    if current is None:
        raise ValueError(
            f"message {message_id} has no obligation_state — only "
            f"request/proposal/handoff carry obligations"
        )
    ok, reason = validate_obligation_transition(current, new_state)
    if not ok:
        raise ValueError(reason)
    data["obligation_state"] = new_state
    data.setdefault("metadata", {})
    data["metadata"]["last_obligation_note"] = note
    data["metadata"]["last_obligation_actor"] = actor
    data["metadata"]["last_obligation_utc"] = datetime.now(timezone.utc).isoformat()
    _write_json(path, data)
    sender_mirror = (
        _role_sent(str(data.get("from_role", "")), channels_dir=channels_dir)
        / f"{message_id}.json"
    )
    if sender_mirror.exists():
        _write_json(sender_mirror, data)
    append_transition(
        event=f"agent.obligation.{new_state}",
        actor=actor,
        role_id=role_id,
        surface="agent_channel",
        subject=message_id,
        causality_id=data.get("causality_id") or data.get("thread_id"),
        payload={
            "note": note,
            "from_state": current,
            "to_state": new_state,
            "from_role": data.get("from_role"),
            "to_role": data.get("to_role"),
            "parent_obligation_id": data.get("parent_obligation_id"),
        },
        log_path=transition_log_path,
    )
    return AgentMessage(**data)


def list_blocked_obligations(role_id: str | None = None) -> list[AgentMessage]:
    """Return messages whose obligation_state is `blocked_input` — the
    structurally-visible "B is blocked waiting" view that Orbit and the
    manager-role daemon render to the principal.

    If role_id is None, scan all role inboxes; otherwise only that role's.
    """
    if not CHANNELS_DIR.exists():
        return []
    targets: list[Path]
    if role_id:
        targets = [_role_inbox(role_id)]
    else:
        targets = [p / "inbox" for p in CHANNELS_DIR.iterdir() if p.is_dir()]

    out: list[AgentMessage] = []
    for inbox in targets:
        if not inbox.exists():
            continue
        for path in inbox.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("obligation_state") == "blocked_input":
                    out.append(AgentMessage(**data))
            except Exception:
                continue
    return out
