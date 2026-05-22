"""Uniform primitive-extension-schema registry (O3-P6).

The kernel is *designed open*. A :class:`~cognitive_firm.orchestration.work_items.WorkItem`
carries a free ``kind`` string and an uninterpreted ``payload`` dict; an
:class:`~cognitive_firm.orchestration.operating_units.OperatingUnit` carries a
free ``unit_kind`` and ``metadata`` dict. A tenant may therefore declare a
*custom type* — a new ``kind`` — purely as config, with no kernel change. That
is the right design (`schemas/role.v1.schema.json` does the same with
``additionalProperties: true``), but it leaves one gap the OS-path spec §5.2
names: a custom type's payload is **extensible but not validated**. There is no
place for a package to *register* a per-``kind`` payload schema, so a typo or a
malformed payload flows straight through.

This module is the one-time, generic mechanism that closes that gap for *every*
primitive at once — the §5.2-sanctioned kernel revision. It is written once;
after it exists, an org or a package adds a custom *validated* type purely by
dropping a JSON Schema file in a conventional location. No further kernel
change is ever needed per type — that is the §1.2 invariant ("adding a type
must never require a kernel change").

The registry is a directory, not code::

    <schemas_root>/extension_schemas/<primitive>/<type_key>.schema.json

e.g. ``org/extension_schemas/work_item/refund_request.schema.json``. A package
ships such a file as ordinary config; installing it is an ordinary governed
install.

The single contract every call site uses:

    validate_payload(primitive, type_key, payload) -> list[str]

An empty list means *valid*. **Open by default**: if no schema is registered
for ``(primitive, type_key)`` the result is ``[]`` — no schema means no
constraint, so every existing custom type keeps working untouched. A schema
only ever *adds* a constraint; it never removes the open-typed baseline.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from cognitive_firm.common.paths import ORG_ROOT_DIR

# The conventional directory a package/org ships extension schemas under,
# relative to the schemas root (the org root by default).
EXTENSION_SCHEMAS_DIRNAME = "extension_schemas"

# Primitive identifiers are a small, documented, kernel-side vocabulary. The
# *types* within a primitive are open; the primitive label is not.
KNOWN_PRIMITIVES = ("work_item", "operating_unit", "role")

# A type key mirrors a WorkItem.kind / OperatingUnit.unit_kind: lowercase
# kebab/snake, no path separators. This is also the on-disk-safety guard.
_TYPE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def _schemas_root(schemas_root: Path | str | None) -> Path:
    """Resolve the directory that *contains* the ``extension_schemas/`` tree."""
    return Path(schemas_root) if schemas_root is not None else ORG_ROOT_DIR


def extension_schema_path(
    primitive: str,
    type_key: str,
    *,
    schemas_root: Path | str | None = None,
) -> Path:
    """Return the conventional on-disk path for one extension schema.

    Does not check existence; :func:`load_extension_schema` does that.
    """
    if not _TYPE_KEY_RE.match(type_key or ""):
        raise ValueError(
            f"type key {type_key!r} is not a valid extension-schema type key "
            "(lowercase a-z, 0-9, '_', '-', '.'; no path separators)"
        )
    if not re.fullmatch(r"[a-z0-9][a-z0-9_]*", primitive or ""):
        raise ValueError(f"primitive {primitive!r} is not a valid primitive identifier")
    return (
        _schemas_root(schemas_root)
        / EXTENSION_SCHEMAS_DIRNAME
        / primitive
        / f"{type_key}.schema.json"
    )


@lru_cache(maxsize=256)
def _load_schema_cached(path_str: str, mtime: float) -> dict[str, Any]:
    """Read and parse a schema file. Keyed on path + mtime so an edit busts it."""
    with open(path_str, "r", encoding="utf-8") as handle:
        schema = json.load(handle)
    if not isinstance(schema, dict):
        raise ValueError(f"extension schema {path_str} must be a JSON object")
    return schema


def load_extension_schema(
    primitive: str,
    type_key: str,
    *,
    schemas_root: Path | str | None = None,
) -> dict[str, Any] | None:
    """Return the registered JSON Schema for ``(primitive, type_key)`` or ``None``.

    ``None`` means no schema is registered — the open-by-default state. The
    parsed schema is cached, keyed on the file's modification time, so editing
    a schema file is picked up without a process restart.
    """
    path = extension_schema_path(primitive, type_key, schemas_root=schemas_root)
    if not path.is_file():
        return None
    return _load_schema_cached(str(path), path.stat().st_mtime)


def list_extension_schemas(
    primitive: str | None = None,
    *,
    schemas_root: Path | str | None = None,
) -> dict[str, list[str]]:
    """Discover every registered extension schema.

    Returns ``{primitive: [type_key, ...]}`` for every schema file found under
    ``<schemas_root>/extension_schemas/``. With ``primitive`` set, only that
    primitive's directory is scanned.
    """
    base = _schemas_root(schemas_root) / EXTENSION_SCHEMAS_DIRNAME
    out: dict[str, list[str]] = {}
    if not base.is_dir():
        return out
    primitive_dirs = (
        [base / primitive] if primitive is not None else sorted(base.iterdir())
    )
    for prim_dir in primitive_dirs:
        if not prim_dir.is_dir():
            continue
        keys = sorted(
            f.name[: -len(".schema.json")]
            for f in prim_dir.iterdir()
            if f.is_file() and f.name.endswith(".schema.json")
        )
        if keys:
            out[prim_dir.name] = keys
    return out


def register_extension_schema(
    primitive: str,
    type_key: str,
    schema: dict[str, Any],
    *,
    schemas_root: Path | str | None = None,
    overwrite: bool = False,
) -> Path:
    """Write a schema file into the registry (used by package install / tests).

    This is the *mechanical* write. In a real deployment a package ships the
    file and the governed install puts it in place; this function is the
    primitive that install — and tests — call. Refuses to clobber an existing
    schema unless ``overwrite`` is set, so an install cannot silently replace a
    type contract.
    """
    if not isinstance(schema, dict):
        raise ValueError("schema must be a JSON object (dict)")
    path = extension_schema_path(primitive, type_key, schemas_root=schemas_root)
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"an extension schema is already registered at {path}; "
            "pass overwrite=True to replace it"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # An edit/replace must bust the mtime-keyed cache deterministically.
    _load_schema_cached.cache_clear()
    return path


def validate_payload(
    primitive: str,
    type_key: str,
    payload: dict[str, Any] | None,
    *,
    schemas_root: Path | str | None = None,
) -> list[str]:
    """Validate a primitive instance's payload against its registered schema.

    The single, uniform hook every primitive's enqueue/define path calls.

    - If **no** schema is registered for ``(primitive, type_key)``: returns
      ``[]``. Open by default — no schema means no constraint.
    - If a schema **is** registered: returns the list of human-readable
      validation errors (empty list = valid).
    - A schema file that is itself unparseable or not a valid JSON Schema is a
      *registry* error and is surfaced as an error string, not silently
      ignored — a broken schema must fail loudly rather than wave payloads
      through.

    The ``jsonschema`` library (a declared dependency) does the validation.
    """
    try:
        schema = load_extension_schema(primitive, type_key, schemas_root=schemas_root)
    except (json.JSONDecodeError, OSError) as exc:
        return [
            f"extension schema for {primitive}/{type_key} could not be read: {exc}"
        ]
    except ValueError as exc:
        # json.JSONDecodeError subclasses ValueError, so the decode branch
        # above must come first; this catches a bad type_key / primitive.
        return [f"extension-schema lookup failed: {exc}"]
    if schema is None:
        return []  # open by default — no registered schema, no constraint.

    try:
        import jsonschema  # declared in requirements.txt
        from jsonschema import Draft202012Validator
    except ImportError:  # pragma: no cover - jsonschema is a hard dependency.
        return [
            "jsonschema is not installed; cannot validate against the "
            f"extension schema registered for {primitive}/{type_key}"
        ]

    try:
        Draft202012Validator.check_schema(schema)
    except jsonschema.exceptions.SchemaError as exc:
        return [
            f"extension schema for {primitive}/{type_key} is not a valid "
            f"JSON Schema: {exc.message}"
        ]

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload or {}), key=lambda e: list(e.path))
    messages: list[str] = []
    for err in errors:
        location = "/".join(str(p) for p in err.absolute_path)
        prefix = f"payload.{location}: " if location else ""
        messages.append(f"{prefix}{err.message}")
    return messages
