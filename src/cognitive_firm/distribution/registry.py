"""Distribution-layer package registry.

A registry is a directory of packages, each in its own subdirectory with a
``package.yaml`` manifest. This is the seed of the package/overlay ecosystem:
``discover_packages`` indexes a registry so an operator can list, inspect, and
install distros and overlays without knowing their on-disk layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cognitive_firm.distribution.manifest import (
    ManifestError,
    PackageManifest,
    load_manifest,
)

MANIFEST_FILENAME = "package.yaml"


@dataclass(frozen=True)
class RegistryEntry:
    """One indexed package: its directory and parsed manifest.

    ``source_url`` and ``resolved_sha`` are populated for a package that was
    fetched from a remote git repo (O3-P3); they are empty for a package
    discovered from a purely local registry directory. When ``resolved_sha``
    is set, the package's immutable identity is ``name@<sha>`` (see
    :attr:`pinned_id`).
    """

    root: Path
    manifest: PackageManifest
    source_url: str = ""
    resolved_sha: str = ""

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def is_remote(self) -> bool:
        """True if this entry came from a remote git source."""
        return bool(self.source_url and self.resolved_sha)

    @property
    def pinned_id(self) -> str:
        """The immutable ``name@<sha>`` identity for a remote-fetched package.

        For a local package (no resolved SHA) this falls back to
        ``name@<version>`` — local packages have no commit pin.
        """
        if self.resolved_sha:
            return f"{self.name}@{self.resolved_sha}"
        return f"{self.name}@{self.manifest.version}"


@dataclass(frozen=True)
class PackageIndex:
    """The result of indexing a registry directory."""

    entries: tuple[RegistryEntry, ...]
    errors: tuple[str, ...] = ()

    def get(self, name: str) -> RegistryEntry | None:
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None

    def of_kind(self, kind: str) -> tuple[RegistryEntry, ...]:
        return tuple(e for e in self.entries if e.manifest.kind == kind)


def discover_packages(registry_root: Path) -> PackageIndex:
    """Index every package directory under ``registry_root``.

    A package directory is any immediate child holding a ``package.yaml``.
    Malformed manifests are recorded in ``errors`` rather than raised, so one
    bad package does not hide the rest of the registry.
    """
    registry_root = Path(registry_root)
    if not registry_root.is_dir():
        return PackageIndex(
            entries=(), errors=(f"registry not found: {registry_root}",)
        )

    entries: list[RegistryEntry] = []
    errors: list[str] = []
    seen: set[str] = set()
    for child in sorted(registry_root.iterdir()):
        manifest_path = child / MANIFEST_FILENAME
        if not manifest_path.is_file():
            continue
        try:
            manifest = load_manifest(manifest_path)
        except ManifestError as exc:
            errors.append(str(exc))
            continue
        if manifest.name in seen:
            errors.append(f"duplicate package name: {manifest.name}")
            continue
        seen.add(manifest.name)
        entries.append(RegistryEntry(root=child, manifest=manifest))
    return PackageIndex(entries=tuple(entries), errors=tuple(errors))


def remote_entry(
    *,
    root: Path,
    manifest: PackageManifest,
    source_url: str,
    resolved_sha: str,
) -> RegistryEntry:
    """Build a ``RegistryEntry`` for a package fetched from a remote git repo.

    A read-only, additive convenience so a remote fetch (``remote_registry``)
    and a local ``discover_packages`` index share one entry type. ``root`` is
    the cached package directory; ``source_url``/``resolved_sha`` carry the
    git URL and the 40-char commit pin.
    """
    return RegistryEntry(
        root=Path(root),
        manifest=manifest,
        source_url=source_url,
        resolved_sha=resolved_sha,
    )
