#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-cognitive-firm-public-smoke}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker client is not installed." >&2
  exit 2
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: docker daemon is not reachable." >&2
  echo "Start Docker Desktop, Colima, or the server Docker service, then re-run:" >&2
  echo "  ./scripts/docker_smoke.sh" >&2
  exit 3
fi

docker build -t "$IMAGE" .

docker run --rm "$IMAGE" python scripts/package_smoke.py >/tmp/cognitive-firm-package-smoke.json
docker run --rm "$IMAGE" python scripts/kernel_conformance_smoke.py >/tmp/cognitive-firm-kernel-conformance.json
docker run --rm "$IMAGE" python scripts/app_integration_conformance.py >/tmp/cognitive-firm-app-conformance.json
docker run --rm "$IMAGE" python scripts/app_service_integration_smoke.py >/tmp/cognitive-firm-app-service-smoke.json
docker run --rm "$IMAGE" python scripts/field_pilot_scaffold.py /tmp/cognitive-firm-field-pilot-smoke >/tmp/cognitive-firm-field-pilot-scaffold.txt
docker run --rm "$IMAGE" python -m cognitive_firm.orchestration.org_surface --json >/tmp/cognitive-firm-org-surface.json
docker run --rm "$IMAGE" python -m cognitive_firm.orchestration.human_work --help >/tmp/cognitive-firm-human-work-help.txt
container_id="$(docker run -d --rm -e ORBIT_SURFACE_MODE=projection_only -p 3001:3001 "$IMAGE" node orbit/node_modules/tsx/dist/cli.mjs orbit/src/server/git-sync.ts)"
trap 'docker rm -f "$container_id" >/dev/null 2>&1 || true' EXIT

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:3001/api/health >/tmp/cognitive-firm-orbit-health.json; then
    echo "OK: Docker image built and Orbit backend health endpoint responded."
    exit 0
  fi
  sleep 1
done

echo "ERROR: Orbit backend did not answer /api/health within 30s." >&2
docker logs "$container_id" >&2 || true
exit 4
