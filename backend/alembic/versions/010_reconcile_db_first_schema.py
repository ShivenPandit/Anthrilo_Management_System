"""Reconcile DB-first schema against legacy drift.

Revision ID: 010_reconcile_db_first_schema
Revises: 009_db_first_read_indexes
Create Date: 2026-04-10 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "010_reconcile_db_first_schema"
down_revision = "009_db_first_read_indexes"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    result = bind.execute(
        sa.text("SELECT to_regclass(:name) IS NOT NULL"),
        {"name": f"public.{table_name}"},
    ).scalar()
    return bool(result)


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    result = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).first()
    return result is not None


def _index_exists(bind, index_name: str) -> bool:
    result = bind.execute(
        sa.text("SELECT to_regclass(:name) IS NOT NULL"),
        {"name": f"public.{index_name}"},
    ).scalar()
    return bool(result)


def _add_column_if_missing(bind, table_name: str, column_name: str, column_sql: str) -> None:
    if not _column_exists(bind, table_name, column_name):
        op.execute(sa.text(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}"))


def _create_index_if_missing(bind, index_name: str, create_sql: str) -> None:
    if not _index_exists(bind, index_name):
        op.execute(sa.text(create_sql))


def _ensure_export_jobs(bind) -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS export_jobs (
                id SERIAL PRIMARY KEY,
                export_type VARCHAR(50) NOT NULL,
                job_code VARCHAR(120),
                status VARCHAR(20) NOT NULL DEFAULT 'running',
                requested_from TIMESTAMP,
                requested_to TIMESTAMP,
                requested_columns JSONB,
                csv_headers JSONB,
                download_url TEXT,
                file_checksum VARCHAR(64),
                total_csv_rows INTEGER NOT NULL DEFAULT 0,
                parsed_entities INTEGER NOT NULL DEFAULT 0,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT now(),
                updated_at TIMESTAMP DEFAULT now()
            )
            """
        )
    )

    _create_index_if_missing(
        bind,
        "ix_export_jobs_export_type",
        "CREATE INDEX ix_export_jobs_export_type ON export_jobs (export_type)",
    )
    _create_index_if_missing(
        bind,
        "ix_export_jobs_job_code",
        "CREATE INDEX ix_export_jobs_job_code ON export_jobs (job_code)",
    )
    _create_index_if_missing(
        bind,
        "ix_export_jobs_status",
        "CREATE INDEX ix_export_jobs_status ON export_jobs (status)",
    )
    _create_index_if_missing(
        bind,
        "ix_export_jobs_type_created",
        "CREATE INDEX ix_export_jobs_type_created ON export_jobs (export_type, created_at)",
    )
    _create_index_if_missing(
        bind,
        "ix_export_jobs_file_checksum",
        "CREATE INDEX ix_export_jobs_file_checksum ON export_jobs (file_checksum)",
    )


def _ensure_export_rows(bind) -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS export_rows (
                id SERIAL PRIMARY KEY,
                export_job_id INTEGER NOT NULL,
                row_number INTEGER NOT NULL,
                entity_type VARCHAR(40) NOT NULL,
                entity_key VARCHAR(180),
                row_hash VARCHAR(64) NOT NULL,
                payload JSONB NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT now(),
                partition_month DATE NOT NULL DEFAULT date_trunc('month', now())::date
            )
            """
        )
    )

    _add_column_if_missing(bind, "export_rows", "export_job_id", "export_job_id INTEGER")
    _add_column_if_missing(bind, "export_rows", "row_number", "row_number INTEGER")
    _add_column_if_missing(bind, "export_rows", "entity_type", "entity_type VARCHAR(40)")
    _add_column_if_missing(bind, "export_rows", "entity_key", "entity_key VARCHAR(180)")
    _add_column_if_missing(bind, "export_rows", "row_hash", "row_hash VARCHAR(64)")
    _add_column_if_missing(bind, "export_rows", "payload", "payload JSONB")
    _add_column_if_missing(bind, "export_rows", "created_at", "created_at TIMESTAMP DEFAULT now()")
    _add_column_if_missing(bind, "export_rows", "partition_month", "partition_month DATE")

    op.execute(
        sa.text(
            """
            UPDATE export_rows
            SET partition_month = date_trunc('month', COALESCE(created_at, now()))::date
            WHERE partition_month IS NULL
            """
        )
    )

    op.execute(sa.text("ALTER TABLE export_rows ALTER COLUMN partition_month SET NOT NULL"))

    op.execute(sa.text("ALTER TABLE export_rows DROP CONSTRAINT IF EXISTS uq_export_rows_job_row_number"))

    op.execute(
        sa.text(
            """
            DELETE FROM export_rows a
            USING export_rows b
            WHERE a.id < b.id
              AND a.export_job_id = b.export_job_id
              AND a.row_number = b.row_number
              AND a.partition_month = b.partition_month
            """
        )
    )

    _create_index_if_missing(
        bind,
        "uq_export_rows_job_row_number_month",
        "CREATE UNIQUE INDEX uq_export_rows_job_row_number_month ON export_rows (export_job_id, row_number, partition_month)",
    )
    _create_index_if_missing(
        bind,
        "ix_export_rows_export_job_id",
        "CREATE INDEX ix_export_rows_export_job_id ON export_rows (export_job_id)",
    )
    _create_index_if_missing(
        bind,
        "ix_export_rows_entity_type",
        "CREATE INDEX ix_export_rows_entity_type ON export_rows (entity_type)",
    )
    _create_index_if_missing(
        bind,
        "ix_export_rows_entity_key",
        "CREATE INDEX ix_export_rows_entity_key ON export_rows (entity_key)",
    )
    _create_index_if_missing(
        bind,
        "ix_export_rows_entity_type_key",
        "CREATE INDEX ix_export_rows_entity_type_key ON export_rows (entity_type, entity_key)",
    )
    _create_index_if_missing(
        bind,
        "ix_export_rows_partition_month",
        "CREATE INDEX ix_export_rows_partition_month ON export_rows (partition_month)",
    )


def _ensure_sales_orders(bind) -> None:
    if not _table_exists(bind, "sales_orders"):
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
            sa.Column("partition_month", sa.Date(), nullable=False),
        )

    _add_column_if_missing(bind, "sales_orders", "sale_order_item_code", "sale_order_item_code VARCHAR(120)")
    _add_column_if_missing(bind, "sales_orders", "partition_month", "partition_month DATE")

    if _column_exists(bind, "sales_orders", "raw_data"):
        op.execute(
            sa.text(
                """
                UPDATE sales_orders
                SET sale_order_item_code = COALESCE(
                    NULLIF(raw_data->>'Sale Order Item Code', ''),
                    NULLIF(raw_data->>'saleOrderItemCode', ''),
                    NULLIF(raw_data->>'soicode', ''),
                    'LEGACY-' || id::text
                )
                WHERE sale_order_item_code IS NULL OR sale_order_item_code = ''
                """
            )
        )

    op.execute(
        sa.text(
            """
            UPDATE sales_orders
            SET sale_order_item_code = 'LEGACY-' || id::text
            WHERE sale_order_item_code IS NULL OR sale_order_item_code = ''
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE sales_orders
            SET partition_month = date_trunc('month', COALESCE(order_date, created_at, now()))::date
            WHERE partition_month IS NULL
            """
        )
    )

    op.execute(sa.text("UPDATE sales_orders SET selling_price = 0 WHERE selling_price IS NULL"))
    op.execute(sa.text("UPDATE sales_orders SET qty = 0 WHERE qty IS NULL"))

    op.execute(sa.text("ALTER TABLE sales_orders ALTER COLUMN sale_order_item_code SET NOT NULL"))
    op.execute(sa.text("ALTER TABLE sales_orders ALTER COLUMN partition_month SET NOT NULL"))
    op.execute(sa.text("ALTER TABLE sales_orders ALTER COLUMN qty SET NOT NULL"))
    op.execute(sa.text("ALTER TABLE sales_orders ALTER COLUMN qty SET DEFAULT 0"))
    op.execute(sa.text("ALTER TABLE sales_orders ALTER COLUMN selling_price SET NOT NULL"))
    op.execute(sa.text("ALTER TABLE sales_orders ALTER COLUMN selling_price SET DEFAULT 0"))

    op.execute(sa.text("ALTER TABLE sales_orders DROP CONSTRAINT IF EXISTS uq_sales_orders_order_id"))
    op.execute(sa.text("ALTER TABLE sales_orders DROP CONSTRAINT IF EXISTS ck_sales_orders_status"))

    _create_index_if_missing(
        bind,
        "uq_sales_orders_order_item_month",
        "CREATE UNIQUE INDEX uq_sales_orders_order_item_month ON sales_orders (order_id, sale_order_item_code, partition_month)",
    )
    _create_index_if_missing(
        bind,
        "ix_sales_orders_order_id",
        "CREATE INDEX ix_sales_orders_order_id ON sales_orders (order_id)",
    )
    _create_index_if_missing(
        bind,
        "ix_sales_orders_status",
        "CREATE INDEX ix_sales_orders_status ON sales_orders (status)",
    )
    _create_index_if_missing(
        bind,
        "ix_sales_orders_order_date",
        "CREATE INDEX ix_sales_orders_order_date ON sales_orders (order_date)",
    )
    _create_index_if_missing(
        bind,
        "ix_sales_orders_updated_at",
        "CREATE INDEX ix_sales_orders_updated_at ON sales_orders (updated_at)",
    )
    _create_index_if_missing(
        bind,
        "ix_sales_orders_sku",
        "CREATE INDEX ix_sales_orders_sku ON sales_orders (sku)",
    )
    _create_index_if_missing(
        bind,
        "ix_sales_orders_partition_month",
        "CREATE INDEX ix_sales_orders_partition_month ON sales_orders (partition_month)",
    )


def _ensure_sync_logs(bind) -> None:
    if not _table_exists(bind, "sync_logs"):
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

    _add_column_if_missing(bind, "sync_logs", "sync_type", "sync_type VARCHAR(40)")
    _add_column_if_missing(bind, "sync_logs", "entity", "entity VARCHAR(40)")
    _add_column_if_missing(bind, "sync_logs", "status", "status VARCHAR(20)")
    _add_column_if_missing(bind, "sync_logs", "started_at", "started_at TIMESTAMP")
    _add_column_if_missing(bind, "sync_logs", "completed_at", "completed_at TIMESTAMP")
    _add_column_if_missing(bind, "sync_logs", "processed_count", "processed_count INTEGER")
    _add_column_if_missing(bind, "sync_logs", "failed_count", "failed_count INTEGER")
    _add_column_if_missing(bind, "sync_logs", "fallback_used", "fallback_used BOOLEAN")
    _add_column_if_missing(bind, "sync_logs", "error_message", "error_message TEXT")
    _add_column_if_missing(bind, "sync_logs", "details", "details JSONB")
    _add_column_if_missing(bind, "sync_logs", "created_at", "created_at TIMESTAMP DEFAULT now()")

    entity_source = "entity_type" if _column_exists(bind, "sync_logs", "entity_type") else "sync_type"
    processed_source = "records_upserted" if _column_exists(bind, "sync_logs", "records_upserted") else "0"
    detail_source = "detail" if _column_exists(bind, "sync_logs", "detail") else "NULL"
    error_source = "error" if _column_exists(bind, "sync_logs", "error") else "NULL"

    op.execute(
        sa.text(
            f"""
            UPDATE sync_logs
            SET entity = COALESCE(NULLIF(entity, ''), NULLIF({entity_source}, ''), 'unknown')
            WHERE entity IS NULL OR entity = ''
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE sync_logs
            SET processed_count = COALESCE(processed_count, {processed_source}, 0)
            WHERE processed_count IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE sync_logs
            SET failed_count = COALESCE(
                failed_count,
                CASE WHEN {error_source} IS NOT NULL THEN 1 ELSE 0 END,
                0
            )
            WHERE failed_count IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE sync_logs
            SET details = COALESCE(details, {detail_source}, '{{}}'::jsonb)
            WHERE details IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE sync_logs
            SET error_message = COALESCE(error_message, {error_source})
            WHERE error_message IS NULL
            """
        )
    )

    op.execute(sa.text("UPDATE sync_logs SET fallback_used = false WHERE fallback_used IS NULL"))
    op.execute(sa.text("UPDATE sync_logs SET status = 'unknown' WHERE status IS NULL OR status = ''"))
    op.execute(sa.text("UPDATE sync_logs SET sync_type = 'unknown' WHERE sync_type IS NULL OR sync_type = ''"))
    op.execute(sa.text("UPDATE sync_logs SET started_at = COALESCE(started_at, created_at, now()) WHERE started_at IS NULL"))

    op.execute(sa.text("ALTER TABLE sync_logs ALTER COLUMN entity SET NOT NULL"))
    op.execute(sa.text("ALTER TABLE sync_logs ALTER COLUMN sync_type SET NOT NULL"))
    op.execute(sa.text("ALTER TABLE sync_logs ALTER COLUMN status SET NOT NULL"))
    op.execute(sa.text("ALTER TABLE sync_logs ALTER COLUMN started_at SET NOT NULL"))
    op.execute(sa.text("ALTER TABLE sync_logs ALTER COLUMN processed_count SET NOT NULL"))
    op.execute(sa.text("ALTER TABLE sync_logs ALTER COLUMN processed_count SET DEFAULT 0"))
    op.execute(sa.text("ALTER TABLE sync_logs ALTER COLUMN failed_count SET NOT NULL"))
    op.execute(sa.text("ALTER TABLE sync_logs ALTER COLUMN failed_count SET DEFAULT 0"))
    op.execute(sa.text("ALTER TABLE sync_logs ALTER COLUMN fallback_used SET NOT NULL"))
    op.execute(sa.text("ALTER TABLE sync_logs ALTER COLUMN fallback_used SET DEFAULT false"))

    _create_index_if_missing(
        bind,
        "ix_sync_logs_sync_type",
        "CREATE INDEX ix_sync_logs_sync_type ON sync_logs (sync_type)",
    )
    _create_index_if_missing(
        bind,
        "ix_sync_logs_entity",
        "CREATE INDEX ix_sync_logs_entity ON sync_logs (entity)",
    )
    _create_index_if_missing(
        bind,
        "ix_sync_logs_status",
        "CREATE INDEX ix_sync_logs_status ON sync_logs (status)",
    )
    _create_index_if_missing(
        bind,
        "ix_sync_logs_started_at",
        "CREATE INDEX ix_sync_logs_started_at ON sync_logs (started_at)",
    )


def _ensure_sales_returns(bind) -> None:
    if not _table_exists(bind, "sales_returns"):
        op.create_table(
            "sales_returns",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("return_code", sa.String(length=120), nullable=False),
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

    _add_column_if_missing(bind, "sales_returns", "return_code", "return_code VARCHAR(120)")

    if _column_exists(bind, "sales_returns", "raw_data"):
        op.execute(
            sa.text(
                """
                UPDATE sales_returns
                SET return_code = left(COALESCE(
                    NULLIF(raw_data->>'rpcode', ''),
                    NULLIF(raw_data->>'RP Code', ''),
                    NULLIF(raw_data->>'returnCode', ''),
                    NULLIF(raw_data->>'Invoice number', ''),
                    NULLIF(raw_data->>'Invoice Code', ''),
                    NULLIF(raw_data->>'invoiceCode', ''),
                    'RET'
                ), 100) || '-' || id::text
                WHERE return_code IS NULL OR return_code = ''
                """
            )
        )

    op.execute(
        sa.text(
            """
            UPDATE sales_returns
            SET return_code = 'RET-' || id::text
            WHERE return_code IS NULL OR return_code = ''
            """
        )
    )

    op.execute(sa.text("ALTER TABLE sales_returns DROP CONSTRAINT IF EXISTS uq_sales_returns_order_sku"))
    op.execute(sa.text("ALTER TABLE sales_returns ALTER COLUMN return_code SET NOT NULL"))

    _create_index_if_missing(
        bind,
        "uq_sales_returns_return_code",
        "CREATE UNIQUE INDEX uq_sales_returns_return_code ON sales_returns (return_code)",
    )
    _create_index_if_missing(
        bind,
        "ix_sales_returns_return_code",
        "CREATE INDEX ix_sales_returns_return_code ON sales_returns (return_code)",
    )
    _create_index_if_missing(
        bind,
        "ix_sales_returns_order_id",
        "CREATE INDEX ix_sales_returns_order_id ON sales_returns (order_id)",
    )
    _create_index_if_missing(
        bind,
        "ix_sales_returns_sku",
        "CREATE INDEX ix_sales_returns_sku ON sales_returns (sku)",
    )
    _create_index_if_missing(
        bind,
        "ix_sales_returns_return_status",
        "CREATE INDEX ix_sales_returns_return_status ON sales_returns (return_status)",
    )


def _ensure_inventory_snapshots(bind) -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS inventory_snapshots (
                id SERIAL PRIMARY KEY,
                sku VARCHAR(120) NOT NULL,
                warehouse VARCHAR(120) NOT NULL,
                available_qty INTEGER NOT NULL DEFAULT 0,
                reserved_qty INTEGER NOT NULL DEFAULT 0,
                blocked_qty INTEGER NOT NULL DEFAULT 0,
                raw_data JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT now(),
                updated_at TIMESTAMP NOT NULL DEFAULT now()
            )
            """
        )
    )

    _create_index_if_missing(
        bind,
        "uq_inventory_snapshots_sku_warehouse",
        "CREATE UNIQUE INDEX uq_inventory_snapshots_sku_warehouse ON inventory_snapshots (sku, warehouse)",
    )
    _create_index_if_missing(
        bind,
        "ix_inventory_snapshots_sku",
        "CREATE INDEX ix_inventory_snapshots_sku ON inventory_snapshots (sku)",
    )
    _create_index_if_missing(
        bind,
        "ix_inventory_snapshots_warehouse",
        "CREATE INDEX ix_inventory_snapshots_warehouse ON inventory_snapshots (warehouse)",
    )


def upgrade() -> None:
    bind = op.get_bind()

    _ensure_export_jobs(bind)
    _ensure_export_rows(bind)
    _ensure_sales_orders(bind)
    _ensure_sync_logs(bind)
    _ensure_sales_returns(bind)
    _ensure_inventory_snapshots(bind)


def downgrade() -> None:
    """No-op downgrade for reconciliation migration."""
