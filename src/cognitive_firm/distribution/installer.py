"""Distribution-layer installer.

Materializes a package (see ``manifest.py``) into a target organization
directory, records an install receipt, and verifies the result boots.

The installer never touches the kernel. It only writes overlay files the
adopter owns, so the installed organization stays inspectable, forkable, and
replayable.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import yaml

from cognitive_firm.distribution.manifest import FILES_DIRNAME, PackageManifest

RECEIPT_DIRNAME = ".cognitive-firm"

# Top-level keys every installed role.yaml must carry (role.v1 schema).
_ROLE_REQUIRED_KEYS = (
    "schema_version",
    "role_id",
    "role_class",
    "description",
    "authorized_paths",
    "forbidden_paths",
    "delegates_to",
    "escalates_to",
    "budget",
)


@dataclass(frozen=True)
class InstalledFile:
    """One file the installer considered, and what it did with it."""

    dest: str
    action: str  # "created" | "overwritten" | "skipped"


@dataclass(frozen=True)
class InstallReceipt:
    """The durable record of one install, written under the target."""

    package: str
    version: str
    kind: str
    installed_at: str
    target_root: str
    files: tuple[InstalledFile, ...]
    skipped_conflicts: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "package": self.package,
            "version": self.version,
            "kind": self.kind,
            "installed_at": self.installed_at,
            "target_root": self.target_root,
            "files": [{"dest": f.dest, "action": f.action} for f in self.files],
            "skipped_conflicts": list(self.skipped_conflicts),
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
        )


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


def install(
    manifest: PackageManifest,
    package_root: Path,
    target_root: Path,
    *,
    force: bool = False,
) -> InstallReceipt:
    """Install a package into ``target_root`` and write an install receipt.

    Existing files are skipped unless ``force`` is set, so an install never
    silently clobbers an adopter's edits.
    """
    target_root = Path(target_root)
    plan = plan_install(manifest, package_root, target_root)

    installed: list[InstalledFile] = []
    skipped: list[str] = []
    for src_file, dest_rel, conflict in plan:
        if conflict and not force:
            skipped.append(dest_rel)
            installed.append(InstalledFile(dest_rel, "skipped"))
            continue
        dest_path = target_root / dest_rel
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_file, dest_path)
        installed.append(
            InstalledFile(dest_rel, "overwritten" if conflict else "created")
        )

    receipt = InstallReceipt(
        package=manifest.name,
        version=manifest.version,
        kind=manifest.kind,
        installed_at=datetime.now(timezone.utc).isoformat(),
        target_root=str(target_root.resolve()),
        files=tuple(installed),
        skipped_conflicts=tuple(skipped),
    )
    receipt_dir = target_root / RECEIPT_DIRNAME
    receipt_dir.mkdir(parents=True, exist_ok=True)
    (receipt_dir / f"install-{manifest.name}.json").write_text(
        json.dumps(receipt.as_dict(), indent=2) + "\n"
    )
    return receipt


def load_receipt(target_root: Path, package: str) -> InstallReceipt:
    """Load the install receipt for ``package`` from a target directory."""
    path = Path(target_root) / RECEIPT_DIRNAME / f"install-{package}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no install receipt for '{package}' at {path}")
    return InstallReceipt.from_dict(json.loads(path.read_text()))


def verify_install(receipt: InstallReceipt, target_root: Path) -> list[str]:
    """Boot-proxy check over an installed organization.

    This is a structural check, not a full kernel boot. It confirms every
    non-skipped file landed, each installed ``roles/*.yaml`` parses and carries
    the role.v1 required keys, and each role's ``mandate_path`` resolves inside
    the target. An empty list means the organization is structurally bootable.
    """
    target_root = Path(target_root)
    issues: list[str] = []

    for f in receipt.files:
        if f.action == "skipped":
            continue
        if not (target_root / f.dest).is_file():
            issues.append(f"installed file is missing: {f.dest}")

    roles_dir = target_root / "roles"
    role_files = sorted(roles_dir.glob("*.yaml")) if roles_dir.is_dir() else []
    if not role_files:
        issues.append("no role files under roles/ - organization cannot boot")
    for role_file in role_files:
        try:
            role = yaml.safe_load(role_file.read_text())
        except yaml.YAMLError as exc:
            issues.append(f"role {role_file.name} does not parse: {exc}")
            continue
        if not isinstance(role, dict):
            issues.append(f"role {role_file.name} is not a mapping")
            continue
        missing = [k for k in _ROLE_REQUIRED_KEYS if k not in role]
        if missing:
            issues.append(
                f"role {role_file.name} missing keys: {', '.join(missing)}"
            )
        mandate_path = role.get("mandate_path")
        if mandate_path and not (target_root / mandate_path).is_file():
            issues.append(
                f"role {role_file.name} mandate_path does not resolve: "
                f"{mandate_path}"
            )
    return issues
