"""Add indexes on sales_returns created_at and updated_at

Revision ID: 005_ret_dt_idx
Revises: 011_sync_logs_legacy_compat
"""
from alembic import op

revision = "005_ret_dt_idx"
down_revision = "011_sync_logs_legacy_compat"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_sales_returns_created_at", "sales_returns", ["created_at"])
    op.create_index("ix_sales_returns_updated_at", "sales_returns", ["updated_at"])


def downgrade():
    op.drop_index("ix_sales_returns_updated_at", table_name="sales_returns")
    op.drop_index("ix_sales_returns_created_at", table_name="sales_returns")
