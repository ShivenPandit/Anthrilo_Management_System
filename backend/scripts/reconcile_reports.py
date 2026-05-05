#!/usr/bin/env python3
"""
Reconciliation Analysis: Production Report vs Sales Report
Identifies the root cause of quantity differences
"""
from datetime import datetime, date, timedelta, timezone
from app.db.session import SessionLocal
from app.db.export_models import SalesOrderRecord, ShopifyMasterData, InventorySnapshotRecord
from sqlalchemy import func, and_, or_

db = SessionLocal()

# Date range from the reports
start_date = date(2026, 4, 5)
end_date = date(2026, 5, 5)
ist = timezone(timedelta(hours=5, minutes=30))
start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=ist).astimezone(timezone.utc)
end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time()).replace(tzinfo=ist).astimezone(timezone.utc)

EXCLUDED_STATUSES = {
    "CANCELLED", "CANCELED", "RETURNED", "REFUNDED",
    "FAILED", "UNFULFILLABLE", "ERROR", "PENDING_VERIFICATION",
}

print("="*80)
print("RECONCILIATION ANALYSIS: Sales vs Production Report")
print("="*80)
print(f"\nDate Range: {start_date} to {end_date}\n")

# 1. Total sales quantity (all SKUs)
total_sales_qty = db.query(func.sum(SalesOrderRecord.qty)).filter(
    SalesOrderRecord.order_date >= start_dt,
    SalesOrderRecord.order_date < end_dt,
    SalesOrderRecord.status.notin_(EXCLUDED_STATUSES),
    SalesOrderRecord.sku.isnot(None),
    SalesOrderRecord.sku != ""
).scalar() or 0
print(f"1. TOTAL SALES QUANTITY (DB): {int(total_sales_qty)} units")

# 2. Sales quantity by bundle status
bundle_sales = db.query(func.sum(SalesOrderRecord.qty)).filter(
    SalesOrderRecord.order_date >= start_dt,
    SalesOrderRecord.order_date < end_dt,
    SalesOrderRecord.status.notin_(EXCLUDED_STATUSES),
    SalesOrderRecord.sku.isnot(None),
    SalesOrderRecord.sku != "",
    or_(
        SalesOrderRecord.item_type_size.ilike('%bundle%'),
        SalesOrderRecord.item_type_size.ilike('%combo%'),
        SalesOrderRecord.item_type_size.ilike('%set%'),
    )
).scalar() or 0

simple_sales = total_sales_qty - bundle_sales
print(f"   - Simple/Single SKU sales: {int(simple_sales)} units")
print(f"   - Bundle/Combo sales: {int(bundle_sales)} units")

# 3. Unique SKUs in sales
unique_skus_sales = db.query(func.count(func.distinct(SalesOrderRecord.sku))).filter(
    SalesOrderRecord.order_date >= start_dt,
    SalesOrderRecord.order_date < end_dt,
    SalesOrderRecord.status.notin_(EXCLUDED_STATUSES),
    SalesOrderRecord.sku.isnot(None),
    SalesOrderRecord.sku != ""
).scalar() or 0
print(f"\n2. UNIQUE SKUS IN SALES (DB): {unique_skus_sales}")

# 4. Master data stats
master_total = db.query(func.count(ShopifyMasterData.id)).scalar() or 0
print(f"\n3. MASTER DATA STATS:")
print(f"   - Total master SKUs: {master_total}")

# 5. Overlap: SKUs in both sales and master
overlap = db.query(func.count(func.distinct(SalesOrderRecord.sku))).filter(
    SalesOrderRecord.order_date >= start_dt,
    SalesOrderRecord.order_date < end_dt,
    SalesOrderRecord.status.notin_(EXCLUDED_STATUSES),
    SalesOrderRecord.sku.isnot(None),
    SalesOrderRecord.sku != ""
).join(
    ShopifyMasterData,
    func.upper(func.trim(SalesOrderRecord.sku)) == func.upper(func.trim(ShopifyMasterData.variant_sku))
).scalar() or 0
print(f"   - SKUs in both sales + master: {overlap}")
print(f"   - Legacy/missing SKUs (sales only): {unique_skus_sales - overlap}")

# 6. Sales quantity for master-matched SKUs only
master_matched_sales = db.query(func.sum(SalesOrderRecord.qty)).filter(
    SalesOrderRecord.order_date >= start_dt,
    SalesOrderRecord.order_date < end_dt,
    SalesOrderRecord.status.notin_(EXCLUDED_STATUSES),
    SalesOrderRecord.sku.isnot(None),
    SalesOrderRecord.sku != ""
).join(
    ShopifyMasterData,
    func.upper(func.trim(SalesOrderRecord.sku)) == func.upper(func.trim(ShopifyMasterData.variant_sku))
).scalar() or 0
print(f"\n4. SALES QUANTITY (MASTER-MATCHED SKUS ONLY): {int(master_matched_sales)} units")

# 7. Sales quantity from legacy/non-master SKUs
legacy_sales = total_sales_qty - master_matched_sales
print(f"   - From current master SKUs: {int(master_matched_sales)} units")
print(f"   - From legacy/missing SKUs: {int(legacy_sales)} units")

# 8. Production report says 6,768 for date range 2026-04-04 to 2026-05-05
# Let's recalculate with their exact date range
prod_start = date(2026, 4, 4)
prod_end = date(2026, 5, 5)
prod_start_dt = datetime.combine(prod_start, datetime.min.time()).replace(tzinfo=ist).astimezone(timezone.utc)
prod_end_dt = datetime.combine(prod_end + timedelta(days=1), datetime.min.time()).replace(tzinfo=ist).astimezone(timezone.utc)

prod_simple_sales = db.query(func.sum(SalesOrderRecord.qty)).filter(
    SalesOrderRecord.order_date >= prod_start_dt,
    SalesOrderRecord.order_date < prod_end_dt,
    SalesOrderRecord.status.notin_(EXCLUDED_STATUSES),
    SalesOrderRecord.sku.isnot(None),
    SalesOrderRecord.sku != "",
    ~or_(
        SalesOrderRecord.item_type_size.ilike('%bundle%'),
        SalesOrderRecord.item_type_size.ilike('%combo%'),
        SalesOrderRecord.item_type_size.ilike('%set%'),
    )
).join(
    ShopifyMasterData,
    func.upper(func.trim(SalesOrderRecord.sku)) == func.upper(func.trim(ShopifyMasterData.variant_sku))
).scalar() or 0

print(f"\n5. PRODUCTION REPORT ANALYSIS:")
print(f"   - Report date range: 2026-04-04 to 2026-05-05")
print(f"   - Reported total: 6,768 units (single SKUs from master)")
print(f"   - Calculated simple SKU sales (master-matched): {int(prod_simple_sales)} units")
print(f"   - Difference: {int(6768 - prod_simple_sales)} units")

# 9. Check for any status filtering issues
all_sales_unfiltered = db.query(func.sum(SalesOrderRecord.qty)).filter(
    SalesOrderRecord.order_date >= start_dt,
    SalesOrderRecord.order_date < end_dt,
    SalesOrderRecord.sku.isnot(None),
    SalesOrderRecord.sku != ""
).scalar() or 0

print(f"\n6. STATUS FILTERING CHECK:")
print(f"   - Total sales (unfiltered): {int(all_sales_unfiltered)} units")
print(f"   - Excluded statuses total: {int(all_sales_unfiltered - total_sales_qty)} units")

# 10. Sample of top SKUs by sales volume
print(f"\n7. TOP 10 SKUS BY SALES VOLUME:")
top_skus = db.query(
    SalesOrderRecord.sku,
    func.sum(SalesOrderRecord.qty).label('qty'),
    func.count(SalesOrderRecord.id).label('order_lines')
).filter(
    SalesOrderRecord.order_date >= start_dt,
    SalesOrderRecord.order_date < end_dt,
    SalesOrderRecord.status.notin_(EXCLUDED_STATUSES),
    SalesOrderRecord.sku.isnot(None),
    SalesOrderRecord.sku != ""
).group_by(SalesOrderRecord.sku).order_by(func.sum(SalesOrderRecord.qty).desc()).limit(10).all()

for sku, qty, lines in top_skus:
    in_master = db.query(ShopifyMasterData).filter(
        func.upper(func.trim(ShopifyMasterData.variant_sku)) == func.upper(func.trim(sku))
    ).first()
    status = "✓ IN MASTER" if in_master else "✗ LEGACY/MISSING"
    print(f"   {sku}: {int(qty)} units ({int(lines)} order lines) - {status}")

# 11. Check if there are duplicate/multi-line orders (one order, many items)
print(f"\n8. ORDER STRUCTURE ANALYSIS:")
total_order_ids = db.query(func.count(func.distinct(SalesOrderRecord.order_id))).filter(
    SalesOrderRecord.order_date >= start_dt,
    SalesOrderRecord.order_date < end_dt,
    SalesOrderRecord.status.notin_(EXCLUDED_STATUSES),
    SalesOrderRecord.sku.isnot(None),
    SalesOrderRecord.sku != ""
).scalar() or 0

total_items = db.query(func.count(SalesOrderRecord.id)).filter(
    SalesOrderRecord.order_date >= start_dt,
    SalesOrderRecord.order_date < end_dt,
    SalesOrderRecord.status.notin_(EXCLUDED_STATUSES),
    SalesOrderRecord.sku.isnot(None),
    SalesOrderRecord.sku != ""
).scalar() or 0

print(f"   - Total orders: {int(total_order_ids)}")
print(f"   - Total order items: {int(total_items)}")
print(f"   - Avg items per order: {round(total_items / max(1, total_order_ids), 2)}")

db.close()
print("\n" + "="*80)
print("\nKEY FINDINGS:")
print("="*80)
print(f"• Total sales quantity in DB: {int(total_sales_qty)} units")
print(f"• Of which from current master SKUs: {int(master_matched_sales)} units")
print(f"• Of which from legacy/old SKUs: {int(legacy_sales)} units")
print(f"• Production report shows: 6,768 units (master-matched single SKUs only)")
print(f"• Sales export shows: ~38,285 units (transaction-level, includes legacy + bundles)")
print(f"\nReason for huge difference:")
print(f"  1. Master catalog has only {master_total} current SKUs")
print(f"  2. Sales DB has {unique_skus_sales} unique SKU codes across all time")
print(f"  3. Only {overlap} SKUs overlap between the two")
print(f"  4. Production report filters for: single SKUs + current master + date range")
print(f"  5. Sales export includes: ALL transactions + legacy SKUs + bundles")
