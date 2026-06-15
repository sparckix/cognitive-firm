from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_attestation import (  # noqa: E402
    action_attestation_resource,
    agent_invocation_audit_row,
    create_action_attestation,
    digest_file,
    digest_text,
    list_agent_invocation_audits,
    list_action_attestations,
    main as action_attestation_main,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


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


def test_action_attestation_projects_to_resource_envelope(tmp_path: Path):
    log = tmp_path / "action_attestations.jsonl"
    attestation = create_action_attestation(
        subject_kind="tool_call",
        subject_ref="mcp://linear/create_issue/1",
        subject_digest=digest_text("linear payload"),
        producer="role.manager",
        action_type="external_tool_call",
        runtime_ref="run:run_1",
        tool_ref="mcp.linear.create_issue",
        policy_ref="mcp_capability:linear_write",
        input_refs=["artifact://brief"],
        output_refs=["linear://issue/CF-1"],
        signature_ref="sigstore://bundle/1",
        transparency_ref="rekor://entry/1",
        verification_status="verified",
        verification_summary="signature and digest matched",
        tenant_id="tenant.example",
        project_id="project.alpha",
        run_id="run_1",
        metadata={"surface": "kernel_service"},
        log_path=log,
    )

    payload = action_attestation_resource(attestation).as_dict()

    assert validate_resource(payload) == []
    assert payload["kind"] == "ActionAttestation"
    assert payload["metadata"]["name"] == attestation.attestation_id
    assert payload["metadata"]["tenant_id"] == "tenant.example"
    assert payload["metadata"]["project_id"] == "project.alpha"
    assert payload["metadata"]["labels"]["subject_kind"] == "tool_call"
    assert payload["metadata"]["labels"]["verification_status"] == "verified"
    assert payload["metadata"]["labels"]["run_id"] == "run_1"
    assert payload["metadata"]["annotations"]["surface"] == "kernel_service"
    assert payload["spec"]["subject_digest"].startswith("sha256:")
    assert payload["spec"]["input_refs"] == ["artifact://brief"]
    assert payload["spec"]["metadata"] == {"surface": "kernel_service"}
    assert payload["status"]["verification_summary"] == "signature and digest matched"
    assert {"rel": "subject", "href": "mcp://linear/create_issue/1"} in payload["links"]
    assert {"rel": "tool", "href": "mcp.linear.create_issue"} in payload["links"]
    assert {"rel": "output", "href": "linear://issue/CF-1"} in payload["links"]


def test_action_attestation_resource_preserves_structured_invocation_receipt(
    tmp_path: Path,
):
    log = tmp_path / "action_attestations.jsonl"
    receipt = {
        "schema_version": "agent_invocation_receipt.v1",
        "runtime": "claude",
        "adapter": "claude_print",
        "command_argv": ["claude", "--print", "{prompt}"],
        "prompt_digest": digest_text("prompt"),
        "stdout_digest": digest_text("stdout"),
        "stderr_digest": digest_text(""),
    }
    attestation = create_action_attestation(
        subject_kind="runtime_event",
        subject_ref="agent_invocation_receipt:abc123",
        subject_digest=digest_text("receipt"),
        producer="role.manager",
        action_type="agent_cli_dispatch",
        runtime_ref="run:run_1",
        verification_status="verified",
        run_id="run_1",
        metadata={"agent_invocation_receipt": receipt},
        log_path=log,
    )

    payload = action_attestation_resource(attestation).as_dict()

    assert validate_resource(payload) == []
    assert payload["spec"]["metadata"]["agent_invocation_receipt"] == receipt
    assert (
        payload["spec"]["metadata"]["agent_invocation_receipt"]["schema_version"]
        == "agent_invocation_receipt.v1"
    )
    assert payload["metadata"]["annotations"]["agent_invocation_receipt"].startswith("{")


def test_agent_invocation_audit_read_model_lists_recent_receipts(tmp_path: Path):
    log = tmp_path / "action_attestations.jsonl"
    receipt = {
        "schema_version": "agent_invocation_receipt.v1",
        "runtime": "codex",
        "adapter": "codex_exec",
        "command_argv": ["codex", "exec", "-"],
        "prompt_transport": "stdin",
        "returncode": 0,
        "prompt_digest": digest_text("prompt"),
        "stdout_digest": digest_text("stdout"),
        "stderr_digest": digest_text(""),
    }
    ignored = create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        log_path=log,
    )
    first = create_action_attestation(
        subject_kind="runtime_event",
        subject_ref="agent_invocation_receipt:first",
        subject_digest=digest_text("first"),
        producer="role.manager",
        action_type="agent_cli_dispatch",
        verification_status="verified",
        run_id="run_1",
        metadata={"agent_invocation_receipt": receipt},
        log_path=log,
    )
    second = create_action_attestation(
        subject_kind="runtime_event",
        subject_ref="agent_invocation_receipt:second",
        subject_digest=digest_text("second"),
        producer="role.manager",
        action_type="agent_cli_dispatch",
        verification_status="failed",
        run_id="run_2",
        metadata={
            "agent_invocation_receipt": {
                **receipt,
                "returncode": 2,
                "agent_session_id": "session-2",
            }
        },
        log_path=log,
    )

    assert agent_invocation_audit_row(ignored) is None
    rows = list_agent_invocation_audits(log_path=log)

    assert [row.attestation_id for row in rows] == [
        second.attestation_id,
        first.attestation_id,
    ]
    assert rows[0].verification_status == "failed"
    assert rows[0].returncode == 2
    assert rows[0].agent_session_id == "session-2"
    assert rows[1].runtime == "codex"
    assert [row.attestation_id for row in list_agent_invocation_audits(limit=1, log_path=log)] == [
        second.attestation_id
    ]


def test_action_attestation_cli_can_render_resource_envelopes(
    tmp_path: Path,
    capsys,
):
    log = tmp_path / "action_attestations.jsonl"
    attestation = create_action_attestation(
        subject_kind="artifact",
        subject_ref="artifact://claim-brief",
        subject_digest=digest_text("claim brief"),
        producer="role.analyst",
        action_type="write_artifact",
        verification_status="verified",
        log_path=log,
    )

    rc = action_attestation_main(["list", "--log-path", str(log), "--resource"])

    assert rc == 0
    output = capsys.readouterr().out
    assert '"kind": "ActionAttestation"' in output
    assert attestation.attestation_id in output
