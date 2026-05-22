"""Tests for the O3-P3 remote registry and lockfile.

Remote packages are fetched from a git URL and pinned by commit SHA; the
lockfile makes a later install reproducible and detects a force-pushed tag.
A local file path is a valid git-cloneable URL, so these tests build real
throwaway git repos under ``tmp_path`` — no network.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from cognitive_firm.distribution.lockfile import (
    LockEntry,
    Lockfile,
    LockError,
    LockMismatch,
    hash_directory,
    lock_package,
    lockfile_path,
    read_lockfile,
    verify_against_lock,
    write_lockfile,
)
from cognitive_firm.distribution.registry import RegistryEntry, remote_entry
from cognitive_firm.distribution.remote_registry import (
    PKG_CACHE_DIRNAME,
    FetchedPackage,
    RemoteFetchError,
    RemotePackageSource,
    cache_dir_for,
    fetch_and_lock,
    fetch_package,
    resolve_ref,
    to_lock_entry,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTER = REPO_ROOT / "distro" / "starter-firm"

_GIT_ENV = (
    "-c",
    "user.name=test",
    "-c",
    "user.email=test@test.local",
)


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _make_package_repo(
    repo_dir: Path,
    *,
    subdir: str = "",
    second_commit: bool = False,
) -> dict[str, str]:
    """Create a git repo containing a copy of the starter-firm package.

    If ``subdir`` is given the package is placed under that path. Returns a
    dict of ref-name -> SHA, including ``v1`` (a tag) and, if requested,
    ``head2`` (a second commit's SHA).
    """
    repo_dir.mkdir(parents=True, exist_ok=True)
    _git(["init", "--quiet"], repo_dir)
    pkg_dest = repo_dir / subdir if subdir else repo_dir
    pkg_dest.mkdir(parents=True, exist_ok=True)
    for item in STARTER.iterdir():
        target = pkg_dest / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copyfile(item, target)
    _git(["add", "-A"], repo_dir)
    _git([*_GIT_ENV, "commit", "--quiet", "-m", "initial"], repo_dir)
    _git(["tag", "v1"], repo_dir)
    refs = {"v1": _git(["rev-parse", "HEAD"], repo_dir)}
    if second_commit:
        marker = pkg_dest / "files" / "EXTRA.md"
        marker.write_text("second commit content\n")
        _git(["add", "-A"], repo_dir)
        _git([*_GIT_ENV, "commit", "--quiet", "-m", "second"], repo_dir)
        refs["head2"] = _git(["rev-parse", "HEAD"], repo_dir)
    return refs


# --------------------------------------------------------------------------
# lockfile primitives
# --------------------------------------------------------------------------


def test_hash_directory_is_stable_and_content_sensitive(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "f.txt").write_text("hello")
    (b / "f.txt").write_text("hello")
    assert hash_directory(a) == hash_directory(b)
    assert hash_directory(a).startswith("sha256:")
    (b / "f.txt").write_text("hello!")
    assert hash_directory(a) != hash_directory(b)


def test_hash_directory_excludes_git_and_receipt_dir(tmp_path):
    d = tmp_path / "pkg"
    d.mkdir()
    (d / "f.txt").write_text("payload")
    before = hash_directory(d)
    (d / ".git").mkdir()
    (d / ".git" / "junk").write_text("git internals")
    (d / ".cognitive-firm").mkdir()
    (d / ".cognitive-firm" / "lock").write_text("receipt")
    assert hash_directory(d) == before


def test_lock_entry_rejects_a_non_sha_pin():
    with pytest.raises(LockError):
        LockEntry(
            name="p",
            version="1",
            source_url="u",
            resolved_sha="v1.0",  # a tag, not a 40-char SHA
            content_hash="sha256:x",
        )


def test_lock_entry_requires_a_content_hash():
    with pytest.raises(LockError):
        LockEntry(
            name="p",
            version="1",
            source_url="u",
            resolved_sha="a" * 40,
            content_hash="",
        )


def test_lockfile_roundtrip(tmp_path):
    entry = LockEntry(
        name="starter-firm",
        version="0.1.0",
        source_url="https://example.com/r.git",
        resolved_sha="a" * 40,
        content_hash="sha256:deadbeef",
        subdir="pkg",
        signature="sig",
        installed_kernel_event_id="evt-1",
    )
    write_lockfile(tmp_path, Lockfile(entries=(entry,)))
    assert lockfile_path(tmp_path).is_file()
    loaded = read_lockfile(tmp_path)
    assert loaded.get("starter-firm") == entry
    assert loaded.get("starter-firm").pinned_id == f"starter-firm@{'a' * 40}"


def test_read_lockfile_missing_is_empty(tmp_path):
    assert read_lockfile(tmp_path).entries == ()


def test_lockfile_with_entry_replaces_by_name_and_sorts(tmp_path):
    e1 = LockEntry("zeta", "1", "u", "a" * 40, "sha256:1")
    e2 = LockEntry("alpha", "1", "u", "b" * 40, "sha256:2")
    e1b = LockEntry("zeta", "2", "u", "c" * 40, "sha256:3")
    lf = Lockfile().with_entry(e1).with_entry(e2).with_entry(e1b)
    assert [e.name for e in lf.entries] == ["alpha", "zeta"]
    assert lf.get("zeta").version == "2"
    assert lf.without("alpha").get("alpha") is None


def test_lockfile_rejects_duplicate_names():
    raw = {
        "schema_version": 1,
        "packages": [
            {"name": "p", "resolved_sha": "a" * 40, "content_hash": "h"},
            {"name": "p", "resolved_sha": "b" * 40, "content_hash": "h"},
        ],
    }
    with pytest.raises(LockError):
        Lockfile.from_dict(raw)


def test_lockfile_rejects_bad_schema_version():
    with pytest.raises(LockError):
        Lockfile.from_dict({"schema_version": 99, "packages": []})


def test_lock_package_persists(tmp_path):
    entry = LockEntry("p", "1", "u", "a" * 40, "sha256:h")
    lock_package(tmp_path, entry)
    assert read_lockfile(tmp_path).get("p") == entry


def test_verify_against_lock_passes_on_match(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "f.txt").write_text("content")
    entry = LockEntry("p", "1", "u", "a" * 40, hash_directory(pkg))
    lock_package(tmp_path, entry)
    assert verify_against_lock(tmp_path, "p", pkg) == entry


def test_verify_against_lock_detects_changed_content(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "f.txt").write_text("original")
    lock_package(tmp_path, LockEntry("p", "1", "u", "a" * 40, hash_directory(pkg)))
    (pkg / "f.txt").write_text("force-pushed")  # same SHA, different content
    with pytest.raises(LockMismatch):
        verify_against_lock(tmp_path, "p", pkg)


def test_verify_against_lock_errors_when_not_locked(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "f.txt").write_text("x")
    with pytest.raises(LockError):
        verify_against_lock(tmp_path, "missing", pkg)


# --------------------------------------------------------------------------
# remote fetch
# --------------------------------------------------------------------------


def test_resolve_ref_resolves_a_tag_to_a_full_sha(tmp_path):
    repo = tmp_path / "repo"
    refs = _make_package_repo(repo)
    sha = resolve_ref(str(repo), "v1")
    assert sha == refs["v1"]
    assert len(sha) == 40


def test_resolve_ref_passes_through_a_full_sha(tmp_path):
    repo = tmp_path / "repo"
    refs = _make_package_repo(repo)
    assert resolve_ref(str(repo), refs["v1"]) == refs["v1"]


def test_resolve_ref_rejects_an_unknown_ref(tmp_path):
    repo = tmp_path / "repo"
    _make_package_repo(repo)
    with pytest.raises(RemoteFetchError):
        resolve_ref(str(repo), "no-such-tag")


def test_fetch_package_pins_to_a_commit_sha(tmp_path):
    repo = tmp_path / "repo"
    refs = _make_package_repo(repo)
    cache = tmp_path / "cache"
    fetched = fetch_package(RemotePackageSource(url=str(repo), ref="v1"), cache)
    assert isinstance(fetched, FetchedPackage)
    assert fetched.resolved_sha == refs["v1"]
    assert fetched.manifest.name == "starter-firm"
    assert fetched.pinned_id == f"starter-firm@{refs['v1']}"
    assert (fetched.package_root / "package.yaml").is_file()
    assert fetched.content_hash.startswith("sha256:")


def test_fetch_package_uses_a_sha_keyed_cache(tmp_path):
    repo = tmp_path / "repo"
    refs = _make_package_repo(repo)
    cache = tmp_path / "cache"
    fetch_package(RemotePackageSource(url=str(repo), ref="v1"), cache)
    assert cache_dir_for(cache, refs["v1"]).is_dir()
    # A second fetch of the same SHA reuses the cache (no re-clone needed).
    again = fetch_package(RemotePackageSource(url=str(repo), ref="v1"), cache)
    assert again.resolved_sha == refs["v1"]


def test_fetch_package_from_a_subdirectory(tmp_path):
    repo = tmp_path / "repo"
    refs = _make_package_repo(repo, subdir="packages/starter")
    cache = tmp_path / "cache"
    fetched = fetch_package(
        RemotePackageSource(
            url=str(repo), ref="v1", subdir="packages/starter"
        ),
        cache,
    )
    assert fetched.resolved_sha == refs["v1"]
    assert fetched.manifest.name == "starter-firm"


def test_fetch_package_errors_on_missing_manifest(tmp_path):
    repo = tmp_path / "repo"
    _make_package_repo(repo)
    cache = tmp_path / "cache"
    with pytest.raises(RemoteFetchError):
        fetch_package(
            RemotePackageSource(url=str(repo), ref="v1", subdir="nope"),
            cache,
        )


def test_remote_source_rejects_an_escaping_subdir():
    with pytest.raises(RemoteFetchError):
        RemotePackageSource(url="u", subdir="../escape")


def test_moved_tag_resolves_to_a_different_sha(tmp_path):
    """A force-pushed/moved tag is detected: v1 now points elsewhere."""
    repo = tmp_path / "repo"
    refs = _make_package_repo(repo, second_commit=True)
    first_sha = resolve_ref(str(repo), "v1")
    assert first_sha == refs["v1"]
    # Move the tag forward, as a force-push would.
    _git(["tag", "-f", "v1", refs["head2"]], repo)
    moved_sha = resolve_ref(str(repo), "v1")
    assert moved_sha == refs["head2"]
    assert moved_sha != first_sha


# --------------------------------------------------------------------------
# fetch + lockfile together
# --------------------------------------------------------------------------


def test_fetch_and_lock_writes_a_reproducible_lock_entry(tmp_path):
    repo = tmp_path / "repo"
    refs = _make_package_repo(repo)
    org = tmp_path / "org"
    org.mkdir()
    fetched, lockfile = fetch_and_lock(
        RemotePackageSource(url=str(repo), ref="v1"), org
    )
    entry = lockfile.get("starter-firm")
    assert entry is not None
    assert entry.resolved_sha == refs["v1"]
    assert entry.source_url == str(repo)
    assert entry.content_hash == fetched.content_hash
    # The lockfile is persisted under the org's .cognitive-firm dir.
    assert lockfile_path(org).is_file()
    assert read_lockfile(org).get("starter-firm") == entry


def test_fetch_and_lock_default_cache_is_under_the_org(tmp_path):
    repo = tmp_path / "repo"
    refs = _make_package_repo(repo)
    org = tmp_path / "org"
    org.mkdir()
    fetch_and_lock(RemotePackageSource(url=str(repo), ref="v1"), org)
    assert (org / PKG_CACHE_DIRNAME / refs["v1"]).is_dir()


def test_fetched_content_verifies_against_its_own_lock(tmp_path):
    repo = tmp_path / "repo"
    _make_package_repo(repo)
    org = tmp_path / "org"
    org.mkdir()
    fetched, _ = fetch_and_lock(
        RemotePackageSource(url=str(repo), ref="v1"), org
    )
    # A re-verify of the same fetched content passes.
    entry = verify_against_lock(org, "starter-firm", fetched.package_root)
    assert entry.content_hash == fetched.content_hash


def test_lock_then_tampered_refetch_is_a_hard_error(tmp_path):
    """The force-push case: same SHA recorded, but content changed underneath."""
    repo = tmp_path / "repo"
    _make_package_repo(repo)
    org = tmp_path / "org"
    org.mkdir()
    fetched, _ = fetch_and_lock(
        RemotePackageSource(url=str(repo), ref="v1"), org
    )
    # Simulate the SHA's content being rewritten in the cache.
    (fetched.package_root / "TAMPERED.txt").write_text("malicious overlay\n")
    with pytest.raises(LockMismatch):
        verify_against_lock(org, "starter-firm", fetched.package_root)


def test_to_lock_entry_carries_signature_and_event_id(tmp_path):
    repo = tmp_path / "repo"
    _make_package_repo(repo)
    cache = tmp_path / "cache"
    fetched = fetch_package(RemotePackageSource(url=str(repo), ref="v1"), cache)
    entry = to_lock_entry(
        fetched, signature="sig-abc", installed_kernel_event_id="evt-9"
    )
    assert entry.signature == "sig-abc"
    assert entry.installed_kernel_event_id == "evt-9"
    assert entry.resolved_sha == fetched.resolved_sha


# --------------------------------------------------------------------------
# registry helper
# --------------------------------------------------------------------------


def test_remote_entry_marks_a_package_as_remote(tmp_path):
    repo = tmp_path / "repo"
    refs = _make_package_repo(repo)
    cache = tmp_path / "cache"
    fetched = fetch_package(RemotePackageSource(url=str(repo), ref="v1"), cache)
    entry = remote_entry(
        root=fetched.package_root,
        manifest=fetched.manifest,
        source_url=str(repo),
        resolved_sha=fetched.resolved_sha,
    )
    assert isinstance(entry, RegistryEntry)
    assert entry.is_remote
    assert entry.pinned_id == f"starter-firm@{refs['v1']}"


def test_local_registry_entry_is_not_remote():
    from cognitive_firm.distribution.manifest import load_manifest

    manifest = load_manifest(STARTER / "package.yaml")
    entry = RegistryEntry(root=STARTER, manifest=manifest)
    assert not entry.is_remote
    assert entry.pinned_id == f"starter-firm@{manifest.version}"
