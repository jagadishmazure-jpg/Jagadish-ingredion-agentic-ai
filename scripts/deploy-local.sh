#!/usr/bin/env bash
# One-command local demo: build the image and start the API + demo UI.
#
# Usage:
#   ./scripts/deploy-local.sh          # start in background
#   ./scripts/deploy-local.sh --logs   # start and follow logs
#
# Stop with: docker compose down
set -euo pipefail

command -v docker >/dev/null 2>&1 || { echo "ERROR: docker not found. Install Docker Desktop first." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "ERROR: 'docker compose' plugin not found." >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "ERROR: curl not found." >&2; exit 1; }

echo "[local] Building and starting the service ..."
docker compose up --build -d

echo "[local] Waiting for http://localhost:8000/api/health ..."
for i in $(seq 1 30); do
  if curl -sf --max-time 5 http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "[local] Service is healthy."
    break
  fi
  if [[ "$i" -eq 30 ]]; then
    echo "[local] ERROR: health check timed out. Logs:" >&2
    docker compose logs --tail=50
    exit 1
  fi
  sleep 2
done

echo ""
echo "================================================================"
echo "  Demo UI:    http://localhost:8000/"
echo "  API health: http://localhost:8000/api/health"
echo "  API docs:   http://localhost:8000/docs"
echo "================================================================"
echo ""
echo "Stop with: docker compose down"

if [[ "${1:-}" == "--logs" ]]; then
  docker compose logs -f
fi
