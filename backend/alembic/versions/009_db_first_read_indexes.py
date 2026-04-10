"""Restore missing DB-first read-index revision.

Revision ID: 009_db_first_read_indexes
Revises: 008_monthly_partition_tables
Create Date: 2026-04-10 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "009_db_first_read_indexes"
down_revision = "008_monthly_partition_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Historical placeholder revision.

    This revision was referenced in live databases but missing from source.
    Keep this as a no-op to preserve migration graph continuity.
    """



def downgrade() -> None:
    """No-op downgrade for historical placeholder revision."""
