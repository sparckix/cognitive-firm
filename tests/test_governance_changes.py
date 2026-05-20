from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.governance_changes import (  # noqa: E402
    REQUIRED_INVARIANTS,
    InvariantCheck,
    failed_invariants,
    list_governance_changes,
    missing_required_invariants,
    propose_governance_change,
)


def _passing_checks() -> list[InvariantCheck]:
    return [
        InvariantCheck(
            invariant=invariant,
            status="pass",
            rationale=f"{invariant} preserved by deterministic guard.",
            evidence_refs=[f"tests/{invariant}.txt"],
        )
        for invariant in sorted(REQUIRED_INVARIANTS)
    ]


def test_governance_change_requires_all_invariants_for_review_ready(tmp_path: Path):
    log_path = tmp_path / "governance_changes.jsonl"

    proposal = propose_governance_change(
        change_kind="mandate_change",
        title="Tighten reviewer write scope",
        proposed_by="role.research_director",
        target_ref="org/mandates/reviewer_mandate.md",
        rationale="Repeated scope drift requires a narrower default write boundary.",
        expected_behavior_change="Reviewer can edit review artifacts only unless escalated.",
        rollback_plan="Restore previous mandate hash.",
        invariant_checks=_passing_checks(),
        log_path=log_path,
    )

    assert proposal.status == "review_ready"
    assert proposal.review_ready is True
    assert missing_required_invariants(proposal.invariant_checks) == []
    assert failed_invariants(proposal.invariant_checks) == []

    proposals = list_governance_changes(status="review_ready", log_path=log_path)
    assert [item.proposal_id for item in proposals] == [proposal.proposal_id]


def test_governance_change_blocks_missing_or_failed_invariants(tmp_path: Path):
    log_path = tmp_path / "governance_changes.jsonl"
    checks = [
        InvariantCheck(
            invariant="principal_independence",
            status="pass",
            rationale="Principal approval remains required.",
        ),
        InvariantCheck(
            invariant="write_scope_preserved",
            status="fail",
            rationale="Proposed route would let a role edit its own mandate.",
        ),
    ]

    proposal = propose_governance_change(
        change_kind="route_policy_change",
        title="Allow role to self-route governance changes",
        proposed_by="role.manager",
        target_ref="org/policies/routing.md",
        rationale="Would reduce review latency.",
        invariant_checks=checks,
        log_path=log_path,
    )

    assert proposal.status == "blocked"
    assert proposal.review_ready is False
    assert "write_scope_preserved" in failed_invariants(proposal.invariant_checks)
    assert "deterministic_enforcement_floor" in missing_required_invariants(proposal.invariant_checks)


def test_governance_change_keeps_approval_separate_from_proposal(tmp_path: Path):
    proposal = propose_governance_change(
        change_kind="gate_policy_change",
        title="Add new fail-closed gate",
        proposed_by="role.engineer",
        target_ref="docs/protocols/h2a.md",
        rationale="A new external action needs explicit operator approval.",
        invariant_checks=_passing_checks(),
        log_path=tmp_path / "governance_changes.jsonl",
    )

    assert proposal.approval_ref is None
    assert proposal.status == "review_ready"
