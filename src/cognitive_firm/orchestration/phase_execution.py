"""Phase-separated execution overlay.

This is a thin execution recipe over existing kernel surfaces. It records
Strategy -> Execution -> Verification directives and verifier feedback, then
applies bounded retry budget decay after failed verification. It does not run
agents or own a development framework.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.learning_transition_compiler import (
    LearningTransitionCandidate,
    LearningTransitionKind,
)
from cognitive_firm.orchestration.resource_envelope import KernelResource, make_resource


PhaseName = Literal["strategy", "execution", "verification"]
PlanStatus = Literal["active", "passed", "failed", "blocked", "cancelled"]
PhaseDirectiveStatus = Literal["recorded", "superseded"]
VerificationVerdict = Literal["passed", "failed", "blocked", "inconclusive"]

VALID_PHASES = {"strategy", "execution", "verification"}
VALID_PLAN_STATUSES = {"active", "passed", "failed", "blocked", "cancelled"}
VALID_VERDICTS = {"passed", "failed", "blocked", "inconclusive"}
VALID_LEARNING_TRANSITION_KINDS = {
    "evidence_gap",
    "project_charter_update",
    "mandate_review",
    "human_work_session",
    "forecast_contract",
    "route_policy_change",
    "action_impact_repair",
    "role_review",
    "source_repair",
}

DEFAULT_PHASE_EXECUTION_LOG = ORG_ROOT_DIR / "phase_execution" / "phase_execution.jsonl"


@dataclass(frozen=True)
class PhaseDirective:
    directive_id: str
    plan_id: str
    created_at_utc: str
    phase: PhaseName | str
    issued_by: str
    directive: str
    status: PhaseDirectiveStatus | str = "recorded"
    run_id: str | None = None
    work_id: str | None = None
    budget_units: float | None = None
    evidence_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VerificationFeedback:
    feedback_id: str
    plan_id: str
    created_at_utc: str
    verifier_role: str
    verdict: VerificationVerdict | str
    rationale: str
    evidence_refs: list[str] = field(default_factory=list)
    failed_phase: PhaseName | str = "execution"
    retry_budget_before: float | None = None
    retry_budget_after: float | None = None
    budget_decay: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PhaseExecutionPlan:
    plan_id: str
    created_at_utc: str
    updated_at_utc: str
    objective: str
    owner_role: str
    status: PlanStatus | str = "active"
    current_phase: PhaseName | str = "strategy"
    remaining_budget_units: float = 1.0
    max_attempts: int = 3
    attempts: int = 0
    run_id: str | None = None
    work_id: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    directives: list[dict[str, Any]] = field(default_factory=list)
    feedback: list[dict[str, Any]] = field(default_factory=list)
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def start_phase_execution_plan(
    *,
    objective: str,
    owner_role: str,
    total_budget_units: float = 1.0,
    max_attempts: int = 3,
    run_id: str | None = None,
    work_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    plan_id: str | None = None,
    log_path: Path | None = None,
) -> PhaseExecutionPlan:
    if not objective.strip():
        raise ValueError("objective is required")
    if not owner_role.strip():
        raise ValueError("owner_role is required")
    if total_budget_units <= 0:
        raise ValueError("total_budget_units must be positive")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    now = _now_iso()
    plan = PhaseExecutionPlan(
        plan_id=plan_id or f"pex_{uuid.uuid4().hex[:12]}",
        created_at_utc=now,
        updated_at_utc=now,
        objective=objective,
        owner_role=owner_role,
        remaining_budget_units=float(total_budget_units),
        max_attempts=max_attempts,
        run_id=run_id,
        work_id=work_id,
        tenant_id=tenant_id,
        project_id=project_id,
        metadata=metadata or {},
    )
    _append_event(log_path or DEFAULT_PHASE_EXECUTION_LOG, "phase_execution.plan_started", plan.as_dict())
    return plan


def record_phase_directive(
    *,
    plan_id: str,
    phase: PhaseName | str,
    issued_by: str,
    directive: str,
    run_id: str | None = None,
    work_id: str | None = None,
    budget_units: float | None = None,
    evidence_refs: list[str] | None = None,
    output_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    directive_id: str | None = None,
    log_path: Path | None = None,
) -> PhaseExecutionPlan:
    path = log_path or DEFAULT_PHASE_EXECUTION_LOG
    plan = get_phase_execution_plan(plan_id, log_path=path)
    if plan.status != "active":
        raise ValueError(f"cannot record directive for {plan.status} plan {plan_id}")
    if not directive.strip():
        raise ValueError("directive is required")
    if not issued_by.strip():
        raise ValueError("issued_by is required")
    phase = _validate(phase, VALID_PHASES, "phase")
    if budget_units is not None and budget_units < 0:
        raise ValueError("budget_units cannot be negative")
    directive_record = PhaseDirective(
        directive_id=directive_id or f"pdir_{uuid.uuid4().hex[:12]}",
        plan_id=plan_id,
        created_at_utc=_now_iso(),
        phase=phase,
        issued_by=issued_by,
        directive=directive,
        run_id=run_id or plan.run_id,
        work_id=work_id or plan.work_id,
        budget_units=budget_units,
        evidence_refs=evidence_refs or [],
        output_refs=output_refs or [],
        metadata=metadata or {},
    )
    _append_event(path, "phase_execution.directive_recorded", directive_record.as_dict())
    return get_phase_execution_plan(plan_id, log_path=path)


def record_verification_feedback(
    *,
    plan_id: str,
    verifier_role: str,
    verdict: VerificationVerdict | str,
    rationale: str,
    evidence_refs: list[str] | None = None,
    failed_phase: PhaseName | str = "execution",
    budget_decay: float = 0.5,
    min_remaining_budget_units: float = 0.01,
    metadata: dict[str, Any] | None = None,
    feedback_id: str | None = None,
    log_path: Path | None = None,
) -> PhaseExecutionPlan:
    path = log_path or DEFAULT_PHASE_EXECUTION_LOG
    plan = get_phase_execution_plan(plan_id, log_path=path)
    if plan.status != "active":
        raise ValueError(f"cannot record feedback for {plan.status} plan {plan_id}")
    if not verifier_role.strip():
        raise ValueError("verifier_role is required")
    if not rationale.strip():
        raise ValueError("rationale is required")
    verdict = _validate(verdict, VALID_VERDICTS, "verdict")
    failed_phase = _validate(failed_phase, VALID_PHASES, "failed_phase")
    if not 0 < budget_decay <= 1:
        raise ValueError("budget_decay must be in (0, 1]")
    if min_remaining_budget_units < 0:
        raise ValueError("min_remaining_budget_units cannot be negative")

    budget_before = plan.remaining_budget_units
    budget_after = budget_before
    feedback_metadata = dict(metadata or {})
    if verdict in {"failed", "blocked", "inconclusive"}:
        budget_after = budget_before * budget_decay
        if budget_after < min_remaining_budget_units:
            budget_after = 0.0
            feedback_metadata["blocked_by_budget_floor"] = True
    feedback = VerificationFeedback(
        feedback_id=feedback_id or f"pfb_{uuid.uuid4().hex[:12]}",
        plan_id=plan_id,
        created_at_utc=_now_iso(),
        verifier_role=verifier_role,
        verdict=verdict,
        rationale=rationale,
        evidence_refs=evidence_refs or [],
        failed_phase=failed_phase,
        retry_budget_before=budget_before,
        retry_budget_after=budget_after,
        budget_decay=budget_decay if verdict in {"failed", "blocked", "inconclusive"} else None,
        metadata=feedback_metadata,
    )
    _append_event(path, "phase_execution.verification_feedback_recorded", feedback.as_dict())
    return get_phase_execution_plan(plan_id, log_path=path)


def list_phase_execution_plans(*, log_path: Path | None = None) -> list[PhaseExecutionPlan]:
    return list(_project(_read_events(log_path or DEFAULT_PHASE_EXECUTION_LOG)).values())


def get_phase_execution_plan(plan_id: str, *, log_path: Path | None = None) -> PhaseExecutionPlan:
    plans = _project(_read_events(log_path or DEFAULT_PHASE_EXECUTION_LOG))
    if plan_id not in plans:
        raise KeyError(f"phase execution plan not found: {plan_id}")
    return plans[plan_id]


def phase_execution_plan_resource(plan: PhaseExecutionPlan) -> KernelResource:
    links = []
    if plan.run_id:
        links.append({"rel": "run", "href": f"run:{plan.run_id}"})
    if plan.work_id:
        links.append({"rel": "work_item", "href": f"work_item:{plan.work_id}"})
    return make_resource(
        kind="PhaseExecutionPlan",
        name=plan.plan_id,
        resource_id=plan.plan_id,
        tenant_id=plan.tenant_id,
        project_id=plan.project_id,
        spec={
            "objective": plan.objective,
            "owner_role": plan.owner_role,
            "run_id": plan.run_id,
            "work_id": plan.work_id,
            "max_attempts": plan.max_attempts,
            "metadata": plan.metadata,
        },
        status={
            "status": plan.status,
            "current_phase": plan.current_phase,
            "remaining_budget_units": plan.remaining_budget_units,
            "attempts": plan.attempts,
            "failure_reason": plan.failure_reason,
            "directives": plan.directives,
            "feedback": plan.feedback,
        },
        links=links,
    )


def learning_candidate_from_phase_execution_plan(
    plan: PhaseExecutionPlan,
) -> LearningTransitionCandidate:
    """Project blocked phase execution into an observer-only learning candidate."""
    if plan.status not in {"blocked", "failed"}:
        raise ValueError(f"phase execution plan {plan.plan_id} is not blocked or failed")
    transition_kind = _transition_kind_for_phase_plan(plan)
    source_refs = _phase_plan_source_refs(plan)
    digest_payload = {
        "plan_id": plan.plan_id,
        "status": plan.status,
        "transition_kind": transition_kind,
        "source_refs": source_refs,
    }
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return LearningTransitionCandidate(
        candidate_id=f"ltc_{digest}",
        transition_kind=transition_kind,
        severity="blocking" if plan.status == "blocked" else "warning",
        rationale=plan.failure_reason or f"Phase execution did not complete: {plan.objective}",
        source_kind="phase_execution_plan",
        object_ref=plan.work_id or plan.run_id or plan.plan_id,
        suggested_owner_role=plan.owner_role,
        review_question=(
            "Should this bounded execution failure change a mandate, route, "
            "evidence standard, or review threshold?"
        ),
        source_refs=source_refs,
        proposed_payload={
            "plan_id": plan.plan_id,
            "objective": plan.objective,
            "status": plan.status,
            "current_phase": plan.current_phase,
            "remaining_budget_units": plan.remaining_budget_units,
            "max_attempts": plan.max_attempts,
            "attempts": plan.attempts,
            "run_id": plan.run_id,
            "work_id": plan.work_id,
            "failure_reason": plan.failure_reason,
            "directives": plan.directives,
            "feedback": plan.feedback,
            "metadata": plan.metadata,
        },
        observer_only=True,
    )


def _project(rows: list[dict[str, Any]]) -> dict[str, PhaseExecutionPlan]:
    plans: dict[str, PhaseExecutionPlan] = {}
    for row in rows:
        event = row.get("event")
        payload = dict(row.get("payload") or {})
        plan_id = str(payload.get("plan_id") or "")
        if not plan_id:
            continue
        if event == "phase_execution.plan_started":
            plans[plan_id] = PhaseExecutionPlan(**payload)
            continue
        if plan_id not in plans:
            continue
        current = plans[plan_id]
        if event == "phase_execution.directive_recorded":
            directive = PhaseDirective(**payload).as_dict()
            plans[plan_id] = PhaseExecutionPlan(
                **{
                    **current.as_dict(),
                    "updated_at_utc": row.get("ts") or _now_iso(),
                    "current_phase": directive["phase"],
                    "directives": current.directives + [directive],
                }
            )
        elif event == "phase_execution.verification_feedback_recorded":
            feedback = VerificationFeedback(**payload)
            feedback_payload = feedback.as_dict()
            attempts = current.attempts
            status = current.status
            current_phase = current.current_phase
            failure_reason = current.failure_reason
            remaining = current.remaining_budget_units
            if feedback.verdict == "passed":
                status = "passed"
                current_phase = "verification"
                failure_reason = None
            elif feedback.verdict == "blocked":
                attempts += 1
                remaining = float(feedback.retry_budget_after or 0)
                status = "blocked"
                current_phase = "verification"
                failure_reason = feedback.rationale
            elif feedback.verdict in {"failed", "inconclusive"}:
                attempts += 1
                remaining = float(feedback.retry_budget_after or 0)
                if attempts >= current.max_attempts or remaining <= 0:
                    status = "blocked"
                    current_phase = "verification"
                    failure_reason = feedback.rationale
                else:
                    status = "active"
                    current_phase = "execution"
                    failure_reason = feedback.rationale
            plans[plan_id] = PhaseExecutionPlan(
                **{
                    **current.as_dict(),
                    "updated_at_utc": row.get("ts") or _now_iso(),
                    "status": status,
                    "current_phase": current_phase,
                    "remaining_budget_units": remaining,
                    "attempts": attempts,
                    "failure_reason": failure_reason,
                    "feedback": current.feedback + [feedback_payload],
                }
            )
    return plans


def _transition_kind_for_phase_plan(plan: PhaseExecutionPlan) -> LearningTransitionKind:
    raw = str(plan.metadata.get("proposed_transition_kind") or "")
    if raw in VALID_LEARNING_TRANSITION_KINDS:
        return raw  # type: ignore[return-value]
    evidence_text = " ".join(
        [
            plan.failure_reason or "",
            plan.objective,
            " ".join(str(ref) for ref in _phase_plan_source_refs(plan)),
        ]
    ).lower()
    if "source" in evidence_text:
        return "source_repair"
    if "evidence" in evidence_text:
        return "evidence_gap"
    if "human" in evidence_text or "receipt" in evidence_text:
        return "human_work_session"
    if "mandate" in evidence_text or "authority" in evidence_text:
        return "mandate_review"
    return "role_review"


def _phase_plan_source_refs(plan: PhaseExecutionPlan) -> list[str]:
    refs = [f"phase_execution_plan:{plan.plan_id}"]
    if plan.run_id:
        refs.append(f"run:{plan.run_id}")
    if plan.work_id:
        refs.append(f"work_item:{plan.work_id}")
    for directive in plan.directives:
        refs.extend(str(ref) for ref in directive.get("evidence_refs") or [] if ref)
        refs.extend(str(ref) for ref in directive.get("output_refs") or [] if ref)
        directive_id = directive.get("directive_id")
        if directive_id:
            refs.append(f"phase_directive:{directive_id}")
    for feedback in plan.feedback:
        refs.extend(str(ref) for ref in feedback.get("evidence_refs") or [] if ref)
        feedback_id = feedback.get("feedback_id")
        if feedback_id:
            refs.append(f"phase_feedback:{feedback_id}")
    out: list[str] = []
    for ref in refs:
        if ref and ref not in out:
            out.append(ref)
    return out


def _append_event(path: Path, event: str, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "event_id": f"pevt_{uuid.uuid4().hex[:12]}",
        "event": event,
        "ts": _now_iso(),
        "payload": payload,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _validate(value: str, allowed: set[str], label: str) -> str:
    text = str(value)
    if text not in allowed:
        raise ValueError(f"{label} must be one of: {', '.join(sorted(allowed))}")
    return text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect phase-separated execution plans.")
    parser.add_argument("--log", type=Path, default=DEFAULT_PHASE_EXECUTION_LOG)
    parser.add_argument("--resource", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    args = parser.parse_args(argv)
    if args.cmd == "list":
        for plan in list_phase_execution_plans(log_path=args.log):
            payload = phase_execution_plan_resource(plan).as_dict() if args.resource else plan.as_dict()
            print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
