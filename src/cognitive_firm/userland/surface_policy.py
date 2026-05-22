"""L3 — kernel-side surface write policy.

Closes O-Q4. Write-gating must be enforced by the kernel, not by a surface's
own backend (today Orbit gates its own writes in its Node server — a §1.3
violation: "every mutation is a kernel-attested event", yet the gate sits
outside the kernel).

A surface carries an ``ActorContext.surface`` tag (`orbit`, `cli`, `telegram`,
`kernel_service`). This module decides, per surface, whether a mutation is
allowed; the kernel service calls it before any mutation and returns the
``reason`` plainly on a deny. The policy is a pure function — config in, a
decision out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

PROJECTION_ONLY = "projection_only"  # the surface may read, never mutate
READ_WRITE = "read_write"            # the surface may mutate
SURFACE_WRITE_MODES = (PROJECTION_ONLY, READ_WRITE)

# A surface with no explicit mode may write: the policy denies only what is
# explicitly restricted, so adding a surface never silently locks it out.
DEFAULT_MODE = READ_WRITE


@dataclass(frozen=True)
class SurfaceWriteDecision:
    """The outcome of a surface-write check, with a plain-language reason."""

    allowed: bool
    surface: str
    mode: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "surface": self.surface,
            "mode": self.mode,
            "reason": self.reason,
        }


def surface_write_allowed(
    *,
    surface: str,
    is_mutation: bool,
    modes: Mapping[str, str] | None = None,
) -> SurfaceWriteDecision:
    """Decide whether ``surface`` may perform this request.

    Reads are always allowed. A mutation is allowed unless ``surface`` is
    explicitly configured ``projection_only``.
    """
    mode = (modes or {}).get(surface, DEFAULT_MODE)
    if mode not in SURFACE_WRITE_MODES:
        mode = DEFAULT_MODE
    if not is_mutation:
        return SurfaceWriteDecision(
            True, surface, mode, "read access is always allowed"
        )
    if mode == PROJECTION_ONLY:
        return SurfaceWriteDecision(
            False,
            surface,
            mode,
            f"the '{surface}' surface is projection-only; changes to the "
            f"organization cannot be made from it",
        )
    return SurfaceWriteDecision(
        True, surface, mode, f"the '{surface}' surface permits changes"
    )
