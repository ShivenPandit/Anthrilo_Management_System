"""fix_inventory_case_duplicate_skus

Merge case-variant duplicate SKU rows in facility_inventory_snapshot.
The CSV export provides SKUs in both 'Item Type SKU' (UPPERCASE) and
'Item SkuCode' (lowercase), causing duplicate rows like AN46886 / an46886.
This migration keeps the UPPER variant and deletes lowercase duplicates.

Revision ID: 030_fix_inventory_case_duplicates
Revises: e636796d27cc
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = '030_fix_inv_case_dups'
down_revision = 'e636796d27cc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: For each case-duplicate group, delete the lowercase variant.
    # The uppercase variant is the canonical SKU in Unicommerce.
    # We keep the row with sku = UPPER(sku). If both are uppercase (shouldn't happen),
    # we keep the one with the latest synced_at.
    op.execute(sa.text("""
        DELETE FROM facility_inventory_snapshot
        WHERE id IN (
            SELECT id FROM (
                SELECT
                    id,
                    sku,
                    UPPER(sku) AS sku_upper,
                    ROW_NUMBER() OVER (
                        PARTITION BY UPPER(sku), facility_code
                        ORDER BY
                            -- Prefer the uppercase variant
                            CASE WHEN sku = UPPER(sku) THEN 0 ELSE 1 END,
                            -- Then prefer the most recently synced
                            synced_at DESC
                    ) AS rn
                FROM facility_inventory_snapshot
            ) ranked
            WHERE rn > 1
        )
    """))

    # Step 2: Normalize remaining lowercase SKUs to uppercase
    op.execute(sa.text("""
        UPDATE facility_inventory_snapshot
        SET sku = UPPER(sku)
        WHERE sku != UPPER(sku)
    """))


def downgrade() -> None:
    # Cannot un-delete rows, but this is a data-only migration
    # so downgrade is a no-op
    pass
