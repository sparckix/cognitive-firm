"""Conformance helpers and manifests for integration adapters.

Adapter code can live outside the kernel as a Python package, local command,
container, or hosted service. The kernel-owned object is the adapter manifest:
the declared protocol boundary, executable reference, trust refs, and
deterministic conformance checks an organization expects before treating the
adapter as supported.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml


ADAPTER_MANIFEST_SCHEMA_VERSION = "cognitive-firm-adapter-manifest/v1"
ADAPTER_CONFORMANCE_SCHEMA_VERSION = "cognitive-firm-adapter-conformance/v1"

ADAPTER_FAMILIES: tuple[str, ...] = (
    "app_surface",
    "enterprise_system",
    "runtime",
    "state_backend",
    "inbound_event",
    "notification",
    "identity_provider",
    "tenant_adapter",
    "formal_verification_provider",
    "mcp_server",
)

ADAPTER_PROTOCOLS: tuple[str, ...] = (
    "runtime_event",
    "mcp_outbox_projection",
    "inbound_event_projection",
    "formal_verification_provider_payload",
    "state_backend",
    "notification_channel",
    "identity_provider",
    "kernel_service_app_surface",
)

EXECUTABLE_KINDS: tuple[str, ...] = (
    "python_package",
    "local_command",
    "container_image",
    "hosted_service",
    "repository",
    "mcp_server",
)


class AdapterManifestError(ValueError):
    """Raised when an adapter manifest is malformed."""


class AdapterConformanceConfigError(ValueError):
    """Raised when an adapter conformance config is malformed."""


@dataclass(frozen=True)
class ExecutableReference:
    """Where the external adapter code comes from.

    This is a declaration only. Loading a manifest never installs or runs the
    executable.
    """

    kind: str
    ref: str
    version: str | None = None
    digest: str | None = None
    signature_ref: str | None = None
    public_key_ref: str | None = None
    install_hint: str = ""

    @classmethod
    def from_raw(cls, raw: Any) -> "ExecutableReference":
        if not isinstance(raw, dict):
            raise AdapterManifestError("executable must be a mapping")
        return cls(
            kind=str(raw.get("kind", "")).strip(),
            ref=str(raw.get("ref", "")).strip(),
            version=_optional_text(raw.get("version")),
            digest=_optional_text(raw.get("digest")),
            signature_ref=_optional_text(raw.get("signature_ref")),
            public_key_ref=_optional_text(raw.get("public_key_ref")),
            install_hint=str(raw.get("install_hint", "")).strip(),
        )

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.kind not in EXECUTABLE_KINDS:
            issues.append(f"executable.kind {self.kind!r} not in {EXECUTABLE_KINDS}")
        if not self.ref:
            issues.append("executable.ref is required")
        return issues

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "kind": self.kind,
            "ref": self.ref,
            "install_hint": self.install_hint,
        }
        for key in ("version", "digest", "signature_ref", "public_key_ref"):
            value = getattr(self, key)
            if value:
                payload[key] = value
        return payload


@dataclass(frozen=True)
class AdapterManifest:
    """Durable declaration for an external adapter integration."""

    adapter_id: str
    family: str
    protocol: str
    description: str
    executable: ExecutableReference
    conformance_checks: tuple[str, ...]
    trust_requirements: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    schema_version: str = ADAPTER_MANIFEST_SCHEMA_VERSION

    @classmethod
    def from_raw(cls, raw: Any) -> "AdapterManifest":
        if not isinstance(raw, dict):
            raise AdapterManifestError("adapter manifest must be a mapping")
        return cls(
            schema_version=str(raw.get("schema_version", "")).strip(),
            adapter_id=str(raw.get("adapter_id", "")).strip(),
            family=str(raw.get("family", "")).strip(),
            protocol=str(raw.get("protocol", "")).strip(),
            description=str(raw.get("description", "")).strip(),
            executable=ExecutableReference.from_raw(raw.get("executable")),
            conformance_checks=tuple(
                str(check).strip()
                for check in (raw.get("conformance_checks") or [])
                if str(check).strip()
            ),
            trust_requirements=dict(raw.get("trust_requirements") or {}),
            evidence_refs=tuple(
                str(ref).strip()
                for ref in (raw.get("evidence_refs") or [])
                if str(ref).strip()
            ),
        )

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.schema_version != ADAPTER_MANIFEST_SCHEMA_VERSION:
            issues.append(
                f"schema_version {self.schema_version!r} != "
                f"{ADAPTER_MANIFEST_SCHEMA_VERSION!r}"
            )
        if not self.adapter_id:
            issues.append("adapter_id is required")
        if self.family not in ADAPTER_FAMILIES:
            issues.append(f"family {self.family!r} not in {ADAPTER_FAMILIES}")
        if self.protocol not in ADAPTER_PROTOCOLS:
            issues.append(f"protocol {self.protocol!r} not in {ADAPTER_PROTOCOLS}")
        if len(self.description) < 20:
            issues.append("description is too short (min 20 chars)")
        issues.extend(self.executable.validate())
        if not self.conformance_checks:
            issues.append("at least one conformance check is required")
        if not isinstance(self.trust_requirements, dict):
            issues.append("trust_requirements must be a mapping")
        return issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "family": self.family,
            "protocol": self.protocol,
            "description": self.description,
            "executable": self.executable.as_dict(),
            "trust_requirements": self.trust_requirements,
            "conformance_checks": list(self.conformance_checks),
            "evidence_refs": list(self.evidence_refs),
        }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_adapter_manifest(path: Path) -> AdapterManifest:
    """Load and validate a JSON/YAML adapter manifest."""
    path = Path(path)
    if not path.is_file():
        raise AdapterManifestError(f"adapter manifest not found: {path}")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(path.read_text())
        else:
            raw = yaml.safe_load(path.read_text())
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise AdapterManifestError(f"cannot parse adapter manifest {path}: {exc}") from exc
    manifest = AdapterManifest.from_raw(raw or {})
    issues = manifest.validate()
    if issues:
        raise AdapterManifestError(
            f"invalid adapter manifest {path}: " + "; ".join(issues)
        )
    return manifest


def validate_adapter_manifest_file(path: Path) -> list[str]:
    """Return validation issues for a manifest file without raising."""
    try:
        load_adapter_manifest(path)
    except AdapterManifestError as exc:
        return [str(exc)]
    return []


@dataclass(frozen=True)
class RequiredConformanceCheck:
    """One check an installed adapter policy expects a fixture to prove."""

    check_id: str
    evidence: str

    @classmethod
    def from_raw(cls, raw: Any) -> "RequiredConformanceCheck":
        if not isinstance(raw, dict):
            raise AdapterConformanceConfigError("required_checks entries must be mappings")
        return cls(
            check_id=str(raw.get("check_id", "")).strip(),
            evidence=str(raw.get("evidence", "")).strip(),
        )

    def validate(self) -> list[str]:
        issues: list[str] = []
        if not self.check_id:
            issues.append("required_checks[].check_id is required")
        if not self.evidence:
            issues.append(f"required_checks[{self.check_id or '?'}].evidence is required")
        return issues

    def as_dict(self) -> dict[str, str]:
        return {
            "check_id": self.check_id,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class AdapterConformanceConfig:
    """Org-owned conformance expectations for one installed adapter policy.

    This config is a declaration, not a test runner. It records which fixture
    command and evidence paths the org expects before treating an external
    adapter as supported.
    """

    adapter_id: str
    protocol: str
    fixture_command: str
    required_checks: tuple[RequiredConformanceCheck, ...]
    runtime_boundary: dict[str, Any] = field(default_factory=dict)
    schema_version: str = ADAPTER_CONFORMANCE_SCHEMA_VERSION

    @classmethod
    def from_raw(cls, raw: Any) -> "AdapterConformanceConfig":
        if not isinstance(raw, dict):
            raise AdapterConformanceConfigError("adapter conformance config must be a mapping")
        return cls(
            schema_version=str(raw.get("schema_version", "")).strip(),
            adapter_id=str(raw.get("adapter_id", "")).strip(),
            protocol=str(raw.get("protocol", "")).strip(),
            fixture_command=str(raw.get("fixture_command", "")).strip(),
            required_checks=tuple(
                RequiredConformanceCheck.from_raw(check)
                for check in (raw.get("required_checks") or [])
            ),
            runtime_boundary=dict(raw.get("runtime_boundary") or {}),
        )

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.schema_version != ADAPTER_CONFORMANCE_SCHEMA_VERSION:
            issues.append(
                f"schema_version {self.schema_version!r} != "
                f"{ADAPTER_CONFORMANCE_SCHEMA_VERSION!r}"
            )
        if not self.adapter_id:
            issues.append("adapter_id is required")
        if self.protocol not in ADAPTER_PROTOCOLS:
            issues.append(f"protocol {self.protocol!r} not in {ADAPTER_PROTOCOLS}")
        if not self.fixture_command:
            issues.append("fixture_command is required")
        if not self.required_checks:
            issues.append("at least one required check is required")
        seen: set[str] = set()
        for check in self.required_checks:
            issues.extend(check.validate())
            if check.check_id in seen:
                issues.append(f"duplicate required check: {check.check_id}")
            seen.add(check.check_id)
        if not isinstance(self.runtime_boundary, dict):
            issues.append("runtime_boundary must be a mapping")
        return issues

    @property
    def check_ids(self) -> tuple[str, ...]:
        return tuple(check.check_id for check in self.required_checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "protocol": self.protocol,
            "fixture_command": self.fixture_command,
            "required_checks": [check.as_dict() for check in self.required_checks],
            "runtime_boundary": self.runtime_boundary,
        }


def load_adapter_conformance_config(path: Path) -> AdapterConformanceConfig:
    """Load and validate an adapter conformance config."""
    path = Path(path)
    if not path.is_file():
        raise AdapterConformanceConfigError(f"adapter conformance config not found: {path}")
    try:
        if path.suffix.lower() == ".json":
            raw = json.loads(path.read_text())
        else:
            raw = yaml.safe_load(path.read_text())
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise AdapterConformanceConfigError(
            f"cannot parse adapter conformance config {path}: {exc}"
        ) from exc
    config = AdapterConformanceConfig.from_raw(raw or {})
    issues = config.validate()
    if issues:
        raise AdapterConformanceConfigError(
            f"invalid adapter conformance config {path}: " + "; ".join(issues)
        )
    return config


def validate_adapter_conformance_config_file(
    path: Path,
    *,
    manifest_path: Path | None = None,
    evidence_root: Path | None = None,
) -> list[str]:
    """Validate a conformance config and optionally align it to a manifest.

    The optional manifest check prevents package drift: an adapter manifest and
    its conformance config must name the same adapter/protocol, and every
    manifest check must appear in the installed conformance config. The
    optional evidence root checks that evidence refs point at local files.
    """
    issues: list[str] = []
    try:
        config = load_adapter_conformance_config(path)
    except AdapterConformanceConfigError as exc:
        return [str(exc)]

    manifest: AdapterManifest | None = None
    if manifest_path is not None:
        try:
            manifest = load_adapter_manifest(manifest_path)
        except AdapterManifestError as exc:
            issues.append(str(exc))
        else:
            if config.adapter_id != manifest.adapter_id:
                issues.append(
                    f"adapter_id mismatch: config {config.adapter_id!r} "
                    f"!= manifest {manifest.adapter_id!r}"
                )
            if config.protocol != manifest.protocol:
                issues.append(
                    f"protocol mismatch: config {config.protocol!r} "
                    f"!= manifest {manifest.protocol!r}"
                )
            missing = sorted(set(manifest.conformance_checks) - set(config.check_ids))
            if missing:
                issues.append(
                    "conformance config missing manifest checks: "
                    + ", ".join(missing)
                )

    if evidence_root is not None:
        root = Path(evidence_root)
        for check in config.required_checks:
            evidence = root / check.evidence
            if not evidence.exists():
                issues.append(
                    f"evidence for {check.check_id!r} does not exist: {check.evidence}"
                )
    return issues


@dataclass(frozen=True)
class ConformanceCheck:
    check_id: str
    passed: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdapterConformanceReport:
    adapter_id: str
    family: str
    checks: list[ConformanceCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.passed for check in self.checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "family": self.family,
            "ok": self.ok,
            "checks": [check.as_dict() for check in self.checks],
        }


def run_adapter_conformance(
    *,
    adapter_id: str,
    family: str,
    checks: dict[str, Callable[[], bool]],
) -> AdapterConformanceReport:
    results: list[ConformanceCheck] = []
    for check_id, check in checks.items():
        try:
            passed = bool(check())
        except Exception as exc:  # pragma: no cover - exercised by callers
            results.append(
                ConformanceCheck(check_id=check_id, passed=False, detail=str(exc))
            )
        else:
            results.append(ConformanceCheck(check_id=check_id, passed=passed))
    return AdapterConformanceReport(adapter_id=adapter_id, family=family, checks=results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate cognitive-firm adapter manifests."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-manifest", help="Validate an adapter manifest")
    validate.add_argument("path", type=Path)
    validate.add_argument("--json", action="store_true", help="Print the normalized manifest JSON")
    validate_config = sub.add_parser(
        "validate-conformance",
        help="Validate an adapter conformance config and optional manifest alignment.",
    )
    validate_config.add_argument("path", type=Path)
    validate_config.add_argument("--manifest", type=Path)
    validate_config.add_argument("--evidence-root", type=Path)
    validate_config.add_argument("--json", action="store_true", help="Print the normalized config JSON")
    args = parser.parse_args(argv)

    if args.command == "validate-manifest":
        try:
            manifest = load_adapter_manifest(args.path)
        except AdapterManifestError as exc:
            print(str(exc))
            return 1
        if args.json:
            print(json.dumps(manifest.as_dict(), indent=2, sort_keys=True))
        else:
            print(f"adapter manifest ok: {manifest.adapter_id}")
        return 0
    if args.command == "validate-conformance":
        issues = validate_adapter_conformance_config_file(
            args.path,
            manifest_path=args.manifest,
            evidence_root=args.evidence_root,
        )
        if issues:
            for issue in issues:
                print(issue)
            return 1
        config = load_adapter_conformance_config(args.path)
        if args.json:
            print(json.dumps(config.as_dict(), indent=2, sort_keys=True))
        else:
            print(f"adapter conformance config ok: {config.adapter_id}")
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
