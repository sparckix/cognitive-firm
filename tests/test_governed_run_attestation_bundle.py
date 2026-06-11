from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_attestation import (  # noqa: E402
    create_action_attestation,
    digest_text,
)
from cognitive_firm.distribution.signing import generate_keypair  # noqa: E402
from cognitive_firm.orchestration.accountability_cases import (  # noqa: E402
    create_accountability_case,
    update_accountability_case_status,
)
from cognitive_firm.orchestration.artifact_bundle import (  # noqa: E402
    GOVERNED_RUN_BUNDLE_SCHEMA_PATH,
    build_authority_snapshot,
    build_governed_run_attestation_bundle,
    governed_run_bundle_to_dict,
    governed_run_bundle_summary,
    main as artifact_bundle_main,
    validate_governed_run_bundle_payload,
)
from cognitive_firm.orchestration.outcome_links import (  # noqa: E402
    create_outcome_link,
    record_metric_snapshot,
    record_verdict,
)
from cognitive_firm.orchestration.formal_verification import (  # noqa: E402
    FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
    FORMAL_VERIFICATION_TRUST_POLICY_VERSION,
    TRUSTED_FORMAL_VERIFICATION_PROVIDERS_RELATIVE_PATH,
    create_formal_verification,
    create_formal_verification_from_provider_payload,
    sign_provider_payload,
)
from cognitive_firm.orchestration.actor_identity import ActorContext  # noqa: E402
from cognitive_firm.orchestration.leases import acquire_lease  # noqa: E402
from cognitive_firm.orchestration.kernel_events import record_kernel_event  # noqa: E402
from cognitive_firm.orchestration.runtime_adapters import RuntimeEvent, record_runtime_event  # noqa: E402
from cognitive_firm.orchestration.operating_units import define_operating_unit  # noqa: E402
from cognitive_firm.orchestration.work_items import (  # noqa: E402
    claim_next_work_item,
    complete_work_item,
    enqueue_work_item,
    fail_work_item,
)


def _start_run(log: Path, external_run_id: str = "thread-1") -> str:
    result = record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id=external_run_id,
            kind="started",
            owner_role="role.manager",
            actor="role.manager",
            objective="run governed graph",
            tenant_id="tenant-demo",
            project_id="project-demo",
        ),
        log_path=log,
    )
    return str(result["cognitive_run_id"])


def _write_trusted_provider_policy(
    authority_root: Path,
    *,
    provider: str,
    public_key_pem: str | None = None,
    requires_payload_signature: bool = False,
    requires_reverification_refs: bool = False,
    requires_faithfulness_refs: bool = False,
) -> None:
    path = authority_root / TRUSTED_FORMAL_VERIFICATION_PROVIDERS_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": FORMAL_VERIFICATION_TRUST_POLICY_VERSION,
                "trusted_providers": [
                    {
                        "provider": provider,
                        "trust_basis": "test policy",
                        **(
                            {"public_key_pem": public_key_pem}
                            if public_key_pem is not None
                            else {}
                        ),
                        "requires_payload_signature": requires_payload_signature,
                        "requires_reverification_refs": requires_reverification_refs,
                        "requires_faithfulness_refs": requires_faithfulness_refs,
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_governed_run_attestation_bundle_passes_completed_verified_run(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    run_id = _start_run(transition_log)

    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-1",
            kind="checkpointed",
            owner_role="role.manager",
            actor="role.manager",
            step_id="source-check",
            checkpoint_status="completed",
            summary="checked source packet",
            payload_ref="workspace/source.md",
        ),
        log_path=transition_log,
    )
    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        verification_summary="digest and source refs checked",
        run_id=run_id,
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-1",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
    )

    assert bundle.verdict == "passed"
    assert bundle.caveats == []
    assert bundle.run["tenant_id"] == "tenant-demo"
    assert bundle.action_attestations[0]["verification_status"] == "verified"
    assert bundle.bundle_digest.startswith("sha256:")


def test_governed_run_bundle_payload_validates_against_schema_and_digest(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-schema")

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        run_id=run_id,
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-schema",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
    )
    payload = governed_run_bundle_to_dict(bundle)

    assert validate_governed_run_bundle_payload(payload) == []
    assert validate_governed_run_bundle_payload(
        payload,
        schema_path=GOVERNED_RUN_BUNDLE_SCHEMA_PATH,
    ) == []

    tampered = dict(payload)
    tampered["verdict"] = "incomplete"
    errors = validate_governed_run_bundle_payload(tampered)

    assert any("bundle_digest mismatch" in error for error in errors)


def test_governed_run_bundle_exports_evidence_hashes(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    org = tmp_path / "org"
    roles = org / "roles"
    mandates = org / "mandates"
    roles.mkdir(parents=True)
    mandates.mkdir(parents=True)
    (roles / "manager.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "role_id: manager",
                "authorized_paths:",
                "  - workspace/",
                "forbidden_paths: []",
                "delegates_to: []",
                "escalates_to:",
                "  - role.principal",
                "mandate_path: org/mandates/manager_mandate.md",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (mandates / "manager_mandate.md").write_text(
        "Manager may build a bounded evidence packet.\n",
        encoding="utf-8",
    )
    run_id = _start_run(transition_log, external_run_id="thread-evidence-hash")
    input_digest = digest_text("input-state")
    subject_digest = digest_text("report")

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=subject_digest,
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        input_refs=[input_digest],
        run_id=run_id,
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-evidence-hash",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        authority_root=tmp_path,
    )
    payload = governed_run_bundle_to_dict(bundle)
    hashes = bundle.evidence_hashes

    assert validate_governed_run_bundle_payload(payload) == []
    assert any(
        row["kind"] == "record_set_digest" and row["source"] == "run"
        for row in hashes
    )
    assert any(
        row["kind"] == "subject_digest"
        and row["ref"] == "workspace/report.md"
        and row["digest"] == subject_digest
        for row in hashes
    )
    assert any(
        row["kind"] == "input_output_ref_digest" and row["digest"] == input_digest
        for row in hashes
    )
    assert any(
        row["kind"] == "authority_contract_digest"
        and row["ref"] == "org/roles/manager.yaml"
        and row["digest"].startswith("sha256:")
        for row in hashes
    )
    assert any(
        row["kind"] == "authority_contract_hash"
        and row["algorithm"] == "cognitive_firm_mandate_hash"
        for row in hashes
    )
    assert governed_run_bundle_summary(bundle)["counts"]["evidence_hashes"] == len(hashes)


def test_governed_run_bundle_cli_validates_existing_json(tmp_path: Path, capsys):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    bundle_path = tmp_path / "bundle.json"
    run_id = _start_run(transition_log, external_run_id="thread-cli-validate")

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        run_id=run_id,
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-cli-validate",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )
    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
    )
    bundle_path.write_text(
        json.dumps(governed_run_bundle_to_dict(bundle), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    assert artifact_bundle_main(["--validate-json", str(bundle_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"errors": [], "ok": True}


def test_governed_run_attestation_bundle_exports_observability_refs(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-observe")

    checkpoint = record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-observe",
            kind="checkpointed",
            owner_role="role.manager",
            actor="role.manager",
            step_id="verify-claim",
            checkpoint_status="completed",
            summary="checked claim evidence",
            payload_ref="workspace/evidence.json",
            side_effect_key="claim-check:1",
        ),
        log_path=transition_log,
    )
    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        runtime_ref="runtime:langgraph:thread-observe",
        verification_status="verified",
        run_id=run_id,
        metadata={"trace_id": "trace-abc", "span_ids": ["span-1", "span-2"]},
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-observe",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
    )
    summary = governed_run_bundle_summary(bundle)
    refs = {row["ref"] for row in bundle.observability_refs}

    assert bundle.verdict == "passed"
    assert f"cognitive_firm.run:{run_id}" in refs
    assert checkpoint["event_id"] in refs
    assert "workspace/evidence.json" in refs
    assert "claim-check:1" in refs
    assert "runtime:langgraph:thread-observe" in refs
    assert {"trace-abc", "span-1", "span-2"} <= refs
    assert summary["counts"]["observability_refs"] == len(bundle.observability_refs)


def _define_execution_unit(log_path: Path) -> None:
    define_operating_unit(
        unit_id="execution_lane",
        unit_kind="production_lane",
        display_name="Execution Lane",
        owner_role="role.manager",
        allowed_work_kinds=["evidence_pack"],
        allowed_exits=["pack_ready"],
        worker_roles=["role.manager"],
        log_path=log_path,
    )


def test_governed_run_bundle_includes_linked_completed_work_items(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    units_log = tmp_path / "operating_units.jsonl"
    work_log = tmp_path / "work_items.jsonl"
    _define_execution_unit(units_log)
    work = enqueue_work_item(
        unit_id="execution_lane",
        kind="evidence_pack",
        log_path=work_log,
        operating_units_log=units_log,
    )
    claimed = claim_next_work_item(
        unit_id="execution_lane",
        actor="actor.manager",
        role_id="role.manager",
        log_path=work_log,
        operating_units_log=units_log,
    )
    assert claimed is not None

    run_id = _start_run(transition_log, external_run_id="thread-work-item")
    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        input_refs=[f"work_item:{work.work_id}"],
        run_id=run_id,
        log_path=attestation_log,
    )
    complete_work_item(
        claimed.work_id,
        actor="actor.manager",
        claim_token=claimed.claim_token,
        exit_kind="pack_ready",
        producer="role.manager",
        verifier="role.reviewer",
        artifact_refs=[{"kind": "run", "path": run_id}],
        log_path=work_log,
        operating_units_log=units_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-work-item",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        work_items_log_path=work_log,
    )
    summary = governed_run_bundle_summary(bundle)

    assert bundle.verdict == "passed"
    assert bundle.work_items[0]["work_id"] == work.work_id
    assert bundle.work_items[0]["status"] == "done"
    assert summary["counts"]["work_items"] == 1
    assert summary["ids"]["work_items"] == [work.work_id]


def test_governed_run_bundle_caveats_missing_referenced_work_item(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-missing-work-item")
    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        input_refs=["work_item:work_missing"],
        run_id=run_id,
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-missing-work-item",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        work_items_log_path=tmp_path / "work_items.jsonl",
    )

    assert bundle.verdict == "incomplete"
    assert any("referenced work items not found: work_missing" in item for item in bundle.caveats)


def test_governed_run_bundle_fails_when_linked_work_item_failed(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    units_log = tmp_path / "operating_units.jsonl"
    work_log = tmp_path / "work_items.jsonl"
    _define_execution_unit(units_log)
    work = enqueue_work_item(
        unit_id="execution_lane",
        kind="evidence_pack",
        metadata={"cognitive_run_id": "will-be-replaced"},
        log_path=work_log,
        operating_units_log=units_log,
    )
    claimed = claim_next_work_item(
        unit_id="execution_lane",
        actor="actor.manager",
        role_id="role.manager",
        log_path=work_log,
        operating_units_log=units_log,
    )
    assert claimed is not None

    run_id = _start_run(transition_log, external_run_id="thread-failed-work-item")
    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        metadata={"work_id": work.work_id},
        run_id=run_id,
        log_path=attestation_log,
    )
    fail_work_item(
        claimed.work_id,
        actor="actor.manager",
        claim_token=claimed.claim_token,
        reason="worker failed the production task",
        retryable=False,
        log_path=work_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-failed-work-item",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        work_items_log_path=work_log,
    )

    assert bundle.verdict == "failed"
    assert any(f"failed work items: {work.work_id}" in item for item in bundle.caveats)


def test_authority_snapshot_hashes_role_and_mandate_files(tmp_path: Path):
    org = tmp_path / "org"
    roles = org / "roles"
    mandates = org / "mandates"
    roles.mkdir(parents=True)
    mandates.mkdir(parents=True)
    (roles / "manager.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "role_id: manager",
                "authorized_paths:",
                "  - docs/",
                "forbidden_paths:",
                "  - secrets/",
                "delegates_to: []",
                "escalates_to:",
                "  - role.principal",
                "mandate_path: org/mandates/manager_mandate.md",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (mandates / "manager_mandate.md").write_text(
        "Manager may update docs and must not read secrets.\n",
        encoding="utf-8",
    )

    snapshot = build_authority_snapshot("role.manager", authority_root=tmp_path)

    assert snapshot["status"] == "resolved"
    assert snapshot["role_ref"] == "org/roles/manager.yaml"
    assert snapshot["mandate_ref"] == "org/mandates/manager_mandate.md"
    assert snapshot["role_digest"].startswith("sha256:")
    assert snapshot["mandate_digest"].startswith("sha256:")
    assert len(snapshot["mandate_hash"]) == 16


def test_authority_snapshot_reports_missing_synthetic_role_without_caveat(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-synthetic-role")

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.analyst",
        action_type="write_artifact",
        verification_status="verified",
        run_id=run_id,
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-synthetic-role",
            kind="state_changed",
            owner_role="role.analyst",
            actor="role.analyst",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        authority_root=tmp_path,
    )

    assert bundle.verdict == "passed"
    assert bundle.caveats == []
    assert bundle.authority_snapshot["status"] == "role_missing"


def test_governed_run_attestation_bundle_joins_linked_lease_evidence(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    leases_log = tmp_path / "leases.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-lease")
    actor = ActorContext(actor_id="actor.manager", actor_kind="service", role_id="role.manager")
    lease = acquire_lease(
        resource_ref="human_work:hws_review",
        actor=actor,
        ttl_seconds=300,
        purpose="integrate governed-run review",
        metadata={"cognitive_run_id": run_id},
        log_path=leases_log,
    )

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        run_id=run_id,
        metadata={"lease_id": lease.lease_id},
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-lease",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        leases_log_path=leases_log,
    )
    summary = governed_run_bundle_summary(bundle)

    assert bundle.verdict == "passed"
    assert bundle.leases[0]["lease_id"] == lease.lease_id
    assert summary["counts"]["leases"] == 1
    assert summary["ids"]["leases"] == [lease.lease_id]


def test_governed_run_attestation_bundle_flags_missing_referenced_lease(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    leases_log = tmp_path / "leases.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-missing-lease")

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        run_id=run_id,
        metadata={"lease_id": "lease_missing"},
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-missing-lease",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        leases_log_path=leases_log,
    )

    assert bundle.verdict == "incomplete"
    assert bundle.leases == []
    assert "referenced leases not found: lease_missing" in bundle.caveats


def test_governed_run_attestation_bundle_joins_governance_approval_event(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-approval")
    approval = record_kernel_event(
        actor="human.lead",
        verb="governance_change.approved",
        object_ref="governance_change:gcp_review_gate",
        payload={"reason": "reviewed", "cognitive_run_id": run_id},
        log_path=transition_log,
    )

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        run_id=run_id,
        metadata={"approval_ref": "governance_change:gcp_review_gate"},
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-approval",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
    )
    summary = governed_run_bundle_summary(bundle)

    assert bundle.verdict == "passed"
    assert bundle.approval_events[0]["event_id"] == approval.event_id
    assert summary["counts"]["approval_events"] == 1
    assert summary["ids"]["approval_events"] == [approval.event_id]


def test_governed_run_attestation_bundle_flags_missing_governance_approval(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-missing-approval")

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        run_id=run_id,
        metadata={"approval_ref": "governance_change:gcp_missing"},
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-missing-approval",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
    )

    assert bundle.verdict == "incomplete"
    assert bundle.approval_events == []
    assert (
        "referenced governance approvals not found: governance_change:gcp_missing"
        in bundle.caveats
    )


def test_governed_run_attestation_bundle_reports_incomplete_evidence(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    human_work_log = tmp_path / "human_work.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-hitl")

    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-hitl",
            kind="interrupted",
            owner_role="role.manager",
            actor="role.manager",
            interrupt_id="approval-1",
            interrupt_summary="Approve external write before resume",
            human_actor="human.reviewer",
            human_deliverable="approval note or rejection rationale",
            resume_ref="langgraph://thread-hitl/resume/approval-1",
        ),
        log_path=transition_log,
        human_work_log_path=human_work_log,
    )
    create_action_attestation(
        subject_kind="tool_call",
        subject_ref="linear:create_issue:1",
        subject_digest=digest_text("payload"),
        producer="role.manager",
        action_type="external_tool_call",
        verification_status="unverified",
        run_id=run_id,
        log_path=attestation_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        human_work_log_path=human_work_log,
    )
    rendered = governed_run_bundle_to_dict(bundle)

    assert rendered["verdict"] == "incomplete"
    assert any("unverified action attestations" in caveat for caveat in bundle.caveats)
    assert any("human-work sessions missing receipts" in caveat for caveat in bundle.caveats)
    assert bundle.human_work_sessions[0]["metadata"]["interrupt_id"] == "approval-1"


def test_governed_run_attestation_bundle_fails_failed_attestation(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-fail")

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="failed",
        verification_summary="digest mismatch",
        run_id=run_id,
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-fail",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
    )

    assert bundle.verdict == "failed"
    assert any("failed action attestations" in caveat for caveat in bundle.caveats)


def test_governed_run_attestation_bundle_joins_outcomes_and_accountability(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    outcome_log = tmp_path / "outcome_links.jsonl"
    accountability_log = tmp_path / "accountability_cases.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-evidence")

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        verification_summary="digest and source refs checked",
        run_id=run_id,
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-evidence",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    outcome = create_outcome_link(
        change_ref=f"run:{run_id}",
        change_kind="governed_run",
        metric_name="rework_rate",
        metric_unit="ratio",
        created_by="role.manager",
        tenant_id="tenant-demo",
        project_id="project-demo",
        metadata={"cognitive_run_id": run_id},
        log_path=outcome_log,
        kernel_events_log=transition_log,
    )
    record_metric_snapshot(
        outcome.outcome_link_id,
        kind="baseline",
        value=0.3,
        captured_by="role.manager",
        log_path=outcome_log,
        kernel_events_log=transition_log,
    )
    record_metric_snapshot(
        outcome.outcome_link_id,
        kind="post",
        value=0.1,
        captured_by="role.manager",
        log_path=outcome_log,
        kernel_events_log=transition_log,
    )
    record_verdict(
        outcome.outcome_link_id,
        verdict="improved",
        recorded_by="role.manager",
        rationale="post-pilot rework fell under the tenant metric",
        log_path=outcome_log,
        kernel_events_log=transition_log,
    )
    case = create_accountability_case(
        trigger_ref=f"run:{run_id}",
        accountable_role="role.manager",
        responsible_actor="role.manager",
        decision_right_basis="mandate",
        authority_envelope_ref="org/mandates/manager.yaml",
        risk_tier="medium",
        recourse_path="reopen",
        tenant_id="tenant-demo",
        project_id="project-demo",
        metadata={"cognitive_run_id": run_id},
        log_path=accountability_log,
    )
    update_accountability_case_status(
        case.case_id,
        "closed",
        closure_evidence_refs=[f"run:{run_id}", f"outcome_link:{outcome.outcome_link_id}"],
        log_path=accountability_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        outcome_links_log_path=outcome_log,
        accountability_cases_log_path=accountability_log,
    )

    assert bundle.verdict == "passed"
    assert bundle.caveats == []
    assert bundle.outcome_links[0]["verdict"] == "improved"
    assert bundle.accountability_cases[0]["status"] == "closed"

    summary = governed_run_bundle_summary(bundle)
    assert summary["verdict"] == "passed"
    assert summary["counts"]["action_attestations"] == 1
    assert summary["counts"]["outcome_links"] == 1
    assert summary["counts"]["accountability_cases"] == 1
    assert summary["ids"]["outcome_links"] == [outcome.outcome_link_id]


def test_governed_run_attestation_bundle_flags_unresolved_outcome_and_case(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    outcome_log = tmp_path / "outcome_links.jsonl"
    accountability_log = tmp_path / "accountability_cases.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-open-evidence")

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        run_id=run_id,
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-open-evidence",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )
    outcome = create_outcome_link(
        change_ref=f"run:{run_id}",
        change_kind="governed_run",
        metric_name="cycle_time",
        metric_unit="hours",
        created_by="role.manager",
        metadata={"cognitive_run_id": run_id},
        log_path=outcome_log,
        kernel_events_log=transition_log,
    )
    case = create_accountability_case(
        trigger_ref=f"run:{run_id}",
        accountable_role="role.manager",
        responsible_actor="role.manager",
        decision_right_basis="mandate",
        authority_envelope_ref="org/mandates/manager.yaml",
        risk_tier="medium",
        recourse_path="reopen",
        metadata={"cognitive_run_id": run_id},
        log_path=accountability_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        outcome_links_log_path=outcome_log,
        accountability_cases_log_path=accountability_log,
    )

    assert bundle.verdict == "incomplete"
    assert any(outcome.outcome_link_id in caveat for caveat in bundle.caveats)
    assert any(case.case_id in caveat for caveat in bundle.caveats)


def test_governed_run_attestation_bundle_joins_formal_verification(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    formal_log = tmp_path / "formal_verifications.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-formal")

    create_formal_verification(
        formal_system="lean",
        verifier_ref="lean:4.30.0",
        property_class="policy",
        subject_ref="policy://basel/cet1",
        subject_digest=digest_text("basel policy"),
        claim_ref="claim://basel/cet1-threshold",
        certificate_ref="proofs/basel_threshold.lean#adequate_iff",
        certificate_digest=digest_text("proof"),
        verdict="verified",
        verification_summary="Lean certificate checked labelled boundary cases.",
        run_id=run_id,
        log_path=formal_log,
        action_attestation_log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-formal",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        formal_verification_log_path=formal_log,
    )

    assert bundle.verdict == "passed"
    assert bundle.caveats == []
    assert bundle.formal_verifications[0]["formal_system"] == "lean"
    assert bundle.formal_verifications[0]["verdict"] == "verified"
    assert governed_run_bundle_summary(bundle)["counts"]["formal_verifications"] == 1


def test_governed_run_attestation_bundle_trusts_installed_leanmill_provider_policy(
    tmp_path: Path,
):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    formal_log = tmp_path / "formal_verifications.jsonl"
    authority_root = tmp_path / "org"
    keypair = generate_keypair()
    _write_trusted_provider_policy(
        authority_root,
        provider="leanmill",
        public_key_pem=keypair.public_pem,
        requires_payload_signature=True,
        requires_reverification_refs=True,
        requires_faithfulness_refs=True,
    )
    run_id = _start_run(transition_log, external_run_id="thread-leanmill-default")

    provider_payload = {
        "schema_version": FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
        "provider": "leanmill",
        "formal_system": "lean",
        "verifier_ref": "leanmill:certify-demo@abc123",
        "property_class": "workflow_safety",
        "subject_ref": "workflow://release",
        "subject_digest": digest_text("workflow"),
        "claim_ref": "claim://review-before-release",
        "certificate_ref": "leanmill://certificates/review-before-release",
        "certificate_digest": digest_text("leanmill certificate"),
        "verdict": "verified",
        "verification_summary": "LeanMill emitted a checked workflow invariant.",
        "faithfulness_refs": ["leanmill://faithfulness/review-before-release"],
        "checker_evidence_refs": ["leanmill://kernel-log/review-before-release"],
        "metadata": {},
        "run_id": run_id,
    }
    provider_payload["metadata"] = {
        "provider_payload_signature": sign_provider_payload(
            provider_payload,
            private_key_pem=keypair.private_pem,
        )
    }

    create_formal_verification_from_provider_payload(
        provider_payload,
        log_path=formal_log,
        action_attestation_log_path=attestation_log,
        authority_root=authority_root,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-leanmill-default",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        formal_verification_log_path=formal_log,
        authority_root=authority_root,
    )

    assert bundle.verdict == "passed"
    assert bundle.caveats == []
    assert bundle.formal_verifications[0]["metadata"]["provider"] == "leanmill"


def test_governed_run_attestation_bundle_caveats_missing_trusted_provider_evidence(
    tmp_path: Path,
):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    formal_log = tmp_path / "formal_verifications.jsonl"
    authority_root = tmp_path / "org"
    _write_trusted_provider_policy(
        authority_root,
        provider="leanmill",
        requires_payload_signature=True,
        requires_reverification_refs=True,
        requires_faithfulness_refs=True,
    )
    run_id = _start_run(transition_log, external_run_id="thread-leanmill-missing")

    record = create_formal_verification_from_provider_payload(
        {
            "schema_version": FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
            "provider": "leanmill",
            "formal_system": "lean",
            "verifier_ref": "leanmill:certify-demo@abc123",
            "property_class": "workflow_safety",
            "subject_ref": "workflow://release",
            "subject_digest": digest_text("workflow"),
            "claim_ref": "claim://review-before-release",
            "certificate_ref": "leanmill://certificates/review-before-release",
            "certificate_digest": digest_text("leanmill certificate"),
            "verdict": "verified",
            "verification_summary": "LeanMill emitted a checked workflow invariant.",
            "run_id": run_id,
        },
        log_path=formal_log,
        action_attestation_log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-leanmill-missing",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        formal_verification_log_path=formal_log,
        authority_root=authority_root,
    )

    assert bundle.verdict == "incomplete"
    assert (
        "verified formal verifications with trust caveats: "
        + record.verification_id
        + " missing trusted-provider evidence: provider_payload_signature, "
        + "trusted_provider_public_key, provider_payload_signature_verified, "
        + "checker_evidence_refs, faithfulness_refs"
    ) in bundle.caveats


def test_governed_run_attestation_bundle_caveats_untrusted_verified_provider(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    formal_log = tmp_path / "formal_verifications.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-untrusted-formal")

    record = create_formal_verification_from_provider_payload(
        {
            "schema_version": FORMAL_VERIFICATION_PROVIDER_SCHEMA_VERSION,
            "provider": "alloy-adapter",
            "formal_system": "alloy",
            "verifier_ref": "alloy:6.1",
            "property_class": "schema",
            "subject_ref": "schema://order",
            "subject_digest": digest_text("order schema"),
            "claim_ref": "claim://order-transition-total",
            "certificate_ref": "alloy://instances/order-transition-total",
            "certificate_digest": digest_text("alloy certificate"),
            "verdict": "verified",
            "verification_summary": "Provider emitted a checked schema invariant.",
            "run_id": run_id,
        },
        log_path=formal_log,
        action_attestation_log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-untrusted-formal",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        formal_verification_log_path=formal_log,
    )

    assert bundle.verdict == "incomplete"
    assert (
        "verified formal verifications with trust caveats: "
        + record.verification_id
        + " provider 'alloy-adapter' is not trusted"
    ) in bundle.caveats

    trusted_bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        formal_verification_log_path=formal_log,
        trusted_formal_verification_providers={"alloy-adapter"},
    )

    assert trusted_bundle.verdict == "passed"
    assert trusted_bundle.caveats == []


def test_governed_run_attestation_bundle_fails_refuted_formal_verification(tmp_path: Path):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    formal_log = tmp_path / "formal_verifications.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-formal-refuted")

    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-formal-refuted",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )
    record = create_formal_verification(
        formal_system="smt",
        verifier_ref="z3:fixture",
        property_class="workflow_safety",
        subject_ref="workflow://release",
        subject_digest=digest_text("workflow"),
        claim_ref="claim://review-before-release",
        certificate_ref="z3://counterexample/review-before-release",
        certificate_digest=digest_text("counterexample"),
        verdict="refuted",
        verification_summary="Counterexample found.",
        counterexample_ref="z3://model/1",
        run_id=run_id,
        log_path=formal_log,
        action_attestation_log_path=attestation_log,
    )

    bundle = build_governed_run_attestation_bundle(
        run_id,
        transition_log_path=transition_log,
        action_attestation_log_path=attestation_log,
        formal_verification_log_path=formal_log,
    )

    assert bundle.verdict == "failed"
    assert any(record.verification_id in caveat for caveat in bundle.caveats)
    assert any("failed formal verifications" in caveat for caveat in bundle.caveats)


def test_governed_run_attestation_bundle_cli_exports_json(tmp_path: Path, capsys):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-cli")

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        run_id=run_id,
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-cli",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    rc = artifact_bundle_main(
        [
            run_id,
            "--transition-log-path",
            str(transition_log),
            "--action-attestation-log-path",
            str(attestation_log),
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert rendered["bundle_id"] == f"gab_{run_id}"
    assert rendered["verdict"] == "passed"
    assert rendered["caveats"] == []


def test_governed_run_attestation_bundle_cli_exports_summary(tmp_path: Path, capsys):
    transition_log = tmp_path / "transitions.jsonl"
    attestation_log = tmp_path / "action_attestations.jsonl"
    run_id = _start_run(transition_log, external_run_id="thread-cli-summary")

    create_action_attestation(
        subject_kind="artifact",
        subject_ref="workspace/report.md",
        subject_digest=digest_text("report"),
        producer="role.manager",
        action_type="write_artifact",
        verification_status="verified",
        run_id=run_id,
        log_path=attestation_log,
    )
    record_runtime_event(
        RuntimeEvent(
            runtime_name="langgraph",
            external_run_id="thread-cli-summary",
            kind="state_changed",
            owner_role="role.manager",
            actor="role.manager",
            state="completed",
        ),
        log_path=transition_log,
    )

    rc = artifact_bundle_main(
        [
            run_id,
            "--transition-log-path",
            str(transition_log),
            "--action-attestation-log-path",
            str(attestation_log),
            "--summary",
        ]
    )

    rendered = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert rendered["bundle_id"] == f"gab_{run_id}"
    assert rendered["verdict"] == "passed"
    assert rendered["counts"]["action_attestations"] == 1
    assert "action_attestations" in rendered["ids"]
    assert "action_attestations" not in rendered
