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
    plan_install,
    upgrade,
    verify_install,
)
from cognitive_firm.distribution.manifest import (
    ManifestError,
    PackageManifest,
    load_manifest,
    validate_manifest,
)
from cognitive_firm.distribution.registry import (
    MANIFEST_FILENAME,
    PackageIndex,
    discover_packages,
    resolve_extends,
)
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


def _load_manifest_unchecked(
    manifest_path: Path,
) -> tuple[PackageManifest | None, str | None]:
    """Parse a ``package.yaml`` into a manifest WITHOUT raising on validation
    problems — so ``lint`` can report every problem instead of the first one.

    Returns ``(manifest, None)`` on a parseable file, or ``(None, error)`` if
    the file is missing or not even structurally loadable as YAML/a mapping.
    """
    import yaml

    if not manifest_path.is_file():
        return None, f"manifest not found: {manifest_path}"
    try:
        raw = yaml.safe_load(manifest_path.read_text())
    except yaml.YAMLError as exc:
        return None, f"YAML parse error: {exc}"
    try:
        return PackageManifest.from_raw(raw or {}), None
    except ManifestError as exc:
        return None, str(exc)


def _resolve_lint_package(
    args: argparse.Namespace,
) -> tuple[Path, str | None]:
    """Resolve the ``lint`` argument to a package directory.

    The argument may be a filesystem path to a package directory (or its
    ``package.yaml``), or the name of a package in the registry.
    """
    raw = Path(args.package)
    if raw.is_file() and raw.name == MANIFEST_FILENAME:
        return raw.parent, None
    if (raw / MANIFEST_FILENAME).is_file():
        return raw, None
    # Fall back to a registry lookup by name.
    entry = _index(args).get(args.package)
    if entry is not None:
        return entry.root, None
    return raw, (
        f"no package found at path or in registry: {args.package}"
    )


def _cmd_lint(args: argparse.Namespace) -> int:
    """Lint a package: parse its manifest and report authoring problems.

    Exit 0 means the package is clean; non-zero means problems were found.
    This is the O3-P4 third-party authoring inner loop — an author runs it on
    their package directory before publishing, with no install and no org.
    """
    package_root, resolve_err = _resolve_lint_package(args)
    if resolve_err is not None:
        print(f"ERROR: {resolve_err}", file=sys.stderr)
        return 2

    manifest_path = package_root / MANIFEST_FILENAME
    manifest, parse_err = _load_manifest_unchecked(manifest_path)
    if manifest is None:
        print(f"LINT FAILED: {package_root}", file=sys.stderr)
        print(f"  - {parse_err}", file=sys.stderr)
        return 1

    issues = list(validate_manifest(manifest, package_root))

    # Surface authoring mistakes validate_manifest does not cover.
    files_root = package_root / "files"
    if not files_root.is_dir():
        issues.append("no files/ directory — a package ships its overlay there")
    for component in manifest.components:
        src = files_root / component.source
        if component.op == "patch" and component.optional and not src.exists():
            issues.append(
                f"optional patch component has no source: {component.source}"
            )

    if issues:
        print(f"LINT FAILED: {manifest.name or package_root} "
              f"({len(issues)} problem(s))", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    print(
        f"lint ok: {manifest.name} {manifest.version} ({manifest.kind}) — "
        f"{len(manifest.components)} component(s), no problems found"
    )
    return 0


def _print_install_plan(
    manifest: PackageManifest, package_root: Path, target: Path
) -> int:
    """Resolve and print the install plan WITHOUT applying it (``--dry-run``).

    No git repo is created and no files are written — this is a preview an
    author or operator uses to see exactly what an install would do.
    """
    try:
        plan = plan_install(manifest, package_root, target)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        f"dry-run: would install {manifest.name} {manifest.version} "
        f"({manifest.kind}) -> {target}"
    )
    if not plan:
        print("  (no files to install)")
        return 0
    conflicts = 0
    by_op = {c.dest: c.op for c in manifest.components}
    for src_file, dest_rel, conflict in plan:
        # Map the file back to its component to surface the composition op.
        op = next(
            (o for d, o in by_op.items() if dest_rel == d
             or dest_rel.startswith(d + "/")),
            "add",
        )
        marker = "CONFLICT" if conflict else "new"
        if conflict:
            conflicts += 1
        print(f"  [{op:<7}] {dest_rel}  ({marker})")
    print(
        f"  total: {len(plan)} file(s), {conflicts} conflict(s) — "
        "nothing was written"
    )
    return 0


def _is_git_url(value: str) -> bool:
    return "://" in value or value.startswith("git@")


def _cmd_install(args: argparse.Namespace) -> int:
    target = Path(args.into)

    # O3-P3: a git URL is fetched (SHA-pinned, locked); a plain name is
    # resolved from the local registry.
    if _is_git_url(args.package):
        from cognitive_firm.distribution.remote_registry import (
            RemoteFetchError,
            RemotePackageSource,
            fetch_and_lock,
        )

        try:
            fetched, _lockfile = fetch_and_lock(
                RemotePackageSource(url=args.package, ref=args.ref or "HEAD"),
                target,
            )
        except RemoteFetchError as exc:
            print(f"ERROR: remote fetch failed: {exc}", file=sys.stderr)
            return 2
        manifest, package_root = fetched.manifest, fetched.package_root
        print(f"fetched {fetched.pinned_id}")
    else:
        entry = _index(args).get(args.package)
        if entry is None:
            print(f"ERROR: package not found: {args.package}", file=sys.stderr)
            return 2
        manifest, package_root = entry.manifest, entry.root

    if args.dry_run:
        return _print_install_plan(manifest, package_root, target)

    # O3-P5: a package that `extends` a base distro installs the base first.
    if manifest.extends:
        try:
            base = resolve_extends(manifest, _index(args))
        except ManifestError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(
            f"installing base distro '{base.manifest.name}' "
            f"(extended by '{manifest.name}')"
        )
        install(base.manifest, base.root, target, force=args.force)

    receipt = install(manifest, package_root, target, force=args.force)
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
    if manifest.post_install_message:
        print()
        print(manifest.post_install_message.rstrip())
    return 0


def _cmd_install_overlay(args: argparse.Namespace) -> int:
    """Governed install of an overlay onto a *running* organization (O3-P1).

    Stages the overlay, computes the authority-diff, files a governance
    proposal, and prints the diff. Without ``--approve`` it stops there (a
    preview); with ``--approve`` it applies a non-blocked proposal.
    """
    from cognitive_firm.distribution.governed_install import (
        GovernedInstallError,
        apply_approved_install,
        propose_overlay_install,
    )

    target = Path(args.into)
    overlay_path = Path(args.package)
    if (overlay_path / "package.yaml").is_file():
        overlay_root = overlay_path
        try:
            manifest = load_manifest(overlay_root / "package.yaml")
        except ManifestError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    else:
        entry = _index(args).get(args.package)
        if entry is None:
            print(
                f"ERROR: overlay not found: {args.package}", file=sys.stderr
            )
            return 2
        overlay_root, manifest = entry.root, entry.manifest

    try:
        proposed = propose_overlay_install(
            overlay_manifest=manifest,
            overlay_root=overlay_root,
            target_root=target,
            governance_log=(
                target / "governance_changes" / "governance_changes.jsonl"
            ),
        )
    except GovernedInstallError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        f"governance proposal {proposed.proposal.proposal_id} "
        f"-> {proposed.proposal.status}"
    )
    print()
    print(proposed.diff.render())
    print()
    if not proposed.can_proceed:
        print(
            "BLOCKED: this overlay cannot be installed - it fails a required "
            "governance invariant (a package may not widen authority).",
            file=sys.stderr,
        )
        return 1
    if not args.approve:
        print(
            "review the authority-diff above, then re-run with --approve "
            "to install."
        )
        return 0
    try:
        receipt = apply_approved_install(proposed, overlay_root, target)
    except GovernedInstallError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        f"installed overlay {receipt.package} {receipt.version} "
        f"-> {receipt.target_root}"
    )
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
    p_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and print the install plan without applying anything.",
    )
    p_install.add_argument(
        "--ref",
        help="git ref to fetch when the package is a git URL (default HEAD).",
    )
    p_install.set_defaults(func=_cmd_install)

    p_install_overlay = sub.add_parser(
        "install-overlay",
        help="Governed install of an overlay onto a running organization.",
    )
    p_install_overlay.add_argument("package")
    p_install_overlay.add_argument(
        "--into", required=True, help="The running organization directory."
    )
    p_install_overlay.add_argument(
        "--approve",
        action="store_true",
        help="Approve and apply, after reviewing the authority-diff.",
    )
    p_install_overlay.set_defaults(func=_cmd_install_overlay)

    p_lint = sub.add_parser(
        "lint",
        help="Check a package manifest for authoring problems.",
    )
    p_lint.add_argument(
        "package",
        help="Package directory, package.yaml path, or registry package name.",
    )
    p_lint.set_defaults(func=_cmd_lint)

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
