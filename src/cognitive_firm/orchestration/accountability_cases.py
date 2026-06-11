"""Accountability cases for authority, recourse, and closure.

`accountability.py` is a read model that surfaces unresolved follow-up.
Accountability cases are the small write-side record for who owns review,
which authority basis applies, what recourse exists, and how closure is proven.
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


RiskTier = Literal["low", "medium", "high", "irreversible"]
AccountabilityStatus = Literal["open", "under_review", "remediated", "accepted_risk", "escalated", "closed"]
RecoursePath = Literal["reopen", "compensate", "rollback", "escalate", "external_review", "none"]
OperatorBurden = Literal["low", "medium", "high"]

DEFAULT_ACCOUNTABILITY_CASES_LOG = ORG_ROOT_DIR / "accountability" / "accountability_cases.jsonl"
VALID_RISK_TIERS = {"low", "medium", "high", "irreversible"}
VALID_STATUSES = {"open", "under_review", "remediated", "accepted_risk", "escalated", "closed"}
VALID_RECOURSE_PATHS = {"reopen", "compensate", "rollback", "escalate", "external_review", "none"}
VALID_OPERATOR_BURDEN = {"low", "medium", "high"}
TERMINAL_STATUSES = {"accepted_risk", "closed"}
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"under_review", "remediated", "accepted_risk", "escalated", "closed"},
    "under_review": {"remediated", "accepted_risk", "escalated", "closed"},
    "remediated": {"closed", "under_review"},
    "escalated": {"under_review", "accepted_risk", "closed"},
    "accepted_risk": set(),
    "closed": set(),
}


@dataclass(frozen=True)
class AccountabilityCase:
    case_id: str
    created_at_utc: str
    updated_at_utc: str
    trigger_ref: str
    accountable_role: str
    responsible_actor: str
    decision_right_basis: str
    authority_envelope_ref: str
    risk_tier: RiskTier
    recourse_path: RecoursePath
    status: AccountabilityStatus = "open"
    residual_risk_accepted_by: str | None = None
    review_sla: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    due_at_utc: str | None = None
    closure_evidence_refs: list[str] = field(default_factory=list)
    externality_tags: list[str] = field(default_factory=list)
    operator_burden: OperatorBurden = "medium"
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


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


def create_accountability_case(
    *,
    trigger_ref: str,
    accountable_role: str,
    responsible_actor: str,
    decision_right_basis: str,
    authority_envelope_ref: str,
    risk_tier: RiskTier | str,
    recourse_path: RecoursePath | str,
    residual_risk_accepted_by: str | None = None,
    review_sla: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    due_at_utc: str | None = None,
    externality_tags: list[str] | None = None,
    operator_burden: OperatorBurden | str = "medium",
    rationale: str = "",
    metadata: dict[str, Any] | None = None,
    case_id: str | None = None,
    log_path: Path | None = None,
) -> AccountabilityCase:
    if not trigger_ref.strip():
        raise ValueError("trigger_ref is required")
    if not accountable_role.strip():
        raise ValueError("accountable_role is required")
    if not responsible_actor.strip():
        raise ValueError("responsible_actor is required")
    if not decision_right_basis.strip():
        raise ValueError("decision_right_basis is required")
    if not authority_envelope_ref.strip():
        raise ValueError("authority_envelope_ref is required")

    now = _now_iso()
    case = AccountabilityCase(
        case_id=case_id or f"acct_{uuid.uuid4().hex[:12]}",
        created_at_utc=now,
        updated_at_utc=now,
        trigger_ref=trigger_ref,
        accountable_role=accountable_role,
        responsible_actor=responsible_actor,
        decision_right_basis=decision_right_basis,
        authority_envelope_ref=authority_envelope_ref,
        risk_tier=_validate(str(risk_tier), VALID_RISK_TIERS, "risk_tier"),  # type: ignore[arg-type]
        recourse_path=_validate(str(recourse_path), VALID_RECOURSE_PATHS, "recourse_path"),  # type: ignore[arg-type]
        residual_risk_accepted_by=residual_risk_accepted_by,
        review_sla=review_sla,
        tenant_id=tenant_id,
        project_id=project_id,
        due_at_utc=due_at_utc,
        externality_tags=externality_tags or [],
        operator_burden=_validate(str(operator_burden), VALID_OPERATOR_BURDEN, "operator_burden"),  # type: ignore[arg-type]
        rationale=rationale,
        metadata=metadata or {},
    )
    _append_jsonl(log_path or DEFAULT_ACCOUNTABILITY_CASES_LOG, asdict(case))
    return case


def list_accountability_cases(
    *,
    status: AccountabilityStatus | str | None = None,
    accountable_role: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    risk_tier: RiskTier | str | None = None,
    log_path: Path | None = None,
) -> list[AccountabilityCase]:
    if status is not None:
        status = _validate(str(status), VALID_STATUSES, "status")
    if risk_tier is not None:
        risk_tier = _validate(str(risk_tier), VALID_RISK_TIERS, "risk_tier")
    out: list[AccountabilityCase] = []
    for row in _read_jsonl(log_path or DEFAULT_ACCOUNTABILITY_CASES_LOG):
        case = AccountabilityCase(**row)
        if status is not None and case.status != status:
            continue
        if accountable_role is not None and case.accountable_role != accountable_role:
            continue
        if tenant_id is not None and case.tenant_id != tenant_id:
            continue
        if project_id is not None and case.project_id != project_id:
            continue
        if risk_tier is not None and case.risk_tier != risk_tier:
            continue
        out.append(case)
    return out


def update_accountability_case_status(
    case_id: str,
    status: AccountabilityStatus | str,
    *,
    closure_evidence_refs: list[str] | None = None,
    residual_risk_accepted_by: str | None = None,
    log_path: Path | None = None,
) -> AccountabilityCase:
    next_status = _validate(str(status), VALID_STATUSES, "status")
    path = log_path or DEFAULT_ACCOUNTABILITY_CASES_LOG
    rows = _read_jsonl(path)
    updated: AccountabilityCase | None = None
    next_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("case_id") == case_id:
            current = str(row.get("status"))
            if current in TERMINAL_STATUSES:
                raise ValueError(f"{current} is terminal; no transitions allowed")
            allowed = ALLOWED_TRANSITIONS.get(current, set())
            if next_status not in allowed:
                raise ValueError(f"illegal transition {current} -> {next_status}; allowed: {sorted(allowed)}")
            row["status"] = next_status
            row["updated_at_utc"] = _now_iso()
            if closure_evidence_refs is not None:
                existing = list(row.get("closure_evidence_refs") or [])
                row["closure_evidence_refs"] = list(dict.fromkeys(existing + closure_evidence_refs))
            if residual_risk_accepted_by is not None:
                row["residual_risk_accepted_by"] = residual_risk_accepted_by
            if next_status in {"accepted_risk", "closed"}:
                if not row.get("closure_evidence_refs") and next_status == "closed":
                    raise ValueError("closed accountability cases require closure evidence")
                if next_status == "accepted_risk" and not row.get("residual_risk_accepted_by"):
                    raise ValueError("accepted_risk requires residual_risk_accepted_by")
            updated = AccountabilityCase(**row)
        next_rows.append(row)
    if updated is None:
        raise KeyError(f"accountability case not found: {case_id}")
    _write_jsonl(path, next_rows)
    return updated


def accountability_case_summary(case: AccountabilityCase) -> dict[str, Any]:
    return asdict(case)


def accountability_case_resource(case: AccountabilityCase) -> KernelResource:
    """Project an accountability case into the common resource envelope.

    The case JSONL row remains canonical. The resource view is for adapters,
    dashboards, migration checks, and conformance fixtures that need a stable
    object shape for residual-risk and recourse state.
    """
    labels = {
        "accountable_role": case.accountable_role,
        "responsible_actor": case.responsible_actor,
        "risk_tier": case.risk_tier,
        "recourse_path": case.recourse_path,
        "status": case.status,
    }
    if case.operator_burden:
        labels["operator_burden"] = case.operator_burden
    links = [
        {"rel": "trigger", "href": case.trigger_ref},
        {"rel": "accountable_role", "href": case.accountable_role},
        {"rel": "responsible_actor", "href": case.responsible_actor},
        {"rel": "authority_envelope", "href": case.authority_envelope_ref},
    ]
    for ref in case.closure_evidence_refs:
        links.append({"rel": "closure_evidence", "href": ref})
    if case.residual_risk_accepted_by:
        links.append(
            {
                "rel": "residual_risk_accepted_by",
                "href": case.residual_risk_accepted_by,
            }
        )
    return make_resource(
        kind="AccountabilityCase",
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
            "trigger_ref": case.trigger_ref,
            "accountable_role": case.accountable_role,
            "responsible_actor": case.responsible_actor,
            "decision_right_basis": case.decision_right_basis,
            "authority_envelope_ref": case.authority_envelope_ref,
            "risk_tier": case.risk_tier,
            "recourse_path": case.recourse_path,
            "review_sla": case.review_sla,
            "due_at_utc": case.due_at_utc,
            "externality_tags": case.externality_tags,
            "operator_burden": case.operator_burden,
            "rationale": case.rationale,
        },
        status={
            "status": case.status,
            "residual_risk_accepted_by": case.residual_risk_accepted_by,
            "closure_evidence_refs": case.closure_evidence_refs,
            "created_at_utc": case.created_at_utc,
            "updated_at_utc": case.updated_at_utc,
        },
        links=links,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage accountability cases.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--status")
    list_parser.add_argument("--accountable-role")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--risk-tier")
    list_parser.add_argument("--log-path", type=Path)
    list_parser.add_argument("--resource", action="store_true", help="render resource envelopes")

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--trigger-ref", required=True)
    create_parser.add_argument("--accountable-role", required=True)
    create_parser.add_argument("--responsible-actor", required=True)
    create_parser.add_argument("--decision-right-basis", required=True)
    create_parser.add_argument("--authority-envelope-ref", required=True)
    create_parser.add_argument("--risk-tier", required=True)
    create_parser.add_argument("--recourse-path", required=True)
    create_parser.add_argument("--residual-risk-accepted-by")
    create_parser.add_argument("--review-sla")
    create_parser.add_argument("--tenant-id")
    create_parser.add_argument("--project-id")
    create_parser.add_argument("--due-at-utc")
    create_parser.add_argument("--externality-tag", action="append", default=[])
    create_parser.add_argument("--operator-burden", default="medium")
    create_parser.add_argument("--rationale", default="")
    create_parser.add_argument("--log-path", type=Path)

    update_parser = sub.add_parser("update")
    update_parser.add_argument("case_id")
    update_parser.add_argument("--status", required=True)
    update_parser.add_argument("--closure-evidence-ref", action="append", default=[])
    update_parser.add_argument("--residual-risk-accepted-by")
    update_parser.add_argument("--log-path", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "list":
        for case in list_accountability_cases(
            status=args.status,
            accountable_role=args.accountable_role,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            risk_tier=args.risk_tier,
            log_path=args.log_path,
        ):
            payload = (
                accountability_case_resource(case).as_dict()
                if args.resource
                else accountability_case_summary(case)
            )
            print(json.dumps(payload, sort_keys=True))
        return 0

    if args.cmd == "create":
        case = create_accountability_case(
            trigger_ref=args.trigger_ref,
            accountable_role=args.accountable_role,
            responsible_actor=args.responsible_actor,
            decision_right_basis=args.decision_right_basis,
            authority_envelope_ref=args.authority_envelope_ref,
            risk_tier=args.risk_tier,
            recourse_path=args.recourse_path,
            residual_risk_accepted_by=args.residual_risk_accepted_by,
            review_sla=args.review_sla,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            due_at_utc=args.due_at_utc,
            externality_tags=args.externality_tag,
            operator_burden=args.operator_burden,
            rationale=args.rationale,
            log_path=args.log_path,
        )
        print(json.dumps(accountability_case_summary(case), sort_keys=True))
        return 0

    if args.cmd == "update":
        case = update_accountability_case_status(
            args.case_id,
            args.status,
            closure_evidence_refs=args.closure_evidence_ref or None,
            residual_risk_accepted_by=args.residual_risk_accepted_by,
            log_path=args.log_path,
        )
        print(json.dumps(accountability_case_summary(case), sort_keys=True))
        return 0

    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
