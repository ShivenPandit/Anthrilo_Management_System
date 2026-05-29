"""Trim inventory_snapshots columns to match export API.

Revision ID: 029_trim_inventory_snapshots
Revises: 028_add_sync_state
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa


revision = "029_trim_inventory_snapshots"
down_revision = "028_add_sync_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("inventory_snapshots", "category_name", new_column_name="category")
    op.add_column("inventory_snapshots", sa.Column("mrp", sa.Numeric(12, 2), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("cost_price", sa.Numeric(12, 2), nullable=True))

    op.execute(
        """
        UPDATE inventory_snapshots
        SET cost_price = CASE
            WHEN cost_price_csv ~ '^[0-9]+(\\.[0-9]+)?$' THEN cost_price_csv::numeric
            ELSE NULL
        END
        WHERE cost_price IS NULL
        """
    )

    op.drop_column("inventory_snapshots", "item_type_name")
    op.drop_column("inventory_snapshots", "ean")
    op.drop_column("inventory_snapshots", "upc")
    op.drop_column("inventory_snapshots", "isbn")
    op.drop_column("inventory_snapshots", "open_sale")
    op.drop_column("inventory_snapshots", "bad_inventory")
    op.drop_column("inventory_snapshots", "putaway_pending")
    op.drop_column("inventory_snapshots", "pending_inventory_assessment")
    op.drop_column("inventory_snapshots", "open_purchase")
    op.drop_column("inventory_snapshots", "enabled")
    op.drop_column("inventory_snapshots", "source_updated_at")
    op.drop_column("inventory_snapshots", "cost_price_csv")


def downgrade() -> None:
    op.add_column("inventory_snapshots", sa.Column("cost_price_csv", sa.Text(), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("source_updated_at", sa.Text(), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("enabled", sa.Text(), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("open_purchase", sa.Text(), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("pending_inventory_assessment", sa.Text(), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("putaway_pending", sa.Text(), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("bad_inventory", sa.Text(), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("open_sale", sa.Text(), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("isbn", sa.Text(), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("upc", sa.Text(), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("ean", sa.Text(), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("item_type_name", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE inventory_snapshots
        SET cost_price_csv = cost_price::text
        WHERE cost_price IS NOT NULL
        """
    )

    op.drop_column("inventory_snapshots", "cost_price")
    op.drop_column("inventory_snapshots", "mrp")
    op.alter_column("inventory_snapshots", "category", new_column_name="category_name")
