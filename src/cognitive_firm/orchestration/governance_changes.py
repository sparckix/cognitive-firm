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
FORMAL_PROOF_CHANGE_KINDS = {
    "route_policy_change",
    "capability_policy_change",
    "gate_policy_change",
    "tenant_policy_change",
}
FORMAL_PROOF_TARGET_HINTS = {
    "adapter",
    "capability",
    "contract",
    "gate",
    "policy",
    "provider",
    "runtime",
    "schema",
    "verifier",
}
FORMAL_VERIFICATION_REF_PREFIXES = (
    "formal_verification:",
    "formal-verification:",
)


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


def governance_change_request_template(
    *,
    change_kind: GovernanceChangeKind | str = "route_policy_change",
    title: str | None = None,
    proposed_by: str | None = None,
    target_ref: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Return a POST body skeleton for an evidence-complete proposal."""
    return {
        "change_kind": _validate_change_kind(str(change_kind)),
        "title": title or "<short human-readable title>",
        "proposed_by": proposed_by or "<role-or-actor>",
        "target_ref": target_ref or "<mandate/role/policy/ref>",
        "rationale": "<why this governance change is being proposed>",
        "source_refs": ["<evidence-ref>"],
        "expected_behavior_change": "<what should change if approved>",
        "predicted_effect": {
            "metric_name": "<metric>",
            "expected_direction": "increase|decrease|maintain",
            "expected_window": "<review window>",
        },
        "risk_summary": "<operator-visible risk summary>",
        "rollback_plan": "<how to revert or retire the change>",
        "tenant_id": tenant_id,
        "project_id": project_id,
        "invariant_checks": [
            {
                "invariant": invariant,
                "status": "unknown",
                "rationale": "<why this invariant is preserved>",
                "evidence_refs": ["<evidence-ref>"],
            }
            for invariant in sorted(REQUIRED_INVARIANTS)
        ],
    }


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


def governance_change_review_projection(
    proposal: GovernanceChangeProposal,
    *,
    decided: bool = False,
) -> dict[str, Any]:
    """Return a compact, read-only proposal review projection.

    App surfaces should not reimplement governance-change evidence logic just
    to render a review queue. This projection summarizes the canonical
    proposal row into the facts a human reviewer or dashboard needs while
    leaving proposal creation, decision, and lifecycle rules with the kernel
    service routes.
    """

    sufficiency = proposal.evidence_sufficiency
    missing_evidence = (
        list(sufficiency.missing)
        if sufficiency is not None
        else sorted(REQUIRED_EVIDENCE_FIELDS)
    )
    failed = failed_invariants(proposal.invariant_checks)
    missing_required = missing_required_invariants(proposal.invariant_checks)
    passed_required = sorted(
        check.invariant
        for check in proposal.invariant_checks
        if check.invariant in REQUIRED_INVARIANTS and check.status == "pass"
    )
    unknown = sorted(
        check.invariant
        for check in proposal.invariant_checks
        if check.status == "unknown"
    )
    evidence_refs = _governance_change_evidence_refs(proposal)
    proof_obligations = governance_change_proof_obligations(proposal)
    if decided:
        review_state = "decided"
    elif proof_obligations["blocking"]:
        review_state = "blocked"
    elif proposal.status == "review_ready" and proposal.review_ready:
        review_state = "awaiting_review"
    elif proposal.status == "blocked" or failed or missing_evidence:
        review_state = "blocked"
    else:
        review_state = proposal.status

    predicted = proposal.predicted_effect or {}
    prediction_summary = None
    if predicted:
        bits = [
            str(value)
            for value in (
                predicted.get("metric_name") or predicted.get("metric"),
                predicted.get("expected_direction") or predicted.get("direction"),
                predicted.get("expected_window") or predicted.get("window"),
            )
            if value
        ]
        prediction_summary = ", ".join(bits) if bits else None

    return {
        "proposal_id": proposal.proposal_id,
        "created_at_utc": proposal.created_at_utc,
        "change_kind": proposal.change_kind,
        "title": proposal.title,
        "target_ref": proposal.target_ref,
        "proposed_by": proposal.proposed_by,
        "owner_role": proposal.owner_role,
        "tenant_id": proposal.tenant_id,
        "project_id": proposal.project_id,
        "status": proposal.status,
        "decided": decided,
        "review_state": review_state,
        "review_ready": proposal.review_ready,
        "expected_behavior_change": proposal.expected_behavior_change,
        "risk_summary": proposal.risk_summary,
        "rollback_plan": proposal.rollback_plan,
        "prediction_summary": prediction_summary,
        "evidence_status": sufficiency.status if sufficiency else "unknown",
        "missing_evidence": missing_evidence,
        "failed_invariants": failed,
        "missing_required_invariants": missing_required,
        "unknown_invariants": unknown,
        "passed_required_invariants": passed_required,
        "required_invariants": sorted(REQUIRED_INVARIANTS),
        "source_ref_count": len(proposal.source_refs),
        "evidence_ref_count": len(evidence_refs),
        "proof_obligations": proof_obligations,
        "decision_route": (
            f"POST /kernel/governance-changes/{proposal.proposal_id}/decision"
        ),
        "read_only": True,
    }


def governance_change_proof_obligations(
    proposal: GovernanceChangeProposal,
) -> dict[str, Any]:
    """Return a read-only formal-proof review signal for one proposal.

    Formal verification remains evidence, not authority. This helper only tells
    proposal reviewers whether a policy/provider/adapter-shaped proposal cites
    formal-verification refs, or whether metadata explicitly made such refs a
    prerequisite for review.
    """

    evidence_refs = _governance_change_evidence_refs(proposal)
    formal_refs = [
        ref for ref in evidence_refs if _is_formal_verification_ref(ref)
    ]
    metadata_obligations = _formal_proof_obligation_rows(
        proposal.metadata.get("formal_proof_obligations")
    )
    explicitly_required = _metadata_bool(
        proposal.metadata,
        "requires_formal_verification",
        "formal_proof_required",
        "proof_obligation_required",
    )
    expected = (
        explicitly_required
        or bool(metadata_obligations)
        or proposal.change_kind in FORMAL_PROOF_CHANGE_KINDS
        or _target_has_formal_proof_hint(proposal.target_ref)
    )
    required = explicitly_required or any(
        row["required"] for row in metadata_obligations
    )
    missing = ["formal_verification_ref"] if expected and not formal_refs else []
    blocking = bool(required and missing)
    if not expected and not formal_refs:
        status = "not_expected"
        rationale = "proposal does not match a formal-proof-sensitive surface"
    elif missing and blocking:
        status = "blocking"
        rationale = "metadata requires formal-verification evidence before review"
    elif missing:
        status = "attention"
        rationale = "policy/provider/adapter-shaped change has no formal-verification ref"
    else:
        status = "satisfied"
        rationale = "proposal cites formal-verification evidence refs"

    obligations = metadata_obligations
    if not obligations and expected:
        obligations = [
            {
                "obligation_id": "formal_verification_ref",
                "property_class": None,
                "subject_ref": proposal.target_ref,
                "required": required,
                "formal_verification_refs": formal_refs,
                "satisfied": bool(formal_refs),
            }
        ]

    return {
        "status": status,
        "expected": bool(expected),
        "required": bool(required),
        "blocking": blocking,
        "missing": missing,
        "formal_verification_refs": formal_refs,
        "accepted_ref_prefixes": list(FORMAL_VERIFICATION_REF_PREFIXES),
        "obligations": [
            {
                **row,
                "formal_verification_refs": (
                    row["formal_verification_refs"] or formal_refs
                ),
                "satisfied": bool(row["formal_verification_refs"] or formal_refs),
            }
            for row in obligations
        ],
        "rationale": rationale,
        "read_only": True,
        "projection_only": True,
    }


def governance_change_review_packet(
    proposal: GovernanceChangeProposal,
    *,
    decided: bool = False,
    provenance_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a portable read-only handoff for one proposal review.

    This packages the existing proposal-review projection with evidence refs,
    invariant rows, optional provenance-report context, and Markdown. It does
    not approve, reject, mutate, or create a separate proposal lifecycle.
    """
    review = governance_change_review_projection(proposal, decided=decided)
    evidence_refs = _governance_change_evidence_ref_rows(proposal)
    provenance_summary: dict[str, Any] | None = None
    if provenance_report:
        provenance_summary = {
            "query": provenance_report.get("query", {}),
            "summary": provenance_report.get("summary", {}),
            "coverage": provenance_report.get("coverage", {}),
            "follow_through": provenance_report.get("follow_through", {}),
            "caveats": list(provenance_report.get("caveats", []) or []),
            "event_excerpt": list(provenance_report.get("event_excerpt", []) or []),
            "evidence_refs": list(provenance_report.get("evidence_refs", []) or []),
        }
    packet = {
        "packet_kind": "governance_change_review_handoff",
        "proposal_id": proposal.proposal_id,
        "read_only": True,
        "projection_only": True,
        "review": review,
        "decision_route": review["decision_route"],
        "proof_obligations": review["proof_obligations"],
        "follow_through": (
            provenance_summary.get("follow_through", {})
            if provenance_summary
            else {}
        ),
        "evidence_refs": evidence_refs,
        "invariant_checks": [
            {
                "invariant": check.invariant,
                "status": check.status,
                "rationale": check.rationale,
                "evidence_refs": list(check.evidence_refs),
            }
            for check in proposal.invariant_checks
        ],
        "review_questions": _governance_review_questions(
            review,
            provenance_summary=provenance_summary,
        ),
        "provenance_report": provenance_summary,
    }
    packet["markdown"] = _render_governance_review_packet_markdown(packet)
    return packet


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


def _governance_change_evidence_refs(
    proposal: GovernanceChangeProposal,
) -> list[str]:
    sufficiency = proposal.evidence_sufficiency
    return list(
        dict.fromkeys(
            [
                *proposal.source_refs,
                *(sufficiency.evidence_refs if sufficiency is not None else []),
                *[
                    ref
                    for check in proposal.invariant_checks
                    for ref in check.evidence_refs
                ],
            ]
        )
    )


def _governance_change_evidence_ref_rows(
    proposal: GovernanceChangeProposal,
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for ref in proposal.source_refs:
        row = rows.setdefault(
            ref,
            {"ref": ref, "sources": [], "invariants": []},
        )
        if "source_refs" not in row["sources"]:
            row["sources"].append("source_refs")
    sufficiency = proposal.evidence_sufficiency
    if sufficiency is not None:
        for ref in sufficiency.evidence_refs:
            row = rows.setdefault(
                ref,
                {"ref": ref, "sources": [], "invariants": []},
            )
            if "evidence_sufficiency" not in row["sources"]:
                row["sources"].append("evidence_sufficiency")
    for check in proposal.invariant_checks:
        for ref in check.evidence_refs:
            row = rows.setdefault(
                ref,
                {"ref": ref, "sources": [], "invariants": []},
            )
            if "invariant_check" not in row["sources"]:
                row["sources"].append("invariant_check")
            if check.invariant not in row["invariants"]:
                row["invariants"].append(check.invariant)
    return sorted(rows.values(), key=lambda row: row["ref"])


def _is_formal_verification_ref(ref: str) -> bool:
    normalized = ref.strip().lower()
    return normalized.startswith(FORMAL_VERIFICATION_REF_PREFIXES)


def _target_has_formal_proof_hint(target_ref: str) -> bool:
    normalized = target_ref.strip().lower().replace("_", "-")
    tokens = {
        token
        for chunk in normalized.replace(":", "/").replace(".", "/").split("/")
        for token in chunk.replace("-", " ").split()
        if token
    }
    return bool(tokens & FORMAL_PROOF_TARGET_HINTS)


def _metadata_bool(metadata: dict[str, Any], *keys: str) -> bool:
    return any(metadata.get(key) is True for key in keys)


def _formal_proof_obligation_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        refs = _string_list(item.get("formal_verification_refs") or [])
        rows.append(
            {
                "obligation_id": str(
                    item.get("obligation_id")
                    or item.get("property_class")
                    or f"formal_proof_obligation_{index + 1}"
                ),
                "property_class": (
                    str(item["property_class"]) if item.get("property_class") else None
                ),
                "subject_ref": (
                    str(item["subject_ref"]) if item.get("subject_ref") else None
                ),
                "required": item.get("required") is not False,
                "formal_verification_refs": refs,
                "satisfied": bool(refs),
            }
        )
    return rows


def _governance_review_questions(
    review: dict[str, Any],
    *,
    provenance_summary: dict[str, Any] | None,
) -> list[str]:
    questions = [
        "Do the cited refs support the expected behavior change?",
        "Are the risks and rollback plan acceptable for this target?",
    ]
    if review.get("review_state") == "awaiting_review":
        questions.append("Should the accountable actor approve or decline this proposal?")
    if review.get("missing_evidence"):
        questions.append("Which missing evidence must be supplied before review?")
    if review.get("failed_invariants"):
        questions.append("Should failed invariants block the proposal or trigger a revised proposal?")
    if review.get("unknown_invariants"):
        questions.append("Which unknown invariants need evidence before a decision?")
    if review.get("prediction_summary"):
        questions.append("What outcome link or routine review will test the predicted effect?")
    follow_through = (provenance_summary or {}).get("follow_through") or {}
    for question in follow_through.get("review_questions") or []:
        text = str(question)
        if text not in questions:
            questions.append(text)
    proof = review.get("proof_obligations") or {}
    if proof.get("blocking"):
        questions.append("Which formal-verification evidence is required before review can proceed?")
    elif proof.get("status") == "attention":
        questions.append("Should this policy/provider/adapter-shaped change cite formal-verification evidence before approval?")
    if provenance_summary:
        gaps = provenance_summary.get("coverage", {}).get("gaps") or []
        if gaps:
            questions.append("Do the provenance coverage gaps matter for this decision?")
    return questions


def _render_governance_review_packet_markdown(packet: dict[str, Any]) -> str:
    review = packet["review"]
    lines = [
        "# Governance Change Review Packet",
        "",
        "Read-only projection over the proposal row and selected provenance.",
        "",
        f"Proposal: {packet['proposal_id']}",
        f"State: {review.get('review_state')} ({review.get('status')})",
        f"Kind: {review.get('change_kind')}",
        f"Target: {review.get('target_ref')}",
        f"Title: {review.get('title')}",
    ]
    if review.get("expected_behavior_change"):
        lines.append(f"Expected change: {review.get('expected_behavior_change')}")
    if review.get("risk_summary"):
        lines.append(f"Risk: {review.get('risk_summary')}")
    if review.get("rollback_plan"):
        lines.append(f"Rollback: {review.get('rollback_plan')}")
    if review.get("prediction_summary"):
        lines.append(f"Prediction: {review.get('prediction_summary')}")
    lines.append("")

    follow_through = packet.get("follow_through") or {}
    if follow_through:
        lines.extend(["## Follow-Through", ""])
        lines.append(f"- status: {follow_through.get('status')}")
        lines.append(f"- decision events: {follow_through.get('decision_events', 0)}")
        lines.append(f"- outcome links: {follow_through.get('outcome_links', 0)}")
        lines.append(f"- routine reviews: {follow_through.get('routine_reviews', 0)}")
        lines.append(
            f"- learning-use receipts: {follow_through.get('learning_use_receipts', 0)}"
        )
        for ref in follow_through.get("latest_refs") or []:
            lines.append(f"- ref: {ref}")
        lines.append("")

    proof = packet.get("proof_obligations") or {}
    if proof.get("expected") or proof.get("formal_verification_refs"):
        lines.extend(["## Proof Obligations", ""])
        lines.append(f"- status: {proof.get('status')}")
        lines.append(f"- required: {proof.get('required')}")
        for missing in proof.get("missing") or []:
            lines.append(f"- missing: {missing}")
        for ref in proof.get("formal_verification_refs") or []:
            lines.append(f"- formal evidence: {ref}")
        lines.append("")

    gaps = review.get("missing_evidence") or []
    if gaps:
        lines.extend(["## Missing Evidence", ""])
        for gap in gaps:
            lines.append(f"- {gap}")
        lines.append("")

    failed = review.get("failed_invariants") or []
    unknown = review.get("unknown_invariants") or []
    if failed or unknown:
        lines.extend(["## Invariant Attention", ""])
        for invariant in failed:
            lines.append(f"- failed: {invariant}")
        for invariant in unknown:
            lines.append(f"- unknown: {invariant}")
        lines.append("")

    evidence_refs = packet.get("evidence_refs") or []
    if evidence_refs:
        lines.extend(["## Evidence Refs", ""])
        for row in evidence_refs[:20]:
            sources = ",".join(row.get("sources") or [])
            invariants = ",".join(row.get("invariants") or [])
            suffix = f" [{sources}]"
            if invariants:
                suffix = f"{suffix} invariants={invariants}"
            lines.append(f"- {row.get('ref')}{suffix}")
        if len(evidence_refs) > 20:
            lines.append(f"- ... {len(evidence_refs) - 20} more ref(s)")
        lines.append("")

    provenance = packet.get("provenance_report") or {}
    if provenance:
        summary = provenance.get("summary") or {}
        coverage = provenance.get("coverage") or {}
        lines.extend(["## Provenance", ""])
        lines.append(f"- events: {summary.get('event_count', 0)}")
        lines.append(f"- coverage: {coverage.get('status')}")
        for caveat in provenance.get("caveats") or []:
            lines.append(f"- caveat: {caveat}")
        lines.append("")

    questions = packet.get("review_questions") or []
    if questions:
        lines.extend(["## Review Questions", ""])
        for question in questions:
            lines.append(f"- {question}")
        lines.append("")

    lines.extend(["## Decision Route", "", f"`{packet['decision_route']}`"])
    return "\n".join(lines).rstrip() + "\n"


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
