#!/usr/bin/env python3
"""Compare live export aggregates against DB-first aggregates for a date window."""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
from datetime import datetime, timedelta
from typing import Any, Dict


ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.unicommerce import get_unicommerce_service
from app.services.unicommerce_data_service import get_unicommerce_data_service
from app.utils.timezone_utils import IST, normalize_date_range_ist


def _drift_pct(diff: float, baseline: float) -> float:
    return round((abs(diff) / max(abs(baseline), 1.0)) * 100.0, 4)


def _parse_thresholds(raw: str) -> Dict[str, float]:
    thresholds: Dict[str, float] = {
        "revenue": 1.0,
        "orders": 1.0,
        "items": 1.0,
    }
    if not raw.strip():
        return thresholds
    for token in raw.split(","):
        piece = token.strip()
        if not piece:
            continue
        if "=" not in piece:
            raise ValueError(f"Invalid threshold token '{piece}'. Use key=value format.")
        key, value = piece.split("=", 1)
        key_norm = key.strip().lower()
        if key_norm not in thresholds:
            raise ValueError(f"Unknown threshold key '{key_norm}'. Use revenue,orders,items.")
        thresholds[key_norm] = float(value.strip())
    return thresholds


async def _run(
    from_date: str,
    to_date: str,
    *,
    closed_window_mode: bool,
    exclude_boundary_days: bool,
) -> Dict[str, Any]:
    start_utc, end_exclusive_utc, window_meta = normalize_date_range_ist(
        from_date,
        to_date,
        closed_window_mode=closed_window_mode,
    )
    from_dt = start_utc
    to_dt = end_exclusive_utc - timedelta(seconds=1)

    effective_from_ist = datetime.fromisoformat(str(window_meta["from_date_ist"]))
    effective_to_ist = datetime.fromisoformat(str(window_meta["to_date_ist"]))
    if exclude_boundary_days:
        effective_from_ist = effective_from_ist + timedelta(days=1)
        effective_to_ist = effective_to_ist - timedelta(days=1)
        if effective_to_ist < effective_from_ist:
            raise ValueError("Cannot exclude boundary days: resulting date window is empty")
        from_dt, end_exclusive_utc, window_meta = normalize_date_range_ist(
            effective_from_ist.date().isoformat(),
            effective_to_ist.date().isoformat(),
            closed_window_mode=False,
        )
        to_dt = end_exclusive_utc - timedelta(seconds=1)
        window_meta["boundary_days_excluded"] = True
    else:
        window_meta["boundary_days_excluded"] = False

    now_ist_date = datetime.now(IST).date()
    if datetime.fromisoformat(str(window_meta["to_date_ist"])).date() >= now_ist_date:
        return {
            "success": False,
            "error": "Open window detected. Current IST day cannot be validated.",
            "window_type": "open",
            "timezone": "IST",
            "data_completeness": "partial",
            "window": {"from_date": from_dt.isoformat(), "to_date": to_dt.isoformat()},
        }
    if (to_dt - from_dt).total_seconds() < 24 * 60 * 60:
        window_meta["warning"] = "Validation window is less than 24 hours; drift may be noisy"

    uc = get_unicommerce_service()
    ds = get_unicommerce_data_service()

    export_result = await uc.get_sales_data(from_dt, to_dt, period_name="custom")
    db_result = ds.get_sales_data(
        period="custom",
        from_date=from_dt,
        to_date=to_dt,
        include_legacy_orders=False,
        include_orders=False,
        include_summary=True,
    )

    export_summary = dict(export_result.get("summary") or {})
    db_summary = dict(db_result.get("summary") or {})

    export_revenue = float(export_summary.get("total_revenue", 0) or 0.0)
    db_revenue = float(db_summary.get("total_revenue", 0) or 0.0)
    export_orders = int(export_summary.get("valid_orders", 0) or 0)
    db_orders = int(db_summary.get("valid_orders", 0) or 0)
    export_items = int(export_summary.get("total_items", 0) or 0)
    db_items = int(db_summary.get("total_items", 0) or 0)

    revenue_diff = round(db_revenue - export_revenue, 2)
    orders_diff = db_orders - export_orders
    items_diff = db_items - export_items

    return {
        "success": bool(export_result.get("success")) and bool(db_result.get("success")),
        "window": {"from_date": from_dt.isoformat(), "to_date": to_dt.isoformat()},
        "window_type": window_meta["window_type"],
        "timezone": "IST",
        "data_completeness": window_meta["data_completeness"],
        "window_metadata": window_meta,
        "export": {
            "revenue": round(export_revenue, 2),
            "order_count": export_orders,
            "item_count": export_items,
        },
        "db": {
            "revenue": round(db_revenue, 2),
            "order_count": db_orders,
            "item_count": db_items,
            "data_source": db_result.get("data_source"),
        },
        "drift": {
            "revenue_diff": revenue_diff,
            "revenue_drift_pct": _drift_pct(revenue_diff, export_revenue),
            "order_count_diff": orders_diff,
            "order_count_drift_pct": _drift_pct(float(orders_diff), float(export_orders)),
            "item_count_diff": items_diff,
            "item_count_drift_pct": _drift_pct(float(items_diff), float(export_items)),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile sales export API vs DB aggregates.")
    parser.add_argument("--from-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--to-date",
        default=datetime.now(IST).strftime("%Y-%m-%d"),
        help="YYYY-MM-DD (defaults to today IST, then closed-window mode may shift to yesterday)",
    )
    parser.add_argument(
        "--closed-window-mode",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When true (default), excludes current IST day by shifting to_date to yesterday",
    )
    parser.add_argument(
        "--exclude-boundary-days",
        action="store_true",
        help="Exclude first and last day of the supplied window before reconciliation",
    )
    parser.add_argument(
        "--thresholds",
        default="revenue=1,orders=1,items=1",
        help="Comma-separated drift thresholds in percent. Example: revenue=1,orders=1,items=1",
    )
    args = parser.parse_args()

    thresholds = _parse_thresholds(args.thresholds)
    result = asyncio.run(
        _run(
            args.from_date,
            args.to_date,
            closed_window_mode=bool(args.closed_window_mode),
            exclude_boundary_days=bool(args.exclude_boundary_days),
        )
    )
    if not result.get("success"):
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 2
    drift = dict(result.get("drift") or {})
    verdict = {
        "revenue": float(drift.get("revenue_drift_pct", 100.0)) <= thresholds["revenue"],
        "orders": float(drift.get("order_count_drift_pct", 100.0)) <= thresholds["orders"],
        "items": float(drift.get("item_count_drift_pct", 100.0)) <= thresholds["items"],
    }
    result["thresholds"] = thresholds
    result["within_thresholds"] = verdict
    result["passed"] = all(verdict.values())

    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
