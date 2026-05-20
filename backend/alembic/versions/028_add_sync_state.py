"""Add sync_state table for recovery tracking.

Revision ID: 028_add_sync_state
Revises: 4ee7c3339ab0
Create Date: 2026-05-20
"""

from alembic import op
import sqlalchemy as sa


revision = "028_add_sync_state"
down_revision = "4ee7c3339ab0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity", sa.String(length=50), nullable=False),
        sa.Column("last_successful_sync", sa.DateTime(), nullable=True),
        sa.Column("last_full_sync", sa.DateTime(), nullable=True),
        sa.Column("sync_status", sa.String(length=32), nullable=False, server_default="idle"),
        sa.Column("sync_duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rows_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recovery_mode", sa.String(length=32), nullable=True),
        sa.Column("recovery_total_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recovery_completed_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recovery_current_chunk", sa.String(length=120), nullable=True),
        sa.Column("recovery_started_at", sa.DateTime(), nullable=True),
        sa.Column("recovery_last_chunk_at", sa.DateTime(), nullable=True),
        sa.Column("recovery_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recovery_next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sync_state_entity", "sync_state", ["entity"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sync_state_entity", table_name="sync_state")
    op.drop_table("sync_state")
