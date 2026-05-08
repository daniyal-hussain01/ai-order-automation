#!/usr/bin/env bash
# One-shot deploy script — run on the EC2 host after `git clone`.
set -euo pipefail

cd "$(dirname "$0")/.."

# Ensure .env exists
if [ ! -f .env ]; then
  cp .env.example .env
  echo "→ Created .env from example. Edit it before re-running for live integrations."
fi

# Build & start
docker compose pull || true
docker compose build
docker compose up -d

# Wait for health
echo "→ Waiting for backend to become healthy…"
for i in {1..30}; do
  if curl -fsS http://localhost/api/v1/health >/dev/null 2>&1; then
    echo "✓ Healthy"
    docker compose ps
    exit 0
  fi
  sleep 2
done
echo "✗ Backend did not become healthy in time"
docker compose logs --tail=80
exit 1
