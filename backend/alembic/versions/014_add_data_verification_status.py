"""Compatibility bridge for historical data verification status revision.

Revision ID: 014_add_data_verification_status
Revises: 013_merge_shopify_returns_heads
Create Date: 2026-04-21 10:30:00.000000
"""

# revision identifiers, used by Alembic.
revision = "014_add_data_verification_status"
down_revision = "013_merge_shopify_returns_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No-op bridge migration: keeps environments with stamped 014 compatible.
    pass


def downgrade() -> None:
    pass
