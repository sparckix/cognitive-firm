"""Durable work items: the production queue under the governance layer.

The kernel already records *decisions* (gates), *human work* (A2H sessions),
*obligations* (A2A), and *residual risk* (accountability cases). It did not
have a generic record for the recurring unit of *production work* that a
company actually runs: a claimable, retryable, bounded-exit task that flows
through an :class:`~cognitive_firm.orchestration.operating_units.OperatingUnit`.

A ``WorkItem`` is that record. It is deliberately not a graph node and not a
runtime step. External runtimes still own execution; the kernel owns the
organizational facts:

- who is authorized to claim the work (typed authority);
- that exactly one worker holds it at a time (lease + fencing token);
- how many attempts it has survived, and when it becomes a dead letter;
- that finished work terminates in a *bounded exit* the tenant defined
  (the production-layer analogue of accountable closure).

Every transition emits a canonical :class:`KernelEvent`, so the work queue is
auditable through the same envelope as the rest of the kernel. The kernel does
not interpret the ``payload`` or the meaning of an exit; the tenant does.

T1 uses the JSONL log with an exclusive file lock around every mutation, which
is enough for one host. A T2 deployment puts the same rows behind the
transactional state backend so claim and fencing are checked in the mutation
transaction; the contract in this module is identical either way.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.extension_schemas import validate_payload
from cognitive_firm.orchestration.kernel_events import record_kernel_event
from cognitive_firm.orchestration.operating_units import OperatingUnit, get_operating_unit


WorkItemStatus = Literal[
    "queued",
    "claimed",
    "running",
    "done",
    "failed",
    "retired",
    "dead_letter",
]
VALID_WORK_ITEM_STATUSES = {
    "queued",
    "claimed",
    "running",
    "done",
    "failed",
    "retired",
    "dead_letter",
}
# Terminal states never transition again on their own. ``dead_letter`` is
# terminal but reviewable: an operator may explicitly requeue it.
TERMINAL_STATES = {"done", "failed", "retired", "dead_letter"}
# A claimed or running item whose lease has expired is reclaimable.
CLAIMED_STATES = {"claimed", "running"}

DEFAULT_WORK_ITEMS_LOG = ORG_ROOT_DIR / "work_items" / "work_items.jsonl"
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_LEASE_SECONDS = 300


@dataclass(frozen=True)
class WorkItem:
    """One durable, claimable unit of production work.

    Canonical state. The operating-unit dashboard is a read model derived from
    these rows and can always be rebuilt.
    """

    work_id: str
    kind: str
    unit_id: str
    owner_role: str
    created_at_utc: str
    updated_at_utc: str
    status: WorkItemStatus = "queued"
    priority: int = 0
    attempts: int = 0
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    tenant_id: str | None = None
    project_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    claimed_by_actor: str | None = None
    claimed_by_role: str | None = None
    claim_token: int = 0
    lease_until_utc: str | None = None
    exit_kind: str | None = None
    result: str | None = None
    producer: str | None = None
    verifier: str | None = None
    artifact_refs: list[dict[str, Any]] = field(default_factory=list)
    failure_reason: str | None = None
    dead_letter_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    def is_claim_stale(self, *, now: datetime | None = None) -> bool:
        """Return whether a claimed item's lease has expired."""
        if self.status not in CLAIMED_STATES or not self.lease_until_utc:
            return False
        return _parse_iso(self.lease_until_utc) <= (now or _now())

    def is_claimable(self, *, now: datetime | None = None) -> bool:
        """Return whether this item can be claimed right now."""
        if self.status == "queued":
            return True
        return self.is_claim_stale(now=now)


# ---------------------------------------------------------------------------
# time + io helpers (kept module-local, matching the kernel's primitive style)
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    parsed = datetime.fromisoformat(value)
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


@contextlib.contextmanager
def _work_items_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive lock so two local writers cannot both claim a row."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _clean_artifact_refs(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("artifact_refs must be a list")
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            if not str(item.get("kind") or "").strip():
                raise ValueError("each artifact ref needs a non-empty 'kind'")
            out.append(dict(item))
        elif isinstance(item, str) and item.strip():
            out.append({"kind": "ref", "path": item.strip()})
        else:
            raise ValueError("artifact refs must be objects or non-empty strings")
    return out


def _emit(
    item: WorkItem,
    *,
    verb: str,
    actor: str,
    extra: dict[str, Any] | None = None,
    kernel_events_log: Path | None = None,
) -> None:
    """Record a work-item transition on the canonical kernel-event stream.

    The payload is the conventional *work event* shape: it links to the
    operating unit, the bounded exit, and producer/verifier provenance rather
    than duplicating an action attestation.
    """
    payload: dict[str, Any] = {
        "work_id": item.work_id,
        "unit_id": item.unit_id,
        "kind": item.kind,
        "status": item.status,
        "attempts": item.attempts,
        "priority": item.priority,
    }
    for key in ("exit_kind", "result", "producer", "verifier", "failure_reason", "dead_letter_reason"):
        value = getattr(item, key)
        if value is not None:
            payload[key] = value
    if item.artifact_refs:
        payload["artifact_refs"] = item.artifact_refs
    if extra:
        payload.update(extra)
    record_kernel_event(
        actor=actor,
        verb=verb,
        object_ref=f"work_item:{item.work_id}",
        subject_ref=f"operating_unit:{item.unit_id}",
        tenant_id=item.tenant_id,
        project_id=item.project_id,
        idempotency_key=f"{verb}:{item.work_id}:{item.claim_token}",
        payload=payload,
        log_path=kernel_events_log,
    )


def _resolve_unit(
    unit_id: str,
    *,
    operating_units_log: Path | None,
) -> OperatingUnit:
    unit = get_operating_unit(unit_id, log_path=operating_units_log)
    if unit is None:
        raise KeyError(f"operating unit not found: {unit_id}")
    return unit


def _mutate(
    path: Path,
    work_id: str,
    mutate: Callable[[dict[str, Any]], dict[str, Any]],
) -> WorkItem:
    """Apply ``mutate`` to one row inside the exclusive lock."""
    with _work_items_lock(path):
        rows = _read_jsonl(path)
        updated: WorkItem | None = None
        next_rows: list[dict[str, Any]] = []
        for row in rows:
            if row.get("work_id") == work_id:
                row = mutate(dict(row))
                updated = WorkItem(**row)
            next_rows.append(row)
        if updated is None:
            raise KeyError(f"work item not found: {work_id}")
        _write_jsonl(path, next_rows)
        return updated


def _require_live_claim(row: dict[str, Any], *, actor: str, claim_token: int) -> None:
    """Fail closed unless ``actor`` still holds a live claim with this token."""
    status = row.get("status")
    if status not in CLAIMED_STATES:
        raise ValueError(f"work item is {status}, not claimed")
    if row.get("claimed_by_actor") != actor:
        raise PermissionError("claim is held by a different actor")
    if int(row.get("claim_token") or 0) != int(claim_token):
        raise PermissionError("stale claim fencing token")
    if _parse_iso(row.get("lease_until_utc")) <= _now():
        raise PermissionError("claim lease has expired; re-claim the work item")


# ---------------------------------------------------------------------------
# queue operations
# ---------------------------------------------------------------------------


def enqueue_work_item(
    *,
    unit_id: str,
    kind: str,
    payload: dict[str, Any] | None = None,
    priority: int = 0,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    owner_role: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    idempotency_key: str | None = None,
    metadata: dict[str, Any] | None = None,
    actor: str = "service.kernel",
    work_id: str | None = None,
    log_path: Path | None = None,
    operating_units_log: Path | None = None,
    kernel_events_log: Path | None = None,
    extension_schemas_root: Path | None = None,
) -> WorkItem:
    """Enqueue a new work item against an operating unit.

    Enqueue is idempotent on ``idempotency_key``: a second enqueue with a key
    that already exists returns the existing item instead of creating a
    duplicate. The work ``kind`` must be one the unit accepts.

    If — and only if — an extension schema is registered for this ``kind``
    (under ``<extension_schemas_root>/extension_schemas/work_item/<kind>.schema.json``),
    the ``payload`` is validated against it (O3-P6). A ``kind`` with **no**
    registered schema stays open and unvalidated, exactly as before: a custom
    work type never needs a schema, but may ship one.
    """
    if not kind.strip():
        raise ValueError("kind is required")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    unit = _resolve_unit(unit_id, operating_units_log=operating_units_log)
    if unit.status != "active":
        raise ValueError(f"operating unit {unit_id} is {unit.status}, not active")
    if not unit.allows_work_kind(kind):
        raise ValueError(
            f"work kind {kind!r} is not in {unit_id}.allowed_work_kinds "
            f"{unit.allowed_work_kinds}"
        )
    # O3-P6: validate the payload against a registered per-kind extension
    # schema, if one exists. No schema registered == no constraint (open by
    # default) — this never breaks an existing unvalidated custom kind.
    schema_errors = validate_payload(
        "work_item", kind.strip(), payload or {}, schemas_root=extension_schemas_root
    )
    if schema_errors:
        raise ValueError(
            f"work item payload fails the extension schema registered for "
            f"kind {kind.strip()!r}: {'; '.join(schema_errors)}"
        )
    path = log_path or DEFAULT_WORK_ITEMS_LOG
    with _work_items_lock(path):
        rows = _read_jsonl(path)
        if idempotency_key:
            for row in rows:
                if row.get("idempotency_key") == idempotency_key:
                    return WorkItem(**row)
        now = _now_iso()
        item = WorkItem(
            work_id=work_id or f"work_{uuid.uuid4().hex[:16]}",
            kind=kind.strip(),
            unit_id=unit_id,
            owner_role=owner_role or unit.owner_role,
            created_at_utc=now,
            updated_at_utc=now,
            status="queued",
            priority=priority,
            max_attempts=max_attempts,
            tenant_id=tenant_id if tenant_id is not None else unit.tenant_id,
            project_id=project_id if project_id is not None else unit.project_id,
            payload=dict(payload or {}),
            idempotency_key=idempotency_key,
            metadata=dict(metadata or {}),
        )
        _write_jsonl(path, [*rows, item.as_dict()])
    _emit(item, verb="work_item.enqueued", actor=actor, kernel_events_log=kernel_events_log)
    return item


def _apply_claim(
    row: dict[str, Any],
    *,
    actor: str,
    role_id: str | None,
    lease_seconds: int,
) -> dict[str, Any]:
    row["status"] = "claimed"
    row["attempts"] = int(row.get("attempts") or 0) + 1
    row["claim_token"] = int(row.get("claim_token") or 0) + 1
    row["claimed_by_actor"] = actor
    row["claimed_by_role"] = role_id
    row["lease_until_utc"] = (_now() + timedelta(seconds=lease_seconds)).isoformat()
    row["updated_at_utc"] = _now_iso()
    return row


def claim_work_item(
    work_id: str,
    *,
    actor: str,
    role_id: str | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    log_path: Path | None = None,
    operating_units_log: Path | None = None,
    kernel_events_log: Path | None = None,
) -> WorkItem:
    """Claim one specific work item for a worker.

    A queued item, or a claimed item whose lease has expired, can be claimed.
    Each claim increments a monotonic ``claim_token`` so a worker whose lease
    expired cannot complete the item after another worker has reclaimed it.
    """
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    path = log_path or DEFAULT_WORK_ITEMS_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        item = WorkItem(**row)
        if not item.is_claimable():
            raise ValueError(
                f"work item {work_id} is {item.status} and not claimable"
            )
        unit = _resolve_unit(item.unit_id, operating_units_log=operating_units_log)
        if unit.status != "active":
            raise ValueError(f"operating unit {item.unit_id} is {unit.status}, not active")
        if not unit.allows_worker_role(role_id):
            raise PermissionError(
                f"role {role_id!r} is not an authorized worker for {item.unit_id} "
                f"(worker_roles={unit.worker_roles})"
            )
        if int(row.get("attempts") or 0) >= int(row.get("max_attempts") or DEFAULT_MAX_ATTEMPTS):
            raise ValueError(
                f"work item {work_id} has exhausted its attempts; it must be "
                "dead-lettered or requeued, not re-claimed"
            )
        return _apply_claim(row, actor=actor, role_id=role_id, lease_seconds=lease_seconds)

    item = _mutate(path, work_id, mutate)
    _emit(
        item,
        verb="work_item.claimed",
        actor=actor,
        extra={"lease_until_utc": item.lease_until_utc, "claim_token": item.claim_token},
        kernel_events_log=kernel_events_log,
    )
    return item


def claim_next_work_item(
    *,
    unit_id: str,
    actor: str,
    role_id: str | None = None,
    kind: str | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    log_path: Path | None = None,
    operating_units_log: Path | None = None,
    kernel_events_log: Path | None = None,
) -> WorkItem | None:
    """Claim the highest-priority claimable item in a unit, or return ``None``.

    Ordering is priority descending, then oldest first. This is the queue's
    main worker entry point; :func:`claim_work_item` targets a specific row.
    """
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    path = log_path or DEFAULT_WORK_ITEMS_LOG
    with _work_items_lock(path):
        rows = _read_jsonl(path)
        unit = _resolve_unit(unit_id, operating_units_log=operating_units_log)
        if unit.status != "active":
            raise ValueError(f"operating unit {unit_id} is {unit.status}, not active")
        if not unit.allows_worker_role(role_id):
            raise PermissionError(
                f"role {role_id!r} is not an authorized worker for {unit_id} "
                f"(worker_roles={unit.worker_roles})"
            )
        now = _now()
        candidates: list[tuple[int, str, int]] = []
        for index, row in enumerate(rows):
            item = WorkItem(**row)
            if item.unit_id != unit_id:
                continue
            if kind is not None and item.kind != kind:
                continue
            if not item.is_claimable(now=now):
                continue
            if int(row.get("attempts") or 0) >= int(row.get("max_attempts") or DEFAULT_MAX_ATTEMPTS):
                continue
            candidates.append((item.priority, item.created_at_utc, index))
        if not candidates:
            return None
        candidates.sort(key=lambda entry: (-entry[0], entry[1]))
        chosen_index = candidates[0][2]
        rows[chosen_index] = _apply_claim(
            dict(rows[chosen_index]), actor=actor, role_id=role_id, lease_seconds=lease_seconds
        )
        item = WorkItem(**rows[chosen_index])
        _write_jsonl(path, rows)
    _emit(
        item,
        verb="work_item.claimed",
        actor=actor,
        extra={"lease_until_utc": item.lease_until_utc, "claim_token": item.claim_token},
        kernel_events_log=kernel_events_log,
    )
    return item


def start_work_item(
    work_id: str,
    *,
    actor: str,
    claim_token: int,
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> WorkItem:
    """Move a claimed item to ``running`` (optional; ``complete`` also works)."""
    path = log_path or DEFAULT_WORK_ITEMS_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        _require_live_claim(row, actor=actor, claim_token=claim_token)
        row["status"] = "running"
        row["updated_at_utc"] = _now_iso()
        return row

    item = _mutate(path, work_id, mutate)
    _emit(item, verb="work_item.started", actor=actor, kernel_events_log=kernel_events_log)
    return item


def heartbeat_work_item(
    work_id: str,
    *,
    actor: str,
    claim_token: int,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> WorkItem:
    """Extend the lease on a held claim for long-running work."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    path = log_path or DEFAULT_WORK_ITEMS_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        _require_live_claim(row, actor=actor, claim_token=claim_token)
        row["lease_until_utc"] = (_now() + timedelta(seconds=lease_seconds)).isoformat()
        row["updated_at_utc"] = _now_iso()
        return row

    item = _mutate(path, work_id, mutate)
    _emit(
        item,
        verb="work_item.heartbeat",
        actor=actor,
        extra={"lease_until_utc": item.lease_until_utc},
        kernel_events_log=kernel_events_log,
    )
    return item


def complete_work_item(
    work_id: str,
    *,
    actor: str,
    claim_token: int,
    exit_kind: str,
    result: str = "pass",
    producer: str | None = None,
    verifier: str | None = None,
    artifact_refs: list[dict[str, Any]] | None = None,
    log_path: Path | None = None,
    operating_units_log: Path | None = None,
    kernel_events_log: Path | None = None,
) -> WorkItem:
    """Complete a held work item with a bounded exit.

    ``exit_kind`` must be one of the operating unit's ``allowed_exits``: the
    kernel requires finished production work to land on a tenant-defined exit
    rather than an open-ended "done". When both ``producer`` and ``verifier``
    are recorded they must differ — completed-by-verified work keeps the
    generation/evaluation separation invariant.
    """
    if not exit_kind.strip():
        raise ValueError("exit_kind is required")
    if producer and verifier and producer == verifier:
        raise ValueError("producer and verifier must differ when both are recorded")
    clean_artifacts = _clean_artifact_refs(artifact_refs)
    path = log_path or DEFAULT_WORK_ITEMS_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        _require_live_claim(row, actor=actor, claim_token=claim_token)
        unit = _resolve_unit(row["unit_id"], operating_units_log=operating_units_log)
        if not unit.allows_exit(exit_kind):
            raise ValueError(
                f"exit {exit_kind!r} is not in {unit.unit_id}.allowed_exits "
                f"{unit.allowed_exits}"
            )
        row["status"] = "done"
        row["exit_kind"] = exit_kind
        row["result"] = result
        row["producer"] = producer
        row["verifier"] = verifier
        if clean_artifacts:
            row["artifact_refs"] = clean_artifacts
        row["lease_until_utc"] = None
        row["updated_at_utc"] = _now_iso()
        return row

    item = _mutate(path, work_id, mutate)
    extra: dict[str, Any] = {}
    unit = get_operating_unit(item.unit_id, log_path=operating_units_log)
    if unit is not None and unit.requires_governance_for(exit_kind):
        # The exit is recorded, but the tenant's governance worker still has to
        # ratify it before it counts as value. Surface that explicitly.
        extra["governance_required"] = True
    _emit(item, verb="work_item.completed", actor=actor, extra=extra, kernel_events_log=kernel_events_log)
    return item


def fail_work_item(
    work_id: str,
    *,
    actor: str,
    claim_token: int,
    reason: str,
    retryable: bool = True,
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> WorkItem:
    """Fail a held work item.

    A retryable failure with attempts remaining returns the item to ``queued``.
    A retryable failure that has exhausted ``max_attempts`` becomes a
    ``dead_letter`` for review. A non-retryable failure goes straight to
    ``failed``.
    """
    if not reason.strip():
        raise ValueError("reason is required")
    path = log_path or DEFAULT_WORK_ITEMS_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        _require_live_claim(row, actor=actor, claim_token=claim_token)
        attempts = int(row.get("attempts") or 0)
        max_attempts = int(row.get("max_attempts") or DEFAULT_MAX_ATTEMPTS)
        row["failure_reason"] = reason
        row["claimed_by_actor"] = None
        row["claimed_by_role"] = None
        row["lease_until_utc"] = None
        row["updated_at_utc"] = _now_iso()
        if not retryable:
            row["status"] = "failed"
        elif attempts >= max_attempts:
            row["status"] = "dead_letter"
            row["dead_letter_reason"] = (
                f"exhausted {max_attempts} attempts; last failure: {reason}"
            )
        else:
            row["status"] = "queued"
        return row

    item = _mutate(path, work_id, mutate)
    verb = {
        "queued": "work_item.failed_retry",
        "failed": "work_item.failed",
        "dead_letter": "work_item.dead_lettered",
    }[item.status]
    _emit(
        item,
        verb=verb,
        actor=actor,
        extra={"retryable": retryable},
        kernel_events_log=kernel_events_log,
    )
    return item


def retire_work_item(
    work_id: str,
    *,
    actor: str,
    reason: str,
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> WorkItem:
    """Retire a non-terminal work item that is no longer worth doing."""
    if not reason.strip():
        raise ValueError("reason is required")
    path = log_path or DEFAULT_WORK_ITEMS_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        if row.get("status") in TERMINAL_STATES:
            raise ValueError(f"work item is {row.get('status')}; cannot retire")
        row["status"] = "retired"
        row["failure_reason"] = reason
        row["claimed_by_actor"] = None
        row["claimed_by_role"] = None
        row["lease_until_utc"] = None
        row["updated_at_utc"] = _now_iso()
        return row

    item = _mutate(path, work_id, mutate)
    _emit(item, verb="work_item.retired", actor=actor, kernel_events_log=kernel_events_log)
    return item


def requeue_dead_letter(
    work_id: str,
    *,
    actor: str,
    reset_attempts: bool = True,
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> WorkItem:
    """Return a reviewed dead letter to the queue.

    This is the only transition out of ``dead_letter`` and is meant for an
    operator who has fixed the underlying cause.
    """
    path = log_path or DEFAULT_WORK_ITEMS_LOG

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        if row.get("status") != "dead_letter":
            raise ValueError(f"work item is {row.get('status')}, not a dead letter")
        row["status"] = "queued"
        if reset_attempts:
            row["attempts"] = 0
        row["dead_letter_reason"] = None
        row["updated_at_utc"] = _now_iso()
        return row

    item = _mutate(path, work_id, mutate)
    _emit(
        item,
        verb="work_item.requeued",
        actor=actor,
        extra={"reset_attempts": reset_attempts},
        kernel_events_log=kernel_events_log,
    )
    return item


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------


def list_work_items(
    *,
    unit_id: str | None = None,
    status: WorkItemStatus | str | None = None,
    kind: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> list[WorkItem]:
    if status is not None and status not in VALID_WORK_ITEM_STATUSES:
        raise ValueError(
            f"invalid status {status!r}; expected one of {sorted(VALID_WORK_ITEM_STATUSES)}"
        )
    out: list[WorkItem] = []
    for row in _read_jsonl(log_path or DEFAULT_WORK_ITEMS_LOG):
        item = WorkItem(**row)
        if unit_id is not None and item.unit_id != unit_id:
            continue
        if status is not None and item.status != status:
            continue
        if kind is not None and item.kind != kind:
            continue
        if tenant_id is not None and item.tenant_id != tenant_id:
            continue
        if project_id is not None and item.project_id != project_id:
            continue
        out.append(item)
    return out


def get_work_item(work_id: str, *, log_path: Path | None = None) -> WorkItem | None:
    for item in list_work_items(log_path=log_path):
        if item.work_id == work_id:
            return item
    return None


def list_dead_letters(
    *,
    unit_id: str | None = None,
    log_path: Path | None = None,
) -> list[WorkItem]:
    return list_work_items(unit_id=unit_id, status="dead_letter", log_path=log_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage cognitive-firm work items.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("--unit-id", required=True)
    enqueue.add_argument("--kind", required=True)
    enqueue.add_argument("--priority", type=int, default=0)
    enqueue.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    enqueue.add_argument("--owner-role")
    enqueue.add_argument("--tenant-id")
    enqueue.add_argument("--project-id")
    enqueue.add_argument("--idempotency-key")
    enqueue.add_argument("--payload-json", default="{}")
    enqueue.add_argument("--actor", default="service.kernel")
    enqueue.add_argument("--log-path", type=Path)
    enqueue.add_argument("--operating-units-log", type=Path)

    claim = sub.add_parser("claim-next")
    claim.add_argument("--unit-id", required=True)
    claim.add_argument("--actor", required=True)
    claim.add_argument("--role-id")
    claim.add_argument("--kind")
    claim.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    claim.add_argument("--log-path", type=Path)
    claim.add_argument("--operating-units-log", type=Path)

    complete = sub.add_parser("complete")
    complete.add_argument("work_id")
    complete.add_argument("--actor", required=True)
    complete.add_argument("--claim-token", type=int, required=True)
    complete.add_argument("--exit-kind", required=True)
    complete.add_argument("--result", default="pass")
    complete.add_argument("--producer")
    complete.add_argument("--verifier")
    complete.add_argument("--log-path", type=Path)
    complete.add_argument("--operating-units-log", type=Path)

    fail = sub.add_parser("fail")
    fail.add_argument("work_id")
    fail.add_argument("--actor", required=True)
    fail.add_argument("--claim-token", type=int, required=True)
    fail.add_argument("--reason", required=True)
    fail.add_argument("--non-retryable", action="store_true")
    fail.add_argument("--log-path", type=Path)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--unit-id")
    list_parser.add_argument("--status")
    list_parser.add_argument("--kind")
    list_parser.add_argument("--log-path", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "enqueue":
        item = enqueue_work_item(
            unit_id=args.unit_id,
            kind=args.kind,
            payload=json.loads(args.payload_json),
            priority=args.priority,
            max_attempts=args.max_attempts,
            owner_role=args.owner_role,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            idempotency_key=args.idempotency_key,
            actor=args.actor,
            log_path=args.log_path,
            operating_units_log=args.operating_units_log,
        )
        print(json.dumps(item.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "claim-next":
        item = claim_next_work_item(
            unit_id=args.unit_id,
            actor=args.actor,
            role_id=args.role_id,
            kind=args.kind,
            lease_seconds=args.lease_seconds,
            log_path=args.log_path,
            operating_units_log=args.operating_units_log,
        )
        print(json.dumps(item.as_dict() if item else {}, sort_keys=True))
        return 0
    if args.cmd == "complete":
        item = complete_work_item(
            args.work_id,
            actor=args.actor,
            claim_token=args.claim_token,
            exit_kind=args.exit_kind,
            result=args.result,
            producer=args.producer,
            verifier=args.verifier,
            log_path=args.log_path,
            operating_units_log=args.operating_units_log,
        )
        print(json.dumps(item.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "fail":
        item = fail_work_item(
            args.work_id,
            actor=args.actor,
            claim_token=args.claim_token,
            reason=args.reason,
            retryable=not args.non_retryable,
            log_path=args.log_path,
        )
        print(json.dumps(item.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "list":
        for item in list_work_items(
            unit_id=args.unit_id,
            status=args.status,
            kind=args.kind,
            log_path=args.log_path,
        ):
            print(json.dumps(item.as_dict(), sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
