"""Human work sessions for joint human-agent activity.

Decision gates ask a human to approve or reject. Human work sessions record
bounded work a human performs alongside role offices: source checks, edits,
external actions, taste calls, relationship work, or data entry.
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR


HumanWorkState = Literal[
    "requested",
    "claimed",
    "in_progress",
    "blocked",
    "handed_off",
    "completed",
    "abandoned",
    "integrated",
]

HumanWorkMode = Literal[
    "source_check",
    "edit",
    "external_action",
    "judgment",
    "relationship",
    "data_entry",
    "taste_call",
    "other",
]

BottleneckClass = Literal[
    "authority",
    "access",
    "taste",
    "relationship",
    "cognition",
    "labor",
    "safety",
    "other",
]
Observability = Literal["digital_artifact", "external_system", "human_attested", "unobservable"]
ReceiptType = Literal["note", "artifact_ref", "external_ref", "witness", "none"]
Confidence = Literal["low", "medium", "high"]
InteractionSurface = Literal["offline", "cli", "orbit", "telegram", "external_system", "mixed"]

DEFAULT_HUMAN_WORK_LOG = ORG_ROOT_DIR / "human_work" / "human_work.jsonl"
VALID_STATES = {
    "requested",
    "claimed",
    "in_progress",
    "blocked",
    "handed_off",
    "completed",
    "abandoned",
    "integrated",
}
VALID_MODES = {
    "source_check",
    "edit",
    "external_action",
    "judgment",
    "relationship",
    "data_entry",
    "taste_call",
    "other",
}
VALID_BOTTLENECKS = {
    "authority",
    "access",
    "taste",
    "relationship",
    "cognition",
    "labor",
    "safety",
    "other",
}
VALID_OBSERVABILITY = {"digital_artifact", "external_system", "human_attested", "unobservable"}
VALID_RECEIPT_TYPES = {"note", "artifact_ref", "external_ref", "witness", "none"}
VALID_CONFIDENCE = {"low", "medium", "high"}
VALID_INTERACTION_SURFACES = {"offline", "cli", "orbit", "telegram", "external_system", "mixed"}
TERMINAL_STATES = {"abandoned", "integrated"}
A2H_WAITING_ON_HUMAN_STATES = {"requested", "claimed", "in_progress", "blocked"}
A2H_READY_FOR_AGENT_STATES = {"handed_off", "completed"}
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "requested": {"claimed", "in_progress", "abandoned"},
    "claimed": {"in_progress", "blocked", "handed_off", "abandoned"},
    "in_progress": {"blocked", "handed_off", "completed", "abandoned"},
    "blocked": {"in_progress", "handed_off", "abandoned"},
    "handed_off": {"claimed", "in_progress", "completed", "abandoned"},
    "completed": {"integrated", "in_progress"},
    "abandoned": set(),
    "integrated": set(),
}


@dataclass(frozen=True)
class HumanWorkSession:
    session_id: str
    created_at_utc: str
    updated_at_utc: str
    requested_by: str
    human_actor: str
    objective: str
    work_mode: HumanWorkMode
    bottleneck_class: BottleneckClass
    state: HumanWorkState = "requested"
    tenant_id: str | None = None
    project_id: str | None = None
    collaborating_roles: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    observability: Observability = "human_attested"
    receipt_required: bool = False
    receipt_type: ReceiptType = "none"
    receipt: str | None = None
    confidence: Confidence = "medium"
    sample_for_review: bool = False
    obligation_id: str | None = None
    deadline_utc: str | None = None
    completion_summary: str | None = None
    integration_ref: str | None = None
    interaction_surface: InteractionSurface = "mixed"
    agent_counterparty_role: str | None = None
    human_deliverable: str | None = None
    agent_followup_required: bool = False
    agent_followup_ref: str | None = None
    notes: list[dict[str, Any]] = field(default_factory=list)
    interaction_events: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class A2HWorkPressure:
    """Read-side pressure summary for agent-requested human work."""

    agent_counterparty_role: str
    bottleneck_class: str
    active_count: int
    waiting_count: int
    missing_receipt_count: int
    stale_count: int
    session_ids: list[str]
    recommendation: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate(value: str, allowed: set[str], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"invalid {label} {value!r}; expected one of {sorted(allowed)}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def create_human_work_session(
    *,
    requested_by: str,
    human_actor: str,
    objective: str,
    work_mode: HumanWorkMode | str,
    bottleneck_class: BottleneckClass | str,
    tenant_id: str | None = None,
    project_id: str | None = None,
    collaborating_roles: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    observability: Observability | str = "human_attested",
    receipt_required: bool = False,
    receipt_type: ReceiptType | str = "none",
    receipt: str | None = None,
    confidence: Confidence | str = "medium",
    sample_for_review: bool = False,
    obligation_id: str | None = None,
    deadline_utc: str | None = None,
    interaction_surface: InteractionSurface | str = "mixed",
    agent_counterparty_role: str | None = None,
    human_deliverable: str | None = None,
    agent_followup_required: bool = False,
    agent_followup_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
    session_id: str | None = None,
    log_path: Path | None = None,
) -> HumanWorkSession:
    """Create a durable record of bounded human work."""
    if not requested_by.strip():
        raise ValueError("requested_by is required")
    if not human_actor.strip():
        raise ValueError("human_actor is required")
    if not objective.strip():
        raise ValueError("objective is required")

    now = _now_iso()
    session = HumanWorkSession(
        session_id=session_id or f"hws_{uuid.uuid4().hex[:12]}",
        created_at_utc=now,
        updated_at_utc=now,
        requested_by=requested_by,
        human_actor=human_actor,
        objective=objective,
        work_mode=_validate(str(work_mode), VALID_MODES, "work_mode"),  # type: ignore[arg-type]
        bottleneck_class=_validate(str(bottleneck_class), VALID_BOTTLENECKS, "bottleneck_class"),  # type: ignore[arg-type]
        tenant_id=tenant_id,
        project_id=project_id,
        collaborating_roles=collaborating_roles or [],
        artifact_refs=artifact_refs or [],
        observability=_validate(str(observability), VALID_OBSERVABILITY, "observability"),  # type: ignore[arg-type]
        receipt_required=receipt_required,
        receipt_type=_validate(str(receipt_type), VALID_RECEIPT_TYPES, "receipt_type"),  # type: ignore[arg-type]
        receipt=receipt,
        confidence=_validate(str(confidence), VALID_CONFIDENCE, "confidence"),  # type: ignore[arg-type]
        sample_for_review=sample_for_review,
        obligation_id=obligation_id,
        deadline_utc=deadline_utc,
        interaction_surface=_validate(str(interaction_surface), VALID_INTERACTION_SURFACES, "interaction_surface"),  # type: ignore[arg-type]
        agent_counterparty_role=agent_counterparty_role,
        human_deliverable=human_deliverable,
        agent_followup_required=agent_followup_required,
        agent_followup_ref=agent_followup_ref,
        metadata=metadata or {},
    )
    _append_jsonl(log_path or DEFAULT_HUMAN_WORK_LOG, asdict(session))
    return session


def create_agent_requested_human_work_session(
    *,
    requested_by_role: str,
    human_actor: str,
    objective: str,
    work_mode: HumanWorkMode | str,
    bottleneck_class: BottleneckClass | str,
    human_deliverable: str,
    tenant_id: str | None = None,
    project_id: str | None = None,
    collaborating_roles: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    observability: Observability | str = "human_attested",
    receipt_required: bool = True,
    receipt_type: ReceiptType | str = "note",
    confidence: Confidence | str = "medium",
    sample_for_review: bool = False,
    obligation_id: str | None = None,
    deadline_utc: str | None = None,
    interaction_surface: InteractionSurface | str = "mixed",
    agent_followup_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
    session_id: str | None = None,
    log_path: Path | None = None,
) -> HumanWorkSession:
    """Create the standard A2H work-coordination record.

    The agent remains the requesting role and integration counterparty; the
    human remains the actor performing bounded work. The initial interaction
    event makes the agent request visible without treating it as an authority
    transfer.
    """
    if not human_deliverable.strip():
        raise ValueError("human_deliverable is required")
    session = create_human_work_session(
        requested_by=requested_by_role,
        human_actor=human_actor,
        objective=objective,
        work_mode=work_mode,
        bottleneck_class=bottleneck_class,
        tenant_id=tenant_id,
        project_id=project_id,
        collaborating_roles=collaborating_roles,
        artifact_refs=artifact_refs,
        observability=observability,
        receipt_required=receipt_required,
        receipt_type=receipt_type,
        confidence=confidence,
        sample_for_review=sample_for_review,
        obligation_id=obligation_id,
        deadline_utc=deadline_utc,
        interaction_surface=interaction_surface,
        agent_counterparty_role=requested_by_role,
        human_deliverable=human_deliverable,
        agent_followup_required=True,
        agent_followup_ref=agent_followup_ref,
        metadata={**(metadata or {}), "coordination_pattern": "a2h_work_request"},
        session_id=session_id,
        log_path=log_path,
    )
    return append_human_work_interaction(
        session.session_id,
        actor=requested_by_role,
        event_type="agent_requested_human_work",
        surface=interaction_surface,
        summary=f"Requested bounded human work: {human_deliverable}",
        artifact_refs=artifact_refs,
        agent_followup_required=True,
        log_path=log_path,
    )


def list_human_work_sessions(
    *,
    state: HumanWorkState | str | None = None,
    human_actor: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    obligation_id: str | None = None,
    agent_followup_required: bool | None = None,
    interaction_surface: InteractionSurface | str | None = None,
    log_path: Path | None = None,
) -> list[HumanWorkSession]:
    if state is not None:
        state = _validate(str(state), VALID_STATES, "state")
    if interaction_surface is not None:
        interaction_surface = _validate(
            str(interaction_surface),
            VALID_INTERACTION_SURFACES,
            "interaction_surface",
        )
    out: list[HumanWorkSession] = []
    for row in _read_jsonl(log_path or DEFAULT_HUMAN_WORK_LOG):
        session = HumanWorkSession(**row)
        if state is not None and session.state != state:
            continue
        if human_actor is not None and session.human_actor != human_actor:
            continue
        if tenant_id is not None and session.tenant_id != tenant_id:
            continue
        if project_id is not None and session.project_id != project_id:
            continue
        if obligation_id is not None and session.obligation_id != obligation_id:
            continue
        if (
            agent_followup_required is not None
            and session.agent_followup_required is not agent_followup_required
        ):
            continue
        if interaction_surface is not None and session.interaction_surface != interaction_surface:
            continue
        out.append(session)
    return out


def list_agent_followup_human_work_sessions(
    *,
    agent_counterparty_role: str | None = None,
    log_path: Path | None = None,
) -> list[HumanWorkSession]:
    """Return A2H sessions whose result is ready for role-office follow-up."""
    sessions = list_human_work_sessions(agent_followup_required=True, log_path=log_path)
    out: list[HumanWorkSession] = []
    for session in sessions:
        if session.state not in A2H_READY_FOR_AGENT_STATES:
            continue
        if agent_counterparty_role and session.agent_counterparty_role != agent_counterparty_role:
            continue
        out.append(session)
    return out


def list_a2h_waiting_on_human_sessions(
    *,
    agent_counterparty_role: str | None = None,
    log_path: Path | None = None,
) -> list[HumanWorkSession]:
    """Return A2H sessions that are waiting for human work or coordination."""
    sessions = list_human_work_sessions(agent_followup_required=True, log_path=log_path)
    out: list[HumanWorkSession] = []
    for session in sessions:
        if session.state not in A2H_WAITING_ON_HUMAN_STATES:
            continue
        if agent_counterparty_role and session.agent_counterparty_role != agent_counterparty_role:
            continue
        out.append(session)
    return out


def list_missing_receipt_human_work_sessions(
    *,
    log_path: Path | None = None,
) -> list[HumanWorkSession]:
    """Return open sessions requiring receipts that are not yet present."""
    return [
        session
        for session in list_human_work_sessions(log_path=log_path)
        if session.state not in TERMINAL_STATES
        and session.receipt_required
        and not (session.receipt or "").strip()
    ]


def summarize_a2h_work_pressure(
    *,
    sessions: list[HumanWorkSession] | None = None,
    log_path: Path | None = None,
    stale_after_hours: float = 24.0,
    concentration_threshold: int = 3,
) -> list[A2HWorkPressure]:
    """Summarize repeated A2H pressure by role and bottleneck class.

    This is a read model for routing and review. It does not apply rate limits
    or mutate sessions.
    """
    now = datetime.now(timezone.utc)
    groups: dict[tuple[str, str], list[HumanWorkSession]] = {}
    for session in sessions if sessions is not None else list_human_work_sessions(log_path=log_path):
        role = session.agent_counterparty_role
        if not role or not session.agent_followup_required or session.state in TERMINAL_STATES:
            continue
        groups.setdefault((role, session.bottleneck_class), []).append(session)

    pressure: list[A2HWorkPressure] = []
    for (role, bottleneck), rows in sorted(groups.items()):
        waiting = [s for s in rows if s.state in A2H_WAITING_ON_HUMAN_STATES]
        missing_receipts = [s for s in rows if s.receipt_required and not (s.receipt or "").strip()]
        stale = []
        for session in rows:
            updated = _parse_iso(session.updated_at_utc)
            if updated and (now - updated).total_seconds() >= stale_after_hours * 3600:
                stale.append(session)
        if len(rows) < concentration_threshold and not missing_receipts and not stale:
            continue
        if bottleneck in {"labor", "access"} and len(rows) >= concentration_threshold:
            recommendation = "consider source connector, tooling, or mandate change"
        elif bottleneck in {"authority", "taste", "relationship", "safety"}:
            recommendation = "preserve human boundary; batch or schedule review"
        else:
            recommendation = "review repeated human-work pressure"
        pressure.append(
            A2HWorkPressure(
                agent_counterparty_role=role,
                bottleneck_class=bottleneck,
                active_count=len(rows),
                waiting_count=len(waiting),
                missing_receipt_count=len(missing_receipts),
                stale_count=len(stale),
                session_ids=[session.session_id for session in rows],
                recommendation=recommendation,
            )
        )
    return pressure


def _replace_session(path: Path, session_id: str, mutate) -> HumanWorkSession:
    rows = _read_jsonl(path)
    updated: HumanWorkSession | None = None
    next_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("session_id") == session_id:
            row = mutate(dict(row))
            updated = HumanWorkSession(**row)
        next_rows.append(row)
    if updated is None:
        raise KeyError(f"human work session not found: {session_id}")
    _write_jsonl(path, next_rows)
    return updated


def update_human_work_state(
    session_id: str,
    state: HumanWorkState | str,
    *,
    completion_summary: str | None = None,
    integration_ref: str | None = None,
    receipt: str | None = None,
    confidence: Confidence | str | None = None,
    agent_followup_required: bool | None = None,
    agent_followup_ref: str | None = None,
    log_path: Path | None = None,
) -> HumanWorkSession:
    """Move a human work session through its lifecycle."""
    next_state = _validate(str(state), VALID_STATES, "state")
    path = log_path or DEFAULT_HUMAN_WORK_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        current = row.get("state")
        if current in TERMINAL_STATES:
            raise ValueError(f"{current} is terminal; no transitions allowed")
        allowed = ALLOWED_TRANSITIONS.get(str(current), set())
        if next_state not in allowed:
            raise ValueError(
                f"illegal transition {current} -> {next_state}; allowed: {sorted(allowed)}"
            )
        row["state"] = next_state
        row["updated_at_utc"] = _now_iso()
        if completion_summary is not None:
            row["completion_summary"] = completion_summary
        if integration_ref is not None:
            row["integration_ref"] = integration_ref
        if receipt is not None:
            row["receipt"] = receipt
            if row.get("receipt_type") == "none":
                row["receipt_type"] = "note"
        if confidence is not None:
            row["confidence"] = _validate(str(confidence), VALID_CONFIDENCE, "confidence")
        if agent_followup_required is not None:
            row["agent_followup_required"] = bool(agent_followup_required)
        if agent_followup_ref is not None:
            row["agent_followup_ref"] = agent_followup_ref
        if (
            next_state == "integrated"
            and row.get("receipt_required")
            and not str(row.get("receipt") or "").strip()
        ):
            raise ValueError("integrated human work requires receipt when receipt_required is true")
        return row

    return _replace_session(path, session_id, mutate)


def append_human_work_note(
    session_id: str,
    *,
    actor: str,
    note: str,
    artifact_refs: list[str] | None = None,
    log_path: Path | None = None,
) -> HumanWorkSession:
    """Append a coordination-relevant note without storing full chat."""
    if not actor.strip():
        raise ValueError("actor is required")
    if not note.strip():
        raise ValueError("note is required")
    path = log_path or DEFAULT_HUMAN_WORK_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        notes = list(row.get("notes") or [])
        notes.append(
            {
                "ts": _now_iso(),
                "actor": actor,
                "note": note,
                "artifact_refs": artifact_refs or [],
            }
        )
        row["notes"] = notes
        row["updated_at_utc"] = _now_iso()
        if artifact_refs:
            existing = list(row.get("artifact_refs") or [])
            row["artifact_refs"] = list(dict.fromkeys(existing + artifact_refs))
        return row

    return _replace_session(path, session_id, mutate)


def append_human_work_interaction(
    session_id: str,
    *,
    actor: str,
    event_type: str,
    summary: str,
    surface: InteractionSurface | str = "mixed",
    artifact_refs: list[str] | None = None,
    blocker: str | None = None,
    agent_followup_required: bool | None = None,
    log_path: Path | None = None,
) -> HumanWorkSession:
    """Append a structured human-agent co-work event.

    Use this for non-digitized or mixed work where the transcript is not the
    artifact. The row records the bounded interaction and references durable
    evidence when available.
    """
    if not actor.strip():
        raise ValueError("actor is required")
    if not event_type.strip():
        raise ValueError("event_type is required")
    if not summary.strip():
        raise ValueError("summary is required")
    surface = _validate(str(surface), VALID_INTERACTION_SURFACES, "surface")
    path = log_path or DEFAULT_HUMAN_WORK_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        events = list(row.get("interaction_events") or [])
        events.append(
            {
                "ts": _now_iso(),
                "actor": actor,
                "event_type": event_type,
                "surface": surface,
                "summary": summary,
                "artifact_refs": artifact_refs or [],
                "blocker": blocker,
            }
        )
        row["interaction_events"] = events
        row["updated_at_utc"] = _now_iso()
        if artifact_refs:
            existing = list(row.get("artifact_refs") or [])
            row["artifact_refs"] = list(dict.fromkeys(existing + artifact_refs))
        if agent_followup_required is not None:
            row["agent_followup_required"] = bool(agent_followup_required)
        return row

    return _replace_session(path, session_id, mutate)


def human_work_summary(session: HumanWorkSession) -> dict[str, Any]:
    return asdict(session)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage cognitive-firm human work sessions.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--state")
    list_parser.add_argument("--human-actor")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--obligation-id")
    list_parser.add_argument("--agent-followup-required", action=argparse.BooleanOptionalAction, default=None)
    list_parser.add_argument("--interaction-surface")
    list_parser.add_argument("--log-path", type=Path)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--requested-by", required=True)
    create_parser.add_argument("--human-actor", required=True)
    create_parser.add_argument("--objective", required=True)
    create_parser.add_argument("--work-mode", default="other")
    create_parser.add_argument("--bottleneck-class", default="other")
    create_parser.add_argument("--tenant-id")
    create_parser.add_argument("--project-id")
    create_parser.add_argument("--collaborating-role", action="append", default=[])
    create_parser.add_argument("--artifact-ref", action="append", default=[])
    create_parser.add_argument("--observability", default="human_attested")
    create_parser.add_argument("--receipt-required", action="store_true")
    create_parser.add_argument("--receipt-type", default="none")
    create_parser.add_argument("--receipt")
    create_parser.add_argument("--confidence", default="medium")
    create_parser.add_argument("--sample-for-review", action="store_true")
    create_parser.add_argument("--obligation-id")
    create_parser.add_argument("--deadline-utc")
    create_parser.add_argument("--interaction-surface", default="mixed")
    create_parser.add_argument("--agent-counterparty-role")
    create_parser.add_argument("--human-deliverable")
    create_parser.add_argument("--agent-followup-required", action="store_true")
    create_parser.add_argument("--agent-followup-ref")
    create_parser.add_argument("--log-path", type=Path)

    create_a2h_parser = sub.add_parser("create-a2h")
    create_a2h_parser.add_argument("--requested-by-role", required=True)
    create_a2h_parser.add_argument("--human-actor", required=True)
    create_a2h_parser.add_argument("--objective", required=True)
    create_a2h_parser.add_argument("--work-mode", default="other")
    create_a2h_parser.add_argument("--bottleneck-class", default="other")
    create_a2h_parser.add_argument("--human-deliverable", required=True)
    create_a2h_parser.add_argument("--tenant-id")
    create_a2h_parser.add_argument("--project-id")
    create_a2h_parser.add_argument("--collaborating-role", action="append", default=[])
    create_a2h_parser.add_argument("--artifact-ref", action="append", default=[])
    create_a2h_parser.add_argument("--observability", default="human_attested")
    create_a2h_parser.add_argument("--no-receipt-required", action="store_true")
    create_a2h_parser.add_argument("--receipt-type", default="note")
    create_a2h_parser.add_argument("--confidence", default="medium")
    create_a2h_parser.add_argument("--sample-for-review", action="store_true")
    create_a2h_parser.add_argument("--obligation-id")
    create_a2h_parser.add_argument("--deadline-utc")
    create_a2h_parser.add_argument("--interaction-surface", default="mixed")
    create_a2h_parser.add_argument("--agent-followup-ref")
    create_a2h_parser.add_argument("--log-path", type=Path)

    state_parser = sub.add_parser("update-state")
    state_parser.add_argument("session_id")
    state_parser.add_argument("state")
    state_parser.add_argument("--completion-summary")
    state_parser.add_argument("--integration-ref")
    state_parser.add_argument("--receipt")
    state_parser.add_argument("--confidence")
    state_parser.add_argument("--agent-followup-required", action=argparse.BooleanOptionalAction, default=None)
    state_parser.add_argument("--agent-followup-ref")
    state_parser.add_argument("--log-path", type=Path)

    note_parser = sub.add_parser("note")
    note_parser.add_argument("session_id")
    note_parser.add_argument("--actor", required=True)
    note_parser.add_argument("--note", required=True)
    note_parser.add_argument("--artifact-ref", action="append", default=[])
    note_parser.add_argument("--log-path", type=Path)

    interaction_parser = sub.add_parser("interaction")
    interaction_parser.add_argument("session_id")
    interaction_parser.add_argument("--actor", required=True)
    interaction_parser.add_argument("--event-type", required=True)
    interaction_parser.add_argument("--summary", required=True)
    interaction_parser.add_argument("--surface", default="mixed")
    interaction_parser.add_argument("--artifact-ref", action="append", default=[])
    interaction_parser.add_argument("--blocker")
    interaction_parser.add_argument("--agent-followup-required", action=argparse.BooleanOptionalAction, default=None)
    interaction_parser.add_argument("--log-path", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "list":
        sessions = list_human_work_sessions(
            state=args.state,
            human_actor=args.human_actor,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            obligation_id=args.obligation_id,
            agent_followup_required=args.agent_followup_required,
            interaction_surface=args.interaction_surface,
            log_path=args.log_path,
        )
        for session in sessions:
            print(json.dumps(human_work_summary(session), sort_keys=True))
        return 0
    if args.cmd == "create":
        session = create_human_work_session(
            requested_by=args.requested_by,
            human_actor=args.human_actor,
            objective=args.objective,
            work_mode=args.work_mode,
            bottleneck_class=args.bottleneck_class,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            collaborating_roles=args.collaborating_role,
            artifact_refs=args.artifact_ref,
            observability=args.observability,
            receipt_required=args.receipt_required,
            receipt_type=args.receipt_type,
            receipt=args.receipt,
            confidence=args.confidence,
            sample_for_review=args.sample_for_review,
            obligation_id=args.obligation_id,
            deadline_utc=args.deadline_utc,
            interaction_surface=args.interaction_surface,
            agent_counterparty_role=args.agent_counterparty_role,
            human_deliverable=args.human_deliverable,
            agent_followup_required=args.agent_followup_required,
            agent_followup_ref=args.agent_followup_ref,
            log_path=args.log_path,
        )
        print(json.dumps(human_work_summary(session), sort_keys=True))
        return 0
    if args.cmd == "create-a2h":
        session = create_agent_requested_human_work_session(
            requested_by_role=args.requested_by_role,
            human_actor=args.human_actor,
            objective=args.objective,
            work_mode=args.work_mode,
            bottleneck_class=args.bottleneck_class,
            human_deliverable=args.human_deliverable,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            collaborating_roles=args.collaborating_role,
            artifact_refs=args.artifact_ref,
            observability=args.observability,
            receipt_required=not args.no_receipt_required,
            receipt_type=args.receipt_type,
            confidence=args.confidence,
            sample_for_review=args.sample_for_review,
            obligation_id=args.obligation_id,
            deadline_utc=args.deadline_utc,
            interaction_surface=args.interaction_surface,
            agent_followup_ref=args.agent_followup_ref,
            log_path=args.log_path,
        )
        print(json.dumps(human_work_summary(session), sort_keys=True))
        return 0
    if args.cmd == "update-state":
        session = update_human_work_state(
            args.session_id,
            args.state,
            completion_summary=args.completion_summary,
            integration_ref=args.integration_ref,
            receipt=args.receipt,
            confidence=args.confidence,
            agent_followup_required=args.agent_followup_required,
            agent_followup_ref=args.agent_followup_ref,
            log_path=args.log_path,
        )
        print(json.dumps(human_work_summary(session), sort_keys=True))
        return 0
    if args.cmd == "interaction":
        session = append_human_work_interaction(
            args.session_id,
            actor=args.actor,
            event_type=args.event_type,
            summary=args.summary,
            surface=args.surface,
            artifact_refs=args.artifact_ref,
            blocker=args.blocker,
            agent_followup_required=args.agent_followup_required,
            log_path=args.log_path,
        )
        print(json.dumps(human_work_summary(session), sort_keys=True))
        return 0
    if args.cmd == "note":
        session = append_human_work_note(
            args.session_id,
            actor=args.actor,
            note=args.note,
            artifact_refs=args.artifact_ref,
            log_path=args.log_path,
        )
        print(json.dumps(human_work_summary(session), sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
