# Deployment

`cognitive-firm` supports two deployment paths:

- Docker Compose for local evaluation and simple server installs.
- systemd on a VPS for long-running single-principal operation.

The public kernel should stay tenant-neutral. Mount or symlink tenant overlays
into `org/` or `tenants/` rather than baking private project state into the
image.

## Docker Compose

Start from a clean checkout:

```bash
cp .env.example .env
./scripts/docker_smoke.sh
docker compose build
docker compose run --rm kernel
docker compose up orbit-sync orbit-web
```

Open `http://localhost:3000` for Orbit and `http://localhost:3001/api/health`
for the backend health endpoint.

By default, Compose runs Orbit in read-only projection mode:

```env
ORBIT_SURFACE_MODE=projection_only
COGNITIVE_FIRM_NOTIFICATION_CHANNEL=null
```

To let Orbit submit typed human intents such as gate resolution or human-work
updates, set:

```env
ORBIT_SURFACE_MODE=kernel_intents
ORBIT_API_TOKEN=<random bearer token>
```

Direct role/config mutation from Orbit remains disabled unless explicitly set:

```env
ORBIT_ALLOW_DIRECT_CONFIG_WRITES=1
```

`scripts/docker_smoke.sh` is the self-contained boot test. It builds the image,
runs the organization-surface CLI inside the container, runs the human-work CLI
inside the container, starts the Orbit backend, and checks `/api/health`.

## VPS / systemd

The systemd path is for the long-running daemon and local Orbit sync service:

```bash
./scripts/setup_vps.sh root@<vps-ip>
```

The bootstrap script installs Python, Node, agent CLIs, stages the systemd
units, creates `.env`, and leaves principal-specific secrets and tenant overlay
setup as explicit follow-up steps.

Relevant units:

- `deploy/agent-daemon.service`
- `deploy/orbit-sync.service`

## Deployment Boundary

The container image packages the kernel and optional Orbit surface. It does not
package:

- private tenant overlays;
- model-provider credentials;
- agent-CLI OAuth state;
- enterprise identity or SSO;
- production database/object-store adapters.

Those are deployment-specific configuration, not public-kernel state.
