"""Loosen sales order_date guard for historical backfill (>= 2022-01-01).

This migration allows importing older orders for full historical dataset backfill.
"""

from alembic import op


# New revision identifiers, used by Alembic.
revision = "021_order_date_guard_2022"
down_revision = "020_add_sales_returns_channel"
branch_labels = None
depends_on = None


CHECK_CONSTRAINT_NAME = "ck_sales_orders_order_date_valid"


def upgrade() -> None:
    # Drop the old constraint and recreate with a lower minimum date.
    op.drop_constraint(CHECK_CONSTRAINT_NAME, "sales_orders", type_="check")
    op.create_check_constraint(
        CHECK_CONSTRAINT_NAME,
        "sales_orders",
        "order_date >= TIMESTAMP '2022-01-01 00:00:00'",
    )


def downgrade() -> None:
    op.drop_constraint(CHECK_CONSTRAINT_NAME, "sales_orders", type_="check")
    op.create_check_constraint(
        CHECK_CONSTRAINT_NAME,
        "sales_orders",
        "order_date >= TIMESTAMP '2024-01-01 00:00:00'",
    )

