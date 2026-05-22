"""Distribution layer: distros, overlays, the installer, and rollback.

The kernel is generic and an adopter never edits it. This layer is the
"userland" of the OS analogy: a *distro* composes a day-one-runnable governed
organization that an operator installs in one action, transactionally and
git-backed, and can roll back. See ``docs/protocols/distribution.md``.
"""

from cognitive_firm.distribution.boot import boot_check
from cognitive_firm.distribution.installer import (
    InstalledFile,
    InstallError,
    InstallReceipt,
    install,
    load_receipt,
    plan_install,
    record_distribution_event,
    upgrade,
    verify_install,
)
from cognitive_firm.distribution.manifest import (
    Component,
    KernelCompat,
    ManifestError,
    PackageManifest,
    check_kernel_compat,
    load_manifest,
    validate_manifest,
)
from cognitive_firm.distribution.registry import (
    PackageIndex,
    RegistryEntry,
    discover_packages,
)
from cognitive_firm.distribution.rollback import (
    RollbackError,
    RollbackResult,
    rollback,
)

__all__ = [
    "Component",
    "InstallError",
    "InstallReceipt",
    "InstalledFile",
    "KernelCompat",
    "ManifestError",
    "PackageIndex",
    "PackageManifest",
    "RegistryEntry",
    "RollbackError",
    "RollbackResult",
    "boot_check",
    "check_kernel_compat",
    "discover_packages",
    "install",
    "load_manifest",
    "load_receipt",
    "plan_install",
    "record_distribution_event",
    "rollback",
    "upgrade",
    "validate_manifest",
    "verify_install",
]
