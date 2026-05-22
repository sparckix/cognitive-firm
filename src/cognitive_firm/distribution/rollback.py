"""Distribution-layer rollback.

Undo a package install. Two modes (spec R2):

- **clean** — nothing has been committed since the install boundary: a
  ``git reset --hard`` to the pre-install ref. Total and exact. (For a
  first-ever install, with no prior ref, the installed files are removed.)
- **compensating** — the org has run since the install: the install commit is
  reverted as a new *forward* commit, so the append-only history stays
  replayable (spec §1.1). If post-install edits to the installed files make
  the revert conflict, the rollback is reported blocked rather than forced.

Rollback is not "undo" — events that happened, happened. It is a governed,
attested, git-backed reversion that keeps replay faithful.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cognitive_firm.distribution import gitops
from cognitive_firm.distribution.installer import (
    RECEIPT_DIRNAME,
    InstallReceipt,
    load_receipt,
    record_distribution_event,
)


class RollbackError(RuntimeError):
    """Raised when a rollback cannot be completed safely."""


@dataclass(frozen=True)
class RollbackResult:
    """The durable record of one rollback."""

    package: str
    mode: str  # "clean" | "compensating"
    reason: str
    rolled_back_at: str
    actor: str
    reverted_to_ref: str | None = None  # clean: the pre-install ref restored
    rollback_commit: str | None = None  # compensating: the new revert commit
    affected_window: tuple[str, str] | None = None  # (install_sha, head)

    def as_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "mode": self.mode,
            "reason": self.reason,
            "rolled_back_at": self.rolled_back_at,
            "actor": self.actor,
            "reverted_to_ref": self.reverted_to_ref,
            "rollback_commit": self.rollback_commit,
            "affected_window": list(self.affected_window)
            if self.affected_window
            else None,
        }


def _remove_genesis(target_root: Path, receipt: InstallReceipt) -> None:
    """Clean rollback of a first-ever install: there is no prior ref to reset
    to, so the installed files are removed and the removal is committed."""
    for f in receipt.files:
        if f.action in ("created", "overwritten"):
            path = target_root / f.dest
            if path.is_file():
                path.unlink()
    gitops.stage_all(target_root)
    if gitops.has_staged_changes(target_root):
        gitops.commit(
            target_root, f"rollback {receipt.package} (clean, genesis install)"
        )


def rollback(
    target_root: Path,
    package: str,
    *,
    reason: str,
    actor: str = "operator",
) -> RollbackResult:
    """Roll back the install of ``package`` from ``target_root``.

    Picks clean or compensating mode automatically (spec R2), records a
    ``package.rolled_back`` kernel event, replaces the install receipt with a
    rollback record, and returns the :class:`RollbackResult`.
    """
    target_root = Path(target_root)
    receipt = load_receipt(target_root, package)  # raises FileNotFoundError
    if not receipt.commit_sha:
        raise RollbackError(
            f"install of '{package}' has no commit boundary to roll back"
        )

    # A dirty working tree must be resolved before any rollback (F-2). Clean
    # mode (`git reset --hard`) would silently discard uncommitted work;
    # compensating mode (`git revert`) would fail and be misreported as a
    # content merge conflict. Refuse with an accurate, actionable message that
    # is distinct from the genuine post-install conflict diagnosis below.
    if gitops.is_dirty(target_root):
        raise RollbackError(
            f"cannot roll back '{package}': the firm has uncommitted changes "
            f"in its working tree. Commit or stash them first, then retry — "
            f"rollback will not discard in-flight work."
        )

    head = gitops.current_ref(target_root)
    clean = head == receipt.commit_sha

    reverted_to: str | None = None
    rollback_commit: str | None = None
    window: tuple[str, str] | None = None

    if clean:
        mode = "clean"
        if receipt.pre_install_ref:
            gitops.reset_hard(target_root, receipt.pre_install_ref)
            reverted_to = receipt.pre_install_ref
        else:
            _remove_genesis(target_root, receipt)
    else:
        mode = "compensating"
        try:
            rollback_commit = gitops.revert_no_edit(
                target_root, receipt.commit_sha
            )
        except gitops.GitError as exc:
            gitops.revert_abort(target_root)
            raise RollbackError(
                f"compensating rollback of '{package}' conflicts with "
                f"post-install changes to the same files; resolve manually. "
                f"({exc})"
            ) from exc
        window = (receipt.commit_sha, head or "")

    result = RollbackResult(
        package=package,
        mode=mode,
        reason=reason,
        rolled_back_at=datetime.now(timezone.utc).isoformat(),
        actor=actor,
        reverted_to_ref=reverted_to,
        rollback_commit=rollback_commit,
        affected_window=window,
    )

    record_distribution_event(
        target_root,
        actor=actor,
        verb="package.rolled_back",
        package=package,
        payload=result.as_dict(),
    )

    receipt_dir = target_root / RECEIPT_DIRNAME
    install_receipt = receipt_dir / f"install-{package}.json"
    if install_receipt.is_file():
        install_receipt.unlink()
    receipt_dir.mkdir(parents=True, exist_ok=True)
    (receipt_dir / f"rollback-{package}.json").write_text(
        json.dumps(result.as_dict(), indent=2) + "\n"
    )
    return result
