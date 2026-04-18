"""Add indexes on sales_returns created_at and updated_at

Revision ID: 005_ret_dt_idx
Revises: 011_sync_logs_legacy_compat
"""
from alembic import op
import sqlalchemy as sa

revision = "005_ret_dt_idx"
down_revision = "011_sync_logs_legacy_compat"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_sales_returns_created_at ON sales_returns (created_at)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_sales_returns_updated_at ON sales_returns (updated_at)"))


def downgrade():
    op.execute(sa.text("DROP INDEX IF EXISTS ix_sales_returns_updated_at"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_sales_returns_created_at"))
