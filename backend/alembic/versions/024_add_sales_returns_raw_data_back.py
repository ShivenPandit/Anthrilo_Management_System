"""Add raw_data JSONB back to sales_returns.

Revision ID: 024_add_sales_returns_raw_data_back
Revises: 023_jsonb_guardrails_indexes
Create Date: 2026-04-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "024_add_sales_returns_raw_data_back"
down_revision = "023_jsonb_guardrails_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("sales_returns")}
    if "raw_data" not in existing:
        op.add_column("sales_returns", sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns("sales_returns")}
    if "raw_data" in existing:
        op.drop_column("sales_returns", "raw_data")
