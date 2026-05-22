# Extension Schemas — Uniform Primitive-Extension Validation

**Status:** first-party interface shipped (O3-P6).
**Module:** `cognitive_firm.orchestration.extension_schemas`
**Tests:** `tests/test_extension_schemas.py`
**Spec:** GP-230 OS-path spec §5.2; O3 package-ecosystem design O3-P6.

The kernel is *designed open*. A
[`WorkItem`](work-items.md) carries a free `kind` string and an uninterpreted
`payload` dict; an `OperatingUnit` carries a free `unit_kind` and a `metadata`
dict; a role YAML is `additionalProperties: true`. A tenant or a package may
therefore declare a **custom type** — a new `kind` — purely as config, with no
kernel change. That is the right design.

But until O3-P6, custom types were **extensible but not validated**. A custom
`WorkItem.kind` got a free `payload` dict the kernel could not check, and there
was *no place for a package to register a per-`kind` payload schema*. Only
roles had an extension-schema pattern (`schemas/role.v1.schema.json` — "domain
extensions layer on via per-adapter extension schemas, NOT by modifying this
file"). This protocol generalizes that pattern to **every primitive**.

## The mechanism

Three parts, exactly mirroring the role-schema pattern made uniform.

### 1. The registry is a directory, not code

A package or an org ships JSON Schema files under a conventional path:

```text
<schemas_root>/extension_schemas/<primitive>/<type_key>.schema.json
```

For example `org/extension_schemas/work_item/refund_request.schema.json` is the
payload schema for `WorkItem`s whose `kind == "refund_request"`. The directory
is *config* — the O3 delivery vehicle. Installing a package that ships an
extension schema is an ordinary governed install: a schema *constrains*
behavior, so it correctly routes through governance.

`schemas_root` defaults to the org root (`ORG_ROOT_DIR`). The known primitive
identifiers are `work_item`, `operating_unit`, `role`; the *types* within each
are open.

### 2. One generic module — the one-time kernel revision

`cognitive_firm.orchestration.extension_schemas` is the generic mechanism. Per
spec §1.2, "adding a type must never require a kernel change" — and it does
not: this module is written **once**, and after it exists a package adds a
custom *validated* type purely by dropping a schema file. The module exposes:

| Function | Purpose |
|---|---|
| `validate_payload(primitive, type_key, payload, *, schemas_root=None)` | the uniform hook — returns a list of errors (`[]` = valid) |
| `load_extension_schema(primitive, type_key, *, schemas_root=None)` | the parsed schema, or `None` if none registered |
| `register_extension_schema(primitive, type_key, schema, *, ...)` | write a schema file (used by package install / tests) |
| `list_extension_schemas(primitive=None, *, schemas_root=None)` | discover the registry — `{primitive: [type_key, ...]}` |
| `extension_schema_path(primitive, type_key, *, schemas_root=None)` | the conventional on-disk path |

### 3. The validation hook — open by default

`validate_payload` is the single contract every primitive's enqueue/define path
calls:

- If **no** schema is registered for `(primitive, type_key)`: returns `[]`.
  **Open by default** — no schema means no constraint, so every existing
  custom type keeps working untouched. A schema only ever *adds* a constraint.
- If a schema **is** registered: the payload is validated with the
  `jsonschema` library (Draft 2020-12) and the list of human-readable errors
  is returned.
- If a schema file is itself unparseable or not a valid JSON Schema: that is a
  *registry* error and is surfaced as an error string — a broken schema fails
  loudly rather than waving payloads through.

## Wired call site

Today the hook is wired into one primitive: **`WorkItem` enqueue**. In
`enqueue_work_item`, immediately after the existing
`unit.allows_work_kind(kind)` check:

```python
schema_errors = validate_payload("work_item", kind, payload or {},
                                 schemas_root=extension_schemas_root)
if schema_errors:
    raise ValueError(f"work item payload fails the extension schema "
                     f"registered for kind {kind!r}: ...")
```

A `kind` with **no** registered schema is still enqueued with any payload —
the kernel's open-typed baseline is preserved exactly. A rejected enqueue
persists nothing.

The *same one-line idiom* — one registry, one `validate_payload` signature,
one call site — is how a future primitive (`OperatingUnit.metadata`, the role
loader) opts in. This is the "uniform" in O3-P6: `role` is no longer the only
primitive with an extension-schema pattern.

## Schema versioning

A custom type's schema versions like any other. A breaking change to a custom
type's schema is a package upgrade (governed). A breaking change to the
*extension-schema protocol itself* — this module's contract — is a kernel v2,
the rare case spec §5.2 reserves a kernel revision for.

## Residual risks (from the O3-P6 design)

- **`additionalProperties` policy.** A registered schema with
  `additionalProperties: true` catches little; `false` is real type-safety but
  breaks on an unforeseen field. The mechanism does not mandate either — the
  schema author chooses. Type-safety depends on authors writing strict schemas.
- **The call-site set grows over time.** Every future primitive with a free
  `payload`/`metadata` dict must remember to add the `validate_payload` hook,
  or it silently re-opens the gap for itself. This belongs on the
  primitive-authoring checklist and the adapter-conformance suite.
- **Performance.** `validate_payload` reads (and mtime-caches) a schema file
  per enqueue. Negligible at T1 (JSONL, single host); a T2 backend should
  cache compiled validators.
- **The registry is authority-bearing config.** A permissive schema is no
  worse than today's no-schema state — a schema only ever constrains — and the
  schema install is governed, so it is surfaced, not silent.
