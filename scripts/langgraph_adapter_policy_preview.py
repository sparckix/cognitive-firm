#!/usr/bin/env python3
"""Preview the bundled LangGraph adapter-policy package without installing it.

This is an adoption proof for the package/overlay boundary. It installs a
temporary starter organization by default, previews the
``langgraph-runtime-adapter`` overlay against that org, validates the adapter
manifest/conformance declaration, and reports whether the overlay widens
authority. It does not install LangGraph, execute a graph, write a governance
proposal, or apply the overlay to a live organization.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.distribution import (  # noqa: E402
    install,
    load_manifest,
    validate_manifest,
    verify_install,
)
from cognitive_firm.distribution.governed_install import (  # noqa: E402
    preview_overlay_install,
)
from cognitive_firm.orchestration.adapter_conformance import (  # noqa: E402
    load_adapter_manifest,
    validate_adapter_conformance_config_file,
)


REGISTRY = ROOT / "distro"
STARTER = REGISTRY / "starter-firm"
DEFAULT_PACKAGE = "langgraph-runtime-adapter"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preview the bundled LangGraph adapter-policy overlay against a "
            "starter org, proving authority-neutral package installation."
        )
    )
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument(
        "--target-root",
        type=Path,
        help="Existing organization directory to preview against. Defaults to a temporary starter-firm install.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the JSON proof.",
    )
    args = parser.parse_args(argv)

    if args.target_root:
        payload = build_preview_payload(args.package, target_root=args.target_root)
    else:
        with tempfile.TemporaryDirectory(prefix="cf-adapter-policy-preview-") as raw:
            payload = build_preview_payload(args.package, target_root=Path(raw) / "org")

    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if payload["ok"] else 1


def build_preview_payload(package: str, *, target_root: Path) -> dict[str, Any]:
    package_root = _resolve_package_root(package)
    package_manifest = load_manifest(package_root / "package.yaml")
    package_manifest_issues = validate_manifest(package_manifest, package_root)

    installed_temp_starter = False
    starter_verify_issues: list[str] = []
    if not target_root.exists():
        target_root.mkdir(parents=True)
        starter_manifest = load_manifest(STARTER / "package.yaml")
        receipt = install(starter_manifest, STARTER, target_root)
        starter_verify_issues = verify_install(receipt, target_root)
        installed_temp_starter = True

    preview = preview_overlay_install(
        overlay_manifest=package_manifest,
        overlay_root=package_root,
        target_root=target_root,
    )
    adapter_manifest_path = (
        package_root / "files" / "adapters" / "langgraph-runtime-adapter.yaml"
    )
    conformance_path = (
        package_root
        / "files"
        / "adapter_conformance"
        / "langgraph-runtime-adapter.json"
    )
    adapter_manifest = load_adapter_manifest(adapter_manifest_path)
    conformance_issues = validate_adapter_conformance_config_file(
        conformance_path,
        manifest_path=adapter_manifest_path,
        evidence_root=ROOT,
    )
    preview_payload = preview.as_dict()
    expected_files = {
        "adapters/langgraph-runtime-adapter.md",
        "adapters/langgraph-runtime-adapter.yaml",
        "adapter_conformance/langgraph-runtime-adapter.json",
    }
    observed_files = {item["dest"] for item in preview_payload["files"]}
    ok = (
        not package_manifest_issues
        and not starter_verify_issues
        and not conformance_issues
        and preview_payload["status"] == "review_ready"
        and preview_payload["can_proceed"] is True
        and preview_payload["expands_authority"] is False
        and observed_files == expected_files
    )
    return {
        "schema": "adapter_policy_preview.v1",
        "ok": ok,
        "package": package_manifest.name,
        "package_version": package_manifest.version,
        "target_root": str(target_root),
        "installed_temp_starter": installed_temp_starter,
        "preview": preview_payload,
        "adapter_manifest": {
            "path": str(adapter_manifest_path),
            "adapter_id": adapter_manifest.adapter_id,
            "family": adapter_manifest.family,
            "protocol": adapter_manifest.protocol,
            "executable_kind": adapter_manifest.executable.kind,
            "executable_ref": adapter_manifest.executable.ref,
            "conformance_checks": list(adapter_manifest.conformance_checks),
        },
        "conformance_config": {
            "path": str(conformance_path),
            "issues": conformance_issues,
        },
        "validation": {
            "package_manifest_issues": package_manifest_issues,
            "starter_verify_issues": starter_verify_issues,
            "expected_files_present": observed_files == expected_files,
            "authority_neutral": preview_payload["expands_authority"] is False,
        },
        "boundary": {
            "does_not_install_overlay": True,
            "does_not_write_governance_proposal": True,
            "does_not_execute_runtime": True,
            "does_not_install_langgraph": True,
            "does_not_widen_authority": preview_payload["expands_authority"] is False,
            "not_a_package_manager": True,
        },
    }


def _resolve_package_root(package: str) -> Path:
    candidate = Path(package)
    if candidate.exists():
        return candidate if candidate.is_dir() else candidate.parent
    registry_candidate = REGISTRY / package
    if registry_candidate.exists():
        return registry_candidate
    raise SystemExit(f"unknown package: {package}")


if __name__ == "__main__":
    raise SystemExit(main())
