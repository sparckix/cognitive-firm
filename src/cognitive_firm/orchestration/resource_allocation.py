"""M-form resource allocation: governed reallocation across operating units.

The kernel ships operating units (the divisional "M" of Chandler's
multidivisional form) and a read-only dashboard. It did not have the *general
office*: the body that allocates capital across divisions and holds them to
account. Without it, capacity drifts silently — a unit runs to a cap that no
one decided, and a starved high-yield unit can never be rebalanced through a
reviewable transition.

An :class:`AllocationDecision` is that missing record. It is a durable,
governed statement that a deciding role moved a bounded quantity of a named
``resource_kind`` (``budget_usd``, ``worker_capacity``, ``attention_quota`` —
a tenant-defined string) FROM one operating unit (or the reserve pool) TO
another, under an explicit ``authority_basis``, with a ``rationale`` and
optional evidence references that justified it.

CRITICAL BOUNDARY. The kernel records WHO decided to move HOW MUCH, WHY, and
under WHAT authority — and projects the resulting ledger. The kernel does NOT
decide the amounts. There is no optimizer, no scoring, no bandit here; that is
tenant policy (see ``docs/abstraction-map.md``, "What Belongs Outside The
Kernel"). The general office's capital-allocation *decisions* become reviewable
governed state; the general office's *strategy* stays in the tenant overlay.

A decision moves through ``proposed -> applied`` (and ``applied -> reverted``).
Only an *applied* decision mutates the allocation ledger. The ledger read model
(:func:`current_allocation`) is derived: it sums applied, non-reverted
decisions into a net quantity per unit and can be rebuilt at any time.

T1 stores decisions in a JSONL log and holds an exclusive file lock around
every mutation, which is enough for one host. A T2 deployment puts the same
rows behind the transactional state backend so the status transition is
checked inside the mutation transaction; the contract here is identical either
way.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.kernel_events import record_kernel_event


AllocationStatus = Literal["proposed", "applied", "reverted"]
VALID_ALLOCATION_STATUSES = {"proposed", "applied", "reverted"}
# Only an applied decision contributes to the ledger.
LEDGER_AFFECTING_STATUSES = {"applied"}

# Sentinel unit id for the firm-level reserve pool that capital is allocated
# out of and returned to. It is not an operating unit; it is the general
# office's unallocated balance. A tenant never registers it as an
# OperatingUnit; the kernel treats it as a valid allocation endpoint.
RESERVE_POOL = "__reserve__"

DEFAULT_RESOURCE_ALLOCATION_LOG = (
    ORG_ROOT_DIR / "resource_allocation" / "allocation_decisions.jsonl"
)


@dataclass(frozen=True)
class AllocationDecision:
    """One governed decision to move resource between operating units.

    Canonical state. The allocation ledger
    (:func:`current_allocation`) and :func:`allocation_summary` are read models
    derived from these rows and can be rebuilt at any time.

    The kernel records the decision. It does not compute the ``amount``: the
    amount, and the policy that produced it, are tenant-owned.
    """

    decision_id: str
    resource_kind: str
    from_unit: str
    to_unit: str
    amount: float
    deciding_role: str
    deciding_actor: str
    authority_basis: str
    rationale: str
    effective_from_utc: str
    created_at_utc: str
    updated_at_utc: str
    status: AllocationStatus = "proposed"
    effective_until_utc: str | None = None
    applied_at_utc: str | None = None
    reverted_at_utc: str | None = None
    reverted_reason: str | None = None
    outcome_link_ids: list[str] = field(default_factory=list)
    change_refs: list[str] = field(default_factory=list)
    tenant_id: str | None = None
    project_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_ledger_affecting(self) -> bool:
        """Return whether this decision currently moves the ledger."""
        return self.status in LEDGER_AFFECTING_STATUSES


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


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


@contextlib.contextmanager
def _allocation_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive lock so two local writers cannot race a status change."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _clean_str(value: Any, *, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _clean_ref_list(values: list[str] | None, *, label: str) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if not text:
            raise ValueError(f"{label} entries must be non-empty")
        if text not in out:
            out.append(text)
    return out


def _emit(
    decision: AllocationDecision,
    *,
    verb: str,
    actor: str,
    extra: dict[str, Any] | None = None,
    kernel_events_log: Path | None = None,
) -> None:
    """Record an allocation transition on the canonical kernel-event stream.

    The payload carries the move (resource kind, from/to unit, amount) and the
    authority under which it was decided — not a recomputation of any score.
    """
    payload: dict[str, Any] = {
        "decision_id": decision.decision_id,
        "resource_kind": decision.resource_kind,
        "from_unit": decision.from_unit,
        "to_unit": decision.to_unit,
        "amount": decision.amount,
        "status": decision.status,
        "deciding_role": decision.deciding_role,
        "authority_basis": decision.authority_basis,
    }
    if decision.outcome_link_ids:
        payload["outcome_link_ids"] = decision.outcome_link_ids
    if decision.change_refs:
        payload["change_refs"] = decision.change_refs
    if extra:
        payload.update(extra)
    record_kernel_event(
        actor=actor,
        verb=verb,
        object_ref=f"allocation_decision:{decision.decision_id}",
        subject_ref=f"resource_kind:{decision.resource_kind}",
        tenant_id=decision.tenant_id,
        project_id=decision.project_id,
        idempotency_key=f"{verb}:{decision.decision_id}",
        payload=payload,
        log_path=kernel_events_log,
    )


def _mutate(
    path: Path,
    decision_id: str,
    mutate: Callable[[dict[str, Any]], dict[str, Any]],
) -> AllocationDecision:
    """Apply ``mutate`` to one decision row inside the exclusive lock."""
    with _allocation_lock(path):
        rows = _read_jsonl(path)
        updated: AllocationDecision | None = None
        next_rows: list[dict[str, Any]] = []
        for row in rows:
            if row.get("decision_id") == decision_id:
                row = mutate(dict(row))
                updated = AllocationDecision(**row)
            next_rows.append(row)
        if updated is None:
            raise KeyError(f"allocation decision not found: {decision_id}")
        _write_jsonl(path, next_rows)
        return updated


# ---------------------------------------------------------------------------
# decision lifecycle
# ---------------------------------------------------------------------------


def record_allocation_decision(
    *,
    resource_kind: str,
    from_unit: str,
    to_unit: str,
    amount: float,
    deciding_role: str,
    deciding_actor: str,
    authority_basis: str,
    rationale: str,
    effective_from_utc: str | None = None,
    effective_until_utc: str | None = None,
    outcome_link_ids: list[str] | None = None,
    change_refs: list[str] | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    decision_id: str | None = None,
    actor: str | None = None,
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> AllocationDecision:
    """Record a proposed allocation decision.

    The decision starts in ``proposed`` and does not move the ledger until it
    is applied. The kernel validates the *shape* of the move — a positive
    amount, two distinct endpoints — but never the *size*: the amount, and the
    policy that produced it, are tenant-owned.

    ``from_unit``/``to_unit`` are operating-unit ids, or the ``RESERVE_POOL``
    sentinel for the firm's unallocated balance. The kernel does not require
    the units to be registered: an allocation decision is a governance record,
    and a tenant may pre-record a move against a unit it is about to define.
    """
    resource_kind = _clean_str(resource_kind, label="resource_kind")
    from_unit = _clean_str(from_unit, label="from_unit")
    to_unit = _clean_str(to_unit, label="to_unit")
    deciding_role = _clean_str(deciding_role, label="deciding_role")
    deciding_actor = _clean_str(deciding_actor, label="deciding_actor")
    authority_basis = _clean_str(authority_basis, label="authority_basis")
    rationale = _clean_str(rationale, label="rationale")

    if from_unit == to_unit:
        raise ValueError("from_unit and to_unit must differ; a decision moves resource")
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise ValueError("amount must be a number")
    if amount <= 0:
        raise ValueError("amount must be positive; it is the quantity moved")

    now = _now_iso()
    effective_from = effective_from_utc or now
    if effective_until_utc is not None and (
        _parse_iso(effective_until_utc) <= _parse_iso(effective_from)
    ):
        raise ValueError("effective_until_utc must be after effective_from_utc")

    decision = AllocationDecision(
        decision_id=decision_id or f"alloc_{uuid.uuid4().hex[:16]}",
        resource_kind=resource_kind,
        from_unit=from_unit,
        to_unit=to_unit,
        amount=amount,
        deciding_role=deciding_role,
        deciding_actor=deciding_actor,
        authority_basis=authority_basis,
        rationale=rationale,
        effective_from_utc=effective_from,
        created_at_utc=now,
        updated_at_utc=now,
        status="proposed",
        effective_until_utc=effective_until_utc,
        outcome_link_ids=_clean_ref_list(outcome_link_ids, label="outcome_link_ids"),
        change_refs=_clean_ref_list(change_refs, label="change_refs"),
        tenant_id=tenant_id,
        project_id=project_id,
        metadata=dict(metadata or {}),
    )
    path = log_path or DEFAULT_RESOURCE_ALLOCATION_LOG
    with _allocation_lock(path):
        _append_jsonl(path, decision.as_dict())
    _emit(
        decision,
        verb="allocation_decision.proposed",
        actor=actor or deciding_actor,
        kernel_events_log=kernel_events_log,
    )
    return decision


def apply_allocation_decision(
    decision_id: str,
    *,
    actor: str,
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> AllocationDecision:
    """Apply a proposed decision: this is what mutates the allocation ledger.

    Only a ``proposed`` decision can be applied. Applying records the firm's
    commitment to the move; from this point the decision contributes to
    :func:`current_allocation`.
    """

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        status = row.get("status")
        if status != "proposed":
            raise ValueError(
                f"allocation decision is {status}, not proposed; cannot apply"
            )
        now = _now_iso()
        row["status"] = "applied"
        row["applied_at_utc"] = now
        row["updated_at_utc"] = now
        return row

    decision = _mutate(log_path or DEFAULT_RESOURCE_ALLOCATION_LOG, decision_id, mutate)
    _emit(
        decision,
        verb="allocation_decision.applied",
        actor=actor,
        extra={"applied_at_utc": decision.applied_at_utc},
        kernel_events_log=kernel_events_log,
    )
    return decision


def revert_allocation_decision(
    decision_id: str,
    *,
    actor: str,
    reason: str,
    log_path: Path | None = None,
    kernel_events_log: Path | None = None,
) -> AllocationDecision:
    """Revert an applied decision: undo its effect on the ledger.

    Only an ``applied`` decision can be reverted. A reverted decision no longer
    contributes to :func:`current_allocation`. Reverting is itself a governed
    transition with its own actor and reason; the original decision row is kept
    for audit rather than deleted.
    """
    reason = _clean_str(reason, label="reason")

    def mutate(row: dict[str, Any]) -> dict[str, Any]:
        status = row.get("status")
        if status != "applied":
            raise ValueError(
                f"allocation decision is {status}, not applied; only an applied "
                "decision can be reverted"
            )
        now = _now_iso()
        row["status"] = "reverted"
        row["reverted_at_utc"] = now
        row["reverted_reason"] = reason
        row["updated_at_utc"] = now
        return row

    decision = _mutate(log_path or DEFAULT_RESOURCE_ALLOCATION_LOG, decision_id, mutate)
    _emit(
        decision,
        verb="allocation_decision.reverted",
        actor=actor,
        extra={"reverted_reason": reason},
        kernel_events_log=kernel_events_log,
    )
    return decision


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------


def list_allocation_decisions(
    *,
    resource_kind: str | None = None,
    unit_id: str | None = None,
    status: AllocationStatus | str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> list[AllocationDecision]:
    """List allocation decisions, optionally filtered.

    ``unit_id`` matches a decision whose ``from_unit`` *or* ``to_unit`` is the
    unit — every decision that touched that unit's allocation.
    """
    if status is not None and status not in VALID_ALLOCATION_STATUSES:
        raise ValueError(
            f"invalid status {status!r}; expected one of "
            f"{sorted(VALID_ALLOCATION_STATUSES)}"
        )
    out: list[AllocationDecision] = []
    for row in _read_jsonl(log_path or DEFAULT_RESOURCE_ALLOCATION_LOG):
        decision = AllocationDecision(**row)
        if resource_kind is not None and decision.resource_kind != resource_kind:
            continue
        if unit_id is not None and unit_id not in (decision.from_unit, decision.to_unit):
            continue
        if status is not None and decision.status != status:
            continue
        if tenant_id is not None and decision.tenant_id != tenant_id:
            continue
        if project_id is not None and decision.project_id != project_id:
            continue
        out.append(decision)
    return out


def get_allocation_decision(
    decision_id: str,
    *,
    log_path: Path | None = None,
) -> AllocationDecision | None:
    for decision in list_allocation_decisions(log_path=log_path):
        if decision.decision_id == decision_id:
            return decision
    return None


def require_allocation_decision(
    decision_id: str,
    *,
    log_path: Path | None = None,
) -> AllocationDecision:
    """Return a decision or raise ``KeyError`` when it does not exist."""
    decision = get_allocation_decision(decision_id, log_path=log_path)
    if decision is None:
        raise KeyError(f"allocation decision not found: {decision_id}")
    return decision


def current_allocation(
    resource_kind: str,
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> dict[str, float]:
    """Project the net allocated quantity per unit for one ``resource_kind``.

    This is the allocation ledger read model. It sums every *applied*,
    non-reverted decision: a ``to_unit`` gains ``amount``, a ``from_unit`` loses
    ``amount``. Proposed and reverted decisions are ignored. The result maps a
    unit id (including the ``RESERVE_POOL`` sentinel, if it appears) to its net
    position; a zero net position is kept so the unit stays visible.

    The ledger owns no facts of its own — it can always be rebuilt from the
    applied decisions in the log.
    """
    resource_kind = _clean_str(resource_kind, label="resource_kind")
    ledger: dict[str, float] = {}
    for decision in list_allocation_decisions(
        resource_kind=resource_kind,
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=log_path,
    ):
        if not decision.is_ledger_affecting():
            continue
        ledger[decision.from_unit] = (
            ledger.get(decision.from_unit, 0.0) - decision.amount
        )
        ledger[decision.to_unit] = (
            ledger.get(decision.to_unit, 0.0) + decision.amount
        )
    return ledger


def allocation_summary(
    resource_kind: str,
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Return a reviewable summary of one resource kind's allocation state.

    Reports the per-unit ledger, decision counts by status, and the net moved
    out of the reserve pool. Like :func:`current_allocation` this is a read
    model: it computes nothing the applied decisions do not already imply.
    """
    resource_kind = _clean_str(resource_kind, label="resource_kind")
    decisions = list_allocation_decisions(
        resource_kind=resource_kind,
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=log_path,
    )
    by_status: dict[str, int] = {status: 0 for status in sorted(VALID_ALLOCATION_STATUSES)}
    for decision in decisions:
        by_status[decision.status] = by_status.get(decision.status, 0) + 1
    ledger = current_allocation(
        resource_kind,
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=log_path,
    )
    unit_ledger = {
        unit: net for unit, net in sorted(ledger.items()) if unit != RESERVE_POOL
    }
    return {
        "resource_kind": resource_kind,
        "decision_count": len(decisions),
        "decisions_by_status": by_status,
        "ledger": unit_ledger,
        "reserve_pool_net": round(ledger.get(RESERVE_POOL, 0.0), 12),
        "allocated_to_units": round(sum(unit_ledger.values()), 12),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage cognitive-firm M-form resource-allocation decisions."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    record = sub.add_parser("record", help="record a proposed allocation decision")
    record.add_argument("--resource-kind", required=True)
    record.add_argument("--from-unit", required=True)
    record.add_argument("--to-unit", required=True)
    record.add_argument("--amount", type=float, required=True)
    record.add_argument("--deciding-role", required=True)
    record.add_argument("--deciding-actor", required=True)
    record.add_argument("--authority-basis", required=True)
    record.add_argument("--rationale", required=True)
    record.add_argument("--effective-from-utc")
    record.add_argument("--effective-until-utc")
    record.add_argument("--outcome-link-id", action="append", default=[])
    record.add_argument("--change-ref", action="append", default=[])
    record.add_argument("--tenant-id")
    record.add_argument("--project-id")
    record.add_argument("--log-path", type=Path)

    apply_parser = sub.add_parser("apply", help="apply a proposed decision to the ledger")
    apply_parser.add_argument("decision_id")
    apply_parser.add_argument("--actor", required=True)
    apply_parser.add_argument("--log-path", type=Path)

    revert = sub.add_parser("revert", help="revert an applied decision")
    revert.add_argument("decision_id")
    revert.add_argument("--actor", required=True)
    revert.add_argument("--reason", required=True)
    revert.add_argument("--log-path", type=Path)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--resource-kind")
    list_parser.add_argument("--unit-id")
    list_parser.add_argument("--status")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--log-path", type=Path)

    ledger = sub.add_parser("ledger", help="show the current allocation per unit")
    ledger.add_argument("resource_kind")
    ledger.add_argument("--tenant-id")
    ledger.add_argument("--project-id")
    ledger.add_argument("--log-path", type=Path)

    summary = sub.add_parser("summary")
    summary.add_argument("resource_kind")
    summary.add_argument("--tenant-id")
    summary.add_argument("--project-id")
    summary.add_argument("--log-path", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "record":
        decision = record_allocation_decision(
            resource_kind=args.resource_kind,
            from_unit=args.from_unit,
            to_unit=args.to_unit,
            amount=args.amount,
            deciding_role=args.deciding_role,
            deciding_actor=args.deciding_actor,
            authority_basis=args.authority_basis,
            rationale=args.rationale,
            effective_from_utc=args.effective_from_utc,
            effective_until_utc=args.effective_until_utc,
            outcome_link_ids=args.outcome_link_id,
            change_refs=args.change_ref,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
        )
        print(json.dumps(decision.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "apply":
        decision = apply_allocation_decision(
            args.decision_id, actor=args.actor, log_path=args.log_path
        )
        print(json.dumps(decision.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "revert":
        decision = revert_allocation_decision(
            args.decision_id,
            actor=args.actor,
            reason=args.reason,
            log_path=args.log_path,
        )
        print(json.dumps(decision.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "list":
        for decision in list_allocation_decisions(
            resource_kind=args.resource_kind,
            unit_id=args.unit_id,
            status=args.status,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
        ):
            print(json.dumps(decision.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "ledger":
        ledger_view = current_allocation(
            args.resource_kind,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
        )
        print(json.dumps(ledger_view, sort_keys=True))
        return 0
    if args.cmd == "summary":
        print(
            json.dumps(
                allocation_summary(
                    args.resource_kind,
                    tenant_id=args.tenant_id,
                    project_id=args.project_id,
                    log_path=args.log_path,
                ),
                sort_keys=True,
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
