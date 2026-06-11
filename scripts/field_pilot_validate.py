#!/usr/bin/env python3
"""Validate a field-pilot folder before or after a pilot run."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_impact import summary_from_mapping  # noqa: E402


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
ACTION_IMPACT_SUMMARY_NAMES = (
    "action-impact-summary.json",
    "action_impact_summary.json",
    "org/action_impact/action_impact_summary.json",
)


def validate_pilot(
    path: Path,
    *,
    require_action_impact: bool = False,
    min_action_impact_records: int = 0,
) -> dict[str, object]:
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
    action_impact = _action_impact_status(path, errors=errors, warnings=warnings)
    if require_action_impact and not action_impact["present"]:
        errors.append(
            "action-impact summary required; add one of: "
            + ", ".join(ACTION_IMPACT_SUMMARY_NAMES)
        )
    if action_impact["present"] and action_impact["n_total"] < min_action_impact_records:
        errors.append(
            "action-impact summary has too few records: "
            f"{action_impact['n_total']} < {min_action_impact_records}"
        )

    ok = not errors
    return {
        "ok": ok,
        "path": str(path),
        "errors": errors,
        "warnings": warnings,
        "required_files": sorted(REQUIRED_FILES),
        "action_impact": action_impact,
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


def _action_impact_status(
    path: Path,
    *,
    errors: list[str],
    warnings: list[str],
) -> dict[str, object]:
    summary_path = _find_action_impact_summary(path)
    if summary_path is None:
        return {
            "present": False,
            "path": None,
            "n_total": 0,
            "n_measured": 0,
            "n_review_required": 0,
            "n_local_with_negative_externalities": 0,
        }
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("summary JSON must be an object")
        summary = summary_from_mapping(payload, root=str(summary_path.parent))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{summary_path.name}: invalid action-impact summary: {exc}")
        return {
            "present": True,
            "path": str(summary_path),
            "n_total": 0,
            "n_measured": 0,
            "n_review_required": 0,
            "n_local_with_negative_externalities": 0,
        }
    if summary.n_total and not summary.n_measured:
        warnings.append(f"{summary_path.name}: action-impact rows are present but none are measured")
    if summary.n_review_required:
        warnings.append(
            f"{summary_path.name}: {summary.n_review_required} action-impact rows require review"
        )
    if summary.n_local_with_negative_externalities:
        warnings.append(
            f"{summary_path.name}: {summary.n_local_with_negative_externalities} local rows carry negative externalities"
        )
    return {
        "present": True,
        "path": str(summary_path),
        "n_total": summary.n_total,
        "n_measured": summary.n_measured,
        "n_review_required": summary.n_review_required,
        "n_local_with_negative_externalities": summary.n_local_with_negative_externalities,
    }


def _find_action_impact_summary(path: Path) -> Path | None:
    for name in ACTION_IMPACT_SUMMARY_NAMES:
        candidate = path / name
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot_dir", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="Return success for a freshly scaffolded but incomplete pilot pack.",
    )
    parser.add_argument(
        "--require-action-impact",
        action="store_true",
        help="Require a machine-readable action-impact summary in the pilot folder.",
    )
    parser.add_argument(
        "--min-action-impact-records",
        type=int,
        default=0,
        help="Minimum action-impact rows required when a summary is present.",
    )
    args = parser.parse_args()
    result = validate_pilot(
        args.pilot_dir,
        require_action_impact=args.require_action_impact,
        min_action_impact_records=args.min_action_impact_records,
    )
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
