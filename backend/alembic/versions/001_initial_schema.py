"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2026-01-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('username', sa.String(100), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('is_superuser', sa.Boolean(), default=False, nullable=False),
        sa.Column('role', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username')
    )
    op.create_index('ix_users_email', 'users', ['email'])
    
    # Yarn Management
    op.create_table(
        'yarns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('yarn_type', sa.String(100), nullable=False),
        sa.Column('yarn_count', sa.String(50), nullable=False),
        sa.Column('composition', sa.String(255), nullable=False),
        sa.Column('percentage_breakdown', postgresql.JSONB(), nullable=True),
        sa.Column('supplier', sa.String(255), nullable=True),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('stock_quantity', sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column('unit', sa.String(20), nullable=False, default='kg'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Process Management
    op.create_table(
        'processes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('process_type', sa.String(50), nullable=False),  # KNITTING, DYEING, FINISHING, PRINTING
        sa.Column('process_name', sa.String(100), nullable=False),
        sa.Column('process_rate', sa.Numeric(10, 2), nullable=False),
        sa.Column('rate_unit', sa.String(20), nullable=False, default='per_kg'),
        sa.Column('vendor', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Fabric Management
    op.create_table(
        'fabrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fabric_type', sa.String(50), nullable=False),  # JERSEY, TERRY, FLEECE
        sa.Column('subtype', sa.String(100), nullable=False),
        sa.Column('gsm', sa.Integer(), nullable=False),
        sa.Column('composition', sa.String(255), nullable=False),
        sa.Column('width', sa.Numeric(8, 2), nullable=True),
        sa.Column('color', sa.String(100), nullable=True),
        sa.Column('stock_quantity', sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column('unit', sa.String(20), nullable=False, default='kg'),
        sa.Column('cost_per_unit', sa.Numeric(10, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fabrics_fabric_type', 'fabrics', ['fabric_type'])
    
    # Garment Master Data
    op.create_table(
        'garments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('style_sku', sa.String(100), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('sub_category', sa.String(100), nullable=True),
        sa.Column('sizes', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('gross_weight_per_size', postgresql.JSONB(), nullable=True),
        sa.Column('mrp', sa.Numeric(10, 2), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('style_sku')
    )
    op.create_index('ix_garments_style_sku', 'garments', ['style_sku'])
    op.create_index('ix_garments_category', 'garments', ['category'])
    
    # Inventory Management
    op.create_table(
        'inventory',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('garment_id', sa.Integer(), nullable=False),
        sa.Column('size', sa.String(20), nullable=False),
        sa.Column('good_stock', sa.Integer(), nullable=False, default=0),
        sa.Column('virtual_stock', sa.Integer(), nullable=False, default=0),
        sa.Column('warehouse_location', sa.String(100), nullable=True),
        sa.Column('last_updated', sa.DateTime(), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['garment_id'], ['garments.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('garment_id', 'size', name='uix_garment_size')
    )
    op.create_index('ix_inventory_garment_id', 'inventory', ['garment_id'])
    
    # Panels (Sales Channels)
    op.create_table(
        'panels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('panel_name', sa.String(255), nullable=False),
        sa.Column('panel_type', sa.String(50), nullable=False),  # e-commerce, retail, wholesale
        sa.Column('contact_person', sa.String(255), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Sales Transactions
    op.create_table(
        'sales',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('garment_id', sa.Integer(), nullable=False),
        sa.Column('panel_id', sa.Integer(), nullable=False),
        sa.Column('size', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('discount_percentage', sa.Numeric(5, 2), nullable=False, default=0),
        sa.Column('total_amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('is_return', sa.Boolean(), default=False, nullable=False),
        sa.Column('invoice_number', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['garment_id'], ['garments.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['panel_id'], ['panels.id'], ondelete='RESTRICT')
    )
    op.create_index('ix_sales_transaction_date', 'sales', ['transaction_date'])
    op.create_index('ix_sales_panel_id', 'sales', ['panel_id'])
    
    # Production Planning
    op.create_table(
        'production_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_name', sa.String(255), nullable=False),
        sa.Column('garment_id', sa.Integer(), nullable=False),
        sa.Column('planned_quantity', sa.Integer(), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, default='PLANNED'),  # PLANNED, IN_PROGRESS, COMPLETED
        sa.Column('fabric_requirement', sa.Numeric(12, 2), nullable=True),
        sa.Column('yarn_requirement', sa.Numeric(12, 2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['garment_id'], ['garments.id'], ondelete='RESTRICT')
    )
    
    # Production Activities
    op.create_table(
        'production_activities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('production_plan_id', sa.Integer(), nullable=False),
        sa.Column('activity_type', sa.String(50), nullable=False),  # FABRIC_ISSUE, CUTTING, STITCHING, FINISHING
        sa.Column('activity_date', sa.Date(), nullable=False),
        sa.Column('quantity', sa.Numeric(12, 2), nullable=False),
        sa.Column('gross_weight_calculated', sa.Numeric(12, 2), nullable=True),
        sa.Column('gross_weight_actual', sa.Numeric(12, 2), nullable=True),
        sa.Column('variance', sa.Numeric(12, 2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['production_plan_id'], ['production_plans.id'], ondelete='CASCADE')
    )
    
    # Discounts Management
    op.create_table(
        'discounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('discount_name', sa.String(255), nullable=False),
        sa.Column('discount_type', sa.String(50), nullable=False),  # PERCENTAGE, FIXED_AMOUNT, REBATE
        sa.Column('discount_value', sa.Numeric(10, 2), nullable=False),
        sa.Column('applicable_to', sa.String(50), nullable=False),  # PANEL, GARMENT, CATEGORY
        sa.Column('panel_id', sa.Integer(), nullable=True),
        sa.Column('garment_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('valid_to', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['panel_id'], ['panels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['garment_id'], ['garments.id'], ondelete='CASCADE')
    )
    
    # Paid Ads Tracking
    op.create_table(
        'paid_ads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ad_date', sa.Date(), nullable=False),
        sa.Column('panel_id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(100), nullable=False),  # Google Ads, Facebook, Instagram, etc.
        sa.Column('campaign_name', sa.String(255), nullable=False),
        sa.Column('daily_spend', sa.Numeric(10, 2), nullable=False),
        sa.Column('impressions', sa.Integer(), nullable=True),
        sa.Column('clicks', sa.Integer(), nullable=True),
        sa.Column('conversions', sa.Integer(), nullable=True),
        sa.Column('revenue_generated', sa.Numeric(12, 2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['panel_id'], ['panels.id'], ondelete='CASCADE')
    )
    op.create_index('ix_paid_ads_ad_date', 'paid_ads', ['ad_date'])
    op.create_index('ix_paid_ads_panel_id', 'paid_ads', ['panel_id'])


def downgrade() -> None:
    op.drop_table('paid_ads')
    op.drop_table('discounts')
    op.drop_table('production_activities')
    op.drop_table('production_plans')
    op.drop_table('sales')
    op.drop_table('panels')
    op.drop_table('inventory')
    op.drop_table('garments')
    op.drop_table('fabrics')
    op.drop_table('processes')
    op.drop_table('yarns')
    op.drop_table('users')
