"""Remote package fetch and immutable identity (O3-P3).

``discover_packages`` (``registry.py``) only indexes a *local* directory. A
real ecosystem needs packages fetched from a git URL. This module is the fetch
path:

- A **remote package source** is a git URL plus an optional ref (tag/branch)
  and an optional subdirectory within the repo holding ``package.yaml``.
- Identity is ``name@<commit-sha>``, never ``name@<tag>``. A human-friendly
  ref is resolved to a 40-char SHA *once*, at fetch time; everything downstream
  pins the SHA. A moved tag therefore resolves to a different SHA — caught.
- A fetched package lands in a content-addressed cache directory keyed by SHA
  (``<cache>/<sha>/``). Fetching the same SHA twice reuses the cache.

The fetch produces a :class:`FetchedPackage` carrying the resolved SHA, the
parsed manifest, and a content hash — exactly the inputs the lockfile
(``lockfile.py``) records. Fetch + lockfile ship together: a fetch without a
lock is not a valid intermediate state, so :func:`fetch_and_lock` does both.

This is package-manager (userland) layer code — no kernel change.
``cognitive-firm-distro install <git-url>`` runs this fetch path, then installs
the SHA-pinned package from the content-addressed cache.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from cognitive_firm.distribution.lockfile import (
    LockEntry,
    Lockfile,
    hash_directory,
    lock_package,
)
from cognitive_firm.distribution.manifest import (
    ManifestError,
    PackageManifest,
    load_manifest,
)
from cognitive_firm.distribution.registry import MANIFEST_FILENAME

PKG_CACHE_DIRNAME = ".cognitive-firm/pkg-cache"
_SHA_LEN = 40


class RemoteFetchError(RuntimeError):
    """Raised when a remote package cannot be fetched or resolved."""


def _git(args: list[str], cwd: Path | None = None) -> str:
    """Run a git command; raise ``RemoteFetchError`` on failure.

    Mirrors ``gitops._run`` but raises this module's error type so callers
    can distinguish a remote-fetch failure from a local-install git failure.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        where = f" in {cwd}" if cwd is not None else ""
        raise RemoteFetchError(
            f"git {' '.join(args)} failed{where}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def _is_full_sha(value: str) -> bool:
    return (
        len(value) == _SHA_LEN
        and all(c in "0123456789abcdef" for c in value.lower())
    )


@dataclass(frozen=True)
class RemotePackageSource:
    """How to locate a package in a remote git repo.

    ``url``    - any git-cloneable URL (https, ssh, or a local file path).
    ``ref``    - a tag, branch, or SHA to resolve; ``HEAD`` if unset.
    ``subdir`` - the path within the repo to the package root (the directory
                 holding ``package.yaml``); empty means the repo root.
    """

    url: str
    ref: str = "HEAD"
    subdir: str = ""

    def __post_init__(self) -> None:
        if not self.url:
            raise RemoteFetchError("remote package source has an empty url")
        if self.subdir.startswith("/") or ".." in Path(self.subdir).parts:
            raise RemoteFetchError(
                f"remote package subdir escapes the repo: {self.subdir!r}"
            )


@dataclass(frozen=True)
class FetchedPackage:
    """A package fetched from a remote git repo and pinned to a commit SHA."""

    source: RemotePackageSource
    resolved_sha: str
    package_root: Path  # the cached directory holding package.yaml
    manifest: PackageManifest
    content_hash: str

    @property
    def pinned_id(self) -> str:
        """The immutable ``name@<sha>`` identity."""
        return f"{self.manifest.name}@{self.resolved_sha}"


def resolve_ref(url: str, ref: str = "HEAD") -> str:
    """Resolve a tag/branch/ref on a remote repo to a full 40-char commit SHA.

    Uses ``git ls-remote`` so the repo need not be cloned. If ``ref`` is
    already a full SHA it is returned unchanged (``ls-remote`` cannot resolve
    an arbitrary SHA, but a SHA is already the pinned form). Raises
    ``RemoteFetchError`` if the ref does not exist on the remote.
    """
    if _is_full_sha(ref):
        return ref.lower()
    out = _git(["ls-remote", url, ref])
    if not out:
        # Retry without a ref pattern for the HEAD-of-default-branch case.
        if ref in ("HEAD", ""):
            out = _git(["ls-remote", url, "HEAD"])
        if not out:
            raise RemoteFetchError(
                f"ref {ref!r} not found on remote {url}"
            )
    # ls-remote emits "<sha>\t<refname>" lines; an exact tag may also yield a
    # peeled "<sha>\t<refname>^{}" line — prefer the peeled (dereferenced) SHA
    # so an annotated tag pins the commit it points at, not the tag object.
    sha_by_ref: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        sha, name = parts[0].strip(), parts[1].strip()
        if not _is_full_sha(sha):
            continue
        sha_by_ref[name] = sha
    for name, sha in sha_by_ref.items():
        if name.endswith("^{}"):
            return sha
    if sha_by_ref:
        return next(iter(sha_by_ref.values()))
    raise RemoteFetchError(f"could not resolve a SHA for {ref!r} on {url}")


def cache_dir_for(cache_root: Path, sha: str) -> Path:
    """The content-addressed cache directory for a resolved commit SHA."""
    if not _is_full_sha(sha):
        raise RemoteFetchError(
            f"cache key must be a 40-char commit SHA, got {sha!r}"
        )
    return Path(cache_root) / sha


def fetch_package(
    source: RemotePackageSource,
    cache_root: Path,
    *,
    force: bool = False,
) -> FetchedPackage:
    """Clone/checkout a remote package into the SHA-keyed cache and parse it.

    Steps:

    1. resolve ``source.ref`` to a full commit SHA via ``git ls-remote``;
    2. if the SHA's cache dir exists and is non-empty, reuse it (unless
       ``force``); otherwise clone the repo and hard-checkout the SHA;
    3. load and validate the ``package.yaml`` at ``source.subdir``;
    4. compute a content hash over the package root (excluding ``.git``).

    Returns a :class:`FetchedPackage`. The cache is content-addressed by SHA,
    so two refs that resolve to the same commit share one cache entry. The
    cache excludes ``.git`` from the content hash, so the hash reflects package
    *content*, not git history.
    """
    sha = resolve_ref(source.url, source.ref)
    cache_root = Path(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    repo_dir = cache_dir_for(cache_root, sha)

    populated = repo_dir.is_dir() and any(repo_dir.iterdir())
    if force or not populated:
        if repo_dir.exists():
            shutil.rmtree(repo_dir)
        _clone_at_sha(source.url, sha, repo_dir)

    package_root = repo_dir / source.subdir if source.subdir else repo_dir
    if not package_root.is_dir():
        raise RemoteFetchError(
            f"package subdir {source.subdir!r} not found in {source.url} "
            f"at {sha}"
        )
    manifest_path = package_root / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise RemoteFetchError(
            f"no {MANIFEST_FILENAME} at {source.subdir or '<repo root>'} "
            f"in {source.url}@{sha}"
        )
    try:
        manifest = load_manifest(manifest_path)
    except ManifestError as exc:
        raise RemoteFetchError(
            f"fetched package at {source.url}@{sha} is invalid: {exc}"
        ) from exc

    content_hash = hash_directory(package_root)
    return FetchedPackage(
        source=source,
        resolved_sha=sha,
        package_root=package_root,
        manifest=manifest,
        content_hash=content_hash,
    )


def _clone_at_sha(url: str, sha: str, dest: Path) -> None:
    """Clone ``url`` into ``dest`` and hard-checkout exactly ``sha``.

    A full clone is used (not ``--depth 1``) because an arbitrary historical
    SHA may not be a branch tip; after cloning, ``checkout <sha>`` pins the
    exact commit. The repo is left in a detached-HEAD state at the SHA — the
    cache is read-only package content, never developed in.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _git(["clone", "--quiet", url, str(dest)])
    _git(["checkout", "--quiet", sha], cwd=dest)
    head = _git(["rev-parse", "HEAD"], cwd=dest)
    if head.lower() != sha.lower():
        raise RemoteFetchError(
            f"checkout of {sha} in {url} landed on {head} — refusing"
        )


def to_lock_entry(
    fetched: FetchedPackage,
    *,
    signature: str = "",
    installed_kernel_event_id: str = "",
) -> LockEntry:
    """Build the lockfile entry that records this fetch reproducibly."""
    return LockEntry(
        name=fetched.manifest.name,
        version=fetched.manifest.version,
        source_url=fetched.source.url,
        resolved_sha=fetched.resolved_sha,
        content_hash=fetched.content_hash,
        subdir=fetched.source.subdir,
        signature=signature,
        installed_kernel_event_id=installed_kernel_event_id,
    )


def fetch_and_lock(
    source: RemotePackageSource,
    org_root: Path,
    *,
    cache_root: Path | None = None,
    force: bool = False,
    signature: str = "",
    installed_kernel_event_id: str = "",
) -> tuple[FetchedPackage, Lockfile]:
    """Fetch a remote package and record it in the org's lockfile.

    This is the intended one-call entry point: fetch + lock ship together
    (O3-P3), so a fetch never leaves the org without a reproducibility record.
    The cache defaults to ``<org>/.cognitive-firm/pkg-cache/``.

    Returns the :class:`FetchedPackage` and the updated :class:`Lockfile`.
    Does **not** install the package — that is a separate, governed step in
    another lane.
    """
    org_root = Path(org_root)
    if cache_root is None:
        cache_root = org_root / PKG_CACHE_DIRNAME
    fetched = fetch_package(source, cache_root, force=force)
    entry = to_lock_entry(
        fetched,
        signature=signature,
        installed_kernel_event_id=installed_kernel_event_id,
    )
    lockfile = lock_package(org_root, entry)
    return fetched, lockfile
