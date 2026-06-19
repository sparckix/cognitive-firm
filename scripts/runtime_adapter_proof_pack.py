#!/usr/bin/env python3
"""Build a runtime-adapter proof pack from deterministic demo outputs.

The script runs no-cost native and LangGraph-style fixtures by default, then
hands their JSON outputs to the adapter-conformance checker. It does not run
LangGraph, install adapter code, or mutate durable org state.
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
    RuntimeAdapterProofPackInput,
    build_runtime_adapter_proof_pack,
    load_adapter_conformance_config,
    load_adapter_manifest,
)


DEFAULT_MANIFEST = (
    ROOT
    / "distro"
    / "langgraph-runtime-adapter"
    / "files"
    / "adapters"
    / "langgraph-runtime-adapter.yaml"
)
DEFAULT_CONFIG = (
    ROOT
    / "distro"
    / "langgraph-runtime-adapter"
    / "files"
    / "adapter_conformance"
    / "langgraph-runtime-adapter.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a projection-only runtime-adapter proof pack. By default it "
            "runs deterministic no-cost demos in temporary workspaces."
        )
    )
    parser.add_argument("--adapter-id", default="langgraph-runtime-adapter")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--conformance-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--native-result",
        type=Path,
        help="Existing full-JSON native demo output. If omitted, the script runs the demo.",
    )
    parser.add_argument(
        "--runtime-result",
        type=Path,
        help="Existing full-JSON runtime demo output. If omitted, the script runs the demo.",
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

    native_payload = (
        _load_json(args.native_result)
        if args.native_result
        else _run_demo("native_e2e_demo.py")
    )
    runtime_payload = (
        _load_json(args.runtime_result)
        if args.runtime_result
        else _run_demo("langgraph_governance_demo.py")
    )
    manifest = load_adapter_manifest(args.manifest)
    config = load_adapter_conformance_config(args.conformance_config)
    packet = build_runtime_adapter_proof_pack(
        RuntimeAdapterProofPackInput(
            adapter_id=args.adapter_id,
            native_payload=native_payload,
            runtime_payload=runtime_payload,
            manifest=manifest,
            conformance_config=config,
            evidence_refs=tuple(args.evidence_ref),
            metadata={
                "native_source": str(args.native_result or "scripts/native_e2e_demo.py --full-json"),
                "runtime_source": str(
                    args.runtime_result or "scripts/langgraph_governance_demo.py --full-json"
                ),
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
        raise SystemExit(f"cannot read result {path}: {exc}") from exc


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
