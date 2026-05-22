# Distribution Protocol

The kernel is generic and an adopter never edits it. The distribution layer is
the **userland** of the OS analogy: it composes a runnable governed
organization an operator installs in one action, while the installed result
stays inspectable, forkable, and replayable.

## Concepts

- **Package** — a versioned, installable bundle of overlay files. Two kinds:
  - `distro` — a curated, day-one-runnable starter organization.
  - `overlay` — an add-on overlay (extra roles, mandates, protocols) installed
    on top of an existing organization.
- **Registry** — a directory of package directories. `discover_packages`
  indexes one so packages can be listed and installed without knowing their
  on-disk layout. This is the seed of the package/overlay ecosystem.
- **Install receipt** — a durable JSON record written under the target's
  `.cognitive-firm/` directory: what package, what version, which files.

## Layout

Each package is a directory with a `package.yaml` manifest and a `files/`
directory holding exactly the overlay it installs:

```text
distro/
  starter-firm/
    package.yaml
    files/
      roles/        analyst.yaml, lead.yaml, principal.yaml, reviewer.yaml
      mandates/     analyst_mandate.md, lead_mandate.md, reviewer_mandate.md
      preferences/  principal.yaml
```

## Manifest format (`package.yaml`, schema_version 1)

| Field | Meaning |
|---|---|
| `name`, `version` | package identity |
| `kind` | `distro` or `overlay` |
| `description` | human summary (min 10 chars) |
| `kernel.min_version` / `max_version` | supported kernel range |
| `components` | list of `{source, dest, optional}` install units |
| `requires` | other package names this package depends on |
| `provides` | capability tags this package contributes |
| `post_install_message` | shown to the operator after install |

A `component` `source` is a path under `files/` (a directory or a file);
`dest` is where it lands in the target. Both are validated to stay inside
their roots — a `source` or `dest` that escapes is rejected.

## Installer contract

- Files that already exist in the target are **skipped**, never silently
  overwritten, unless `--force` is passed. The receipt records each file as
  `created`, `overwritten`, or `skipped`.
- After install, `verify_install` runs a **boot-proxy check**: every
  non-skipped file landed, each installed `roles/*.yaml` parses and carries the
  role.v1 required keys, and each role's `mandate_path` resolves inside the
  target. This is structural, not a full kernel boot.
- The installer never writes to the kernel or to kernel state logs. It only
  writes overlay files the adopter owns.

## CLI

```sh
cognitive-firm-distro list
cognitive-firm-distro show starter-firm
cognitive-firm-distro install starter-firm --into ./my-firm
cognitive-firm-distro verify starter-firm --into ./my-firm
```

`--registry <dir>` selects a registry other than the repo's `distro/`. From an
installed wheel, pass `--registry` explicitly: the `distro/` tree is
checkout-level, like `scripts/`.

## Boundary rule

A distro is policy: roles, mandates, and preferences an adopter then edits to
match their firm. The kernel defines the mechanisms a distro composes. Adding a
distro or overlay must never require a kernel change.
