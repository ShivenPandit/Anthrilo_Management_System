#!/usr/bin/env python3
"""Import Shopify Master Data from CSV into the database.

Workflow:
- Backup existing `shopify_master_data` to `shopify_master_data_backup.csv` in repo root
- Truncate `shopify_master_data`
- Read CSV file from repo root named exactly: "Shopify Master Data .csv"
- Bulk insert rows mapping headers to model columns using positional/header mapping logic

Run with: `python backend/scripts/import_shopify_master_data.py`
"""
import csv
import os
import sys
from decimal import Decimal, InvalidOperation
from typing import Dict

from app.db.session import SessionLocal
from app.db.export_models import ShopifyMasterData

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CSV_CANDIDATES = ["ShopifyMasterData.csv", "Shopify Master Data .csv"]
CSV_PATH = next((os.path.join(ROOT, name) for name in CSV_CANDIDATES if os.path.exists(
    os.path.join(ROOT, name))), os.path.join(ROOT, CSV_CANDIDATES[0]))
BACKUP_PATH = os.path.join(ROOT, "shopify_master_data_backup.csv")


def _clean(value, upper=False):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"N/A", "#N/A", "NA", "NULL", "NONE", "-"}:
        return None
    return text.upper() if upper else text


def _to_decimal(value):
    value = _clean(value)
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def backup_existing(db):
    rows = db.query(ShopifyMasterData).all()
    if not rows:
        print("No existing ShopifyMasterData rows to backup.")
        return
    keys = [c.name for c in ShopifyMasterData.__table__.columns]
    with open(BACKUP_PATH, "w", newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=keys)
        writer.writeheader()
        for r in rows:
            row = {k: getattr(r, k) for k in keys}
            writer.writerow(row)
    print(f"Backed up {len(rows)} rows to {BACKUP_PATH}")


def truncate_table(db):
    deleted = db.query(ShopifyMasterData).delete(synchronize_session=False)
    db.commit()
    print(f"Truncated ShopifyMasterData, deleted {deleted} rows")


def read_csv(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding='utf-8-sig', newline='') as fh:
        reader = csv.DictReader(fh)
        rows = [r for r in reader]
    print(f"Read {len(rows)} rows from {path}")
    return rows


def bulk_insert(db, rows: list[Dict[str, str]]):
    mapped = []
    seen = set()
    for r in rows:
        sku = _clean(r.get('SKU'))
        if not sku:
            continue
        sku_key = sku.lower()
        if sku_key in seen:
            continue
        seen.add(sku_key)
        mapped.append(
            {
                "variant_sku": sku,
                "style_code": _clean(r.get("STYLE CODE")),
                "title": _clean(r.get("NAME")),
                "type": _clean(r.get("TYPE")),
                "gender": _clean(r.get("GENDER")),
                "tags": _clean(r.get("TAG")),
                "size": _clean(r.get("SIZE")),
                "collection": _clean(r.get("COLLECTION")),
                "subtype": _clean(r.get("SUBTYPE")),
                "season": _clean(r.get("SEASON")),
                "fabric_type": _clean(r.get("FABRIC TYPE"), upper=True),
                "print_name": _clean(r.get("PRINT"), upper=True),
                "net_weight": _clean(r.get("NET WEIGHT")),
                "buffer": _clean(r.get("BUFFER")),
                "production_time": _clean(r.get("BUFFER")),
                "simple_bundle": _clean(r.get("SIMPLE/BUNDLE")),
                "mrp": _to_decimal(r.get("MRP")),
                "gross_weights_1": _clean(r.get("LIFECYCLE")),
                "garment_1": _clean(r.get("SUMMER FACTOR")),
                "gross_weights_2": _clean(r.get("WINTER FACTOR")),
                "garment_2": _clean(r.get("STYLE FACTOR")),
                "amazon_asin": _clean(r.get("LEAD TIME")),
                "cost_per_item": _to_decimal(r.get("MRP")),
            }
        )
    if not mapped:
        print("No valid rows to insert after normalization.")
        return 0
    db.bulk_insert_mappings(ShopifyMasterData, mapped)
    db.commit()
    return len(mapped)


def main():
    print("Starting Shopify master data import")
    if not os.path.exists(CSV_PATH):
        print(f"CSV file not found at {CSV_PATH}")
        sys.exit(1)

    db = SessionLocal()
    try:
        backup_existing(db)
        truncate_table(db)
        rows = read_csv(CSV_PATH)
        inserted = bulk_insert(db, rows)
        print(f"Inserted {inserted} rows into shopify_master_data")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    main()
