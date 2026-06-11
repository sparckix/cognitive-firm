"""Validation for installed extension policy.

Packages can install governance-side declarations for external adapters and
formal-verification providers. This module validates those declarations without
installing or running the external executable.
"""

from __future__ import annotations

from pathlib import Path

from cognitive_firm.orchestration.adapter_conformance import (
    AdapterManifestError,
    load_adapter_conformance_config,
    load_adapter_manifest,
    validate_adapter_conformance_config_file,
    validate_adapter_manifest_file,
)


def validate_extension_policy_tree(
    config_root: Path,
    *,
    report_root: Path | None = None,
    evidence_root: Path | None = None,
) -> list[str]:
    """Validate adapter/provider policy files under ``config_root``.

    ``config_root`` is either an installed organization root or a package's
    ``files/`` directory. ``report_root`` controls relative paths in returned
    messages; package lint passes the package root so messages include
    ``files/...``.
    """
    config_root = Path(config_root)
    report_root = Path(report_root) if report_root is not None else config_root
    issues: list[str] = []
    issues.extend(
        _validate_adapter_policy_tree(
            config_root,
            report_root=report_root,
            evidence_root=evidence_root,
        )
    )
    issues.extend(
        _validate_formal_verification_policy_tree(
            config_root,
            report_root=report_root,
        )
    )
    return issues


def _display(path: Path, report_root: Path) -> str:
    try:
        return path.relative_to(report_root).as_posix()
    except ValueError:
        return path.as_posix()


def _validate_adapter_policy_tree(
    config_root: Path,
    *,
    report_root: Path,
    evidence_root: Path | None,
) -> list[str]:
    issues: list[str] = []
    adapter_manifests: dict[str, Path] = {}
    adapters_dir = config_root / "adapters"
    if adapters_dir.is_dir():
        for path in sorted(adapters_dir.iterdir()):
            if path.suffix.lower() not in {".yaml", ".yml", ".json"}:
                continue
            rel = _display(path, report_root)
            manifest_issues = validate_adapter_manifest_file(path)
            issues.extend(f"{rel}: {issue}" for issue in manifest_issues)
            if manifest_issues:
                continue
            try:
                adapter = load_adapter_manifest(path)
            except AdapterManifestError as exc:
                issues.append(f"{rel}: {exc}")
            else:
                adapter_manifests[adapter.adapter_id] = path

    conformance_dir = config_root / "adapter_conformance"
    if conformance_dir.is_dir():
        for path in sorted(conformance_dir.iterdir()):
            if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
                continue
            rel = _display(path, report_root)
            try:
                config = load_adapter_conformance_config(path)
            except ValueError as exc:
                issues.append(f"{rel}: {exc}")
                continue
            manifest_path = adapter_manifests.get(config.adapter_id)
            config_issues = validate_adapter_conformance_config_file(
                path,
                manifest_path=manifest_path,
                evidence_root=evidence_root,
            )
            issues.extend(f"{rel}: {issue}" for issue in config_issues)
            if manifest_path is None:
                issues.append(
                    f"{rel}: no matching adapter manifest found for "
                    f"{config.adapter_id!r}"
                )
    return issues


def _validate_formal_verification_policy_tree(
    config_root: Path,
    *,
    report_root: Path,
) -> list[str]:
    policy_path = config_root / "formal_verification" / "trusted_providers.json"
    if not policy_path.exists():
        return []
    from cognitive_firm.orchestration.formal_verification import (
        validate_formal_verification_trust_policy_file,
    )

    rel = _display(policy_path, report_root)
    return [
        f"{rel}: {issue}"
        for issue in validate_formal_verification_trust_policy_file(policy_path)
    ]
