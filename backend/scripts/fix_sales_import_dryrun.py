#!/usr/bin/env python3
"""Dry-run and corrective re-import for Unicommerce sales export.

Usage (from backend/):
  python scripts/fix_sales_import_dryrun.py --from 2026-05-16 --to 2026-05-21 [--apply]

By default this performs a dry-run: it fetches the export CSV from Unicommerce,
compares order codes against `sales_orders.order_id` for the given business
date window, and prints a summary. Add `--apply` to delete DB rows in the
window and re-import rows from the export CSV (idempotent upsert).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import List, Set

# Ensure backend package root is on sys.path so `import app` works when running
# the script from the repo root or from the backend directory.
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from app.services.unicommerce import get_unicommerce_service
from app.db.session import SessionLocal
from app.db.export_models import SalesOrderRecord


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="from_date", required=True, help="YYYY-MM-DD")
    p.add_argument("--to", dest="to_date", required=True, help="YYYY-MM-DD")
    p.add_argument("--apply", action="store_true", help="Apply changes (delete+reimport)")
    return p.parse_args()


def to_utc_dt(d: str) -> datetime:
    # Interpret input as local date and make UTC range covering whole day
    dt = datetime.fromisoformat(d)
    start = datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(dt.year, dt.month, dt.day, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


async def fetch_export_rows(from_dt: datetime, to_dt: datetime):
    svc = get_unicommerce_service()
    # Use internal export helpers but avoid upstream normalization/upsert
    job_code = await svc._create_export_job(from_dt, to_dt)
    if not job_code:
        raise RuntimeError("Failed to create export job")

    download_url = await svc._poll_export_status(job_code)
    if download_url is None:
        raise RuntimeError("Export job failed or timed out")

    orders, raw_rows, headers = await svc._download_parse_export(download_url, include_rows=True)
    return orders, raw_rows


def db_orders_in_window(from_dt: datetime, to_dt: datetime) -> Set[str]:
    db = SessionLocal()
    try:
        rows = db.query(SalesOrderRecord.order_id).filter(
            SalesOrderRecord.order_date >= from_dt.replace(tzinfo=None),
            SalesOrderRecord.order_date <= to_dt.replace(tzinfo=None),
        ).all()
        return set(r[0] for r in rows)
    finally:
        db.close()


def count_db_orders_in_window(from_dt: datetime, to_dt: datetime) -> int:
    db = SessionLocal()
    try:
        return db.query(SalesOrderRecord).filter(
            SalesOrderRecord.order_date >= from_dt.replace(tzinfo=None),
            SalesOrderRecord.order_date <= to_dt.replace(tzinfo=None),
        ).count()
    finally:
        db.close()


def delete_db_orders_in_window(from_dt: datetime, to_dt: datetime) -> int:
    db = SessionLocal()
    try:
        q = db.query(SalesOrderRecord).filter(
            SalesOrderRecord.order_date >= from_dt.replace(tzinfo=None),
            SalesOrderRecord.order_date <= to_dt.replace(tzinfo=None),
        )
        count = q.count()
        q.delete(synchronize_session=False)
        db.commit()
        return count
    finally:
        db.close()


def backup_db_orders_in_window(from_dt: datetime, to_dt: datetime, out_path: str) -> int:
    """Dump sales_orders rows in window to a JSON file and return count."""
    import json
    db = SessionLocal()
    try:
        rows = db.query(SalesOrderRecord).filter(
            SalesOrderRecord.order_date >= from_dt.replace(tzinfo=None),
            SalesOrderRecord.order_date <= to_dt.replace(tzinfo=None),
        ).all()
        items = []
        for r in rows:
            rec = {}
            for c in r.__table__.columns:
                val = getattr(r, c.name)
                # naive datetime -> iso
                if hasattr(val, 'isoformat'):
                    try:
                        val = val.isoformat()
                    except Exception:
                        pass
                rec[c.name] = val
            items.append(rec)

        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({'exported_at': datetime.utcnow().isoformat(), 'count': len(items), 'rows': items}, f, ensure_ascii=False, indent=2)

        return len(items)
    finally:
        db.close()


def sample_items(seq: List[str], n: int = 10) -> List[str]:
    return seq[:n]


async def main():
    args = parse_args()
    from_start, _ = to_utc_dt(args.from_date)
    _, to_end = to_utc_dt(args.to_date)

    print(f"Dry-run: fetching Unicommerce export for {from_start.date()} -> {to_end.date()}")
    orders, raw_rows = await fetch_export_rows(from_start, to_end)

    export_order_codes = [o.get("code") or o.get("saleOrderCode") or o.get("saleOrderCode") for o in orders]
    export_set = set([c for c in export_order_codes if c])

    db_set = db_orders_in_window(from_start, to_end)

    only_in_export = sorted(list(export_set - db_set))
    only_in_db = sorted(list(db_set - export_set))

    print("\nSummary:")
    print(f"  Export orders fetched: {len(export_set)}")
    print(f"  DB orders in window: {len(db_set)}")
    print(f"  Orders in export but not in DB: {len(only_in_export)}")
    print(f"  Orders in DB but not in export: {len(only_in_db)}")

    if only_in_export:
        print("\nSample orders present in export but missing in DB:")
        for s in sample_items(only_in_export, 20):
            print("  ", s)

    if only_in_db:
        print("\nSample orders present in DB but missing in export:")
        for s in sample_items(only_in_db, 20):
            print("  ", s)

    if args.apply:
        # If DB already has zero rows in the window, assume deletion already ran
        existing = count_db_orders_in_window(from_start, to_end)
        if existing == 0:
            print("\nAPPLY: no DB rows found in window — assuming deletion already performed; skipping delete.")
        else:
            # Backup then delete
            backup_path = f"sales_orders_backup_{from_start.date()}_{to_end.date()}.json"
            backed = backup_db_orders_in_window(from_start, to_end, backup_path)
            print(f"\nAPPLY: backed up {backed} rows to {backup_path}")
            deleted = delete_db_orders_in_window(from_start, to_end)
            print(f"  Deleted {deleted} rows from sales_orders")

        print("  Re-importing export rows (best-effort upsert, resilient chunks)... this may take some time")
        svc = get_unicommerce_service()

        def import_raw_rows(rows_list):
            normalized_total = 0
            skipped_total = 0
            failed_codes = []
            CHUNK = 500
            for i in range(0, len(rows_list), CHUNK):
                chunk = rows_list[i:i+CHUNK]
                try:
                    n, s = svc._upsert_sales_order_rows_best_effort(
                        chunk,
                        requested_from=from_start,
                        requested_to=to_end,
                        validation_context="repair_import",
                    )
                    normalized_total += n
                    skipped_total += s
                except Exception as e:
                    # Fallback: try per-row to isolate bad rows
                    for r in chunk:
                        try:
                            n2, s2 = svc._upsert_sales_order_rows_best_effort(
                                [r],
                                requested_from=from_start,
                                requested_to=to_end,
                                validation_context="repair_import",
                            )
                            normalized_total += n2
                            skipped_total += s2
                        except Exception as ex_row:
                            # log and record failed order key if present
                            key = r.get('Sale Order Code') or r.get('saleOrderCode') or r.get('code') or 'UNKNOWN'
                            failed_codes.append((key, str(ex_row)))
            return normalized_total, skipped_total, failed_codes

        normalized_rows, skipped, failures = import_raw_rows(raw_rows)
        print(f"  Normalized/imported rows: {normalized_rows}, skipped: {skipped}")
        if failures:
            print(f"  Failed to import {len(failures)} rows — sample:")
            for f in failures[:20]:
                print("   ", f)

    else:
        print('\nDry-run complete. No DB changes performed. Use --apply to perform deletion+reimport.')


if __name__ == '__main__':
    asyncio.run(main())
