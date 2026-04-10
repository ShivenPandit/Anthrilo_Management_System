"""Add synced_orders and sync_status tables

Revision ID: 002
Revises: 001
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = '002_add_sync_tables'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SyncedOrder table - caches Unicommerce order details
    op.create_table(
        'synced_orders',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('order_code', sa.String(100), nullable=False, unique=True),
        sa.Column('status', sa.String(50), nullable=True),
        sa.Column('channel', sa.String(100), nullable=True),
        sa.Column('created_at_uc', sa.DateTime(), nullable=True),
        sa.Column('selling_price', sa.Float(), server_default='0'),
        sa.Column('net_revenue', sa.Float(), server_default='0'),
        sa.Column('discount', sa.Float(), server_default='0'),
        sa.Column('tax', sa.Float(), server_default='0'),
        sa.Column('refund', sa.Float(), server_default='0'),
        sa.Column('item_count', sa.Integer(), server_default='0'),
        sa.Column('include_in_revenue', sa.Boolean(), server_default='true'),
        sa.Column('excluded_reason', sa.String(200), nullable=True),
        sa.Column('raw_order_data', JSONB(), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_index('ix_synced_orders_order_code', 'synced_orders', ['order_code'])
    op.create_index('ix_synced_orders_status', 'synced_orders', ['status'])
    op.create_index('ix_synced_orders_channel', 'synced_orders', ['channel'])
    op.create_index('ix_synced_orders_created_at_uc', 'synced_orders', ['created_at_uc'])
    op.create_index('ix_synced_orders_channel_created', 'synced_orders', ['channel', 'created_at_uc'])
    op.create_index('ix_synced_orders_status_created', 'synced_orders', ['status', 'created_at_uc'])
    op.create_index('ix_synced_orders_synced_at', 'synced_orders', ['synced_at'])

    # SyncStatus table - tracks background sync state
    op.create_table(
        'sync_status',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('period', sa.String(50), nullable=False, unique=True),
        sa.Column('from_date', sa.DateTime(), nullable=False),
        sa.Column('to_date', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('total_expected', sa.Integer(), server_default='0'),
        sa.Column('total_synced', sa.Integer(), server_default='0'),
        sa.Column('total_failed', sa.Integer(), server_default='0'),
        sa.Column('failed_codes', JSONB(), nullable=True),
        sa.Column('last_synced_code', sa.String(100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_index('ix_sync_status_period', 'sync_status', ['period'])


def downgrade() -> None:
    op.drop_table('sync_status')
    op.drop_table('synced_orders')
