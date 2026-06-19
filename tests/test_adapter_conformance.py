from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.adapter_conformance import (  # noqa: E402
    AdapterManifestError,
    RuntimeAdapterProofPackInput,
    build_runtime_adapter_proof_pack,
    load_adapter_conformance_config,
    load_adapter_manifest,
    main as adapter_conformance_main,
    run_adapter_conformance,
    validate_adapter_conformance_config_file,
)


def test_adapter_conformance_reports_pass_and_failure():
    report = run_adapter_conformance(
        adapter_id="fixture",
        family="identity_provider",
        checks={
            "authenticates_subject": lambda: True,
            "rejects_spoof": lambda: False,
        },
    )

    assert report.ok is False
    assert report.as_dict()["checks"][1]["check_id"] == "rejects_spoof"


def test_adapter_manifest_loads_yaml_without_running_executable(tmp_path: Path):
    manifest_path = tmp_path / "adapter.yaml"
    manifest_path.write_text(
        """\
schema_version: cognitive-firm-adapter-manifest/v1
adapter_id: langgraph-runtime-adapter
family: runtime
protocol: runtime_event
description: Maps LangGraph lifecycle callbacks into runtime event rows.
executable:
  kind: python_package
  ref: cognitive_firm_langgraph_adapter
  version: 0.1.0
  digest: sha256:abc123
  install_hint: Install the adapter in the same Python environment as LangGraph.
trust_requirements:
  conformance_fixture: required
conformance_checks:
  - started_event_idempotent
  - interrupt_creates_human_work
evidence_refs:
  - tests/test_runtime_adapters.py
"""
    )

    manifest = load_adapter_manifest(manifest_path)

    assert manifest.adapter_id == "langgraph-runtime-adapter"
    assert manifest.family == "runtime"
    assert manifest.protocol == "runtime_event"
    assert manifest.executable.kind == "python_package"
    assert manifest.executable.ref == "cognitive_firm_langgraph_adapter"
    assert manifest.conformance_checks == (
        "started_event_idempotent",
        "interrupt_creates_human_work",
    )


def test_adapter_manifest_rejects_unknown_family(tmp_path: Path):
    manifest_path = tmp_path / "adapter.yaml"
    manifest_path.write_text(
        """\
schema_version: cognitive-firm-adapter-manifest/v1
adapter_id: bad
family: generic_magic
protocol: runtime_event
description: This manifest declares an unsupported adapter family.
executable:
  kind: python_package
  ref: pkg
conformance_checks:
  - fixture
"""
    )

    try:
        load_adapter_manifest(manifest_path)
    except AdapterManifestError as exc:
        assert "family" in str(exc)
    else:
        raise AssertionError("expected invalid adapter family to be rejected")


def test_adapter_manifest_cli_validates_and_prints_json(tmp_path: Path, capsys):
    manifest_path = tmp_path / "adapter.json"
    manifest_path.write_text(
        """{
  "schema_version": "cognitive-firm-adapter-manifest/v1",
  "adapter_id": "leanmill-formal-verification",
  "family": "formal_verification_provider",
  "protocol": "formal_verification_provider_payload",
  "description": "LeanMill provider adapter declaration for governed evidence.",
  "executable": {
    "kind": "repository",
    "ref": "leanmill",
    "public_key_ref": "configure://leanmill-ed25519-public-key"
  },
  "trust_requirements": {
    "payload_signature": "required"
  },
  "conformance_checks": [
    "accepts_signed_verified_payload"
  ]
}
"""
    )

    assert adapter_conformance_main(["validate-manifest", str(manifest_path), "--json"]) == 0
    out = capsys.readouterr().out
    assert '"adapter_id": "leanmill-formal-verification"' in out


def test_adapter_manifest_cli_reports_invalid_manifest(tmp_path: Path, capsys):
    manifest_path = tmp_path / "adapter.yaml"
    manifest_path.write_text("schema_version: cognitive-firm-adapter-manifest/v1\n")

    assert adapter_conformance_main(["validate-manifest", str(manifest_path)]) == 1
    assert "executable must be a mapping" in capsys.readouterr().out


def test_adapter_conformance_config_aligns_with_manifest(tmp_path: Path):
    manifest_path = tmp_path / "adapter.yaml"
    manifest_path.write_text(
        """\
schema_version: cognitive-firm-adapter-manifest/v1
adapter_id: langgraph-runtime-adapter
family: runtime
protocol: runtime_event
description: Maps LangGraph lifecycle callbacks into runtime event rows.
executable:
  kind: python_package
  ref: cognitive_firm_langgraph_adapter
conformance_checks:
  - started_event_idempotent
  - interrupt_creates_human_work
"""
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_runtime_adapters.py").write_text("# fixture\n")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        """{
  "schema_version": "cognitive-firm-adapter-conformance/v1",
  "adapter_id": "langgraph-runtime-adapter",
  "protocol": "runtime_event",
  "fixture_command": "make langgraph-governance-demo",
  "required_checks": [
    {"check_id": "started_event_idempotent", "evidence": "tests/test_runtime_adapters.py"},
    {"check_id": "interrupt_creates_human_work", "evidence": "tests/test_runtime_adapters.py"}
  ]
}
"""
    )

    config = load_adapter_conformance_config(config_path)
    issues = validate_adapter_conformance_config_file(
        config_path,
        manifest_path=manifest_path,
        evidence_root=tmp_path,
    )

    assert config.adapter_id == "langgraph-runtime-adapter"
    assert issues == []


def test_adapter_conformance_config_reports_manifest_drift(tmp_path: Path):
    manifest_path = tmp_path / "adapter.yaml"
    manifest_path.write_text(
        """\
schema_version: cognitive-firm-adapter-manifest/v1
adapter_id: langgraph-runtime-adapter
family: runtime
protocol: runtime_event
description: Maps LangGraph lifecycle callbacks into runtime event rows.
executable:
  kind: python_package
  ref: cognitive_firm_langgraph_adapter
conformance_checks:
  - started_event_idempotent
  - interrupt_creates_human_work
"""
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        """{
  "schema_version": "cognitive-firm-adapter-conformance/v1",
  "adapter_id": "other-adapter",
  "protocol": "runtime_event",
  "fixture_command": "make langgraph-governance-demo",
  "required_checks": [
    {"check_id": "started_event_idempotent", "evidence": "tests/test_runtime_adapters.py"}
  ]
}
"""
    )

    issues = validate_adapter_conformance_config_file(
        config_path,
        manifest_path=manifest_path,
        evidence_root=tmp_path,
    )

    assert any("adapter_id mismatch" in issue for issue in issues)
    assert any("missing manifest checks" in issue for issue in issues)
    assert any("does not exist" in issue for issue in issues)


def test_adapter_conformance_cli_validates_config(capsys):
    manifest = ROOT / "distro" / "langgraph-runtime-adapter" / "files" / "adapters" / "langgraph-runtime-adapter.yaml"
    config = (
        ROOT
        / "distro"
        / "langgraph-runtime-adapter"
        / "files"
        / "adapter_conformance"
        / "langgraph-runtime-adapter.json"
    )

    assert adapter_conformance_main(
        [
            "validate-conformance",
            str(config),
            "--manifest",
            str(manifest),
            "--evidence-root",
            str(ROOT),
            "--json",
        ]
    ) == 0
    out = capsys.readouterr().out
    assert '"adapter_id": "langgraph-runtime-adapter"' in out


def test_runtime_adapter_proof_pack_compares_native_and_runtime_contracts():
    manifest = load_adapter_manifest(
        ROOT
        / "distro"
        / "langgraph-runtime-adapter"
        / "files"
        / "adapters"
        / "langgraph-runtime-adapter.yaml"
    )
    config = load_adapter_conformance_config(
        ROOT
        / "distro"
        / "langgraph-runtime-adapter"
        / "files"
        / "adapter_conformance"
        / "langgraph-runtime-adapter.json"
    )

    packet = build_runtime_adapter_proof_pack(
        RuntimeAdapterProofPackInput(
            adapter_id="langgraph-runtime-adapter",
            native_payload=_proof_payload("native_cognitive_firm_e2e", "native"),
            runtime_payload=_proof_payload(
                "langgraph_governance_projection",
                "runtime",
                include_runtime_projection=True,
            ),
            manifest=manifest,
            conformance_config=config,
        )
    )

    assert packet["schema"] == "runtime_adapter_proof_pack.v1"
    assert packet["summary"]["ok"] is True
    assert packet["boundary"]["checker_does_not_execute_runtime"] is True
    assert "same governed-run contract" in " ".join(packet["isomorphism_takeaways"])


def test_runtime_adapter_proof_pack_blocks_missing_runtime_resume_ref():
    manifest = load_adapter_manifest(
        ROOT
        / "distro"
        / "langgraph-runtime-adapter"
        / "files"
        / "adapters"
        / "langgraph-runtime-adapter.yaml"
    )
    config = load_adapter_conformance_config(
        ROOT
        / "distro"
        / "langgraph-runtime-adapter"
        / "files"
        / "adapter_conformance"
        / "langgraph-runtime-adapter.json"
    )
    runtime_payload = _proof_payload(
        "langgraph_governance_projection",
        "runtime",
        include_runtime_projection=True,
    )
    del runtime_payload["run_projection"]["runtime_projection"]["resume_ref"]

    packet = build_runtime_adapter_proof_pack(
        RuntimeAdapterProofPackInput(
            adapter_id="langgraph-runtime-adapter",
            native_payload=_proof_payload("native_cognitive_firm_e2e", "native"),
            runtime_payload=runtime_payload,
            manifest=manifest,
            conformance_config=config,
        )
    )

    assert packet["summary"]["ok"] is False
    failing = {
        check["check_id"]: check
        for check in packet["checks"]
        if check["status"] != "passed"
    }
    assert "runtime_projection_keeps_runtime_owned_refs" in failing
    assert any("resume_ref" in error for error in failing["runtime_projection_keeps_runtime_owned_refs"]["errors"])


def _proof_payload(
    demo: str,
    suffix: str,
    *,
    include_runtime_projection: bool = False,
) -> dict:
    run_id = f"run_{suffix}"
    payload = {
        "demo": demo,
        "bundle_validation": {"ok": True, "errors": []},
        "summary": {
            "authority_snapshot": {
                "mandate_hash": f"hash_{suffix}",
                "mandate_ref": f"org/mandates/{suffix}.md",
                "owner_role": f"role.{suffix}",
                "role_ref": f"org/roles/{suffix}.yaml",
                "status": "resolved",
            },
            "bundle_digest": "sha256:" + "a" * 64,
            "bundle_id": f"gab_{suffix}",
            "caveats": [],
            "counts": {
                "accountability_cases": 1,
                "action_attestations": 1,
                "approval_events": 0,
                "checkpoints": 1,
                "evidence_hashes": 1,
                "formal_verifications": 0,
                "human_work_sessions": 1,
                "leases": 0,
                "observability_refs": 1,
                "outcome_links": 1,
                "work_items": 0,
            },
            "ids": {
                "accountability_cases": [f"acct_{suffix}"],
                "action_attestations": [f"aat_{suffix}"],
                "approval_events": [],
                "evidence_hashes": [f"record_set_digest:run:{run_id}"],
                "formal_verifications": [],
                "human_work_sessions": [f"hws_{suffix}"],
                "leases": [],
                "observability_refs": [f"cognitive_firm.run:{run_id}"],
                "outcome_links": [f"olink_{suffix}"],
                "work_items": [],
            },
            "objective": f"prove {suffix}",
            "owner_role": f"role.{suffix}",
            "project_id": f"project-{suffix}",
            "run_id": run_id,
            "run_state": "completed",
            "tenant_id": f"tenant-{suffix}",
            "verdict": "passed",
        },
    }
    if include_runtime_projection:
        payload["run_projection"] = {
            "state": "completed",
            "runtime_projection": {
                "runtime_name": "langgraph",
                "external_run_id": "thread-proof",
                "resume_ref": "langgraph://thread-proof/resume/approval-1",
                "evidence_refs": [
                    f"run:{run_id}",
                    f"human_work:hws_{suffix}",
                    f"outcome_link:olink_{suffix}",
                ],
            },
        }
    return payload
