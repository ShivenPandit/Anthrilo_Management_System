"""Add financial fields (discount, tax, refund, category) to sales_orders.

Revision ID: 016_financial_fields
Revises: 015_shopify_master_v2
Create Date: 2026-04-25 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "016_financial_fields"
down_revision = "015_shopify_master_v2"
branch_labels = None
depends_on = None


def _index_exists(bind, index_name: str) -> bool:
    result = bind.execute(
        sa.text("SELECT to_regclass(:name) IS NOT NULL"),
        {"name": f"public.{index_name}"},
    ).scalar()
    return bool(result)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Add columns ──
    op.execute(sa.text(
        "ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS discount NUMERIC(12, 2) NOT NULL DEFAULT 0"
    ))
    op.execute(sa.text(
        "ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS tax NUMERIC(12, 2) NOT NULL DEFAULT 0"
    ))
    op.execute(sa.text(
        "ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS refund NUMERIC(12, 2) NOT NULL DEFAULT 0"
    ))
    op.execute(sa.text(
        "ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS category VARCHAR(120)"
    ))

    # ── Index on category ──
    if not _index_exists(bind, "ix_sales_orders_category"):
        op.execute(sa.text(
            "CREATE INDEX ix_sales_orders_category ON sales_orders (category)"
        ))

    # ── Backfill category from raw_data ──
    op.execute(sa.text("""
        UPDATE sales_orders
        SET category = COALESCE(
            raw_data->>'Category',
            raw_data->>'category',
            ''
        )
        WHERE category IS NULL
          AND raw_data IS NOT NULL
    """))

    # ── Backfill discount from raw_data ──
    op.execute(sa.text("""
        UPDATE sales_orders
        SET discount = COALESCE(
            NULLIF(REPLACE(COALESCE(
                raw_data->>'Discount',
                raw_data->>'discount',
                '0'
            ), ',', ''), '')::NUMERIC(12, 2),
            0
        )
        WHERE discount = 0
          AND raw_data IS NOT NULL
    """))

    # ── Backfill tax from raw_data ──
    op.execute(sa.text("""
        UPDATE sales_orders
        SET tax = COALESCE(
            NULLIF(REPLACE(COALESCE(
                raw_data->>'Tax Amount',
                raw_data->>'taxAmount',
                raw_data->>'Tax',
                raw_data->>'tax',
                '0'
            ), ',', ''), '')::NUMERIC(12, 2),
            0
        )
        WHERE tax = 0
          AND raw_data IS NOT NULL
    """))

    # ── Backfill refund from raw_data ──
    op.execute(sa.text("""
        UPDATE sales_orders
        SET refund = COALESCE(
            NULLIF(REPLACE(COALESCE(
                raw_data->>'Refund Amount',
                raw_data->>'refundAmount',
                raw_data->>'Refund',
                raw_data->>'refund',
                '0'
            ), ',', ''), '')::NUMERIC(12, 2),
            0
        )
        WHERE refund = 0
          AND raw_data IS NOT NULL
    """))

    # ── Normalize status to uppercase ──
    op.execute(sa.text("""
        UPDATE sales_orders
        SET status = UPPER(status)
        WHERE status != UPPER(status)
    """))


def downgrade() -> None:
    # Keep downgrade non-destructive
    pass
