#!/bin/sh
set -eu

case "${RUN_MIGRATIONS_ON_STARTUP:-true}" in
true|TRUE|1|yes|YES)
  echo "Applying database migrations..."
  python - <<'PY'
import os
from sqlalchemy import create_engine, inspect, text

database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise SystemExit(0)

engine = create_engine(database_url)
with engine.begin() as conn:
    inspector = inspect(conn)
    if not inspector.has_table("alembic_version"):
        raise SystemExit(0)

    rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    versions = {row[0] for row in rows}
    if {"4ee7c3339ab0", "028_facility_inventory"}.issubset(versions):
        # Keep the newer descendant revision to avoid Alembic overlap errors.
        conn.execute(
            text("DELETE FROM alembic_version WHERE version_num = :version"),
            {"version": "4ee7c3339ab0"},
        )
        print("Normalized alembic_version: removed overlapping 4ee7c3339ab0")

    # If sync_state schema already exists, ensure the corresponding migration
    # revision is stamped so Alembic does not attempt to recreate the table.
    versions = {
        row[0]
        for row in conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    }
    if inspector.has_table("sync_state") and "028_add_sync_state" not in versions:
        if "028_facility_inventory" in versions:
            conn.execute(
                text(
                    "UPDATE alembic_version "
                    "SET version_num = :target "
                    "WHERE version_num = :source"
                ),
                {"target": "028_add_sync_state", "source": "028_facility_inventory"},
            )
            print("Stamped alembic_version to 028_add_sync_state from 028_facility_inventory")
        elif "4ee7c3339ab0" in versions:
            conn.execute(
                text(
                    "UPDATE alembic_version "
                    "SET version_num = :target "
                    "WHERE version_num = :source"
                ),
                {"target": "028_add_sync_state", "source": "4ee7c3339ab0"},
            )
            print("Stamped alembic_version to 028_add_sync_state from 4ee7c3339ab0")
PY
  alembic upgrade head
  ;;
*)
  echo "Skipping migrations (RUN_MIGRATIONS_ON_STARTUP=${RUN_MIGRATIONS_ON_STARTUP:-false})"
  ;;
esac

exec "$@"
