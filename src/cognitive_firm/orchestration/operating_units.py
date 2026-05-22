"""Operating units: typed contracts for recurring production work.

A decision gate asks a human to approve. An accountability case records who
owns residual risk. Neither describes the *recurring production lane* that
turns inputs into bounded, reviewable outputs: a support desk, a sales-ops
queue, a research-triage lane, a data-cleaning station, a CI lane, a proof
mill.

An `OperatingUnit` is the kernel's generic name for one such lane. A tenant may
call it a station, desk, lane, or department. The kernel does not own the
domain policy inside a unit; it owns the typed contract around it:

- which work kinds the unit accepts;
- which roles may claim its work;
- which bounded exits count as a finished unit of work;
- when an operator must be in the loop;
- which exits require governance before they count as value.

Work flows through a unit as :class:`~cognitive_firm.orchestration.work_items.WorkItem`
records. The unit is the contract; the work item is the claimable row.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.resource_envelope import KernelResource, make_resource


OperatingUnitStatus = Literal["active", "paused", "retired"]
VALID_OPERATING_UNIT_STATUSES = {"active", "paused", "retired"}

# Worker classes are an open, documented vocabulary. The kernel enforces actor
# *identity* and *role* (via ``worker_roles``); the class is the design-time
# label that explains why a role is allowed to touch this unit.
WORKER_CLASSES = (
    "deterministic",  # gates, filters, schema checks, replay, registry refresh
    "llm",            # bounded proposal output only
    "agent",          # stateful edit/debug/repair within a budget
    "governance",     # independent verification and classification
    "operator",       # human policy, budget, hard interpretation, ambiguous promotion
)

DEFAULT_OPERATING_UNITS_LOG = ORG_ROOT_DIR / "operating_units" / "operating_units.jsonl"
_UNIT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")


@dataclass(frozen=True)
class OperatingUnit:
    """A typed contract for one recurring production lane.

    This is canonical state, not a read model. The dashboard in
    :mod:`cognitive_firm.orchestration.operating_unit_surface` is derived from
    units plus their work items and can be rebuilt at any time.
    """

    unit_id: str
    unit_kind: str
    display_name: str
    owner_role: str
    created_at_utc: str
    updated_at_utc: str
    input_kinds: list[str] = field(default_factory=list)
    allowed_work_kinds: list[str] = field(default_factory=list)
    allowed_exits: list[str] = field(default_factory=list)
    worker_roles: list[str] = field(default_factory=list)
    sla: dict[str, Any] = field(default_factory=dict)
    operator_required_when: list[str] = field(default_factory=list)
    governance_required_for: list[str] = field(default_factory=list)
    status: OperatingUnitStatus = "active"
    tenant_id: str | None = None
    project_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def allows_work_kind(self, kind: str) -> bool:
        return kind in self.allowed_work_kinds

    def allows_exit(self, exit_kind: str) -> bool:
        return exit_kind in self.allowed_exits

    def allows_worker_role(self, role_id: str | None) -> bool:
        """Return whether a role may claim work in this unit.

        An empty ``worker_roles`` list means the unit does not restrict
        claimants. This keeps single-principal T1 deployments lightweight; a
        tenant that wants the separation guarantee names its worker roles.
        """
        if not self.worker_roles:
            return True
        return bool(role_id) and role_id in self.worker_roles

    def requires_governance_for(self, exit_kind: str) -> bool:
        return exit_kind in self.governance_required_for


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _clean_list(values: list[str] | None, *, label: str) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = str(value).strip()
        if not text:
            raise ValueError(f"{label} entries must be non-empty")
        if text not in out:
            out.append(text)
    return out


def validate_operating_unit_payload(payload: dict[str, Any]) -> list[str]:
    """Return human-readable errors for a candidate operating-unit payload."""
    errors: list[str] = []
    unit_id = str(payload.get("unit_id") or "").strip()
    if not unit_id:
        errors.append("unit_id is required")
    elif not _UNIT_ID_RE.match(unit_id):
        errors.append("unit_id must be lowercase kebab/snake (a-z, 0-9, _)")
    for required in ("unit_kind", "display_name", "owner_role"):
        if not str(payload.get(required) or "").strip():
            errors.append(f"{required} is required")
    if not payload.get("allowed_work_kinds"):
        errors.append("allowed_work_kinds must list at least one work kind")
    if not payload.get("allowed_exits"):
        errors.append("allowed_exits must list at least one bounded exit")
    status = str(payload.get("status") or "active")
    if status not in VALID_OPERATING_UNIT_STATUSES:
        errors.append(
            f"status must be one of {sorted(VALID_OPERATING_UNIT_STATUSES)}"
        )
    governance = payload.get("governance_required_for") or []
    exits = set(payload.get("allowed_exits") or [])
    for exit_kind in governance:
        if exit_kind not in exits:
            errors.append(
                f"governance_required_for exit {exit_kind!r} is not in allowed_exits"
            )
    return errors


def define_operating_unit(
    *,
    unit_id: str,
    unit_kind: str,
    display_name: str,
    owner_role: str,
    input_kinds: list[str] | None = None,
    allowed_work_kinds: list[str] | None = None,
    allowed_exits: list[str] | None = None,
    worker_roles: list[str] | None = None,
    sla: dict[str, Any] | None = None,
    operator_required_when: list[str] | None = None,
    governance_required_for: list[str] | None = None,
    status: OperatingUnitStatus | str = "active",
    tenant_id: str | None = None,
    project_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    log_path: Path | None = None,
) -> OperatingUnit:
    """Register or replace one operating-unit contract.

    Definition is idempotent on ``unit_id``: redefining a unit replaces the
    contract and preserves the original ``created_at_utc``.
    """
    candidate = {
        "unit_id": unit_id,
        "unit_kind": unit_kind,
        "display_name": display_name,
        "owner_role": owner_role,
        "allowed_work_kinds": _clean_list(allowed_work_kinds, label="allowed_work_kinds"),
        "allowed_exits": _clean_list(allowed_exits, label="allowed_exits"),
        "governance_required_for": _clean_list(
            governance_required_for, label="governance_required_for"
        ),
        "status": str(status),
    }
    errors = validate_operating_unit_payload(candidate)
    if errors:
        raise ValueError("; ".join(errors))

    path = log_path or DEFAULT_OPERATING_UNITS_LOG
    rows = _read_jsonl(path)
    now = _now_iso()
    created_at = now
    next_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("unit_id") == unit_id:
            created_at = str(row.get("created_at_utc") or now)
            continue
        next_rows.append(row)

    unit = OperatingUnit(
        unit_id=unit_id.strip(),
        unit_kind=unit_kind.strip(),
        display_name=display_name.strip(),
        owner_role=owner_role.strip(),
        created_at_utc=created_at,
        updated_at_utc=now,
        input_kinds=_clean_list(input_kinds, label="input_kinds"),
        allowed_work_kinds=candidate["allowed_work_kinds"],
        allowed_exits=candidate["allowed_exits"],
        worker_roles=_clean_list(worker_roles, label="worker_roles"),
        sla=dict(sla or {}),
        operator_required_when=_clean_list(
            operator_required_when, label="operator_required_when"
        ),
        governance_required_for=candidate["governance_required_for"],
        status=str(status),  # type: ignore[arg-type]
        tenant_id=tenant_id,
        project_id=project_id,
        metadata=dict(metadata or {}),
    )
    _write_jsonl(path, [*next_rows, unit.as_dict()])
    return unit


def set_operating_unit_status(
    unit_id: str,
    status: OperatingUnitStatus | str,
    *,
    log_path: Path | None = None,
) -> OperatingUnit:
    """Pause, reactivate, or retire a unit without rewriting its contract."""
    if str(status) not in VALID_OPERATING_UNIT_STATUSES:
        raise ValueError(
            f"status must be one of {sorted(VALID_OPERATING_UNIT_STATUSES)}"
        )
    path = log_path or DEFAULT_OPERATING_UNITS_LOG
    rows = _read_jsonl(path)
    updated: OperatingUnit | None = None
    next_rows: list[dict[str, Any]] = []
    for row in rows:
        if row.get("unit_id") == unit_id:
            row = dict(row)
            row["status"] = str(status)
            row["updated_at_utc"] = _now_iso()
            updated = OperatingUnit(**row)
        next_rows.append(row)
    if updated is None:
        raise KeyError(f"operating unit not found: {unit_id}")
    _write_jsonl(path, next_rows)
    return updated


def list_operating_units(
    *,
    status: OperatingUnitStatus | str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    log_path: Path | None = None,
) -> list[OperatingUnit]:
    out: list[OperatingUnit] = []
    for row in _read_jsonl(log_path or DEFAULT_OPERATING_UNITS_LOG):
        unit = OperatingUnit(**row)
        if status is not None and unit.status != status:
            continue
        if tenant_id is not None and unit.tenant_id != tenant_id:
            continue
        if project_id is not None and unit.project_id != project_id:
            continue
        out.append(unit)
    return out


def get_operating_unit(unit_id: str, *, log_path: Path | None = None) -> OperatingUnit | None:
    for unit in list_operating_units(log_path=log_path):
        if unit.unit_id == unit_id:
            return unit
    return None


def require_operating_unit(unit_id: str, *, log_path: Path | None = None) -> OperatingUnit:
    """Return a unit or raise ``KeyError`` when it is not registered."""
    unit = get_operating_unit(unit_id, log_path=log_path)
    if unit is None:
        raise KeyError(f"operating unit not found: {unit_id}")
    return unit


def operating_unit_resource(unit: OperatingUnit) -> KernelResource:
    """Project a unit into the kernel resource envelope.

    The envelope is the compatibility shape external adapters and dashboards
    read; the JSONL row remains the source of truth.
    """
    return make_resource(
        kind="OperatingUnit",
        name=unit.unit_id,
        resource_id=unit.unit_id,
        tenant_id=unit.tenant_id,
        project_id=unit.project_id,
        stability="alpha",
        labels={"unit_kind": unit.unit_kind, "owner_role": unit.owner_role},
        spec={
            "unit_kind": unit.unit_kind,
            "display_name": unit.display_name,
            "owner_role": unit.owner_role,
            "input_kinds": unit.input_kinds,
            "allowed_work_kinds": unit.allowed_work_kinds,
            "allowed_exits": unit.allowed_exits,
            "worker_roles": unit.worker_roles,
            "sla": unit.sla,
            "operator_required_when": unit.operator_required_when,
            "governance_required_for": unit.governance_required_for,
        },
        status={"status": unit.status},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage cognitive-firm operating units.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    define = sub.add_parser("define")
    define.add_argument("--unit-id", required=True)
    define.add_argument("--unit-kind", required=True)
    define.add_argument("--display-name", required=True)
    define.add_argument("--owner-role", required=True)
    define.add_argument("--input-kind", action="append", default=[])
    define.add_argument("--allowed-work-kind", action="append", default=[])
    define.add_argument("--allowed-exit", action="append", default=[])
    define.add_argument("--worker-role", action="append", default=[])
    define.add_argument("--operator-required-when", action="append", default=[])
    define.add_argument("--governance-required-for", action="append", default=[])
    define.add_argument("--p95-seconds", type=int)
    define.add_argument("--tenant-id")
    define.add_argument("--project-id")
    define.add_argument("--log-path", type=Path)

    status_parser = sub.add_parser("set-status")
    status_parser.add_argument("unit_id")
    status_parser.add_argument("status")
    status_parser.add_argument("--log-path", type=Path)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--status")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--log-path", type=Path)
    list_parser.add_argument("--resource", action="store_true", help="render resource envelopes")

    args = parser.parse_args(argv)
    if args.cmd == "define":
        unit = define_operating_unit(
            unit_id=args.unit_id,
            unit_kind=args.unit_kind,
            display_name=args.display_name,
            owner_role=args.owner_role,
            input_kinds=args.input_kind,
            allowed_work_kinds=args.allowed_work_kind,
            allowed_exits=args.allowed_exit,
            worker_roles=args.worker_role,
            sla={"p95_seconds": args.p95_seconds} if args.p95_seconds else None,
            operator_required_when=args.operator_required_when,
            governance_required_for=args.governance_required_for,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
        )
        print(json.dumps(unit.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "set-status":
        unit = set_operating_unit_status(args.unit_id, args.status, log_path=args.log_path)
        print(json.dumps(unit.as_dict(), sort_keys=True))
        return 0
    if args.cmd == "list":
        for unit in list_operating_units(
            status=args.status,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            log_path=args.log_path,
        ):
            if args.resource:
                print(json.dumps(operating_unit_resource(unit).as_dict(), sort_keys=True))
            else:
                print(json.dumps(unit.as_dict(), sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
