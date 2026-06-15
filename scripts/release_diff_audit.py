#!/usr/bin/env python3
"""Classify the current release diff into review buckets.

This is a review aid, not a private-state hygiene check. It answers a narrower
question before staging a broad release: which changed paths are kernel code,
tests, demos, docs, generated indexes, config, or unknown? Unknown paths fail so
large diffs cannot silently hide a new release surface.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Bucket:
    name: str
    description: str
    matcher: Callable[[str], bool]


def _git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line]


def _is_generated_index(path: str) -> bool:
    return (
        path.endswith("/README.md")
        and path
        in {
            "docs/README.md",
            "docs/protocols/README.md",
            "docs/examples/README.md",
            "scripts/README.md",
            "src/README.md",
            "src/cognitive_firm/README.md",
            "src/cognitive_firm/orchestration/README.md",
            "tests/README.md",
            "org/README.md",
            "org/roles/README.md",
        }
    )


BUCKETS: tuple[Bucket, ...] = (
    Bucket(
        "generated_indexes",
        "Folder indexes and navigational README refreshes.",
        _is_generated_index,
    ),
    Bucket(
        "release_gates",
        "Release hygiene, public-claim discipline, and their tests.",
        lambda p: p
        in {
            "scripts/release_hygiene_check.py",
            "scripts/public_claims_check.py",
            "tests/test_release_hygiene_check.py",
            "tests/test_public_claims_check.py",
        },
    ),
    Bucket(
        "demo_and_examples",
        "First-party demos, example docs, and demo tests.",
        lambda p: (
            p.startswith("demos/")
            or p.startswith("docs/examples/")
            or p == "scripts/agent_fleet_audit_demo.py"
            or p.endswith("_demo.py")
            or "/test_self_evolving_" in f"/{p}"
            or p.startswith("tests/test_agent_fleet_audit_demo.py")
            or p.startswith("tests/test_multi_agent_trace_attribution_demo.py")
            or p.startswith("tests/test_phase_execution_demo.py")
            or p.startswith("tests/test_protocol_experiment_demo.py")
            or p.startswith("tests/test_capability_signal_demo.py")
        ),
    ),
    Bucket(
        "kernel_code",
        "Reusable kernel primitives, service routes, adapters, and projections.",
        lambda p: p.startswith("src/cognitive_firm/"),
    ),
    Bucket(
        "public_schemas",
        "Public JSON schemas and protocol validation surfaces.",
        lambda p: p.startswith("schemas/"),
    ),
    Bucket(
        "orbit_surface",
        "Orbit dashboard shell and UI assets shipped with the public repo.",
        lambda p: p.startswith("orbit/"),
    ),
    Bucket(
        "protocol_docs",
        "Public protocol, capability, positioning, and testing docs.",
        lambda p: p.startswith("docs/") or p in {"README.md", "CHANGELOG.md", "AGENTS.md"},
    ),
    Bucket(
        "operator_scripts",
        "Thin scripts, smokes, CLIs, and operator entrypoints.",
        lambda p: p.startswith("scripts/"),
    ),
    Bucket(
        "tests",
        "Unit and integration tests for non-demo kernel behavior.",
        lambda p: p.startswith("tests/"),
    ),
    Bucket(
        "org_examples",
        "Public org skeleton, templates, and copyable example roles/patterns.",
        lambda p: p.startswith("org/"),
    ),
    Bucket(
        "repo_config",
        "Build, environment example, gitignore, and package metadata.",
        lambda p: p
        in {
            ".env.example",
            ".gitignore",
            "Makefile",
            "pyproject.toml",
        },
    ),
)


def classify(path: str) -> str:
    for bucket in BUCKETS:
        if bucket.matcher(path):
            return bucket.name
    return "unclassified"


def changed_paths() -> dict[str, list[str]]:
    modified = set(_git_lines("diff", "--name-only"))
    staged = set(_git_lines("diff", "--cached", "--name-only"))
    untracked = set(_git_lines("ls-files", "--others", "--exclude-standard"))
    return {
        "modified": sorted(modified),
        "staged": sorted(staged),
        "untracked": sorted(untracked),
        "all": sorted(modified | staged | untracked),
    }


def build_audit() -> dict[str, object]:
    paths = changed_paths()
    buckets: dict[str, list[str]] = {bucket.name: [] for bucket in BUCKETS}
    buckets["unclassified"] = []
    for path in paths["all"]:
        buckets[classify(path)].append(path)
    bucket_summaries = {
        name: {
            "count": len(items),
            "paths": items,
        }
        for name, items in buckets.items()
        if items or name == "unclassified"
    }
    return {
        "ok": not buckets["unclassified"],
        "counts": {
            "modified": len(paths["modified"]),
            "staged": len(paths["staged"]),
            "untracked": len(paths["untracked"]),
            "total_unique": len(paths["all"]),
        },
        "bucket_descriptions": {
            bucket.name: bucket.description for bucket in BUCKETS
        },
        "buckets": bucket_summaries,
        "notes": [
            "This classifies release surface area only.",
            "Run release-hygiene-check separately for private/generated state.",
            "A passing audit does not replace human diff review by bucket.",
        ],
    }


def main() -> int:
    audit = build_audit()
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
