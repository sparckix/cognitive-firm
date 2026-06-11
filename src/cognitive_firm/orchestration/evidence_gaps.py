"""Typed evidence-gap state for organizational learning.

Evidence gaps are durable work-state objects. They record that a role,
reviewer, evaluator, or operator found a missing source, comparator, external
fact, or adversarial check. This module does not fetch evidence; tenants may
bind their own sourcing workflow on top.
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


EvidenceGapSeverity = Literal["blocking", "useful", "archival"]
EvidenceGapStatus = Literal["open", "collecting", "reviewed", "compiled", "closed"]

DEFAULT_EVIDENCE_GAPS_LOG = ORG_ROOT_DIR / "evidence_gaps" / "evidence_gaps.jsonl"
VALID_SEVERITIES = {"blocking", "useful", "archival"}
VALID_STATUSES = {"open", "collecting", "reviewed", "compiled", "closed"}


@dataclass(frozen=True)
class EvidenceGap:
    gap_id: str
    created_at_utc: str
    updated_at_utc: str
    gap_type: str
    target: str
    description: str
    severity: EvidenceGapSeverity
    producer: str
    status: EvidenceGapStatus = "open"
    adversarial_direction: bool = False
    fetch_query: str | None = None
    owner_role: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    source_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _validate_severity(severity: str) -> EvidenceGapSeverity:
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"invalid severity {severity!r}; expected one of {sorted(VALID_SEVERITIES)}")
    return severity  # type: ignore[return-value]


def _validate_status(status: str) -> EvidenceGapStatus:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}; expected one of {sorted(VALID_STATUSES)}")
    return status  # type: ignore[return-value]


def create_evidence_gap(
    *,
    gap_type: str,
    target: str,
    description: str,
    severity: EvidenceGapSeverity | str,
    producer: str,
    adversarial_direction: bool = False,
    fetch_query: str | None = None,
    owner_role: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    source_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
    gap_id: str | None = None,
    log_path: Path | None = None,
) -> EvidenceGap:
    """Create and append an evidence gap to the JSONL state surface."""
    if not gap_type.strip():
        raise ValueError("gap_type is required")
    if not target.strip():
        raise ValueError("target is required")
    if not description.strip():
        raise ValueError("description is required")
    if not producer.strip():
        raise ValueError("producer is required")

    now = _now_iso()
    gap = EvidenceGap(
        gap_id=gap_id or f"gap_{uuid.uuid4().hex[:12]}",
        created_at_utc=now,
        updated_at_utc=now,
        gap_type=gap_type,
        target=target,
        description=description,
        severity=_validate_severity(str(severity)),
        producer=producer,
        adversarial_direction=adversarial_direction,
        fetch_query=fetch_query,
        owner_role=owner_role,
        tenant_id=tenant_id,
        project_id=project_id,
        source_ref=source_ref,
        metadata=metadata or {},
    )
    _append_jsonl(log_path or DEFAULT_EVIDENCE_GAPS_LOG, asdict(gap))
    return gap


def list_evidence_gaps(
    *,
    status: EvidenceGapStatus | str | None = None,
    severity: EvidenceGapSeverity | str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> list[EvidenceGap]:
    """Read current evidence gaps, optionally filtered."""
    if status is not None:
        status = _validate_status(str(status))
    if severity is not None:
        severity = _validate_severity(str(severity))

    gaps: list[EvidenceGap] = []
    for row in _read_jsonl(log_path or DEFAULT_EVIDENCE_GAPS_LOG):
        gap = EvidenceGap(**row)
        if status is not None and gap.status != status:
            continue
        if severity is not None and gap.severity != severity:
            continue
        if tenant_id is not None and gap.tenant_id != tenant_id:
            continue
        if project_id is not None and gap.project_id != project_id:
            continue
        gaps.append(gap)
    return gaps


def update_evidence_gap_status(
    gap_id: str,
    status: EvidenceGapStatus | str,
    *,
    log_path: Path | None = None,
) -> EvidenceGap:
    """Update one gap status by rewriting the JSONL projection.

    This is a small filesystem adapter, not the enterprise event outbox. The
    logical primitive is a durable typed evidence gap; tenants can replace this
    adapter with a database-backed implementation.
    """
    path = log_path or DEFAULT_EVIDENCE_GAPS_LOG
    rows = _read_jsonl(path)
    next_status = _validate_status(str(status))
    updated: EvidenceGap | None = None
    next_rows: list[dict[str, Any]] = []

    for row in rows:
        if row.get("gap_id") == gap_id:
            row = dict(row)
            row["status"] = next_status
            row["updated_at_utc"] = _now_iso()
            updated = EvidenceGap(**row)
        next_rows.append(row)

    if updated is None:
        raise KeyError(f"evidence gap not found: {gap_id}")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in next_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return updated


def evidence_gap_summary(gap: EvidenceGap) -> dict[str, Any]:
    return asdict(gap)


def evidence_gap_resource(gap: EvidenceGap) -> KernelResource:
    """Project an evidence gap into the common resource envelope.

    The evidence-gap JSONL row remains canonical. The resource view is for
    adapters, dashboards, migration checks, and conformance fixtures that need a
    stable object shape for missing-evidence work.
    """
    labels = {
        "gap_type": gap.gap_type,
        "severity": gap.severity,
        "status": gap.status,
        "producer": gap.producer,
        "adversarial_direction": str(gap.adversarial_direction).lower(),
    }
    if gap.owner_role:
        labels["owner_role"] = gap.owner_role

    links = [
        {"rel": "target", "href": gap.target},
        {"rel": "producer", "href": gap.producer},
    ]
    if gap.owner_role:
        links.append({"rel": "owner_role", "href": gap.owner_role})
    if gap.source_ref:
        links.append({"rel": "source", "href": gap.source_ref})
    if gap.fetch_query:
        links.append({"rel": "fetch_query", "href": gap.fetch_query})

    return make_resource(
        kind="EvidenceGap",
        name=gap.gap_id,
        resource_id=gap.gap_id,
        tenant_id=gap.tenant_id,
        project_id=gap.project_id,
        stability="alpha",
        labels=labels,
        annotations={
            key: str(value)
            for key, value in gap.metadata.items()
            if isinstance(key, str) and value is not None
        },
        spec={
            "gap_type": gap.gap_type,
            "target": gap.target,
            "description": gap.description,
            "severity": gap.severity,
            "producer": gap.producer,
            "adversarial_direction": gap.adversarial_direction,
            "fetch_query": gap.fetch_query,
            "owner_role": gap.owner_role,
            "source_ref": gap.source_ref,
        },
        status={
            "status": gap.status,
            "created_at_utc": gap.created_at_utc,
            "updated_at_utc": gap.updated_at_utc,
        },
        links=links,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage cognitive-firm evidence gaps.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--status")
    list_parser.add_argument("--severity")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--log-path", type=Path)
    list_parser.add_argument("--resource", action="store_true", help="render resource envelopes")

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--gap-type", required=True)
    create_parser.add_argument("--target", required=True)
    create_parser.add_argument("--description", required=True)
    create_parser.add_argument("--severity", default="useful")
    create_parser.add_argument("--producer", required=True)
    create_parser.add_argument("--fetch-query")
    create_parser.add_argument("--owner-role")
    create_parser.add_argument("--tenant-id")
    create_parser.add_argument("--project-id")
    create_parser.add_argument("--source-ref")
    create_parser.add_argument("--adversarial-direction", action="store_true")
    create_parser.add_argument("--log-path", type=Path)

    update_parser = sub.add_parser("update-status")
    update_parser.add_argument("gap_id")
    update_parser.add_argument("status")
    update_parser.add_argument("--log-path", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "list":
        gaps = list_evidence_gaps(
            status=args.status,
            severity=args.severity,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
        )
        for gap in gaps:
            payload = (
                evidence_gap_resource(gap).as_dict()
                if args.resource
                else evidence_gap_summary(gap)
            )
            print(json.dumps(payload, sort_keys=True))
        return 0
    if args.cmd == "create":
        gap = create_evidence_gap(
            gap_type=args.gap_type,
            target=args.target,
            description=args.description,
            severity=args.severity,
            producer=args.producer,
            adversarial_direction=args.adversarial_direction,
            fetch_query=args.fetch_query,
            owner_role=args.owner_role,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            source_ref=args.source_ref,
            log_path=args.log_path,
        )
        print(json.dumps(evidence_gap_summary(gap), sort_keys=True))
        return 0
    if args.cmd == "update-status":
        gap = update_evidence_gap_status(args.gap_id, args.status, log_path=args.log_path)
        print(json.dumps(evidence_gap_summary(gap), sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
