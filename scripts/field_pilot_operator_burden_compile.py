#!/usr/bin/env python3
"""Compile measured field-pilot rows into an operator-burden summary."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.governed_run_recipes import (  # noqa: E402
    summarize_operator_burden_field_pilot,
)


DEFAULT_OUTPUT = "operator-burden-field-pilot-summary.json"
JSON_FIELDS = {"operator_burden", "operator_burden_projection", "metadata"}
BOOL_FIELDS = {"hidden_burden_reported", "burden_shift_reported"}
INT_FIELDS = {
    "missing_receipts",
    "rework_count",
    "review_required",
    "review_required_count",
    "stale_sessions",
}
FLOAT_FIELDS = {
    "actual_human_touchpoints",
    "coordination_minutes",
    "human_coordination_minutes",
    "human_touchpoints",
    "manual_touchpoints",
    "operator_touchpoints",
    "projected_human_touchpoints",
    "projected_operator_touchpoints",
    "review_minutes",
}


def compile_operator_burden(
    pilot_dir: Path,
    rows_path: Path,
    *,
    output_path: Path | None = None,
    min_baseline_runs: int = 1,
    min_pilot_runs: int = 1,
    max_touchpoint_increase_rate: float = 0.1,
    projection_tolerance: float = 1.0,
) -> dict[str, Any]:
    rows = load_rows(rows_path)
    target = output_path or pilot_dir / DEFAULT_OUTPUT
    target.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize_operator_burden_field_pilot(
        rows,
        min_baseline_runs=min_baseline_runs,
        min_pilot_runs=min_pilot_runs,
        max_touchpoint_increase_rate=max_touchpoint_increase_rate,
        projection_tolerance=projection_tolerance,
    )
    target.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "compiler": "field_pilot_operator_burden",
        "input": str(rows_path),
        "output": str(target),
        "summary": {
            "schema": summary["schema"],
            "measurement_status": summary["measurement_status"],
            "n_total": summary["n_total"],
            "baseline_runs": summary["phases"]["baseline"]["n_runs"],
            "pilot_runs": summary["phases"]["pilot"]["n_runs"],
            "mean_touchpoint_delta": summary["deltas"][
                "mean_actual_human_touchpoints"
            ],
            "projection_undercounted_rows": len(
                summary["projection_fit"]["undercounted_rows"]
            ),
            "review_reasons": summary["review_reasons"],
        },
        "verdict": "passed"
        if summary["measurement_status"] == "stable"
        else "review_required",
    }


def load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
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
            rows = payload.get("records") or payload.get("runs")
            if isinstance(rows, list):
                return [_require_mapping(row, path) for row in rows]
        raise ValueError(f"{path}: expected a JSON list or object with records/runs")
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
            out[clean_key] = json.loads(raw)
        elif clean_key in BOOL_FIELDS:
            out[clean_key] = _parse_bool(raw)
        elif clean_key in INT_FIELDS:
            out[clean_key] = int(raw)
        elif clean_key in FLOAT_FIELDS:
            out[clean_key] = float(raw)
        else:
            out[clean_key] = raw
    return out


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
    parser.add_argument("rows", type=Path, help="CSV, JSON, or JSONL burden rows.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-baseline-runs", type=int, default=1)
    parser.add_argument("--min-pilot-runs", type=int, default=1)
    parser.add_argument("--max-touchpoint-increase-rate", type=float, default=0.1)
    parser.add_argument("--projection-tolerance", type=float, default=1.0)
    args = parser.parse_args(argv)

    payload = compile_operator_burden(
        args.pilot_dir,
        args.rows,
        output_path=args.output,
        min_baseline_runs=args.min_baseline_runs,
        min_pilot_runs=args.min_pilot_runs,
        max_touchpoint_increase_rate=args.max_touchpoint_increase_rate,
        projection_tolerance=args.projection_tolerance,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["verdict"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
