"""Governed self-modification proposals.

Recursive systems need a way to improve their own governance without letting
the proposer become the evaluator of its own constraints. This module records
proposed governance changes and runs simple deterministic invariant checks. It
does not apply the proposed change.
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


GovernanceChangeKind = Literal[
    "mandate_change",
    "role_change",
    "project_charter_change",
    "route_policy_change",
    "capability_policy_change",
    "gate_policy_change",
    "learning_policy_change",
    "tenant_policy_change",
]
GovernanceChangeStatus = Literal["proposed", "blocked", "review_ready", "approved", "rejected", "superseded"]
InvariantStatus = Literal["pass", "fail", "unknown"]

DEFAULT_GOVERNANCE_CHANGES_LOG = ORG_ROOT_DIR / "governance_changes" / "governance_changes.jsonl"
VALID_CHANGE_KINDS = {
    "mandate_change",
    "role_change",
    "project_charter_change",
    "route_policy_change",
    "capability_policy_change",
    "gate_policy_change",
    "learning_policy_change",
    "tenant_policy_change",
}
VALID_STATUSES = {"proposed", "blocked", "review_ready", "approved", "rejected", "superseded"}
VALID_INVARIANT_STATUSES = {"pass", "fail", "unknown"}
REQUIRED_INVARIANTS = {
    "principal_independence",
    "deterministic_enforcement_floor",
    "fail_closed_behavior",
    "write_scope_preserved",
    "tenant_boundary_preserved",
}


@dataclass(frozen=True)
class InvariantCheck:
    invariant: str
    status: InvariantStatus
    rationale: str
    evidence_refs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernanceChangeProposal:
    proposal_id: str
    created_at_utc: str
    change_kind: GovernanceChangeKind
    title: str
    proposed_by: str
    target_ref: str
    rationale: str
    status: GovernanceChangeStatus = "proposed"
    source_refs: list[str] = field(default_factory=list)
    expected_behavior_change: str | None = None
    risk_summary: str | None = None
    rollback_plan: str | None = None
    owner_role: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    invariant_checks: list[InvariantCheck] = field(default_factory=list)
    approval_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def review_ready(self) -> bool:
        statuses = {check.invariant: check.status for check in self.invariant_checks}
        return all(statuses.get(invariant) == "pass" for invariant in REQUIRED_INVARIANTS)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["review_ready"] = self.review_ready
        return payload


def propose_governance_change(
    *,
    change_kind: GovernanceChangeKind | str,
    title: str,
    proposed_by: str,
    target_ref: str,
    rationale: str,
    source_refs: list[str] | None = None,
    expected_behavior_change: str | None = None,
    risk_summary: str | None = None,
    rollback_plan: str | None = None,
    owner_role: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    invariant_checks: list[InvariantCheck | dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    proposal_id: str | None = None,
    log_path: Path | None = None,
) -> GovernanceChangeProposal:
    """Record a proposed governance change after deterministic checks."""
    if not title.strip():
        raise ValueError("title is required")
    if not proposed_by.strip():
        raise ValueError("proposed_by is required")
    if not target_ref.strip():
        raise ValueError("target_ref is required")
    if not rationale.strip():
        raise ValueError("rationale is required")

    checks = normalize_invariant_checks(invariant_checks or [])
    proposal = GovernanceChangeProposal(
        proposal_id=proposal_id or f"gcp_{uuid.uuid4().hex[:12]}",
        created_at_utc=_now_iso(),
        change_kind=_validate_change_kind(str(change_kind)),
        title=title,
        proposed_by=proposed_by,
        target_ref=target_ref,
        rationale=rationale,
        status="review_ready" if _checks_review_ready(checks) else "blocked",
        source_refs=source_refs or [],
        expected_behavior_change=expected_behavior_change,
        risk_summary=risk_summary,
        rollback_plan=rollback_plan,
        owner_role=owner_role,
        tenant_id=tenant_id,
        project_id=project_id,
        invariant_checks=checks,
        metadata=metadata or {},
    )
    _append_jsonl(log_path or DEFAULT_GOVERNANCE_CHANGES_LOG, proposal.as_dict())
    return proposal


def list_governance_changes(
    *,
    status: GovernanceChangeStatus | str | None = None,
    change_kind: GovernanceChangeKind | str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> list[GovernanceChangeProposal]:
    """Read governance change proposals, optionally filtered."""
    if status is not None:
        status = _validate_status(str(status))
    if change_kind is not None:
        change_kind = _validate_change_kind(str(change_kind))

    out: list[GovernanceChangeProposal] = []
    for row in _read_jsonl(log_path or DEFAULT_GOVERNANCE_CHANGES_LOG):
        row = dict(row)
        row.pop("review_ready", None)
        row["invariant_checks"] = normalize_invariant_checks(row.get("invariant_checks") or [])
        proposal = GovernanceChangeProposal(**row)
        if status is not None and proposal.status != status:
            continue
        if change_kind is not None and proposal.change_kind != change_kind:
            continue
        if tenant_id is not None and proposal.tenant_id != tenant_id:
            continue
        if project_id is not None and proposal.project_id != project_id:
            continue
        out.append(proposal)
    return out


def normalize_invariant_checks(rows: list[InvariantCheck | dict[str, Any]]) -> list[InvariantCheck]:
    checks: list[InvariantCheck] = []
    for row in rows:
        if isinstance(row, InvariantCheck):
            checks.append(row)
            continue
        if not isinstance(row, dict):
            continue
        checks.append(
            InvariantCheck(
                invariant=str(row.get("invariant") or ""),
                status=_validate_invariant_status(str(row.get("status") or "unknown")),
                rationale=str(row.get("rationale") or ""),
                evidence_refs=_string_list(row.get("evidence_refs") or row.get("source_refs") or []),
            )
        )
    return checks


def missing_required_invariants(checks: list[InvariantCheck]) -> list[str]:
    present = {check.invariant for check in checks if check.status == "pass"}
    return sorted(REQUIRED_INVARIANTS - present)


def failed_invariants(checks: list[InvariantCheck]) -> list[str]:
    return sorted(check.invariant for check in checks if check.status == "fail")


def _checks_review_ready(checks: list[InvariantCheck]) -> bool:
    return not missing_required_invariants(checks) and not failed_invariants(checks)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_change_kind(kind: str) -> GovernanceChangeKind:
    if kind not in VALID_CHANGE_KINDS:
        raise ValueError(f"invalid change_kind {kind!r}; expected one of {sorted(VALID_CHANGE_KINDS)}")
    return kind  # type: ignore[return-value]


def _validate_status(status: str) -> GovernanceChangeStatus:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}; expected one of {sorted(VALID_STATUSES)}")
    return status  # type: ignore[return-value]


def _validate_invariant_status(status: str) -> InvariantStatus:
    if status not in VALID_INVARIANT_STATUSES:
        raise ValueError(
            f"invalid invariant status {status!r}; expected one of {sorted(VALID_INVARIANT_STATUSES)}"
        )
    return status  # type: ignore[return-value]


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


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _string_list(payload: Any) -> list[str]:
    if isinstance(payload, list):
        return [str(item) for item in payload if item]
    if payload:
        return [str(payload)]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage governed self-modification proposals.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--status")
    list_parser.add_argument("--change-kind")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--log-path", type=Path)

    propose_parser = sub.add_parser("propose")
    propose_parser.add_argument("--change-kind", required=True)
    propose_parser.add_argument("--title", required=True)
    propose_parser.add_argument("--proposed-by", required=True)
    propose_parser.add_argument("--target-ref", required=True)
    propose_parser.add_argument("--rationale", required=True)
    propose_parser.add_argument("--source-ref", action="append", default=[])
    propose_parser.add_argument("--expected-behavior-change")
    propose_parser.add_argument("--risk-summary")
    propose_parser.add_argument("--rollback-plan")
    propose_parser.add_argument("--owner-role")
    propose_parser.add_argument("--tenant-id")
    propose_parser.add_argument("--project-id")
    propose_parser.add_argument(
        "--invariant-check-json",
        action="append",
        default=[],
        help="JSON object with invariant, status, rationale, and optional evidence_refs.",
    )
    propose_parser.add_argument("--log-path", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "list":
        proposals = list_governance_changes(
            status=args.status,
            change_kind=args.change_kind,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
        )
        print(json.dumps([proposal.as_dict() for proposal in proposals], indent=2, sort_keys=True))
        return 0

    checks = [json.loads(row) for row in args.invariant_check_json]
    proposal = propose_governance_change(
        change_kind=args.change_kind,
        title=args.title,
        proposed_by=args.proposed_by,
        target_ref=args.target_ref,
        rationale=args.rationale,
        source_refs=args.source_ref,
        expected_behavior_change=args.expected_behavior_change,
        risk_summary=args.risk_summary,
        rollback_plan=args.rollback_plan,
        owner_role=args.owner_role,
        tenant_id=args.tenant_id,
        project_id=args.project_id,
        invariant_checks=checks,
        log_path=args.log_path,
    )
    print(json.dumps(proposal.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
