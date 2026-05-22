"""Distribution-layer installer.

Materializes a package into a target organization directory, records an
install receipt, and verifies the result boots.

Each install is transactional and git-backed: the installer ensures the target
is its own git repo, applies the package, verifies the org boots, then commits
and tags the result (spec R1/G11). A failed install leaves the target as it
was. The installer never touches the kernel — only overlay files the adopter
owns, so the installed org stays inspectable, forkable, and replayable.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import yaml

import cognitive_firm
from cognitive_firm.distribution import gitops
from cognitive_firm.distribution.boot import boot_check
from cognitive_firm.distribution.manifest import (
    FILES_DIRNAME,
    PATCH_TARGET_SUFFIXES,
    PackageManifest,
    check_kernel_compat,
)
from cognitive_firm.distribution.signing import (
    SigningError,
    verify_against_trust_store,
)
from cognitive_firm.orchestration.kernel_events import (
    append_kernel_event,
    create_kernel_event,
)

RECEIPT_DIRNAME = ".cognitive-firm"
DISTRIBUTION_EVENTS_LOG = "distribution-events.jsonl"


class InstallError(RuntimeError):
    """Raised when an install cannot proceed or did not produce a bootable org."""


@dataclass(frozen=True)
class InstalledFile:
    """One file the installer considered, and what it did with it."""

    dest: str
    action: str  # "created" | "overwritten" | "skipped"


@dataclass(frozen=True)
class InstallReceipt:
    """The durable record of one install, written under the target.

    ``pre_install_ref`` / ``commit_sha`` / ``git_tag`` are the install boundary
    (spec R1): the git refs rollback uses to undo this install.
    """

    package: str
    version: str
    kind: str
    installed_at: str
    target_root: str
    files: tuple[InstalledFile, ...]
    skipped_conflicts: tuple[str, ...] = ()
    pre_install_ref: str | None = None
    commit_sha: str = ""
    git_tag: str = ""
    signature_verified: bool = False  # O3-P1(4): provenance outcome

    def as_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "version": self.version,
            "kind": self.kind,
            "installed_at": self.installed_at,
            "target_root": self.target_root,
            "files": [{"dest": f.dest, "action": f.action} for f in self.files],
            "skipped_conflicts": list(self.skipped_conflicts),
            "pre_install_ref": self.pre_install_ref,
            "commit_sha": self.commit_sha,
            "git_tag": self.git_tag,
            "signature_verified": self.signature_verified,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "InstallReceipt":
        return cls(
            package=raw["package"],
            version=raw["version"],
            kind=raw["kind"],
            installed_at=raw["installed_at"],
            target_root=raw["target_root"],
            files=tuple(
                InstalledFile(f["dest"], f["action"])
                for f in raw.get("files", [])
            ),
            skipped_conflicts=tuple(raw.get("skipped_conflicts", [])),
            pre_install_ref=raw.get("pre_install_ref"),
            commit_sha=raw.get("commit_sha", ""),
            git_tag=raw.get("git_tag", ""),
            signature_verified=bool(raw.get("signature_verified", False)),
        )


def record_distribution_event(
    target_root: Path,
    *,
    actor: str,
    verb: str,
    package: str,
    payload: dict[str, Any],
) -> None:
    """Append a typed kernel event for an install-layer action.

    The event uses the canonical ``KernelEvent`` envelope and lands in the
    org's distribution event log (``.cognitive-firm/distribution-events.jsonl``)
    — the attested, append-only trail of installs, upgrades, and rollbacks.
    """
    event = create_kernel_event(
        actor=actor,
        verb=verb,
        object_ref=f"package:{package}",
        payload=payload,
    )
    log_path = Path(target_root) / RECEIPT_DIRNAME / DISTRIBUTION_EVENTS_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    append_kernel_event(event, log_path=log_path)


def _iter_files(src: Path, dest_prefix: str) -> Iterator[tuple[Path, str]]:
    """Yield (source_file, target-relative path) for one component."""
    if src.is_file():
        yield src, dest_prefix
        return
    for child in sorted(src.rglob("*")):
        if child.is_file():
            rel = child.relative_to(src).as_posix()
            yield child, f"{dest_prefix}/{rel}"


def plan_install(
    manifest: PackageManifest, package_root: Path, target_root: Path
) -> list[tuple[Path, str, bool]]:
    """Resolve a manifest into (source_file, dest_relative, conflict) tuples."""
    files_root = Path(package_root) / FILES_DIRNAME
    target_root = Path(target_root)
    plan: list[tuple[Path, str, bool]] = []
    for component in manifest.components:
        src = files_root / component.source
        if not src.exists():
            if component.optional:
                continue
            raise FileNotFoundError(
                f"component source missing: {component.source}"
            )
        for src_file, dest_rel in _iter_files(src, component.dest):
            conflict = (target_root / dest_rel).exists()
            plan.append((src_file, dest_rel, conflict))
    return plan


def _component_files(
    manifest: PackageManifest, package_root: Path, target_root: Path
) -> Iterator[tuple[Path, str, bool, str]]:
    """Yield (source_file, dest_relative, conflict, op) for every file to
    install — the op-aware plan the installer applies (O3-P2)."""
    files_root = Path(package_root) / FILES_DIRNAME
    target_root = Path(target_root)
    for component in manifest.components:
        src = files_root / component.source
        if not src.exists():
            if component.optional:
                continue
            raise FileNotFoundError(
                f"component source missing: {component.source}"
            )
        for src_file, dest_rel in _iter_files(src, component.dest):
            conflict = (target_root / dest_rel).exists()
            yield src_file, dest_rel, conflict, component.op


def _merge_patch(target: Any, patch: Any) -> Any:
    """Apply an RFC 7386 JSON Merge Patch to a document. A `null` value in the
    patch deletes the key; a non-object patch replaces the target outright."""
    if not isinstance(patch, dict):
        return patch
    base = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            base.pop(key, None)
        else:
            base[key] = _merge_patch(base.get(key), value)
    return base


def _load_structured(path: Path) -> Any:
    text = Path(path).read_text()
    if Path(path).suffix == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _apply_merge_patch(patch_file: Path, target_file: Path) -> None:
    """Merge the patch document at ``patch_file`` into ``target_file`` in place,
    preserving the target's JSON/YAML encoding."""
    if target_file.suffix not in PATCH_TARGET_SUFFIXES:
        raise InstallError(
            f"a patch component may only target JSON/YAML: {target_file.name}"
        )
    merged = _merge_patch(
        _load_structured(target_file), _load_structured(patch_file)
    )
    if target_file.suffix == ".json":
        target_file.write_text(json.dumps(merged, indent=2) + "\n")
    else:
        target_file.write_text(yaml.safe_dump(merged, sort_keys=False))


def _ensure_gitignore(target_root: Path) -> None:
    """Ensure the install-receipt directory is never committed into the org."""
    gitignore = target_root / ".gitignore"
    line = f"{RECEIPT_DIRNAME}/"
    existing = gitignore.read_text() if gitignore.is_file() else ""
    if line in existing.splitlines():
        return
    with gitignore.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(line + "\n")


def _undo_failed_install(
    target_root: Path,
    *,
    target_existed: bool,
    pre_install_ref: str | None,
    created: list[str],
    original_bytes: dict[str, bytes],
) -> None:
    """Restore the target after a failed install (the transactional guarantee).

    If the target did not exist before, it is removed entirely. Otherwise:

    - With a pre-install ref (branch 2), a ``git reset --hard`` restores every
      tracked file exactly. A failed reset is *not* swallowed (F-3): it is
      re-raised so the operator learns the target may be inconsistent.
    - With no pre-install ref (branch 3 — the target existed but was not yet a
      committed git repo), there is nothing to reset to, so each file the
      installer mutated is restored from a byte snapshot captured before the
      mutation (F-1): patched and overwritten files alike.

    Newly created (untracked) files are then deleted precisely — no
    ``git clean``, so an adopter's unrelated untracked files are never touched.
    """
    if not target_existed:
        shutil.rmtree(target_root, ignore_errors=True)
        return
    if pre_install_ref is not None:
        try:
            gitops.reset_hard(target_root, pre_install_ref)
        except gitops.GitError as exc:
            raise InstallError(
                "install failed AND the target could not be restored to its "
                f"pre-install state ({pre_install_ref}): {exc}. The target "
                "may be in an inconsistent state and needs manual recovery."
            ) from exc
    else:
        # Branch 3: no commit to reset to — restore each mutated file from the
        # byte snapshot captured before it was patched or overwritten.
        for dest_rel, original in original_bytes.items():
            (target_root / dest_rel).write_bytes(original)
    for dest_rel in created:
        path = target_root / dest_rel
        if path.is_file():
            path.unlink()


def _verify_signature(
    manifest: PackageManifest, package_root: Path, target_root: Path
) -> bool:
    """Verify a package's provenance before install (O3-P1 constraint 4).

    If the manifest declares no ``signing`` block the package is *unsigned*:
    returns ``False`` (recorded as ``signature_verified: false``) — unsigned
    packages still install, so existing distros like ``starter-firm`` are never
    broken.

    If the manifest declares ``signing``, the detached Ed25519 signature is
    verified against the publisher's key in the target org's local trust store
    (``.cognitive-firm/trusted_publishers/``). A signed package whose signature
    does not check out — a tampered package, the wrong key, or an untrusted
    publisher — is refused with ``InstallError`` *before any file is written*.
    """
    if manifest.signing is None:
        return False
    try:
        verified = verify_against_trust_store(
            package_root,
            manifest.signing.publisher,
            manifest.signing.signature,
            trust_root=target_root,
        )
    except SigningError as exc:
        raise InstallError(
            f"cannot install signed package '{manifest.name}': {exc}"
        ) from exc
    if not verified:
        raise InstallError(
            f"refusing to install '{manifest.name}': its declared signature "
            f"from publisher '{manifest.signing.publisher}' does not verify — "
            f"the package may be tampered or the trusted key is wrong"
        )
    return True


def install(
    manifest: PackageManifest,
    package_root: Path,
    target_root: Path,
    *,
    force: bool = False,
    kernel_version: str | None = None,
) -> InstallReceipt:
    """Install a package into ``target_root``, transactionally and git-backed.

    Refuses with ``InstallError`` if the running kernel is outside the
    package's declared range (G1), or if the resulting org does not boot (G5).
    If the manifest declares a ``signing`` block, the package's Ed25519
    signature is verified against the target's trust store before any mutation
    and a bad signature is refused (O3-P1 constraint 4); an unsigned package
    still installs, with ``signature_verified: false`` on the receipt and
    event. On any failure the target is restored (G11). On success the install
    is a git commit tagged ``install/<package>/<version>`` (R1). Existing files
    are skipped unless ``force`` is set. ``kernel_version`` overrides the
    running kernel version (for tests).
    """
    version = kernel_version or cognitive_firm.__version__
    compat = check_kernel_compat(manifest.kernel, version)
    if compat:
        raise InstallError(
            f"cannot install '{manifest.name}': " + "; ".join(compat)
        )

    signature_verified = _verify_signature(
        manifest, Path(package_root), Path(target_root)
    )

    target_root = Path(target_root)
    target_existed = target_root.exists()
    target_root.mkdir(parents=True, exist_ok=True)

    if not gitops.is_repo(target_root):
        gitops.init_repo(target_root)
    pre_install_ref = gitops.current_ref(target_root)

    installed: list[InstalledFile] = []
    skipped: list[str] = []
    created: list[str] = []
    # Byte snapshots of pre-existing files before they are patched/overwritten,
    # so a failed install can restore them even with no prior git commit (F-1).
    original_bytes: dict[str, bytes] = {}

    def _snapshot(dest_rel: str, dest_path: Path) -> None:
        if dest_rel not in original_bytes and dest_path.is_file():
            original_bytes[dest_rel] = dest_path.read_bytes()

    try:
        for src_file, dest_rel, conflict, op in _component_files(
            manifest, package_root, target_root
        ):
            dest_path = target_root / dest_rel
            if op == "patch":
                if not conflict:
                    raise InstallError(
                        f"patch component targets a missing file: {dest_rel}"
                    )
                _snapshot(dest_rel, dest_path)
                _apply_merge_patch(src_file, dest_path)
                installed.append(InstalledFile(dest_rel, "patched"))
                continue
            if op == "add" and conflict and not force:
                skipped.append(dest_rel)
                installed.append(InstalledFile(dest_rel, "skipped"))
                continue
            # op == "add" (no conflict, or forced) or op == "replace"
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if conflict:
                _snapshot(dest_rel, dest_path)
            shutil.copyfile(src_file, dest_path)
            action = "overwritten" if conflict else "created"
            installed.append(InstalledFile(dest_rel, action))
            if action == "created":
                created.append(dest_rel)

        boot_issues = boot_check(target_root)
        if boot_issues:
            raise InstallError(
                f"installed organization for '{manifest.name}' does not boot: "
                + "; ".join(boot_issues)
            )
    except Exception:
        _undo_failed_install(
            target_root,
            target_existed=target_existed,
            pre_install_ref=pre_install_ref,
            created=created,
            original_bytes=original_bytes,
        )
        raise

    # Commit the install — the boundary rollback undoes from (spec R1).
    _ensure_gitignore(target_root)
    gitops.stage_all(target_root)
    if gitops.has_staged_changes(target_root):
        commit_sha = gitops.commit(
            target_root, f"install {manifest.name} {manifest.version}"
        )
    else:
        commit_sha = gitops.current_ref(target_root) or ""
    git_tag = f"install/{manifest.name}/{manifest.version}"
    if commit_sha:
        gitops.tag(target_root, git_tag)

    receipt = InstallReceipt(
        package=manifest.name,
        version=manifest.version,
        kind=manifest.kind,
        installed_at=datetime.now(timezone.utc).isoformat(),
        target_root=str(target_root.resolve()),
        files=tuple(installed),
        skipped_conflicts=tuple(skipped),
        pre_install_ref=pre_install_ref,
        commit_sha=commit_sha,
        git_tag=git_tag if commit_sha else "",
        signature_verified=signature_verified,
    )
    receipt_dir = target_root / RECEIPT_DIRNAME
    receipt_dir.mkdir(parents=True, exist_ok=True)
    (receipt_dir / f"install-{manifest.name}.json").write_text(
        json.dumps(receipt.as_dict(), indent=2) + "\n"
    )
    record_distribution_event(
        target_root,
        actor="installer",
        verb="package.installed",
        package=manifest.name,
        payload={
            "version": manifest.version,
            "kind": manifest.kind,
            "commit_sha": commit_sha,
            "git_tag": receipt.git_tag,
            "pre_install_ref": pre_install_ref,
            "file_count": len(installed),
            "signature_verified": signature_verified,
        },
    )
    return receipt


def upgrade(
    manifest: PackageManifest,
    package_root: Path,
    target_root: Path,
    *,
    kernel_version: str | None = None,
) -> InstallReceipt:
    """Install a (newer) package version over an existing org.

    An upgrade is a forced install: the new version overwrites the old files,
    commits with the new ``install/<package>/<version>`` tag, and records a
    receipt whose ``pre_install_ref`` is the pre-upgrade HEAD — so a rollback
    after an upgrade returns to the pre-upgrade state.
    """
    return install(
        manifest,
        package_root,
        target_root,
        force=True,
        kernel_version=kernel_version,
    )


def load_receipt(target_root: Path, package: str) -> InstallReceipt:
    """Load the install receipt for ``package`` from a target directory."""
    path = Path(target_root) / RECEIPT_DIRNAME / f"install-{package}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no install receipt for '{package}' at {path}")
    return InstallReceipt.from_dict(json.loads(path.read_text()))


def verify_install(receipt: InstallReceipt, target_root: Path) -> list[str]:
    """Verify an installed organization: files present + governance bootable.

    Confirms every non-skipped file in the receipt landed, then runs
    ``boot_check`` over the target — the org parses, carries the role.v1 keys,
    and has a sound governance graph. An empty list means the install is good.
    """
    target_root = Path(target_root)
    issues: list[str] = []
    for f in receipt.files:
        if f.action == "skipped":
            continue
        if not (target_root / f.dest).is_file():
            issues.append(f"installed file is missing: {f.dest}")
    issues.extend(boot_check(target_root))
    return issues
