#!/usr/bin/env python3
"""Validate a field-pilot folder before or after a pilot run."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED_FILES = {
    "pilot-scope.md": [
        "Workflow name:",
        "Baseline window:",
        "Pilot window:",
        "Success Criteria",
        "Human coordination burden",
    ],
    "baseline-notes.md": [
        "Number of completed decisions:",
        "Baseline Metrics",
        "Human coordination burden",
        "Baseline Caveats",
    ],
    "metrics-table.md": [
        "Completed decisions",
        "Decision error rate",
        "Human coordination burden",
        "Approved learning events",
        "Outcome Verdict",
        "Burden Verdict",
    ],
    "learning-event-summary.md": [
        "What Changed",
        "Approved learning event",
        "Future Behavior",
        "Residual Risks",
    ],
}


def validate_pilot(path: Path) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    for filename, required_terms in REQUIRED_FILES.items():
        file_path = path / filename
        if not file_path.exists():
            errors.append(f"missing required file: {filename}")
            continue
        text = file_path.read_text(encoding="utf-8")
        for term in required_terms:
            if term not in text:
                errors.append(f"{filename}: missing section or term {term!r}")
        if _has_blank_table_rows(text):
            warnings.append(f"{filename}: contains blank table rows that may need completion")

    scope = _read(path / "pilot-scope.md")
    metrics = _read(path / "metrics-table.md")
    if scope and not re.search(r"The pilot passes if:\n\n- \S", scope):
        errors.append("pilot-scope.md: success criteria appear blank")
    if metrics and "n/a" not in metrics:
        warnings.append("metrics-table.md: expected n/a baseline markers for pilot-only metrics")

    ok = not errors
    return {
        "ok": ok,
        "path": str(path),
        "errors": errors,
        "warnings": warnings,
        "required_files": sorted(REQUIRED_FILES),
    }


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _has_blank_table_rows(text: str) -> bool:
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) >= 3 and all(cell == "" for cell in cells[1:]):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot_dir", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="Return success for a freshly scaffolded but incomplete pilot pack.",
    )
    args = parser.parse_args()
    result = validate_pilot(args.pilot_dir)
    exit_ok = bool(result["ok"]) or args.allow_draft
    if args.allow_draft and not result["ok"]:
        result = {**result, "ready": False, "draft_allowed": True, "ok": True}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"field pilot validation: {args.pilot_dir}")
        print(f"ok: {str(result['ok']).lower()}")
        for error in result["errors"]:  # type: ignore[index]
            print(f"error: {error}")
        for warning in result["warnings"]:  # type: ignore[index]
            print(f"warning: {warning}")
    return 0 if exit_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
