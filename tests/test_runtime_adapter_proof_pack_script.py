from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_adapter_proof_pack_script_builds_packet(tmp_path: Path) -> None:
    output_path = tmp_path / "runtime-adapter-proof-pack.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/runtime_adapter_proof_pack.py",
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert output_path.read_text(encoding="utf-8") == result.stdout
    assert payload["schema"] == "runtime_adapter_proof_pack.v1"
    assert payload["summary"]["ok"] is True
    assert payload["summary"]["native_demo"] == "native_cognitive_firm_e2e"
    assert payload["summary"]["runtime_demo"] == "langgraph_governance_projection"
    assert payload["runtime_boundary"]["external_runtime_owns"]
    assert payload["boundary"]["checker_does_not_install_adapter"] is True
