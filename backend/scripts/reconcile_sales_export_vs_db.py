#!/usr/bin/env python3
"""Reconcile live export API results against DB-first data for a date window.

Usage (from backend/):
  python scripts/reconcile_sales_export_vs_db.py --from-date 2026-04-20 --to-date 2026-04-26
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

from sqlalchemy import func

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db.export_models import InventorySnapshotRecord
from app.db.session import SessionLocal
from app.services.unicommerce import get_unicommerce_service
from app.services.unicommerce_data_service import get_unicommerce_data_service
from app.services.unicommerce_sync_orchestrator import get_unicommerce_sync_orchestrator


def _parse_date_start(value: str) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%d")
    return parsed.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def _parse_date_end(value: str) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%d")
    return parsed.replace(hour=23, minute=59, second=59, microsecond=0, tzinfo=timezone.utc)


def _drift_pct(diff: float, baseline: float) -> float:
    return round((abs(diff) / max(abs(baseline), 1.0)) * 100.0, 4)


def _sum_db_refund(items: list[Dict[str, Any]]) -> float:
    total = Decimal("0")
    for item in items:
        raw = item.get("refundAmount", 0) or 0
        try:
            total += Decimal(str(raw))
        except Exception:
            continue
    return float(total.quantize(Decimal("0.01")))


async def _run(args: argparse.Namespace) -> Dict[str, Any]:
    from_dt = _parse_date_start(args.from_date)
    to_dt = _parse_date_end(args.to_date)

    uc = get_unicommerce_service()
    ds = get_unicommerce_data_service()
    orchestrator = get_unicommerce_sync_orchestrator()

    # 1) Sales: live export vs DB-first
    live_sales = await uc.get_sales_data(from_dt, to_dt, period_name="custom")
    db_sales = ds.get_sales_data(
        period="custom",
        from_date=from_dt,
        to_date=to_dt,
        include_legacy_orders=False,
        include_orders=False,
        include_summary=True,
    )

    live_sales_summary = dict(live_sales.get("summary") or {})
    db_sales_summary = dict(db_sales.get("summary") or {})

    live_revenue = float(live_sales_summary.get("total_revenue", 0) or 0.0)
    db_revenue = float(db_sales_summary.get("total_revenue", 0) or 0.0)

    live_orders = int(live_sales_summary.get("valid_orders", 0) or 0)
    db_orders = int(db_sales_summary.get("valid_orders", 0) or 0)

    live_items = int(live_sales_summary.get("total_items", 0) or 0)
    db_items = int(db_sales_summary.get("total_items", 0) or 0)

    revenue_diff = round(db_revenue - live_revenue, 2)
    orders_diff = db_orders - live_orders
    items_diff = db_items - live_items

    # 2) Returns: live export vs DB-first
    live_returns = await uc.fetch_returns_via_export(from_dt, to_dt)
    db_returns = ds.get_returns_data(from_date=from_dt, to_date=to_dt, return_type="ALL")

    live_return_items = int(live_returns.get("total_items", 0) or 0)
    db_return_items = len(list(db_returns.get("items") or []))

    db_returns_refund = _sum_db_refund(list(db_returns.get("items") or []))

    # 3) Inventory snapshot export test (full-discovery optional)
    db = SessionLocal()
    try:
        before_inventory_rows = int(db.query(func.count(InventorySnapshotRecord.id)).scalar() or 0)
    finally:
        db.close()

    inventory_sync = await orchestrator.sync_inventory(
        facility_code=args.facility_code,
        full_discovery=bool(args.full_inventory_discovery),
        discovery_limit=args.inventory_discovery_limit,
    )

    db = SessionLocal()
    try:
        after_inventory_rows = int(db.query(func.count(InventorySnapshotRecord.id)).scalar() or 0)
    finally:
        db.close()

    result = {
        "success": True,
        "window": {
            "from_date": from_dt.isoformat(),
            "to_date": to_dt.isoformat(),
        },
        "sales": {
            "live_success": bool(live_sales.get("success")),
            "db_success": bool(db_sales.get("success")),
            "live": {
                "valid_orders": live_orders,
                "total_items": live_items,
                "total_revenue": round(live_revenue, 2),
            },
            "db": {
                "valid_orders": db_orders,
                "total_items": db_items,
                "total_revenue": round(db_revenue, 2),
                "data_source": db_sales.get("data_source"),
            },
            "drift": {
                "revenue_diff": revenue_diff,
                "revenue_drift_pct": _drift_pct(revenue_diff, live_revenue),
                "orders_diff": orders_diff,
                "orders_drift_pct": _drift_pct(float(orders_diff), float(live_orders)),
                "items_diff": items_diff,
                "items_drift_pct": _drift_pct(float(items_diff), float(live_items)),
            },
        },
        "returns": {
            "live_success": bool(live_returns.get("successful")),
            "db_success": bool(db_returns.get("success")),
            "live_total_items": live_return_items,
            "db_total_items": db_return_items,
            "db_total_refund": db_returns_refund,
            "items_diff": db_return_items - live_return_items,
        },
        "inventory": {
            "sync_success": bool(inventory_sync.get("success")),
            "requested_skus": int(inventory_sync.get("requested_skus", 0) or 0),
            "fetched_skus": int(inventory_sync.get("fetched_skus", 0) or 0),
            "full_discovery": bool(inventory_sync.get("full_discovery")),
            "facility_code": inventory_sync.get("facility_code", args.facility_code),
            "db_rows_before": before_inventory_rows,
            "db_rows_after": after_inventory_rows,
        },
    }

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile live export APIs vs DB-first data.")
    parser.add_argument("--from-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--to-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--facility-code", default="anthrilo", help="Inventory facility code")
    parser.add_argument(
        "--full-inventory-discovery",
        action="store_true",
        help="Use full SKU discovery for inventory snapshot validation",
    )
    parser.add_argument(
        "--inventory-discovery-limit",
        type=int,
        default=None,
        help="Optional discovery limit when full discovery is disabled",
    )
    parser.add_argument("--max-revenue-drift-pct", type=float, default=1.0)
    parser.add_argument("--max-orders-drift-pct", type=float, default=1.0)
    parser.add_argument("--max-items-drift-pct", type=float, default=1.0)

    args = parser.parse_args()

    result = asyncio.run(_run(args))
    print(json.dumps(result, indent=2, ensure_ascii=True))

    sales = result.get("sales", {})
    drift = sales.get("drift", {})

    revenue_ok = float(drift.get("revenue_drift_pct", 100.0)) <= float(args.max_revenue_drift_pct)
    orders_ok = float(drift.get("orders_drift_pct", 100.0)) <= float(args.max_orders_drift_pct)
    items_ok = float(drift.get("items_drift_pct", 100.0)) <= float(args.max_items_drift_pct)

    if revenue_ok and orders_ok and items_ok:
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
