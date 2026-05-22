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
    """Classify a change to a role's ``authorized_paths`` set.

    Polarity: a wider set is an expansion of write authority. A set that both
    adds and removes paths cannot be called a pure expand or narrow, so it is
    UNKNOWN — but see ``_path_set_delta`` and the rendering in
    ``compute_authority_diff``: the added paths are still surfaced honestly as
    an expansion component (F-7), and UNKNOWN is treated as expanding by the
    governed-install gate (fail-closed).
    """
    classification, _, _ = _path_set_delta(before, after, widening_adds=True)
    return classification


def _path_set_delta(
    before: Any, after: Any, *, widening_adds: bool
) -> tuple[str, set[str], set[str]]:
    """Classify a set change and return ``(classification, added, removed)``.

    ``widening_adds`` encodes polarity. For ``authorized_paths`` and
    ``delegates_to`` adding entries widens authority, so ``widening_adds`` is
    True. For ``forbidden_paths`` the polarity is inverted: *removing* an entry
    widens authority, so ``widening_adds`` is False.
    """
    b = set(before or [])
    a = set(after or [])
    added = a - b
    removed = b - a
    if not added and not removed:
        return NEUTRAL, added, removed

    # "*" (write-anywhere) is a special widest element for path sets.
    if "*" in a and "*" not in b:
        return (EXPANDS if widening_adds else NARROWS), added, removed
    if "*" in b and "*" not in a:
        return (NARROWS if widening_adds else EXPANDS), added, removed

    widen, shrink = (
        (EXPANDS, NARROWS) if widening_adds else (NARROWS, EXPANDS)
    )
    if added and not removed:
        return widen, added, removed
    if removed and not added:
        return shrink, added, removed
    # the sets diverge — both add and remove. Cannot be called a pure
    # expand or narrow; UNKNOWN, which the gate treats as expanding.
    return UNKNOWN, added, removed


def _join(items: set[str]) -> str:
    """Render a set of path/role tokens for an operator-readable diff line."""
    return ", ".join(sorted(str(i) for i in items)) or "(none)"


# Budget keys that bound spend authority. A higher value is more authority for
# every one of these caps.
_BUDGET_CAP_KEYS = (
    "daily_cap_usd",
    "session_cap_usd",
    "single_action_cap_usd",
    "absolute_ceiling_usd",
)


def _classify_budget(
    role_id: str, before: Any, after: Any
) -> tuple[str, str]:
    """Classify a change to a role's spend ``budget``.

    Raising any cap expands spend authority; lowering it narrows. A change that
    raises some caps and lowers others is UNKNOWN (the gate treats it as
    expanding — fail-closed).
    """
    b = before if isinstance(before, dict) else {}
    a = after if isinstance(after, dict) else {}
    raised: list[str] = []
    lowered: list[str] = []
    for key in _BUDGET_CAP_KEYS:
        bv, av = b.get(key), a.get(key)
        if not isinstance(bv, (int, float)) or not isinstance(av, (int, float)):
            continue
        if av > bv:
            raised.append(f"{key} {bv} -> {av}")
        elif av < bv:
            lowered.append(f"{key} {bv} -> {av}")
    if not raised and not lowered:
        return NEUTRAL, ""
    if raised and not lowered:
        return EXPANDS, (
            f"Raises the spend budget of role '{role_id}': "
            f"{'; '.join(raised)} (an expansion of spend authority)."
        )
    if lowered and not raised:
        return NARROWS, (
            f"Lowers the spend budget of role '{role_id}': "
            f"{'; '.join(lowered)}."
        )
    return UNKNOWN, (
        f"Changes the spend budget of role '{role_id}': raises "
        f"{'; '.join(raised)} (an expansion) while lowering "
        f"{'; '.join(lowered)}."
    )


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

        paths_class, paths_added, paths_removed = _path_set_delta(
            before.get("authorized_paths"),
            after.get("authorized_paths"),
            widening_adds=True,
        )
        if paths_class != NEUTRAL:
            text = (
                f"Changes role '{role_id}': now "
                f"{vocabulary.render('authorized_paths', after.get('authorized_paths') or [])}."
            )
            if paths_class == UNKNOWN:
                # The set both adds and removes: not a pure expand/narrow, but
                # the added paths ARE an expansion component — name them
                # honestly rather than calling the change merely uninterpretable.
                text = (
                    f"Changes role '{role_id}' write scope: gains write access "
                    f"to {_join(paths_added)} (an expansion) while losing "
                    f"{_join(paths_removed)}. Now "
                    f"{vocabulary.render('authorized_paths', after.get('authorized_paths') or [])}."
                )
            lines.append(DiffLine(f"role:{role_id}", paths_class, text))

        forbidden_class, forbidden_added, forbidden_removed = _path_set_delta(
            before.get("forbidden_paths"),
            after.get("forbidden_paths"),
            widening_adds=False,
        )
        if forbidden_class == EXPANDS:
            text = (
                f"Removes forbidden-path guardrail(s) from role '{role_id}': "
                f"{_join(forbidden_removed)} — it may now write where it "
                "previously could not (an expansion)."
            )
            if forbidden_added:
                text = (
                    f"Changes the forbidden-path guardrails of role "
                    f"'{role_id}': drops {_join(forbidden_removed)} (an "
                    f"expansion) while adding {_join(forbidden_added)}."
                )
            lines.append(DiffLine(f"role:{role_id}", EXPANDS, text))
        elif forbidden_class == NARROWS:
            lines.append(
                DiffLine(
                    f"role:{role_id}",
                    NARROWS,
                    f"Adds forbidden-path guardrail(s) to role '{role_id}': "
                    f"{_join(forbidden_added)}.",
                )
            )
        elif forbidden_class == UNKNOWN:
            lines.append(
                DiffLine(
                    f"role:{role_id}",
                    UNKNOWN,
                    f"Changes the forbidden-path guardrails of role "
                    f"'{role_id}': drops {_join(forbidden_removed)} (an "
                    f"expansion) while adding {_join(forbidden_added)}.",
                )
            )

        deleg_class, deleg_added, deleg_removed = _path_set_delta(
            before.get("delegates_to"),
            after.get("delegates_to"),
            widening_adds=True,
        )
        if deleg_class == EXPANDS:
            lines.append(
                DiffLine(
                    f"role:{role_id}",
                    EXPANDS,
                    f"Adds delegation edge(s) to role '{role_id}': it may now "
                    f"delegate to {_join(deleg_added)}.",
                )
            )
        elif deleg_class == NARROWS:
            lines.append(
                DiffLine(
                    f"role:{role_id}",
                    NARROWS,
                    f"Removes delegation edge(s) from role '{role_id}': "
                    f"{_join(deleg_removed)}.",
                )
            )
        elif deleg_class == UNKNOWN:
            lines.append(
                DiffLine(
                    f"role:{role_id}",
                    UNKNOWN,
                    f"Changes the delegation edges of role '{role_id}': adds "
                    f"{_join(deleg_added)} (an expansion) while removing "
                    f"{_join(deleg_removed)}.",
                )
            )

        budget_class, budget_text = _classify_budget(
            role_id, before.get("budget"), after.get("budget")
        )
        if budget_class != NEUTRAL:
            lines.append(DiffLine(f"role:{role_id}", budget_class, budget_text))

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
