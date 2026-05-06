# Quick test script to verify sales items include size and bundle fields
from app.services.unicommerce_data_service import get_unicommerce_data_service
from datetime import datetime, timezone, timedelta

svc = get_unicommerce_data_service()
# date range where we previously tested
from_dt = datetime(2026, 4, 5, 0, 0, 0, tzinfo=timezone.utc)
to_dt = datetime(2026, 5, 5, 23, 59, 59, tzinfo=timezone.utc)
res = svc.get_sales_data(period='custom', from_date=from_dt, to_date=to_dt, include_legacy_orders=False)
print('success:', res.get('success'))
items = res.get('orders') or res.get('orders') or []
# orders is aggregated; check raw normalized fetch separately
# Instead, call internal path used by daily report to fetch item_rows
from app.db.session import SessionLocal
from app.db.export_models import SalesOrderRecord
from sqlalchemy import and_

db = SessionLocal()
try:
    rows = db.query(
        SalesOrderRecord.sku,
        SalesOrderRecord.sale_order_item_code,
        SalesOrderRecord.product_name,
        SalesOrderRecord.channel,
        SalesOrderRecord.order_date,
        SalesOrderRecord.created_at,
        SalesOrderRecord.selling_price,
        SalesOrderRecord.status,
        SalesOrderRecord.item_type_size.label('item_type_size'),
        SalesOrderRecord.bundle_sku_code_number.label('bundle_sku_code_number'),
    ).filter(
        and_(
            SalesOrderRecord.order_date.isnot(None),
            SalesOrderRecord.order_date >= from_dt,
            SalesOrderRecord.order_date < to_dt,
        )
    ).limit(5).all()
    for r in rows:
        print(dict(
            sku=r.sku,
            sale_order_item_code=r.sale_order_item_code,
            product_name=r.product_name,
            channel=r.channel,
            order_date=r.order_date.isoformat() if r.order_date else None,
            selling_price=float(r.selling_price or 0),
            item_type_size=getattr(r, 'item_type_size', None),
            bundle_sku_code_number=getattr(r, 'bundle_sku_code_number', None),
        ))
finally:
    db.close()
