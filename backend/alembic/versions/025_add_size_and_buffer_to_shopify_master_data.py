"""Add size and buffer columns to shopify_master_data

Revision ID: 025_add_size_and_buffer_to_shopify_master_data
Revises: 024_add_sales_returns_raw_data_back
Create Date: 2026-05-04
"""

from alembic import op
import sqlalchemy as sa


revision = "025_shopify_size_buffer"
down_revision = "024_returns_raw_data_back"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shopify_master_data", sa.Column("size", sa.String(length=120), nullable=True))
    op.create_index("ix_shopify_master_data_size", "shopify_master_data", ["size"], unique=False)
    op.add_column("shopify_master_data", sa.Column("buffer", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("shopify_master_data", "buffer")
    op.drop_index("ix_shopify_master_data_size", table_name="shopify_master_data")
    op.drop_column("shopify_master_data", "size")