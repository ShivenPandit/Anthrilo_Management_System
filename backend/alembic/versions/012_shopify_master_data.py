"""Create Shopify master data table.

Revision ID: 012_shopify_master_data
Revises: 011_sync_logs_legacy_compat
Create Date: 2026-04-18 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "012_shopify_master_data"
down_revision = "011_sync_logs_legacy_compat"
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

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS shopify_master_data (
                id SERIAL PRIMARY KEY,
                variant_sku VARCHAR(120) NOT NULL,
                title VARCHAR(255),
                type VARCHAR(120),
                tags TEXT,
                option1_value VARCHAR(120),
                cost_per_item NUMERIC(12, 2),
                created_at TIMESTAMP NOT NULL DEFAULT now(),
                updated_at TIMESTAMP NOT NULL DEFAULT now(),
                CONSTRAINT uq_shopify_master_data_variant_sku UNIQUE (variant_sku)
            )
            """
        )
    )

    if not _index_exists(bind, "ix_shopify_master_data_variant_sku"):
        op.execute(
            sa.text(
                "CREATE INDEX ix_shopify_master_data_variant_sku ON shopify_master_data (variant_sku)"
            )
        )

    if not _index_exists(bind, "ix_shopify_master_data_title"):
        op.execute(
            sa.text(
                "CREATE INDEX ix_shopify_master_data_title ON shopify_master_data (title)"
            )
        )

    if not _index_exists(bind, "ix_shopify_master_data_type"):
        op.execute(
            sa.text(
                "CREATE INDEX ix_shopify_master_data_type ON shopify_master_data (type)"
            )
        )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS shopify_master_data"))
