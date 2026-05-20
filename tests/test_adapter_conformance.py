from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.adapter_conformance import run_adapter_conformance  # noqa: E402


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
