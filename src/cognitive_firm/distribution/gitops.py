"""Minimal git operations for the distribution layer.

Each install is a git commit: that makes the install transactional (a failed
install leaves no trace) and forms the rollback boundary (spec R1). These are
thin, well-scoped wrappers over the ``git`` CLI — no third-party dependency.
The installed organization is always its own git repo rooted at the target.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# A self-contained commit identity, so a fresh install does not depend on the
# host having global git config set.
_COMMIT_IDENTITY = (
    "-c",
    "user.name=cognitive-firm installer",
    "-c",
    "user.email=installer@cognitive-firm.local",
)


class GitError(RuntimeError):
    """A git command failed."""


def _run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed in {cwd}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def is_repo(path: Path) -> bool:
    """True if ``path`` is the root of its own git repo."""
    return (Path(path) / ".git").is_dir()


def init_repo(path: Path) -> None:
    _run(["init"], Path(path))


def current_ref(path: Path) -> str | None:
    """The HEAD commit sha, or None if the repo has no commits yet."""
    try:
        return _run(["rev-parse", "HEAD"], Path(path))
    except GitError:
        return None


def has_staged_changes(path: Path) -> bool:
    """True if there is something staged to commit."""
    # exit 1 => staged differences exist; exit 0 => nothing staged.
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=str(path),
        capture_output=True,
    )
    return result.returncode != 0


def stage_all(path: Path) -> None:
    _run(["add", "-A"], Path(path))


def commit(path: Path, message: str) -> str:
    """Commit staged changes; return the new commit sha."""
    _run(
        [*_COMMIT_IDENTITY, "commit", "-m", message, "--no-verify"],
        Path(path),
    )
    return _run(["rev-parse", "HEAD"], Path(path))


def tag(path: Path, name: str) -> None:
    """Create or move a tag to the current HEAD."""
    _run(["tag", "-f", name], Path(path))


def reset_hard(path: Path, ref: str) -> None:
    _run(["reset", "--hard", ref], Path(path))


def revert_no_edit(path: Path, sha: str) -> str:
    """Revert a commit as a new forward commit; return the revert commit sha.

    Raises ``GitError`` if the revert conflicts with later changes.
    """
    _run(
        [*_COMMIT_IDENTITY, "revert", "--no-edit", sha],
        Path(path),
    )
    return _run(["rev-parse", "HEAD"], Path(path))


def revert_abort(path: Path) -> None:
    """Abort an in-progress revert (best effort)."""
    try:
        _run(["revert", "--abort"], Path(path))
    except GitError:
        pass
