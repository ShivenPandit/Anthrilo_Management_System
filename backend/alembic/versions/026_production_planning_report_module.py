"""Add production planning report and history tables.

Revision ID: 026_prod_planning_report
Revises: 025_shopify_size_buffer
Create Date: 2026-05-08
"""

from alembic import op
import sqlalchemy as sa


revision = "026_prod_planning_report"
down_revision = "025_shopify_size_buffer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_planning_reports",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("sku", sa.String(length=120), nullable=False),
        sa.Column("style_code", sa.String(length=120), nullable=True),
        sa.Column("cutting_plan", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cutting", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stitching", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("finishing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("sku", name="uq_production_planning_reports_sku"),
    )
    op.create_index("ix_production_planning_reports_sku", "production_planning_reports", ["sku"], unique=False)
    op.create_index("ix_production_planning_reports_updated_at", "production_planning_reports", ["updated_at"], unique=False)

    op.create_table(
        "production_planning_history",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("sku", sa.String(length=120), nullable=False),
        sa.Column("old_cutting_plan", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_cutting_plan", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("old_cutting", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_cutting", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("old_stitching", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_stitching", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("old_finishing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_finishing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_quantity_difference", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("update_source", sa.String(length=20), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_production_planning_history_sku", "production_planning_history", ["sku"], unique=False)
    op.create_index("ix_production_planning_history_updated_at", "production_planning_history", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_production_planning_history_updated_at", table_name="production_planning_history")
    op.drop_index("ix_production_planning_history_sku", table_name="production_planning_history")
    op.drop_table("production_planning_history")

    op.drop_index("ix_production_planning_reports_updated_at", table_name="production_planning_reports")
    op.drop_index("ix_production_planning_reports_sku", table_name="production_planning_reports")
    op.drop_table("production_planning_reports")
