"""Add export archival and DB-first normalized tables.

Revision ID: 007_export_archival_pipeline
Revises: 006_rbac_hierarchy
Create Date: 2026-04-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "007_export_archival_pipeline"
down_revision = "006_rbac_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("export_type", sa.String(length=50), nullable=False),
        sa.Column("job_code", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("requested_from", sa.DateTime(), nullable=True),
        sa.Column("requested_to", sa.DateTime(), nullable=True),
        sa.Column("requested_columns", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("csv_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("download_url", sa.Text(), nullable=True),
        sa.Column("file_checksum", sa.String(length=64), nullable=True),
        sa.Column("total_csv_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parsed_entities", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )
    op.create_index("ix_export_jobs_export_type", "export_jobs", ["export_type"])
    op.create_index("ix_export_jobs_job_code", "export_jobs", ["job_code"])
    op.create_index("ix_export_jobs_status", "export_jobs", ["status"])
    op.create_index("ix_export_jobs_type_created", "export_jobs", ["export_type", "created_at"])
    op.create_index("ix_export_jobs_file_checksum", "export_jobs", ["file_checksum"])

    op.create_table(
        "export_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("export_job_id", sa.Integer(), sa.ForeignKey("export_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_key", sa.String(length=180), nullable=True),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("export_job_id", "row_number", name="uq_export_rows_job_row_number"),
    )
    op.create_index("ix_export_rows_export_job_id", "export_rows", ["export_job_id"])
    op.create_index("ix_export_rows_entity_type", "export_rows", ["entity_type"])
    op.create_index("ix_export_rows_entity_key", "export_rows", ["entity_key"])
    op.create_index("ix_export_rows_entity_type_key", "export_rows", ["entity_type", "entity_key"])

    op.create_table(
        "sales_orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(length=120), nullable=False),
        sa.Column("sale_order_item_code", sa.String(length=120), nullable=False),
        sa.Column("channel", sa.String(length=120), nullable=True),
        sa.Column("sku", sa.String(length=120), nullable=True),
        sa.Column("product_name", sa.String(length=255), nullable=True),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selling_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="created"),
        sa.Column("order_date", sa.DateTime(), nullable=True),
        sa.Column("dispatch_date", sa.DateTime(), nullable=True),
        sa.Column("delivery_date", sa.DateTime(), nullable=True),
        sa.Column("cancel_date", sa.DateTime(), nullable=True),
        sa.Column("return_date", sa.DateTime(), nullable=True),
        sa.Column("warehouse", sa.String(length=120), nullable=True),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("customer_city", sa.String(length=120), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", "sale_order_item_code", name="uq_sales_orders_order_item"),
    )
    op.create_index("ix_sales_orders_order_id", "sales_orders", ["order_id"])
    op.create_index("ix_sales_orders_status", "sales_orders", ["status"])
    op.create_index("ix_sales_orders_order_date", "sales_orders", ["order_date"])
    op.create_index("ix_sales_orders_updated_at", "sales_orders", ["updated_at"])
    op.create_index("ix_sales_orders_sku", "sales_orders", ["sku"])

    op.create_table(
        "inventory_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sku", sa.String(length=120), nullable=False),
        sa.Column("warehouse", sa.String(length=120), nullable=False),
        sa.Column("available_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("sku", "warehouse", name="uq_inventory_snapshots_sku_warehouse"),
    )
    op.create_index("ix_inventory_snapshots_sku", "inventory_snapshots", ["sku"])
    op.create_index("ix_inventory_snapshots_warehouse", "inventory_snapshots", ["warehouse"])

    op.create_table(
        "sales_returns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("return_code", sa.String(length=120), nullable=False, unique=True),
        sa.Column("order_id", sa.String(length=120), nullable=False),
        sa.Column("sku", sa.String(length=120), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("return_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("return_status", sa.String(length=40), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sales_returns_return_code", "sales_returns", ["return_code"])
    op.create_index("ix_sales_returns_order_id", "sales_returns", ["order_id"])
    op.create_index("ix_sales_returns_sku", "sales_returns", ["sku"])
    op.create_index("ix_sales_returns_return_status", "sales_returns", ["return_status"])

    op.create_table(
        "sync_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sync_type", sa.String(length=40), nullable=False),
        sa.Column("entity", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sync_logs_sync_type", "sync_logs", ["sync_type"])
    op.create_index("ix_sync_logs_entity", "sync_logs", ["entity"])
    op.create_index("ix_sync_logs_status", "sync_logs", ["status"])
    op.create_index("ix_sync_logs_started_at", "sync_logs", ["started_at"])


def downgrade() -> None:
    op.drop_table("sync_logs")
    op.drop_table("sales_returns")
    op.drop_table("inventory_snapshots")
    op.drop_table("sales_orders")
    op.drop_table("export_rows")
    op.drop_table("export_jobs")
