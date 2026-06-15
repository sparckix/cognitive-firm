"""Protocol experiment records for coordination-pattern comparisons.

The kernel records experiment evidence for protocols such as coordinator,
sequential, batched sequential, shared, and broadcast. It does not choose a
live coordination policy or execute agents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.learning_transition_compiler import (
    LearningTransitionCandidate,
)
from cognitive_firm.orchestration.resource_envelope import KernelResource, make_resource


ProtocolKind = Literal["coordinator", "sequential", "batched_sequential", "shared", "broadcast", "custom"]
ExperimentStatus = Literal["active", "reported", "blocked"]
ReportStatus = Literal["blocked", "advisory", "review_ready"]

VALID_PROTOCOLS = {"coordinator", "sequential", "batched_sequential", "shared", "broadcast", "custom"}

DEFAULT_PROTOCOL_EXPERIMENTS_LOG = ORG_ROOT_DIR / "protocol_experiments" / "protocol_experiments.jsonl"


@dataclass(frozen=True)
class ProtocolExperimentObservation:
    observation_id: str
    experiment_id: str
    observed_at_utc: str
    protocol: ProtocolKind | str
    task_ref: str
    quality_score: float
    latency_units: float = 0.0
    cost_units: float = 0.0
    abstentions: int = 0
    failures: int = 0
    guardrail_violations: int = 0
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProtocolExperimentReport:
    report_id: str
    experiment_id: str
    created_at_utc: str
    status: ReportStatus | str
    baseline_protocol: str
    recommended_protocol: str | None
    objective_metric: str
    n_observations: int
    protocol_summaries: dict[str, dict[str, Any]]
    review_blockers: list[str] = field(default_factory=list)
    governance_change_candidate: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    observer_only: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProtocolExperiment:
    experiment_id: str
    created_at_utc: str
    updated_at_utc: str
    objective: str
    owner_role: str
    candidate_protocols: list[str]
    baseline_protocol: str
    objective_metric: str = "quality_score"
    status: ExperimentStatus | str = "active"
    tenant_id: str | None = None
    project_id: str | None = None
    observations: list[dict[str, Any]] = field(default_factory=list)
    reports: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def start_protocol_experiment(
    *,
    objective: str,
    owner_role: str,
    candidate_protocols: list[str],
    baseline_protocol: str,
    objective_metric: str = "quality_score",
    tenant_id: str | None = None,
    project_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    experiment_id: str | None = None,
    log_path: Path | None = None,
) -> ProtocolExperiment:
    if not objective.strip():
        raise ValueError("objective is required")
    if not owner_role.strip():
        raise ValueError("owner_role is required")
    if not objective_metric.strip():
        raise ValueError("objective_metric is required")
    protocols = [_validate_protocol(item) for item in candidate_protocols]
    if not protocols:
        raise ValueError("candidate_protocols are required")
    baseline = _validate_protocol(baseline_protocol)
    if baseline not in protocols:
        raise ValueError("baseline_protocol must be in candidate_protocols")
    now = _now_iso()
    experiment = ProtocolExperiment(
        experiment_id=experiment_id or f"pexp_{uuid.uuid4().hex[:12]}",
        created_at_utc=now,
        updated_at_utc=now,
        objective=objective,
        owner_role=owner_role,
        candidate_protocols=protocols,
        baseline_protocol=baseline,
        objective_metric=objective_metric,
        tenant_id=tenant_id,
        project_id=project_id,
        metadata=metadata or {},
    )
    _append_event(log_path or DEFAULT_PROTOCOL_EXPERIMENTS_LOG, "protocol_experiment.started", experiment.as_dict())
    return experiment


def record_protocol_observation(
    *,
    experiment_id: str,
    protocol: ProtocolKind | str,
    task_ref: str,
    quality_score: float,
    latency_units: float = 0.0,
    cost_units: float = 0.0,
    abstentions: int = 0,
    failures: int = 0,
    guardrail_violations: int = 0,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    observation_id: str | None = None,
    log_path: Path | None = None,
) -> ProtocolExperiment:
    path = log_path or DEFAULT_PROTOCOL_EXPERIMENTS_LOG
    experiment = get_protocol_experiment(experiment_id, log_path=path)
    if experiment.status != "active":
        raise ValueError(f"cannot record observation for {experiment.status} experiment {experiment_id}")
    protocol = _validate_protocol(protocol)
    if protocol not in experiment.candidate_protocols:
        raise ValueError("protocol must be in candidate_protocols")
    if not task_ref.strip():
        raise ValueError("task_ref is required")
    if not 0 <= quality_score <= 1:
        raise ValueError("quality_score must be in [0, 1]")
    for label, value in {
        "latency_units": latency_units,
        "cost_units": cost_units,
        "abstentions": abstentions,
        "failures": failures,
        "guardrail_violations": guardrail_violations,
    }.items():
        if value < 0:
            raise ValueError(f"{label} cannot be negative")
    observation = ProtocolExperimentObservation(
        observation_id=observation_id or f"pobs_{uuid.uuid4().hex[:12]}",
        experiment_id=experiment_id,
        observed_at_utc=_now_iso(),
        protocol=protocol,
        task_ref=task_ref,
        quality_score=float(quality_score),
        latency_units=float(latency_units),
        cost_units=float(cost_units),
        abstentions=int(abstentions),
        failures=int(failures),
        guardrail_violations=int(guardrail_violations),
        evidence_refs=evidence_refs or [],
        metadata=metadata or {},
    )
    _append_event(path, "protocol_experiment.observation_recorded", observation.as_dict())
    return get_protocol_experiment(experiment_id, log_path=path)


def build_protocol_experiment_report(
    *,
    experiment_id: str,
    proposed_by: str,
    target_ref: str,
    min_observations_per_protocol: int = 2,
    min_quality_delta: float = 0.05,
    max_guardrail_violations: int = 0,
    log_path: Path | None = None,
) -> ProtocolExperiment:
    path = log_path or DEFAULT_PROTOCOL_EXPERIMENTS_LOG
    experiment = get_protocol_experiment(experiment_id, log_path=path)
    if not proposed_by.strip():
        raise ValueError("proposed_by is required")
    if not target_ref.strip():
        raise ValueError("target_ref is required")
    if min_observations_per_protocol < 1:
        raise ValueError("min_observations_per_protocol must be at least 1")
    if min_quality_delta < 0:
        raise ValueError("min_quality_delta cannot be negative")
    if max_guardrail_violations < 0:
        raise ValueError("max_guardrail_violations cannot be negative")
    summaries = _protocol_summaries(experiment.observations)
    blockers: list[str] = []
    for protocol in experiment.candidate_protocols:
        if summaries.get(protocol, {}).get("n", 0) < min_observations_per_protocol:
            blockers.append(f"{protocol} has fewer than {min_observations_per_protocol} observations")
    baseline = summaries.get(experiment.baseline_protocol)
    if not baseline:
        blockers.append("baseline protocol has no observations")
    if any(item.get("guardrail_violations", 0) > max_guardrail_violations for item in summaries.values()):
        blockers.append("guardrail violations exceed threshold")

    recommended: str | None = None
    if not blockers:
        recommended = max(
            summaries,
            key=lambda protocol: _protocol_score(summaries[protocol]),
        )
        delta = summaries[recommended]["mean_quality_score"] - baseline["mean_quality_score"]
        if recommended == experiment.baseline_protocol or delta < min_quality_delta:
            blockers.append(f"best protocol did not beat baseline by {min_quality_delta:.3f}")
            recommended = None

    status: ReportStatus = "review_ready" if recommended and not blockers else "blocked"
    governance_candidate = {}
    if recommended:
        governance_candidate = {
            "change_kind": "route_policy_change",
            "title": f"Promote {recommended} protocol for {experiment.objective}",
            "proposed_by": proposed_by,
            "target_ref": target_ref,
            "rationale": (
                f"Protocol experiment {experiment.experiment_id} found {recommended} "
                f"outperformed {experiment.baseline_protocol} on {experiment.objective_metric}."
            ),
            "source_refs": [f"protocol_experiment:{experiment.experiment_id}"],
            "expected_behavior_change": f"Use {recommended} protocol for matching coordination work.",
            "risk_summary": "Protocol-specific gains may not generalize outside the measured task set.",
            "rollback_plan": f"Revert to {experiment.baseline_protocol} protocol.",
        }
    report = ProtocolExperimentReport(
        report_id=f"preport_{uuid.uuid4().hex[:12]}",
        experiment_id=experiment_id,
        created_at_utc=_now_iso(),
        status=status,
        baseline_protocol=experiment.baseline_protocol,
        recommended_protocol=recommended,
        objective_metric=experiment.objective_metric,
        n_observations=len(experiment.observations),
        protocol_summaries=summaries,
        review_blockers=blockers,
        governance_change_candidate=governance_candidate,
        evidence_refs=[f"protocol_experiment:{experiment.experiment_id}"],
        metadata={
            "min_observations_per_protocol": min_observations_per_protocol,
            "min_quality_delta": min_quality_delta,
            "max_guardrail_violations": max_guardrail_violations,
        },
    )
    _append_event(path, "protocol_experiment.report_recorded", report.as_dict())
    return get_protocol_experiment(experiment_id, log_path=path)


def list_protocol_experiments(*, log_path: Path | None = None) -> list[ProtocolExperiment]:
    return list(_project(_read_events(log_path or DEFAULT_PROTOCOL_EXPERIMENTS_LOG)).values())


def get_protocol_experiment(experiment_id: str, *, log_path: Path | None = None) -> ProtocolExperiment:
    experiments = _project(_read_events(log_path or DEFAULT_PROTOCOL_EXPERIMENTS_LOG))
    if experiment_id not in experiments:
        raise KeyError(f"protocol experiment not found: {experiment_id}")
    return experiments[experiment_id]


def protocol_experiment_resource(experiment: ProtocolExperiment) -> KernelResource:
    return make_resource(
        kind="ProtocolExperiment",
        name=experiment.experiment_id,
        resource_id=experiment.experiment_id,
        tenant_id=experiment.tenant_id,
        project_id=experiment.project_id,
        spec={
            "objective": experiment.objective,
            "owner_role": experiment.owner_role,
            "candidate_protocols": experiment.candidate_protocols,
            "baseline_protocol": experiment.baseline_protocol,
            "objective_metric": experiment.objective_metric,
            "metadata": experiment.metadata,
        },
        status={
            "status": experiment.status,
            "observations": experiment.observations,
            "reports": experiment.reports,
        },
    )


def learning_candidate_from_protocol_experiment_report(
    experiment: ProtocolExperiment,
    report: ProtocolExperimentReport | dict[str, Any],
) -> LearningTransitionCandidate:
    """Project a review-ready protocol report into a learning candidate."""
    report_payload = report.as_dict() if hasattr(report, "as_dict") else dict(report)
    if report_payload.get("status") != "review_ready":
        raise ValueError("protocol experiment report is not review_ready")
    governance_candidate = dict(report_payload.get("governance_change_candidate") or {})
    target_ref = governance_candidate.get("target_ref") or experiment.experiment_id
    report_id = report_payload.get("report_id")
    source_refs = _unique_strings(
        [
            f"protocol_experiment:{experiment.experiment_id}",
            f"protocol_experiment_report:{report_id}" if report_id else None,
            *(report_payload.get("evidence_refs") or []),
            *(governance_candidate.get("source_refs") or []),
        ]
    )
    digest_payload = {
        "experiment_id": experiment.experiment_id,
        "report_id": report_id,
        "recommended_protocol": report_payload.get("recommended_protocol"),
        "target_ref": target_ref,
        "source_refs": source_refs,
    }
    digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return LearningTransitionCandidate(
        candidate_id=f"ltc_{digest}",
        transition_kind="route_policy_change",
        severity="warning",
        rationale=str(
            governance_candidate.get("rationale")
            or f"Protocol experiment {experiment.experiment_id} produced a review-ready report."
        ),
        source_kind="protocol_experiment_report",
        object_ref=str(target_ref),
        suggested_owner_role=experiment.owner_role,
        review_question="Should this protocol experiment change route policy for matching work?",
        source_refs=source_refs,
        proposed_payload={
            "experiment_id": experiment.experiment_id,
            "report_id": report_payload.get("report_id"),
            "recommended_protocol": report_payload.get("recommended_protocol"),
            "baseline_protocol": report_payload.get("baseline_protocol"),
            "objective_metric": report_payload.get("objective_metric"),
            "n_observations": report_payload.get("n_observations"),
            "protocol_summaries": report_payload.get("protocol_summaries") or {},
            "governance_change_candidate": governance_candidate,
            "metadata": report_payload.get("metadata") or {},
        },
        observer_only=True,
    )


def _protocol_summaries(observations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        grouped.setdefault(str(observation.get("protocol")), []).append(observation)
    summaries: dict[str, dict[str, Any]] = {}
    for protocol, rows in grouped.items():
        summaries[protocol] = {
            "n": len(rows),
            "mean_quality_score": mean(float(row.get("quality_score") or 0) for row in rows),
            "mean_latency_units": mean(float(row.get("latency_units") or 0) for row in rows),
            "mean_cost_units": mean(float(row.get("cost_units") or 0) for row in rows),
            "abstentions": sum(int(row.get("abstentions") or 0) for row in rows),
            "failures": sum(int(row.get("failures") or 0) for row in rows),
            "guardrail_violations": sum(int(row.get("guardrail_violations") or 0) for row in rows),
        }
    return summaries


def _protocol_score(summary: dict[str, Any]) -> float:
    return (
        float(summary.get("mean_quality_score") or 0)
        - 0.01 * float(summary.get("mean_latency_units") or 0)
        - 0.01 * float(summary.get("mean_cost_units") or 0)
        - 0.05 * float(summary.get("failures") or 0)
        - 0.05 * float(summary.get("guardrail_violations") or 0)
    )


def _unique_strings(values: list[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        if not text or text in out:
            continue
        out.append(text)
    return out


def _project(rows: list[dict[str, Any]]) -> dict[str, ProtocolExperiment]:
    experiments: dict[str, ProtocolExperiment] = {}
    for row in rows:
        event = row.get("event")
        payload = dict(row.get("payload") or {})
        experiment_id = str(payload.get("experiment_id") or "")
        if not experiment_id:
            continue
        if event == "protocol_experiment.started":
            experiments[experiment_id] = ProtocolExperiment(**payload)
            continue
        if experiment_id not in experiments:
            continue
        current = experiments[experiment_id]
        if event == "protocol_experiment.observation_recorded":
            observation = ProtocolExperimentObservation(**payload).as_dict()
            experiments[experiment_id] = ProtocolExperiment(
                **{
                    **current.as_dict(),
                    "updated_at_utc": row.get("ts") or _now_iso(),
                    "observations": current.observations + [observation],
                }
            )
        elif event == "protocol_experiment.report_recorded":
            report = ProtocolExperimentReport(**payload).as_dict()
            status = "reported" if report["status"] == "review_ready" else "blocked"
            experiments[experiment_id] = ProtocolExperiment(
                **{
                    **current.as_dict(),
                    "updated_at_utc": row.get("ts") or _now_iso(),
                    "status": status,
                    "reports": current.reports + [report],
                }
            )
    return experiments


def _append_event(path: Path, event: str, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "event_id": f"protoevt_{uuid.uuid4().hex[:12]}",
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


def _validate_protocol(value: str) -> str:
    text = str(value)
    if text not in VALID_PROTOCOLS:
        raise ValueError(f"protocol must be one of: {', '.join(sorted(VALID_PROTOCOLS))}")
    return text


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect protocol experiment records.")
    parser.add_argument("--log", type=Path, default=DEFAULT_PROTOCOL_EXPERIMENTS_LOG)
    parser.add_argument("--resource", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    args = parser.parse_args(argv)
    if args.cmd == "list":
        for experiment in list_protocol_experiments(log_path=args.log):
            payload = protocol_experiment_resource(experiment).as_dict() if args.resource else experiment.as_dict()
            print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
