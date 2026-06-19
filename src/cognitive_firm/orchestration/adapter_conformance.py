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


@dataclass(frozen=True)
class RuntimeAdapterProofPackInput:
    """Observed native/runtime demo outputs for a runtime-adapter proof pack.

    The payloads should come from already-run deterministic fixtures. The
    builder compares governance evidence shape; it does not execute runtimes,
    install adapters, or approve support status.
    """

    adapter_id: str
    native_payload: dict[str, Any]
    runtime_payload: dict[str, Any]
    manifest: AdapterManifest | None = None
    conformance_config: AdapterConformanceConfig | None = None
    generated_at_utc: str | None = None
    evidence_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


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


def build_runtime_adapter_proof_pack(
    pack_input: RuntimeAdapterProofPackInput,
) -> dict[str, Any]:
    """Build a read-only proof pack comparing native and runtime-adapter paths."""

    native_summary = _payload_summary(pack_input.native_payload)
    runtime_summary = _payload_summary(pack_input.runtime_payload)
    checks: list[dict[str, Any]] = []
    checks.extend(_manifest_config_checks(pack_input))
    checks.append(
        _pack_check(
            "native_governance_contract",
            not _governed_summary_errors(native_summary, pack_input.native_payload),
            detail="native demo satisfies the governed-run summary contract",
            errors=_governed_summary_errors(native_summary, pack_input.native_payload),
            evidence_refs=_summary_refs(native_summary, prefix="native"),
        )
    )
    checks.append(
        _pack_check(
            "runtime_governance_contract",
            not _governed_summary_errors(runtime_summary, pack_input.runtime_payload),
            detail="runtime-adapter demo satisfies the governed-run summary contract",
            errors=_governed_summary_errors(runtime_summary, pack_input.runtime_payload),
            evidence_refs=_summary_refs(runtime_summary, prefix="runtime"),
        )
    )
    shared_contract_errors = _shared_summary_contract_errors(native_summary, runtime_summary)
    checks.append(
        _pack_check(
            "shared_governed_run_summary_contract",
            not shared_contract_errors,
            detail="native and runtime-adapter demos expose the same summary keys",
            errors=shared_contract_errors,
        )
    )
    runtime_projection_errors = _runtime_projection_errors(pack_input.runtime_payload)
    checks.append(
        _pack_check(
            "runtime_projection_keeps_runtime_owned_refs",
            not runtime_projection_errors,
            detail=(
                "runtime projection carries external run identity, opaque resume "
                "ref, and evidence refs without becoming the graph runtime"
            ),
            errors=runtime_projection_errors,
            evidence_refs=_runtime_projection_refs(pack_input.runtime_payload),
        )
    )
    blockers = [check for check in checks if check["required"] and check["status"] != "passed"]
    packet = {
        "schema": "runtime_adapter_proof_pack.v1",
        "adapter_id": pack_input.adapter_id,
        "generated_at_utc": pack_input.generated_at_utc,
        "read_only": True,
        "projection_only": True,
        "summary": {
            "ok": not blockers,
            "checks": len(checks),
            "required_blockers": len(blockers),
            "native_demo": pack_input.native_payload.get("demo"),
            "runtime_demo": pack_input.runtime_payload.get("demo"),
            "native_run_id": native_summary.get("run_id"),
            "runtime_run_id": runtime_summary.get("run_id"),
            "native_bundle_id": native_summary.get("bundle_id"),
            "runtime_bundle_id": runtime_summary.get("bundle_id"),
        },
        "checks": checks,
        "manifest": (
            pack_input.manifest.as_dict() if pack_input.manifest is not None else None
        ),
        "conformance_config": (
            pack_input.conformance_config.as_dict()
            if pack_input.conformance_config is not None
            else None
        ),
        "runtime_boundary": (
            dict(pack_input.conformance_config.runtime_boundary)
            if pack_input.conformance_config is not None
            else {}
        ),
        "isomorphism_takeaways": [
            "same governed-run contract across execution substrates",
            "external runtime keeps graph execution and native resume tokens",
            "kernel owns authority, human-work receipt state, evidence, and bundle projection",
            "missing or malformed evidence becomes a blocker, not an inferred pass",
        ],
        "review_questions": _runtime_adapter_review_questions(checks),
        "evidence_refs": _dedupe_text_refs(
            list(pack_input.evidence_refs)
            + _summary_refs(native_summary, prefix="native")
            + _summary_refs(runtime_summary, prefix="runtime")
            + _runtime_projection_refs(pack_input.runtime_payload)
        ),
        "boundary": {
            "checker_does_not_execute_runtime": True,
            "checker_does_not_install_adapter": True,
            "checker_does_not_approve_adapter_support": True,
            "checker_does_not_mutate_kernel_state": True,
            "demo_commands_use_bounded_temp_state": True,
            "runtime_graph_semantics_remain_external": True,
        },
        "metadata": dict(pack_input.metadata or {}),
    }
    packet["markdown"] = render_runtime_adapter_proof_pack_markdown(packet)
    return packet


def render_runtime_adapter_proof_pack_markdown(packet: dict[str, Any]) -> str:
    """Render a runtime adapter proof pack for human review."""

    if packet.get("schema") != "runtime_adapter_proof_pack.v1":
        raise ValueError("packet schema must be runtime_adapter_proof_pack.v1")
    summary = packet.get("summary") or {}
    lines = [
        "# Runtime Adapter Proof Pack",
        "",
        "## Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Adapter | {_md(packet.get('adapter_id', ''))} |",
        f"| OK | {_md(summary.get('ok', False))} |",
        f"| Required blockers | {_md(summary.get('required_blockers', 0))} |",
        f"| Native demo | {_md(summary.get('native_demo', ''))} |",
        f"| Runtime demo | {_md(summary.get('runtime_demo', ''))} |",
        f"| Native bundle | {_md(summary.get('native_bundle_id', ''))} |",
        f"| Runtime bundle | {_md(summary.get('runtime_bundle_id', ''))} |",
        "",
        "## Checks",
        "",
        "| Check | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    for check in packet.get("checks") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(check.get("check_id", "")),
                    _md(check.get("status", "")),
                    _md(", ".join(check.get("evidence_refs") or [])),
                ]
            )
            + " |"
        )
    if packet.get("review_questions"):
        lines.extend(["", "## Review Questions", ""])
        for question in packet["review_questions"]:
            lines.append(f"- {_md(question)}")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- The proof-pack checker does not execute or install an external runtime.",
            "- The demo commands use bounded temporary state.",
            "- The packet does not approve adapter support or mutate kernel state.",
            "",
        ]
    )
    return "\n".join(lines)


def _manifest_config_checks(pack_input: RuntimeAdapterProofPackInput) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    manifest = pack_input.manifest
    config = pack_input.conformance_config
    manifest_errors: list[str] = []
    if manifest is None:
        manifest_errors.append("adapter manifest is missing")
    else:
        if manifest.adapter_id != pack_input.adapter_id:
            manifest_errors.append(
                f"manifest adapter_id {manifest.adapter_id!r} != {pack_input.adapter_id!r}"
            )
        if manifest.family != "runtime":
            manifest_errors.append(f"manifest family must be 'runtime', got {manifest.family!r}")
        if manifest.protocol != "runtime_event":
            manifest_errors.append(
                f"manifest protocol must be 'runtime_event', got {manifest.protocol!r}"
            )
    checks.append(
        _pack_check(
            "runtime_adapter_manifest",
            not manifest_errors,
            detail="manifest declares a runtime_event adapter",
            errors=manifest_errors,
        )
    )

    config_errors: list[str] = []
    if config is None:
        config_errors.append("adapter conformance config is missing")
    else:
        if config.adapter_id != pack_input.adapter_id:
            config_errors.append(
                f"config adapter_id {config.adapter_id!r} != {pack_input.adapter_id!r}"
            )
        if config.protocol != "runtime_event":
            config_errors.append(
                f"config protocol must be 'runtime_event', got {config.protocol!r}"
            )
        if manifest is not None:
            missing = sorted(set(manifest.conformance_checks) - set(config.check_ids))
            if missing:
                config_errors.append(
                    "conformance config missing manifest checks: " + ", ".join(missing)
                )
        config_errors.extend(_runtime_boundary_declaration_errors(config.runtime_boundary))
    checks.append(
        _pack_check(
            "runtime_adapter_conformance_config",
            not config_errors,
            detail="conformance config aligns with the runtime boundary declaration",
            errors=config_errors,
        )
    )
    return checks


def _governed_summary_errors(summary: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not summary:
        return ["summary is missing"]
    if _deep_get(payload, "bundle_validation.ok") is not True:
        errors.append("bundle_validation.ok must be true")
    if summary.get("verdict") != "passed":
        errors.append("summary.verdict must be 'passed'")
    if summary.get("run_state") != "completed":
        errors.append("summary.run_state must be 'completed'")
    for field_name in ("run_id", "owner_role", "project_id", "bundle_id", "bundle_digest"):
        if not summary.get(field_name):
            errors.append(f"summary.{field_name} is required")
    if not str(summary.get("owner_role") or "").startswith("role."):
        errors.append("summary.owner_role must be a role ref")
    if _deep_get(summary, "authority_snapshot.status") != "resolved":
        errors.append("summary.authority_snapshot.status must be 'resolved'")
    if not _deep_get(summary, "authority_snapshot.mandate_hash"):
        errors.append("summary.authority_snapshot.mandate_hash is required")
    if summary.get("caveats") != []:
        errors.append("summary.caveats must be empty")
    counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
    for key in (
        "action_attestations",
        "human_work_sessions",
        "outcome_links",
        "accountability_cases",
    ):
        if int(counts.get(key) or 0) < 1:
            errors.append(f"summary.counts.{key} must be at least 1")
    ids = summary.get("ids") if isinstance(summary.get("ids"), dict) else {}
    for key in (
        "action_attestations",
        "human_work_sessions",
        "outcome_links",
        "accountability_cases",
    ):
        if not ids.get(key):
            errors.append(f"summary.ids.{key} is required")
    return errors


def _shared_summary_contract_errors(
    native_summary: dict[str, Any],
    runtime_summary: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    native_keys = set(native_summary)
    runtime_keys = set(runtime_summary)
    if native_keys != runtime_keys:
        errors.append(
            "summary keys differ: "
            f"native_only={sorted(native_keys - runtime_keys)}, "
            f"runtime_only={sorted(runtime_keys - native_keys)}"
        )
    for field_name in ("verdict", "run_state"):
        if native_summary.get(field_name) != runtime_summary.get(field_name):
            errors.append(
                f"summary.{field_name} differs: "
                f"{native_summary.get(field_name)!r} != {runtime_summary.get(field_name)!r}"
            )
    return errors


def _runtime_projection_errors(payload: dict[str, Any]) -> list[str]:
    projection = _deep_get(payload, "run_projection.runtime_projection")
    if not isinstance(projection, dict):
        return ["run_projection.runtime_projection is required"]
    errors: list[str] = []
    for field_name in ("runtime_name", "external_run_id", "resume_ref"):
        if not projection.get(field_name):
            errors.append(f"runtime_projection.{field_name} is required")
    if _deep_get(payload, "run_projection.state") != "completed":
        errors.append("run_projection.state must be 'completed'")
    evidence_refs = [
        str(ref)
        for ref in projection.get("evidence_refs") or []
        if str(ref).strip()
    ]
    for prefix in ("run:", "human_work:", "outcome_link:"):
        if not any(ref.startswith(prefix) for ref in evidence_refs):
            errors.append(f"runtime_projection.evidence_refs missing {prefix} ref")
    return errors


def _runtime_boundary_declaration_errors(boundary: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    external = [str(item).lower() for item in boundary.get("external_runtime_owns") or []]
    kernel = [str(item).lower() for item in boundary.get("cognitive_firm_owns") or []]
    expected_external = ("graph execution", "native resume token")
    expected_kernel = ("role-owned run projection", "governed-run attestation bundle")
    for phrase in expected_external:
        if not any(phrase in item for item in external):
            errors.append(f"runtime_boundary.external_runtime_owns missing {phrase!r}")
    for phrase in expected_kernel:
        if not any(phrase in item for item in kernel):
            errors.append(f"runtime_boundary.cognitive_firm_owns missing {phrase!r}")
    return errors


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    return dict(summary) if isinstance(summary, dict) else {}


def _summary_refs(summary: dict[str, Any], *, prefix: str) -> list[str]:
    refs: list[str] = []
    for key, ref_prefix in (
        ("run_id", "run:"),
        ("bundle_id", "governed_run_bundle:"),
    ):
        value = summary.get(key)
        if value:
            refs.append(f"{prefix}:{ref_prefix}{value}")
    ids = summary.get("ids") if isinstance(summary.get("ids"), dict) else {}
    for key, ref_prefix in (
        ("action_attestations", "action_attestation:"),
        ("human_work_sessions", "human_work:"),
        ("outcome_links", "outcome_link:"),
        ("accountability_cases", "accountability_case:"),
    ):
        for value in ids.get(key) or []:
            refs.append(f"{prefix}:{ref_prefix}{value}")
    return _dedupe_text_refs(refs)


def _runtime_projection_refs(payload: dict[str, Any]) -> list[str]:
    refs = _deep_get(payload, "run_projection.runtime_projection.evidence_refs")
    if not isinstance(refs, list):
        return []
    return _dedupe_text_refs([f"runtime_projection:{ref}" for ref in refs if str(ref).strip()])


def _runtime_adapter_review_questions(checks: list[dict[str, Any]]) -> list[str]:
    blockers = [check["check_id"] for check in checks if check["status"] != "passed"]
    questions = [
        "Does the real adapter preserve the same governed-run contract as the no-cost fixture?",
        "Are runtime-owned tokens treated as opaque refs rather than kernel state?",
        "Does the adapter package remain governance policy and conformance declaration only?",
    ]
    if blockers:
        questions.append(
            "Which blocker must be repaired before adapter support review: "
            + ", ".join(blockers)
            + "?"
        )
    return questions


def _pack_check(
    check_id: str,
    passed: bool,
    *,
    detail: str,
    errors: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    required: bool = True,
) -> dict[str, Any]:
    errors = list(errors or [])
    return {
        "check_id": check_id,
        "required": required,
        "status": "passed" if passed else "failed" if required else "warning",
        "detail": detail,
        "errors": errors,
        "evidence_refs": _dedupe_text_refs(list(evidence_refs or [])),
    }


def _deep_get(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _dedupe_text_refs(refs: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for ref in refs:
        text = str(ref).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _md(value: Any) -> str:
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text


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
