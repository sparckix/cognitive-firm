#!/usr/bin/env python3
"""Refresh README auto-index blocks for selected folders."""

from __future__ import annotations

import argparse
from pathlib import Path

START = "<!-- AUTO-INDEX:START"
END = "<!-- AUTO-INDEX:END -->"
IGNORED_NAMES = {"__pycache__", ".pytest_cache", ".hypothesis", "node_modules", "dist", "build"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=["docs", "org", "scripts", "src"])
    args = parser.parse_args()
    for raw_path in args.paths:
        refresh_readmes(Path(raw_path))
    return 0


def refresh_readmes(root: Path) -> None:
    targets = [root] if (root / "README.md").exists() else []
    targets.extend(path.parent for path in root.rglob("README.md"))
    for folder in sorted(set(targets)):
        readme = folder / "README.md"
        text = readme.read_text()
        if START not in text:
            continue
        readme.write_text(replace_block(text, render_index(folder)).rstrip() + "\n")


def replace_block(text: str, index: str) -> str:
    start_at = text.index(START)
    start_line_end = text.index("\n", start_at)
    if END in text[start_at:]:
        end_at = text.index(END, start_at) + len(END)
        suffix = text[end_at:]
    else:
        suffix = ""
    return text[: start_line_end + 1] + "\n" + index + "\n\n" + END + suffix


def render_index(folder: Path) -> str:
    children = sorted(child for child in folder.iterdir() if not _is_ignored(child))
    subfolders = [child for child in children if child.is_dir()]
    docs = [child for child in children if child.is_file() and child.name != "README.md"]

    lines = ["## Index", ""]
    lines.append("**Sub-folders**")
    lines.append("")
    if subfolders:
        for child in subfolders:
            count = sum(1 for item in child.iterdir() if not _is_ignored(item)) if child.exists() else 0
            lines.append(f"- [`{child.name}/`]({child.name}/) - {count} file(s)")
    else:
        lines.append("- None")

    lines.append("")
    lines.append("**Documents**")
    lines.append("")
    if docs:
        for child in docs:
            lines.append(f"- [{child.name}]({child.name})")
    else:
        lines.append("- None")

    lines.append("")
    lines.append(
        f"<sub>{len(subfolders)} sub-folder(s), {len(docs)} document(s). "
        "Auto-generated; re-run `scripts/gen_folder_index.py` after adding files.</sub>"
    )
    return "\n".join(lines)


def _is_ignored(path: Path) -> bool:
    if path.name.startswith(".") or path.name in IGNORED_NAMES:
        return True
    if path.is_dir():
        try:
            return not any(not _is_ignored(child) for child in path.iterdir())
        except OSError:
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
