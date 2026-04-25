"""Expand Shopify master data structure to match new CSV format.

Revision ID: 015_shopify_master_v2
Revises: 014_add_data_verification_status
Create Date: 2026-04-25 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "015_shopify_master_v2"
down_revision = "014_add_data_verification_status"
branch_labels = None
depends_on = None


def _index_exists(bind, index_name: str) -> bool:
    result = bind.execute(
        sa.text("SELECT to_regclass(:name) IS NOT NULL"),
        {"name": f"public.{index_name}"},
    ).scalar()
    return bool(result)


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS style_code VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS gender VARCHAR(50)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS collection VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS subtype VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS season VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS fabric_type VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS print_name VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS net_weight VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS production_time VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS simple_bundle VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS mrp NUMERIC(12, 2)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS gross_weights_1 VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS garment_1 VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS gross_weights_2 VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS garment_2 VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS amazon_asin VARCHAR(255)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS amazon_flex_sku VARCHAR(255)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS amazon_fba_sku VARCHAR(255)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS amazon_mfn_sku VARCHAR(255)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS myntra_style_id VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS myntra_sku VARCHAR(120)"))
    op.execute(sa.text("ALTER TABLE shopify_master_data ADD COLUMN IF NOT EXISTS fc VARCHAR(120)"))

    if not _index_exists(bind, "ix_shopify_master_data_style_code"):
        op.execute(sa.text("CREATE INDEX ix_shopify_master_data_style_code ON shopify_master_data (style_code)"))
    if not _index_exists(bind, "ix_shopify_master_data_gender"):
        op.execute(sa.text("CREATE INDEX ix_shopify_master_data_gender ON shopify_master_data (gender)"))
    if not _index_exists(bind, "ix_shopify_master_data_amazon_asin"):
        op.execute(sa.text("CREATE INDEX ix_shopify_master_data_amazon_asin ON shopify_master_data (amazon_asin)"))
    if not _index_exists(bind, "ix_shopify_master_data_myntra_style_id"):
        op.execute(sa.text("CREATE INDEX ix_shopify_master_data_myntra_style_id ON shopify_master_data (myntra_style_id)"))
    if not _index_exists(bind, "ix_shopify_master_data_myntra_sku"):
        op.execute(sa.text("CREATE INDEX ix_shopify_master_data_myntra_sku ON shopify_master_data (myntra_sku)"))


def downgrade() -> None:
    # Keep downgrade non-destructive to avoid accidental data loss in production.
    pass
