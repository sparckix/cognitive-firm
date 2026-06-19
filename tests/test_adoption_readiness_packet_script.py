from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cognitive_firm.orchestration.governed_run_recipes import (
    AdoptionReadinessPacketInput,
    build_adoption_readiness_packet,
)


ROOT = Path(__file__).resolve().parents[1]


def test_adoption_readiness_packet_script_renders_markdown(tmp_path: Path) -> None:
    result_path = tmp_path / "kernel-service-smoke.json"
    result_path.write_text(
        json.dumps(
            {
                "ok": True,
                "governed_run_bundle_verdict": "passed",
                "mutation_proof_validated": True,
                "stale_rejected": True,
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "adoption-readiness.md"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/adoption_readiness_packet.py",
            "--target-label",
            "smoke-adopter",
            "--result",
            f"kernel_service_smoke={result_path}",
            "--include-live-agent",
            "--markdown",
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "# Adoption Readiness Packet" in result.stdout
    assert "smoke-adopter" in result.stdout
    assert "Reviewer Path" in result.stdout
    assert "Purpose: Verify the public gate" in result.stdout
    assert "Not a: command runner" in result.stdout
    assert "make adoption-readiness-packet" in result.stdout
    assert "this_packet" in result.stdout
    assert "Kernel service smoke" in result.stdout
    assert "Bounded live agent run" in result.stdout
    assert output_path.read_text(encoding="utf-8") == result.stdout


def test_adoption_readiness_packet_script_renders_latest_onramp_packet(
    tmp_path: Path,
) -> None:
    onramp_root = tmp_path / "adoption-onramp"
    run_dir = onramp_root / "99990101T000000Z"
    run_dir.mkdir(parents=True)
    packet = build_adoption_readiness_packet(
        AdoptionReadinessPacketInput(
            target_label="latest-onramp-adopter",
            observed_results={
                "kernel_service_smoke": {
                    "ok": True,
                    "governed_run_bundle_verdict": "passed",
                    "mutation_proof_validated": True,
                    "stale_rejected": True,
                    "governance_proposal_status": "review_ready",
                    "governance_decision": "approve",
                    "provenance_report_counts": {
                        "provenance_report_coverage": "partial",
                        "provenance_follow_through": "closed_loop_observed",
                        "provenance_outcome_links": 1,
                        "provenance_routine_reviews": 1,
                        "provenance_learning_events": 1,
                        "provenance_learning_use_receipts": 1,
                    },
                }
            },
            metadata={"collector": "scripts/adoption_onramp_packet.py"},
        )
    )
    packet["reviewer_path"]["steps"][2]["description"] = "stale stored copy"
    packet["markdown"] = "stale stored markdown"
    packet_path = run_dir / "adoption-readiness-packet.json"
    packet_path.write_text(
        json.dumps(packet, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/adoption_readiness_packet.py",
            "--latest-onramp",
            "--onramp-root",
            str(onramp_root),
            "--markdown",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "latest-onramp-adopter" in result.stdout
    assert "| Observed checks | 1 |" in result.stdout
    assert "Kernel service smoke" in result.stdout
    assert "stale stored copy" not in result.stdout
    assert "latest on-ramp handoff" in result.stdout


def test_adoption_readiness_packet_script_latest_onramp_falls_back(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/adoption_readiness_packet.py",
            "--latest-onramp",
            "--onramp-root",
            str(tmp_path / "missing-onramp"),
            "--markdown",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    assert "local_adopter" in result.stdout
    assert "| Observed checks | 0 |" in result.stdout
