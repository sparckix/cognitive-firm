"""Build a read-only adoption readiness packet from existing smoke outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.governed_run_recipes import (  # noqa: E402
    AdoptionReadinessPacketInput,
    build_adoption_readiness_packet,
    refresh_adoption_readiness_packet_projection,
    render_adoption_readiness_packet_markdown,
)

DEFAULT_ONRAMP_ROOT = ROOT / ".cognitive-firm-runs" / "adoption-onramp"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a projection-only adoption readiness packet. The script "
            "does not run smokes or mutate kernel state."
        )
    )
    parser.add_argument(
        "--target-label",
        default="local_adopter",
        help="Human label for the adopter, pilot, or release review target.",
    )
    parser.add_argument(
        "--result",
        action="append",
        default=[],
        metavar="CHECK_ID=PATH",
        help=(
            "Observed JSON result for a check, for example "
            "kernel_service_smoke=/tmp/kernel-smoke.json. Repeat as needed."
        ),
    )
    parser.add_argument(
        "--include-live-agent",
        action="store_true",
        help="Include optional bounded live-agent proof in the packet.",
    )
    parser.add_argument(
        "--include-release-gate",
        action="store_true",
        help="Include release-candidate-check as a required review gate.",
    )
    parser.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Additional reviewer evidence ref to cite in the packet.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print Markdown instead of JSON.",
    )
    parser.add_argument(
        "--latest-onramp",
        action="store_true",
        help=(
            "Render the latest adoption-onramp packet when one exists; otherwise "
            "fall back to the expected/missing readiness projection."
        ),
    )
    parser.add_argument(
        "--onramp-root",
        type=Path,
        default=DEFAULT_ONRAMP_ROOT,
        help=(
            "Directory containing timestamped adoption-onramp runs. Used only "
            "with --latest-onramp."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the rendered packet. Stdout is still written.",
    )
    args = parser.parse_args(argv)

    packet = (
        _load_latest_onramp_packet(args.onramp_root)
        if args.latest_onramp
        else None
    )
    if packet is None:
        observed_results = _load_results(args.result)
        packet = build_adoption_readiness_packet(
            AdoptionReadinessPacketInput(
                target_label=args.target_label,
                observed_results=observed_results,
                include_live_agent=args.include_live_agent,
                include_release_gate=args.include_release_gate,
                evidence_refs=args.evidence_ref,
                metadata={"collector": "scripts/adoption_readiness_packet.py"},
            )
        )
    rendered = _render_packet(packet, markdown=args.markdown)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


def _load_latest_onramp_packet(onramp_root: Path) -> dict[str, Any] | None:
    if not onramp_root.exists():
        return None
    candidates = sorted(
        (
            packet_path
            for packet_path in onramp_root.glob("*/adoption-readiness-packet.json")
            if packet_path.is_file()
        ),
        key=lambda packet_path: (
            packet_path.parent.stat().st_mtime,
            packet_path.parent.name,
        ),
        reverse=True,
    )
    if not candidates:
        return None
    packet_path = candidates[0]
    try:
        payload = json.loads(packet_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(
            f"cannot read latest on-ramp packet {packet_path}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"cannot parse latest on-ramp packet {packet_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise SystemExit(
            f"latest on-ramp packet {packet_path} must contain a JSON object"
        )
    if payload.get("schema") != "adoption_readiness_packet.v1":
        raise SystemExit(
            f"latest on-ramp packet {packet_path} has unsupported schema "
            f"{payload.get('schema')!r}"
        )
    packet = dict(payload)
    metadata = dict(packet.get("metadata") or {})
    metadata.setdefault("rendered_from_onramp_packet", str(packet_path))
    packet["metadata"] = metadata
    return refresh_adoption_readiness_packet_projection(packet)


def _render_packet(packet: dict[str, Any], *, markdown: bool) -> str:
    if markdown:
        return render_adoption_readiness_packet_markdown(packet).rstrip() + "\n"
    return json.dumps(packet, indent=2, sort_keys=True) + "\n"


def _load_results(items: list[str]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit("--result must use CHECK_ID=PATH")
        check_id, raw_path = item.split("=", 1)
        check_id = check_id.strip()
        path = Path(raw_path.strip())
        if not check_id:
            raise SystemExit("--result check id cannot be blank")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise SystemExit(f"cannot read result {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SystemExit(f"cannot parse result {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise SystemExit(f"result {path} must contain a JSON object")
        results[check_id] = payload
    return results


if __name__ == "__main__":
    raise SystemExit(main())
