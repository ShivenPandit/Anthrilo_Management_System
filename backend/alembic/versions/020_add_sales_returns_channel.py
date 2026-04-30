"""Add channel column to sales_returns.

This file is intentionally recreated because the database currently expects
revision '020_add_sales_returns_channel' but the migration script was missing
from the repository.
"""

from alembic import op
import sqlalchemy as sa


revision = "020_add_sales_returns_channel"
down_revision = "019_sales_order_date_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add channel column if not already present.
    # (Postgres will throw if the column exists, so we guard by executing a DDL check.)
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name='sales_returns' AND column_name='channel'
          ) THEN
            ALTER TABLE sales_returns ADD COLUMN channel VARCHAR(120);
          END IF;
        END $$;
        """
    )
    # Index for channel filtering/aggregation (safe if exists).
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE schemaname='public' AND tablename='sales_returns' AND indexname='ix_sales_returns_channel'
          ) THEN
            CREATE INDEX ix_sales_returns_channel ON sales_returns (channel);
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sales_returns DROP COLUMN IF EXISTS channel;")

