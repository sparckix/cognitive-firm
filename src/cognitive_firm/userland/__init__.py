"""Userland — the operator- and member-human-facing layer over the kernel.

The userland is not a surface; it is the participant-relative *environment of
human participation* in a governed firm. It is an assembly layer — pure
functions over kernel logs and the kernel service — never a kernel primitive
and never a holder of durable state.

L1, the attention router, lives here. Design notes are intentionally outside
the package runtime; this module exposes only the reusable implementation
surface.
"""
