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
from cognitive_firm.orchestration.outcome_links import predicted_effect_from_dict
from cognitive_firm.orchestration.resource_envelope import KernelResource, make_resource


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
REQUIRED_EVIDENCE_FIELDS = {
    "source_refs",
    "expected_behavior_change",
    "risk_summary",
    "rollback_plan",
    "invariant_evidence_refs",
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
class EvidenceSufficiencyCheck:
    status: InvariantStatus
    rationale: str
    missing: list[str] = field(default_factory=list)
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
    predicted_effect: dict[str, Any] | None = None
    risk_summary: str | None = None
    rollback_plan: str | None = None
    owner_role: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    invariant_checks: list[InvariantCheck] = field(default_factory=list)
    evidence_sufficiency: EvidenceSufficiencyCheck | None = None
    approval_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def review_ready(self) -> bool:
        statuses = {check.invariant: check.status for check in self.invariant_checks}
        invariants_ready = all(
            statuses.get(invariant) == "pass" for invariant in REQUIRED_INVARIANTS
        )
        evidence_ready = (
            self.evidence_sufficiency is not None
            and self.evidence_sufficiency.status == "pass"
        )
        return invariants_ready and evidence_ready

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
    predicted_effect: dict[str, Any] | None = None,
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
    normalized_predicted_effect = normalize_predicted_effect(predicted_effect)
    evidence_sufficiency = assess_evidence_sufficiency(
        source_refs=source_refs or [],
        expected_behavior_change=expected_behavior_change,
        predicted_effect=normalized_predicted_effect,
        risk_summary=risk_summary,
        rollback_plan=rollback_plan,
        invariant_checks=checks,
    )
    proposal = GovernanceChangeProposal(
        proposal_id=proposal_id or f"gcp_{uuid.uuid4().hex[:12]}",
        created_at_utc=_now_iso(),
        change_kind=_validate_change_kind(str(change_kind)),
        title=title,
        proposed_by=proposed_by,
        target_ref=target_ref,
        rationale=rationale,
        status=(
            "review_ready"
            if _checks_review_ready(checks) and evidence_sufficiency.status == "pass"
            else "blocked"
        ),
        source_refs=source_refs or [],
        expected_behavior_change=expected_behavior_change,
        predicted_effect=normalized_predicted_effect,
        risk_summary=risk_summary,
        rollback_plan=rollback_plan,
        owner_role=owner_role,
        tenant_id=tenant_id,
        project_id=project_id,
        invariant_checks=checks,
        evidence_sufficiency=evidence_sufficiency,
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
        row["evidence_sufficiency"] = normalize_evidence_sufficiency(
            row.get("evidence_sufficiency"),
            source_refs=row.get("source_refs") or [],
            expected_behavior_change=row.get("expected_behavior_change"),
            predicted_effect=row.get("predicted_effect"),
            risk_summary=row.get("risk_summary"),
            rollback_plan=row.get("rollback_plan"),
            invariant_checks=row["invariant_checks"],
        )
        row["predicted_effect"] = normalize_predicted_effect(row.get("predicted_effect"))
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


def classify_governance_change_tier(
    *,
    target_ref: str,
    change_kind: GovernanceChangeKind | str,
) -> dict[str, str]:
    """Classify amendment tier for a proposed governance target.

    This is a standard check helper. It does not decide or approve the
    proposal; callers include the resulting invariant check as review evidence.
    """

    target = str(target_ref or "").strip()
    kind = str(change_kind or "").strip()
    if not target:
        raise ValueError("target_ref is required for tier classification")
    immutable_targets = (
        "docs/kernel-invariants.md",
        "org/invariants/",
        "org/roles/principal",
        "org/mandates/principal",
        "org/authority/principal",
    )
    tier_one_targets = (
        "org/charters/",
        "org/workload/scorecards/",
        "org/workload/scoring/",
    )
    tier_two_targets = (
        "org/roles/",
        "org/mandates/",
        "org/policies/",
        "org/reviews/",
        "org/decision_models/",
        "org/learning_events/",
    )
    if target == "AGENTS.md" or target.startswith(immutable_targets):
        return {
            "tier": "tier_0_immutable",
            "required_approval_path": "not_admissible",
            "rationale": (
                "target affects immutable authority, invariant, or "
                "principal-control surface"
            ),
        }
    if kind == "project_charter_change" or target.startswith(tier_one_targets):
        return {
            "tier": "tier_1_principal_only",
            "required_approval_path": "principal_explicit_approval",
            "rationale": (
                "target affects charter, capability definition, or scoring "
                "interface"
            ),
        }
    if target.startswith(tier_two_targets):
        return {
            "tier": "tier_2_governed_mutation",
            "required_approval_path": "ordinary_governed_mutation",
            "rationale": "target affects ordinary governed organization structure",
        }
    return {
        "tier": "tier_2_governed_mutation",
        "required_approval_path": "ordinary_governed_mutation",
        "rationale": "target is not a known immutable or principal-only surface",
    }


def tier_classification_invariant_check(
    *,
    target_ref: str,
    change_kind: GovernanceChangeKind | str,
    evidence_refs: list[str] | None = None,
) -> InvariantCheck:
    """Return a standard invariant check for amendment-tier classification."""

    classification = classify_governance_change_tier(
        target_ref=target_ref,
        change_kind=change_kind,
    )
    tier = classification["tier"]
    status: InvariantStatus = "fail" if tier == "tier_0_immutable" else "pass"
    refs = _string_list(evidence_refs or [])
    refs.append(f"tier_classification:{tier}")
    return InvariantCheck(
        invariant="amendment_tier_classified",
        status=status,
        rationale=(
            f"{tier}; required approval path: "
            f"{classification['required_approval_path']}; "
            f"{classification['rationale']}"
        ),
        evidence_refs=refs,
    )


def deletion_duty_invariant_check(
    *,
    target_ref: str,
    change_kind: GovernanceChangeKind | str,
    retirement_candidate_ref: str | None = None,
    net_growth_justification: str | None = None,
    evidence_refs: list[str] | None = None,
) -> InvariantCheck:
    """Return an optional net-growth/deletion-duty check.

    This check is for charters that want structural additions to name what can
    be retired, merged, or explicitly kept despite net growth. It does not make
    deletion mandatory across the kernel; callers opt in by adding the check to
    a proposal's invariant evidence.
    """

    target = str(target_ref or "").strip()
    kind = str(change_kind or "").strip()
    if not target:
        raise ValueError("target_ref is required for deletion-duty check")
    structural_addition = kind in {
        "role_change",
        "route_policy_change",
        "capability_policy_change",
        "gate_policy_change",
        "learning_policy_change",
        "tenant_policy_change",
    } or target.startswith(
        (
            "org/roles/",
            "org/policies/",
            "org/decision_models/",
            "org/protocols/",
            "org/routes/",
        )
    )
    refs = _string_list(evidence_refs or [])
    if not structural_addition:
        refs.append("deletion_duty:not_applicable")
        return InvariantCheck(
            invariant="deletion_duty_checked",
            status="pass",
            rationale="target is not classified as a structure-adding change",
            evidence_refs=refs,
        )

    retirement = (retirement_candidate_ref or "").strip()
    justification = (net_growth_justification or "").strip()
    if retirement:
        refs.append(f"retirement_candidate:{retirement}")
        return InvariantCheck(
            invariant="deletion_duty_checked",
            status="pass",
            rationale="structure-adding proposal names a retirement candidate",
            evidence_refs=refs,
        )
    if justification:
        refs.append("net_growth_justification:present")
        return InvariantCheck(
            invariant="deletion_duty_checked",
            status="pass",
            rationale="structure-adding proposal justifies net growth",
            evidence_refs=refs,
        )
    refs.append("deletion_duty:missing_retirement_or_justification")
    return InvariantCheck(
        invariant="deletion_duty_checked",
        status="fail",
        rationale=(
            "structure-adding proposal must name a retirement candidate or "
            "justify net growth"
        ),
        evidence_refs=refs,
    )


def assess_evidence_sufficiency(
    *,
    source_refs: list[str],
    expected_behavior_change: str | None,
    predicted_effect: dict[str, Any] | None = None,
    risk_summary: str | None,
    rollback_plan: str | None,
    invariant_checks: list[InvariantCheck],
) -> EvidenceSufficiencyCheck:
    """Check whether a governance proposal cites enough evidence for review.

    This is a structural sufficiency check, not a domain judgment. It prevents a
    recursive system from moving a self-modification proposal to review with
    only prose and self-asserted invariant results.
    """
    missing: list[str] = []
    clean_sources = _string_list(source_refs)
    if not clean_sources:
        missing.append("source_refs")
    if not (expected_behavior_change or "").strip() and predicted_effect is None:
        missing.append("expected_behavior_change")
    if not (risk_summary or "").strip():
        missing.append("risk_summary")
    if not (rollback_plan or "").strip():
        missing.append("rollback_plan")

    for check in invariant_checks:
        if check.status == "pass" and not check.evidence_refs:
            missing.append(f"invariant_evidence_refs:{check.invariant}")

    evidence_refs = list(dict.fromkeys(
        [
            *clean_sources,
            *[
                ref
                for check in invariant_checks
                for ref in check.evidence_refs
            ],
        ]
    ))
    if missing:
        return EvidenceSufficiencyCheck(
            status="fail",
            rationale="governance change is missing required review evidence",
            missing=sorted(missing),
            evidence_refs=evidence_refs,
        )
    return EvidenceSufficiencyCheck(
        status="pass",
        rationale="governance change carries structural evidence for review",
        missing=[],
        evidence_refs=evidence_refs,
    )


def normalize_evidence_sufficiency(
    payload: EvidenceSufficiencyCheck | dict[str, Any] | None,
    *,
    source_refs: list[str],
    expected_behavior_change: str | None,
    predicted_effect: dict[str, Any] | None = None,
    risk_summary: str | None,
    rollback_plan: str | None,
    invariant_checks: list[InvariantCheck],
) -> EvidenceSufficiencyCheck:
    if isinstance(payload, EvidenceSufficiencyCheck):
        return payload
    if isinstance(payload, dict):
        return EvidenceSufficiencyCheck(
            status=_validate_invariant_status(str(payload.get("status") or "unknown")),
            rationale=str(payload.get("rationale") or ""),
            missing=sorted(_string_list(payload.get("missing") or [])),
            evidence_refs=_string_list(payload.get("evidence_refs") or []),
        )
    return assess_evidence_sufficiency(
        source_refs=source_refs,
        expected_behavior_change=expected_behavior_change,
        predicted_effect=predicted_effect,
        risk_summary=risk_summary,
        rollback_plan=rollback_plan,
        invariant_checks=invariant_checks,
    )


def normalize_predicted_effect(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate and normalize an optional governance-change predicted effect."""

    if payload is None:
        return None
    return predicted_effect_from_dict(payload).as_dict()


def missing_required_invariants(checks: list[InvariantCheck]) -> list[str]:
    present = {check.invariant for check in checks if check.status == "pass"}
    return sorted(REQUIRED_INVARIANTS - present)


def failed_invariants(checks: list[InvariantCheck]) -> list[str]:
    return sorted(check.invariant for check in checks if check.status == "fail")


def governance_change_resource(proposal: GovernanceChangeProposal) -> KernelResource:
    """Project a governance-change proposal into the common resource envelope.

    The proposal JSONL row remains canonical. The resource view is for adapters,
    dashboards, migration checks, and conformance fixtures that need a stable
    object shape for governed self-modification state.
    """
    labels = {
        "change_kind": proposal.change_kind,
        "status": proposal.status,
        "proposed_by": proposal.proposed_by,
        "target_ref": proposal.target_ref,
        "review_ready": str(proposal.review_ready).lower(),
    }
    if proposal.owner_role:
        labels["owner_role"] = proposal.owner_role

    links = [
        {"rel": "target", "href": proposal.target_ref},
        {"rel": "proposed_by", "href": proposal.proposed_by},
    ]
    if proposal.owner_role:
        links.append({"rel": "owner_role", "href": proposal.owner_role})
    if proposal.approval_ref:
        links.append({"rel": "approval", "href": proposal.approval_ref})
    for ref in proposal.source_refs:
        links.append({"rel": "source", "href": ref})
    if proposal.evidence_sufficiency:
        for ref in proposal.evidence_sufficiency.evidence_refs:
            links.append({"rel": "evidence", "href": ref})
    for check in proposal.invariant_checks:
        for ref in check.evidence_refs:
            links.append({"rel": f"invariant_evidence:{check.invariant}", "href": ref})

    return make_resource(
        kind="GovernanceChangeProposal",
        name=proposal.proposal_id,
        resource_id=proposal.proposal_id,
        tenant_id=proposal.tenant_id,
        project_id=proposal.project_id,
        stability="alpha",
        labels=labels,
        annotations={
            key: str(value)
            for key, value in proposal.metadata.items()
            if isinstance(key, str) and value is not None
        },
        spec={
            "change_kind": proposal.change_kind,
            "title": proposal.title,
            "target_ref": proposal.target_ref,
            "rationale": proposal.rationale,
            "proposed_by": proposal.proposed_by,
            "source_refs": proposal.source_refs,
            "expected_behavior_change": proposal.expected_behavior_change,
            "predicted_effect": proposal.predicted_effect,
            "risk_summary": proposal.risk_summary,
            "rollback_plan": proposal.rollback_plan,
            "owner_role": proposal.owner_role,
        },
        status={
            "status": proposal.status,
            "review_ready": proposal.review_ready,
            "invariant_checks": [check.as_dict() for check in proposal.invariant_checks],
            "evidence_sufficiency": (
                proposal.evidence_sufficiency.as_dict()
                if proposal.evidence_sufficiency
                else None
            ),
            "approval_ref": proposal.approval_ref,
            "created_at_utc": proposal.created_at_utc,
        },
        links=links,
    )


def governance_change_from_candidate(
    candidate: Any,
    *,
    target_ref: str,
    proposed_by: str,
    change_kind: GovernanceChangeKind | str | None = None,
    title: str | None = None,
    expected_behavior_change: str | None = None,
    predicted_effect: dict[str, Any] | None = None,
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
    """Create a reviewable governance proposal from a learning candidate.

    The candidate supplies evidence and rationale only. The caller must provide
    a concrete target, risk summary, rollback plan, and invariant evidence; the
    normal governance-change sufficiency gate decides whether the proposal is
    review-ready or blocked.
    """
    payload = candidate.as_dict() if hasattr(candidate, "as_dict") else dict(candidate)
    candidate_id = str(payload.get("candidate_id") or "").strip()
    if not candidate_id:
        raise ValueError("candidate_id is required")
    transition_kind = str(payload.get("transition_kind") or "")
    inferred_change_kind = change_kind or _change_kind_from_transition_kind(transition_kind)
    rationale = str(payload.get("rationale") or "").strip()
    review_question = str(payload.get("review_question") or "").strip()
    source_refs = _string_list(payload.get("source_refs") or [])
    object_ref = payload.get("object_ref")
    if object_ref:
        source_refs.append(str(object_ref))
    source_refs.append(f"learning_transition_candidate:{candidate_id}")
    source_refs = list(dict.fromkeys(source_refs))
    next_metadata = {
        **(metadata or {}),
        "candidate_id": candidate_id,
        "candidate_transition_kind": transition_kind,
        "candidate_source_kind": payload.get("source_kind"),
        "candidate_severity": payload.get("severity"),
        "candidate_proposed_payload": payload.get("proposed_payload") or {},
    }
    return propose_governance_change(
        change_kind=inferred_change_kind,
        title=title
        or f"Review {transition_kind or 'learning'} candidate {candidate_id}",
        proposed_by=proposed_by,
        target_ref=target_ref,
        rationale=rationale or review_question or f"Promote learning candidate {candidate_id}.",
        source_refs=source_refs,
        expected_behavior_change=expected_behavior_change,
        predicted_effect=predicted_effect,
        risk_summary=risk_summary,
        rollback_plan=rollback_plan,
        owner_role=owner_role or payload.get("suggested_owner_role"),
        tenant_id=tenant_id,
        project_id=project_id,
        invariant_checks=invariant_checks,
        metadata=next_metadata,
        proposal_id=proposal_id,
        log_path=log_path,
    )


def _change_kind_from_transition_kind(transition_kind: str) -> str:
    if transition_kind == "mandate_review":
        return "mandate_change"
    if transition_kind == "project_charter_update":
        return "project_charter_change"
    if transition_kind == "forecast_contract":
        return "route_policy_change"
    if transition_kind == "route_policy_change":
        return "route_policy_change"
    if transition_kind == "human_work_session":
        return "route_policy_change"
    if transition_kind == "evidence_gap":
        return "learning_policy_change"
    if transition_kind == "source_repair":
        return "learning_policy_change"
    return "role_change"


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
    list_parser.add_argument("--resource", action="store_true", help="render resource envelopes")

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
        payload = [
            governance_change_resource(proposal).as_dict()
            if args.resource
            else proposal.as_dict()
            for proposal in proposals
        ]
        print(json.dumps(payload, indent=2, sort_keys=True))
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
