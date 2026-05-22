from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration import work_items as work_items_module  # noqa: E402
from cognitive_firm.orchestration.operating_unit_surface import (  # noqa: E402
    build_operating_unit_dashboard,
    format_dashboard_table,
)
from cognitive_firm.orchestration.operating_units import define_operating_unit  # noqa: E402
from cognitive_firm.orchestration.work_items import (  # noqa: E402
    claim_next_work_item,
    complete_work_item,
    enqueue_work_item,
    fail_work_item,
)


class _Logs:
    def __init__(self, tmp_path: Path):
        self.units = tmp_path / "operating_units.jsonl"
        self.work = tmp_path / "work_items.jsonl"
        self.events = tmp_path / "kernel_events.jsonl"


@pytest.fixture()
def logs(tmp_path: Path) -> _Logs:
    bundle = _Logs(tmp_path)
    define_operating_unit(
        unit_id="residual_compiler",
        unit_kind="transformation_lane",
        display_name="Residual Compiler",
        owner_role="role.manager",
        allowed_work_kinds=["compile"],
        allowed_exits=["exact_gap"],
        worker_roles=["role.worker"],
        sla={"p95_seconds": 5},
        log_path=bundle.units,
    )
    return bundle


def _enqueue(logs: _Logs, **overrides):
    base = dict(
        unit_id="residual_compiler",
        kind="compile",
        log_path=logs.work,
        operating_units_log=logs.units,
        kernel_events_log=logs.events,
    )
    base.update(overrides)
    return enqueue_work_item(**base)


def _claim(logs: _Logs):
    return claim_next_work_item(
        unit_id="residual_compiler",
        actor="actor.worker",
        role_id="role.worker",
        log_path=logs.work,
        operating_units_log=logs.units,
        kernel_events_log=logs.events,
    )


def test_dashboard_counts_backlog_and_claimed(logs: _Logs):
    _enqueue(logs)
    _enqueue(logs)
    _claim(logs)

    dashboard = build_operating_unit_dashboard(
        operating_units_log=logs.units, work_items_log=logs.work
    )
    unit = dashboard.units[0]
    assert unit.backlog == 1
    assert unit.claimed == 1
    assert dashboard.counts["total_backlog"] == 1
    assert dashboard.counts["total_claimed"] == 1
    # The table renderer should not raise on a populated dashboard.
    assert "Residual Compiler" in format_dashboard_table(dashboard)


def test_dashboard_reports_p95_and_sla_breach(logs: _Logs, monkeypatch):
    base = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)
    clock = {"now": base}
    monkeypatch.setattr(work_items_module, "_now", lambda: clock["now"])

    item = _enqueue(logs)
    claimed = _claim(logs)
    assert claimed is not None
    # Work takes 30 seconds of wall time, well past the 5s SLA.
    clock["now"] = base + timedelta(seconds=30)
    complete_work_item(
        item.work_id,
        actor="actor.worker",
        claim_token=claimed.claim_token,
        exit_kind="exact_gap",
        log_path=logs.work,
        operating_units_log=logs.units,
        kernel_events_log=logs.events,
    )

    dashboard = build_operating_unit_dashboard(
        operating_units_log=logs.units, work_items_log=logs.work
    )
    unit = dashboard.units[0]
    assert unit.done == 1
    assert unit.p95_seconds == 30.0
    assert unit.sla_p95_seconds == 5.0
    assert unit.sla_breached is True
    assert unit.blocker == "sla breach"


def test_dashboard_flags_dead_letters_as_blocker(logs: _Logs):
    item = _enqueue(logs, max_attempts=1)
    claimed = _claim(logs)
    assert claimed is not None
    fail_work_item(
        item.work_id,
        actor="actor.worker",
        claim_token=claimed.claim_token,
        reason="hard failure",
        log_path=logs.work,
        kernel_events_log=logs.events,
    )

    dashboard = build_operating_unit_dashboard(
        operating_units_log=logs.units, work_items_log=logs.work
    )
    unit = dashboard.units[0]
    assert unit.dead_letter == 1
    assert "dead letter" in unit.blocker
    assert dashboard.counts["units_with_blocker"] == 1


def test_dashboard_flags_stale_claims(logs: _Logs, monkeypatch):
    # Claim in the distant past so the lease is long expired by real "now".
    monkeypatch.setattr(
        work_items_module,
        "_now",
        lambda: datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    _enqueue(logs)
    claimed = _claim(logs)
    assert claimed is not None
    monkeypatch.undo()

    dashboard = build_operating_unit_dashboard(
        operating_units_log=logs.units, work_items_log=logs.work
    )
    unit = dashboard.units[0]
    assert unit.claimed == 1
    assert unit.stale_claims == 1
    assert "stale claim" in unit.blocker


def test_empty_dashboard_is_well_formed(logs: _Logs):
    dashboard = build_operating_unit_dashboard(
        operating_units_log=logs.units, work_items_log=logs.work
    )
    assert dashboard.counts["operating_units"] == 1
    assert dashboard.units[0].blocker == "none"
