"""O3-P1 — the authority-diff.

Before an overlay is installed onto a *running* organization, the operator must
see, in plain language, how it changes who-can-do-what. The authority-diff
compares the org as it is against the org as the overlay would make it, along
the governance-bearing axes — roles, their write scope, their class, their
escalation, the mandates — and classifies each change as **expanding**,
**narrowing**, or **neutral** with respect to authority.

Without this, approving an install is blind. This is package-manager-layer
code: it reads org files and renders plain language; it changes no kernel
state. It is the foundation of the governed overlay install (spec O3-P1).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cognitive_firm.userland import vocabulary

EXPANDS = "expands"
NARROWS = "narrows"
NEUTRAL = "neutral"
UNKNOWN = "unknown"  # a change the differ cannot interpret — treated as expanding


@dataclass(frozen=True)
class DiffLine:
    """One classified, plain-language change to the authority structure."""

    subject: str  # e.g. "role:billing-clerk"
    classification: str  # EXPANDS | NARROWS | NEUTRAL | UNKNOWN
    text: str

    def as_dict(self) -> dict[str, str]:
        return {
            "subject": self.subject,
            "classification": self.classification,
            "text": self.text,
        }


@dataclass(frozen=True)
class AuthorityDiff:
    """The classified authority delta of a would-be install."""

    lines: tuple[DiffLine, ...]

    @property
    def expands_authority(self) -> bool:
        """True if any change expands authority — or cannot be interpreted.

        An install for which this is true must take the full governance path:
        it may never be auto-approved.
        """
        return any(
            line.classification in (EXPANDS, UNKNOWN) for line in self.lines
        )

    @property
    def is_empty(self) -> bool:
        return not self.lines

    def as_dict(self) -> dict[str, Any]:
        return {
            "expands_authority": self.expands_authority,
            "lines": [line.as_dict() for line in self.lines],
        }

    def render(self) -> str:
        """A plain-language report grouped by classification — what an operator
        reads before approving the install."""
        if not self.lines:
            return (
                "This install makes no change to the organization's authority "
                "structure."
            )
        headings = {
            EXPANDS: "Expands authority:",
            UNKNOWN: (
                "Changes authority in ways the installer cannot fully "
                "interpret — review these files directly:"
            ),
            NARROWS: "Narrows authority:",
            NEUTRAL: "Other changes:",
        }
        out: list[str] = []
        for classification in (EXPANDS, UNKNOWN, NARROWS, NEUTRAL):
            group = [
                line for line in self.lines
                if line.classification == classification
            ]
            if not group:
                continue
            out.append(headings[classification])
            out.extend(f"  - {line.text}" for line in group)
        return "\n".join(out)


def _load_yaml_dir(directory: Path) -> dict[str, dict]:
    """Map file stem -> parsed mapping for every ``*.yaml`` in a directory."""
    out: dict[str, dict] = {}
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue
        if isinstance(data, dict):
            out[path.stem] = data
    return out


def _classify_paths(before: Any, after: Any) -> str:
    """Classify a change to a role's ``authorized_paths`` set."""
    b = set(before or [])
    a = set(after or [])
    if a == b:
        return NEUTRAL
    if "*" in a and "*" not in b:
        return EXPANDS
    if "*" in b and "*" not in a:
        return NARROWS
    if a > b:
        return EXPANDS
    if a < b:
        return NARROWS
    return UNKNOWN  # the sets diverge — cannot be called expand or narrow


def _mandate_files(org_root: Path) -> dict[str, str]:
    mandates = org_root / "mandates"
    if not mandates.is_dir():
        return {}
    return {p.name: p.read_text() for p in sorted(mandates.glob("*.md"))}


def compute_authority_diff(before_root: Path, after_root: Path) -> AuthorityDiff:
    """Compute the authority delta from ``before_root`` to ``after_root``.

    ``before_root`` is the live org; ``after_root`` is the org as the staged
    overlay would make it. Both are organization directories.
    """
    before_root = Path(before_root)
    after_root = Path(after_root)
    lines: list[DiffLine] = []

    before_roles = _load_yaml_dir(before_root / "roles")
    after_roles = _load_yaml_dir(after_root / "roles")

    for role_id in sorted(set(after_roles) - set(before_roles)):
        paths = after_roles[role_id].get("authorized_paths") or []
        lines.append(
            DiffLine(
                f"role:{role_id}",
                EXPANDS if paths else NEUTRAL,
                f"Adds role '{role_id}': "
                f"{vocabulary.render('authorized_paths', paths)}.",
            )
        )

    for role_id in sorted(set(before_roles) - set(after_roles)):
        lines.append(
            DiffLine(
                f"role:{role_id}",
                NARROWS,
                f"Removes role '{role_id}' and the authority it held.",
            )
        )

    for role_id in sorted(set(before_roles) & set(after_roles)):
        before = before_roles[role_id]
        after = after_roles[role_id]

        paths_class = _classify_paths(
            before.get("authorized_paths"), after.get("authorized_paths")
        )
        if paths_class != NEUTRAL:
            lines.append(
                DiffLine(
                    f"role:{role_id}",
                    paths_class,
                    f"Changes role '{role_id}': now "
                    f"{vocabulary.render('authorized_paths', after.get('authorized_paths') or [])}.",
                )
            )

        if before.get("role_class") != after.get("role_class"):
            to_authority = after.get("role_class") == "authority"
            lines.append(
                DiffLine(
                    f"role:{role_id}",
                    EXPANDS if to_authority else UNKNOWN,
                    f"Changes role '{role_id}' class from "
                    f"'{before.get('role_class')}' to "
                    f"'{after.get('role_class')}'.",
                )
            )

        if (before.get("escalates_to") or []) != (
            after.get("escalates_to") or []
        ):
            lines.append(
                DiffLine(
                    f"role:{role_id}",
                    UNKNOWN,
                    f"Changes the escalation path of role '{role_id}' — "
                    "review the governance graph.",
                )
            )

    before_mandates = _mandate_files(before_root)
    after_mandates = _mandate_files(after_root)
    for name in sorted(set(after_mandates) - set(before_mandates)):
        lines.append(
            DiffLine(f"mandate:{name}", NEUTRAL, f"Adds mandate '{name}'.")
        )
    for name in sorted(set(before_mandates) - set(after_mandates)):
        lines.append(
            DiffLine(
                f"mandate:{name}", NARROWS, f"Removes mandate '{name}'."
            )
        )
    for name in sorted(set(before_mandates) & set(after_mandates)):
        if before_mandates[name] != after_mandates[name]:
            lines.append(
                DiffLine(
                    f"mandate:{name}",
                    UNKNOWN,
                    f"Changes mandate '{name}' — review the scope it grants.",
                )
            )

    return AuthorityDiff(lines=tuple(lines))
