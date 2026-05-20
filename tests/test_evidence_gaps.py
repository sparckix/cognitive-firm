from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.evidence_gaps import (  # noqa: E402
    create_evidence_gap,
    list_evidence_gaps,
    update_evidence_gap_status,
)


def test_create_and_list_evidence_gap(tmp_path: Path):
    log = tmp_path / "evidence_gaps.jsonl"
    gap = create_evidence_gap(
        gap_type="missing_external_comparator",
        target="vendor onboarding latency claim",
        description="Need an external baseline for review latency.",
        severity="blocking",
        producer="reviewer",
        adversarial_direction=True,
        fetch_query="approval workflow review latency benchmarks",
        owner_role="ops_director",
        tenant_id="acme",
        project_id="vendor_onboarding",
        log_path=log,
    )

    gaps = list_evidence_gaps(log_path=log)
    assert len(gaps) == 1
    assert gaps[0] == gap
    assert gaps[0].gap_id.startswith("gap_")
    assert gaps[0].adversarial_direction is True


def test_filter_evidence_gaps(tmp_path: Path):
    log = tmp_path / "evidence_gaps.jsonl"
    create_evidence_gap(
        gap_type="missing_external_comparator",
        target="A",
        description="Need source A.",
        severity="blocking",
        producer="reviewer",
        tenant_id="tenant_a",
        project_id="project_a",
        log_path=log,
    )
    create_evidence_gap(
        gap_type="missing_source",
        target="B",
        description="Need source B.",
        severity="useful",
        producer="operator",
        tenant_id="tenant_b",
        project_id="project_b",
        log_path=log,
    )

    assert len(list_evidence_gaps(severity="blocking", log_path=log)) == 1
    assert len(list_evidence_gaps(tenant_id="tenant_b", log_path=log)) == 1
    assert len(list_evidence_gaps(project_id="project_a", log_path=log)) == 1


def test_update_evidence_gap_status(tmp_path: Path):
    log = tmp_path / "evidence_gaps.jsonl"
    gap = create_evidence_gap(
        gap_type="missing_source",
        target="claim",
        description="Need source.",
        severity="useful",
        producer="reviewer",
        log_path=log,
    )

    updated = update_evidence_gap_status(gap.gap_id, "reviewed", log_path=log)
    assert updated.status == "reviewed"

    listed = list_evidence_gaps(status="reviewed", log_path=log)
    assert len(listed) == 1
    assert listed[0].gap_id == gap.gap_id


def test_invalid_status_or_severity_fails(tmp_path: Path):
    log = tmp_path / "evidence_gaps.jsonl"
    with pytest.raises(ValueError):
        create_evidence_gap(
            gap_type="missing_source",
            target="claim",
            description="Need source.",
            severity="urgent",
            producer="reviewer",
            log_path=log,
        )

    gap = create_evidence_gap(
        gap_type="missing_source",
        target="claim",
        description="Need source.",
        severity="useful",
        producer="reviewer",
        log_path=log,
    )
    with pytest.raises(ValueError):
        update_evidence_gap_status(gap.gap_id, "blocked", log_path=log)


def test_update_missing_gap_fails(tmp_path: Path):
    with pytest.raises(KeyError):
        update_evidence_gap_status("gap_missing", "closed", log_path=tmp_path / "gaps.jsonl")
