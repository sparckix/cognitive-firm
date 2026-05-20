#!/usr/bin/env python3
"""Strict smoke for the field-pilot validator with a minimally completed pack."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from field_pilot_validate import validate_pilot


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "docs" / "templates" / "field-pilot"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-field-pilot-validator-") as raw:
        target = Path(raw) / "pilot"
        target.mkdir()
        for source in TEMPLATE_DIR.glob("*.md"):
            shutil.copyfile(source, target / source.name)
        scope = target / "pilot-scope.md"
        text = scope.read_text(encoding="utf-8")
        text = text.replace(
            "The pilot passes if:\n\n- ",
            "The pilot passes if:\n\n- error rate falls without increased human burden\n",
        )
        scope.write_text(text, encoding="utf-8")
        for path in target.glob("*.md"):
            lines = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if _has_blank_table_cells(line):
                    cells = [cell.strip() for cell in line.strip("|").split("|")]
                    line = "|" + "|".join([f" {cell or 'example'} " for cell in cells]) + "|"
                lines.append(line)
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = validate_pilot(target)
        print(json.dumps(result, sort_keys=True))
        if not result["ok"]:
            raise SystemExit(1)
    return 0


def _has_blank_table_cells(line: str) -> bool:
    if not line.startswith("|"):
        return False
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    if len(cells) < 3:
        return False
    if set(cells[1]) <= {"-"}:
        return False
    return any(cell == "" for cell in cells[1:])


if __name__ == "__main__":
    raise SystemExit(main())
