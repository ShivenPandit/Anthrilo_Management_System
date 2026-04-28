"""add sales order date sanity guard

Revision ID: 019_sales_order_date_guard
Revises: 018_sales_order_item_uniq
Create Date: 2026-04-28 15:15:00.000000
"""

from alembic import op


revision = "019_sales_order_date_guard"
down_revision = "018_sales_order_item_uniq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_sales_orders_order_date_valid",
        "sales_orders",
        "order_date >= TIMESTAMP '2024-01-01 00:00:00'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_sales_orders_order_date_valid", "sales_orders", type_="check")
