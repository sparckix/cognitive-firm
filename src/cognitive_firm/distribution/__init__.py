"""Distribution layer: distros, overlays, and the installer.

The kernel is generic and an adopter never edits it. This layer is the
"userland" of the OS analogy: a *distro* composes a day-one-runnable governed
organization that an operator installs in one action. See
``docs/protocols/distribution.md``.
"""

from cognitive_firm.distribution.installer import (
    InstalledFile,
    InstallReceipt,
    install,
    load_receipt,
    plan_install,
    verify_install,
)
from cognitive_firm.distribution.manifest import (
    Component,
    KernelCompat,
    ManifestError,
    PackageManifest,
    load_manifest,
    validate_manifest,
)
from cognitive_firm.distribution.registry import (
    PackageIndex,
    RegistryEntry,
    discover_packages,
)

__all__ = [
    "Component",
    "InstallReceipt",
    "InstalledFile",
    "KernelCompat",
    "ManifestError",
    "PackageIndex",
    "PackageManifest",
    "RegistryEntry",
    "discover_packages",
    "install",
    "load_manifest",
    "load_receipt",
    "plan_install",
    "validate_manifest",
    "verify_install",
]
