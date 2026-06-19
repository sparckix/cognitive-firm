from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_formal_provider_proof_pack_script_emits_operator_receipt():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "formal_provider_proof_pack.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    packet = json.loads(result.stdout)

    assert packet["schema"] == "formal_provider_proof_pack.v1"
    assert packet["summary"]["ok"] is True
    assert packet["summary"]["trusted_bundle_verdict"] == "passed"
    assert packet["summary"]["missing_evidence_bundle_verdict"] == "incomplete"
    assert packet["boundary"]["checker_does_not_execute_provider"] is True
    assert any(
        check["check_id"] == "missing_evidence_falsifier_contract"
        and check["status"] == "passed"
        for check in packet["checks"]
    )
