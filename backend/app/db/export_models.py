"""Models for Unicommerce export archival and DB-first normalized reads."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id = Column(Integer, primary_key=True, index=True)
    export_type = Column(String(50), nullable=False, index=True)
    job_code = Column(String(120), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="running", index=True)

    requested_from = Column(DateTime, nullable=True, index=True)
    requested_to = Column(DateTime, nullable=True, index=True)

    requested_columns = Column(JSONB, nullable=True)
    csv_headers = Column(JSONB, nullable=True)

    download_url = Column(Text, nullable=True)
    file_checksum = Column(String(64), nullable=True, index=True)

    total_csv_rows = Column(Integer, nullable=False, default=0)
    parsed_entities = Column(Integer, nullable=False, default=0)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_export_jobs_type_created", "export_type", "created_at"),
    )


class ExportRow(Base):
    __tablename__ = "export_rows"

    id = Column(Integer, primary_key=True, index=True)
    export_job_id = Column(Integer, ForeignKey("export_jobs.id", ondelete="CASCADE"), nullable=False, index=True)

    row_number = Column(Integer, nullable=False)
    entity_type = Column(String(40), nullable=False, index=True)
    entity_key = Column(String(180), nullable=True, index=True)

    row_hash = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    partition_month = Column(
        Date,
        nullable=False,
        default=lambda: datetime.utcnow().date().replace(day=1),
        index=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "export_job_id",
            "row_number",
            "partition_month",
            name="uq_export_rows_job_row_number_month",
        ),
        Index("ix_export_rows_entity_type_key", "entity_type", "entity_key"),
        Index("ix_export_rows_partition_month", "partition_month"),
    )


class SalesOrderRecord(Base):
    __tablename__ = "sales_orders"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String(120), nullable=False, index=True)
    sale_order_item_code = Column(String(120), nullable=False)

    channel = Column(String(120), nullable=True, index=True)
    sku = Column(String(120), nullable=True, index=True)
    product_name = Column(String(255), nullable=True)

    qty = Column(Integer, nullable=False, default=0)
    selling_price = Column(Numeric(12, 2), nullable=False, default=0)

    status = Column(String(40), nullable=False, default="created", index=True)
    order_date = Column(DateTime, nullable=True, index=True)
    dispatch_date = Column(DateTime, nullable=True)
    delivery_date = Column(DateTime, nullable=True)
    cancel_date = Column(DateTime, nullable=True)
    return_date = Column(DateTime, nullable=True)

    warehouse = Column(String(120), nullable=True)
    customer_name = Column(String(255), nullable=True)
    customer_city = Column(String(120), nullable=True)

    raw_data = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)
    partition_month = Column(
        Date,
        nullable=False,
        default=lambda: datetime.utcnow().date().replace(day=1),
        index=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "sale_order_item_code",
            "partition_month",
            name="uq_sales_orders_order_item_month",
        ),
        Index("ix_sales_orders_order_id", "order_id"),
        Index("ix_sales_orders_status", "status"),
        Index("ix_sales_orders_order_date", "order_date"),
        Index("ix_sales_orders_updated_at", "updated_at"),
        Index("ix_sales_orders_sku", "sku"),
        Index("ix_sales_orders_partition_month", "partition_month"),
    )


class InventorySnapshotRecord(Base):
    __tablename__ = "inventory_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(120), nullable=False, index=True)
    warehouse = Column(String(120), nullable=False, index=True)

    available_qty = Column(Integer, nullable=False, default=0)
    reserved_qty = Column(Integer, nullable=False, default=0)
    blocked_qty = Column(Integer, nullable=False, default=0)

    raw_data = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("sku", "warehouse", name="uq_inventory_snapshots_sku_warehouse"),
        Index("ix_inventory_snapshots_sku", "sku"),
        Index("ix_inventory_snapshots_warehouse", "warehouse"),
    )


class SalesReturnRecord(Base):
    __tablename__ = "sales_returns"

    id = Column(Integer, primary_key=True, index=True)
    return_code = Column(String(120), nullable=False, unique=True, index=True)

    order_id = Column(String(120), nullable=False, index=True)
    sku = Column(String(120), nullable=True, index=True)

    reason = Column(String(255), nullable=True)
    return_qty = Column(Integer, nullable=False, default=0)
    refund_amount = Column(Numeric(12, 2), nullable=False, default=0)
    return_status = Column(String(40), nullable=True, index=True)

    raw_data = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    sync_type = Column(String(40), nullable=False, index=True)
    entity = Column(String(40), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="running", index=True)

    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    processed_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)

    fallback_used = Column(Boolean, nullable=False, default=False)

    error_message = Column(Text, nullable=True)
    details = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
