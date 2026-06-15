#!/usr/bin/env python3
"""Release hygiene checks for private, local, and generated state.

This is intentionally conservative about tracked/staged files and permissive
about ignored local state. A developer may keep `.env` or generated demo runs on
disk; a release should fail only if those paths are tracked, staged, or visible
as unignored sensitive files.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Finding:
    path: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "reason": self.reason}


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [line for line in result.stdout.splitlines() if line]


def is_allowed_tenant_example(path: str) -> bool:
    return (
        path == "tenants/README.md"
        or path == "tenants/.gitkeep"
        or path.startswith("tenants/example/")
    )


def private_tracked_reason(path: str) -> str | None:
    name = Path(path).name
    if path in {".env", ".env.local"} or name.endswith(".env"):
        return "environment files must not be tracked or staged"
    if path.startswith(".cognitive-firm-runs/"):
        return "generated demo/runtime reports belong in ignored run directories"
    if path.startswith("internal/"):
        return "internal strategy, handover, and research notes are not public kernel state"
    if path.startswith(("cognitive_firm_workspace/", "local_runtime_workspace/")):
        return "local runtime workspaces must not be part of the public kernel"
    if path.startswith("org/sessions/"):
        return "session state is local runtime state"
    if path == "org/preferences/principal.yaml":
        return "principal preferences are tenant/operator state; track templates only"
    if path.startswith("org/signals/damage/") and not path.endswith("/.gitkeep"):
        return "damage signal rows are runtime state"
    if path.startswith(
        (
            "org/objectives/",
            "org/key_results/",
            "org/tasks/active/",
            "org/tasks/done/",
            "org/directives/",
        )
    ):
        return "live objectives, tasks, and directives are tenant runtime state"
    if path.startswith("tenants/") and not is_allowed_tenant_example(path):
        return "only tenants/example and tenants/README.md are public kernel examples"
    return None


SENSITIVE_UNTRACKED_TOKENS = (
    ".env",
    "answer_key",
    "operator-only",
    "scorecard",
    "secret",
    "token",
)


def untracked_sensitive_reason(path: str) -> str | None:
    lowered = path.lower()
    if any(token in lowered for token in SENSITIVE_UNTRACKED_TOKENS):
        return "sensitive-looking untracked path is not ignored"
    return None


def findings_for(paths: list[str], *, include_sensitive_untracked: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(set(paths)):
        reason = (
            untracked_sensitive_reason(path)
            if include_sensitive_untracked
            else private_tracked_reason(path)
        )
        if reason:
            findings.append(Finding(path=path, reason=reason))
    return findings


def main() -> int:
    tracked = findings_for(git_lines("ls-files"))
    staged = findings_for(git_lines("diff", "--cached", "--name-only"))
    untracked = findings_for(
        git_lines("ls-files", "--others", "--exclude-standard"),
        include_sensitive_untracked=True,
    )

    payload = {
        "ok": not (tracked or staged or untracked),
        "tracked_private_state": [finding.as_dict() for finding in tracked],
        "staged_private_state": [finding.as_dict() for finding in staged],
        "unignored_sensitive_paths": [finding.as_dict() for finding in untracked],
        "notes": [
            "Ignored local state is allowed on disk.",
            "This check fails only when private/generated state is tracked, staged, or unignored.",
        ],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
