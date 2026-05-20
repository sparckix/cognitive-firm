"""Project-charter parsing for tenant/project scope fidelity.

The kernel only validates the generic charter shape. Tenants own the actual
project content, anchor semantics, and enforcement thresholds.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REQUIRED_SECTIONS = (
    "core question",
    "out of scope",
    "end states",
    "forecast type",
    "inheritance",
    "anchor proxies",
)

VALID_FORECAST_TYPES = {
    "none",
    "directional_forecast",
    "probabilistic_forecast",
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ANCHOR_RE = re.compile(r"^\s*(?:[-*]\s*)?anchor\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
_FIELD_RE = re.compile(r"^\s*(?:[-*]\s*)?(?P<key>[a-zA-Z][a-zA-Z0-9_-]*)\s*:\s*(?P<value>.+?)\s*$")


@dataclass(frozen=True)
class AnchorProxy:
    """A tenant-defined object-level scope anchor."""

    name: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectCharter:
    """Parsed representation of a project charter."""

    path: Path | None
    sections: dict[str, str]
    anchors: list[AnchorProxy]
    forecast_type: str | None

    @property
    def missing_sections(self) -> list[str]:
        return [section for section in REQUIRED_SECTIONS if not self.sections.get(section, "").strip()]

    @property
    def is_valid(self) -> bool:
        return not validate_project_charter(self)


def _normalize_heading(text: str) -> str:
    return text.strip().rstrip(":").lower()


def _split_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for line in markdown.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            heading = _normalize_heading(match.group(2))
            current = heading
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)

    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def parse_anchor_proxies(text: str) -> list[AnchorProxy]:
    """Parse simple anchor blocks from the Anchor Proxies section.

    Supported shape:

    ```text
    - anchor: approval_boundary_preserved
      type: checklist_id
      predicate: approval remains required above threshold
    ```

    The parser intentionally does not interpret the fields. It only preserves
    tenant-defined data for downstream validators.
    """
    anchors: list[AnchorProxy] = []
    current_name: str | None = None
    current_fields: dict[str, str] = {}

    def flush() -> None:
        nonlocal current_name, current_fields
        if current_name:
            anchors.append(AnchorProxy(name=current_name, fields=dict(current_fields)))
        current_name = None
        current_fields = {}

    for line in text.splitlines():
        anchor_match = _ANCHOR_RE.match(line)
        if anchor_match:
            flush()
            current_name = anchor_match.group("value").strip()
            current_fields = {}
            continue

        field_match = _FIELD_RE.match(line)
        if current_name and field_match:
            key = field_match.group("key").strip().lower().replace("-", "_")
            if key == "anchor":
                flush()
                current_name = field_match.group("value").strip()
                current_fields = {}
            else:
                current_fields[key] = field_match.group("value").strip()

    flush()
    return anchors


def _parse_forecast_type(text: str) -> str | None:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" in line:
            _, value = line.split(":", 1)
            line = value.strip()
        line = line.strip("-*` ").lower()
        if line:
            return line
    return None


def parse_project_charter(markdown: str, *, path: Path | None = None) -> ProjectCharter:
    sections = _split_sections(markdown)
    forecast_type = _parse_forecast_type(sections.get("forecast type", ""))
    anchors = parse_anchor_proxies(sections.get("anchor proxies", ""))
    return ProjectCharter(
        path=path,
        sections=sections,
        anchors=anchors,
        forecast_type=forecast_type,
    )


def load_project_charter(path: Path | str) -> ProjectCharter:
    charter_path = Path(path)
    return parse_project_charter(charter_path.read_text(encoding="utf-8"), path=charter_path)


def validate_project_charter(charter: ProjectCharter) -> list[str]:
    """Return validation errors for the generic charter contract."""
    errors: list[str] = []
    for section in charter.missing_sections:
        errors.append(f"missing required section: {section}")

    if charter.forecast_type and charter.forecast_type not in VALID_FORECAST_TYPES:
        errors.append(
            "invalid forecast type: "
            f"{charter.forecast_type!r}; expected one of {sorted(VALID_FORECAST_TYPES)}"
        )

    if charter.sections.get("anchor proxies", "").strip() and not charter.anchors:
        errors.append("anchor proxies section is present but no `anchor:` entries were parsed")

    return errors


def charter_summary(charter: ProjectCharter) -> dict[str, Any]:
    """Return a JSON-serializable summary for CLIs and predispatch hooks."""
    errors = validate_project_charter(charter)
    return {
        "path": str(charter.path) if charter.path else None,
        "valid": not errors,
        "errors": errors,
        "forecast_type": charter.forecast_type,
        "anchors": [
            {
                "name": anchor.name,
                "fields": anchor.fields,
            }
            for anchor in charter.anchors
        ],
        "sections": sorted(charter.sections),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a cognitive-firm project charter.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    charter = load_project_charter(args.path)
    errors = validate_project_charter(charter)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
