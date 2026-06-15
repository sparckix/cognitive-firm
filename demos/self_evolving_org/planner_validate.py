from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from demos.self_evolving_org.run import _parse_llm_evolution_steps  # noqa: E402


def validate_planner_file(path: Path, *, max_steps: int = 20) -> dict[str, Any]:
    """Validate a self-evolving demo planner artifact without mutating state."""

    text = Path(path).read_text(encoding="utf-8")
    try:
        steps = _parse_llm_evolution_steps(text, max_steps=max_steps)
    except Exception as exc:  # noqa: BLE001
        return {
            "valid": False,
            "path": str(path),
            "error": str(exc),
            "steps": [],
        }
    return {
        "valid": True,
        "path": str(path),
        "steps": [
            {
                "step_id": step.step_id,
                "change_kind": step.change_kind,
                "target_ref": step.target_ref,
                "applied_relpath": step.applied_relpath,
                "title": step.title,
            }
            for step in steps
        ],
        "step_count": len(steps),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a self-evolving organization demo planner JSON artifact "
            "without opening proposals or mutating org state."
        )
    )
    parser.add_argument("path", type=Path, help="Planner JSON artifact to validate.")
    parser.add_argument("--max-steps", type=int, default=20)
    args = parser.parse_args(argv)

    result = validate_planner_file(args.path, max_steps=args.max_steps)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
