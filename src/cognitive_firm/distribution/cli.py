"""``cognitive-firm-distro`` - install, inspect, and roll back distribution
packages.

This is the operator-facing installer of the OS analogy: one command turns an
empty directory into a running governed organization, and one command rolls a
bad install back.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cognitive_firm.distribution.installer import (
    install,
    load_receipt,
    upgrade,
    verify_install,
)
from cognitive_firm.distribution.registry import PackageIndex, discover_packages
from cognitive_firm.distribution.rollback import RollbackError, rollback


def _default_registry() -> Path:
    """Locate the bundled ``distro/`` registry, from a checkout or a wheel."""
    here = Path(__file__).resolve()
    # source checkout: <repo>/distro ; installed wheel: <site-packages>/distro
    for candidate in (here.parents[3] / "distro", here.parents[2] / "distro"):
        if candidate.is_dir():
            return candidate
    try:  # installed wheel — the packaged `distro` data tree
        import importlib.resources as resources

        packaged = Path(str(resources.files("distro")))
        if packaged.is_dir():
            return packaged
    except (ImportError, ModuleNotFoundError, TypeError, AttributeError):
        pass
    return here.parents[3] / "distro"  # may not exist; reported as empty


def _registry_root(args: argparse.Namespace) -> Path:
    return Path(args.registry) if args.registry else _default_registry()


def _index(args: argparse.Namespace) -> PackageIndex:
    index = discover_packages(_registry_root(args))
    for err in index.errors:
        print(f"warning: {err}", file=sys.stderr)
    return index


def _summary(text: str, width: int = 64) -> str:
    flat = " ".join(text.split())
    return flat[: width - 1] + "…" if len(flat) > width else flat


def _cmd_list(args: argparse.Namespace) -> int:
    index = _index(args)
    if not index.entries:
        print("no packages found.")
        return 0
    for entry in index.entries:
        m = entry.manifest
        print(
            f"{m.name:<20} {m.version:<10} {m.kind:<8} {_summary(m.description)}"
        )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    entry = _index(args).get(args.package)
    if entry is None:
        print(f"ERROR: package not found: {args.package}", file=sys.stderr)
        return 2
    m = entry.manifest
    print(f"name:        {m.name}")
    print(f"version:     {m.version}")
    print(f"kind:        {m.kind}")
    print(f"description: {_summary(m.description, 200)}")
    if m.kernel.min_version or m.kernel.max_version:
        print(
            f"kernel:      >= {m.kernel.min_version or '*'}, "
            f"<= {m.kernel.max_version or '*'}"
        )
    if m.provides:
        print(f"provides:    {', '.join(m.provides)}")
    print("components:")
    for c in m.components:
        opt = " (optional)" if c.optional else ""
        print(f"  - files/{c.source} -> {c.dest}{opt}")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    index = _index(args)
    entry = index.get(args.package)
    if entry is None:
        available = ", ".join(e.name for e in index.entries) or "(none)"
        print(f"ERROR: package not found: {args.package}", file=sys.stderr)
        print(f"available: {available}", file=sys.stderr)
        return 2

    target = Path(args.into)
    receipt = install(entry.manifest, entry.root, target, force=args.force)
    created = sum(1 for f in receipt.files if f.action == "created")
    overwritten = sum(1 for f in receipt.files if f.action == "overwritten")
    print(
        f"installed {receipt.package} {receipt.version} ({receipt.kind}) "
        f"-> {receipt.target_root}"
    )
    print(
        f"  files: {created} created, {overwritten} overwritten, "
        f"{len(receipt.skipped_conflicts)} skipped"
    )
    print(f"  committed as {receipt.git_tag or receipt.commit_sha[:12]}")
    if receipt.skipped_conflicts and not args.force:
        print(
            "  skipped files already existed; re-run with --force to "
            "overwrite:",
            file=sys.stderr,
        )
        for dest in receipt.skipped_conflicts:
            print(f"    {dest}", file=sys.stderr)

    issues = verify_install(receipt, target)
    if issues:
        print("VERIFY FAILED:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print("  verify: ok - the installed organization boots and is governable")
    if entry.manifest.post_install_message:
        print()
        print(entry.manifest.post_install_message.rstrip())
    return 0


def _cmd_upgrade(args: argparse.Namespace) -> int:
    index = _index(args)
    entry = index.get(args.package)
    if entry is None:
        print(f"ERROR: package not found: {args.package}", file=sys.stderr)
        return 2
    target = Path(args.into)
    receipt = upgrade(entry.manifest, entry.root, target)
    print(
        f"upgraded {receipt.package} to {receipt.version} "
        f"-> {receipt.target_root}"
    )
    issues = verify_install(receipt, target)
    if issues:
        print("VERIFY FAILED:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print("  verify: ok")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    target = Path(args.into)
    try:
        receipt = load_receipt(target, args.package)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    issues = verify_install(receipt, target)
    if issues:
        print(f"VERIFY FAILED for {args.package}:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1
    print(f"verify ok: {args.package} at {target} boots and is governable")
    return 0


def _do_rollback(target: Path, package: str, reason: str) -> int:
    try:
        result = rollback(target, package, reason=reason)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except RollbackError as exc:
        print(f"ROLLBACK BLOCKED: {exc}", file=sys.stderr)
        return 1
    print(f"rolled back {result.package} ({result.mode})")
    if result.mode == "compensating":
        print(
            "  the org ran under the rolled-back config; review the work "
            "produced in that window."
        )
    return 0


def _cmd_rollback(args: argparse.Namespace) -> int:
    return _do_rollback(Path(args.into), args.package, args.reason)


def _cmd_uninstall(args: argparse.Namespace) -> int:
    return _do_rollback(Path(args.into), args.package, "uninstall")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cognitive-firm-distro",
        description="Install, inspect, and roll back distribution packages.",
    )
    parser.add_argument(
        "--registry",
        help="Registry directory (default: the bundled distro/).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List available packages.")
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="Show one package manifest.")
    p_show.add_argument("package")
    p_show.set_defaults(func=_cmd_show)

    p_install = sub.add_parser(
        "install", help="Install a package into a directory."
    )
    p_install.add_argument("package")
    p_install.add_argument(
        "--into", required=True, help="Target organization directory."
    )
    p_install.add_argument(
        "--force", action="store_true", help="Overwrite existing files."
    )
    p_install.set_defaults(func=_cmd_install)

    p_upgrade = sub.add_parser(
        "upgrade", help="Install a newer package version over an org."
    )
    p_upgrade.add_argument("package")
    p_upgrade.add_argument("--into", required=True)
    p_upgrade.set_defaults(func=_cmd_upgrade)

    p_verify = sub.add_parser("verify", help="Re-verify an installed package.")
    p_verify.add_argument("package")
    p_verify.add_argument("--into", required=True)
    p_verify.set_defaults(func=_cmd_verify)

    p_rollback = sub.add_parser(
        "rollback", help="Roll back a package install."
    )
    p_rollback.add_argument("package")
    p_rollback.add_argument("--into", required=True)
    p_rollback.add_argument(
        "--reason", default="operator-initiated rollback",
        help="Why the install is being rolled back (recorded).",
    )
    p_rollback.set_defaults(func=_cmd_rollback)

    p_uninstall = sub.add_parser(
        "uninstall", help="Remove an installed package (rolls its install back)."
    )
    p_uninstall.add_argument("package")
    p_uninstall.add_argument("--into", required=True)
    p_uninstall.set_defaults(func=_cmd_uninstall)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
