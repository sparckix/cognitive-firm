"""Tests for O3-P3 (remote git-URL install) and O3-P5 (distro inheritance)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DISTRO_DIR = REPO_ROOT / "distro"

from cognitive_firm.distribution.cli import main as distro_main


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True,
        capture_output=True, text=True,
    )


# --- O3-P5: distro inheritance ----------------------------------------------

def test_extends_installs_the_base_distro_first(tmp_path):
    # a registry holding starter-firm (the base) plus a thin extender
    registry = tmp_path / "registry"
    shutil.copytree(DISTRO_DIR, registry)
    ext = registry / "my-extension"
    (ext / "files").mkdir(parents=True)
    (ext / "files" / "prefs.yaml").write_text(
        "principal_id: extended\nreview_cadence: weekly\n"
    )
    (ext / "package.yaml").write_text(
        "schema_version: 1\nname: my-extension\nversion: 0.1.0\n"
        "kind: overlay\n"
        "description: a thin overlay that extends the starter-firm distro\n"
        "extends: starter-firm\n"
        "components:\n"
        "  - source: prefs.yaml\n"
        "    dest: preferences/principal.yaml\n"
        "    op: replace\n"
    )
    target = tmp_path / "org"
    rc = distro_main(
        ["--registry", str(registry), "install", "my-extension",
         "--into", str(target)]
    )
    assert rc == 0
    # the base distro's roles were installed first...
    assert (target / "roles" / "principal.yaml").is_file()
    # ...and the extender's change is applied on top
    assert "extended" in (
        target / "preferences" / "principal.yaml"
    ).read_text()


# --- O3-P3: install from a git URL ------------------------------------------

def test_install_from_a_git_url(tmp_path):
    # a package published as a git repository (starter-firm, git-initialised)
    repo = tmp_path / "remote-pkg"
    shutil.copytree(DISTRO_DIR / "starter-firm", repo)
    _git(["init"], repo)
    _git(["-c", "user.name=t", "-c", "user.email=t@t", "add", "-A"], repo)
    _git(
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "pkg"],
        repo,
    )
    target = tmp_path / "org"
    rc = distro_main(["install", f"file://{repo}", "--into", str(target)])
    assert rc == 0
    assert (target / "roles" / "principal.yaml").is_file()
    # the fetch recorded a lockfile
    assert (target / ".cognitive-firm" / "packages.lock").is_file()
