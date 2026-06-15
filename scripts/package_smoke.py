#!/usr/bin/env python3
"""Build a local wheel and inspect its public entry points."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import tomllib
import venv
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject.get("project", {}).get("scripts", {})
    baseline_required = {
        "cognitive-firm-kernel-service",
        "cognitive-firm-actor-membership",
        "cognitive-firm-identity-provisioning",
        "cognitive-firm-userland",
        "cognitive-firm-governed-run-bundle",
        "cognitive-firm-formal-verification",
        "cognitive-firm-adapter-conformance",
        "cognitive-firm-authority-domains",
        "cognitive-firm-action-impact",
        "cognitive-firm-multi-agent-traces",
        "cognitive-firm-phase-execution",
        "cognitive-firm-protocol-experiments",
        "cognitive-firm-capability-signals",
        "cognitive-firm-distro",
    }
    required = set(scripts)
    missing_scripts = sorted(baseline_required - required)
    if missing_scripts:
        raise SystemExit(f"missing console entry points in pyproject.toml: {missing_scripts}")
    if not (ROOT / "src" / "cognitive_firm" / "py.typed").exists():
        raise SystemExit("package is missing src/cognitive_firm/py.typed")
    if not (ROOT / "src" / "cognitive_firm" / "orchestration" / "intelligence_sources.py").exists():
        raise SystemExit("package is missing intelligence_sources module")
    if not (ROOT / "src" / "cognitive_firm" / "orchestration" / "actor_membership.py").exists():
        raise SystemExit("package is missing actor_membership module")
    if not (ROOT / "src" / "cognitive_firm" / "identity_provisioning.py").exists():
        raise SystemExit("package is missing identity_provisioning module")

    try:
        import setuptools.build_meta  # type: ignore[import-not-found]  # noqa: F401
    except ModuleNotFoundError:
        if os.environ.get("ALLOW_STATIC_PACKAGE_SMOKE") != "1":
            raise SystemExit(
                "setuptools/wheel build backend is missing; install requirements.txt "
                "or set ALLOW_STATIC_PACKAGE_SMOKE=1 for metadata-only inspection"
            )
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "static",
                    "build_backend_available": False,
                    "entry_points": sorted(required),
                    "note": "Install requirements.txt to run the wheel build path.",
                },
                sort_keys=True,
            )
        )
        return 0

    import subprocess

    with tempfile.TemporaryDirectory(prefix="cf-package-smoke-") as raw:
        work = Path(raw) / "checkout"
        shutil.copytree(
            ROOT,
            work,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv",
                "venv",
                "node_modules",
                "build",
                "dist",
                ".pytest_cache",
                ".hypothesis",
                "__pycache__",
            ),
        )
        wheel_dir = Path(raw) / "dist"
        wheel_dir.mkdir()
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                ".",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(wheel_dir),
            ],
            cwd=work,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        wheels = sorted(wheel_dir.glob("cognitive_firm-*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"expected one wheel, found {len(wheels)}")
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
            entry_points = next(
                name for name in names if name.endswith(".dist-info/entry_points.txt")
            )
            entry_text = archive.read(entry_points).decode("utf-8")
            missing = [entry for entry in sorted(required) if entry not in entry_text]
            if missing:
                raise SystemExit(f"missing console entry points: {missing}")
            if "cognitive_firm/py.typed" not in names:
                raise SystemExit("wheel is missing cognitive_firm/py.typed")
            if "cognitive_firm/orchestration/intelligence_sources.py" not in names:
                raise SystemExit("wheel is missing intelligence_sources module")
            if "cognitive_firm/orchestration/actor_membership.py" not in names:
                raise SystemExit("wheel is missing actor_membership module")
            if "cognitive_firm/identity_provisioning.py" not in names:
                raise SystemExit("wheel is missing identity_provisioning module")
        installed_checks = run_installed_wheel_checks(raw, wheel, required)
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "wheel",
                    "build_backend_available": True,
                    "wheel": wheel.name,
                    "entry_points": sorted(required),
                    "installed_checks": installed_checks,
                },
                sort_keys=True,
            )
        )
    return 0


def run_installed_wheel_checks(raw: str, wheel: Path, scripts: set[str]) -> list[str]:
    install_root = Path(raw) / "install-venv"
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(install_root)
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    python = install_root / bin_dir / "python"
    pip = install_root / bin_dir / "pip"
    subprocess_run([str(pip), "install", "--no-deps", str(wheel)])

    checks = [
        [str(python), "-m", "cognitive_firm.orchestration.org_surface"],
        [str(python), "-c", "import cognitive_firm.common.llm_runtime"],
    ]
    checks.extend([[str(install_root / bin_dir / script), "--help"] for script in sorted(scripts)])
    labels: list[str] = []
    for command in checks:
        subprocess_run(command)
        if command[0] == str(python) and command[1] == "-c":
            labels.append("python-import-llm-runtime")
        else:
            labels.append(Path(command[0]).name if command[0] != str(python) else "python-module")
    return labels


def subprocess_run(command: list[str]) -> None:
    import subprocess

    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "command failed: "
            + " ".join(command)
            + f"\nexit_code: {result.returncode}"
            + f"\nstdout:\n{result.stdout}"
            + f"\nstderr:\n{result.stderr}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
