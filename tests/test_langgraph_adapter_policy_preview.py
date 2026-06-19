from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_script():
    script_path = ROOT / "scripts" / "langgraph_adapter_policy_preview.py"
    spec = importlib.util.spec_from_file_location(
        "langgraph_adapter_policy_preview",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_langgraph_adapter_policy_preview_payload_is_authority_neutral(tmp_path):
    module = _load_script()
    payload = module.build_preview_payload(
        "langgraph-runtime-adapter",
        target_root=tmp_path / "org",
    )

    assert payload["schema"] == "adapter_policy_preview.v1"
    assert payload["ok"] is True
    assert payload["installed_temp_starter"] is True
    assert payload["preview"]["status"] == "review_ready"
    assert payload["preview"]["can_proceed"] is True
    assert payload["preview"]["expands_authority"] is False
    assert payload["validation"] == {
        "authority_neutral": True,
        "expected_files_present": True,
        "package_manifest_issues": [],
        "starter_verify_issues": [],
    }
    assert payload["conformance_config"]["issues"] == []
    assert payload["adapter_manifest"]["adapter_id"] == "langgraph-runtime-adapter"
    assert payload["boundary"]["does_not_install_overlay"] is True
    assert payload["boundary"]["does_not_execute_runtime"] is True
    assert payload["boundary"]["does_not_widen_authority"] is True


def test_langgraph_adapter_policy_preview_make_target_writes_output(tmp_path: Path):
    output = tmp_path / "preview.json"

    result = subprocess.run(
        [
            "make",
            "-s",
            "langgraph-adapter-policy-preview",
            f"PYTHON=./.venv/bin/python",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["preview"]["expands_authority"] is False

    result_with_output = subprocess.run(
        [
            "./.venv/bin/python",
            "scripts/langgraph_adapter_policy_preview.py",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    stdout_payload = json.loads(result_with_output.stdout)
    file_payload = json.loads(output.read_text(encoding="utf-8"))
    assert file_payload == stdout_payload
    assert file_payload["ok"] is True
