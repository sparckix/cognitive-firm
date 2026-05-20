"""Accountability summary over organizational learning carriers.

This module joins the read side of several primitives into reviewable
accountability items. It does not assign blame and it does not mutate state; it
helps a role or human see who owns follow-up, which project is affected, and
which evidence or externality is still open.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cognitive_firm.common.paths import REPO_ROOT
from cognitive_firm.orchestration.action_impact import DEFAULT_ACTION_IMPACT_SUMMARY
from cognitive_firm.orchestration.evidence_gaps import DEFAULT_EVIDENCE_GAPS_LOG
from cognitive_firm.orchestration.forecast_market import DEFAULT_FORECAST_MARKET_ROOT
from cognitive_firm.orchestration.human_work import DEFAULT_HUMAN_WORK_LOG
from cognitive_firm.orchestration.org_surface import build_org_surface
from cognitive_firm.orchestration.run_checkpoints import TRANSITIONS_LOG


@dataclass(frozen=True)
class AccountabilityItem:
    item_id: str
    source_kind: str
    severity: str
    status: str
    owner_role: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    object_ref: str | None = None
    rationale: str = ""
    review_required: bool = False
    due_at_utc: str | None = None
    source_refs: list[str] = field(default_factory=list)
    externality_tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AccountabilitySummary:
    n_items: int
    n_review_required: int
    n_blocking: int
    n_by_source_kind: dict[str, int] = field(default_factory=dict)
    n_by_owner_role: dict[str, int] = field(default_factory=dict)
    n_by_project_id: dict[str, int] = field(default_factory=dict)
    items: list[AccountabilityItem] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_accountability_summary(surface: Any) -> AccountabilitySummary:
    """Build an accountability summary from an `OrgSurface` or dict payload."""
    payload = surface.as_dict() if hasattr(surface, "as_dict") else dict(surface)
    items: list[AccountabilityItem] = []
    items.extend(_evidence_items(payload.get("blocking_evidence_gaps") or []))
    items.extend(_human_work_items(payload.get("active_human_work_sessions") or []))
    items.extend(_action_impact_items(payload.get("action_impact_state") or {}))
    items.extend(_forecast_items(payload.get("forecast_state") or {}))
    items.extend(_strategy_items(payload.get("strategy_review_state") or {}))
    items.extend(_accountability_case_items(payload.get("open_accountability_cases") or []))
    items.extend(_damage_items(payload.get("recent_damage_signals") or []))
    items.extend(_run_items(payload.get("failed_runs") or []))

    deduped: dict[str, AccountabilityItem] = {}
    for item in items:
        deduped.setdefault(item.item_id, item)
    ordered = sorted(
        deduped.values(),
        key=lambda item: (_severity_rank(item.severity), item.source_kind, item.item_id),
    )
    return AccountabilitySummary(
        n_items=len(ordered),
        n_review_required=sum(1 for item in ordered if item.review_required),
        n_blocking=sum(1 for item in ordered if item.severity == "blocking"),
        n_by_source_kind=_count_by(ordered, "source_kind"),
        n_by_owner_role=_count_by(ordered, "owner_role"),
        n_by_project_id=_count_by(ordered, "project_id"),
        items=ordered,
    )


def _evidence_items(rows: list[dict[str, Any]]) -> list[AccountabilityItem]:
    out: list[AccountabilityItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            _item(
                source_kind="evidence_gap",
                severity=str(row.get("severity") or "warning"),
                status=str(row.get("status") or "open"),
                owner_role=row.get("owner_role") or row.get("producer"),
                tenant_id=row.get("tenant_id"),
                project_id=row.get("project_id"),
                object_ref=row.get("gap_id") or row.get("target"),
                rationale=str(row.get("description") or "Evidence gap requires follow-up."),
                review_required=row.get("severity") == "blocking",
                source_refs=_string_list(row.get("source_ref")),
                metadata={"gap_type": row.get("gap_type"), "target": row.get("target")},
            )
        )
    return out


def _human_work_items(rows: list[dict[str, Any]]) -> list[AccountabilityItem]:
    out: list[AccountabilityItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        receipt_missing = bool(row.get("receipt_required")) and not row.get("receipt")
        followup = bool(row.get("agent_followup_required")) and row.get("state") in {
            "handed_off",
            "completed",
        }
        if not (receipt_missing or followup or row.get("state") in {"requested", "blocked", "handed_off"}):
            continue
        out.append(
            _item(
                source_kind="human_work",
                severity="warning" if receipt_missing or followup else "info",
                status=str(row.get("state") or "unknown"),
                owner_role=row.get("agent_counterparty_role") or row.get("requested_by"),
                tenant_id=row.get("tenant_id"),
                project_id=row.get("project_id"),
                object_ref=row.get("session_id"),
                rationale=str(row.get("objective") or "Human work session requires follow-up."),
                review_required=receipt_missing or followup,
                due_at_utc=row.get("deadline_utc"),
                source_refs=_string_list(row.get("artifact_refs") or []),
                metadata={
                    "human_actor": row.get("human_actor"),
                    "work_mode": row.get("work_mode"),
                    "bottleneck_class": row.get("bottleneck_class"),
                    "receipt_required": row.get("receipt_required"),
                    "agent_followup_required": row.get("agent_followup_required"),
                },
            )
        )
    return out


def _accountability_case_items(rows: list[dict[str, Any]]) -> list[AccountabilityItem]:
    out: list[AccountabilityItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        risk_tier = str(row.get("risk_tier") or "medium")
        out.append(
            _item(
                source_kind="accountability_case",
                severity="blocking" if risk_tier == "irreversible" else "warning",
                status=str(row.get("status") or "open"),
                owner_role=row.get("accountable_role"),
                tenant_id=row.get("tenant_id"),
                project_id=row.get("project_id"),
                object_ref=row.get("case_id") or row.get("trigger_ref"),
                rationale=str(row.get("rationale") or "Accountability case requires closure."),
                review_required=True,
                due_at_utc=row.get("due_at_utc"),
                source_refs=_string_list(
                    [row.get("trigger_ref"), row.get("authority_envelope_ref")]
                    + list(row.get("closure_evidence_refs") or [])
                ),
                externality_tags=_string_list(row.get("externality_tags") or []),
                metadata={
                    "trigger_ref": row.get("trigger_ref"),
                    "risk_tier": risk_tier,
                    "responsible_actor": row.get("responsible_actor"),
                    "decision_right_basis": row.get("decision_right_basis"),
                    "recourse_path": row.get("recourse_path"),
                    "operator_burden": row.get("operator_burden"),
                },
            )
        )
    return out


def _action_impact_items(state: dict[str, Any]) -> list[AccountabilityItem]:
    out: list[AccountabilityItem] = []
    for row in state.get("review_required", []):
        if not isinstance(row, dict):
            continue
        out.append(
            _item(
                source_kind="action_impact_review",
                severity="warning",
                status=str(row.get("status") or "planned"),
                owner_role=row.get("evaluator_role") or row.get("actor_role") or row.get("actor"),
                tenant_id=row.get("tenant_id"),
                project_id=row.get("project_id"),
                object_ref=row.get("action_ref") or row.get("action_id"),
                rationale=str(row.get("impact_summary") or row.get("notes") or "Action requires human review."),
                review_required=True,
                source_refs=_string_list(row.get("artifact_refs") or row.get("measurement_ref")),
                metadata={"action_id": row.get("action_id"), "objective_metric": row.get("objective_metric")},
            )
        )
    for row in state.get("local_with_negative_externalities", []):
        if not isinstance(row, dict):
            continue
        tags = _string_list(row.get("negative_externality_tags") or [])
        out.append(
            _item(
                source_kind="negative_externality",
                severity="warning",
                status=str(row.get("status") or "measured"),
                owner_role=row.get("evaluator_role") or row.get("actor_role") or row.get("actor"),
                tenant_id=row.get("tenant_id"),
                project_id=row.get("project_id"),
                object_ref=row.get("action_ref") or row.get("action_id"),
                rationale="Local action-impact row carries negative externalities.",
                review_required=True,
                source_refs=_string_list(row.get("artifact_refs") or row.get("measurement_ref")),
                externality_tags=tags,
                metadata={
                    "action_id": row.get("action_id"),
                    "externalities": row.get("externalities") or {},
                },
            )
        )
    return out


def _forecast_items(state: dict[str, Any]) -> list[AccountabilityItem]:
    out: list[AccountabilityItem] = []
    for row in state.get("contracts", []):
        if not isinstance(row, dict):
            continue
        decision_use = row.get("decision_use")
        rec = row.get("allocation_recommendation")
        if isinstance(decision_use, dict) and decision_use:
            out.append(
                _item(
                    source_kind="forecast_decision_use",
                    severity="info",
                    status=str(row.get("lifecycle_state") or "unknown"),
                    owner_role=decision_use.get("owner_role") or decision_use.get("actor_role"),
                    object_ref=row.get("contract_id"),
                    rationale=str(decision_use.get("summary") or "Forecast has recorded decision-use."),
                    source_refs=_string_list(row.get("artifact_paths") or row.get("contract_id")),
                    metadata={"decision_use": decision_use},
                )
            )
        if isinstance(rec, dict):
            out.append(
                _item(
                    source_kind="forecast_allocation",
                    severity="warning" if rec.get("action") in {"kill_branch", "request_evidence"} else "info",
                    status=str(row.get("lifecycle_state") or "unknown"),
                    owner_role="role.manager",
                    object_ref=row.get("contract_id"),
                    rationale=str(rec.get("reason") or "Forecast recommends a routing action."),
                    review_required=rec.get("action") in {"kill_branch", "request_evidence", "request_human_work"},
                    source_refs=_string_list(row.get("contract_id")),
                    metadata={"allocation_recommendation": rec},
                )
            )
    return out


def _strategy_items(state: dict[str, Any]) -> list[AccountabilityItem]:
    out: list[AccountabilityItem] = []
    for row in state.get("findings", []):
        if not isinstance(row, dict):
            continue
        out.append(
            _item(
                source_kind="strategy_finding",
                severity=str(row.get("severity") or "info"),
                status="open",
                owner_role=row.get("suggested_owner_role"),
                object_ref=row.get("object_ref") or row.get("finding_id"),
                rationale=str(row.get("rationale") or row.get("review_question") or ""),
                review_required=row.get("severity") in {"blocking", "warning"},
                source_refs=_string_list(row.get("source_refs") or []),
                metadata={
                    "finding_id": row.get("finding_id"),
                    "candidate_transition_kind": row.get("candidate_transition_kind"),
                    "recommendation": row.get("recommendation"),
                },
            )
        )
    return out


def _damage_items(rows: list[dict[str, Any]]) -> list[AccountabilityItem]:
    out: list[AccountabilityItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            _item(
                source_kind="damage_signal",
                severity=str(row.get("severity") or "warning"),
                status=str(row.get("status") or "open"),
                owner_role=row.get("owner_role") or "role.manager",
                object_ref=row.get("signal_id") or row.get("kind"),
                rationale=str(row.get("summary") or row.get("message") or "Damage signal requires review."),
                review_required=True,
                source_refs=_string_list(row.get("artifact_refs") or []),
                metadata=row,
            )
        )
    return out


def _run_items(rows: list[dict[str, Any]]) -> list[AccountabilityItem]:
    out: list[AccountabilityItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            _item(
                source_kind="failed_run",
                severity="warning",
                status="failed",
                owner_role=row.get("owner_role"),
                tenant_id=row.get("tenant_id"),
                project_id=row.get("project_id"),
                object_ref=row.get("run_id"),
                rationale=str(row.get("failure_reason") or "Run failed and needs triage."),
                review_required=True,
                source_refs=_string_list(row.get("run_id")),
                metadata={"objective": row.get("objective"), "idempotency_key": row.get("idempotency_key")},
            )
        )
    return out


def _item(
    *,
    source_kind: str,
    severity: str,
    status: str,
    owner_role: Any = None,
    tenant_id: Any = None,
    project_id: Any = None,
    object_ref: Any = None,
    rationale: str = "",
    review_required: bool = False,
    due_at_utc: Any = None,
    source_refs: list[str] | None = None,
    externality_tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AccountabilityItem:
    payload = {
        "source_kind": source_kind,
        "object_ref": object_ref,
        "owner_role": owner_role,
        "project_id": project_id,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return AccountabilityItem(
        item_id=f"acct_{digest}",
        source_kind=source_kind,
        severity=severity,
        status=status,
        owner_role=str(owner_role) if owner_role else None,
        tenant_id=str(tenant_id) if tenant_id else None,
        project_id=str(project_id) if project_id else None,
        object_ref=str(object_ref) if object_ref else None,
        rationale=rationale,
        review_required=bool(review_required),
        due_at_utc=str(due_at_utc) if due_at_utc else None,
        source_refs=source_refs or [],
        externality_tags=externality_tags or [],
        metadata=metadata or {},
    )


def _count_by(items: list[AccountabilityItem], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = getattr(item, field_name)
        if value is None:
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _string_list(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return [str(value) for value in payload.values() if value]
    if isinstance(payload, list):
        return [str(item) for item in payload if item]
    if payload:
        return [str(payload)]
    return []


def _severity_rank(severity: str) -> int:
    return {"blocking": 0, "critical": 0, "warning": 1, "info": 2}.get(severity, 3)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build accountability summary over org state.")
    parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--evidence-gaps-log", type=Path, default=DEFAULT_EVIDENCE_GAPS_LOG)
    parser.add_argument("--human-work-log", type=Path, default=DEFAULT_HUMAN_WORK_LOG)
    parser.add_argument(
        "--forecast-market-summary",
        type=Path,
        default=DEFAULT_FORECAST_MARKET_ROOT / "global_health.json",
    )
    parser.add_argument("--action-impact-summary", type=Path, default=DEFAULT_ACTION_IMPACT_SUMMARY)
    parser.add_argument("--transitions-log", type=Path, default=TRANSITIONS_LOG)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    summary = build_accountability_summary(
        build_org_surface(
            project_root=args.project_root,
            evidence_gaps_log=args.evidence_gaps_log,
            human_work_log=args.human_work_log,
            forecast_market_summary=args.forecast_market_summary,
            action_impact_summary=args.action_impact_summary,
            transitions_log=args.transitions_log,
        )
    )
    if args.json:
        print(json.dumps(summary.as_dict(), indent=2, sort_keys=True))
    else:
        for item in summary.items:
            print(f"- [{item.severity}] {item.source_kind} {item.object_ref}: {item.rationale}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
