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
from cognitive_firm.orchestration.resource_envelope import KernelResource, make_resource


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
RiskTier = Literal["low", "medium", "high", "irreversible"]
DeploymentClass = Literal[
    "local",
    "internal",
    "customer_facing",
    "regulated",
    "physical_world",
    "external_write",
]
HumanSpeedClass = Literal[
    "agent_speed",
    "sampled_review",
    "batched_human_review",
    "gate_before_action",
    "accountable_closure",
]

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
VALID_RISK_TIERS = {"low", "medium", "high", "irreversible"}
VALID_DEPLOYMENT_CLASSES = {
    "local",
    "internal",
    "customer_facing",
    "regulated",
    "physical_world",
    "external_write",
}
VALID_HUMAN_SPEED_CLASSES = {
    "agent_speed",
    "sampled_review",
    "batched_human_review",
    "gate_before_action",
    "accountable_closure",
}
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
    work_receipts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HumanWorkReceipt:
    """Structured receipt for bounded human work.

    This records a bounded human claim without making the kernel pretend it
    observed the work directly. `subject_refs` can point at any domain object:
    source, customer, asset, location, system, document, conversation, or work
    order.
    """

    receipt_id: str
    recorded_at_utc: str
    actor: str
    summary: str
    receipt_type: ReceiptType = "note"
    receipt_ref: str | None = None
    observability: Observability = "human_attested"
    confidence: Confidence = "medium"
    subject_refs: list[str] = field(default_factory=list)
    artifact_refs: list[str] = field(default_factory=list)
    review_required: bool = False
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


@dataclass(frozen=True)
class HumanSpeedEnvelope:
    """Read-only guidance for matching work speed to accountability needs."""

    schema: str
    speed_class: HumanSpeedClass
    cadence: str
    required_record: str
    receipt_required: bool
    sample_for_review: bool
    sample_rate: float | None
    gate_required: bool
    accountability_case_recommended: bool
    rationale: str
    review_questions: list[str]
    inputs: dict[str, Any]
    boundary: dict[str, bool]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HumanSpeedFieldPilotSummary:
    """Read-only field-pilot summary for human-speed envelope outcomes."""

    schema: str
    n_total: int
    min_records: int
    enough_records: bool
    measurement_status: str
    expected_matches: int
    expected_mismatches: list[dict[str, Any]]
    by_speed_class: dict[str, dict[str, Any]]
    sample_policy: dict[str, Any]
    review_reasons: list[str]
    boundary: dict[str, bool]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


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


def build_human_speed_envelope(
    *,
    risk_tier: RiskTier | str = "medium",
    bottleneck_class: BottleneckClass | str = "other",
    deployment_class: DeploymentClass | str = "internal",
    reversible: bool = True,
    external_side_effect: bool = False,
    repeated_similar: bool = False,
    private_context: bool = False,
    harm_occurred: bool = False,
    residual_risk_accepted: bool = False,
) -> HumanSpeedEnvelope:
    """Classify the accountable speed for a proposed human/agent work item.

    This is a projection over stated facts. It does not authorize work, open
    gates, schedule review, or sample anything.
    """

    risk = _validate(str(risk_tier), VALID_RISK_TIERS, "risk_tier")
    bottleneck = _validate(str(bottleneck_class), VALID_BOTTLENECKS, "bottleneck_class")
    deployment = _validate(
        str(deployment_class),
        VALID_DEPLOYMENT_CLASSES,
        "deployment_class",
    )
    high_exposure = (
        risk in {"high", "irreversible"}
        or deployment in {"regulated", "physical_world", "external_write"}
        or (deployment == "customer_facing" and external_side_effect)
    )
    pre_action_gate_needed = (
        risk == "irreversible"
        or (high_exposure and not reversible)
        or deployment in {"regulated", "physical_world", "external_write"}
        or (deployment == "customer_facing" and external_side_effect)
        or (risk == "high" and external_side_effect)
    )
    human_judgment_boundary = (
        private_context
        or bottleneck in {"authority", "taste", "relationship", "safety"}
    )

    if harm_occurred or residual_risk_accepted:
        speed_class: HumanSpeedClass = "accountable_closure"
        cadence = "closure_review"
        required_record = "accountability_case"
        receipt_required = True
        sample_for_review = False
        sample_rate = None
        gate_required = False
        accountability_case_recommended = True
        rationale = (
            "Harm or accepted residual risk needs owner, recourse, evidence, "
            "and closure rather than faster execution."
        )
    elif pre_action_gate_needed:
        speed_class = "gate_before_action"
        cadence = "pre_action_gate"
        required_record = "policy_decision_or_gate_plus_lease"
        receipt_required = True
        sample_for_review = False
        sample_rate = None
        gate_required = True
        accountability_case_recommended = False
        rationale = (
            "Irreversible or high-exposure work should be gated before the "
            "side effect, not sampled after the fact."
        )
    elif human_judgment_boundary:
        speed_class = "batched_human_review"
        cadence = "accountable_human_batch"
        required_record = "human_work_session_with_receipt"
        receipt_required = True
        sample_for_review = bottleneck in {"taste", "relationship", "safety"}
        sample_rate = 1.0 if sample_for_review else None
        gate_required = False
        accountability_case_recommended = False
        rationale = (
            "The bottleneck depends on human authority, taste, relationship, "
            "safety, or private context; preserve that boundary but batch the "
            "work when per-item review would add waste."
        )
    elif repeated_similar or risk == "medium" or deployment == "customer_facing":
        speed_class = "sampled_review"
        cadence = "agent_speed_with_sampled_review"
        required_record = "action_attestations_plus_sample_policy"
        receipt_required = False
        sample_for_review = True
        sample_rate = 0.1 if risk == "low" else 0.2
        gate_required = False
        accountability_case_recommended = False
        rationale = (
            "The work can proceed without per-item gates, but similar or "
            "moderate-risk actions should be sampled so errors become visible."
        )
    else:
        speed_class = "agent_speed"
        cadence = "agent_tick"
        required_record = "transition_or_action_attestation"
        receipt_required = False
        sample_for_review = False
        sample_rate = None
        gate_required = False
        accountability_case_recommended = False
        rationale = (
            "The action is reversible, bounded, low-risk, and does not require "
            "private human context."
        )

    return HumanSpeedEnvelope(
        schema="human_speed_envelope.v1",
        speed_class=speed_class,
        cadence=cadence,
        required_record=required_record,
        receipt_required=receipt_required,
        sample_for_review=sample_for_review,
        sample_rate=sample_rate,
        gate_required=gate_required,
        accountability_case_recommended=accountability_case_recommended,
        rationale=rationale,
        review_questions=_speed_envelope_review_questions(speed_class),
        inputs={
            "risk_tier": risk,
            "bottleneck_class": bottleneck,
            "deployment_class": deployment,
            "reversible": bool(reversible),
            "external_side_effect": bool(external_side_effect),
            "repeated_similar": bool(repeated_similar),
            "private_context": bool(private_context),
            "harm_occurred": bool(harm_occurred),
            "residual_risk_accepted": bool(residual_risk_accepted),
        },
        boundary={
            "does_not_authorize_work": True,
            "does_not_dispatch_work": True,
            "does_not_schedule_review": True,
            "does_not_sample_records": True,
            "does_not_approve_policy": True,
        },
    )


def _speed_envelope_review_questions(speed_class: HumanSpeedClass) -> list[str]:
    common = [
        "What evidence would prove this speed choice was safe?",
        "What would make this work move to a slower or more accountable class?",
    ]
    if speed_class == "agent_speed":
        return [
            "Is the action reversible and bounded to the stated scope?",
            "Will a transition or attestation make the fast action replayable?",
            *common,
        ]
    if speed_class == "sampled_review":
        return [
            "What sample rate and error threshold should trigger escalation?",
            "Does the sample cover the cases most likely to hide externalities?",
            *common,
        ]
    if speed_class == "batched_human_review":
        return [
            "Which part of the work is essential human judgment rather than avoidable toil?",
            "Can similar items be batched without erasing relationship, taste, safety, or authority context?",
            *common,
        ]
    if speed_class == "gate_before_action":
        return [
            "Which authority, policy decision, or lease must exist before the side effect?",
            "What rollback or recourse path exists if the gate is wrong?",
            *common,
        ]
    return [
        "Who owns closure, recourse, and future review?",
        "Which future work should encounter this residual risk or harm record?",
        *common,
    ]


def summarize_human_speed_field_pilot(
    rows: list[dict[str, Any]],
    *,
    min_records: int = 0,
    default_expected_sample_rate: float = 0.1,
) -> HumanSpeedFieldPilotSummary:
    """Summarize measured outcomes for chosen human-speed envelope classes.

    This is a field-pilot read model. It checks whether the chosen class
    matched the classifier and whether measured outcomes need review. It does
    not change routing, dispatch work, approve policy, or sample records.
    """

    by_class: dict[str, dict[str, Any]] = {}
    review_reasons: list[str] = []
    expected_mismatches: list[dict[str, Any]] = []
    expected_matches = 0
    sampled_review_rows = 0
    sampled_review_samples = 0
    sampled_expected_rate = default_expected_sample_rate

    for index, row in enumerate(rows, start=1):
        row_id = str(
            row.get("row_id")
            or row.get("action_id")
            or row.get("decision_id")
            or f"row-{index}"
        )
        expected = _expected_speed_envelope_for_pilot_row(row)
        chosen = str(
            row.get("chosen_speed_class")
            or row.get("speed_class")
            or (expected.speed_class if expected is not None else "unclassified")
        )
        if chosen not in VALID_HUMAN_SPEED_CLASSES and chosen != "unclassified":
            review_reasons.append(f"{row_id}: invalid speed_class {chosen!r}")
        stats = by_class.setdefault(chosen, _empty_speed_pilot_stats())
        stats["n_total"] += 1

        if expected is None:
            stats["missing_envelope_inputs"] += 1
            review_reasons.append(f"{row_id}: missing envelope input facts")
        elif chosen == expected.speed_class:
            expected_matches += 1
        else:
            stats["expected_mismatches"] += 1
            mismatch = {
                "row_id": row_id,
                "chosen_speed_class": chosen,
                "expected_speed_class": expected.speed_class,
                "required_record": expected.required_record,
            }
            expected_mismatches.append(mismatch)
            review_reasons.append(
                f"{row_id}: chosen {chosen} differs from expected {expected.speed_class}"
            )

        if _pilot_bool(row, "error_occurred") or _pilot_bool(row, "decision_error"):
            stats["errors"] += 1
        if _pilot_bool(row, "rework_required"):
            stats["rework"] += 1
        if _pilot_bool(row, "hidden_burden_detected"):
            stats["hidden_burden"] += 1
        if _pilot_bool(row, "harm_occurred"):
            stats["harm"] += 1
            review_reasons.append(f"{row_id}: harm occurred under {chosen}")
        if _pilot_bool(row, "residual_risk_open"):
            stats["residual_risk_open"] += 1
            review_reasons.append(f"{row_id}: residual risk remains open")

        receipt_present = _pilot_bool(row, "receipt_present", default=True)
        if chosen in {"gate_before_action", "accountable_closure"} and not receipt_present:
            stats["missing_receipts"] += 1
            review_reasons.append(f"{row_id}: {chosen} missing receipt")

        sampled = _pilot_bool(row, "sampled_for_review")
        if sampled:
            stats["sampled_for_review"] += 1
        if chosen == "sampled_review":
            sampled_review_rows += 1
            if sampled:
                sampled_review_samples += 1
            if expected and expected.sample_rate is not None:
                sampled_expected_rate = max(sampled_expected_rate, expected.sample_rate)
            row_expected = _pilot_float(row, "expected_sample_rate")
            if row_expected is not None:
                sampled_expected_rate = max(sampled_expected_rate, row_expected)

        cycle_time = _pilot_float(row, "cycle_time_hours")
        if cycle_time is not None:
            stats["_cycle_time_sum"] += cycle_time
            stats["_cycle_time_count"] += 1
        touchpoints = _pilot_float(row, "human_touchpoints")
        if touchpoints is not None:
            stats["_human_touchpoints_sum"] += touchpoints
            stats["_human_touchpoints_count"] += 1

    for stats in by_class.values():
        stats["error_rate"] = _rate(stats["errors"], stats["n_total"])
        stats["rework_rate"] = _rate(stats["rework"], stats["n_total"])
        stats["hidden_burden_rate"] = _rate(stats["hidden_burden"], stats["n_total"])
        stats["residual_risk_open_rate"] = _rate(
            stats["residual_risk_open"],
            stats["n_total"],
        )
        stats["sample_rate_observed"] = _rate(
            stats["sampled_for_review"],
            stats["n_total"],
        )
        stats["mean_cycle_time_hours"] = _mean_or_none(
            stats.pop("_cycle_time_sum"),
            stats.pop("_cycle_time_count"),
        )
        stats["mean_human_touchpoints"] = _mean_or_none(
            stats.pop("_human_touchpoints_sum"),
            stats.pop("_human_touchpoints_count"),
        )

    observed_sample_rate = _rate(sampled_review_samples, sampled_review_rows)
    if sampled_review_rows and observed_sample_rate < sampled_expected_rate:
        review_reasons.append(
            "sampled_review observed sample rate "
            f"{observed_sample_rate:.3f} below expected {sampled_expected_rate:.3f}"
        )

    enough_records = len(rows) >= min_records
    if not enough_records:
        measurement_status = "insufficient_evidence"
    elif review_reasons:
        measurement_status = "needs_review"
    else:
        measurement_status = "stable"

    return HumanSpeedFieldPilotSummary(
        schema="human_speed_field_pilot_summary.v1",
        n_total=len(rows),
        min_records=min_records,
        enough_records=enough_records,
        measurement_status=measurement_status,
        expected_matches=expected_matches,
        expected_mismatches=expected_mismatches,
        by_speed_class={key: by_class[key] for key in sorted(by_class)},
        sample_policy={
            "sampled_review_rows": sampled_review_rows,
            "sampled_review_samples": sampled_review_samples,
            "observed_sample_rate": observed_sample_rate,
            "expected_sample_rate": sampled_expected_rate if sampled_review_rows else None,
        },
        review_reasons=review_reasons,
        boundary={
            "does_not_authorize_work": True,
            "does_not_dispatch_work": True,
            "does_not_schedule_review": True,
            "does_not_sample_records": True,
            "does_not_approve_policy": True,
        },
    )


def _expected_speed_envelope_for_pilot_row(
    row: dict[str, Any],
) -> HumanSpeedEnvelope | None:
    if not all(key in row for key in ("risk_tier", "bottleneck_class", "deployment_class")):
        return None
    return build_human_speed_envelope(
        risk_tier=str(row["risk_tier"]),
        bottleneck_class=str(row["bottleneck_class"]),
        deployment_class=str(row["deployment_class"]),
        reversible=_pilot_bool(row, "reversible", default=True),
        external_side_effect=_pilot_bool(row, "external_side_effect"),
        repeated_similar=_pilot_bool(row, "repeated_similar"),
        private_context=_pilot_bool(row, "private_context"),
        harm_occurred=_pilot_bool(row, "harm_occurred"),
        residual_risk_accepted=_pilot_bool(row, "residual_risk_accepted"),
    )


def _empty_speed_pilot_stats() -> dict[str, Any]:
    return {
        "n_total": 0,
        "expected_mismatches": 0,
        "missing_envelope_inputs": 0,
        "errors": 0,
        "rework": 0,
        "hidden_burden": 0,
        "harm": 0,
        "residual_risk_open": 0,
        "missing_receipts": 0,
        "sampled_for_review": 0,
        "_cycle_time_sum": 0.0,
        "_cycle_time_count": 0,
        "_human_touchpoints_sum": 0.0,
        "_human_touchpoints_count": 0,
    }


def _pilot_bool(row: dict[str, Any], key: str, *, default: bool = False) -> bool:
    value = row.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if value is None:
        return default
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    return default


def _pilot_float(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None or value == "":
        return None
    return float(value)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _mean_or_none(total: float, count: int) -> float | None:
    if count <= 0:
        return None
    return total / count


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


def _human_work_receipt_text(receipt: HumanWorkReceipt) -> str:
    parts = [f"human work receipt by {receipt.actor}", receipt.summary]
    if receipt.receipt_ref:
        parts.append(f"receipt_ref={receipt.receipt_ref}")
    if receipt.subject_refs:
        parts.append(f"subjects={','.join(receipt.subject_refs)}")
    return "; ".join(parts)


def append_human_work_receipt(
    session_id: str,
    *,
    actor: str,
    summary: str,
    receipt_type: ReceiptType | str = "note",
    receipt_ref: str | None = None,
    subject_refs: list[str] | None = None,
    artifact_refs: list[str] | None = None,
    confidence: Confidence | str = "medium",
    observability: Observability | str = "human_attested",
    review_required: bool = False,
    metadata: dict[str, Any] | None = None,
    log_path: Path | None = None,
) -> HumanWorkSession:
    """Append a structured receipt for bounded human work."""
    if not actor.strip():
        raise ValueError("actor is required")
    if not summary.strip():
        raise ValueError("summary is required")
    receipt_type = _validate(str(receipt_type), VALID_RECEIPT_TYPES, "receipt_type")
    confidence = _validate(str(confidence), VALID_CONFIDENCE, "confidence")
    observability = _validate(str(observability), VALID_OBSERVABILITY, "observability")
    if receipt_type == "external_ref" and not (receipt_ref or "").strip():
        raise ValueError("receipt_ref is required when receipt_type is external_ref")
    if receipt_type == "artifact_ref" and not (artifact_refs or receipt_ref):
        raise ValueError("artifact_refs or receipt_ref is required when receipt_type is artifact_ref")
    if receipt_type == "witness" and not (receipt_ref or "").strip():
        raise ValueError("receipt_ref is required when receipt_type is witness")
    receipt = HumanWorkReceipt(
        receipt_id=f"hwr_{uuid.uuid4().hex[:12]}",
        recorded_at_utc=_now_iso(),
        actor=actor,
        summary=summary,
        receipt_type=receipt_type,  # type: ignore[arg-type]
        receipt_ref=receipt_ref,
        observability=observability,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        subject_refs=subject_refs or [],
        artifact_refs=artifact_refs or [],
        review_required=review_required,
        metadata=metadata or {},
    )
    receipt_text = receipt_ref or _human_work_receipt_text(receipt)
    path = log_path or DEFAULT_HUMAN_WORK_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        work_receipts = list(row.get("work_receipts") or [])
        work_receipts.append(asdict(receipt))
        row["work_receipts"] = work_receipts
        row["receipt"] = row.get("receipt") or receipt_text
        if row.get("receipt_type") in {None, "none", "note"}:
            row["receipt_type"] = receipt_type
        row["confidence"] = confidence
        row["observability"] = observability
        if review_required:
            row["sample_for_review"] = True
        row["updated_at_utc"] = _now_iso()

        events = list(row.get("interaction_events") or [])
        events.append(
            {
                "ts": receipt.recorded_at_utc,
                "actor": actor,
                "event_type": "human_work_receipt_attested",
                "surface": row.get("interaction_surface") or "mixed",
                "summary": summary,
                "artifact_refs": receipt.artifact_refs,
                "blocker": None,
            }
        )
        row["interaction_events"] = events

        if receipt.artifact_refs:
            existing = list(row.get("artifact_refs") or [])
            row["artifact_refs"] = list(dict.fromkeys(existing + receipt.artifact_refs))
        if (
            receipt_type == "note"
            and not receipt.artifact_refs
            and not receipt.receipt_ref
            and observability in {"human_attested", "unobservable"}
        ):
            row["sample_for_review"] = True
        return row

    return _replace_session(path, session_id, mutate)


def human_work_summary(session: HumanWorkSession) -> dict[str, Any]:
    return asdict(session)


def human_work_resource(session: HumanWorkSession) -> KernelResource:
    """Project a human-work session into the common resource envelope.

    The human-work JSONL row remains canonical. The resource view gives
    adapters, dashboards, migration checks, and conformance fixtures a common
    object shape for A2H coordination, receipt state, and role follow-up.
    """
    labels = {
        "state": session.state,
        "work_mode": session.work_mode,
        "bottleneck_class": session.bottleneck_class,
        "human_actor": session.human_actor,
        "requested_by": session.requested_by,
        "receipt_required": str(session.receipt_required).lower(),
        "agent_followup_required": str(session.agent_followup_required).lower(),
        "work_receipt_present": str(bool(session.work_receipts)).lower(),
    }
    if session.agent_counterparty_role:
        labels["agent_counterparty_role"] = session.agent_counterparty_role
    if session.receipt_type:
        labels["receipt_type"] = session.receipt_type

    links = [
        {"rel": "requested_by", "href": session.requested_by},
        {"rel": "human_actor", "href": session.human_actor},
    ]
    for role in session.collaborating_roles:
        links.append({"rel": "collaborating_role", "href": role})
    for ref in session.artifact_refs:
        links.append({"rel": "artifact", "href": ref})
    if session.obligation_id:
        links.append({"rel": "obligation", "href": session.obligation_id})
    if session.integration_ref:
        links.append({"rel": "integration", "href": session.integration_ref})
    if session.agent_counterparty_role:
        links.append(
            {
                "rel": "agent_counterparty_role",
                "href": session.agent_counterparty_role,
            }
        )
    if session.agent_followup_ref:
        links.append({"rel": "agent_followup", "href": session.agent_followup_ref})
    for receipt in session.work_receipts:
        if receipt.get("receipt_ref"):
            links.append({"rel": "receipt_ref", "href": receipt["receipt_ref"]})
        for ref in receipt.get("subject_refs") or []:
            links.append({"rel": "subject", "href": ref})
        for ref in receipt.get("artifact_refs") or []:
            links.append({"rel": "receipt_artifact", "href": ref})

    return make_resource(
        kind="HumanWorkSession",
        name=session.session_id,
        resource_id=session.session_id,
        tenant_id=session.tenant_id,
        project_id=session.project_id,
        stability="alpha",
        labels=labels,
        annotations={
            key: str(value)
            for key, value in session.metadata.items()
            if isinstance(key, str) and value is not None
        },
        spec={
            "requested_by": session.requested_by,
            "human_actor": session.human_actor,
            "objective": session.objective,
            "work_mode": session.work_mode,
            "bottleneck_class": session.bottleneck_class,
            "collaborating_roles": session.collaborating_roles,
            "artifact_refs": session.artifact_refs,
            "observability": session.observability,
            "receipt_required": session.receipt_required,
            "receipt_type": session.receipt_type,
            "confidence": session.confidence,
            "sample_for_review": session.sample_for_review,
            "obligation_id": session.obligation_id,
            "deadline_utc": session.deadline_utc,
            "interaction_surface": session.interaction_surface,
            "agent_counterparty_role": session.agent_counterparty_role,
            "human_deliverable": session.human_deliverable,
            "agent_followup_required": session.agent_followup_required,
            "agent_followup_ref": session.agent_followup_ref,
        },
        status={
            "state": session.state,
            "receipt_present": bool((session.receipt or "").strip()),
            "receipt": session.receipt,
            "completion_summary": session.completion_summary,
            "integration_ref": session.integration_ref,
            "notes_count": len(session.notes),
            "interaction_event_count": len(session.interaction_events),
            "work_receipt_count": len(session.work_receipts),
            "work_receipts": session.work_receipts,
            "created_at_utc": session.created_at_utc,
            "updated_at_utc": session.updated_at_utc,
        },
        links=links,
    )


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
    list_parser.add_argument("--resource", action="store_true", help="render resource envelopes")

    followup_parser = sub.add_parser("followup")
    followup_parser.add_argument("--agent-counterparty-role")
    followup_parser.add_argument("--log-path", type=Path)
    followup_parser.add_argument("--resource", action="store_true", help="render resource envelopes")

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

    receipt_parser = sub.add_parser("receipt")
    receipt_parser.add_argument("session_id")
    receipt_parser.add_argument("--actor", required=True)
    receipt_parser.add_argument("--summary", required=True)
    receipt_parser.add_argument("--receipt-type", default="note")
    receipt_parser.add_argument("--receipt-ref")
    receipt_parser.add_argument("--subject-ref", action="append", default=[])
    receipt_parser.add_argument("--artifact-ref", action="append", default=[])
    receipt_parser.add_argument("--confidence", default="medium")
    receipt_parser.add_argument("--observability", default="human_attested")
    receipt_parser.add_argument("--review-required", action="store_true")
    receipt_parser.add_argument("--log-path", type=Path)

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
            if args.resource:
                print(
                    json.dumps(
                        human_work_resource(session).as_dict(),
                        sort_keys=True,
                    )
                )
            else:
                print(json.dumps(human_work_summary(session), sort_keys=True))
        return 0
    if args.cmd == "followup":
        sessions = list_agent_followup_human_work_sessions(
            agent_counterparty_role=args.agent_counterparty_role,
            log_path=args.log_path,
        )
        for session in sessions:
            if args.resource:
                print(
                    json.dumps(
                        human_work_resource(session).as_dict(),
                        sort_keys=True,
                    )
                )
            else:
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
    if args.cmd == "receipt":
        session = append_human_work_receipt(
            args.session_id,
            actor=args.actor,
            summary=args.summary,
            receipt_type=args.receipt_type,
            receipt_ref=args.receipt_ref,
            subject_refs=args.subject_ref,
            artifact_refs=args.artifact_ref,
            confidence=args.confidence,
            observability=args.observability,
            review_required=args.review_required,
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
