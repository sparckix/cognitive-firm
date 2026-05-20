from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.migrations import list_migrations, record_migration  # noqa: E402


def test_migration_record_defaults_to_dry_run(tmp_path: Path):
    log_path = tmp_path / "migrations.jsonl"
    record = record_migration(
        migration_id="mig_learning_events_v1_v2",
        primitive="learning_events",
        from_version="v1",
        to_version="v2",
        phase="expand",
        actor="role.engineer",
        rationale="Add superseded_by lifecycle metadata.",
        affected_refs=["org/learning_events/learning_events.jsonl"],
        log_path=log_path,
    )

    assert record.status == "dry_run"
    assert record.dry_run is True
    rows = list_migrations(primitive="learning_events", log_path=log_path)
    assert [row.migration_id for row in rows] == ["mig_learning_events_v1_v2"]


def test_applied_migration_requires_explicit_apply(tmp_path: Path):
    record = record_migration(
        migration_id="mig_governance_changes_v1_v2",
        primitive="governance_changes",
        from_version="v1",
        to_version="v2",
        phase="verify",
        actor="role.engineer",
        dry_run=False,
        verification_ref="tests/test_governance_changes.py",
        log_path=tmp_path / "migrations.jsonl",
    )

    assert record.status == "applied"
