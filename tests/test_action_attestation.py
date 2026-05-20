from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_attestation import (  # noqa: E402
    create_action_attestation,
    digest_file,
    digest_text,
    list_action_attestations,
)


def test_create_and_list_action_attestation(tmp_path: Path):
    log = tmp_path / "action_attestations.jsonl"
    attestation = create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report body"),
        producer="role.researcher",
        action_type="write_artifact",
        runtime_ref="codex-cli",
        tool_ref="apply_patch",
        policy_ref="mandates/researcher.yaml",
        input_refs=["workspace/source.md"],
        output_refs=["workspace/report.md"],
        tenant_id="tenant_a",
        project_id="project_a",
        run_id="run_1",
        log_path=log,
    )

    rows = list_action_attestations(log_path=log)
    assert rows == [attestation]
    assert attestation.attestation_id.startswith("aat_")
    assert attestation.verification_status == "unverified"
    assert attestation.subject_digest.startswith("sha256:")


def test_filter_action_attestations(tmp_path: Path):
    log = tmp_path / "action_attestations.jsonl"
    create_action_attestation(
        subject_kind="tool_call",
        subject_ref="linear:create_issue:1",
        subject_digest=digest_text("linear payload"),
        producer="role.manager",
        action_type="external_tool_call",
        tenant_id="tenant_a",
        project_id="project_a",
        verification_status="verified",
        log_path=log,
    )
    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/other.md",
        subject_digest=digest_text("other"),
        producer="role.reviewer",
        action_type="write_artifact",
        tenant_id="tenant_b",
        project_id="project_b",
        verification_status="failed",
        log_path=log,
    )

    assert len(list_action_attestations(producer="role.manager", log_path=log)) == 1
    assert len(list_action_attestations(tenant_id="tenant_b", log_path=log)) == 1
    assert len(list_action_attestations(verification_status="failed", log_path=log)) == 1
    assert len(list_action_attestations(subject_ref="workspace/other.md", log_path=log)) == 1


def test_digest_file(tmp_path: Path):
    path = tmp_path / "artifact.txt"
    path.write_text("hello", encoding="utf-8")
    assert digest_file(path) == digest_text("hello")


def test_invalid_action_attestation_fields_fail(tmp_path: Path):
    log = tmp_path / "action_attestations.jsonl"
    with pytest.raises(ValueError):
        create_action_attestation(
            subject_kind="unknown",
            subject_ref="x",
            subject_digest=digest_text("x"),
            producer="role.manager",
            action_type="write",
            log_path=log,
        )
