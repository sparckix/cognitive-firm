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

A copyable starting point for a new package lives at `docs/templates/package/`.

## Manifest format (`package.yaml`, schema_version 1)

| Field | Meaning |
|---|---|
| `name`, `version` | package identity |
| `kind` | `distro` or `overlay` |
| `description` | human summary (min 10 chars) |
| `kernel.min_version` / `max_version` | supported kernel range, enforced at install |
| `components` | list of `{source, dest, optional, op}` install units |
| `provides` | capability tags this package contributes |
| `extends` | optional base `distro` this package builds on (see *Inheritance*) |
| `post_install_message` | shown to the operator after install |

A `component` `source` is a path under `files/` (a directory or a file);
`dest` is where it lands in the target. Both are validated to stay inside
their roots — a `source` or `dest` that escapes is rejected.

### Composition `op`

Each component carries an `op` declaring how it composes onto the target:

| `op` | Meaning |
|---|---|
| `add` | install a new file; a pre-existing `dest` is a conflict (the default, historical behavior). |
| `replace` | own the file outright; a pre-existing `dest` is expected and overwritten. |
| `patch` | the component `source` is an [RFC 7386](https://www.rfc-editor.org/rfc/rfc7386) JSON Merge Patch applied to an existing JSON/YAML target. A `null` value deletes a key; a non-object patch replaces the document. A `patch` may only target `.json`, `.yaml`, or `.yml`. |

`op` is what makes an overlay a real composition rather than a file copy: an
overlay can extend a distro's `operating_units.json` with a `patch` instead of
having to ship and `replace` the whole file.

## Installer contract

- **Kernel-version gate.** Install refuses if the running kernel
  (`cognitive_firm.__version__`) is outside the manifest's declared
  `kernel.min/max_version` range.
- **Transactional + git-backed.** The installer ensures the target is its own
  git repo, applies the package, runs `boot_check`, and only then commits and
  tags the result `install/<package>/<version>`. A failed or unbootable
  install leaves the target exactly as it was — the install commit is the
  **rollback boundary** (the receipt records the pre-install ref).
- **Conflict handling.** For an `add` component, files that already exist are
  **skipped**, never silently overwritten, unless `--force` is passed. A
  `replace` component overwrites; a `patch` component merges. The receipt
  records each file as `created`, `overwritten`, or `skipped`.
- **Verification — `boot_check`.** A stable interface (`distribution/boot.py`):
  every installed `roles/*.yaml` parses and carries the role.v1 keys, mandate
  files resolve and are non-empty, and the **governance graph** is sound —
  exactly one `authority` role, every `escalates_to`/`delegates_to` reference
  resolves, and every role's escalation chain reaches an authority (no
  ungoverned decision path). An org that fails `boot_check` is never committed.
- **Events.** Each install/upgrade/rollback appends a typed kernel event
  (`package.installed`, `package.rolled_back`, and — for a governed overlay
  install — `package.install_approved`) to
  `.cognitive-firm/distribution-events.jsonl`.
- The installer never writes to the kernel. It only writes overlay files the
  adopter owns. `git` is a hard dependency of this layer.

## Governed overlay install

Installing an overlay onto a directory is a file operation; installing one
onto a *running* organization changes who-can-do-what, so it must be a
governed, attested event — not an out-of-band copy.
`distribution/governed_install.py` orchestrates that over primitives that
already exist, with no kernel change:

1. **`propose_overlay_install`** stages the overlay against a *copy* of the
   live org, computes an **authority-diff** (`distribution/authority_diff.py`)
   over the before/after role files, and files a `GovernanceChangeProposal`
   (`orchestration/governance_changes.py`) whose `expected_behavior_change` is
   the rendered authority-diff. The installer's own `boot_check` is the hard
   gate: an overlay that would produce an ungovernable org cannot even be
   staged.
2. The proposal's required invariants are derived from the diff. An overlay
   that **expands** a role's write scope fails `write_scope_preserved`; one
   that changes authority in a way the installer **cannot interpret**
   (escalation graph, role class, mandate text) fails
   `principal_independence`. Either failure makes the proposal `blocked` —
   **a package may not widen authority.** An operator who wants that makes it a
   direct config change under their own authority. Only a narrowing-or-neutral
   overlay reaches `review_ready`.
3. **`apply_approved_install`** refuses a `blocked` proposal. For an approved
   one it materializes the overlay via the transactional `install()` and
   attests a `package.install_approved` event tying the install to its
   proposal id.

## Remote packages

`discover_packages` only indexes a *local* directory. A real ecosystem needs
packages fetched from a git URL, and a git URL is not an immutable identity —
tags move and a force-push rewrites history. The fetch path
(`distribution/remote_registry.py`, `distribution/lockfile.py`) closes that:

- A package's identity is `name@<commit-sha>`, never `name@<tag>`. A ref is
  resolved to a 40-char SHA *once*, at fetch time (via `git ls-remote`);
  everything downstream pins the SHA.
- `fetch_and_lock` fetches the package SHA-pinned into a content-addressed
  cache and records an entry in `.cognitive-firm/packages.lock`: the resolved
  URL, the commit SHA, and a **content hash** over the fetched files.
- **SHA pinning** catches a moved tag — a later resolve points at a different
  SHA. The **content hash** catches the rarer case where the same SHA is made
  to carry different bytes (a force-push, a lying registry); a re-fetch whose
  content hash differs is a hard `LockMismatch`.

`cognitive-firm-distro install <git-url>` runs this path; `--ref` selects the
tag/branch/SHA to pin (default `HEAD`).

## Distro inheritance

A manifest may declare `extends: <base-distro>`. Installing the extender first
installs the named base distro, then composes the extender's components on top
— so a specialized distro can build on a general one without copying its
files. Inheritance is **one level only**: the base must be `kind: distro` and
must not itself declare `extends`.

## Rollback

`rollback` (`distribution/rollback.py`) undoes an install. Two modes, chosen
automatically:

- **clean** — nothing has been committed since the install boundary: a
  `git reset --hard` to the pre-install ref. Total and exact. (For a
  first-ever install, with no prior ref, the installed files are removed.)
- **compensating** — the org has run since the install: the install commit is
  reverted as a new *forward* commit, so the append-only history stays
  replayable. If post-install edits to the installed files make the revert
  conflict, the rollback is reported blocked, not forced.

`uninstall` is a rollback; `upgrade` is a forced install of a newer version
whose receipt records the pre-upgrade ref, so a post-upgrade rollback returns
to the pre-upgrade state.

## Authoring loop

A third-party author can iterate on a package without ever installing it into
a live org:

- `cognitive-firm-distro lint <package>` parses the manifest and reports every
  authoring problem at once — missing component sources, an unknown `op`, a
  path that escapes its root, a too-short description, a missing `files/`
  directory. The argument may be a package directory, a `package.yaml` path,
  or a registry package name.
- `cognitive-firm-distro install <package> --into <dir> --dry-run` resolves
  and prints the full install plan — each file, its composition `op`, and
  whether it would conflict — without creating a git repo or writing anything.
- `docs/templates/package/` is a copyable package skeleton with a heavily
  commented manifest.

## CLI

```sh
cognitive-firm-distro list
cognitive-firm-distro show       starter-firm
cognitive-firm-distro lint       ./path/to/package
cognitive-firm-distro install    starter-firm --into ./my-firm
cognitive-firm-distro install    starter-firm --into ./my-firm --dry-run
cognitive-firm-distro install    https://example.com/repo.git --into ./my-firm --ref v1.2.0
cognitive-firm-distro verify     starter-firm --into ./my-firm
cognitive-firm-distro upgrade    starter-firm --into ./my-firm
cognitive-firm-distro rollback   starter-firm --into ./my-firm --reason "..."
cognitive-firm-distro uninstall  starter-firm --into ./my-firm
```

`--registry <dir>` selects a registry. The bundled `distro/` ships in the
wheel, so `list` works from a `pip install`; `--registry` overrides it.

> The `cognitive-firm-distro install` CLI verb performs a direct, transactional
> install. The governed-overlay path (proposal + authority-diff + attested
> `package.install_approved`) is the `distribution/governed_install.py` API,
> used when an overlay is installed onto a *running* org.

## Boundary rule

A distro is policy: roles, mandates, preferences, operating units, and project
charters an adopter then edits to match their firm. The kernel defines the
mechanisms a distro composes. Adding a distro or overlay must never require a
kernel change.

## See also

- [Governance Change Proposals](governance-changes.md) — the proposal and
  invariant model the governed overlay install files into.
- [Extension Schemas](extension-schemas.md) — how a package validates a custom
  primitive payload type without a kernel change.
- [`docs/community-packages.md`](../community-packages.md) — the roadmap for
  shareable third-party packages.
