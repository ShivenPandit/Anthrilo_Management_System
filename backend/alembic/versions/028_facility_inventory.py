"""Compatibility placeholder for removed facility inventory revision.

Revision ID: 028_facility_inventory
Revises: 4ee7c3339ab0
Create Date: 2026-05-25

This migration intentionally performs no schema changes. It exists to
preserve migration graph continuity for databases that were previously
stamped with revision id `028_facility_inventory`.
"""


revision = "028_facility_inventory"
down_revision = "4ee7c3339ab0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
