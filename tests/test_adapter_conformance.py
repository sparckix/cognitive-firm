from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.adapter_conformance import (  # noqa: E402
    AdapterManifestError,
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
