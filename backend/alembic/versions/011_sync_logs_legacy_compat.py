"""Relax legacy sync_logs compatibility constraints.

Revision ID: 011_sync_logs_legacy_compat
Revises: 010_reconcile_db_first_schema
Create Date: 2026-04-10 02:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "011_sync_logs_legacy_compat"
down_revision = "010_reconcile_db_first_schema"
branch_labels = None
depends_on = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    result = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).first()
    return result is not None


def upgrade() -> None:
    bind = op.get_bind()

    table_exists = bool(
        bind.execute(
            sa.text("SELECT to_regclass('public.sync_logs') IS NOT NULL")
        ).scalar()
    )
    if not table_exists:
        return

    if _column_exists(bind, "sync_logs", "entity_type"):
        op.execute(sa.text("UPDATE sync_logs SET entity_type = 'legacy' WHERE entity_type IS NULL OR entity_type = ''"))
        op.execute(sa.text("ALTER TABLE sync_logs ALTER COLUMN entity_type SET DEFAULT 'legacy'"))
        op.execute(sa.text("ALTER TABLE sync_logs ALTER COLUMN entity_type DROP NOT NULL"))


def downgrade() -> None:
    """No-op downgrade for compatibility migration."""
