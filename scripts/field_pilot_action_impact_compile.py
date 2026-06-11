#!/usr/bin/env python3
"""Compile measured field-pilot rows into an action-impact summary."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.action_impact import summary_from_mapping  # noqa: E402
from field_pilot_validate import validate_pilot  # noqa: E402


DEFAULT_OUTPUT = "action-impact-summary.json"
JSON_FIELDS = {
    "artifact_refs",
    "context",
    "context_features",
    "externalities",
    "externality_tags",
    "guardrail_metrics",
    "metadata",
    "negative_externality_tags",
}
BOOL_FIELDS = {"decision_changed_bool", "decision_changed", "requires_human_review"}
FLOAT_FIELDS = {
    "actual_impact",
    "cost_units",
    "expected_impact",
    "human_review_burden",
    "impact",
    "logging_policy_probability",
    "propensity",
    "reward",
    "wall_seconds",
}


def compile_action_impact(
    pilot_dir: Path,
    rows_path: Path,
    *,
    output_path: Path | None = None,
    validate: bool = False,
    min_records: int = 0,
) -> dict[str, Any]:
    rows = load_rows(rows_path)
    target = output_path or pilot_dir / DEFAULT_OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    summary = summary_from_mapping(
        {
            "root": str(pilot_dir),
            "records": rows,
        },
        root=str(pilot_dir),
    )
    target.write_text(
        json.dumps(summary.as_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    validation = None
    if validate:
        validation = validate_pilot(
            pilot_dir,
            require_action_impact=True,
            min_action_impact_records=min_records,
        )
    return {
        "compiler": "field_pilot_action_impact",
        "input": str(rows_path),
        "output": str(target),
        "summary": {
            "n_total": summary.n_total,
            "n_measured": summary.n_measured,
            "n_review_required": summary.n_review_required,
            "n_local_with_negative_externalities": summary.n_local_with_negative_externalities,
            "mean_actual_impact_by_metric": summary.mean_actual_impact_by_metric,
        },
        "validation": validation,
        "verdict": "passed" if validation is None or validation["ok"] else "failed",
    }


def load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}: line {line_number} is not a JSON object")
            rows.append(payload)
        return rows
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [_require_mapping(row, path) for row in payload]
        if isinstance(payload, dict):
            rows = payload.get("records") or payload.get("actions")
            if isinstance(rows, list):
                return [_require_mapping(row, path) for row in rows]
        raise ValueError(f"{path}: expected a JSON list or object with records/actions")
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [_normalize_csv_row(row) for row in csv.DictReader(handle)]
    raise ValueError(f"{path}: unsupported extension; use .csv, .json, or .jsonl")


def _require_mapping(row: Any, path: Path) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError(f"{path}: expected every row to be an object")
    return row


def _normalize_csv_row(row: dict[str, str | None]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        clean_key = key.strip()
        if not clean_key or value is None or value == "":
            continue
        raw = value.strip()
        if clean_key in JSON_FIELDS:
            out[clean_key] = _parse_jsonish(raw, clean_key)
        elif clean_key in BOOL_FIELDS:
            out[clean_key] = _parse_bool(raw)
        elif clean_key in FLOAT_FIELDS:
            out[clean_key] = float(raw)
        else:
            out[clean_key] = raw
    return out


def _parse_jsonish(value: str, field_name: str) -> Any:
    if value.startswith("{") or value.startswith("["):
        return json.loads(value)
    if field_name.endswith("_tags") or field_name == "artifact_refs":
        return [part.strip() for part in value.split(",") if part.strip()]
    raise ValueError(f"{field_name} must be valid JSON")


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"expected boolean, got {value!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot_dir", type=Path)
    parser.add_argument("rows", type=Path, help="CSV, JSON, or JSONL action-impact rows.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--min-records", type=int, default=0)
    args = parser.parse_args(argv)

    payload = compile_action_impact(
        args.pilot_dir,
        args.rows,
        output_path=args.output,
        validate=args.validate,
        min_records=args.min_records,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["verdict"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
