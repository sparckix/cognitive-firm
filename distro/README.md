# Distros

A *distro* is a curated, day-one-runnable governed organization. Installing one
turns an empty directory into a firm with roles, mandates, and principal
preferences — inspectable, forkable, and replayable from the first commit.

This is the userland/distribution layer of the OS analogy: the kernel stays
generic and is never edited by an adopter; a distro composes a runnable
organization an operator installs in one action.

## Layout

Each package is a directory with a `package.yaml` manifest and a `files/`
directory holding the overlay it installs:

```text
distro/
  starter-firm/
    package.yaml
    files/
      roles/
      mandates/
      preferences/
```

## Install

```sh
cognitive-firm-distro list
cognitive-firm-distro show starter-firm
cognitive-firm-distro install starter-firm --into ./my-firm
cognitive-firm-distro verify starter-firm --into ./my-firm
```

See `docs/protocols/distribution.md` for the manifest format, the installer
contract, and how overlay packages extend an installed organization.
