"""Add name, size, and type columns to production planning reports.

Revision ID: 027_add_pp_meta_cols
Revises: 026_prod_planning_report
Create Date: 2026-05-11
"""

from alembic import op
import sqlalchemy as sa


revision = "027_add_pp_meta_cols"
down_revision = "026_prod_planning_report"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("production_planning_reports", sa.Column("name", sa.String(length=255), nullable=True))
    op.add_column("production_planning_reports", sa.Column("size", sa.String(length=50), nullable=True))
    op.add_column("production_planning_reports", sa.Column("type", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("production_planning_reports", "type")
    op.drop_column("production_planning_reports", "size")
    op.drop_column("production_planning_reports", "name")