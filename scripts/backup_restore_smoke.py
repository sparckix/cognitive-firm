#!/usr/bin/env python3
"""Smoke test for snapshot/restore of minimal kernel state.

This is not a full disaster-recovery implementation. It proves the public T1
shape is portable: kernel-owned files can be archived, restored into a fresh
directory, and consumed by the same read models.
"""

from __future__ import annotations

import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.accountability_cases import create_accountability_case
from cognitive_firm.orchestration.human_work import create_human_work_session
from cognitive_firm.orchestration.org_surface import build_org_surface


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cognitive-firm-backup-restore-") as tmp:
        root = Path(tmp)
        source = root / "source"
        restored = root / "restored"
        archive = root / "snapshot.tar.gz"

        human_work_log = source / "org" / "human_work" / "human_work.jsonl"
        accountability_log = source / "org" / "accountability" / "accountability_cases.jsonl"
        create_human_work_session(
            requested_by="role.manager",
            human_actor="human.principal",
            objective="verify restricted source",
            work_mode="source_check",
            bottleneck_class="access",
            receipt_required=True,
            receipt_type="note",
            log_path=human_work_log,
        )
        create_accountability_case(
            trigger_ref="pilot/error-rate-regression",
            accountable_role="role.manager",
            responsible_actor="human.principal",
            decision_right_basis="pilot charter",
            authority_envelope_ref="org/mandates/manager_mandate.md",
            risk_tier="medium",
            recourse_path="reopen",
            rationale="backup/restore smoke fixture",
            log_path=accountability_log,
        )

        with tarfile.open(archive, "w:gz") as handle:
            handle.add(source, arcname=".")

        restored.mkdir(parents=True)
        with tarfile.open(archive, "r:gz") as handle:
            handle.extractall(restored, filter="data")

        surface = build_org_surface(
            project_root=restored,
            human_work_log=restored / "org" / "human_work" / "human_work.jsonl",
            accountability_cases_log=restored
            / "org"
            / "accountability"
            / "accountability_cases.jsonl",
            evidence_gaps_log=restored / "org" / "evidence_gaps" / "evidence_gaps.jsonl",
            governance_changes_log=restored / "org" / "governance" / "governance_changes.jsonl",
            learning_events_log=restored / "org" / "learning" / "learning_events.jsonl",
            transitions_log=restored / "workspace" / "transitions.jsonl",
            damage_limit=0,
        )
        counts = surface.counts
        if counts["active_human_work_sessions"] != 1:
            raise SystemExit("restored human work session was not visible")
        if counts["open_accountability_cases"] != 1:
            raise SystemExit("restored accountability case was not visible")
        if archive.stat().st_size <= 0:
            raise SystemExit("snapshot archive was empty")
        shutil.rmtree(restored)
        print("OK: snapshot restored and organization surface matched expected state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
