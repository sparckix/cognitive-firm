#!/usr/bin/env python3
"""Build a formal-provider proof pack from deterministic demo output.

The script runs the no-cost formal-provider bundle fixture by default, then
checks it against the LeanMill overlay declarations. It does not run LeanMill,
install provider code, approve trust, or mutate durable org state.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.adapter_conformance import (  # noqa: E402
    load_adapter_conformance_config,
    load_adapter_manifest,
)
from cognitive_firm.orchestration.formal_verification import (  # noqa: E402
    FormalProviderProofPackInput,
    build_formal_provider_proof_pack,
)


DEFAULT_MANIFEST = (
    ROOT
    / "distro"
    / "leanmill-formal-verification"
    / "files"
    / "adapters"
    / "leanmill-formal-verification.yaml"
)
DEFAULT_CONFIG = (
    ROOT
    / "distro"
    / "leanmill-formal-verification"
    / "files"
    / "adapter_conformance"
    / "leanmill-formal-verification.json"
)
DEFAULT_TRUST_POLICY = (
    ROOT
    / "distro"
    / "leanmill-formal-verification"
    / "files"
    / "formal_verification"
    / "trusted_providers.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a projection-only formal-provider proof pack. By default it "
            "runs the deterministic no-cost formal-provider demo in a temporary "
            "workspace."
        )
    )
    parser.add_argument("--adapter-id", default="leanmill-formal-verification")
    parser.add_argument("--provider-id", default="leanmill")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--conformance-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--trust-policy", type=Path, default=DEFAULT_TRUST_POLICY)
    parser.add_argument(
        "--demo-result",
        type=Path,
        help="Existing full-JSON formal-provider demo output. If omitted, the script runs the demo.",
    )
    parser.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Additional reviewer evidence ref to cite in the packet.",
    )
    parser.add_argument("--markdown", action="store_true", help="Print Markdown instead of JSON.")
    parser.add_argument("--output", type=Path, help="Optional output path. Stdout is still written.")
    args = parser.parse_args(argv)

    demo_payload = (
        _load_json(args.demo_result)
        if args.demo_result
        else _run_demo("formal_provider_bundle_demo.py")
    )
    manifest = load_adapter_manifest(args.manifest)
    config = load_adapter_conformance_config(args.conformance_config)
    trust_policy = _load_json(args.trust_policy)
    packet = build_formal_provider_proof_pack(
        FormalProviderProofPackInput(
            adapter_id=args.adapter_id,
            provider_id=args.provider_id,
            demo_payload=demo_payload,
            manifest=manifest.as_dict(),
            conformance_config=config.as_dict(),
            trust_policy=trust_policy,
            evidence_refs=tuple(args.evidence_ref),
            metadata={
                "demo_source": str(
                    args.demo_result or "scripts/formal_provider_bundle_demo.py --full-json"
                ),
                "manifest_source": str(args.manifest),
                "conformance_config_source": str(args.conformance_config),
                "trust_policy_source": str(args.trust_policy),
            },
        )
    )
    rendered = (
        packet["markdown"].rstrip() + "\n"
        if args.markdown
        else json.dumps(packet, indent=2, sort_keys=True) + "\n"
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if packet["summary"]["ok"] else 1


def _run_demo(script_name: str) -> dict[str, Any]:
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    if env.get("PYTHONPATH"):
        pythonpath = pythonpath + os.pathsep + env["PYTHONPATH"]
    env["PYTHONPATH"] = pythonpath
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script_name), "--full-json"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    return _parse_json(result.stdout, label=script_name)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return _parse_json(path.read_text(encoding="utf-8"), label=str(path))
    except OSError as exc:
        raise SystemExit(f"cannot read JSON {path}: {exc}") from exc


def _parse_json(text: str, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"cannot parse JSON from {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} must contain a JSON object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
