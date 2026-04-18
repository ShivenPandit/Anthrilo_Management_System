"""Merge heads after shopify master data and return index migrations.

Revision ID: 013_merge_shopify_returns_heads
Revises: 005_ret_dt_idx, 012_shopify_master_data
Create Date: 2026-04-18 09:20:00.000000
"""

# revision identifiers, used by Alembic.
revision = "013_merge_shopify_returns_heads"
down_revision = ("005_ret_dt_idx", "012_shopify_master_data")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
