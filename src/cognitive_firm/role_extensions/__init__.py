"""Role extensions — per-role Python modules loaded by org/ agent runtimes.

Each role in org/roles/ has a corresponding extension module here that
implements the role's procedural duties as callable functions. The
extensions are loaded by a role runtime or app adapter, not by the kernel's
core mutation paths.

This separation preserves the app / role boundary:
  - app runtime = tenant or project-specific execution loop
  - role extensions = per-role logic such as triangulation, adversarial
    probes, or inversion forms
  - mandates (org/roles/<role>.md) = the role's config / procedural rules
  - rubrics (rubrics/<project>.json) = per-substrate data the role reads

Naming convention: one module per role, named after the role
(`research_director.py`, `principal.py`, `skeptic.py`, ...). Each module
exposes a small public API: load(), run(trigger, context) — so the
future daemon framework can wire them in uniformly.
"""
