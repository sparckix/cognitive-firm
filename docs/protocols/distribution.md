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
  on-disk layout.
- **Install receipt** — a durable JSON record under the target's
  `.cognitive-firm/` directory: the package, version, files, and the git
  **install boundary** (`pre_install_ref`, `commit_sha`, `git_tag`) that
  rollback undoes from.

## Layout

Each package is a directory with a `package.yaml` manifest and a `files/`
directory holding exactly the overlay it installs:

```text
distro/
  starter-firm/
    package.yaml
    files/
      roles/           analyst.yaml, lead.yaml, principal.yaml, reviewer.yaml
      mandates/        analyst_mandate.md, lead_mandate.md, reviewer_mandate.md
      preferences/     principal.yaml
      operating_units/ operating_units.json   (the day-one governance loop)
      projects/        first-project/project_charter.md
```

## Manifest format (`package.yaml`, schema_version 1)

| Field | Meaning |
|---|---|
| `name`, `version` | package identity |
| `kind` | `distro` or `overlay` |
| `description` | human summary (min 10 chars) |
| `kernel.min_version` / `max_version` | supported kernel range, enforced at install |
| `components` | list of `{source, dest, optional}` install units |
| `provides` | capability tags this package contributes |
| `post_install_message` | shown to the operator after install |

A `component` `source` is a path under `files/` (a directory or a file);
`dest` is where it lands in the target. Both are validated to stay inside
their roots — a `source` or `dest` that escapes is rejected. (Dependency
declarations — `requires` — return with the O3 package ecosystem.)

## Installer contract

- **Kernel-version gate.** Install refuses if the running kernel
  (`cognitive_firm.__version__`) is outside the manifest's declared
  `kernel.min/max_version` range.
- **Transactional + git-backed.** The installer ensures the target is its own
  git repo, applies the package, runs `boot_check`, and only then commits and
  tags the result `install/<package>/<version>`. A failed or unbootable
  install leaves the target exactly as it was — the install commit is the
  **rollback boundary** (the receipt records the pre-install ref).
- **Conflict handling.** Files that already exist are **skipped**, never
  silently overwritten, unless `--force` is passed. The receipt records each
  file as `created`, `overwritten`, or `skipped`.
- **Verification — `boot_check`.** A stable interface (`distribution/boot.py`):
  every installed `roles/*.yaml` parses and carries the role.v1 keys, mandate
  files resolve and are non-empty, and the **governance graph** is sound —
  exactly one `authority` role, every `escalates_to`/`delegates_to` reference
  resolves, and every role's escalation chain reaches an authority (no
  ungoverned decision path). An org that fails `boot_check` is never committed.
- **Events.** Each install/upgrade/rollback appends a typed kernel event
  (`package.installed`, `package.rolled_back`) to
  `.cognitive-firm/distribution-events.jsonl`.
- The installer never writes to the kernel. It only writes overlay files the
  adopter owns. `git` is a hard dependency of this layer.

## Rollback

`rollback` (`distribution/rollback.py`) undoes an install. Two modes, chosen
automatically:

- **clean** — nothing has been committed since the install boundary: a
  `git reset --hard` to the pre-install ref. Total and exact.
- **compensating** — the org has run since the install: the install commit is
  reverted as a new *forward* commit, so the append-only history stays
  replayable. If post-install edits to the installed files make the revert
  conflict, the rollback is reported blocked, not forced.

`uninstall` is a rollback; `upgrade` is a forced install of a newer version
whose receipt records the pre-upgrade ref, so a post-upgrade rollback returns
to the pre-upgrade state.

## CLI

```sh
cognitive-firm-distro list
cognitive-firm-distro show starter-firm
cognitive-firm-distro install starter-firm --into ./my-firm
cognitive-firm-distro verify  starter-firm --into ./my-firm
cognitive-firm-distro upgrade starter-firm --into ./my-firm
cognitive-firm-distro rollback starter-firm --into ./my-firm --reason "..."
cognitive-firm-distro uninstall starter-firm --into ./my-firm
```

`--registry <dir>` selects a registry. The bundled `distro/` ships in the
wheel, so `list` works from a `pip install`; `--registry` overrides it.

## Boundary rule

A distro is policy: roles, mandates, preferences, operating units, and project
charters an adopter then edits to match their firm. The kernel defines the
mechanisms a distro composes. Adding a distro or overlay must never require a
kernel change.
