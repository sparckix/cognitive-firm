from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_dry_run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "-n", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_primary_self_evolving_target_accepts_compare_feedback() -> None:
    result = _make_dry_run(
        "self-evolving-org",
        "SELF_EVOLVING_RUNTIME=fixture",
        "SELF_EVOLVING_FEEDBACK=compare",
    )

    assert result.returncode == 0
    assert "--compare-feedback" in result.stdout
    assert '--workload-feedback "compare"' not in result.stdout
    assert "self-evolving-org-compare-serve" in result.stdout
    assert "http.server" not in result.stdout


def test_primary_self_evolving_target_can_opt_into_serving() -> None:
    result = _make_dry_run(
        "self-evolving-org",
        "SELF_EVOLVING_RUNTIME=fixture",
        "SELF_EVOLVING_SERVE=1",
    )

    assert result.returncode == 0
    assert "http.server" in result.stdout


def test_single_arm_self_evolving_targets_reject_compare_feedback() -> None:
    result = _make_dry_run(
        "self-evolving-org-demo",
        "SELF_EVOLVING_FEEDBACK=compare",
    )

    assert result.returncode != 0
    assert "SELF_EVOLVING_FEEDBACK=compare is only supported" in result.stderr
    assert "--workload-feedback" not in result.stdout


def test_single_arm_self_evolving_targets_accept_withheld_feedback() -> None:
    result = _make_dry_run(
        "self-evolving-org-demo",
        "SELF_EVOLVING_FEEDBACK=withheld",
    )

    assert result.returncode == 0
    assert '--workload-feedback "withheld"' in result.stdout
