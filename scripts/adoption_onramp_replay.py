#!/usr/bin/env python3
"""Replay the adoption on-ramp from a clean public worktree copy.

This is a release/adoption proof, not a workflow runner. It stages the public
repo surface into an isolated copy, excludes internal/private/local state, and
runs the existing adoption-on-ramp collector there. The goal is to prove that a
first reviewer can replay the documented on-ramp without hidden author-local
state.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_PREFIXES = (
    ".cognitive-firm-runs/",
    ".git/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".venv/",
    "internal/",
    "node_modules/",
    "orbit/node_modules/",
    "venv/",
)
EXCLUDED_NAMES = {".env"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Copy the public repo surface to an isolated directory and replay "
            "the adoption on-ramp collector there."
        )
    )
    parser.add_argument("--target-label", default="outside_adopter_replay")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Directory for the public copy, collector logs, and replay report. "
            "Defaults to a timestamped .cognitive-firm-runs/adoption-onramp-replay folder."
        ),
    )
    parser.add_argument(
        "--include-optional",
        action="store_true",
        help="Run the collector's optional no-cost proof checks as well as the required core checks.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=90.0,
        help="Per-command timeout passed to the adoption on-ramp collector.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing output directory.",
    )
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_output_dir()
    if output_dir.exists():
        if not args.force:
            raise SystemExit(f"output directory already exists: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    public_copy_dir = output_dir / "public-copy"
    artifact_dir = output_dir / "adoption-onramp"
    public_copy_dir.mkdir()
    copied_paths = copy_public_surface(public_copy_dir)
    manifest_path = output_dir / "public-copy-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "public_worktree_copy_manifest.v1",
                "source_root": str(ROOT),
                "public_copy_root": str(public_copy_dir),
                "copied_path_count": len(copied_paths),
                "excluded_prefixes": list(EXCLUDED_PREFIXES),
                "excluded_names": sorted(EXCLUDED_NAMES),
                "paths": copied_paths,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    collector = run_collector(
        public_copy_dir=public_copy_dir,
        artifact_dir=artifact_dir,
        target_label=args.target_label,
        include_optional=args.include_optional,
        timeout_seconds=args.timeout_seconds,
        output_dir=output_dir,
    )
    collector_payload = collector.get("payload")
    collector_ok = (
        collector["returncode"] == 0
        and isinstance(collector_payload, dict)
        and collector_payload.get("ok") is True
    )
    packet_path = None
    markdown_path = None
    if isinstance(collector_payload, dict):
        packet_path = collector_payload.get("packet_path")
        markdown_path = collector_payload.get("markdown_path")

    summary = {
        "schema": "adoption_onramp_replay.v1",
        "target_label": args.target_label,
        "ok": collector_ok,
        "source_root": str(ROOT),
        "output_dir": str(output_dir),
        "public_copy_root": str(public_copy_dir),
        "public_copy_manifest_path": str(manifest_path),
        "copied_path_count": len(copied_paths),
        "collector": collector,
        "collector_packet_path": packet_path,
        "collector_markdown_path": markdown_path,
        "boundary": {
            "uses_clean_public_copy": True,
            "excludes_internal_private_state": True,
            "runs_existing_onramp_collector": True,
            "does_not_run_external_agents": True,
            "does_not_approve_release": True,
            "does_not_schedule_work": True,
            "does_not_mutate_source_worktree": True,
            "not_a_workflow_engine": True,
        },
    }
    report_path = output_dir / "adoption-onramp-replay.json"
    report_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if collector_ok else 1


def copy_public_surface(destination: Path) -> list[str]:
    paths = public_repo_paths()
    for rel_path in paths:
        source = ROOT / rel_path
        target = destination / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return paths


def public_repo_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    paths: list[str] = []
    for line in result.stdout.splitlines():
        rel_path = line.strip()
        if not rel_path or _is_excluded(rel_path):
            continue
        source = ROOT / rel_path
        if source.is_file():
            paths.append(rel_path)
    return sorted(paths)


def run_collector(
    *,
    public_copy_dir: Path,
    artifact_dir: Path,
    target_label: str,
    include_optional: bool,
    timeout_seconds: float,
    output_dir: Path,
) -> dict[str, Any]:
    command = [
        sys.executable,
        "scripts/adoption_onramp_packet.py",
        "--target-label",
        target_label,
        "--output-dir",
        str(artifact_dir),
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    if not include_optional:
        command.append("--core-only")

    completed = subprocess.run(
        command,
        cwd=public_copy_dir,
        env=_replay_env(public_copy_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stdout_path = output_dir / "adoption-onramp-replay.stdout.txt"
    stderr_path = output_dir / "adoption-onramp-replay.stderr.txt"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    payload: dict[str, Any] | None
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = None
    else:
        payload = parsed if isinstance(parsed, dict) else None
    return {
        "command": " ".join(command),
        "returncode": completed.returncode,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "payload": payload,
    }


def _replay_env(public_copy_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(public_copy_dir / "src")
    return env


def _is_excluded(rel_path: str) -> bool:
    name = Path(rel_path).name
    return name in EXCLUDED_NAMES or any(
        rel_path == prefix.rstrip("/") or rel_path.startswith(prefix)
        for prefix in EXCLUDED_PREFIXES
    )


def _default_output_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / ".cognitive-firm-runs" / "adoption-onramp-replay" / stamp


if __name__ == "__main__":
    raise SystemExit(main())
