from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from formal_provider_bundle_demo import main, run_demo  # noqa: E402


def test_formal_provider_bundle_demo_shows_trusted_and_caveated_paths(tmp_path: Path):
    payload = run_demo(tmp_path)

    assert payload["summary"]["verdict"] == "passed"
    trusted = payload["trusted_provider"]
    missing = payload["missing_provider_evidence"]

    assert trusted["bundle_verdict"] == "passed"
    assert trusted["bundle_caveats"] == []
    assert trusted["signature_verified"] is True
    assert trusted["formal_verifications"] == 1
    assert trusted["bundle_schema_valid"] is True

    assert missing["bundle_verdict"] == "incomplete"
    assert missing["formal_verifications"] == 1
    assert missing["bundle_schema_valid"] is True
    assert any("verified formal verifications with trust caveats" in item for item in missing["bundle_caveats"])
    assert any("provider_payload_signature" in item for item in missing["bundle_caveats"])
    assert any("faithfulness_refs" in item for item in missing["bundle_caveats"])


def test_formal_provider_bundle_demo_cli_compact(capsys):
    assert main([]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["demo"] == "formal_provider_bundle"
    assert payload["no_external_calls"] is True
    assert payload["summary"]["verdict"] == "passed"
    assert "log_paths" not in payload


def test_formal_provider_bundle_demo_cli_full_json_keeps_logs(tmp_path: Path, capsys):
    assert main(["--workdir", str(tmp_path), "--full-json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["summary"]["verdict"] == "passed"
    assert "log_paths" in payload
    for path in payload["log_paths"].values():
        assert Path(path).exists()
