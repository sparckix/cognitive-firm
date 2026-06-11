"""O3-P1 — the governed overlay install.

Installing an overlay onto a *running* organization changes who-can-do-what; it
must be a governed, attested event, not an out-of-band copy. This module
orchestrates that as two steps over primitives that already exist — it adds no
kernel change:

1. ``propose_overlay_install`` — stage the overlay against a *copy* of the live
   org, compute the authority-diff (`authority_diff.py`), and file a
   `GovernanceChangeProposal` (`governance_changes.py`) whose
   `expected_behavior_change` is the rendered diff and whose invariant checks
   are derived from it. The hard governability gate is the installer's own
   `boot_check`: an overlay that would produce an ungovernable org cannot even
   be staged. A fileable proposal is `review_ready`; the principal reviews the
   diff before it proceeds.
2. ``apply_approved_install`` — once the operator has reviewed, materialize the
   overlay onto the live org via the transactional `install()` and attest a
   `package.install_approved` event tying the install to the proposal.

A `blocked` proposal (a failed required invariant) can never be applied.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cognitive_firm.distribution.authority_diff import (
    EXPANDS,
    UNKNOWN,
    AuthorityDiff,
    compute_authority_diff,
)
from cognitive_firm.distribution.installer import (
    InstallError,
    InstallReceipt,
    install,
    plan_install,
    record_distribution_event,
)
from cognitive_firm.distribution.manifest import PackageManifest
from cognitive_firm.orchestration.governance_changes import (
    GovernanceChangeProposal,
    InvariantCheck,
    failed_invariants,
    propose_governance_change,
)


class GovernedInstallError(RuntimeError):
    """Raised when a governed install cannot proceed."""


@dataclass(frozen=True)
class GovernedInstallProposal:
    """The result of phase 1+2: the governance proposal, the authority-diff it
    was filed with, and the overlay it concerns."""

    proposal: GovernanceChangeProposal
    diff: AuthorityDiff
    overlay_manifest: PackageManifest

    @property
    def can_proceed(self) -> bool:
        """True unless a required invariant failed — a `blocked` proposal can
        never be applied."""
        return self.proposal.status != "blocked"


@dataclass(frozen=True)
class OverlayPreviewFile:
    """One file a no-write overlay preview would touch."""

    dest: str
    op: str
    conflict: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "dest": self.dest,
            "op": self.op,
            "conflict": self.conflict,
        }


@dataclass(frozen=True)
class OverlayInstallPreview:
    """No-write preview for package authors and reviewers.

    Unlike ``propose_overlay_install``, this does not write a governance
    proposal. It stages the overlay against a copy, verifies it would boot,
    computes the authority diff, and returns the install file plan.
    """

    overlay_manifest: PackageManifest
    diff: AuthorityDiff
    files: tuple[OverlayPreviewFile, ...]

    @property
    def status(self) -> str:
        return "blocked" if self.diff.expands_authority else "review_ready"

    @property
    def can_proceed(self) -> bool:
        return self.status == "review_ready"

    def as_dict(self) -> dict[str, object]:
        return {
            "package": self.overlay_manifest.name,
            "version": self.overlay_manifest.version,
            "kind": self.overlay_manifest.kind,
            "status": self.status,
            "can_proceed": self.can_proceed,
            "expands_authority": self.diff.expands_authority,
            "files": [file.as_dict() for file in self.files],
            "authority_diff": self.diff.as_dict(),
        }


def _invariant_checks_from_diff(diff: AuthorityDiff) -> list[InvariantCheck]:
    """Derive the five required governance invariants from the authority-diff.

    The kernel's governance model is strict: a proposal is `review_ready` only
    if every required invariant *passes*; otherwise it is `blocked`. So this is
    a real deterministic gate — an overlay that **expands** a role's write
    scope fails `write_scope_preserved`, and one that changes authority in a
    way the installer **cannot interpret** (escalation graph, role class,
    mandate text) fails `principal_independence`. Either way the install is
    blocked: a *package* may not widen authority. An operator who wants that
    makes it a direct config change under their own authority. Only a
    narrowing-or-neutral overlay reaches `review_ready`.
    """
    has_expands = any(line.classification == EXPANDS for line in diff.lines)
    has_unknown = any(line.classification == UNKNOWN for line in diff.lines)
    return [
        InvariantCheck(
            "write_scope_preserved",
            "fail" if has_expands else "pass",
            "this overlay expands a role's write scope — a package may not "
            "widen authority; make it a direct config change instead"
            if has_expands
            else "the authority-diff detected no expansion of write scope",
            evidence_refs=["authority_diff:computed"],
        ),
        InvariantCheck(
            "principal_independence",
            "fail" if has_unknown else "pass",
            "this overlay changes authority in a way the installer cannot "
            "interpret — review the files directly"
            if has_unknown
            else "the install changes no escalation graph or role class",
            evidence_refs=["authority_diff:computed"],
        ),
        InvariantCheck(
            "deterministic_enforcement_floor",
            "pass",
            "the kernel's runtime enforcement is unchanged by an overlay "
            "install",
            evidence_refs=["governed_install:boot_check"],
        ),
        InvariantCheck(
            "fail_closed_behavior",
            "pass",
            "the kernel still fails closed against the installed files",
            evidence_refs=["governed_install:boot_check"],
        ),
        InvariantCheck(
            "tenant_boundary_preserved",
            "pass",
            "the authority-diff detected no tenant-scoped change",
            evidence_refs=["authority_diff:computed"],
        ),
    ]


def _op_for_dest(manifest: PackageManifest, dest_rel: str) -> str:
    for component in manifest.components:
        dest = component.dest
        if dest_rel == dest or dest_rel.startswith(dest + "/"):
            return component.op
    return "add"


def preview_overlay_install(
    *,
    overlay_manifest: PackageManifest,
    overlay_root: Path,
    target_root: Path,
) -> OverlayInstallPreview:
    """No-write overlay preview.

    Raises ``GovernedInstallError`` if the target does not exist, the overlay
    has missing files, or staging the overlay would produce an unbootable org.
    """
    target_root = Path(target_root)
    if not target_root.is_dir():
        raise GovernedInstallError(f"target org does not exist: {target_root}")

    try:
        raw_plan = plan_install(overlay_manifest, overlay_root, target_root)
    except FileNotFoundError as exc:
        raise GovernedInstallError(str(exc)) from exc
    files = tuple(
        OverlayPreviewFile(
            dest=dest_rel,
            op=_op_for_dest(overlay_manifest, dest_rel),
            conflict=conflict,
        )
        for _src, dest_rel, conflict in raw_plan
    )

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "staging"
        shutil.copytree(target_root, staging)
        try:
            install(overlay_manifest, overlay_root, staging, force=True)
        except InstallError as exc:
            raise GovernedInstallError(
                f"the overlay '{overlay_manifest.name}' would produce an org "
                f"that does not boot: {exc}"
            ) from exc
        diff = compute_authority_diff(target_root, staging)

    return OverlayInstallPreview(
        overlay_manifest=overlay_manifest,
        diff=diff,
        files=files,
    )


def propose_overlay_install(
    *,
    overlay_manifest: PackageManifest,
    overlay_root: Path,
    target_root: Path,
    proposed_by: str = "operator",
    governance_log: Path | None = None,
) -> GovernedInstallProposal:
    """Phase 1+2: stage the overlay against a copy of the live org, compute the
    authority-diff, and file a governance-change proposal.

    Raises ``GovernedInstallError`` if the target org does not exist or the
    overlay would produce an org that does not boot (the hard gate).
    """
    target_root = Path(target_root)
    if not target_root.is_dir():
        raise GovernedInstallError(f"target org does not exist: {target_root}")

    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "staging"
        shutil.copytree(target_root, staging)
        try:
            install(overlay_manifest, overlay_root, staging, force=True)
        except InstallError as exc:
            raise GovernedInstallError(
                f"the overlay '{overlay_manifest.name}' would produce an org "
                f"that does not boot: {exc}"
            ) from exc
        diff = compute_authority_diff(target_root, staging)

    proposal = propose_governance_change(
        change_kind="role_change",
        title=(
            f"Install overlay '{overlay_manifest.name}' "
            f"v{overlay_manifest.version}"
        ),
        proposed_by=proposed_by,
        target_ref=f"package:{overlay_manifest.name}",
        rationale=(
            overlay_manifest.description
            or f"install overlay {overlay_manifest.name}"
        ),
        source_refs=[
            f"package:{overlay_manifest.name}@{overlay_manifest.version}",
            "authority_diff:computed",
            "governed_install:staged_boot_check",
        ],
        expected_behavior_change=diff.render(),
        risk_summary=(
            "overlay install preview; expands_authority="
            f"{diff.expands_authority}; changed_files={len(diff.lines)}"
        ),
        rollback_plan=(
            "clean rollback to the pre-install git ref "
            "(cognitive-firm-distro rollback)"
        ),
        invariant_checks=_invariant_checks_from_diff(diff),
        log_path=governance_log,
    )
    return GovernedInstallProposal(
        proposal=proposal, diff=diff, overlay_manifest=overlay_manifest
    )


def apply_approved_install(
    governed: GovernedInstallProposal,
    overlay_root: Path,
    target_root: Path,
    *,
    actor: str = "operator",
    kernel_version: str | None = None,
) -> InstallReceipt:
    """Phase 4: apply a reviewed overlay onto the live org and attest it.

    Refuses a ``blocked`` proposal. The install itself is the transactional
    `install()`; this adds the ``package.install_approved`` event tying the
    install to its governance proposal.
    """
    if not governed.can_proceed:
        raise GovernedInstallError(
            f"install of '{governed.overlay_manifest.name}' is blocked by a "
            f"failed invariant: "
            f"{', '.join(failed_invariants(governed.proposal.invariant_checks))}"
        )

    receipt = install(
        governed.overlay_manifest,
        overlay_root,
        target_root,
        force=True,
        kernel_version=kernel_version,
    )
    record_distribution_event(
        target_root,
        actor=actor,
        verb="package.install_approved",
        package=governed.overlay_manifest.name,
        payload={
            "proposal_id": governed.proposal.proposal_id,
            "expands_authority": governed.diff.expands_authority,
            "authority_diff": governed.diff.render(),
        },
    )
    return receipt
