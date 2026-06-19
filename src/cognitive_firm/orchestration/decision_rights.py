"""Incomplete-contract residual-rights owner.

A mandate is necessarily an incomplete contract: it cannot enumerate every
situation a role will face. When a mandate is *silent* on a situation, someone
still has to decide — and the kernel had no typed record of *who* that default
decider is. So "the mandate didn't cover this, so I decided" was invisible and
unaccountable.

This module adds two linked records:

- A :class:`ResidualRightAssignment` names, for a scope (a project, a resource
  class, a decision class, an operating unit, ...), which ``holder_role`` holds
  the **residual control right** — the default decider when no mandate clause
  applies. Reassignment supersedes the prior assignment for that scope, so the
  current holder is always unambiguous.
- A :class:`ResidualDecision` is opened by an actor who hit an *unspecified*
  situation. It cites the governing scope and records what was decided, by
  whom, and why. If the deciding actor's role does **not** match the active
  assignment's ``holder_role`` for that scope, the decision is still recorded —
  the situation was genuinely unspecified, so the kernel fails *open* — but it
  is flagged ``unauthorized`` so the irregularity is visible. A review then
  endorses, corrects, escalates, or marks it ``promote_to_mandate_clause``: the
  bridge back to a complete contract.

The kernel owns the typed assignment, the invocation record, and the review
lifecycle. The tenant owns the actual mandates. This serves Typed authority and
Accountable closure: residual-rights exercise becomes reviewable, and
``promote_to_mandate_clause`` is how a recurring gap gets closed.
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
from cognitive_firm.orchestration.authority_domains import (
    AuthorityDomain,
    resolve_authority_assignment_for_scope,
)
from cognitive_firm.orchestration.kernel_events import record_kernel_event
from cognitive_firm.orchestration.resource_envelope import KernelResource, make_resource


ScopeKind = Literal["project", "resource_class", "decision_class", "operating_unit"]
VALID_SCOPE_KINDS = {"project", "resource_class", "decision_class", "operating_unit"}

AssignmentStatus = Literal["active", "superseded"]
VALID_ASSIGNMENT_STATUSES = {"active", "superseded"}

DecisionStatus = Literal["recorded", "reviewed"]
VALID_DECISION_STATUSES = {"recorded", "reviewed"}

ReviewOutcome = Literal["endorsed", "corrected", "escalated", "promote_to_mandate_clause"]
VALID_REVIEW_OUTCOMES = {"endorsed", "corrected", "escalated", "promote_to_mandate_clause"}

DEFAULT_RESIDUAL_RIGHTS_LOG = ORG_ROOT_DIR / "decision_rights" / "residual_right_assignments.jsonl"
DEFAULT_RESIDUAL_DECISIONS_LOG = ORG_ROOT_DIR / "decision_rights" / "residual_decisions.jsonl"

HolderResolutionSource = Literal[
    "residual_right_assignment",
    "authority_domain",
    "unassigned",
]


@dataclass(frozen=True)
class ResidualRightAssignment:
    """Names the default decider for situations a mandate did not specify.

    Canonical state. Definition is idempotent on the ``(scope_kind, scope_ref)``
    pair: reassigning a scope supersedes the prior active assignment for it.
    """

    assignment_id: str
    scope_kind: ScopeKind
    scope_ref: str
    holder_role: str
    basis: str
    assigned_by: str
    created_at_utc: str
    updated_at_utc: str
    status: AssignmentStatus = "active"
    holder_actor: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def scope_key(self) -> tuple[str, str]:
        return (self.scope_kind, self.scope_ref)


@dataclass(frozen=True)
class ResidualDecision:
    """A decision taken in a situation no mandate clause covered.

    Canonical state. ``unauthorized`` is computed at record time by checking the
    deciding role against the active assignment's ``holder_role`` for the scope.
    """

    decision_id: str
    scope_kind: ScopeKind
    scope_ref: str
    deciding_actor: str
    deciding_role: str
    decision_summary: str
    rationale: str
    created_at_utc: str
    updated_at_utc: str
    status: DecisionStatus = "recorded"
    assignment_id: str | None = None
    unauthorized: bool = False
    reviewed_by: str | None = None
    review_outcome: ReviewOutcome | None = None
    review_notes: str = ""
    tenant_id: str | None = None
    project_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def scope_key(self) -> tuple[str, str]:
        return (self.scope_kind, self.scope_ref)


@dataclass(frozen=True)
class ResidualRightHolderResolution:
    """Read-side accountable-holder view for one residual-right scope.

    Explicit residual-right assignments remain the canonical authorization
    surface. Authority-domain fallback is projection-only: it explains the
    accountable role when an assignment is missing, but it does not create an
    assignment or authorize a residual decision by itself.
    """

    scope_kind: ScopeKind
    scope_ref: str
    source: HolderResolutionSource
    holder_role: str | None = None
    holder_actor: str | None = None
    holder_actors: list[str] = field(default_factory=list)
    assignment_id: str | None = None
    authority_domain_id: str | None = None
    authority_scope_kind: str | None = None
    authority_scope_id: str | None = None
    basis: str = ""
    issues: list[str] = field(default_factory=list)
    explicit_assignment: bool = False
    authoritative_for_decision_recording: bool = False
    projection_only: bool = True

    @property
    def resolved(self) -> bool:
        return self.holder_role is not None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"resolved": self.resolved}


# ---------------------------------------------------------------------------
# time + io helpers (kept module-local, matching the kernel's primitive style)
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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


def _validate(value: str, allowed: set[str], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"invalid {label} {value!r}; expected one of {sorted(allowed)}")
    return value


def _scope_ref_for(scope_kind: str, scope_ref: str) -> str:
    return f"{scope_kind}:{scope_ref}"


def _role_ref(role_id: str | None) -> str | None:
    if role_id is None:
        return None
    role_id = str(role_id).strip()
    if not role_id:
        return None
    if role_id.startswith("role."):
        return role_id
    return f"role.{role_id}"


def _authority_scope_kwargs(
    scope_kind: str,
    scope_ref: str,
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    operating_unit_id: str | None = None,
) -> dict[str, str | None]:
    kwargs: dict[str, str | None] = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "operating_unit_id": operating_unit_id,
        "resource_class": None,
        "decision_class": None,
    }
    if scope_kind == "project":
        kwargs["project_id"] = scope_ref
    elif scope_kind == "operating_unit":
        kwargs["operating_unit_id"] = scope_ref
    elif scope_kind == "resource_class":
        kwargs["resource_class"] = scope_ref
    elif scope_kind == "decision_class":
        kwargs["decision_class"] = scope_ref
    return kwargs


# ---------------------------------------------------------------------------
# assignments: who holds the residual control right for a scope
# ---------------------------------------------------------------------------


def assign_residual_right(
    *,
    scope_kind: ScopeKind | str,
    scope_ref: str,
    holder_role: str,
    basis: str,
    assigned_by: str,
    holder_actor: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    assignment_id: str | None = None,
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> ResidualRightAssignment:
    """Record which role holds the residual control right for one scope.

    Assignment is idempotent on the ``(scope_kind, scope_ref)`` pair: a new
    assignment for a scope that already has an active holder supersedes the
    prior assignment (its ``status`` becomes ``superseded``), so the current
    default decider for a scope is always unambiguous.
    """
    scope_kind = _validate(str(scope_kind), VALID_SCOPE_KINDS, "scope_kind")
    if not str(scope_ref).strip():
        raise ValueError("scope_ref is required")
    if not str(holder_role).strip():
        raise ValueError("holder_role is required")
    if not str(basis).strip():
        raise ValueError("basis is required: residual rights need a stated reason")
    if not str(assigned_by).strip():
        raise ValueError("assigned_by is required")

    path = log_path or DEFAULT_RESIDUAL_RIGHTS_LOG
    rows = _read_jsonl(path)
    now = _now_iso()
    superseded: list[str] = []
    next_rows: list[dict[str, Any]] = []
    for row in rows:
        is_match = (
            row.get("scope_kind") == scope_kind
            and row.get("scope_ref") == str(scope_ref).strip()
            and row.get("status") == "active"
        )
        if is_match:
            row = dict(row)
            row["status"] = "superseded"
            row["updated_at_utc"] = now
            superseded.append(str(row.get("assignment_id")))
        next_rows.append(row)

    assignment = ResidualRightAssignment(
        assignment_id=assignment_id or f"rra_{uuid.uuid4().hex[:12]}",
        scope_kind=scope_kind,  # type: ignore[arg-type]
        scope_ref=str(scope_ref).strip(),
        holder_role=str(holder_role).strip(),
        basis=str(basis).strip(),
        assigned_by=str(assigned_by).strip(),
        created_at_utc=now,
        updated_at_utc=now,
        status="active",
        holder_actor=(holder_actor.strip() if holder_actor and holder_actor.strip() else None),
        tenant_id=tenant_id,
        project_id=project_id,
        metadata=dict(metadata or {}),
    )
    _write_jsonl(path, [*next_rows, assignment.as_dict()])
    record_kernel_event(
        actor=assigned_by,
        verb="residual_right.assigned",
        object_ref=f"residual_right_assignment:{assignment.assignment_id}",
        subject_ref=_scope_ref_for(scope_kind, assignment.scope_ref),
        tenant_id=tenant_id,
        project_id=project_id,
        idempotency_key=f"residual_right.assigned:{assignment.assignment_id}",
        payload={
            "scope_kind": scope_kind,
            "scope_ref": assignment.scope_ref,
            "holder_role": assignment.holder_role,
            "holder_actor": assignment.holder_actor,
            "basis": assignment.basis,
            "superseded": superseded,
        },
        log_path=kernel_events_log,
    )
    return assignment


def list_residual_right_assignments(
    *,
    scope_kind: ScopeKind | str | None = None,
    scope_ref: str | None = None,
    holder_role: str | None = None,
    status: AssignmentStatus | str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> list[ResidualRightAssignment]:
    """List residual-right assignments, optionally filtered."""
    if scope_kind is not None:
        scope_kind = _validate(str(scope_kind), VALID_SCOPE_KINDS, "scope_kind")
    if status is not None:
        status = _validate(str(status), VALID_ASSIGNMENT_STATUSES, "status")
    out: list[ResidualRightAssignment] = []
    for row in _read_jsonl(log_path or DEFAULT_RESIDUAL_RIGHTS_LOG):
        assignment = ResidualRightAssignment(**row)
        if scope_kind is not None and assignment.scope_kind != scope_kind:
            continue
        if scope_ref is not None and assignment.scope_ref != scope_ref:
            continue
        if holder_role is not None and assignment.holder_role != holder_role:
            continue
        if status is not None and assignment.status != status:
            continue
        if tenant_id is not None and assignment.tenant_id != tenant_id:
            continue
        if project_id is not None and assignment.project_id != project_id:
            continue
        out.append(assignment)
    return out


def get_residual_right_assignment(
    assignment_id: str,
    *,
    log_path: Path | None = None,
) -> ResidualRightAssignment | None:
    """Return one assignment by id, or ``None`` if it is not registered."""
    for assignment in list_residual_right_assignments(log_path=log_path):
        if assignment.assignment_id == assignment_id:
            return assignment
    return None


def get_residual_right_holder(
    scope_kind: ScopeKind | str,
    scope_ref: str,
    *,
    log_path: Path | None = None,
) -> ResidualRightAssignment | None:
    """Return the *active* residual-right holder for a scope, or ``None``.

    A ``None`` result means the scope has no named default decider: any residual
    decision recorded against it will be flagged ``unauthorized``.
    """
    scope_kind = _validate(str(scope_kind), VALID_SCOPE_KINDS, "scope_kind")
    for assignment in list_residual_right_assignments(
        scope_kind=scope_kind,
        scope_ref=scope_ref,
        status="active",
        log_path=log_path,
    ):
        return assignment
    return None


def resolve_residual_right_holder(
    scope_kind: ScopeKind | str,
    scope_ref: str,
    *,
    log_path: Path | None = None,
    authority_domains: list[AuthorityDomain] | None = None,
    actor_membership_log: Path | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    operating_unit_id: str | None = None,
    now: datetime | None = None,
) -> ResidualRightHolderResolution:
    """Resolve the accountable holder view for one residual-right scope.

    The canonical answer is still an active residual-right assignment. If the
    scope has no assignment, authority domains can provide a projection-only
    accountable role so operators can see who should close the gap without
    silently granting residual decision rights.
    """
    scope_kind = _validate(str(scope_kind), VALID_SCOPE_KINDS, "scope_kind")
    scope_ref = str(scope_ref).strip()
    if not scope_ref:
        raise ValueError("scope_ref is required")

    assignment = get_residual_right_holder(
        scope_kind,
        scope_ref,
        log_path=log_path,
    )
    if assignment is not None:
        holder_actors = [assignment.holder_actor] if assignment.holder_actor else []
        return ResidualRightHolderResolution(
            scope_kind=scope_kind,  # type: ignore[arg-type]
            scope_ref=scope_ref,
            source="residual_right_assignment",
            holder_role=assignment.holder_role,
            holder_actor=assignment.holder_actor,
            holder_actors=holder_actors,
            assignment_id=assignment.assignment_id,
            basis=assignment.basis,
            explicit_assignment=True,
            authoritative_for_decision_recording=True,
            projection_only=False,
        )

    issues = ["no active residual-right assignment for scope"]
    if authority_domains is None:
        issues.append("authority domains were not supplied")
        return ResidualRightHolderResolution(
            scope_kind=scope_kind,  # type: ignore[arg-type]
            scope_ref=scope_ref,
            source="unassigned",
            issues=issues,
        )
    if not authority_domains:
        issues.append("authority domains were empty")
        return ResidualRightHolderResolution(
            scope_kind=scope_kind,  # type: ignore[arg-type]
            scope_ref=scope_ref,
            source="unassigned",
            issues=issues,
        )

    resolution = resolve_authority_assignment_for_scope(
        authority_domains,
        actor_membership_log=actor_membership_log,
        now=now,
        **_authority_scope_kwargs(
            scope_kind,
            scope_ref,
            tenant_id=tenant_id,
            project_id=project_id,
            operating_unit_id=operating_unit_id,
        ),
    )
    holder_role = _role_ref(resolution.authority_role_id)
    if holder_role is None:
        issues.append("no authority domain resolved for residual-right scope")
        return ResidualRightHolderResolution(
            scope_kind=scope_kind,  # type: ignore[arg-type]
            scope_ref=scope_ref,
            source="unassigned",
            issues=issues,
        )
    holder_actors = list(resolution.actor_ids)
    return ResidualRightHolderResolution(
        scope_kind=scope_kind,  # type: ignore[arg-type]
        scope_ref=scope_ref,
        source="authority_domain",
        holder_role=holder_role,
        holder_actor=holder_actors[0] if len(holder_actors) == 1 else None,
        holder_actors=holder_actors,
        authority_domain_id=resolution.domain_id,
        authority_scope_kind=resolution.scope_kind,
        authority_scope_id=resolution.scope_id,
        basis=(
            "projection from authority domain; create an explicit "
            "residual-right assignment to make it canonical"
        ),
        issues=issues,
        explicit_assignment=False,
        authoritative_for_decision_recording=False,
        projection_only=True,
    )


def residual_right_assignment_resource(
    assignment: ResidualRightAssignment,
) -> KernelResource:
    """Project a residual-right assignment into the common resource envelope.

    The JSONL row remains canonical. The resource view gives adapters,
    dashboards, migration checks, and conformance fixtures a common object
    shape for the default-decider contract.
    """
    labels = {
        "scope_kind": assignment.scope_kind,
        "holder_role": assignment.holder_role,
        "status": assignment.status,
    }
    if assignment.holder_actor:
        labels["holder_actor"] = assignment.holder_actor
    links = [
        {"rel": "scope", "href": _scope_ref_for(assignment.scope_kind, assignment.scope_ref)},
        {"rel": "holder_role", "href": assignment.holder_role},
        {"rel": "assigned_by", "href": assignment.assigned_by},
    ]
    if assignment.holder_actor:
        links.append({"rel": "holder_actor", "href": assignment.holder_actor})
    return make_resource(
        kind="ResidualRightAssignment",
        name=assignment.assignment_id,
        resource_id=assignment.assignment_id,
        tenant_id=assignment.tenant_id,
        project_id=assignment.project_id,
        stability="alpha",
        labels=labels,
        annotations={
            key: str(value)
            for key, value in assignment.metadata.items()
            if isinstance(key, str) and value is not None
        },
        spec={
            "scope_kind": assignment.scope_kind,
            "scope_ref": assignment.scope_ref,
            "holder_role": assignment.holder_role,
            "holder_actor": assignment.holder_actor,
            "basis": assignment.basis,
            "assigned_by": assignment.assigned_by,
        },
        status={
            "status": assignment.status,
            "created_at_utc": assignment.created_at_utc,
            "updated_at_utc": assignment.updated_at_utc,
        },
        links=links,
    )


# ---------------------------------------------------------------------------
# residual decisions: exercising the residual right in an unspecified situation
# ---------------------------------------------------------------------------


def record_residual_decision(
    *,
    scope_kind: ScopeKind | str,
    scope_ref: str,
    deciding_actor: str,
    deciding_role: str,
    decision_summary: str,
    rationale: str,
    tenant_id: str | None = None,
    project_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    decision_id: str | None = None,
    log_path: Path | None = None,
    assignments_log: Path | None = None,
    kernel_events_log: Path | None = None,
) -> ResidualDecision:
    """Record a decision taken in a situation no mandate clause covered.

    The kernel resolves the active residual-right holder for the scope and
    compares it to ``deciding_role``. If they do not match — including the case
    where the scope has no assignment at all — the decision is **still
    recorded** (the situation was genuinely unspecified, so the kernel fails
    open) but flagged ``unauthorized`` so the irregularity is reviewable.
    """
    scope_kind = _validate(str(scope_kind), VALID_SCOPE_KINDS, "scope_kind")
    if not str(scope_ref).strip():
        raise ValueError("scope_ref is required")
    if not str(deciding_actor).strip():
        raise ValueError("deciding_actor is required")
    if not str(deciding_role).strip():
        raise ValueError("deciding_role is required")
    if not str(decision_summary).strip():
        raise ValueError("decision_summary is required")
    if not str(rationale).strip():
        raise ValueError("rationale is required: a residual decision must say why")

    holder = get_residual_right_holder(
        scope_kind, str(scope_ref).strip(), log_path=assignments_log
    )
    unauthorized = holder is None or holder.holder_role != str(deciding_role).strip()

    now = _now_iso()
    decision = ResidualDecision(
        decision_id=decision_id or f"rd_{uuid.uuid4().hex[:12]}",
        scope_kind=scope_kind,  # type: ignore[arg-type]
        scope_ref=str(scope_ref).strip(),
        deciding_actor=str(deciding_actor).strip(),
        deciding_role=str(deciding_role).strip(),
        decision_summary=str(decision_summary).strip(),
        rationale=str(rationale).strip(),
        created_at_utc=now,
        updated_at_utc=now,
        status="recorded",
        assignment_id=holder.assignment_id if holder is not None else None,
        unauthorized=unauthorized,
        tenant_id=tenant_id,
        project_id=project_id,
        metadata=dict(metadata or {}),
    )
    _append_jsonl(log_path or DEFAULT_RESIDUAL_DECISIONS_LOG, decision.as_dict())
    record_kernel_event(
        actor=deciding_actor,
        verb="residual_decision.recorded",
        object_ref=f"residual_decision:{decision.decision_id}",
        subject_ref=_scope_ref_for(scope_kind, decision.scope_ref),
        tenant_id=tenant_id,
        project_id=project_id,
        idempotency_key=f"residual_decision.recorded:{decision.decision_id}",
        payload={
            "scope_kind": scope_kind,
            "scope_ref": decision.scope_ref,
            "deciding_role": decision.deciding_role,
            "assignment_id": decision.assignment_id,
            "unauthorized": decision.unauthorized,
            "decision_summary": decision.decision_summary,
        },
        log_path=kernel_events_log,
    )
    return decision


def review_residual_decision(
    decision_id: str,
    *,
    reviewed_by: str,
    review_outcome: ReviewOutcome | str,
    review_notes: str = "",
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> ResidualDecision:
    """Review a recorded residual decision.

    A decision moves ``recorded -> reviewed`` exactly once. ``review_outcome``
    is one of ``endorsed``, ``corrected``, ``escalated``, or
    ``promote_to_mandate_clause`` — the last marks the decision as a candidate
    for closing the contract gap by adding a mandate clause.
    """
    outcome = _validate(str(review_outcome), VALID_REVIEW_OUTCOMES, "review_outcome")
    if not str(reviewed_by).strip():
        raise ValueError("reviewed_by is required")

    path = log_path or DEFAULT_RESIDUAL_DECISIONS_LOG
    rows = _read_jsonl(path)
    updated: ResidualDecision | None = None
    next_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("decision_id") == decision_id:
            current = str(row.get("status"))
            if current != "recorded":
                raise ValueError(
                    f"illegal transition {current} -> reviewed; "
                    "a residual decision can only be reviewed once"
                )
            row = dict(row)
            row["status"] = "reviewed"
            row["reviewed_by"] = str(reviewed_by).strip()
            row["review_outcome"] = outcome
            row["review_notes"] = str(review_notes or "")
            row["updated_at_utc"] = _now_iso()
            updated = ResidualDecision(**row)
        next_rows.append(row)
    if updated is None:
        raise KeyError(f"residual decision not found: {decision_id}")
    _write_jsonl(path, next_rows)
    record_kernel_event(
        actor=reviewed_by,
        verb="residual_decision.reviewed",
        object_ref=f"residual_decision:{updated.decision_id}",
        subject_ref=_scope_ref_for(updated.scope_kind, updated.scope_ref),
        tenant_id=updated.tenant_id,
        project_id=updated.project_id,
        idempotency_key=f"residual_decision.reviewed:{updated.decision_id}",
        payload={
            "scope_kind": updated.scope_kind,
            "scope_ref": updated.scope_ref,
            "review_outcome": updated.review_outcome,
            "unauthorized": updated.unauthorized,
            "promote_candidate": updated.review_outcome == "promote_to_mandate_clause",
        },
        log_path=kernel_events_log,
    )
    return updated


def list_residual_decisions(
    *,
    scope_kind: ScopeKind | str | None = None,
    scope_ref: str | None = None,
    status: DecisionStatus | str | None = None,
    review_outcome: ReviewOutcome | str | None = None,
    unauthorized: bool | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> list[ResidualDecision]:
    """List residual decisions, optionally filtered by scope/status/flag."""
    if scope_kind is not None:
        scope_kind = _validate(str(scope_kind), VALID_SCOPE_KINDS, "scope_kind")
    if status is not None:
        status = _validate(str(status), VALID_DECISION_STATUSES, "status")
    if review_outcome is not None:
        review_outcome = _validate(str(review_outcome), VALID_REVIEW_OUTCOMES, "review_outcome")
    out: list[ResidualDecision] = []
    for row in _read_jsonl(log_path or DEFAULT_RESIDUAL_DECISIONS_LOG):
        decision = ResidualDecision(**row)
        if scope_kind is not None and decision.scope_kind != scope_kind:
            continue
        if scope_ref is not None and decision.scope_ref != scope_ref:
            continue
        if status is not None and decision.status != status:
            continue
        if review_outcome is not None and decision.review_outcome != review_outcome:
            continue
        if unauthorized is not None and decision.unauthorized != unauthorized:
            continue
        if tenant_id is not None and decision.tenant_id != tenant_id:
            continue
        if project_id is not None and decision.project_id != project_id:
            continue
        out.append(decision)
    return out


def get_residual_decision(
    decision_id: str,
    *,
    log_path: Path | None = None,
) -> ResidualDecision | None:
    """Return one residual decision by id, or ``None`` if not found."""
    for decision in list_residual_decisions(log_path=log_path):
        if decision.decision_id == decision_id:
            return decision
    return None


def residual_decision_resource(decision: ResidualDecision) -> KernelResource:
    """Project a residual decision into the common resource envelope.

    The decision JSONL row remains canonical. The projection exposes
    fail-open authorization flags and review outcomes in a common object shape
    without changing the residual-decision lifecycle.
    """
    labels = {
        "scope_kind": decision.scope_kind,
        "deciding_role": decision.deciding_role,
        "status": decision.status,
        "unauthorized": str(decision.unauthorized).lower(),
    }
    if decision.review_outcome:
        labels["review_outcome"] = decision.review_outcome
    links = [
        {"rel": "scope", "href": _scope_ref_for(decision.scope_kind, decision.scope_ref)},
        {"rel": "deciding_actor", "href": decision.deciding_actor},
        {"rel": "deciding_role", "href": decision.deciding_role},
    ]
    if decision.assignment_id:
        links.append(
            {
                "rel": "residual_right_assignment",
                "href": f"residual_right_assignment:{decision.assignment_id}",
            }
        )
    if decision.reviewed_by:
        links.append({"rel": "reviewed_by", "href": decision.reviewed_by})
    return make_resource(
        kind="ResidualDecision",
        name=decision.decision_id,
        resource_id=decision.decision_id,
        tenant_id=decision.tenant_id,
        project_id=decision.project_id,
        stability="alpha",
        labels=labels,
        annotations={
            key: str(value)
            for key, value in decision.metadata.items()
            if isinstance(key, str) and value is not None
        },
        spec={
            "scope_kind": decision.scope_kind,
            "scope_ref": decision.scope_ref,
            "deciding_actor": decision.deciding_actor,
            "deciding_role": decision.deciding_role,
            "decision_summary": decision.decision_summary,
            "rationale": decision.rationale,
            "assignment_id": decision.assignment_id,
        },
        status={
            "status": decision.status,
            "unauthorized": decision.unauthorized,
            "reviewed_by": decision.reviewed_by,
            "review_outcome": decision.review_outcome,
            "review_notes": decision.review_notes,
            "created_at_utc": decision.created_at_utc,
            "updated_at_utc": decision.updated_at_utc,
        },
        links=links,
    )


# ---------------------------------------------------------------------------
# read model
# ---------------------------------------------------------------------------


def summarize_decision_rights(
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
    assignments_log: Path | None = None,
) -> dict[str, Any]:
    """Derive a health view over residual rights and residual decisions.

    This is a read model — it owns no facts and can be rebuilt at any time. It
    surfaces the four things a governance reviewer needs to act on:

    - scopes that residual decisions touched but that have **no active
      assignment** (no named default decider);
    - residual decisions flagged ``unauthorized``;
    - residual decisions still ``recorded`` and awaiting review;
    - reviewed decisions marked ``promote_to_mandate_clause`` — the candidates
      for closing the contract gap with a mandate clause.
    """
    assignments = list_residual_right_assignments(
        status="active",
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=assignments_log,
    )
    decisions = list_residual_decisions(
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=log_path,
    )
    assigned_scopes = {a.scope_key() for a in assignments}

    unassigned_scopes: list[dict[str, str]] = []
    seen_unassigned: set[tuple[str, str]] = set()
    for decision in decisions:
        key = decision.scope_key()
        if key in assigned_scopes or key in seen_unassigned:
            continue
        seen_unassigned.add(key)
        unassigned_scopes.append({"scope_kind": key[0], "scope_ref": key[1]})

    unauthorized = [d for d in decisions if d.unauthorized]
    awaiting_review = [d for d in decisions if d.status == "recorded"]
    promote_candidates = [
        d for d in decisions if d.review_outcome == "promote_to_mandate_clause"
    ]

    return {
        "active_assignments": len(assignments),
        "total_decisions": len(decisions),
        "unassigned_scopes": sorted(
            unassigned_scopes, key=lambda s: (s["scope_kind"], s["scope_ref"])
        ),
        "unassigned_scope_count": len(unassigned_scopes),
        "unauthorized_decision_count": len(unauthorized),
        "unauthorized_decision_ids": sorted(d.decision_id for d in unauthorized),
        "awaiting_review_count": len(awaiting_review),
        "awaiting_review_ids": sorted(d.decision_id for d in awaiting_review),
        "promote_to_mandate_candidate_count": len(promote_candidates),
        "promote_to_mandate_candidate_ids": sorted(
            d.decision_id for d in promote_candidates
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage cognitive-firm residual decision rights."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    assign = sub.add_parser("assign", help="assign a residual-right holder for a scope")
    assign.add_argument("--scope-kind", required=True)
    assign.add_argument("--scope-ref", required=True)
    assign.add_argument("--holder-role", required=True)
    assign.add_argument("--basis", required=True)
    assign.add_argument("--assigned-by", required=True)
    assign.add_argument("--holder-actor")
    assign.add_argument("--tenant-id")
    assign.add_argument("--project-id")
    assign.add_argument("--log-path", type=Path)
    assign.add_argument("--kernel-events-log", type=Path)

    holder = sub.add_parser("holder", help="show the active holder for a scope")
    holder.add_argument("--scope-kind", required=True)
    holder.add_argument("--scope-ref", required=True)
    holder.add_argument("--log-path", type=Path)
    holder.add_argument(
        "--resolve-authority",
        action="store_true",
        help="include authority-domain holder resolution when no assignment exists",
    )
    holder.add_argument("--org-root", type=Path)
    holder.add_argument("--actor-membership-log", type=Path)
    holder.add_argument("--tenant-id")
    holder.add_argument("--project-id")
    holder.add_argument("--operating-unit-id")

    list_assignments = sub.add_parser("list-assignments")
    list_assignments.add_argument("--scope-kind")
    list_assignments.add_argument("--scope-ref")
    list_assignments.add_argument("--holder-role")
    list_assignments.add_argument("--status")
    list_assignments.add_argument("--log-path", type=Path)
    list_assignments.add_argument("--resource", action="store_true", help="render resource envelopes")

    record = sub.add_parser("record", help="record a decision on an unspecified situation")
    record.add_argument("--scope-kind", required=True)
    record.add_argument("--scope-ref", required=True)
    record.add_argument("--deciding-actor", required=True)
    record.add_argument("--deciding-role", required=True)
    record.add_argument("--decision-summary", required=True)
    record.add_argument("--rationale", required=True)
    record.add_argument("--tenant-id")
    record.add_argument("--project-id")
    record.add_argument("--log-path", type=Path)
    record.add_argument("--assignments-log", type=Path)
    record.add_argument("--kernel-events-log", type=Path)

    review = sub.add_parser("review", help="review a recorded residual decision")
    review.add_argument("decision_id")
    review.add_argument("--reviewed-by", required=True)
    review.add_argument("--review-outcome", required=True)
    review.add_argument("--review-notes", default="")
    review.add_argument("--log-path", type=Path)
    review.add_argument("--kernel-events-log", type=Path)

    list_decisions = sub.add_parser("list-decisions")
    list_decisions.add_argument("--scope-kind")
    list_decisions.add_argument("--scope-ref")
    list_decisions.add_argument("--status")
    list_decisions.add_argument("--review-outcome")
    list_decisions.add_argument("--unauthorized", action="store_true")
    list_decisions.add_argument("--log-path", type=Path)
    list_decisions.add_argument("--resource", action="store_true", help="render resource envelopes")

    summarize = sub.add_parser("summary", help="read model over residual decision rights")
    summarize.add_argument("--tenant-id")
    summarize.add_argument("--project-id")
    summarize.add_argument("--log-path", type=Path)
    summarize.add_argument("--assignments-log", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "assign":
        assignment = assign_residual_right(
            scope_kind=args.scope_kind,
            scope_ref=args.scope_ref,
            holder_role=args.holder_role,
            basis=args.basis,
            assigned_by=args.assigned_by,
            holder_actor=args.holder_actor,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
            kernel_events_log=args.kernel_events_log,
        )
        print(json.dumps(assignment.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "holder":
        assignment = get_residual_right_holder(
            args.scope_kind, args.scope_ref, log_path=args.log_path
        )
        if args.resolve_authority:
            from cognitive_firm.orchestration.authority_domains import (
                load_authority_domains,
            )

            resolution = resolve_residual_right_holder(
                args.scope_kind,
                args.scope_ref,
                log_path=args.log_path,
                authority_domains=load_authority_domains(args.org_root),
                actor_membership_log=args.actor_membership_log,
                tenant_id=args.tenant_id,
                project_id=args.project_id,
                operating_unit_id=args.operating_unit_id,
            )
            print(
                json.dumps(
                    {
                        "holder": assignment.as_dict() if assignment else None,
                        "holder_resolution": resolution.as_dict(),
                        "boundary": {
                            "authority_domain_fallback": "projection_only",
                            "creates_residual_right_assignment": False,
                            "authorizes_residual_decision": (
                                resolution.authoritative_for_decision_recording
                            ),
                        },
                    },
                    sort_keys=True,
                )
            )
        else:
            print(json.dumps(assignment.as_dict() if assignment else {}, sort_keys=True))
        return 0
    if args.cmd == "list-assignments":
        for assignment in list_residual_right_assignments(
            scope_kind=args.scope_kind,
            scope_ref=args.scope_ref,
            holder_role=args.holder_role,
            status=args.status,
            log_path=args.log_path,
        ):
            if args.resource:
                print(
                    json.dumps(
                        residual_right_assignment_resource(assignment).as_dict(),
                        sort_keys=True,
                    )
                )
            else:
                print(json.dumps(assignment.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "record":
        decision = record_residual_decision(
            scope_kind=args.scope_kind,
            scope_ref=args.scope_ref,
            deciding_actor=args.deciding_actor,
            deciding_role=args.deciding_role,
            decision_summary=args.decision_summary,
            rationale=args.rationale,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
            assignments_log=args.assignments_log,
            kernel_events_log=args.kernel_events_log,
        )
        print(json.dumps(decision.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "review":
        decision = review_residual_decision(
            args.decision_id,
            reviewed_by=args.reviewed_by,
            review_outcome=args.review_outcome,
            review_notes=args.review_notes,
            log_path=args.log_path,
            kernel_events_log=args.kernel_events_log,
        )
        print(json.dumps(decision.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "list-decisions":
        for decision in list_residual_decisions(
            scope_kind=args.scope_kind,
            scope_ref=args.scope_ref,
            status=args.status,
            review_outcome=args.review_outcome,
            unauthorized=True if args.unauthorized else None,
            log_path=args.log_path,
        ):
            if args.resource:
                print(
                    json.dumps(
                        residual_decision_resource(decision).as_dict(),
                        sort_keys=True,
                    )
                )
            else:
                print(json.dumps(decision.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "summary":
        print(
            json.dumps(
                summarize_decision_rights(
                    tenant_id=args.tenant_id,
                    project_id=args.project_id,
                    log_path=args.log_path,
                    assignments_log=args.assignments_log,
                ),
                sort_keys=True,
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
