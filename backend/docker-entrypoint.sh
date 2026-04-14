#!/bin/sh
set -eu

case "${RUN_MIGRATIONS_ON_STARTUP:-true}" in
true|TRUE|1|yes|YES)
  echo "Applying database migrations..."
  alembic upgrade head
  ;;
*)
  echo "Skipping migrations (RUN_MIGRATIONS_ON_STARTUP=${RUN_MIGRATIONS_ON_STARTUP:-false})"
  ;;
esac

exec "$@"
