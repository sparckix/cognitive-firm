"""Console entrypoints for the public package."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_script(script: str, argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    script_path = REPO_ROOT / "scripts" / script
    if not script_path.exists():
        if any(arg in {"-h", "--help"} for arg in args):
            print(
                f"{script} is a checkout-level command. Run it from a source checkout, "
                "or use the importable kernel-service, actor-membership, and "
                "identity-provisioning entrypoints from an installed wheel."
            )
            return 0
        print(
            f"ERROR: {script} is not packaged in the installed wheel. "
            "Run this command from a source checkout.",
            file=sys.stderr,
        )
        return 2
    cmd = [sys.executable, str(script_path), *args]
    return subprocess.call(cmd, cwd=str(REPO_ROOT))


def run_daemon(argv: list[str] | None = None) -> int:
    return _run_script("agent_daemon.py", argv)


def run_preflight(argv: list[str] | None = None) -> int:
    return _run_script("org_role_preflight.py", argv)
