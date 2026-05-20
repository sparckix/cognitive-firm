#!/usr/bin/env python3
"""Copy field-pilot starter templates into a tenant workspace."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "docs" / "templates" / "field-pilot"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="Directory to create or update.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing template files.")
    args = parser.parse_args()

    if not TEMPLATE_DIR.exists():
        raise SystemExit(f"template directory is missing: {TEMPLATE_DIR}")
    args.target.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    skipped: list[str] = []
    for source in sorted(TEMPLATE_DIR.glob("*.md")):
        destination = args.target / source.name
        if destination.exists() and not args.force:
            skipped.append(source.name)
            continue
        shutil.copyfile(source, destination)
        copied.append(source.name)

    print(f"field pilot scaffold: {args.target}")
    if copied:
        print("copied:")
        for name in copied:
            print(f"- {name}")
    if skipped:
        print("skipped existing files:")
        for name in skipped:
            print(f"- {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
