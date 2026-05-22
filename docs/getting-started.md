# Getting Started — Zero to a Running Governed Firm

This is the shortest path from nothing to a running, governed organization.
For the conceptual tour read [`first-30-minutes.md`](first-30-minutes.md); for
the kernel/overlay boundary read
[`adopting-cognitive-firm.md`](adopting-cognitive-firm.md). This page is the
*operational* path.

## The mental model

Three things, in three layers:

- **The kernel** — the governance engine. You never edit it. `pip install` gives
  you the kernel plus three command-line tools.
- **A distro** — a runnable governed organization (roles, mandates, an
  operating unit, a project). `starter-firm` is the bundled one. You install a
  distro *into a directory*; that directory becomes your firm, as a git repo.
- **The tools** — `cognitive-firm-distro` (install/manage firms and packages),
  `cognitive-firm-kernel-service` (the local HTTP boundary the userland and
  Orbit read), `cognitive-firm-userland` (the operator's terminal surface).

A firm is a directory. The tools act on a firm by being pointed at it.

## Path A — local

```bash
# 1. Get the kernel and the CLIs.
git clone https://github.com/sparckix/cognitive-firm ~/cognitive-firm
cd ~/cognitive-firm
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt && pip install -e .
# (a published `pip install cognitive-firm` is the intended future path;
#  the packaging is ready, the PyPI release is not yet cut.)

# 2. Install a governed organization into a directory of your choosing.
cognitive-firm-distro install starter-firm --into ~/my-firm
# ~/my-firm is now a governed firm: its own git repo, verified to boot.

# 3. Point the tools at that firm and bring up the local boundary.
export ORG_ROOT=~/my-firm
cognitive-firm-kernel-service --host 127.0.0.1 --port 8765 &

# 4. Use it.
cognitive-firm-userland status                 # plain-language org health
cognitive-firm-userland needs-me <your-actor>   # what needs you
```

**The one thing that connects install to run is `ORG_ROOT`.** The installer
puts the firm in a directory; `ORG_ROOT` tells every tool which firm to act on.
Without it, the tools fall back to the repo's own `org/`.

To run role daemons (agents taking governed ticks), point
`scripts/agent_daemon.py` at the same firm — see
[`first-30-minutes.md`](first-30-minutes.md) and
`distro/starter-firm/DEPLOY.md`.

## Path B — Docker

```bash
docker compose up
```

This builds the image (kernel + bundled distros + Orbit) and brings up a
serviceable firm:

- `kernel` runs `cognitive-firm-kernel-service` — the HTTP boundary — on
  port **8765**. This is the data source the userland CLI and Orbit read and
  write through.
- `orbit-sync` is the Orbit projection daemon (port 3001); it depends on the
  kernel service and proxies reads/writes to it.
- `orbit-web` serves the Orbit web UI on port **3000**.
- Role daemons (agents taking governed ticks, which spend LLM budget) are
  **opt-in**: `docker compose --profile agents up` also starts the `daemon`
  service. Its default tick is a dry-run; drop `--dry-run` for real governed
  ticks.

The CLIs are on PATH in the image, e.g.
`docker compose exec kernel cognitive-firm-userland status`.

Today the compose runs against the repo's `org/`; to run a firm you installed
elsewhere, install it into the directory the compose mounts as the org, or set
`ORG_ROOT` in `.env`.

## Rolling back

Every install is a git commit. A bad install is reversible:

```bash
cognitive-firm-distro rollback starter-firm --into ~/my-firm
```

## Where to go next

- Add capability to a running firm with an overlay — but note: installing an
  overlay onto a *running* org is **governed**. Use
  `cognitive-firm-distro install-overlay <overlay> --into ~/my-firm`; it shows
  the authority-diff and an overlay that would widen authority is blocked.
- Build and share your own distro or overlay —
  [`community-packages.md`](community-packages.md) and the template at
  `docs/templates/package/`.
- The protocol the installer obeys — [`protocols/distribution.md`](protocols/distribution.md).
