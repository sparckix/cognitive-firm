"""Distribution-layer lockfile (O3-P3).

A git URL is not an immutable identity: tags move and a force-push rewrites
history. The lockfile is what turns "install package X" into a *reproducible*
operation. It records, per package, the resolved git URL, the 40-char commit
SHA the install was pinned to, and a content hash computed over the *fetched*
files.

Two distinct guarantees layer here:

- **SHA pinning** catches a moved tag — a later resolve of the same tag points
  at a different SHA, and the lockfile's SHA no longer matches.
- **content hash** catches the rarer case where the *same* SHA is made to
  carry different content (a force-push that rewrites a commit, or a registry
  that lies). A re-fetch whose content hash differs from the lockfile entry is
  a hard error: ``LockMismatch``.

The lockfile lives at ``<org>/.cognitive-firm/packages.lock`` and is a plain
JSON document, append-and-replace per package. It is part of the
package-manager (userland) layer — no kernel change. It is a standalone,
tested primitive: the installer wires it in (another lane), this module only
reads, writes, and verifies.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOCKFILE_DIRNAME = ".cognitive-firm"
LOCKFILE_FILENAME = "packages.lock"
LOCK_SCHEMA_VERSION = 1

# 40-char lowercase hex — the shape of a resolved full git commit SHA. A short
# SHA or a tag name is *not* a valid pin and is rejected at lock time.
_SHA_LEN = 40


class LockError(RuntimeError):
    """Raised when a lockfile is malformed or an entry is invalid."""


class LockMismatch(LockError):
    """Raised when freshly fetched content does not match the locked entry.

    This is the immutability tripwire: the SHA the operator installed now
    resolves to, or carries, different bytes than were recorded.
    """


def _is_full_sha(value: str) -> bool:
    return (
        len(value) == _SHA_LEN
        and all(c in "0123456789abcdef" for c in value.lower())
    )


def hash_directory(root: Path) -> str:
    """Return a stable content hash over every file under ``root``.

    The hash is order-independent and path-aware: each file contributes its
    POSIX-relative path and its bytes. The ``.git`` directory and the
    ``.cognitive-firm`` receipt/lock directory are excluded — they are not
    package content and would make the hash non-deterministic. The result is
    ``sha256:<hex>`` so the algorithm is self-describing.
    """
    root = Path(root)
    if not root.is_dir():
        raise LockError(f"cannot hash a non-directory: {root}")
    digest = hashlib.sha256()
    members: list[tuple[str, Path]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        parts = rel.parts
        if parts and parts[0] in (".git", LOCKFILE_DIRNAME):
            continue
        members.append((rel.as_posix(), path))
    for rel_posix, path in sorted(members, key=lambda m: m[0]):
        digest.update(rel_posix.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


@dataclass(frozen=True)
class LockEntry:
    """One locked package: the reproducibility record for a single install."""

    name: str
    version: str
    source_url: str
    resolved_sha: str
    content_hash: str
    subdir: str = ""  # package path within the repo; "" means repo root
    signature: str = ""
    installed_kernel_event_id: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise LockError("lock entry has an empty name")
        if not _is_full_sha(self.resolved_sha):
            raise LockError(
                f"lock entry '{self.name}' resolved_sha is not a 40-char "
                f"commit SHA: {self.resolved_sha!r}"
            )
        if not self.content_hash:
            raise LockError(
                f"lock entry '{self.name}' has an empty content_hash"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "source_url": self.source_url,
            "resolved_sha": self.resolved_sha,
            "content_hash": self.content_hash,
            "subdir": self.subdir,
            "signature": self.signature,
            "installed_kernel_event_id": self.installed_kernel_event_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LockEntry":
        if not isinstance(raw, dict):
            raise LockError("lock entry must be a JSON object")
        try:
            return cls(
                name=str(raw["name"]),
                version=str(raw.get("version", "")),
                source_url=str(raw.get("source_url", "")),
                resolved_sha=str(raw["resolved_sha"]),
                content_hash=str(raw["content_hash"]),
                subdir=str(raw.get("subdir", "")),
                signature=str(raw.get("signature", "")),
                installed_kernel_event_id=str(
                    raw.get("installed_kernel_event_id", "")
                ),
            )
        except KeyError as exc:
            raise LockError(f"lock entry missing field: {exc}") from exc

    @property
    def pinned_id(self) -> str:
        """The immutable ``name@<sha>`` identity of this locked package."""
        return f"{self.name}@{self.resolved_sha}"


@dataclass(frozen=True)
class Lockfile:
    """An in-memory view of ``.cognitive-firm/packages.lock``."""

    entries: tuple[LockEntry, ...] = ()
    schema_version: int = LOCK_SCHEMA_VERSION

    def get(self, name: str) -> LockEntry | None:
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None

    def with_entry(self, entry: LockEntry) -> "Lockfile":
        """Return a new lockfile with ``entry`` added or replaced by name.

        Entries are kept sorted by name so the on-disk file is stable and
        diff-friendly across re-writes.
        """
        kept = [e for e in self.entries if e.name != entry.name]
        kept.append(entry)
        kept.sort(key=lambda e: e.name)
        return Lockfile(entries=tuple(kept), schema_version=self.schema_version)

    def without(self, name: str) -> "Lockfile":
        """Return a new lockfile with the entry for ``name`` removed."""
        return Lockfile(
            entries=tuple(e for e in self.entries if e.name != name),
            schema_version=self.schema_version,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "packages": [e.as_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "Lockfile":
        if not isinstance(raw, dict):
            raise LockError("lockfile must be a JSON object")
        schema_version = int(raw.get("schema_version", LOCK_SCHEMA_VERSION))
        if schema_version != LOCK_SCHEMA_VERSION:
            raise LockError(
                f"unsupported lockfile schema_version {schema_version} "
                f"(expected {LOCK_SCHEMA_VERSION})"
            )
        packages = raw.get("packages") or []
        if not isinstance(packages, list):
            raise LockError("lockfile 'packages' must be a list")
        entries = tuple(LockEntry.from_dict(p) for p in packages)
        names = [e.name for e in entries]
        if len(names) != len(set(names)):
            raise LockError("lockfile has duplicate package names")
        return cls(entries=entries, schema_version=schema_version)


def lockfile_path(org_root: Path) -> Path:
    """The canonical lockfile path for an org directory."""
    return Path(org_root) / LOCKFILE_DIRNAME / LOCKFILE_FILENAME


def read_lockfile(org_root: Path) -> Lockfile:
    """Read the lockfile for an org; an empty lockfile if none exists yet."""
    path = lockfile_path(org_root)
    if not path.is_file():
        return Lockfile()
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise LockError(f"lockfile is not valid JSON ({path}): {exc}") from exc
    return Lockfile.from_dict(raw)


def write_lockfile(org_root: Path, lockfile: Lockfile) -> Path:
    """Write ``lockfile`` to ``<org>/.cognitive-firm/packages.lock``.

    The directory is created if needed; the file is written with stable key
    ordering so re-writes produce minimal diffs. Returns the written path.
    """
    path = lockfile_path(org_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lockfile.as_dict(), indent=2) + "\n")
    return path


def lock_package(org_root: Path, entry: LockEntry) -> Lockfile:
    """Add or replace ``entry`` in the org's lockfile and persist it.

    Returns the updated in-memory lockfile.
    """
    updated = read_lockfile(org_root).with_entry(entry)
    write_lockfile(org_root, updated)
    return updated


def verify_against_lock(
    org_root: Path, name: str, fetched_dir: Path
) -> LockEntry:
    """Check freshly fetched content against the locked entry for ``name``.

    Recomputes the content hash of ``fetched_dir`` and compares it to the
    lockfile. Raises:

    - ``LockError`` if ``name`` is not in the lockfile (nothing to verify
      against — the caller must ``lock_package`` first);
    - ``LockMismatch`` if the recomputed hash differs from the locked hash —
      the remote content for ``name`` changed since it was installed.

    Returns the matching locked entry on success.
    """
    entry = read_lockfile(org_root).get(name)
    if entry is None:
        raise LockError(f"no lockfile entry for package '{name}'")
    actual = hash_directory(fetched_dir)
    if actual != entry.content_hash:
        raise LockMismatch(
            f"content for '{entry.pinned_id}' changed since install: "
            f"locked {entry.content_hash}, fetched {actual} — a force-push or "
            f"a tampered remote is the likely cause"
        )
    return entry
