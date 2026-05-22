"""L4 — the userland vocabulary spine.

What makes the userland *one environment* rather than a pile of surfaces is
that every surface speaks the same words. L4 is the single source of those
words: one entry per kernel concept, with a plain-language label, a one-line
definition, and the governance interpretation.

`render` is the spec §1.4 worked rule in code — surface the *governance
interpretation* of a kernel datum, hide its encoding. Every userland headline
should be produced through this module, never with ad-hoc strings, so a
surface physically cannot fork the vocabulary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_VOCABULARY_FILE = Path(__file__).with_name("vocabulary.json")


class UnknownTerm(KeyError):
    """Raised when a vocabulary key has no entry — a surface must use a defined
    term, never an ad-hoc string."""


@dataclass(frozen=True)
class Term:
    """One human-facing term: the kernel key, its plain-language label, a
    definition, and the §1.4 governance interpretation."""

    key: str
    label: str
    definition: str
    governance_note: str

    def as_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "definition": self.definition,
            "governance_note": self.governance_note,
        }


@lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    return json.loads(_VOCABULARY_FILE.read_text())


@lru_cache(maxsize=1)
def _terms() -> dict[str, Term]:
    return {
        key: Term(
            key=key,
            label=entry["label"],
            definition=entry["definition"],
            governance_note=entry["governance_note"],
        )
        for key, entry in _raw()["terms"].items()
    }


def schema_version() -> int:
    """The glossary's schema version — every surface should load the same one."""
    return int(_raw()["schema_version"])


def term(key: str) -> Term:
    """The defined term for a kernel key. Raises ``UnknownTerm`` if undefined."""
    terms = _terms()
    if key not in terms:
        raise UnknownTerm(key)
    return terms[key]


def all_terms() -> list[Term]:
    """Every defined term, key-sorted — the glossary a surface ships once."""
    return sorted(_terms().values(), key=lambda t: t.key)


def render(key: str, value: Any) -> str:
    """Plain-language rendering of a kernel datum (spec §1.4).

    Surfaces the governance *interpretation*, not the raw encoding. The worked
    case from the spec: ``render("authorized_paths", ["*"])`` ->
    "this role can write anywhere in the organization".
    """
    defined = term(key)  # raises UnknownTerm — no rendering of unknown keys
    if key == "authorized_paths":
        paths = list(value) if isinstance(value, (list, tuple)) else [value]
        if "*" in paths:
            return "this role can write anywhere in the organization"
        if not paths:
            return "this role is read-only — it can write nowhere"
        return "this role can write to: " + ", ".join(str(p) for p in paths)
    return f"{defined.label}: {value}"
