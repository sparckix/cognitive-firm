"""Operating-unit dashboard: a read model over the production queue.

The organization surface answers "what is blocked, waiting, or carrying
learning?" for governance state. This module answers the parallel question for
production state: "is each operating unit keeping up, and where is the
backlog?"

It is a read model. It derives everything from operating-unit contracts and
their work items and can be rebuilt at any time; it never owns a fact and is
not a second source of truth.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cognitive_firm.orchestration.operating_units import (
    DEFAULT_OPERATING_UNITS_LOG,
    OperatingUnit,
    list_operating_units,
)
from cognitive_firm.orchestration.work_items import (
    DEFAULT_WORK_ITEMS_LOG,
    WorkItem,
    list_work_items,
)


@dataclass(frozen=True)
class OperatingUnitHealth:
    """Derived production health for one operating unit."""

    unit_id: str
    display_name: str
    unit_kind: str
    owner_role: str
    status: str
    backlog: int
    claimed: int
    stale_claims: int
    running: int
    done: int
    failed: int
    dead_letter: int
    retired: int
    throughput_per_day: float
    p95_seconds: float | None
    sla_p95_seconds: float | None
    sla_breached: bool
    blocker: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OperatingUnitDashboard:
    """Production-health projection across all operating units."""

    generated_at_utc: str
    throughput_window_hours: float
    units: list[OperatingUnitHealth] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "operating_units": len(self.units),
            "total_backlog": sum(u.backlog for u in self.units),
            "total_claimed": sum(u.claimed for u in self.units),
            "total_stale_claims": sum(u.stale_claims for u in self.units),
            "total_dead_letter": sum(u.dead_letter for u in self.units),
            "units_with_blocker": sum(1 for u in self.units if u.blocker != "none"),
            "units_breaching_sla": sum(1 for u in self.units if u.sla_breached),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at_utc": self.generated_at_utc,
            "throughput_window_hours": self.throughput_window_hours,
            "counts": self.counts,
            "units": [unit.as_dict() for unit in self.units],
        }


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


def _percentile(values: list[float], fraction: float) -> float | None:
    """Return a nearest-rank percentile; ``None`` for an empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def _unit_health(
    unit: OperatingUnit,
    items: list[WorkItem],
    *,
    now: datetime,
    throughput_window_hours: float,
) -> OperatingUnitHealth:
    backlog = claimed = running = stale = done = failed = dead = retired = 0
    durations: list[float] = []
    window_start = now - timedelta(hours=throughput_window_hours)
    recent_done = 0

    for item in items:
        if item.status == "queued":
            backlog += 1
        elif item.status == "claimed":
            claimed += 1
            if item.is_claim_stale(now=now):
                stale += 1
        elif item.status == "running":
            claimed += 1
            running += 1
            if item.is_claim_stale(now=now):
                stale += 1
        elif item.status == "done":
            done += 1
            created = _parse_iso(item.created_at_utc)
            finished = _parse_iso(item.updated_at_utc)
            if created and finished and finished >= created:
                durations.append((finished - created).total_seconds())
            if finished and finished >= window_start:
                recent_done += 1
        elif item.status == "failed":
            failed += 1
        elif item.status == "dead_letter":
            dead += 1
        elif item.status == "retired":
            retired += 1

    p95 = _percentile(durations, 0.95)
    sla_p95 = unit.sla.get("p95_seconds") if isinstance(unit.sla, dict) else None
    sla_p95_value = float(sla_p95) if isinstance(sla_p95, (int, float)) else None
    sla_breached = bool(sla_p95_value is not None and p95 is not None and p95 > sla_p95_value)
    throughput = recent_done * (24.0 / throughput_window_hours) if throughput_window_hours else 0.0

    if unit.status != "active":
        blocker = f"unit {unit.status}"
    elif dead:
        blocker = f"{dead} dead letter(s)"
    elif stale:
        blocker = f"{stale} stale claim(s)"
    elif sla_breached:
        blocker = "sla breach"
    else:
        blocker = "none"

    return OperatingUnitHealth(
        unit_id=unit.unit_id,
        display_name=unit.display_name,
        unit_kind=unit.unit_kind,
        owner_role=unit.owner_role,
        status=unit.status,
        backlog=backlog,
        claimed=claimed,
        stale_claims=stale,
        running=running,
        done=done,
        failed=failed,
        dead_letter=dead,
        retired=retired,
        throughput_per_day=round(throughput, 2),
        p95_seconds=round(p95, 2) if p95 is not None else None,
        sla_p95_seconds=sla_p95_value,
        sla_breached=sla_breached,
        blocker=blocker,
    )


def build_operating_unit_dashboard(
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    throughput_window_hours: float = 24.0,
    operating_units_log: Path | None = None,
    work_items_log: Path | None = None,
) -> OperatingUnitDashboard:
    """Derive production health for every operating unit."""
    if throughput_window_hours <= 0:
        raise ValueError("throughput_window_hours must be positive")
    now = datetime.now(timezone.utc)
    units = list_operating_units(
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=operating_units_log or DEFAULT_OPERATING_UNITS_LOG,
    )
    all_items = list_work_items(
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=work_items_log or DEFAULT_WORK_ITEMS_LOG,
    )
    by_unit: dict[str, list[WorkItem]] = {}
    for item in all_items:
        by_unit.setdefault(item.unit_id, []).append(item)

    health = [
        _unit_health(
            unit,
            by_unit.get(unit.unit_id, []),
            now=now,
            throughput_window_hours=throughput_window_hours,
        )
        for unit in sorted(units, key=lambda u: u.unit_id)
    ]
    return OperatingUnitDashboard(
        generated_at_utc=now.isoformat(),
        throughput_window_hours=throughput_window_hours,
        units=health,
    )


def format_dashboard_table(dashboard: OperatingUnitDashboard) -> str:
    """Render the dashboard as a compact Markdown table."""
    lines = [
        "# Operating Unit Dashboard",
        "",
        f"Generated: {dashboard.generated_at_utc}",
        f"Throughput window: {dashboard.throughput_window_hours:g}h",
        "",
        "| Operating Unit | Status | Backlog | Claimed | p95 (s) | Throughput/day | Blocker |",
        "|---|---|--:|--:|--:|--:|---|",
    ]
    for unit in dashboard.units:
        p95 = "-" if unit.p95_seconds is None else f"{unit.p95_seconds:g}"
        lines.append(
            f"| {unit.display_name} | {unit.status} | {unit.backlog} | "
            f"{unit.claimed} | {p95} | {unit.throughput_per_day:g} | {unit.blocker} |"
        )
    lines.extend(["", "## Counts"])
    for key, value in dashboard.counts.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the cognitive-firm operating-unit dashboard."
    )
    parser.add_argument("--tenant-id")
    parser.add_argument("--project-id")
    parser.add_argument("--throughput-window-hours", type=float, default=24.0)
    parser.add_argument("--operating-units-log", type=Path)
    parser.add_argument("--work-items-log", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    dashboard = build_operating_unit_dashboard(
        tenant_id=args.tenant_id,
        project_id=args.project_id,
        throughput_window_hours=args.throughput_window_hours,
        operating_units_log=args.operating_units_log,
        work_items_log=args.work_items_log,
    )
    if args.json:
        print(json.dumps(dashboard.as_dict(), indent=2, sort_keys=True))
    else:
        print(format_dashboard_table(dashboard), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
