"""Extend normalized tables for wider Unicommerce CSV coverage.

Backward-compatible additive migration:
- keeps existing keys/constraints
- adds selected structured columns
- adds extra_fields JSONB for complete normalized key-value coverage
"""

from alembic import op


revision = "022_uc_export_cols"
down_revision = "021_order_date_guard_2022"
branch_labels = None
depends_on = None


def _add_if_missing(table: str, column: str, sql_type: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name='{table}' AND column_name='{column}'
          ) THEN
            ALTER TABLE {table} ADD COLUMN {column} {sql_type};
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    # Ensure raw backup JSON columns exist
    _add_if_missing("sales_orders", "raw_data", "JSONB")
    _add_if_missing("sales_returns", "raw_data", "JSONB")
    _add_if_missing("inventory_snapshots", "raw_data", "JSONB")

    # Full-row normalized key/value map (snake_case keys) for complete CSV compatibility
    _add_if_missing("sales_orders", "extra_fields", "JSONB")
    _add_if_missing("sales_returns", "extra_fields", "JSONB")
    _add_if_missing("inventory_snapshots", "extra_fields", "JSONB")

    # Selected high-value missing sales columns
    for col in [
        "display_order_code",
        "invoice_code",
        "invoice_created",
        "sale_order_item_status",
        "shipping_provider",
        "tracking_number",
        "payment_instrument",
        "currency",
        "currency_conversion_rate",
        "total_price",
        "mrp",
        "cost_price",
        "subtotal",
        "tax_percent",
        "tax_value",
        "shipping_charges",
        "shipping_method_charges",
        "cod_service_charges",
        "channel_product_id",
        "item_type_name",
        "item_type_color",
        "item_type_size",
        "item_type_brand",
        "hsn_code",
        "facility",
        "bundle_sku_code_number",
        "seller_sku_code",
        "item_type_ean",
        "parent_sale_order_code",
    ]:
        _add_if_missing("sales_orders", col, "TEXT")

    # Selected high-value missing return columns
    for col in [
        "invoice_number",
        "channel_entry",
        "product_name",
        "unit_price",
        "currency",
        "sales",
        "cgst",
        "sgst",
        "igst",
        "utgst",
        "cess",
        "dispatch_or_cancellation_date",
        "customer_gstin",
        "channel_party_gstin",
        "product_hsn_code",
        "return_type",
    ]:
        _add_if_missing("sales_returns", col, "TEXT")

    # Selected high-value missing inventory snapshot columns
    for col in [
        "facility",
        "item_type_name",
        "ean",
        "upc",
        "isbn",
        "color",
        "size",
        "brand",
        "category_name",
        "open_sale",
        "bad_inventory",
        "putaway_pending",
        "pending_inventory_assessment",
        "open_purchase",
        "enabled",
        "source_updated_at",
        "cost_price_csv",
    ]:
        _add_if_missing("inventory_snapshots", col, "TEXT")


def downgrade() -> None:
    # Keep downgrade intentionally no-op to avoid risky destructive drops in production.
    pass

