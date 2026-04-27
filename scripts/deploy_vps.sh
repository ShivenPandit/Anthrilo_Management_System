#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-.env.prod}"
COMPOSE_FILE="docker-compose.prod.yml"
ACTION="${ACTION:-deploy}"   # deploy | update | restart
NO_BUILD="${NO_BUILD:-0}"     # 1 to skip image build
API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
RUN_POST_DEPLOY_FIXES="${RUN_POST_DEPLOY_FIXES:-1}"   # 1 to reset UC cache after deploy
RUN_FULL_BACKFILL="${RUN_FULL_BACKFILL:-0}"           # 1 to trigger full backfill profile
BACKFILL_FROM_DATE="${BACKFILL_FROM_DATE:-2024-01-01}"
BACKFILL_TO_DATE="${BACKFILL_TO_DATE:-}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Error: docker compose plugin is not available."
  exit 1
fi

for required_file in "$ENV_FILE" "backend/.env" "frontend/.env.local"; do
  if [ ! -f "$required_file" ]; then
    echo "Error: missing required file: $required_file"
    exit 1
  fi
done

if [ -z "$BACKFILL_TO_DATE" ]; then
  BACKFILL_TO_DATE="$(date +%F)"
fi

compose_cmd=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

echo "Action: $ACTION"

case "$ACTION" in
  deploy|update)
    if [ "$NO_BUILD" = "1" ]; then
      echo "Starting production stack (no build)..."
      "${compose_cmd[@]}" up -d
    else
      echo "Building and starting production stack..."
      "${compose_cmd[@]}" up -d --build
    fi
    ;;
  restart)
    echo "Restarting running production stack..."
    "${compose_cmd[@]}" restart
    ;;
  *)
    echo "Error: invalid ACTION '$ACTION' (expected: deploy | update | restart)"
    exit 1
    ;;
esac

echo "Waiting for backend health at ${API_BASE_URL}/health ..."
health_ok=0
for i in $(seq 1 60); do
  if curl -fsS "${API_BASE_URL}/health" >/dev/null 2>&1; then
    health_ok=1
    break
  fi
  sleep 2
done

if [ "$health_ok" != "1" ]; then
  echo "Warning: backend health check did not pass in time. Continuing."
else
  echo "Backend health check passed."
fi

if [ "$RUN_POST_DEPLOY_FIXES" = "1" ]; then
  echo "Resetting Unicommerce cache..."
  curl -fsS -X POST "${API_BASE_URL}/api/v1/integrations/unicommerce/cache/reset?warm=true" >/dev/null \
    && echo "Cache reset successful." \
    || echo "Warning: cache reset request failed."
fi

if [ "$RUN_FULL_BACKFILL" = "1" ]; then
  echo "Triggering full backfill profile (${BACKFILL_FROM_DATE} to ${BACKFILL_TO_DATE})..."
  curl -fsS -X POST "${API_BASE_URL}/api/v1/integrations/unicommerce/sync/profile/full_backfill?from_date=${BACKFILL_FROM_DATE}&to_date=${BACKFILL_TO_DATE}&run_in_background=true" >/dev/null \
    && echo "Backfill started in background." \
    || echo "Warning: full backfill request failed."
fi

echo "Running containers:"
"${compose_cmd[@]}" ps

echo "Recent backend logs:"
"${compose_cmd[@]}" logs --tail=30 backend

echo "Deployment completed."
echo "Health check URL: ${API_BASE_URL}/health"
