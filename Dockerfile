FROM node:22-bookworm-slim AS orbit-build

WORKDIR /app/orbit
COPY orbit/package*.json ./
RUN npm ci
COPY orbit/ ./
RUN npm run build

FROM nginx:1.27-alpine AS orbit-static
COPY --from=orbit-build /app/orbit/dist /usr/share/nginx/html

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ORG_ROOT=/app/org \
    COGNITIVE_FIRM_WORKSPACE=/app/cognitive_firm_workspace \
    TRANSITIONS_LOG=/app/cognitive_firm_workspace/transitions.jsonl \
    GATES_DIR=/app/cognitive_firm_workspace/gates/pending \
    GATES_RESOLVED_DIR=/app/cognitive_firm_workspace/gates/resolved \
    ORBIT_BACKEND_HOST=0.0.0.0 \
    ORBIT_BACKEND_PORT=3001 \
    ORBIT_CORS_ORIGIN=http://localhost:3000 \
    ORBIT_SURFACE_MODE=projection_only \
    COGNITIVE_FIRM_NOTIFICATION_CHANNEL=null

WORKDIR /app

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=orbit-build /usr/local/bin/node /usr/local/bin/node

COPY pyproject.toml README.md requirements.txt ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e .

COPY scripts ./scripts
COPY org ./org
COPY schemas ./schemas
COPY docs ./docs
COPY deploy ./deploy
COPY orbit/src ./orbit/src
COPY orbit/package*.json ./orbit/
COPY --from=orbit-build /app/orbit/node_modules ./orbit/node_modules
COPY --from=orbit-build /app/orbit/dist ./orbit/dist

RUN mkdir -p /app/cognitive_firm_workspace/gates/pending /app/cognitive_firm_workspace/gates/resolved

EXPOSE 3001

CMD ["python", "-m", "cognitive_firm.orchestration.org_surface"]
