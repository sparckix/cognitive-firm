"""Decision aggregation cases for governed multi-actor decisions.

This module records how an eligible set of actors or roles produced a decision
recommendation. It does not allocate authority and it does not mutate org
state. The output is evidence for existing governance, policy, residual-right,
or accountability paths.
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


DecisionProcedureKind = Literal["single_authority", "quorum_majority", "veto", "unanimity"]
DecisionCaseStatus = Literal["collecting", "computed", "escalated", "expired"]
DecisionPositionKind = Literal["approve", "reject", "abstain", "recuse", "veto"]
DecisionRecommendation = Literal["approve", "reject", "escalate"]

VALID_PROCEDURES = {"single_authority", "quorum_majority", "veto", "unanimity"}
VALID_STATUSES = {"collecting", "computed", "escalated", "expired"}
VALID_POSITIONS = {"approve", "reject", "abstain", "recuse", "veto"}

DEFAULT_DECISION_AGGREGATION_LOG = (
    ORG_ROOT_DIR / "decision_aggregation" / "decision_aggregation_cases.jsonl"
)


@dataclass(frozen=True)
class DecisionPosition:
    position_id: str
    case_id: str
    actor_id: str
    role_id: str
    position: DecisionPositionKind | str
    rationale: str
    created_at_utc: str
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionAggregationResult:
    recommendation: DecisionRecommendation | str
    rationale: str
    procedure_kind: DecisionProcedureKind | str
    approvals: int = 0
    rejections: int = 0
    abstentions: int = 0
    recusals: int = 0
    vetoes: int = 0
    quorum: int = 1
    quorum_met: bool = False
    tie: bool = False
    evidence_refs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionProcedureProfile:
    """Reusable procedure recipe that expands into a decision aggregation case.

    Profiles are convenience recipes only. They do not grant authority and they
    do not make the resulting recommendation binding.
    """

    profile_id: str
    procedure_kind: DecisionProcedureKind | str
    quorum_rule: str
    description: str
    binding_semantics: str = "evidence_only"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionAggregationCase:
    case_id: str
    created_at_utc: str
    updated_at_utc: str
    subject_ref: str
    decision_class: str
    scope_kind: str
    scope_ref: str
    procedure_kind: DecisionProcedureKind | str
    opened_by: str
    eligibility_basis: str
    status: DecisionCaseStatus | str = "collecting"
    eligible_roles: list[str] = field(default_factory=list)
    eligible_actors: list[str] = field(default_factory=list)
    quorum: int = 1
    tie_breaker_role: str | None = None
    downstream_ref: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    positions: list[DecisionPosition] = field(default_factory=list)
    result: DecisionAggregationResult | None = None
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["positions"] = [position.as_dict() for position in self.positions]
        payload["result"] = self.result.as_dict() if self.result else None
        return payload


PROCEDURE_PROFILES: dict[str, DecisionProcedureProfile] = {
    "single_authority": DecisionProcedureProfile(
        profile_id="single_authority",
        procedure_kind="single_authority",
        quorum_rule="one",
        description="One eligible authority records one non-abstaining position.",
    ),
    "majority": DecisionProcedureProfile(
        profile_id="majority",
        procedure_kind="quorum_majority",
        quorum_rule="majority_of_eligible",
        description="Recommendation follows the majority once more than half of the eligibility snapshot participates.",
    ),
    "quorum_majority": DecisionProcedureProfile(
        profile_id="quorum_majority",
        procedure_kind="quorum_majority",
        quorum_rule="explicit_or_majority_of_eligible",
        description="Recommendation follows majority after the configured quorum is met.",
    ),
    "unanimity": DecisionProcedureProfile(
        profile_id="unanimity",
        procedure_kind="unanimity",
        quorum_rule="all_eligible",
        description="Every eligible slot must approve; any rejection or veto rejects; absence, abstention, or recusal escalates.",
    ),
    "veto_review": DecisionProcedureProfile(
        profile_id="veto_review",
        procedure_kind="veto",
        quorum_rule="explicit_or_majority_of_eligible",
        description="Any eligible veto rejects; otherwise the case falls back to quorum-majority behavior.",
    ),
}


def list_decision_procedure_profiles() -> list[DecisionProcedureProfile]:
    """Return built-in decision procedure recipes."""
    return list(PROCEDURE_PROFILES.values())


def get_decision_procedure_profile(profile_id: str) -> DecisionProcedureProfile:
    key = str(profile_id).strip()
    if key not in PROCEDURE_PROFILES:
        raise ValueError(
            f"invalid procedure_profile {profile_id!r}; expected one of {sorted(PROCEDURE_PROFILES)}"
        )
    return PROCEDURE_PROFILES[key]


def resolve_decision_procedure_profile(
    profile_id: str,
    *,
    eligible_roles: list[str] | None = None,
    eligible_actors: list[str] | None = None,
    quorum: int | None = None,
) -> dict[str, Any]:
    """Resolve a named profile into `procedure_kind`, `quorum`, and metadata."""
    profile = get_decision_procedure_profile(profile_id)
    roles = _unique_nonempty(eligible_roles or [])
    actors = _unique_nonempty(eligible_actors or [])
    slot_count = _eligible_slot_count(roles, actors)
    if slot_count < 1:
        raise ValueError("eligible_roles or eligible_actors is required")
    resolved_quorum = quorum if quorum is not None else _default_quorum(profile, slot_count)
    if resolved_quorum < 1:
        raise ValueError("quorum must be at least 1")
    if profile.procedure_kind == "single_authority" and resolved_quorum != 1:
        raise ValueError("single_authority quorum must be 1")
    if profile.procedure_kind == "unanimity" and resolved_quorum != slot_count:
        raise ValueError("unanimity quorum must equal the eligible slot count")
    return {
        "profile": profile,
        "procedure_kind": profile.procedure_kind,
        "quorum": resolved_quorum,
        "eligible_roles": roles,
        "eligible_actors": actors,
        "metadata": {
            "procedure_profile": profile.profile_id,
            "procedure_profile_quorum_rule": profile.quorum_rule,
            "procedure_profile_binding": profile.binding_semantics,
        },
    }


def open_decision_aggregation_case_from_profile(
    *,
    procedure_profile: str,
    subject_ref: str,
    decision_class: str,
    scope_kind: str,
    scope_ref: str,
    opened_by: str,
    eligibility_basis: str,
    eligible_roles: list[str] | None = None,
    eligible_actors: list[str] | None = None,
    quorum: int | None = None,
    tie_breaker_role: str | None = None,
    downstream_ref: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    case_id: str | None = None,
    log_path: Path | None = None,
) -> DecisionAggregationCase:
    """Open a case using a built-in decision procedure profile."""
    resolved = resolve_decision_procedure_profile(
        procedure_profile,
        eligible_roles=eligible_roles,
        eligible_actors=eligible_actors,
        quorum=quorum,
    )
    next_metadata = {**resolved["metadata"], **dict(metadata or {})}
    return open_decision_aggregation_case(
        subject_ref=subject_ref,
        decision_class=decision_class,
        scope_kind=scope_kind,
        scope_ref=scope_ref,
        procedure_kind=resolved["procedure_kind"],
        opened_by=opened_by,
        eligibility_basis=eligibility_basis,
        eligible_roles=resolved["eligible_roles"],
        eligible_actors=resolved["eligible_actors"],
        quorum=int(resolved["quorum"]),
        tie_breaker_role=tie_breaker_role,
        downstream_ref=downstream_ref,
        tenant_id=tenant_id,
        project_id=project_id,
        evidence_refs=evidence_refs,
        metadata=next_metadata,
        case_id=case_id,
        log_path=log_path,
    )


def open_decision_aggregation_case(
    *,
    subject_ref: str,
    decision_class: str,
    scope_kind: str,
    scope_ref: str,
    procedure_kind: DecisionProcedureKind | str,
    opened_by: str,
    eligibility_basis: str,
    eligible_roles: list[str] | None = None,
    eligible_actors: list[str] | None = None,
    quorum: int = 1,
    tie_breaker_role: str | None = None,
    downstream_ref: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    case_id: str | None = None,
    log_path: Path | None = None,
) -> DecisionAggregationCase:
    """Open a decision aggregation case with a fixed eligibility snapshot."""
    _require(subject_ref, "subject_ref")
    _require(decision_class, "decision_class")
    _require(scope_kind, "scope_kind")
    _require(scope_ref, "scope_ref")
    procedure = _validate_procedure(procedure_kind)
    _require(opened_by, "opened_by")
    _require(eligibility_basis, "eligibility_basis")
    roles = _unique_nonempty(eligible_roles or [])
    actors = _unique_nonempty(eligible_actors or [])
    if not roles and not actors:
        raise ValueError("eligible_roles or eligible_actors is required")
    if quorum < 1:
        raise ValueError("quorum must be at least 1")
    if procedure == "single_authority" and quorum != 1:
        raise ValueError("single_authority quorum must be 1")
    if procedure == "unanimity" and quorum != _eligible_slot_count(roles, actors):
        raise ValueError("unanimity quorum must equal the eligible slot count")
    now = _now_iso()
    case = DecisionAggregationCase(
        case_id=case_id or f"dac_{uuid.uuid4().hex[:12]}",
        created_at_utc=now,
        updated_at_utc=now,
        subject_ref=subject_ref.strip(),
        decision_class=decision_class.strip(),
        scope_kind=scope_kind.strip(),
        scope_ref=scope_ref.strip(),
        procedure_kind=procedure,
        opened_by=opened_by.strip(),
        eligibility_basis=eligibility_basis.strip(),
        eligible_roles=roles,
        eligible_actors=actors,
        quorum=quorum,
        tie_breaker_role=_optional(tie_breaker_role),
        downstream_ref=_optional(downstream_ref),
        tenant_id=tenant_id,
        project_id=project_id,
        evidence_refs=list(evidence_refs or []),
        metadata=dict(metadata or {}),
    )
    _upsert_case(log_path or DEFAULT_DECISION_AGGREGATION_LOG, case)
    return case


def record_decision_position(
    case_id: str,
    *,
    actor_id: str,
    role_id: str,
    position: DecisionPositionKind | str,
    rationale: str,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    position_id: str | None = None,
    log_path: Path | None = None,
) -> DecisionAggregationCase:
    """Record one eligible actor/role position on a collecting case."""
    path = log_path or DEFAULT_DECISION_AGGREGATION_LOG
    case = get_decision_aggregation_case(case_id, log_path=path)
    if case.status != "collecting":
        raise ValueError(f"cannot record position on {case.status} case {case_id}")
    _require(actor_id, "actor_id")
    _require(role_id, "role_id")
    vote = _validate_position(position)
    _require(rationale, "rationale")
    _verify_eligible(case, actor_id=actor_id, role_id=role_id)
    for existing in case.positions:
        if existing.actor_id == actor_id and existing.role_id == role_id:
            raise ValueError("actor/role already recorded a position for this case")
    next_case = _replace_case(
        case,
        positions=[
            *case.positions,
            DecisionPosition(
                position_id=position_id or f"dpos_{uuid.uuid4().hex[:12]}",
                case_id=case_id,
                actor_id=actor_id.strip(),
                role_id=role_id.strip(),
                position=vote,
                rationale=rationale.strip(),
                created_at_utc=_now_iso(),
                evidence_refs=list(evidence_refs or []),
                metadata=dict(metadata or {}),
            ),
        ],
        updated_at_utc=_now_iso(),
    )
    _upsert_case(path, next_case)
    return next_case


def compute_decision_aggregation_case(
    case_id: str,
    *,
    log_path: Path | None = None,
) -> DecisionAggregationCase:
    """Compute a deterministic recommendation for the case procedure."""
    path = log_path or DEFAULT_DECISION_AGGREGATION_LOG
    case = get_decision_aggregation_case(case_id, log_path=path)
    if case.status not in {"collecting", "computed", "escalated"}:
        raise ValueError(f"cannot compute {case.status} case {case_id}")
    result = _compute_result(case)
    status: DecisionCaseStatus = (
        "computed" if result.recommendation in {"approve", "reject"} else "escalated"
    )
    next_case = _replace_case(
        case,
        result=result,
        status=status,
        updated_at_utc=_now_iso(),
    )
    _upsert_case(path, next_case)
    return next_case


def get_decision_aggregation_case(
    case_id: str,
    *,
    log_path: Path | None = None,
) -> DecisionAggregationCase:
    for case in list_decision_aggregation_cases(log_path=log_path):
        if case.case_id == case_id:
            return case
    raise KeyError(f"decision aggregation case not found: {case_id}")


def list_decision_aggregation_cases(
    *,
    status: DecisionCaseStatus | str | None = None,
    procedure_kind: DecisionProcedureKind | str | None = None,
    subject_ref: str | None = None,
    log_path: Path | None = None,
) -> list[DecisionAggregationCase]:
    if status is not None:
        status = _validate_status(status)
    if procedure_kind is not None:
        procedure_kind = _validate_procedure(procedure_kind)
    cases = [_parse_case(row) for row in _read_jsonl(log_path or DEFAULT_DECISION_AGGREGATION_LOG)]
    out: list[DecisionAggregationCase] = []
    for case in cases:
        if status is not None and case.status != status:
            continue
        if procedure_kind is not None and case.procedure_kind != procedure_kind:
            continue
        if subject_ref is not None and case.subject_ref != subject_ref:
            continue
        out.append(case)
    return out


def decision_aggregation_case_resource(case: DecisionAggregationCase) -> KernelResource:
    labels = {
        "procedure_kind": str(case.procedure_kind),
        "status": str(case.status),
        "decision_class": case.decision_class,
        "scope_kind": case.scope_kind,
    }
    if case.result:
        labels["recommendation"] = str(case.result.recommendation)
    links = [{"rel": "subject", "href": case.subject_ref}]
    if case.downstream_ref:
        links.append({"rel": "downstream", "href": case.downstream_ref})
    for ref in case.evidence_refs:
        links.append({"rel": "evidence", "href": ref})
    return make_resource(
        kind="DecisionAggregationCase",
        name=case.case_id,
        resource_id=case.case_id,
        tenant_id=case.tenant_id,
        project_id=case.project_id,
        stability="alpha",
        labels=labels,
        annotations={
            key: str(value)
            for key, value in case.metadata.items()
            if isinstance(key, str) and value is not None
        },
        spec={
            "subject_ref": case.subject_ref,
            "decision_class": case.decision_class,
            "scope_kind": case.scope_kind,
            "scope_ref": case.scope_ref,
            "procedure_kind": case.procedure_kind,
            "opened_by": case.opened_by,
            "eligibility_basis": case.eligibility_basis,
            "eligible_roles": case.eligible_roles,
            "eligible_actors": case.eligible_actors,
            "quorum": case.quorum,
            "tie_breaker_role": case.tie_breaker_role,
            "downstream_ref": case.downstream_ref,
            "evidence_refs": case.evidence_refs,
        },
        status={
            "status": case.status,
            "positions": [position.as_dict() for position in case.positions],
            "result": case.result.as_dict() if case.result else None,
            "created_at_utc": case.created_at_utc,
            "updated_at_utc": case.updated_at_utc,
        },
        links=links,
    )


def _compute_result(case: DecisionAggregationCase) -> DecisionAggregationResult:
    counts = _position_counts(case.positions)
    evidence_refs = sorted({
        ref
        for position in case.positions
        for ref in position.evidence_refs
    } | set(case.evidence_refs))
    non_abstain = counts["approve"] + counts["reject"] + counts["veto"]
    quorum_met = non_abstain >= case.quorum
    if case.procedure_kind == "single_authority":
        if non_abstain != 1:
            return _result(
                case,
                "escalate",
                "single_authority requires exactly one non-abstaining eligible position",
                counts,
                quorum_met=False,
                evidence_refs=evidence_refs,
            )
        if counts["approve"] == 1:
            return _result(case, "approve", "single authority approved", counts, quorum_met=True, evidence_refs=evidence_refs)
        return _result(case, "reject", "single authority rejected", counts, quorum_met=True, evidence_refs=evidence_refs)
    if case.procedure_kind == "unanimity":
        if counts["veto"] > 0:
            return _result(case, "reject", "eligible veto recorded under unanimity", counts, quorum_met=quorum_met, evidence_refs=evidence_refs)
        if counts["reject"] > 0:
            return _result(case, "reject", "eligible rejection recorded under unanimity", counts, quorum_met=quorum_met, evidence_refs=evidence_refs)
        if counts["approve"] >= case.quorum and counts["abstain"] == 0 and counts["recuse"] == 0:
            return _result(case, "approve", "all eligible positions approved", counts, quorum_met=True, evidence_refs=evidence_refs)
        return _result(case, "escalate", "unanimity requires every eligible slot to approve", counts, quorum_met=False, evidence_refs=evidence_refs)
    if case.procedure_kind == "veto" and counts["veto"] > 0:
        return _result(case, "reject", "eligible veto recorded", counts, quorum_met=quorum_met, evidence_refs=evidence_refs)
    if not quorum_met:
        return _result(case, "escalate", "quorum not met", counts, quorum_met=False, evidence_refs=evidence_refs)
    if counts["approve"] > counts["reject"]:
        return _result(case, "approve", "approvals exceed rejections", counts, quorum_met=True, evidence_refs=evidence_refs)
    if counts["reject"] > counts["approve"]:
        return _result(case, "reject", "rejections exceed approvals", counts, quorum_met=True, evidence_refs=evidence_refs)
    return _result(case, "escalate", "tie without decisive procedure result", counts, quorum_met=True, tie=True, evidence_refs=evidence_refs)


def _result(
    case: DecisionAggregationCase,
    recommendation: DecisionRecommendation,
    rationale: str,
    counts: dict[str, int],
    *,
    quorum_met: bool,
    tie: bool = False,
    evidence_refs: list[str] | None = None,
) -> DecisionAggregationResult:
    return DecisionAggregationResult(
        recommendation=recommendation,
        rationale=rationale,
        procedure_kind=case.procedure_kind,
        approvals=counts["approve"],
        rejections=counts["reject"],
        abstentions=counts["abstain"],
        recusals=counts["recuse"],
        vetoes=counts["veto"],
        quorum=case.quorum,
        quorum_met=quorum_met,
        tie=tie,
        evidence_refs=evidence_refs or [],
    )


def _position_counts(positions: list[DecisionPosition]) -> dict[str, int]:
    counts = {"approve": 0, "reject": 0, "abstain": 0, "recuse": 0, "veto": 0}
    for position in positions:
        counts[str(position.position)] += 1
    return counts


def _verify_eligible(case: DecisionAggregationCase, *, actor_id: str, role_id: str) -> None:
    if case.eligible_actors and actor_id.strip() not in case.eligible_actors:
        raise PermissionError("actor is not eligible for this decision aggregation case")
    if case.eligible_roles and role_id.strip() not in case.eligible_roles:
        raise PermissionError("role is not eligible for this decision aggregation case")


def _replace_case(case: DecisionAggregationCase, **changes: Any) -> DecisionAggregationCase:
    payload = case.as_dict()
    payload.update(changes)
    return _parse_case(payload)


def _parse_case(row: dict[str, Any]) -> DecisionAggregationCase:
    positions = [_parse_position(item) for item in row.get("positions") or []]
    result = row.get("result")
    return DecisionAggregationCase(
        **{
            **row,
            "positions": positions,
            "result": _parse_result(result),
        }
    )


def _parse_position(row: DecisionPosition | dict[str, Any]) -> DecisionPosition:
    if isinstance(row, DecisionPosition):
        return row
    return DecisionPosition(**row)


def _parse_result(
    row: DecisionAggregationResult | dict[str, Any] | None,
) -> DecisionAggregationResult | None:
    if row is None:
        return None
    if isinstance(row, DecisionAggregationResult):
        return row
    return DecisionAggregationResult(**row)


def _upsert_case(path: Path, case: DecisionAggregationCase) -> None:
    rows = _read_jsonl(path)
    next_rows: list[dict[str, Any]] = []
    replaced = False
    for row in rows:
        if row.get("case_id") == case.case_id:
            next_rows.append(case.as_dict())
            replaced = True
        else:
            next_rows.append(row)
    if not replaced:
        next_rows.append(case.as_dict())
    _write_jsonl(path, next_rows)


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require(value: str, label: str) -> str:
    if not str(value).strip():
        raise ValueError(f"{label} is required")
    return str(value).strip()


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _unique_nonempty(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _eligible_slot_count(eligible_roles: list[str], eligible_actors: list[str]) -> int:
    # Actor snapshots are more concrete than role snapshots. If both are present
    # the actor count is the safest bounded participation count.
    return len(eligible_actors) if eligible_actors else len(eligible_roles)


def _default_quorum(profile: DecisionProcedureProfile, eligible_slot_count: int) -> int:
    if profile.quorum_rule == "one":
        return 1
    if profile.quorum_rule == "all_eligible":
        return eligible_slot_count
    if profile.quorum_rule in {"majority_of_eligible", "explicit_or_majority_of_eligible"}:
        return (eligible_slot_count // 2) + 1
    raise ValueError(f"unknown quorum_rule {profile.quorum_rule!r}")


def _validate_procedure(value: DecisionProcedureKind | str) -> DecisionProcedureKind:
    if str(value) not in VALID_PROCEDURES:
        raise ValueError(f"invalid procedure_kind {value!r}; expected one of {sorted(VALID_PROCEDURES)}")
    return str(value)  # type: ignore[return-value]


def _validate_status(value: DecisionCaseStatus | str) -> DecisionCaseStatus:
    if str(value) not in VALID_STATUSES:
        raise ValueError(f"invalid status {value!r}; expected one of {sorted(VALID_STATUSES)}")
    return str(value)  # type: ignore[return-value]


def _validate_position(value: DecisionPositionKind | str) -> DecisionPositionKind:
    if str(value) not in VALID_POSITIONS:
        raise ValueError(f"invalid position {value!r}; expected one of {sorted(VALID_POSITIONS)}")
    return str(value)  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect decision aggregation cases")
    parser.add_argument("--log-path", type=Path, default=DEFAULT_DECISION_AGGREGATION_LOG)
    parser.add_argument("--resource", action="store_true")
    args = parser.parse_args(argv)
    cases = list_decision_aggregation_cases(log_path=args.log_path)
    if args.resource:
        print(json.dumps([decision_aggregation_case_resource(case).as_dict() for case in cases], indent=2, sort_keys=True))
    else:
        print(json.dumps([case.as_dict() for case in cases], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
