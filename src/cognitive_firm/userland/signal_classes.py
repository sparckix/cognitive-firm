"""Signal classes and pace layers for the userland attention layer (L1).

A signal's *class* says which participant it concerns — and therefore who the
attention router sends it to. Its *pace layer* (after the H2A pace-layered
model) says how fast it must reach that human. Its *urgency* is how the
operator/member-human queue orders it.
"""

from __future__ import annotations

# Signal class — the routing dimension (who it concerns).
GOVERNANCE_INTERRUPT = "governance_interrupt"  # needs the operator's authority
WORK_INTERRUPT = "work_interrupt"              # needs a member-human to do work
INFORMATIONAL = "informational"                # no action; surfaced, never paged
SIGNAL_CLASSES = (GOVERNANCE_INTERRUPT, WORK_INTERRUPT, INFORMATIONAL)

# Pace layer — how fast it must reach the human (H2A pace layering).
FAST = "fast"
WORKING = "working"
SLOW = "slow"
PACE_LAYERS = (FAST, WORKING, SLOW)

# Urgency — how the queue orders it (spec §4.5 needs-me presentation model).
BLOCKING_NOW = "blocking_now"
APPROVAL_PENDING = "approval_pending"
INFO = "informational"
URGENCIES = (BLOCKING_NOW, APPROVAL_PENDING, INFO)
