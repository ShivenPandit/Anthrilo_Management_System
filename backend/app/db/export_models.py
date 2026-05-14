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
    discount = Column(Numeric(12, 2), nullable=False, default=0)
    tax = Column(Numeric(12, 2), nullable=False, default=0)
    refund = Column(Numeric(12, 2), nullable=False, default=0)
    category = Column(String(120), nullable=True, index=True)

    status = Column(String(40), nullable=False, default="created", index=True)
    # CRITICAL: order_date is the BUSINESS EVENT timestamp (when customer placed order), NOT sync timestamp
    # NEVER set this to created_at or synced_at — period queries depend on order_date for correct bucketing
    # If wrong, historical data will appear in wrong date ranges (e.g., April 2026 orders show as Sept 2023)
    order_date = Column(DateTime, nullable=True, index=True)
    dispatch_date = Column(DateTime, nullable=True)
    delivery_date = Column(DateTime, nullable=True)
    cancel_date = Column(DateTime, nullable=True)
    return_date = Column(DateTime, nullable=True)

    warehouse = Column(String(120), nullable=True)
    customer_name = Column(String(255), nullable=True)
    customer_city = Column(String(120), nullable=True)

    raw_data = Column(JSONB, nullable=True)
    extra_fields = Column(JSONB, nullable=True)

    # Extended CSV compatibility columns (additive/backward-compatible)
    display_order_code = Column(Text, nullable=True)
    invoice_code = Column(Text, nullable=True)
    invoice_created = Column(Text, nullable=True)
    sale_order_item_status = Column(Text, nullable=True)
    shipping_provider = Column(Text, nullable=True)
    tracking_number = Column(Text, nullable=True)
    payment_instrument = Column(Text, nullable=True)
    currency = Column(Text, nullable=True)
    currency_conversion_rate = Column(Text, nullable=True)
    total_price = Column(Text, nullable=True)
    mrp = Column(Text, nullable=True)
    cost_price = Column(Text, nullable=True)
    subtotal = Column(Text, nullable=True)
    tax_percent = Column(Text, nullable=True)
    tax_value = Column(Text, nullable=True)
    shipping_charges = Column(Text, nullable=True)
    shipping_method_charges = Column(Text, nullable=True)
    cod_service_charges = Column(Text, nullable=True)
    channel_product_id = Column(Text, nullable=True)
    item_type_name = Column(Text, nullable=True)
    item_type_color = Column(Text, nullable=True)
    item_type_size = Column(Text, nullable=True)
    item_type_brand = Column(Text, nullable=True)
    hsn_code = Column(Text, nullable=True)
    facility = Column(Text, nullable=True)
    bundle_sku_code_number = Column(Text, nullable=True)
    seller_sku_code = Column(Text, nullable=True)
    item_type_ean = Column(Text, nullable=True)
    parent_sale_order_code = Column(Text, nullable=True)

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
            name="uq_sales_orders_order_item",
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

    facility = Column(Text, nullable=True)
    item_type_name = Column(Text, nullable=True)
    ean = Column(Text, nullable=True)
    upc = Column(Text, nullable=True)
    isbn = Column(Text, nullable=True)
    color = Column(Text, nullable=True)
    size = Column(Text, nullable=True)
    brand = Column(Text, nullable=True)
    category_name = Column(Text, nullable=True)
    open_sale = Column(Text, nullable=True)
    bad_inventory = Column(Text, nullable=True)
    putaway_pending = Column(Text, nullable=True)
    pending_inventory_assessment = Column(Text, nullable=True)
    open_purchase = Column(Text, nullable=True)
    enabled = Column(Text, nullable=True)
    source_updated_at = Column(Text, nullable=True)
    cost_price_csv = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("sku", "warehouse", name="uq_inventory_snapshots_sku_warehouse"),
        Index("ix_inventory_snapshots_sku", "sku"),
        Index("ix_inventory_snapshots_warehouse", "warehouse"),
    )


class FacilityInventorySnapshot(Base):
    """
    Facility-bounded inventory snapshot synced from Unicommerce 'Inventory Snapshot' export.
    This guarantees 100% parity with Unicommerce UI by strictly bounding catalog visibility.
    """
    __tablename__ = "facility_inventory_snapshot"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(120), nullable=False, index=True)
    facility_code = Column(String(120), nullable=False, index=True)
    
    category = Column(Text, nullable=True)
    inventory = Column(Integer, nullable=False, default=0)
    available_inventory = Column(Integer, nullable=False, default=0)
    reserved_inventory = Column(Integer, nullable=False, default=0)
    
    disabled = Column(Boolean, nullable=False, default=False)
    archived = Column(Boolean, nullable=False, default=False)
    
    cost_price = Column(Numeric(12, 2), nullable=True)
    
    snapshot_date = Column(DateTime, nullable=False, index=True)
    raw_data = Column(JSONB, nullable=True)
    synced_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("sku", "facility_code", name="uq_facility_inventory_sku_facility"),
        Index("ix_facility_inventory_snapshot_sku_facility", "sku", "facility_code"),
    )


class ShopifyMasterData(Base):
    __tablename__ = "shopify_master_data"

    id = Column(Integer, primary_key=True, index=True)
    variant_sku = Column(String(120), nullable=False, unique=True, index=True)
    style_code = Column(String(120), nullable=True, index=True)
    title = Column(String(255), nullable=True, index=True)
    type = Column(String(120), nullable=True, index=True)
    gender = Column(String(50), nullable=True, index=True)
    tags = Column(Text, nullable=True)
    size = Column(String(120), nullable=True, index=True)
    option1_value = Column(String(120), nullable=True)
    collection = Column(String(120), nullable=True)
    subtype = Column(String(120), nullable=True)
    season = Column(String(120), nullable=True)
    fabric_type = Column(String(120), nullable=True)
    print_name = Column(String(120), nullable=True)
    net_weight = Column(String(120), nullable=True)
    buffer = Column(String(120), nullable=True)
    production_time = Column(String(120), nullable=True)
    simple_bundle = Column(String(120), nullable=True)
    mrp = Column(Numeric(12, 2), nullable=True)
    gross_weights_1 = Column(String(120), nullable=True)
    garment_1 = Column(String(120), nullable=True)
    gross_weights_2 = Column(String(120), nullable=True)
    garment_2 = Column(String(120), nullable=True)
    amazon_asin = Column(String(255), nullable=True, index=True)
    amazon_flex_sku = Column(String(255), nullable=True)
    amazon_fba_sku = Column(String(255), nullable=True)
    amazon_mfn_sku = Column(String(255), nullable=True)
    myntra_style_id = Column(String(120), nullable=True, index=True)
    myntra_sku = Column(String(120), nullable=True, index=True)
    fc = Column(String(120), nullable=True)
    cost_per_item = Column(Numeric(12, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


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

    invoice_number = Column(Text, nullable=True)
    channel_entry = Column(Text, nullable=True)
    channel = Column(String(120), nullable=True, index=True)
    product_name = Column(Text, nullable=True)
    unit_price = Column(Text, nullable=True)
    currency = Column(Text, nullable=True)
    sales = Column(Text, nullable=True)
    cgst = Column(Text, nullable=True)
    sgst = Column(Text, nullable=True)
    igst = Column(Text, nullable=True)
    utgst = Column(Text, nullable=True)
    cess = Column(Text, nullable=True)
    dispatch_or_cancellation_date = Column(Text, nullable=True)
    return_date = Column(Text, nullable=True, index=True)  # "Date" from Tally Return GST export — the actual return event date
    customer_gstin = Column(Text, nullable=True)
    channel_party_gstin = Column(Text, nullable=True)
    product_hsn_code = Column(Text, nullable=True)
    return_type = Column(Text, nullable=True)
    raw_data = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)


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


class SyncAuditLog(Base):
    __tablename__ = "sync_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    sync_time = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    entity = Column(String(40), nullable=False, index=True)
    
    rows_fetched = Column(Integer, nullable=False, default=0)
    rows_inserted = Column(Integer, nullable=False, default=0)
    rows_updated = Column(Integer, nullable=False, default=0)
    duplicates_detected = Column(Integer, nullable=False, default=0)
    missing_rows = Column(Integer, nullable=False, default=0)
    
    coverage_percent = Column(Numeric(5, 2), nullable=True)
    sync_duration = Column(Numeric(10, 2), nullable=False, default=0.0)
    parity_percent = Column(Numeric(5, 2), nullable=True)
    error_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_sync_audit_logs_time", "sync_time"),
        Index("ix_sync_audit_logs_entity", "entity"),
    )
