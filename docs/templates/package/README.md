# cognitive-firm package template

Copy this directory as the starting point for a new distribution package — a
`distro` (a day-one-runnable starter organization) or an `overlay` (an add-on
installed on top of an existing organization).

## Layout

```text
package.yaml                    The manifest. Heavily commented — edit every field.
files/                          Exactly the overlay the package installs.
  roles/example-role.yaml       Example role.v1 file. Replace with your roles.
  mandates/example-role_mandate.md   Example mandate. Replace with your mandates.
README.md                       This file.
```

Everything the package installs lives under `files/`. Each `component` in
`package.yaml` maps a path under `files/` to a destination path in the target
organization. A `source` or `dest` that escapes its root is rejected.

## The authoring loop

This template is built for the third-party authoring loop. You can
iterate on a package without ever installing it into a live, governed org:

1. **Lint** — parse the manifest and report authoring problems (missing
   component sources, bad `op`, escaping paths, short description, malformed
   adapter manifests, or adapter conformance configs that drift from their
   manifest):

   ```sh
   cognitive-firm-distro lint path/to/your-package
   ```

   Exit code 0 means clean; non-zero means problems were printed. `lint`
   accepts a package directory, a `package.yaml` path, or a registry package
   name.

2. **Dry-run install** — resolve and print the full install plan (every file,
   its composition `op`, and whether it would conflict) without creating a git
   repo or writing any file:

   ```sh
   cognitive-firm-distro install your-package --into ./scratch-org --dry-run
   ```

Use these two commands as your inner loop: edit `package.yaml` or a file under
`files/`, re-run `lint`, then `--dry-run` against a representative org, and
only do a real `install` once both are clean.

## Notes

- This template lives under `docs/templates/` on purpose — it is **not** under
  `distro/`, so the registry never indexes it as a (deliberately incomplete)
  package.
- See `docs/protocols/distribution.md` for the full manifest and installer
  contract, and `distro/starter-firm/` for a complete, real distro to model.
