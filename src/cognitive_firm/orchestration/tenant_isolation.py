"""Lean tenant-scope checks for app/config overlays."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cognitive_firm.orchestration.actor_identity import ActorContext


@dataclass(frozen=True)
class TenantBoundary:
    tenant_id: str
    root: Path

    def contains(self, path: Path) -> bool:
        root = self.root.resolve()
        candidate = path.resolve()
        return candidate == root or root in candidate.parents


def validate_tenant_ref(
    *,
    actor: ActorContext,
    tenant_id: str,
    path: Path | None = None,
    boundary: TenantBoundary | None = None,
) -> None:
    """Reject cross-tenant actor context or overlay path escapes."""
    if actor.tenant_id and actor.tenant_id != tenant_id:
        raise PermissionError(f"actor tenant {actor.tenant_id!r} cannot access tenant {tenant_id!r}")
    if boundary is not None:
        if boundary.tenant_id != tenant_id:
            raise PermissionError(f"boundary tenant {boundary.tenant_id!r} does not match {tenant_id!r}")
        if path is not None and not boundary.contains(path):
            raise PermissionError(f"path escapes tenant boundary: {path}")


def tenant_overlay_root(root: Path, tenant_id: str) -> TenantBoundary:
    if not tenant_id.strip():
        raise ValueError("tenant_id is required")
    if any(part in {"", ".", ".."} for part in tenant_id.split("/")):
        raise ValueError("tenant_id must be a simple relative identifier")
    return TenantBoundary(tenant_id=tenant_id, root=root / tenant_id)
