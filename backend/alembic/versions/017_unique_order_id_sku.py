"""add unique constraint on order_id and sku

Revision ID: 017_unique_order_id_sku
Revises: 016_financial_fields
Create Date: 2026-04-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '017_unique_order_id_sku'
down_revision = '016_financial_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Remove duplicates on (order_id, sku) by keeping only the first record
    op.execute("""
    DELETE FROM sales_orders
    WHERE id NOT IN (
        SELECT MIN(id)
        FROM sales_orders
        WHERE sku IS NOT NULL AND order_id IS NOT NULL
        GROUP BY order_id, sku
    )
    AND sku IS NOT NULL 
    AND order_id IS NOT NULL
    """)

    # Step 2: Add unique constraint on (order_id, sku)
    op.create_unique_constraint(
        'uq_sales_orders_order_id_sku',
        'sales_orders',
        ['order_id', 'sku']
    )


def downgrade() -> None:
    op.drop_constraint('uq_sales_orders_order_id_sku', 'sales_orders')
