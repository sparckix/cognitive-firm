from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.evidence_gaps import (  # noqa: E402
    create_evidence_gap,
    evidence_gap_resource,
    list_evidence_gaps,
    main as evidence_gaps_main,
    update_evidence_gap_status,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


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


def test_evidence_gap_projects_to_resource_envelope(tmp_path: Path):
    log = tmp_path / "evidence_gaps.jsonl"
    gap = create_evidence_gap(
        gap_type="missing_external_comparator",
        target="launch claim: teardown time under 90 seconds",
        description="Need a competitor or field baseline before approving claim.",
        severity="blocking",
        producer="role.reviewer",
        adversarial_direction=True,
        fetch_query="field teardown time comparison",
        owner_role="role.research_director",
        tenant_id="tenant.example",
        project_id="project.alpha",
        source_ref="claim_brief:artifact_1",
        metadata={"queue": "evidence"},
        log_path=log,
    )

    payload = evidence_gap_resource(gap).as_dict()

    assert validate_resource(payload) == []
    assert payload["kind"] == "EvidenceGap"
    assert payload["metadata"]["name"] == gap.gap_id
    assert payload["metadata"]["tenant_id"] == "tenant.example"
    assert payload["metadata"]["project_id"] == "project.alpha"
    assert payload["metadata"]["labels"]["severity"] == "blocking"
    assert payload["metadata"]["labels"]["status"] == "open"
    assert payload["metadata"]["labels"]["adversarial_direction"] == "true"
    assert payload["metadata"]["annotations"]["queue"] == "evidence"
    assert payload["spec"]["target"] == "launch claim: teardown time under 90 seconds"
    assert payload["spec"]["source_ref"] == "claim_brief:artifact_1"
    assert payload["status"]["status"] == "open"
    assert {
        "rel": "target",
        "href": "launch claim: teardown time under 90 seconds",
    } in payload["links"]
    assert {"rel": "owner_role", "href": "role.research_director"} in payload["links"]
    assert {"rel": "source", "href": "claim_brief:artifact_1"} in payload["links"]


def test_evidence_gap_cli_can_render_resource_envelopes(
    tmp_path: Path,
    capsys,
):
    log = tmp_path / "evidence_gaps.jsonl"
    gap = create_evidence_gap(
        gap_type="missing_source",
        target="pricing claim",
        description="Need primary source before external use.",
        severity="useful",
        producer="role.analyst",
        log_path=log,
    )

    rc = evidence_gaps_main(["list", "--log-path", str(log), "--resource"])

    assert rc == 0
    output = capsys.readouterr().out
    assert '"kind": "EvidenceGap"' in output
    assert gap.gap_id in output
