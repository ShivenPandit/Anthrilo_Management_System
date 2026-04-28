"""dedupe sales orders and tighten uniqueness

Revision ID: 018_sales_order_item_uniq
Revises: 017_unique_order_id_sku
Create Date: 2026-04-28 14:35:00.000000
"""

from alembic import op


revision = "018_sales_order_item_uniq"
down_revision = "017_unique_order_id_sku"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM sales_orders a
        USING sales_orders b
        WHERE a.id > b.id
          AND a.order_id = b.order_id
          AND a.sale_order_item_code = b.sale_order_item_code
        """
    )

    op.execute(
        """
        DELETE FROM sales_orders
        WHERE order_id LIKE '%_FORWARD%'
           OR order_id LIKE '%_REPL%'
           OR LOWER(COALESCE(order_id, '')) LIKE '%test%'
        """
    )

    op.execute("ALTER TABLE sales_orders DROP CONSTRAINT IF EXISTS uq_sales_orders_order_id_sku")
    op.execute("DROP INDEX IF EXISTS uq_sales_orders_order_item_month")
    op.execute("ALTER TABLE sales_orders DROP CONSTRAINT IF EXISTS uq_sales_orders_order_item_month")
    op.create_unique_constraint(
        "uq_sales_orders_order_item",
        "sales_orders",
        ["order_id", "sale_order_item_code"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_sales_orders_order_item", "sales_orders", type_="unique")
    op.create_unique_constraint(
        "uq_sales_orders_order_item_month",
        "sales_orders",
        ["order_id", "sale_order_item_code", "partition_month"],
    )
    op.create_unique_constraint(
        "uq_sales_orders_order_id_sku",
        "sales_orders",
        ["order_id", "sku"],
    )
