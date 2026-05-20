"""Kernel state migration registry.

This is a small T1 migration protocol: migrations are explicit records with a
phase, source/target version, dry-run support, and an append-only application
log. It does not transform any specific primitive by itself.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR


MigrationPhase = Literal["expand", "backfill", "contract", "verify"]
MigrationStatus = Literal["planned", "dry_run", "applied", "failed"]

DEFAULT_MIGRATION_LOG = ORG_ROOT_DIR / "migrations" / "migrations.jsonl"
VALID_PHASES = {"expand", "backfill", "contract", "verify"}
VALID_STATUSES = {"planned", "dry_run", "applied", "failed"}


@dataclass(frozen=True)
class MigrationRecord:
    migration_id: str
    primitive: str
    from_version: str
    to_version: str
    phase: MigrationPhase
    status: MigrationStatus
    actor: str
    created_at_utc: str
    dry_run: bool = True
    rationale: str = ""
    affected_refs: list[str] = field(default_factory=list)
    backup_ref: str | None = None
    verification_ref: str | None = None
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def record_migration(
    *,
    migration_id: str,
    primitive: str,
    from_version: str,
    to_version: str,
    phase: MigrationPhase | str,
    actor: str,
    dry_run: bool = True,
    rationale: str = "",
    affected_refs: list[str] | None = None,
    backup_ref: str | None = None,
    verification_ref: str | None = None,
    errors: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    log_path: Path | None = None,
) -> MigrationRecord:
    if not migration_id.strip():
        raise ValueError("migration_id is required")
    if not primitive.strip():
        raise ValueError("primitive is required")
    if not from_version.strip() or not to_version.strip():
        raise ValueError("from_version and to_version are required")
    if not actor.strip():
        raise ValueError("actor is required")
    status = "dry_run" if dry_run else ("failed" if errors else "applied")
    record = MigrationRecord(
        migration_id=migration_id,
        primitive=primitive,
        from_version=from_version,
        to_version=to_version,
        phase=_validate_phase(str(phase)),
        status=status,  # type: ignore[arg-type]
        actor=actor,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        dry_run=dry_run,
        rationale=rationale,
        affected_refs=affected_refs or [],
        backup_ref=backup_ref,
        verification_ref=verification_ref,
        errors=errors or [],
        metadata=metadata or {},
    )
    _append_jsonl(log_path or DEFAULT_MIGRATION_LOG, record.as_dict())
    return record


def list_migrations(
    *,
    primitive: str | None = None,
    status: MigrationStatus | str | None = None,
    log_path: Path | None = None,
) -> list[MigrationRecord]:
    if status is not None:
        status = _validate_status(str(status))
    out: list[MigrationRecord] = []
    for row in _read_jsonl(log_path or DEFAULT_MIGRATION_LOG):
        record = MigrationRecord(**row)
        if primitive is not None and record.primitive != primitive:
            continue
        if status is not None and record.status != status:
            continue
        out.append(record)
    return out


def _validate_phase(phase: str) -> MigrationPhase:
    if phase not in VALID_PHASES:
        raise ValueError(f"invalid migration phase {phase!r}; expected one of {sorted(VALID_PHASES)}")
    return phase  # type: ignore[return-value]


def _validate_status(status: str) -> MigrationStatus:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid migration status {status!r}; expected one of {sorted(VALID_STATUSES)}")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record or inspect kernel migration records.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--primitive")
    list_parser.add_argument("--status")
    list_parser.add_argument("--log-path", type=Path)

    record_parser = sub.add_parser("record")
    record_parser.add_argument("--migration-id", required=True)
    record_parser.add_argument("--primitive", required=True)
    record_parser.add_argument("--from-version", required=True)
    record_parser.add_argument("--to-version", required=True)
    record_parser.add_argument("--phase", required=True)
    record_parser.add_argument("--actor", required=True)
    record_parser.add_argument("--apply", action="store_true")
    record_parser.add_argument("--rationale", default="")
    record_parser.add_argument("--affected-ref", action="append", default=[])
    record_parser.add_argument("--backup-ref")
    record_parser.add_argument("--verification-ref")
    record_parser.add_argument("--error", action="append", default=[])
    record_parser.add_argument("--log-path", type=Path)
    args = parser.parse_args(argv)

    if args.cmd == "list":
        rows = list_migrations(primitive=args.primitive, status=args.status, log_path=args.log_path)
        print(json.dumps([row.as_dict() for row in rows], indent=2, sort_keys=True))
        return 0

    record = record_migration(
        migration_id=args.migration_id,
        primitive=args.primitive,
        from_version=args.from_version,
        to_version=args.to_version,
        phase=args.phase,
        actor=args.actor,
        dry_run=not args.apply,
        rationale=args.rationale,
        affected_refs=args.affected_ref,
        backup_ref=args.backup_ref,
        verification_ref=args.verification_ref,
        errors=args.error,
        log_path=args.log_path,
    )
    print(json.dumps(record.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
