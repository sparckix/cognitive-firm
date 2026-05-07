"""Lightweight command-surface discovery for the org runtime.

The goal is not to be a shell parser. The goal is to make existing repo
commands legible to the daemon so it can prefer them over ad hoc scripts.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from src.cognitive_firm.common.paths import REPO_ROOT


MAKE_TARGET_RE = re.compile(r"^([A-Za-z0-9_.-]+):", re.MULTILINE)
MAKE_TOKEN_RE = re.compile(r"\bmake\s+([A-Za-z0-9_.-]+)\b")
PYTHON_SCRIPT_RE = re.compile(r"\bpython(?:3)?\s+([A-Za-z0-9_./-]+\.py)\b")


@lru_cache(maxsize=1)
def list_make_targets(repo_root: Path = REPO_ROOT) -> frozenset[str]:
    makefile = repo_root / "Makefile"
    if not makefile.exists():
        return frozenset()
    text = makefile.read_text(encoding="utf-8", errors="ignore")
    targets = {
        match.group(1)
        for match in MAKE_TARGET_RE.finditer(text)
        if "%" not in match.group(1) and not match.group(1).startswith(".")
    }
    return frozenset(targets)


@lru_cache(maxsize=1)
def list_python_entrypoints(repo_root: Path = REPO_ROOT) -> frozenset[str]:
    paths = set()
    for root in (repo_root / "scripts", repo_root / "src"):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            try:
                rel = path.relative_to(repo_root).as_posix()
            except ValueError:
                continue
            paths.add(rel)
    return frozenset(paths)


def command_surface_matches(text: str) -> list[str]:
    """Return exact repo commands referenced by a task or prompt body."""
    normalized = text.lower()
    matches: list[str] = []

    for target in sorted(list_make_targets()):
        if f"make {target}".lower() in normalized or target.lower() in normalized:
            candidate = f"make {target}"
            if candidate not in matches:
                matches.append(candidate)

    for rel in sorted(list_python_entrypoints()):
        basename = Path(rel).name.lower()
        if rel.lower() in normalized or basename in normalized:
            candidate = f"python {rel}"
            if candidate not in matches:
                matches.append(candidate)

    for target in MAKE_TOKEN_RE.findall(text):
        candidate = f"make {target}"
        if target in list_make_targets() and candidate not in matches:
            matches.append(candidate)

    for rel in PYTHON_SCRIPT_RE.findall(text):
        rel = rel.rstrip(".,);:")
        candidate = f"python {rel}"
        if rel in list_python_entrypoints() and candidate not in matches:
            matches.append(candidate)

    return matches


def command_surface_hint(text: str) -> str:
    matches = command_surface_matches(text)
    if not matches:
        return "No exact repo command matched the task text."
    return "Known repo command surface: " + ", ".join(f"`{m}`" for m in matches)

