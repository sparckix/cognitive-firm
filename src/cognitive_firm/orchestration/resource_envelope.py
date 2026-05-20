"""Lightweight kernel resource envelope.

The shape intentionally resembles mature resource APIs without importing a full
Kubernetes-style object model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


ResourceStability = Literal["alpha", "beta", "stable"]


@dataclass(frozen=True)
class ResourceMetadata:
    name: str
    resource_id: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    created_at_utc: str | None = None
    updated_at_utc: str | None = None


@dataclass(frozen=True)
class KernelResource:
    api_version: str
    kind: str
    metadata: ResourceMetadata
    stability: ResourceStability | str = "alpha"
    spec: dict[str, Any] = field(default_factory=dict)
    status: dict[str, Any] = field(default_factory=dict)
    links: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_resource(
    *,
    kind: str,
    name: str,
    spec: dict[str, Any] | None = None,
    status: dict[str, Any] | None = None,
    links: list[dict[str, str]] | None = None,
    api_version: str = "cognitive-firm/v1alpha1",
    stability: ResourceStability | str = "alpha",
    resource_id: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    labels: dict[str, str] | None = None,
    annotations: dict[str, str] | None = None,
) -> KernelResource:
    if not kind.strip():
        raise ValueError("kind is required")
    if not name.strip():
        raise ValueError("name is required")
    if stability not in {"alpha", "beta", "stable"}:
        raise ValueError("stability must be alpha, beta, or stable")
    now = datetime.now(timezone.utc).isoformat()
    return KernelResource(
        api_version=api_version,
        kind=kind,
        metadata=ResourceMetadata(
            name=name,
            resource_id=resource_id,
            tenant_id=tenant_id,
            project_id=project_id,
            labels=labels or {},
            annotations=annotations or {},
            created_at_utc=now,
            updated_at_utc=now,
        ),
        stability=stability,
        spec=spec or {},
        status=status or {},
        links=links or [],
    )


def validate_resource(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not payload.get("api_version") and not payload.get("apiVersion"):
        errors.append("api_version is required")
    if not payload.get("kind"):
        errors.append("kind is required")
    if payload.get("stability", "alpha") not in {"alpha", "beta", "stable"}:
        errors.append("stability must be alpha, beta, or stable")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("metadata object is required")
    elif not metadata.get("name"):
        errors.append("metadata.name is required")
    if "spec" in payload and not isinstance(payload.get("spec"), dict):
        errors.append("spec must be an object")
    if "status" in payload and not isinstance(payload.get("status"), dict):
        errors.append("status must be an object")
    if "links" in payload and not isinstance(payload.get("links"), list):
        errors.append("links must be a list")
    return errors
