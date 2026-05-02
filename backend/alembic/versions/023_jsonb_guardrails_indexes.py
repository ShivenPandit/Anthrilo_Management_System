"""Add JSONB guardrails and GIN indexes for extra_fields."""

from alembic import op


revision = "023_jsonb_guardrails"
down_revision = "022_uc_export_cols"
branch_labels = None
depends_on = None


def _add_jsonb_if_missing(table: str, column: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name='{table}' AND column_name='{column}'
          ) THEN
            ALTER TABLE {table} ADD COLUMN {column} JSONB;
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    _add_jsonb_if_missing("sales_orders", "extra_fields")
    _add_jsonb_if_missing("sales_returns", "extra_fields")
    _add_jsonb_if_missing("inventory_snapshots", "extra_fields")

    # Keep JSONB columns non-breaking but predictable for reads.
    op.execute(
        """
        ALTER TABLE sales_orders
        ALTER COLUMN extra_fields SET DEFAULT '{}'::jsonb;
        """
    )
    op.execute(
        """
        ALTER TABLE sales_returns
        ALTER COLUMN extra_fields SET DEFAULT '{}'::jsonb;
        """
    )
    op.execute(
        """
        ALTER TABLE inventory_snapshots
        ALTER COLUMN extra_fields SET DEFAULT '{}'::jsonb;
        """
    )

    # GIN indexes for performant key/value lookups on JSONB.
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public' AND tablename='sales_orders' AND indexname='idx_sales_orders_extra_fields_gin'
          ) THEN
            CREATE INDEX idx_sales_orders_extra_fields_gin
            ON sales_orders USING GIN (extra_fields);
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public' AND tablename='sales_returns' AND indexname='idx_sales_returns_extra_fields_gin'
          ) THEN
            CREATE INDEX idx_sales_returns_extra_fields_gin
            ON sales_returns USING GIN (extra_fields);
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public' AND tablename='inventory_snapshots' AND indexname='idx_inventory_snapshots_extra_fields_gin'
          ) THEN
            CREATE INDEX idx_inventory_snapshots_extra_fields_gin
            ON inventory_snapshots USING GIN (extra_fields);
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Non-destructive downgrade for production safety.
    pass

