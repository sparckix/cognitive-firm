#!/usr/bin/env python3
"""Check that adopter-facing docs name the main kernel composition layer."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.state_surface_inventory import list_state_surfaces  # noqa: E402

REQUIRED_DOCS = (
    "docs/abstraction-map.md",
    "docs/resource-event-catalog.md",
    "docs/blueprints/README.md",
    "docs/examples/app-service-integration-example.md",
    "docs/templates/field-pilot/README.md",
    "docs/reader-checklist.md",
)

ENTRYPOINTS = (
    "README.md",
    "docs/README.md",
    "docs/first-30-minutes.md",
)

STATE_CLASS_LABELS = {
    "canonical_state": "canonical state",
    "read_model": "read model",
    "projection": "projection",
    "telemetry": "telemetry",
    "tenant_owned_ledger": "tenant-owned ledger",
}


def main() -> int:
    missing = [path for path in REQUIRED_DOCS if not (ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required docs: {', '.join(missing)}")

    for path in ENTRYPOINTS:
        text = (ROOT / path).read_text()
        for required in REQUIRED_DOCS:
            required_path = Path(required)
            link_token = (
                str(required_path.parent)
                if required_path.name == "README.md"
                else required_path.name
            )
            local_token = link_token.removeprefix("docs/")
            if required not in text and link_token not in text and local_token not in text:
                raise SystemExit(f"{path} does not link {required}")

    catalog = (ROOT / "docs/resource-event-catalog.md").read_text()
    for surface in list_state_surfaces():
        if surface.primitive not in catalog:
            raise SystemExit(f"resource-event catalog missing {surface.primitive}")
        class_label = STATE_CLASS_LABELS.get(str(surface.state_class), str(surface.state_class))
        if class_label not in catalog:
            raise SystemExit(f"resource-event catalog missing state class {class_label}")

    print("OK: docs surface links and catalog anchors are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
