# Deploying a starter-firm Organization

This is the single-host deployment story for an organization installed from the
`starter-firm` distro: one operator laptop, or one VPS. It uses only the infra
the kernel already ships — no new components.

A starter-firm org is a directory of files plus git. It does not *need* a server
to be real: the filesystem and git are the system of record. Deployment is about
running the long-lived daemons (the agent tick loop and the Orbit surface) so
the governance loop advances without an operator at the keyboard.

## Path A: Operator laptop (local evaluation)

Run the daemons under the existing `docker-compose` profile from a checkout of
the public kernel, with your installed org mounted into `org/`:

```bash
cp .env.example .env
docker compose build
docker compose run --rm kernel        # one agent tick, dry-run
docker compose up orbit-sync orbit-web
```

Orbit is at `http://localhost:3000`; the backend health check is at
`http://localhost:3001/api/health`. Compose runs Orbit read-only
(`ORBIT_SURFACE_MODE=projection_only`) by default. See `deploy/README.md` for
the full Compose options, including `kernel_intents` mode.

This is enough to inspect the governance loop and replay it. It is not a
long-running deployment — the `kernel` service ticks once and exits.

## Path B: One VPS (long-running, single principal)

For an organization that should keep advancing unattended, use the one-host VPS
path. Run from your laptop against a fresh Ubuntu VPS:

```bash
./scripts/setup_vps.sh root@<vps-ip>
```

`setup_vps.sh` is idempotent. It installs Python, Node, and the agent CLIs,
clones the public kernel, builds a venv, and stages — but does not enable — the
systemd units:

- `deploy/agent-daemon.service` — the long-running agent tick loop.
- `deploy/orbit-sync.service` — the local Orbit git-sync surface.

It deliberately leaves principal-specific steps as explicit follow-ups: deploy
keys, model-provider API keys in `.env`, agent-CLI OAuth, and the tenant
overlay clone. The script prints a copy-paste checklist for each.

After preflight passes, enable the daemons:

```bash
ssh cognitive@<vps-ip> 'sudo systemctl enable --now agent-daemon orbit-sync'
```

## Where the starter-firm org lives

The container image and the VPS checkout package the **kernel**, not your org.
Mount or symlink your installed starter-firm org into `org/` (or under
`tenants/`) rather than baking it into the image — the same boundary the kernel
keeps for any tenant overlay. The daemons read the org from there; git is what
makes it durable and replayable.

## Deployment boundary

A single host is the whole supported topology for a starter-firm org. The image
does not package private overlays, model-provider credentials, agent-CLI OAuth
state, or production database adapters — those are deployment-specific
configuration. Multi-host, T2 state backends, and clustered deployment are out
of scope for the starter distro; see `docs/protocols/state-backends.md` if you
outgrow one host.
