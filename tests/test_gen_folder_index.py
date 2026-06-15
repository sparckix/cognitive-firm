from __future__ import annotations

from pathlib import Path

from scripts.gen_folder_index import END, START, refresh_readmes, render_index


def test_render_index_lists_documents_and_ignores_cache_dirs(tmp_path: Path) -> None:
    (tmp_path / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Root\n", encoding="utf-8")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "junk.pyc").write_text("ignored", encoding="utf-8")
    child = tmp_path / "child"
    child.mkdir()
    (child / "note.md").write_text("# Note\n", encoding="utf-8")

    index = render_index(tmp_path)

    assert "[alpha.md](alpha.md)" in index
    assert "[`child/`](child/) - 1 file(s)" in index
    assert "README.md" not in index
    assert "__pycache__" not in index


def test_refresh_readmes_replaces_managed_block_and_normalizes_newline(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Demo",
                "",
                f"{START} (managed)",
                "",
                "old generated text",
                "",
                END,
                "",
                "suffix",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "new-doc.md").write_text("# New\n", encoding="utf-8")

    refresh_readmes(tmp_path)

    text = readme.read_text(encoding="utf-8")
    assert "old generated text" not in text
    assert "[new-doc.md](new-doc.md)" in text
    assert text.endswith("\n")
    assert text.count(START) == 1
    assert text.count(END) == 1
    assert text.rstrip().endswith("suffix")


def test_refresh_readmes_repairs_missing_end_marker(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Demo",
                "",
                f"{START} (managed)",
                "",
                "stale generated text",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "doc.md").write_text("# Doc\n", encoding="utf-8")

    refresh_readmes(tmp_path)

    text = readme.read_text(encoding="utf-8")
    assert "stale generated text" not in text
    assert "[doc.md](doc.md)" in text
    assert text.count(START) == 1
    assert text.count(END) == 1
    assert text.endswith("\n")
