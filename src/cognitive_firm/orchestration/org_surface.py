"""Organizational surface read model.

The kernel's system of record is intentionally low-level: JSONL logs,
role inboxes, damage-signal files, and project charters. This module builds a
small read model over those primitives so humans and agents can ask one
question before doing work: what is blocked, waiting, or carrying learning?
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cognitive_firm.common.paths import REPO_ROOT
from cognitive_firm.orchestration.action_impact import (
    DEFAULT_ACTION_IMPACT_SUMMARY,
    summary_from_optional_path as action_impact_summary_from_path,
)
from cognitive_firm.orchestration.action_attestation import (
    DEFAULT_ACTION_ATTESTATION_LOG,
    AgentInvocationAudit,
    list_agent_invocation_audits,
)
from cognitive_firm.orchestration.agent_channels import list_blocked_obligations
from cognitive_firm.orchestration.accountability_cases import (
    DEFAULT_ACCOUNTABILITY_CASES_LOG,
    AccountabilityCase,
    list_accountability_cases,
)
from cognitive_firm.orchestration.evidence_gaps import (
    DEFAULT_EVIDENCE_GAPS_LOG,
    EvidenceGap,
    list_evidence_gaps,
)
from cognitive_firm.orchestration.forecast_market import (
    DEFAULT_FORECAST_MARKET_ROOT,
    market_summary_from_optional_path,
)
from cognitive_firm.orchestration.governance_changes import (
    DEFAULT_GOVERNANCE_CHANGES_LOG,
    GovernanceChangeProposal,
    list_governance_changes,
)
from cognitive_firm.orchestration.human_work import (
    DEFAULT_HUMAN_WORK_LOG,
    A2HWorkPressure,
    HumanWorkSession,
    list_human_work_sessions,
    list_a2h_waiting_on_human_sessions,
    list_agent_followup_human_work_sessions,
    list_missing_receipt_human_work_sessions,
    summarize_a2h_work_pressure,
)
from cognitive_firm.orchestration.intelligence_sources import build_intelligence_coverage
from cognitive_firm.orchestration.learning_events import (
    DEFAULT_LEARNING_ENCOUNTERS_LOG,
    DEFAULT_LEARNING_EVENTS_LOG,
    ApprovedLearningEvent,
    list_learning_events,
    summarize_learning_events,
)
from cognitive_firm.orchestration.outcome_links import DEFAULT_OUTCOME_LINKS_LOG
from cognitive_firm.orchestration.project_charter import (
    ProjectCharter,
    charter_summary,
    load_project_charter,
    validate_project_charter,
)
from cognitive_firm.orchestration.routine_reviews import DEFAULT_ROUTINE_REVIEWS_LOG
from cognitive_firm.orchestration.run_checkpoints import (
    ACTIVE_STATES as ACTIVE_RUN_STATES,
    TRANSITIONS_LOG,
    RunProjection,
    list_runs,
)
from cognitive_firm.orchestration.strategy_office import build_strategy_review
from cognitive_firm.signals import damage


ACTIVE_HUMAN_WORK_STATES = {
    "requested",
    "claimed",
    "in_progress",
    "blocked",
    "handed_off",
    "completed",
}
WAITING_HUMAN_WORK_STATES = {"requested", "blocked", "handed_off", "completed"}
OPEN_EVIDENCE_GAP_STATUSES = {"open", "collecting", "reviewed", "compiled"}


@dataclass(frozen=True)
class CharterIssue:
    path: str
    errors: list[str]
    summary: dict[str, Any]


@dataclass(frozen=True)
class OrgSurface:
    """A generic status view over kernel state.

    This is a projection, not the source of truth. Callers should mutate the
    underlying primitive modules and rebuild the surface.
    """

    blocking_evidence_gaps: list[EvidenceGap] = field(default_factory=list)
    open_evidence_gaps: list[EvidenceGap] = field(default_factory=list)
    active_human_work_sessions: list[HumanWorkSession] = field(default_factory=list)
    waiting_human_work_sessions: list[HumanWorkSession] = field(default_factory=list)
    a2h_waiting_on_human_sessions: list[HumanWorkSession] = field(default_factory=list)
    a2h_followup_sessions: list[HumanWorkSession] = field(default_factory=list)
    a2h_missing_receipt_sessions: list[HumanWorkSession] = field(default_factory=list)
    a2h_pressure: list[A2HWorkPressure] = field(default_factory=list)
    blocked_obligations: list[dict[str, Any]] = field(default_factory=list)
    recent_damage_signals: list[dict[str, Any]] = field(default_factory=list)
    invalid_project_charters: list[CharterIssue] = field(default_factory=list)
    forecast_state: dict[str, Any] = field(default_factory=dict)
    action_impact_state: dict[str, Any] = field(default_factory=dict)
    strategy_review_state: dict[str, Any] = field(default_factory=dict)
    intelligence_coverage_state: dict[str, Any] = field(default_factory=dict)
    pending_governance_changes: list[GovernanceChangeProposal] = field(default_factory=list)
    open_accountability_cases: list[AccountabilityCase] = field(default_factory=list)
    active_learning_events: list[ApprovedLearningEvent] = field(default_factory=list)
    learning_event_summary: dict[str, Any] = field(default_factory=dict)
    active_runs: list[RunProjection] = field(default_factory=list)
    failed_runs: list[RunProjection] = field(default_factory=list)
    recent_agent_invocations: list[AgentInvocationAudit] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "blocking_evidence_gaps": len(self.blocking_evidence_gaps),
            "open_evidence_gaps": len(self.open_evidence_gaps),
            "active_human_work_sessions": len(self.active_human_work_sessions),
            "waiting_human_work_sessions": len(self.waiting_human_work_sessions),
            "a2h_waiting_on_human_sessions": len(self.a2h_waiting_on_human_sessions),
            "a2h_followup_sessions": len(self.a2h_followup_sessions),
            "a2h_missing_receipt_sessions": len(self.a2h_missing_receipt_sessions),
            "a2h_pressure_groups": len(self.a2h_pressure),
            "blocked_obligations": len(self.blocked_obligations),
            "recent_damage_signals": len(self.recent_damage_signals),
            "invalid_project_charters": len(self.invalid_project_charters),
            "forecast_contracts": int(self.forecast_state.get("n_contracts") or 0),
            "forecast_score_debt": int(self.forecast_state.get("n_score_debt") or 0),
            "planned_action_impacts": int(self.action_impact_state.get("n_planned") or 0),
            "action_impacts_requiring_review": int(
                self.action_impact_state.get("n_review_required") or 0
            ),
            "local_negative_externalities": int(
                self.action_impact_state.get("n_local_with_negative_externalities") or 0
            ),
            "strategy_review_findings": int(self.strategy_review_state.get("n_findings") or 0),
            "strategy_review_blocking": int(self.strategy_review_state.get("n_blocking") or 0),
            "intelligence_source_improvements": int(
                self.intelligence_coverage_state.get("n_improvements") or 0
            ),
            "intelligence_source_warning_or_blocking": int(
                self.intelligence_coverage_state.get("n_warning_or_blocking_improvements") or 0
            ),
            "pending_governance_changes": len(self.pending_governance_changes),
            "open_accountability_cases": len(self.open_accountability_cases),
            "high_risk_accountability_cases": sum(
                1 for case in self.open_accountability_cases if case.risk_tier in {"high", "irreversible"}
            ),
            "governance_changes_review_ready": sum(
                1 for proposal in self.pending_governance_changes if proposal.status == "review_ready"
            ),
            "governance_changes_blocked": sum(
                1 for proposal in self.pending_governance_changes if proposal.status == "blocked"
            ),
            "active_learning_events": len(self.active_learning_events),
            "learning_events_compounded": int(self.learning_event_summary.get("compounded") or 0),
            "learning_events_with_encounters": int(
                self.learning_event_summary.get("events_with_encounters") or 0
            ),
            "learning_event_outcome_links": int(
                self.learning_event_summary.get("outcome_link_count") or 0
            ),
            "learning_event_overdue_reviews": int(
                self.learning_event_summary.get("overdue_routine_review_count") or 0
            ),
            "active_runs": len(self.active_runs),
            "failed_runs": len(self.failed_runs),
            "recent_agent_invocations": len(self.recent_agent_invocations),
            "failed_agent_invocations": sum(
                1 for row in self.recent_agent_invocations if row.verification_status == "failed"
            ),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts,
            "blocking_evidence_gaps": [asdict(g) for g in self.blocking_evidence_gaps],
            "open_evidence_gaps": [asdict(g) for g in self.open_evidence_gaps],
            "active_human_work_sessions": [asdict(s) for s in self.active_human_work_sessions],
            "waiting_human_work_sessions": [asdict(s) for s in self.waiting_human_work_sessions],
            "a2h_waiting_on_human_sessions": [
                asdict(s) for s in self.a2h_waiting_on_human_sessions
            ],
            "a2h_followup_sessions": [asdict(s) for s in self.a2h_followup_sessions],
            "a2h_missing_receipt_sessions": [
                asdict(s) for s in self.a2h_missing_receipt_sessions
            ],
            "a2h_pressure": [asdict(p) for p in self.a2h_pressure],
            "blocked_obligations": self.blocked_obligations,
            "recent_damage_signals": self.recent_damage_signals,
            "invalid_project_charters": [asdict(c) for c in self.invalid_project_charters],
            "forecast_state": self.forecast_state,
            "action_impact_state": self.action_impact_state,
            "strategy_review_state": self.strategy_review_state,
            "intelligence_coverage_state": self.intelligence_coverage_state,
            "pending_governance_changes": [
                proposal.as_dict() for proposal in self.pending_governance_changes
            ],
            "open_accountability_cases": [asdict(case) for case in self.open_accountability_cases],
            "active_learning_events": [event.as_dict() for event in self.active_learning_events],
            "learning_event_summary": self.learning_event_summary,
            "active_runs": [run.as_dict() for run in self.active_runs],
            "failed_runs": [run.as_dict() for run in self.failed_runs],
            "recent_agent_invocations": [
                row.as_dict() for row in self.recent_agent_invocations
            ],
        }


def discover_project_charters(project_root: Path = REPO_ROOT) -> list[Path]:
    """Find likely project-charter files without imposing tenant layout."""
    candidates: dict[str, Path] = {}
    for base in (
        project_root / "org",
        project_root / "projects",
        project_root / "tenants",
    ):
        if not base.exists():
            continue
        for path in base.rglob("project_charter.md"):
            candidates[str(path.resolve()).lower()] = path
        for path in base.rglob("PROJECT_CHARTER.md"):
            candidates[str(path.resolve()).lower()] = path
    return sorted(candidates.values())


def _invalid_charter_issue(charter: ProjectCharter) -> CharterIssue | None:
    errors = validate_project_charter(charter)
    if not errors:
        return None
    return CharterIssue(
        path=str(charter.path) if charter.path else "",
        errors=errors,
        summary=charter_summary(charter),
    )


def _recent_damage(limit: int) -> list[dict[str, Any]]:
    return [asdict(signal) for signal in damage.list_recent(limit=limit)]


def build_org_surface(
    *,
    project_root: Path = REPO_ROOT,
    evidence_gaps_log: Path = DEFAULT_EVIDENCE_GAPS_LOG,
    human_work_log: Path = DEFAULT_HUMAN_WORK_LOG,
    forecast_market_summary: Path = DEFAULT_FORECAST_MARKET_ROOT / "global_health.json",
    action_impact_summary: Path = DEFAULT_ACTION_IMPACT_SUMMARY,
    governance_changes_log: Path = DEFAULT_GOVERNANCE_CHANGES_LOG,
    accountability_cases_log: Path = DEFAULT_ACCOUNTABILITY_CASES_LOG,
    learning_events_log: Path = DEFAULT_LEARNING_EVENTS_LOG,
    learning_encounters_log: Path = DEFAULT_LEARNING_ENCOUNTERS_LOG,
    outcome_links_log: Path = DEFAULT_OUTCOME_LINKS_LOG,
    routine_reviews_log: Path = DEFAULT_ROUTINE_REVIEWS_LOG,
    transitions_log: Path = TRANSITIONS_LOG,
    action_attestation_log: Path = DEFAULT_ACTION_ATTESTATION_LOG,
    damage_limit: int = 20,
    agent_invocation_limit: int = 10,
) -> OrgSurface:
    """Build the generic organization status projection."""
    all_open_gaps = [
        gap
        for gap in list_evidence_gaps(log_path=evidence_gaps_log)
        if gap.status in OPEN_EVIDENCE_GAP_STATUSES
    ]
    blocking_gaps = [gap for gap in all_open_gaps if gap.severity == "blocking"]

    all_human_work = list_human_work_sessions(log_path=human_work_log)
    active_human_work = [
        session for session in all_human_work if session.state in ACTIVE_HUMAN_WORK_STATES
    ]
    waiting_human_work = [
        session for session in active_human_work if session.state in WAITING_HUMAN_WORK_STATES
    ]
    a2h_followup = list_agent_followup_human_work_sessions(log_path=human_work_log)
    a2h_waiting_on_human = list_a2h_waiting_on_human_sessions(log_path=human_work_log)
    a2h_missing_receipts = list_missing_receipt_human_work_sessions(log_path=human_work_log)
    a2h_pressure = summarize_a2h_work_pressure(
        sessions=all_human_work,
        stale_after_hours=24,
        concentration_threshold=3,
    )

    charter_issues: list[CharterIssue] = []
    for path in discover_project_charters(project_root):
        try:
            issue = _invalid_charter_issue(load_project_charter(path))
        except Exception as exc:  # noqa: BLE001
            issue = CharterIssue(path=str(path), errors=[f"failed to parse: {exc}"], summary={})
        if issue is not None:
            charter_issues.append(issue)

    forecast_state = market_summary_from_optional_path(forecast_market_summary)
    action_state = action_impact_summary_from_path(action_impact_summary)
    governance_changes = [
        *list_governance_changes(status="blocked", log_path=governance_changes_log),
        *list_governance_changes(status="review_ready", log_path=governance_changes_log),
    ]
    open_accountability_cases = [
        *list_accountability_cases(status="open", log_path=accountability_cases_log),
        *list_accountability_cases(status="under_review", log_path=accountability_cases_log),
        *list_accountability_cases(status="remediated", log_path=accountability_cases_log),
        *list_accountability_cases(status="escalated", log_path=accountability_cases_log),
    ]
    active_learning_events = list_learning_events(status="active", log_path=learning_events_log)
    learning_summary = summarize_learning_events(
        log_path=learning_events_log,
        encounters_log_path=learning_encounters_log,
        outcome_links_log_path=outcome_links_log,
        routine_reviews_log_path=routine_reviews_log,
    )
    runs = list_runs(log_path=transitions_log)
    recent_agent_invocations = list_agent_invocation_audits(
        limit=agent_invocation_limit,
        log_path=action_attestation_log,
    )
    recent_damage = _recent_damage(damage_limit)
    strategy_review = build_strategy_review(
        forecast_summary=forecast_state,
        action_impact_summary=action_state,
        charter_issues=[asdict(issue) for issue in charter_issues],
        evidence_gaps=[asdict(gap) for gap in all_open_gaps],
        human_work_sessions=[asdict(session) for session in active_human_work],
        recent_damage_signals=recent_damage,
        failed_runs=[run.as_dict() for run in runs if run.state == "failed"],
    )
    base_counts = {
        "blocking_evidence_gaps": len(blocking_gaps),
        "open_evidence_gaps": len(all_open_gaps),
        "active_human_work_sessions": len(active_human_work),
        "waiting_human_work_sessions": len(waiting_human_work),
        "a2h_waiting_on_human_sessions": len(a2h_waiting_on_human),
        "a2h_followup_sessions": len(a2h_followup),
        "a2h_missing_receipt_sessions": len(a2h_missing_receipts),
        "blocked_obligations": len(list_blocked_obligations()),
        "recent_damage_signals": len(recent_damage),
        "invalid_project_charters": len(charter_issues),
        "open_accountability_cases": len(open_accountability_cases),
        "active_learning_events": len(active_learning_events),
        "learning_events_with_encounters": learning_summary.events_with_encounters,
        "learning_event_overdue_reviews": learning_summary.overdue_routine_review_count,
        "active_runs": sum(1 for run in runs if run.state in ACTIVE_RUN_STATES),
        "failed_runs": sum(1 for run in runs if run.state == "failed"),
        "recent_agent_invocations": len(recent_agent_invocations),
        "failed_agent_invocations": sum(
            1 for row in recent_agent_invocations if row.verification_status == "failed"
        ),
    }
    intelligence_coverage = build_intelligence_coverage(
        forecast_state=forecast_state.as_dict(),
        action_impact_state=action_state.as_dict(),
        strategy_review_state=strategy_review.as_dict(),
        surface_counts=base_counts,
    )

    return OrgSurface(
        blocking_evidence_gaps=blocking_gaps,
        open_evidence_gaps=all_open_gaps,
        active_human_work_sessions=active_human_work,
        waiting_human_work_sessions=waiting_human_work,
        a2h_waiting_on_human_sessions=a2h_waiting_on_human,
        a2h_followup_sessions=a2h_followup,
        a2h_missing_receipt_sessions=a2h_missing_receipts,
        a2h_pressure=a2h_pressure,
        blocked_obligations=[asdict(msg) for msg in list_blocked_obligations()],
        recent_damage_signals=recent_damage,
        invalid_project_charters=charter_issues,
        forecast_state=forecast_state.as_dict(),
        action_impact_state=action_state.as_dict(),
        strategy_review_state=strategy_review.as_dict(),
        intelligence_coverage_state=intelligence_coverage.as_dict(),
        pending_governance_changes=governance_changes,
        open_accountability_cases=open_accountability_cases,
        active_learning_events=active_learning_events,
        learning_event_summary=learning_summary.as_dict(),
        active_runs=[run for run in runs if run.state in ACTIVE_RUN_STATES],
        failed_runs=[run for run in runs if run.state == "failed"],
        recent_agent_invocations=recent_agent_invocations,
    )


def format_surface_brief(surface: OrgSurface) -> str:
    """Render a compact human-readable brief for pre-work checks."""
    lines = ["# Organization Surface", ""]
    for key, value in surface.counts.items():
        lines.append(f"- {key}: {value}")

    if surface.blocking_evidence_gaps:
        lines.extend(["", "## Blocking Evidence Gaps"])
        for gap in surface.blocking_evidence_gaps[:10]:
            lines.append(f"- {gap.gap_id}: {gap.target} ({gap.status})")

    if surface.waiting_human_work_sessions:
        lines.extend(["", "## Human Work Waiting"])
        for session in surface.waiting_human_work_sessions[:10]:
            receipt = " receipt-required" if session.receipt_required else ""
            lines.append(f"- {session.session_id}: {session.objective} [{session.state}]{receipt}")

    if surface.a2h_followup_sessions:
        lines.extend(["", "## A2H Follow-Up"])
        for session in surface.a2h_followup_sessions[:10]:
            deliverable = f" -> {session.human_deliverable}" if session.human_deliverable else ""
            role = session.agent_counterparty_role or session.requested_by
            lines.append(f"- {session.session_id}: {role} must integrate{deliverable}")

    if surface.a2h_waiting_on_human_sessions:
        lines.extend(["", "## A2H Waiting On Human"])
        for session in surface.a2h_waiting_on_human_sessions[:10]:
            deliverable = f" -> {session.human_deliverable}" if session.human_deliverable else ""
            role = session.agent_counterparty_role or session.requested_by
            lines.append(f"- {session.session_id}: {role} waits for {session.human_actor}{deliverable}")

    if surface.a2h_missing_receipt_sessions:
        lines.extend(["", "## A2H Missing Receipts"])
        for session in surface.a2h_missing_receipt_sessions[:10]:
            lines.append(
                f"- {session.session_id}: {session.receipt_type} receipt missing for {session.objective}"
            )

    if surface.a2h_pressure:
        lines.extend(["", "## A2H Pressure"])
        for group in surface.a2h_pressure[:10]:
            lines.append(
                "- "
                f"{group.agent_counterparty_role}/{group.bottleneck_class}: "
                f"{group.active_count} active, {group.missing_receipt_count} missing receipts; "
                f"{group.recommendation}"
            )

    if surface.blocked_obligations:
        lines.extend(["", "## Blocked Obligations"])
        for obligation in surface.blocked_obligations[:10]:
            lines.append(
                "- "
                f"{obligation.get('message_id')}: {obligation.get('subject')} "
                f"({obligation.get('from_role')} -> {obligation.get('to_role')})"
            )

    if surface.invalid_project_charters:
        lines.extend(["", "## Invalid Project Charters"])
        for issue in surface.invalid_project_charters[:10]:
            lines.append(f"- {issue.path}: {'; '.join(issue.errors)}")

    if surface.active_runs:
        lines.extend(["", "## Active Runs"])
        for run in surface.active_runs[:10]:
            lines.append(f"- {run.run_id}: {run.objective} ({run.owner_role})")

    if surface.failed_runs:
        lines.extend(["", "## Failed Runs"])
        for run in surface.failed_runs[:10]:
            reason = f": {run.failure_reason}" if run.failure_reason else ""
            lines.append(f"- {run.run_id}: {run.objective}{reason}")

    if surface.recent_agent_invocations:
        lines.extend(["", "## Recent Agent Invocations"])
        for row in surface.recent_agent_invocations[:10]:
            run_ref = f" {row.run_id}" if row.run_id else ""
            status = f"{row.verification_status}/{row.returncode}"
            session = f" session={row.agent_session_id}" if row.agent_session_id else ""
            lines.append(
                "- "
                f"{row.attestation_id}:{run_ref} {row.producer} via "
                f"{row.runtime or 'runtime'}:{row.adapter or 'adapter'} "
                f"({status}){session}"
            )

    action_impact = surface.action_impact_state
    if action_impact.get("n_local_with_negative_externalities"):
        lines.extend(["", "## Action-Impact Externalities"])
        for record in action_impact.get("local_with_negative_externalities", [])[:10]:
            lines.append(f"- {record.get('action_id')}: {record.get('action_ref')}")

    strategy_review = surface.strategy_review_state
    if strategy_review.get("n_findings"):
        lines.extend(["", "## Strategy Review Findings"])
        for finding in strategy_review.get("findings", [])[:10]:
            lines.append(
                "- "
                f"[{finding.get('severity')}] {finding.get('finding_id')}: "
                f"{finding.get('recommendation')}"
            )

    if surface.pending_governance_changes:
        lines.extend(["", "## Governance Changes"])
        for proposal in surface.pending_governance_changes[:10]:
            lines.append(
                "- "
                f"[{proposal.status}] {proposal.proposal_id}: "
                f"{proposal.change_kind} {proposal.target_ref}"
            )

    if surface.open_accountability_cases:
        lines.extend(["", "## Open Accountability Cases"])
        for case in surface.open_accountability_cases[:10]:
            lines.append(
                "- "
                f"[{case.risk_tier}/{case.status}] {case.case_id}: "
                f"{case.accountable_role} owns {case.trigger_ref}"
            )

    if surface.active_learning_events:
        lines.extend(["", "## Approved Learning Events"])
        for event in surface.active_learning_events[:10]:
            lines.append(
                "- "
                f"{event.learning_event_id}: {event.learning_unit_kind} "
                f"({event.future_application_cue})"
            )
            if event.source_carrier_refs:
                lines.append(
                    "  refs: " + ", ".join(event.source_carrier_refs[:3])
                )
            tags = _learning_event_tags(event.metadata)
            if tags:
                lines.append("  tags: " + ", ".join(tags[:5]))

    learning_summary = surface.learning_event_summary
    if learning_summary.get("total"):
        coverage = float(learning_summary.get("outcome_verdict_coverage") or 0.0)
        lines.extend(["", "## Learning Unit Health"])
        lines.append(
            "- "
            f"{learning_summary.get('active', 0)} active; "
            f"{learning_summary.get('compounded', 0)} compounded; "
            f"{learning_summary.get('events_with_encounters', 0)} encountered; "
            f"{learning_summary.get('outcome_link_count', 0)} outcome links; "
            f"{coverage:.0%} verdict coverage"
        )
        if learning_summary.get("overdue_learning_event_ids"):
            lines.append(
                "- overdue review: "
                + ", ".join(str(item) for item in learning_summary["overdue_learning_event_ids"][:10])
            )
        if learning_summary.get("recommendation"):
            lines.append(f"- next: {learning_summary['recommendation']}")

    intelligence_coverage = surface.intelligence_coverage_state
    if intelligence_coverage.get("n_improvements"):
        lines.extend(["", "## Intelligence Source Improvements"])
        for item in intelligence_coverage.get("improvement_backlog", [])[:10]:
            lines.append(
                "- "
                f"[{item.get('severity')}] {item.get('improvement_id')}: "
                f"{item.get('recommended_action')}"
            )

    return "\n".join(lines) + "\n"


def _learning_event_tags(metadata: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("tag", "tags", "labels", "capability_tags"):
        value = metadata.get(key)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item and str(item) not in out:
                out.append(str(item))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the cognitive-firm organization surface.")
    parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--evidence-gaps-log", type=Path, default=DEFAULT_EVIDENCE_GAPS_LOG)
    parser.add_argument("--human-work-log", type=Path, default=DEFAULT_HUMAN_WORK_LOG)
    parser.add_argument(
        "--forecast-market-summary",
        type=Path,
        default=DEFAULT_FORECAST_MARKET_ROOT / "global_health.json",
    )
    parser.add_argument("--action-impact-summary", type=Path, default=DEFAULT_ACTION_IMPACT_SUMMARY)
    parser.add_argument("--governance-changes-log", type=Path, default=DEFAULT_GOVERNANCE_CHANGES_LOG)
    parser.add_argument(
        "--accountability-cases-log",
        type=Path,
        default=DEFAULT_ACCOUNTABILITY_CASES_LOG,
    )
    parser.add_argument("--learning-events-log", type=Path, default=DEFAULT_LEARNING_EVENTS_LOG)
    parser.add_argument("--learning-encounters-log", type=Path, default=DEFAULT_LEARNING_ENCOUNTERS_LOG)
    parser.add_argument("--outcome-links-log", type=Path, default=DEFAULT_OUTCOME_LINKS_LOG)
    parser.add_argument("--routine-reviews-log", type=Path, default=DEFAULT_ROUTINE_REVIEWS_LOG)
    parser.add_argument("--action-attestation-log", type=Path, default=DEFAULT_ACTION_ATTESTATION_LOG)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    surface = build_org_surface(
        project_root=args.project_root,
        evidence_gaps_log=args.evidence_gaps_log,
        human_work_log=args.human_work_log,
        forecast_market_summary=args.forecast_market_summary,
        action_impact_summary=args.action_impact_summary,
        governance_changes_log=args.governance_changes_log,
        accountability_cases_log=args.accountability_cases_log,
        learning_events_log=args.learning_events_log,
        learning_encounters_log=args.learning_encounters_log,
        outcome_links_log=args.outcome_links_log,
        routine_reviews_log=args.routine_reviews_log,
        action_attestation_log=args.action_attestation_log,
    )
    if args.json:
        print(json.dumps(surface.as_dict(), indent=2, sort_keys=True))
    else:
        print(format_surface_brief(surface), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
