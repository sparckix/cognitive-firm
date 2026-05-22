"""Outcome links: tying an approved change to a measured outcome.

The kernel records that learning happened (``learning_events.py``) and that an
approved learning event was *encountered* by future work
(``learning_event_encounters`` telemetry). It does not record whether the change
actually moved a measured outcome. That makes the kernel's own central validity
claim — that governing a pipeline produces *measurable improvement* — untestable
from kernel records.

An :class:`OutcomeLink` is that missing record. It binds a *change* — a learning
event, a governance change, or an accountability case (a generic ``change_ref``
plus an optional typed ``learning_event_id``) — to a *measured outcome* on one
tenant-defined metric. Lifecycle:

    open ── record baseline ──▶ measuring ── record verdict ──▶ verdict_recorded
      │                            │
      └────────── void ────────────┴──────────▶ voided

It carries a baseline metric snapshot taken before the change, one or more
post-change snapshots, a tenant-defined ``metric_name`` and ``metric_unit``, and
a tenant ``verdict`` in {improved, no_change, regressed, inconclusive} with who
recorded it and a rationale.

This is the Holmström informativeness principle applied to organizational
learning: a control system should condition on the most informative available
signal. Recording only "was the lesson encountered" discards the outcome signal;
the outcome link records what is informative about whether the change worked.

CRITICAL BOUNDARY: the kernel does **not** compute the metric or decide the
verdict. The tenant owns the metric definition, supplies the snapshot values,
and supplies the verdict. The kernel owns the typed record, the lifecycle, and a
read-model summary over outcome links. Every transition emits a canonical
:class:`KernelEvent`.

T1 stores outcome links in a JSONL log. A T2 deployment puts the same rows
behind the transactional state backend; the function contract is identical.
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.kernel_events import record_kernel_event


OutcomeLinkStatus = Literal["open", "measuring", "verdict_recorded", "voided"]
OutcomeVerdict = Literal["improved", "no_change", "regressed", "inconclusive"]
SnapshotKind = Literal["baseline", "post"]

VALID_OUTCOME_LINK_STATUSES = {"open", "measuring", "verdict_recorded", "voided"}
VALID_OUTCOME_VERDICTS = {"improved", "no_change", "regressed", "inconclusive"}
VALID_SNAPSHOT_KINDS = {"baseline", "post"}
# Terminal states never transition again.
TERMINAL_STATES = {"verdict_recorded", "voided"}

DEFAULT_OUTCOME_LINKS_LOG = ORG_ROOT_DIR / "outcome_links" / "outcome_links.jsonl"


@dataclass(frozen=True)
class MetricSnapshot:
    """One tenant-supplied measurement of the outcome metric.

    The kernel stores the value verbatim; it does not compute or interpret it.
    ``kind`` is ``baseline`` (taken before the change) or ``post`` (taken after).
    """

    snapshot_id: str
    kind: SnapshotKind
    value: float
    captured_at_utc: str
    recorded_at_utc: str
    captured_by: str
    sample_size: int | None = None
    measurement_ref: str | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OutcomeLink:
    """A durable link from an approved change to a measured outcome.

    Canonical state. The :class:`OutcomeLinkSummary` read model is derived from
    these rows and can always be rebuilt.
    """

    outcome_link_id: str
    change_ref: str
    change_kind: str
    metric_name: str
    metric_unit: str
    created_at_utc: str
    updated_at_utc: str
    created_by: str
    status: OutcomeLinkStatus = "open"
    learning_event_id: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    owner_role: str | None = None
    direction: str | None = None
    baseline: dict[str, Any] | None = None
    post_snapshots: list[dict[str, Any]] = field(default_factory=list)
    verdict: OutcomeVerdict | None = None
    verdict_recorded_by: str | None = None
    verdict_rationale: str | None = None
    verdict_recorded_at_utc: str | None = None
    void_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES


@dataclass(frozen=True)
class OutcomeLinkSummary:
    """Read model: how many governed changes actually moved their metric.

    This is the answer the kernel could not give before: of N approved changes
    with outcome links, how many improved, how many regressed, how many are
    still being measured. It owns no facts and can be rebuilt from outcome-link
    rows at any time.
    """

    total: int
    open: int
    measuring: int
    verdict_recorded: int
    voided: int
    improved: int
    no_change: int
    regressed: int
    inconclusive: int
    awaiting_verdict: int
    verdict_coverage: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# time + io helpers (kept module-local, matching the kernel's primitive style)
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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


def _validate(value: str, allowed: set[str], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"invalid {label} {value!r}; expected one of {sorted(allowed)}")
    return value


def _coerce_value(value: Any) -> float:
    """The tenant supplies the metric value; the kernel only stores a number."""
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError("metric snapshot value must be a number") from None


def _emit(
    link: OutcomeLink,
    *,
    verb: str,
    actor: str,
    extra: dict[str, Any] | None = None,
    kernel_events_log: Path | None = None,
) -> None:
    """Record an outcome-link transition on the canonical kernel-event stream."""
    payload: dict[str, Any] = {
        "outcome_link_id": link.outcome_link_id,
        "change_ref": link.change_ref,
        "change_kind": link.change_kind,
        "metric_name": link.metric_name,
        "metric_unit": link.metric_unit,
        "status": link.status,
    }
    for key in ("learning_event_id", "verdict", "verdict_recorded_by", "void_reason"):
        value = getattr(link, key)
        if value is not None:
            payload[key] = value
    if link.baseline is not None:
        payload["has_baseline"] = True
    payload["post_snapshot_count"] = len(link.post_snapshots)
    if extra:
        payload.update(extra)
    record_kernel_event(
        actor=actor,
        verb=verb,
        object_ref=f"outcome_link:{link.outcome_link_id}",
        subject_ref=link.change_ref,
        tenant_id=link.tenant_id,
        project_id=link.project_id,
        idempotency_key=f"{verb}:{link.outcome_link_id}:{link.updated_at_utc}",
        payload=payload,
        log_path=kernel_events_log,
    )


def _mutate(
    path: Path,
    outcome_link_id: str,
    mutate: Callable[[dict[str, Any]], dict[str, Any]],
) -> OutcomeLink:
    """Apply ``mutate`` to one outcome-link row, rewriting the T1 projection."""
    rows = _read_jsonl(path)
    updated: OutcomeLink | None = None
    next_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("outcome_link_id") == outcome_link_id:
            row = mutate(dict(row))
            updated = OutcomeLink(**row)
        next_rows.append(row)
    if updated is None:
        raise KeyError(f"outcome link not found: {outcome_link_id}")
    _write_jsonl(path, next_rows)
    return updated


# ---------------------------------------------------------------------------
# write operations
# ---------------------------------------------------------------------------


def create_outcome_link(
    *,
    change_ref: str,
    change_kind: str,
    metric_name: str,
    metric_unit: str,
    created_by: str,
    learning_event_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    owner_role: str | None = None,
    direction: str | None = None,
    metadata: dict[str, Any] | None = None,
    outcome_link_id: str | None = None,
    actor: str = "service.kernel",
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> OutcomeLink:
    """Open an outcome link tying a change to a tenant-defined metric.

    ``change_kind`` is a free tenant label (e.g. ``learning_event``,
    ``governance_change``, ``accountability_case``). ``learning_event_id`` is the
    optional typed reference for the learning-event case. The kernel does not
    interpret ``metric_name``/``metric_unit``/``direction``; the tenant owns the
    metric definition. The link opens in ``open`` and carries no measurement
    until a baseline snapshot is recorded.
    """
    if not change_ref.strip():
        raise ValueError("change_ref is required")
    if not change_kind.strip():
        raise ValueError("change_kind is required")
    if not metric_name.strip():
        raise ValueError("metric_name is required")
    if not metric_unit.strip():
        raise ValueError("metric_unit is required")
    if not created_by.strip():
        raise ValueError("created_by is required")
    now = _now_iso()
    link = OutcomeLink(
        outcome_link_id=outcome_link_id or f"olink_{uuid.uuid4().hex[:12]}",
        change_ref=change_ref.strip(),
        change_kind=change_kind.strip(),
        metric_name=metric_name.strip(),
        metric_unit=metric_unit.strip(),
        created_at_utc=now,
        updated_at_utc=now,
        created_by=created_by.strip(),
        status="open",
        learning_event_id=learning_event_id,
        tenant_id=tenant_id,
        project_id=project_id,
        owner_role=owner_role,
        direction=direction,
        metadata=dict(metadata or {}),
    )
    _append_jsonl(log_path or DEFAULT_OUTCOME_LINKS_LOG, link.as_dict())
    _emit(link, verb="outcome_link.created", actor=actor, kernel_events_log=kernel_events_log)
    return link


def record_metric_snapshot(
    outcome_link_id: str,
    *,
    kind: SnapshotKind | str,
    value: float,
    captured_by: str,
    captured_at_utc: str | None = None,
    sample_size: int | None = None,
    measurement_ref: str | None = None,
    note: str | None = None,
    actor: str = "service.kernel",
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> OutcomeLink:
    """Record a tenant-supplied metric measurement on an outcome link.

    A ``baseline`` snapshot must precede any ``post`` snapshot — the kernel
    records the change's effect, which is undefined without a before value.
    Recording the baseline moves the link from ``open`` to ``measuring``. A
    ``post`` snapshot is only accepted while the link is ``measuring``. A second
    baseline is rejected: a link has exactly one before value.
    """
    snapshot_kind = _validate(str(kind), VALID_SNAPSHOT_KINDS, "snapshot kind")
    if not captured_by.strip():
        raise ValueError("captured_by is required")
    numeric = _coerce_value(value)
    path = log_path or DEFAULT_OUTCOME_LINKS_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        status = row.get("status")
        if status in TERMINAL_STATES:
            raise ValueError(f"outcome link is {status}; cannot record snapshots")
        now = _now_iso()
        snapshot = MetricSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:12]}",
            kind=snapshot_kind,  # type: ignore[arg-type]
            value=numeric,
            captured_at_utc=captured_at_utc or now,
            recorded_at_utc=now,
            captured_by=captured_by.strip(),
            sample_size=sample_size,
            measurement_ref=measurement_ref,
            note=note,
        )
        if snapshot_kind == "baseline":
            if row.get("baseline") is not None:
                raise ValueError("outcome link already has a baseline snapshot")
            row["baseline"] = snapshot.as_dict()
            row["status"] = "measuring"
        else:
            if row.get("baseline") is None:
                raise ValueError("record a baseline snapshot before any post snapshot")
            posts = list(row.get("post_snapshots") or [])
            posts.append(snapshot.as_dict())
            row["post_snapshots"] = posts
            if status == "open":
                row["status"] = "measuring"
        row["updated_at_utc"] = now
        return row

    link = _mutate(path, outcome_link_id, mutate)
    _emit(
        link,
        verb="outcome_link.snapshot_recorded",
        actor=actor,
        extra={"snapshot_kind": snapshot_kind, "value": numeric},
        kernel_events_log=kernel_events_log,
    )
    return link


def record_verdict(
    outcome_link_id: str,
    *,
    verdict: OutcomeVerdict | str,
    recorded_by: str,
    rationale: str,
    actor: str = "service.kernel",
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> OutcomeLink:
    """Record the tenant's verdict on whether the change worked.

    The kernel does **not** decide the verdict; the tenant compares the
    baseline and post snapshots under its own metric definition and supplies one
    of {improved, no_change, regressed, inconclusive} with a rationale. A verdict
    is only accepted on a ``measuring`` link that already has both a baseline and
    at least one post snapshot; recording it terminates the link in
    ``verdict_recorded``.
    """
    normalized = _validate(str(verdict), VALID_OUTCOME_VERDICTS, "verdict")
    if not recorded_by.strip():
        raise ValueError("recorded_by is required")
    if not rationale.strip():
        raise ValueError("rationale is required")
    path = log_path or DEFAULT_OUTCOME_LINKS_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        status = row.get("status")
        if status in TERMINAL_STATES:
            raise ValueError(f"outcome link is {status}; verdict cannot be recorded")
        if status != "measuring":
            raise ValueError(
                f"outcome link is {status}; a verdict requires a measuring link "
                "with a baseline and at least one post snapshot"
            )
        if row.get("baseline") is None:
            raise ValueError("cannot record a verdict without a baseline snapshot")
        if not (row.get("post_snapshots") or []):
            raise ValueError("cannot record a verdict without a post-change snapshot")
        now = _now_iso()
        row["status"] = "verdict_recorded"
        row["verdict"] = normalized
        row["verdict_recorded_by"] = recorded_by.strip()
        row["verdict_rationale"] = rationale.strip()
        row["verdict_recorded_at_utc"] = now
        row["updated_at_utc"] = now
        return row

    link = _mutate(path, outcome_link_id, mutate)
    _emit(link, verb="outcome_link.verdict_recorded", actor=actor, kernel_events_log=kernel_events_log)
    return link


def void_outcome_link(
    outcome_link_id: str,
    *,
    reason: str,
    actor: str = "service.kernel",
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> OutcomeLink:
    """Void an outcome link that can no longer yield an informative verdict.

    This is the escape hatch for links whose change was reverted, whose metric
    became unmeasurable, or that were opened in error. A voided link is terminal
    and is excluded from verdict coverage in the summary read model.
    """
    if not reason.strip():
        raise ValueError("reason is required")
    path = log_path or DEFAULT_OUTCOME_LINKS_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        status = row.get("status")
        if status in TERMINAL_STATES:
            raise ValueError(f"outcome link is {status}; cannot void")
        now = _now_iso()
        row["status"] = "voided"
        row["void_reason"] = reason.strip()
        row["updated_at_utc"] = now
        return row

    link = _mutate(path, outcome_link_id, mutate)
    _emit(link, verb="outcome_link.voided", actor=actor, kernel_events_log=kernel_events_log)
    return link


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------


def list_outcome_links(
    *,
    status: OutcomeLinkStatus | str | None = None,
    verdict: OutcomeVerdict | str | None = None,
    learning_event_id: str | None = None,
    change_ref: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> list[OutcomeLink]:
    """Read outcome links, optionally filtered."""
    if status is not None:
        status = _validate(str(status), VALID_OUTCOME_LINK_STATUSES, "status")
    if verdict is not None:
        verdict = _validate(str(verdict), VALID_OUTCOME_VERDICTS, "verdict")
    out: list[OutcomeLink] = []
    for row in _read_jsonl(log_path or DEFAULT_OUTCOME_LINKS_LOG):
        link = OutcomeLink(**row)
        if status is not None and link.status != status:
            continue
        if verdict is not None and link.verdict != verdict:
            continue
        if learning_event_id is not None and link.learning_event_id != learning_event_id:
            continue
        if change_ref is not None and link.change_ref != change_ref:
            continue
        if tenant_id is not None and link.tenant_id != tenant_id:
            continue
        if project_id is not None and link.project_id != project_id:
            continue
        out.append(link)
    return out


def get_outcome_link(
    outcome_link_id: str,
    *,
    log_path: Path | None = None,
) -> OutcomeLink | None:
    """Return one outcome link by id, or ``None``."""
    for link in list_outcome_links(log_path=log_path):
        if link.outcome_link_id == outcome_link_id:
            return link
    return None


def summarize_outcome_links(
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    links: list[OutcomeLink] | None = None,
    log_path: Path | None = None,
) -> OutcomeLinkSummary:
    """Summarize outcome links into the kernel's measurable-improvement read model.

    Answers: of N governed changes with outcome links, how many improved, how
    many regressed, how many are still being measured. ``verdict_coverage`` is
    the share of non-voided links that have reached a verdict — the kernel's own
    measure of whether its learning loop is being closed.
    """
    if links is None:
        links = list_outcome_links(
            tenant_id=tenant_id, project_id=project_id, log_path=log_path
        )
    counts = {
        "open": 0,
        "measuring": 0,
        "verdict_recorded": 0,
        "voided": 0,
    }
    verdicts = {
        "improved": 0,
        "no_change": 0,
        "regressed": 0,
        "inconclusive": 0,
    }
    for link in links:
        counts[link.status] = counts.get(link.status, 0) + 1
        if link.verdict is not None:
            verdicts[link.verdict] = verdicts.get(link.verdict, 0) + 1
    total = len(links)
    awaiting_verdict = counts["open"] + counts["measuring"]
    non_voided = total - counts["voided"]
    coverage = (counts["verdict_recorded"] / non_voided) if non_voided else 0.0
    return OutcomeLinkSummary(
        total=total,
        open=counts["open"],
        measuring=counts["measuring"],
        verdict_recorded=counts["verdict_recorded"],
        voided=counts["voided"],
        improved=verdicts["improved"],
        no_change=verdicts["no_change"],
        regressed=verdicts["regressed"],
        inconclusive=verdicts["inconclusive"],
        awaiting_verdict=awaiting_verdict,
        verdict_coverage=round(coverage, 4),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage cognitive-firm outcome links (outcome-linked learning)."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create")
    create.add_argument("--change-ref", required=True)
    create.add_argument("--change-kind", required=True)
    create.add_argument("--metric-name", required=True)
    create.add_argument("--metric-unit", required=True)
    create.add_argument("--created-by", required=True)
    create.add_argument("--learning-event-id")
    create.add_argument("--tenant-id")
    create.add_argument("--project-id")
    create.add_argument("--owner-role")
    create.add_argument("--direction")
    create.add_argument("--actor", default="service.kernel")
    create.add_argument("--log-path", type=Path)

    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("outcome_link_id")
    snapshot.add_argument("--kind", required=True)
    snapshot.add_argument("--value", type=float, required=True)
    snapshot.add_argument("--captured-by", required=True)
    snapshot.add_argument("--sample-size", type=int)
    snapshot.add_argument("--measurement-ref")
    snapshot.add_argument("--note")
    snapshot.add_argument("--actor", default="service.kernel")
    snapshot.add_argument("--log-path", type=Path)

    verdict = sub.add_parser("verdict")
    verdict.add_argument("outcome_link_id")
    verdict.add_argument("--verdict", required=True)
    verdict.add_argument("--recorded-by", required=True)
    verdict.add_argument("--rationale", required=True)
    verdict.add_argument("--actor", default="service.kernel")
    verdict.add_argument("--log-path", type=Path)

    void = sub.add_parser("void")
    void.add_argument("outcome_link_id")
    void.add_argument("--reason", required=True)
    void.add_argument("--actor", default="service.kernel")
    void.add_argument("--log-path", type=Path)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--status")
    list_parser.add_argument("--verdict")
    list_parser.add_argument("--learning-event-id")
    list_parser.add_argument("--change-ref")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--log-path", type=Path)

    summarize = sub.add_parser("summarize")
    summarize.add_argument("--tenant-id")
    summarize.add_argument("--project-id")
    summarize.add_argument("--log-path", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "create":
        link = create_outcome_link(
            change_ref=args.change_ref,
            change_kind=args.change_kind,
            metric_name=args.metric_name,
            metric_unit=args.metric_unit,
            created_by=args.created_by,
            learning_event_id=args.learning_event_id,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            owner_role=args.owner_role,
            direction=args.direction,
            actor=args.actor,
            log_path=args.log_path,
        )
        print(json.dumps(link.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "snapshot":
        link = record_metric_snapshot(
            args.outcome_link_id,
            kind=args.kind,
            value=args.value,
            captured_by=args.captured_by,
            sample_size=args.sample_size,
            measurement_ref=args.measurement_ref,
            note=args.note,
            actor=args.actor,
            log_path=args.log_path,
        )
        print(json.dumps(link.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "verdict":
        link = record_verdict(
            args.outcome_link_id,
            verdict=args.verdict,
            recorded_by=args.recorded_by,
            rationale=args.rationale,
            actor=args.actor,
            log_path=args.log_path,
        )
        print(json.dumps(link.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "void":
        link = void_outcome_link(
            args.outcome_link_id,
            reason=args.reason,
            actor=args.actor,
            log_path=args.log_path,
        )
        print(json.dumps(link.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "list":
        for link in list_outcome_links(
            status=args.status,
            verdict=args.verdict,
            learning_event_id=args.learning_event_id,
            change_ref=args.change_ref,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
        ):
            print(json.dumps(link.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "summarize":
        summary = summarize_outcome_links(
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
        )
        print(json.dumps(summary.as_dict(), sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
