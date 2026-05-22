"""Distribution-layer package manifests.

A *package* is a versioned, installable bundle of overlay files. Two kinds:

- ``distro``  - a curated, day-one-runnable starter organization.
- ``overlay`` - an add-on overlay (extra roles, mandates, protocols) installed
  on top of an existing organization.

This is the userland/distribution layer of the OS analogy: the kernel stays
generic and is never edited by an adopter; a distro composes a runnable
organization an operator installs in one action. See
``docs/protocols/distribution.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = 1
PACKAGE_KINDS = ("distro", "overlay")
FILES_DIRNAME = "files"

# Overlay-composition intent for a component (O3-P2):
#   add     - install a new file; a pre-existing dest is a conflict (default,
#             the historical behavior).
#   replace - own the file outright; a pre-existing dest is expected and
#             overwritten.
#   patch   - the component source is an RFC 7386 JSON Merge Patch applied to
#             an existing JSON/YAML target file.
COMPONENT_OPS = ("add", "replace", "patch")

# File extensions a `patch` component may target — Merge Patch needs a
# structured (object/map) document to merge into.
PATCH_TARGET_SUFFIXES = (".json", ".yaml", ".yml")


class ManifestError(ValueError):
    """Raised when a package manifest cannot be loaded or is malformed."""


def _escapes(rel: str) -> bool:
    """True if a package-relative path would escape its root."""
    return rel.startswith(("/", "..")) or ".." in Path(rel).parts


@dataclass(frozen=True)
class KernelCompat:
    """Declared kernel-version range a package supports."""

    min_version: str | None = None
    max_version: str | None = None

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> "KernelCompat":
        raw = raw or {}
        return cls(
            min_version=raw.get("min_version"),
            max_version=raw.get("max_version"),
        )


@dataclass(frozen=True)
class Component:
    """One installable unit: a directory or file under the package's files/.

    ``op`` is the overlay-composition intent — see ``COMPONENT_OPS``.
    """

    source: str  # package-relative path under files/
    dest: str  # target-relative install path
    optional: bool = False
    op: str = "add"

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "Component":
        if not isinstance(raw, dict) or "source" not in raw:
            raise ManifestError("component is missing 'source'")
        source = str(raw["source"]).strip()
        return cls(
            source=source,
            dest=str(raw.get("dest", source)).strip(),
            optional=bool(raw.get("optional", False)),
            op=(str(raw.get("op", "add")).strip() or "add"),
        )


@dataclass(frozen=True)
class PackageManifest:
    """A parsed ``package.yaml``."""

    name: str
    version: str
    kind: str
    description: str
    components: tuple[Component, ...]
    kernel: KernelCompat = field(default_factory=KernelCompat)
    provides: tuple[str, ...] = ()
    post_install_message: str = ""
    extends: str | None = None  # O3-P5: a base distro this package extends
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_raw(cls, raw: Any) -> "PackageManifest":
        if not isinstance(raw, dict):
            raise ManifestError("manifest must be a YAML mapping")
        components = tuple(
            Component.from_raw(c) for c in (raw.get("components") or [])
        )
        return cls(
            name=str(raw.get("name", "")).strip(),
            version=str(raw.get("version", "")).strip(),
            kind=str(raw.get("kind", "")).strip(),
            description=str(raw.get("description", "")).strip(),
            components=components,
            kernel=KernelCompat.from_raw(raw.get("kernel")),
            provides=tuple(str(x) for x in (raw.get("provides") or [])),
            post_install_message=str(raw.get("post_install_message", "")),
            extends=(
                str(raw["extends"]).strip() or None
                if raw.get("extends")
                else None
            ),
            schema_version=int(raw.get("schema_version", SCHEMA_VERSION)),
        )


def validate_manifest(
    manifest: PackageManifest, package_root: Path
) -> list[str]:
    """Return structural problems; an empty list means the manifest is sound."""
    issues: list[str] = []
    if manifest.schema_version != SCHEMA_VERSION:
        issues.append(
            f"schema_version {manifest.schema_version} != {SCHEMA_VERSION}"
        )
    if not manifest.name:
        issues.append("name is empty")
    if not manifest.version:
        issues.append("version is empty")
    if manifest.kind not in PACKAGE_KINDS:
        issues.append(f"kind '{manifest.kind}' not in {PACKAGE_KINDS}")
    if len(manifest.description) < 10:
        issues.append("description is too short (min 10 chars)")
    if not manifest.components:
        issues.append("manifest declares no components")

    files_root = Path(package_root) / FILES_DIRNAME
    seen_dests: set[str] = set()
    for component in manifest.components:
        if component.op not in COMPONENT_OPS:
            issues.append(
                f"component op '{component.op}' not in {COMPONENT_OPS}"
            )
        if _escapes(component.source):
            issues.append(
                f"component source escapes package: {component.source}"
            )
            continue
        if _escapes(component.dest):
            issues.append(f"component dest escapes target: {component.dest}")
            continue
        if component.dest in seen_dests:
            issues.append(f"duplicate component dest: {component.dest}")
        seen_dests.add(component.dest)
        if not component.optional and not (files_root / component.source).exists():
            issues.append(f"component source missing: {component.source}")
    return issues


def load_manifest(path: Path) -> PackageManifest:
    """Load and structurally validate a ``package.yaml`` manifest file."""
    path = Path(path)
    if not path.is_file():
        raise ManifestError(f"manifest not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ManifestError(f"YAML parse error in {path}: {exc}") from exc
    manifest = PackageManifest.from_raw(raw or {})
    issues = validate_manifest(manifest, path.parent)
    if issues:
        raise ManifestError(f"invalid manifest {path}: " + "; ".join(issues))
    return manifest


def _parse_version(version: str) -> tuple[int, ...]:
    """Parse a dotted version string into a comparable integer tuple.

    Parsing stops at the first non-numeric segment (e.g. ``1.2.0rc1`` -> (1,2)),
    so a pre-release suffix never raises. An empty/garbage version is (0,).
    """
    parts: list[int] = []
    for segment in str(version).strip().split("."):
        segment = segment.strip()
        try:
            parts.append(int(segment))
        except ValueError:
            break
    return tuple(parts) or (0,)


def check_kernel_compat(
    kernel: KernelCompat, kernel_version: str
) -> list[str]:
    """Return reasons the running kernel is outside a package's declared range.

    An empty list means compatible. Used as the install-time version gate
    (spec G1).
    """
    issues: list[str] = []
    running = _parse_version(kernel_version)
    if kernel.min_version and running < _parse_version(kernel.min_version):
        issues.append(
            f"kernel {kernel_version} is below the package minimum "
            f"{kernel.min_version}"
        )
    if kernel.max_version and running > _parse_version(kernel.max_version):
        issues.append(
            f"kernel {kernel_version} is above the package maximum "
            f"{kernel.max_version}"
        )
    return issues
