# src

This directory is the importable kernel implementation.

Put reusable primitives here when another program, service route, adapter,
tenant overlay, or demo must rely on the behavior. That includes authority
checks, state transitions, schemas, projections, service-route handlers,
runtime adapters, proof builders, and invariant enforcement.

Do not hide reusable kernel behavior in `scripts/`. Scripts may install
fixtures, call service routes, sequence demos, and render reports, but the
logic they depend on should live under `src/cognitive_firm/` once it becomes a
stable primitive.

Boundary rule:

- `src/cognitive_firm/`: canonical behavior and reusable APIs.
- `scripts/`: executable harnesses, demos, smoke checks, migrations, and
  operator entrypoints that compose canonical behavior.
- `docs/` and `org/*/templates/`: public protocol guidance and copyable
  examples, not tenant-specific strategy.
- `internal/`: ignored local strategy notes and working synthesis.

<!-- AUTO-INDEX:START (managed by scripts/gen_folder_index.py — edit prose OUTSIDE this block) -->

## Index

**Sub-folders**

- [`cognitive_firm/`](cognitive_firm/) - 15 file(s)

**Documents**

- [__init__.py](__init__.py)

<sub>1 sub-folder(s), 1 document(s). Auto-generated; re-run `scripts/gen_folder_index.py` after adding files.</sub>

<!-- AUTO-INDEX:END -->
