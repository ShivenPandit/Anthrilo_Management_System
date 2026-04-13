"""Unicommerce integration API endpoints."""

from fastapi import APIRouter, Query, BackgroundTasks, WebSocket, WebSocketDisconnect
import logging
import asyncio
import json as json_module
from datetime import datetime, timezone, timedelta, date as date_cls
from app.services.unicommerce import get_unicommerce_service
from app.services.unicommerce_data_service import get_unicommerce_data_service
from app.services.unicommerce_sync_orchestrator import get_unicommerce_sync_orchestrator
from app.core.token_manager import get_token_manager
from app.core.redis import redis_client
from app.services.cache_service import CacheService

router = APIRouter()
logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
EXCLUDED_REVENUE_STATUSES = {
    "CANCELLED",
    "CANCELED",
    "RETURNED",
    "REFUNDED",
    "FAILED",
    "UNFULFILLABLE",
    "ERROR",
    "PENDING_VERIFICATION",
}


# WEBSOCKET CONNECTION MANAGER

class ConnectionManager:
    """Manages WebSocket connections for real-time dashboard updates."""

    def __init__(self):
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(
            f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(
            f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send data to all connected clients."""
        disconnected = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


ws_manager = ConnectionManager()


def _parse_date_boundary_utc(value: str, end_of_day: bool = False) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%d")
    if end_of_day:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        parsed = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    return parsed.replace(tzinfo=timezone.utc)


async def _broadcast_sales_refresh(sync_event: dict | None = None) -> None:
    """Broadcast refreshed sales snapshot and optional sync completion event."""
    try:
        today_key = f"uc:today:{datetime.now(IST).strftime('%Y-%m-%d')}"
        data_service = get_unicommerce_data_service()
        today_result = data_service.get_sales_data(period="today")

        if today_result.get("success"):
            CacheService.set(today_key, today_result, 180)
            await ws_manager.broadcast({"type": "today_sales", "data": today_result})

        if sync_event is not None:
            await ws_manager.broadcast({"type": "sync_completed", "data": sync_event})
    except Exception as exc:
        logger.warning(f"Failed to broadcast sync refresh event: {exc}")


# Summary endpoints

@router.get("/unicommerce/today")
async def get_today_sales():
    """Get today's sales summary using two-phase approach with Redis caching."""
    try:
        # Check Redis cache (short TTL for today)
        cache_key = f"uc:today:{datetime.now(IST).strftime('%Y-%m-%d')}"
        cached = CacheService.get(cache_key)
        if cached:
            logger.info("TODAY sales: Redis cache hit")
            cached["_cached"] = True
            return cached

        logger.info("Fetching TODAY sales (cache miss)")
        data_service = get_unicommerce_data_service()
        result = data_service.get_sales_data(period="today")

        if result.get("success"):
            summary = result.get("summary", {})
            logger.info(
                f"TODAY: {summary.get('total_orders', 0)} orders, "
                f"INR {summary.get('total_revenue', 0):,.2f}"
            )
            # Cache for 3 minutes (today changes frequently)
            CacheService.set(cache_key, result, 180)

            # Broadcast to WebSocket clients
            await ws_manager.broadcast({"type": "today_sales", "data": result})

        return result

    except Exception as e:
        logger.error(f"Error in get_today_sales: {e}", exc_info=True)
        return {"success": False, "error": str(e), "message": "Failed to fetch today's sales"}


@router.get("/unicommerce/yesterday")
async def get_yesterday_sales():
    """Get yesterday's sales summary with Redis caching."""
    try:
        now_ist = datetime.now(IST)
        yesterday = (now_ist - timedelta(days=1)).strftime('%Y-%m-%d')
        cache_key = f"uc:yesterday:{yesterday}"
        cached = CacheService.get(cache_key)
        if cached:
            logger.info("YESTERDAY sales: Redis cache hit")
            cached["_cached"] = True
            return cached

        logger.info("Fetching YESTERDAY sales (cache miss)")
        data_service = get_unicommerce_data_service()
        result = data_service.get_sales_data(period="yesterday")

        if result.get("success"):
            summary = result.get("summary", {})
            logger.info(
                f"YESTERDAY: {summary.get('total_orders', 0)} orders, "
                f"INR {summary.get('total_revenue', 0):,.2f}"
            )
            # Yesterday data is stable - cache for 30 min
            CacheService.set(cache_key, result, CacheService.TTL_LONG)
        return result

    except Exception as e:
        logger.error(f"Error in get_yesterday_sales: {e}", exc_info=True)
        return {"success": False, "error": str(e), "message": "Failed to fetch yesterday's sales"}


@router.get("/unicommerce/last-7-days")
async def get_last_7_days():
    """Get last 7 complete days sales with Redis caching."""
    try:
        cache_key = f"uc:last7:{datetime.now(IST).strftime('%Y-%m-%d')}"
        cached = CacheService.get(cache_key)
        if cached:
            logger.info("LAST 7 DAYS: Redis cache hit")
            cached["_cached"] = True
            return cached

        logger.info("Fetching LAST 7 DAYS sales (cache miss)")
        data_service = get_unicommerce_data_service()
        result = data_service.get_sales_data(period="last_7_days")

        if result.get("success"):
            summary = result.get("summary", {})
            logger.info(
                f"7 DAYS: {summary.get('total_orders', 0)} orders, "
                f"INR {summary.get('total_revenue', 0):,.2f}"
            )
            # Cache for 30 minutes (historical data changes less frequently)
            CacheService.set(cache_key, result, CacheService.TTL_LONG)
        return result

    except Exception as e:
        logger.error(f"Error in get_last_7_days: {e}", exc_info=True)
        return {"success": False, "error": str(e), "message": "Failed to fetch last 7 days sales"}


# Backward compatibility alias
@router.get("/unicommerce/last-24-hours")
async def get_last_24_hours():
    """Alias for today's sales (backward compatibility)"""
    return await get_today_sales()


# Paginated endpoints

@router.get("/unicommerce/orders/today")
async def get_today_orders_paginated(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(12, ge=1, le=100, description="Orders per page")
):
    """Get today's orders with pagination."""
    try:
        data_service = get_unicommerce_data_service()
        return data_service.get_orders_paginated(
            period="today",
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/orders/yesterday")
async def get_yesterday_orders_paginated(
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100)
):
    """Get yesterday's orders with pagination."""
    try:
        data_service = get_unicommerce_data_service()
        return data_service.get_orders_paginated(
            period="yesterday",
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/orders/last-7-days")
async def get_last_7_days_orders_paginated(
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100)
):
    """Get last 7 days orders with pagination."""
    try:
        data_service = get_unicommerce_data_service()
        return data_service.get_orders_paginated(
            period="last_7_days",
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/orders/custom")
async def get_custom_orders_paginated(
    from_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    to_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100)
):
    """Get orders for custom date range with pagination."""
    try:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0, tzinfo=timezone.utc
        )
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )

        data_service = get_unicommerce_data_service()
        return data_service.get_orders_paginated(
            period="custom",
            from_date=from_dt,
            to_date=to_dt,
            page=page,
            page_size=page_size,
        )

    except ValueError as e:
        return {"success": False, "error": f"Invalid date format: {e}"}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# SALES REPORT ENDPOINT

@router.get("/unicommerce/sales-report")
async def get_sales_report(
    from_date: str = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str = Query(None, description="End date (YYYY-MM-DD)"),
    period: str = Query(
        "today", description="Preset: today, yesterday, last_7_days, custom")
):
    """Get comprehensive sales report with Redis caching."""
    try:
        # Check Redis cache
        cache_key = f"uc:report:{period}:{from_date or 'na'}:{to_date or 'na'}"
        cached = CacheService.get(cache_key)
        if cached:
            cached["_cached"] = True
            return cached

        data_service = get_unicommerce_data_service()

        if period == "today":
            result = data_service.get_sales_data(period="today")
        elif period == "yesterday":
            result = data_service.get_sales_data(period="yesterday")
        elif period == "last_7_days":
            result = data_service.get_sales_data(period="last_7_days")
        elif period == "custom" and from_date and to_date:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc
            )
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
            result = data_service.get_sales_data(
                period="custom",
                from_date=from_dt,
                to_date=to_dt,
            )
        else:
            result = data_service.get_sales_data(period="today")

        # Cache result
        ttl = 180 if period == "today" else CacheService.TTL_MEDIUM
        if result and result.get("success"):
            CacheService.set(cache_key, result, ttl)

        return result

    except ValueError as e:
        return {"success": False, "error": f"Invalid date format: {e}"}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/daily-sales-report")
async def get_daily_sales_report(
    date: str = Query(None, description="Single date for report (YYYY-MM-DD)"),
    from_date: str = Query(None, description="Range start date (YYYY-MM-DD)"),
    to_date: str = Query(None, description="Range end date (YYYY-MM-DD)"),
):
    """
    Get Sales Report with channel-wise breakdown and item-level detail.

    Supports two modes:
    - Single date: pass `date` param
    - Date range: pass `from_date` and `to_date` params

    Returns channel breakdown, item-level detail, and comparison data.
    """
    try:
        # Redis cache check (10-min TTL)
        cache_key = f"uc:daily_report:{date or 'na'}:{from_date or 'na'}:{to_date or 'na'}"
        cached = CacheService.get(cache_key)
        if cached:
            cached["cached"] = True
            return cached

        data_service = get_unicommerce_data_service()

        # Determine mode: range vs single date
        is_range = from_date and to_date
        if not is_range and not date:
            return {"success": False, "error": "Provide either 'date' or both 'from_date' and 'to_date'."}

        if is_range:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc
            )
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
            result = data_service.get_sales_data(
                period="custom",
                from_date=from_dt,
                to_date=to_dt,
            )
            date_label = f"{from_date} to {to_date}"
        else:
            # Single date mode (existing logic)
            report_date = datetime.strptime(date, "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            yesterday = today - timedelta(days=1)

            result = None
            if report_date == today:
                result = data_service.get_sales_data(period="today")
            elif report_date == yesterday:
                result = data_service.get_sales_data(period="yesterday")
            else:
                from_dt = datetime.strptime(date, "%Y-%m-%d").replace(
                    hour=0, minute=0, second=0, tzinfo=timezone.utc
                )
                to_dt = datetime.strptime(date, "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59, tzinfo=timezone.utc
                )
                result = data_service.get_sales_data(
                    period="custom",
                    from_date=from_dt,
                    to_date=to_dt,
                )
            date_label = date

        if not result.get("success"):
            return result

        # Extract channel breakdown data
        channel_breakdown = result.get(
            "summary", {}).get("channel_breakdown", {})

        # Transform to report format
        report_data = []
        for channel_name, channel_data in channel_breakdown.items():
            report_data.append({
                "channel_name": channel_name,
                "quantity": channel_data.get("items", 0),
                "selling_price": channel_data.get("revenue", 0),
                "orders": channel_data.get("orders", 0),
            })

        # Sort by revenue (highest first)
        report_data.sort(key=lambda x: x["selling_price"], reverse=True)

        # Calculate totals
        total_quantity = sum(item["quantity"] for item in report_data)
        total_revenue = sum(item["selling_price"] for item in report_data)
        total_orders = result.get("summary", {}).get(
            "valid_orders", 0)
        total_all_orders = result.get("summary", {}).get(
            "total_orders", 0)
        excluded_items = result.get("summary", {}).get(
            "total_items", 0) - total_quantity

        # ── Extract item-level detail from raw orders ──
        # Must match service.EXCLUDED_STATUSES for consistency with channel totals
        EXCLUDED_STATUSES = {
            "CANCELLED", "CANCELED", "RETURNED", "REFUNDED",
            "FAILED", "UNFULFILLABLE", "ERROR", "PENDING_VERIFICATION"
        }

        def _format_order_date(raw_value) -> str:
            raw = str(raw_value or "").strip()
            if not raw:
                return ""

            try:
                numeric = float(raw)
                if numeric > 1e12:
                    numeric = numeric / 1000.0
                dt = datetime.fromtimestamp(numeric, tz=timezone.utc).astimezone(IST)
                return dt.strftime("%d/%m/%Y %H:%M:%S")
            except (ValueError, TypeError, OverflowError, OSError):
                pass

            try:
                iso_raw = raw.replace("Z", "+00:00")
                dt = datetime.fromisoformat(iso_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=IST)
                else:
                    dt = dt.astimezone(IST)
                return dt.strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                pass

            for fmt in ("%Y-%m-%d %H:%M:%S", "%d %b %Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
                try:
                    dt = datetime.strptime(raw, fmt).replace(tzinfo=IST)
                    return dt.strftime("%d/%m/%Y %H:%M:%S")
                except ValueError:
                    continue

            return raw

        items_detail = []
        raw_orders = result.get("_orders", [])
        for order in raw_orders:
            status = (order.get("status") or "").upper()
            if status in EXCLUDED_STATUSES:
                continue
            channel = order.get("channel", "UNKNOWN")
            order_date = _format_order_date(order.get("created"))
            for item in order.get("saleOrderItems", []):
                selling_price = 0.0
                try:
                    selling_price = float(item.get("sellingPrice", 0))
                except (ValueError, TypeError):
                    pass
                items_detail.append({
                    "item_sku_code": item.get("itemSku", ""),
                    "sale_order_item_code": item.get("code", ""),
                    "item_type_name": item.get("itemTypeName", ""),
                    "size": item.get("size", ""),
                    "channel_name": channel,
                    "order_date": order_date,
                    "bundle_sku_code_number": item.get("bundleSkuCodeNumber", ""),
                    "selling_price": round(selling_price, 2),
                })
        # Sort items by channel then SKU
        items_detail.sort(key=lambda x: (x["channel_name"], x["item_sku_code"]))

        # ── Fetch inventory snapshot for all unique SKUs ──
        unique_skus = list(set(item["item_sku_code"] for item in items_detail if item["item_sku_code"]))
        inventory_map = {}
        try:
            if unique_skus:
                inventory_result = data_service.get_inventory_data(skus=unique_skus)
                if inventory_result.get("success"):
                    for inventory_item in inventory_result.get("items", []):
                        sku_code = inventory_item.get("sku")
                        if not sku_code:
                            continue
                        inventory_map[str(sku_code)] = {
                            "good_inventory": int(inventory_item.get("available_qty", 0) or 0),
                            "virtual_inventory": int(inventory_item.get("reserved_qty", 0) or 0),
                        }
        except Exception as inv_err:
            logger.warning(f"Could not fetch inventory data: {inv_err}")

        # Attach inventory data to each item
        for item in items_detail:
            sku = item["item_sku_code"]
            inv = inventory_map.get(sku, {})
            item["good_inventory"] = inv.get("good_inventory", None)
            item["virtual_inventory"] = inv.get("virtual_inventory", None)

        # ── Fetch comparison data (previous day / period) ──
        comparison = None
        try:
            if not is_range and date:
                comp_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).date()
                comp_today = datetime.now(timezone.utc).date()
                comp_yesterday = comp_today - timedelta(days=1)
                if comp_date == comp_today:
                    comp_result = data_service.get_sales_data(period="today")
                elif comp_date == comp_yesterday:
                    comp_result = data_service.get_sales_data(period="yesterday")
                else:
                    comp_from = datetime.combine(comp_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                    comp_to = datetime.combine(comp_date, datetime.max.time()).replace(tzinfo=timezone.utc)
                    comp_result = data_service.get_sales_data(
                        period="custom",
                        from_date=comp_from,
                        to_date=comp_to,
                    )

                if comp_result.get("success"):
                    comp_breakdown = comp_result.get("summary", {}).get("channel_breakdown", {})
                    comp_report = []
                    for ch_name, ch_data in comp_breakdown.items():
                        comp_report.append({
                            "channel_name": ch_name,
                            "quantity": ch_data.get("items", 0),
                            "selling_price": ch_data.get("revenue", 0),
                            "orders": ch_data.get("orders", 0),
                        })
                    comp_report.sort(key=lambda x: x["selling_price"], reverse=True)
                    comp_total_qty = sum(i["quantity"] for i in comp_report)
                    comp_total_rev = sum(i["selling_price"] for i in comp_report)
                    comp_total_ord = comp_result.get("summary", {}).get("valid_orders", 0)
                    comparison = {
                        "date": comp_date.strftime("%Y-%m-%d"),
                        "report": comp_report,
                        "totals": {
                            "total_channels": len(comp_report),
                            "total_quantity": comp_total_qty,
                            "total_revenue": round(comp_total_rev, 2),
                            "total_orders": comp_total_ord,
                        },
                    }
        except Exception as comp_err:
            logger.warning(f"Could not fetch comparison data: {comp_err}")

        response = {
            "success": True,
            "date": date_label,
            "from_date": from_date if is_range else date,
            "to_date": to_date if is_range else date,
            "report": report_data,
            "items": items_detail,
            "comparison": comparison,
            "totals": {
                "total_channels": len(report_data),
                "total_quantity": total_quantity,
                "total_revenue": round(total_revenue, 2),
                "total_orders": total_orders,
                "excluded_items": excluded_items,
                "all_orders": total_all_orders,
            },
            "currency": "INR",
            "data_source": result.get("data_source", "db_first"),
            "cached": False,
            "note": f"Report shows {total_quantity} items from revenue-generating orders. {excluded_items} items excluded from cancelled/returned orders.",
        }

        # Cache for 10 minutes
        CacheService.set(cache_key, response, CacheService.TTL_MEDIUM)
        return response

    except ValueError as e:
        return {"success": False, "error": f"Invalid date format. Use YYYY-MM-DD: {e}"}
    except Exception as e:
        logger.error(
            f"Error generating daily sales report: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# SALES ACTIVITY REPORT ENDPOINT

@router.get("/unicommerce/sales-activity")
async def get_sales_activity_report(
    from_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    to_date: str = Query(..., description="End date (YYYY-MM-DD)"),
):
    """
    Sales Activity Report — returns item-level data for Size Wise, Item Wise,
    Channel Wise (Detailed), and Channel Wise (Summary) reports.

    Groups sold items by SKU+Size+Channel, attaches cancel/return counts
    and inventory snapshots (good + virtual).
    """
    try:
        # ── Redis cache (10-min TTL) ──
        cache_key = f"uc:sales_activity:{from_date}:{to_date}"
        cached = CacheService.get(cache_key)
        if cached:
            logger.info(f"Sales activity {from_date}→{to_date}: Redis cache hit")
            cached["_cached"] = True
            return cached

        data_service = get_unicommerce_data_service()

        # Construct dates in IST and convert to UTC so the Unicommerce
        # export filter covers the correct IST business day boundaries.
        # Using UTC directly would miss orders between IST 00:00–05:30.
        from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(
            hour=0, minute=0, second=0, tzinfo=IST
        ).astimezone(timezone.utc)
        to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=IST
        ).astimezone(timezone.utc)

        result = data_service.get_sales_data(
            period="custom",
            from_date=from_dt,
            to_date=to_dt,
        )
        if not result.get("success"):
            return result

        raw_orders = result.get("_orders", [])

        # ── Build item-level rows from ALL orders (including cancelled/returned) ──
        # Track sold / cancelled / returned quantities per (sku, size, channel)
        def _norm_sku(v: str) -> str:
            return (v or "").strip().upper()

        def _norm_channel(v: str) -> str:
            ch = (v or "UNKNOWN").strip().upper()
            ch = ch.replace("-", "_").replace(" ", "_")
            while "__" in ch:
                ch = ch.replace("__", "_")
            return ch

        from collections import defaultdict
        detail_map = defaultdict(lambda: {
            "item_sku_code": "",
            "item_type_name": "",
            "size": "",
            "channel": "",
            "total_sale_qty": 0,
            "cancel_qty": 0,
            "return_qty": 0,
        })

        for order in raw_orders:
            status = (order.get("status") or "").upper()
            channel = order.get("channel", "UNKNOWN")

            for item in order.get("saleOrderItems", []):
                sku = item.get("itemSku", "") or ""
                item_type = item.get("itemTypeName", "") or ""
                size = item.get("size", "") or ""
                qty = int(item.get("quantity", 1) or 1)

                key = (sku, size, channel)
                row = detail_map[key]
                row["item_sku_code"] = sku
                row["item_type_name"] = item_type
                row["size"] = size
                row["channel"] = channel

                if status in ("CANCELLED", "CANCELED"):
                    row["cancel_qty"] += qty
                elif status in ("RETURNED", "REFUNDED"):
                    row["return_qty"] += qty
                else:
                    row["total_sale_qty"] += qty

        # Build normalized lookups once for fast matching.
        # 1) (SKU, channel) for fallback matching.
        # 2) (saleOrderCode, SKU) for precise return mapping.
        norm_key_to_detail_keys = defaultdict(list)
        order_sku_to_detail_keys = defaultdict(list)
        for k in detail_map.keys():
            sku_key, _, channel_key = k
            nkey = (_norm_sku(sku_key), _norm_channel(channel_key))
            norm_key_to_detail_keys[nkey].append(k)

        for order in raw_orders:
            order_code = (order.get("code") or "").strip()
            if not order_code:
                continue
            order_code_norm = order_code.upper()
            order_channel = order.get("channel", "UNKNOWN")

            for item in order.get("saleOrderItems", []):
                sku = item.get("itemSku", "") or ""
                size = item.get("size", "") or ""
                key = (sku, size, order_channel)
                if key in detail_map:
                    order_sku_to_detail_keys[(order_code_norm, _norm_sku(sku))].append(key)

        # ── Merge real return events (RTO/CIR) from export-based return report ──
        # Sale order status rarely carries returns; Unicommerce emits returns separately.
        # Use a timeout so large date ranges don't block the entire report.
        return_map = defaultdict(int)  # (sku, channel) -> qty fallback bucket
        return_items_total = 0
        return_items_matched = 0
        try:
            # One custom-range call is significantly faster than per-day calls.
            # Timeout: 600s to accommodate chunked return exports for
            # large date ranges (yearly = ~12 chunks × ~30s each).
            logger.info(f"Sales activity: fetching return report for {from_date} to {to_date}")
            return_report = await asyncio.wait_for(
                get_return_report(
                    from_date=from_date,
                    to_date=to_date,
                    period="custom",
                    return_type="ALL",
                ),
                timeout=600.0,
            )
            logger.info(
                f"Sales activity: return report result — "
                f"success={return_report.get('success')}, "
                f"returns_count={len(return_report.get('returns', []))}, "
                f"totals={return_report.get('totals', {})}, "
                f"error={return_report.get('error', 'none')}"
            )
            if return_report.get("success"):
                for ret in return_report.get("returns", []):
                    so_code_norm = (ret.get("saleOrderCode") or "").strip().upper()
                    ret_channel = _norm_channel(ret.get("channel") or "UNKNOWN")
                    for it in ret.get("items", []):
                        sku = _norm_sku(it.get("sku") or "")
                        try:
                            rqty = int(float(it.get("quantity", 0) or 0))
                        except (TypeError, ValueError):
                            rqty = 0
                        if not sku or rqty <= 0:
                            continue

                        return_items_total += rqty

                        # Primary (real, precise): saleOrderCode + SKU
                        direct_keys = order_sku_to_detail_keys.get((so_code_norm, sku), []) if so_code_norm else []
                        if len(direct_keys) == 1:
                            detail_map[direct_keys[0]]["return_qty"] += rqty
                            return_items_matched += rqty
                            continue

                        if len(direct_keys) > 1:
                            # Ambiguous size within same order+sku; keep in UNKNOWN-size row.
                            sample_row = detail_map[direct_keys[0]]
                            unknown_key = (
                                sample_row.get("item_sku_code") or sku,
                                "UNKNOWN",
                                sample_row.get("channel") or ret_channel,
                            )
                            unknown_row = detail_map[unknown_key]
                            unknown_row["item_sku_code"] = sample_row.get("item_sku_code") or sku
                            unknown_row["item_type_name"] = sample_row.get("item_type_name", "") or ""
                            unknown_row["size"] = "UNKNOWN"
                            unknown_row["channel"] = sample_row.get("channel") or ret_channel
                            unknown_row["return_qty"] += rqty
                            return_items_matched += rqty
                            continue

                        # Fallback: SKU + channel bucket (still real data, lower precision).
                        return_map[(sku, ret_channel)] += rqty

                logger.info(
                    f"Sales activity: return merge phase 1 — "
                    f"total_return_items={return_items_total}, "
                    f"direct_matched={return_items_matched}, "
                    f"fallback_buckets={len(return_map)}"
                )
            else:
                logger.warning(
                    "Sales activity: return-report custom range failed: "
                    f"{return_report.get('error', 'unknown error')}"
                )
        except asyncio.TimeoutError:
            logger.warning(
                f"Sales activity: return-report timed out for range {from_date} to {to_date}, "
                "proceeding without return data"
            )
        except Exception as ret_err:
            logger.warning(f"Sales activity: return merge failed: {ret_err}", exc_info=True)

        # Apply return qty using only real data.
        # If a SKU+channel maps to multiple sizes, we cannot know exact size split from return export,
        # so place it into an explicit UNKNOWN-size row instead of proportional allocation.
        if return_map:
            matched_buckets = 0
            unmatched_buckets = 0
            for (sku, channel), qty in return_map.items():
                matching_keys = norm_key_to_detail_keys.get((sku, channel), [])
                if not matching_keys:
                    unmatched_buckets += 1
                    unknown_key = (sku, "UNKNOWN", channel)
                    unknown_row = detail_map[unknown_key]
                    unknown_row["item_sku_code"] = sku
                    unknown_row["item_type_name"] = unknown_row.get("item_type_name", "") or ""
                    unknown_row["size"] = "UNKNOWN"
                    unknown_row["channel"] = channel
                    unknown_row["return_qty"] += qty
                    continue

                matched_buckets += 1

                if len(matching_keys) == 1:
                    detail_map[matching_keys[0]]["return_qty"] += qty
                    continue

                # Ambiguous size mapping: keep returns in UNKNOWN-size row.
                sample_row = detail_map[matching_keys[0]]
                unknown_key = (sample_row.get("item_sku_code") or sku, "UNKNOWN", sample_row.get("channel") or channel)
                unknown_row = detail_map[unknown_key]
                unknown_row["item_sku_code"] = sample_row.get("item_sku_code") or sku
                unknown_row["item_type_name"] = sample_row.get("item_type_name", "") or ""
                unknown_row["size"] = "UNKNOWN"
                unknown_row["channel"] = sample_row.get("channel") or channel
                unknown_row["return_qty"] += qty

            logger.info(
                f"Sales activity: return buckets matched={matched_buckets}, "
                f"unmatched={unmatched_buckets}, total_buckets={len(return_map)}"
            )

        items = list(detail_map.values())

        # ── Fetch inventory snapshot for all unique SKUs ──
        unique_skus = list(set(r["item_sku_code"] for r in items if r["item_sku_code"]))
        inventory_map = {}
        try:
            if unique_skus:
                inventory_result = data_service.get_inventory_data(skus=unique_skus)
                if inventory_result.get("success"):
                    for inventory_item in inventory_result.get("items", []):
                        sku_code = inventory_item.get("sku")
                        if not sku_code:
                            continue
                        inventory_map[str(sku_code)] = {
                            "good_inventory": int(inventory_item.get("available_qty", 0) or 0),
                            "virtual_inventory": int(inventory_item.get("reserved_qty", 0) or 0),
                        }
        except Exception as inv_err:
            logger.warning(f"Sales activity: inventory fetch failed: {inv_err}")

        # Attach inventory + compute net_sale
        for row in items:
            row["net_sale"] = row["total_sale_qty"] - row["cancel_qty"] - row["return_qty"]
            inv = inventory_map.get(row["item_sku_code"], {})
            row["stock_good"] = inv.get("good_inventory", 0)
            row["stock_virtual"] = inv.get("virtual_inventory", 0)

        # Sort by SKU then size
        items.sort(key=lambda x: (x["item_sku_code"], x["size"], x["channel"]))

        logger.info(
            f"Sales activity report: {len(items)} item rows, "
            f"{len(unique_skus)} unique SKUs, "
            f"date range {from_date} to {to_date}"
        )

        response = {
            "success": True,
            "from_date": from_date,
            "to_date": to_date,
            "items": items,
            "total_skus": len(unique_skus),
        }

        # Cache for 10 min
        CacheService.set(cache_key, response, CacheService.TTL_MEDIUM)
        return response

    except ValueError as e:
        return {"success": False, "error": f"Invalid date format. Use YYYY-MM-DD: {e}"}
    except Exception as e:
        logger.error(f"Error generating sales activity report: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# CHANNEL BREAKDOWN ENDPOINT

@router.get("/unicommerce/channel-revenue")
async def get_channel_revenue(
    period: str = Query(
        "last_7_days", description="Period for channel breakdown")
):
    """Get revenue breakdown by channel/marketplace with Redis caching."""
    try:
        # Check Redis cache
        cache_key = f"uc:channels:{period}:{datetime.now(IST).strftime('%Y-%m-%d')}"
        cached = CacheService.get(cache_key)
        if cached:
            logger.info(f"Channel revenue {period}: Redis cache hit")
            cached["_cached"] = True
            return cached

        data_service = get_unicommerce_data_service()

        if period == "today":
            result = data_service.get_sales_data(period="today")
        elif period == "yesterday":
            result = data_service.get_sales_data(period="yesterday")
        else:
            result = data_service.get_sales_data(period="last_7_days")

        if not result.get("success"):
            return result

        summary = result.get("summary", {})
        channel_breakdown = summary.get("channel_breakdown", {})
        total_revenue = summary.get("total_revenue", 0)

        channels = []
        for channel, data in sorted(
            channel_breakdown.items(),
            key=lambda x: x[1].get("revenue", 0),
            reverse=True
        ):
            channels.append({
                "channel": channel,
                "orders": data.get("orders", 0),
                "revenue": data.get("revenue", 0),
                "percentage": round(
                    (data.get("revenue", 0) / total_revenue *
                     100) if total_revenue > 0 else 0,
                    2
                )
            })

        channel_sum = sum(ch["revenue"] for ch in channels)
        validation_passed = abs(channel_sum - total_revenue) < 1

        response = {
            "success": True,
            "period": period,
            "total_revenue": total_revenue,
            "total_orders": summary.get("total_orders", 0),
            "channels": channels,
            "validation": {
                "channel_sum": channel_sum,
                "total_revenue": total_revenue,
                "passed": validation_passed
            },
            "revenue_method": "sellingPrice_only"
        }

        # Cache channels for 10 min
        CacheService.set(cache_key, response, CacheService.TTL_MEDIUM)
        return response

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# BACKGROUND SYNC ENDPOINTS

@router.post("/unicommerce/sync/{period}")
async def trigger_sync(
    period: str,
    background_tasks: BackgroundTasks
):
    """
    Trigger background sync for a period.
    Orders are fetched from Unicommerce and persisted to DB.

    Valid periods: today, yesterday, last_7_days, last_30_days
    """
    valid_periods = {"today", "yesterday", "last_7_days", "last_30_days"}
    if period not in valid_periods:
        return {
            "success": False,
            "error": f"Invalid period. Use: {', '.join(valid_periods)}"
        }

    try:
        orchestrator = get_unicommerce_sync_orchestrator()
        uc_service = get_unicommerce_service()

        if period == "today":
            from_dt, to_dt = uc_service.get_today_range()
        elif period == "yesterday":
            from_dt, to_dt = uc_service.get_yesterday_range()
        elif period == "last_7_days":
            from_dt, to_dt = uc_service.get_last_n_days_range(7)
        else:
            from_dt, to_dt = uc_service.get_last_n_days_range(30)

        async def _run_sync():
            orders = await orchestrator.sync_orders_window(from_dt, to_dt)
            returns = await orchestrator.sync_returns_window(from_dt, to_dt)
            inventory = await orchestrator.sync_inventory()
            await _broadcast_sales_refresh(
                {
                    "success": bool(orders.get("success")) and bool(returns.get("success")) and bool(inventory.get("success")),
                    "profile": "period_sync",
                    "period": period,
                    "from_date": from_dt.isoformat(),
                    "to_date": to_dt.isoformat(),
                    "orders": orders,
                    "returns": returns,
                    "inventory": inventory,
                }
            )

        background_tasks.add_task(_run_sync)

        return {
            "success": True,
            "message": f"Orchestrated sync started for '{period}' in background",
            "period": period,
            "from_date": from_dt.isoformat(),
            "to_date": to_dt.isoformat(),
        }

    except Exception as e:
        logger.error(f"Error triggering sync: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/unicommerce/sync/all")
async def trigger_sync_all(background_tasks: BackgroundTasks):
    """Trigger background incremental sync profile."""
    try:
        orchestrator = get_unicommerce_sync_orchestrator()

        async def _run_all_syncs():
            result = await orchestrator.run_incremental_sync()
            await _broadcast_sales_refresh(result)

        background_tasks.add_task(_run_all_syncs)

        return {
            "success": True,
            "message": "Incremental sync profile started in background",
        }

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/sync/status")
async def get_sync_status(
    period: str = Query(None, description="Period to check, or omit for all")
):
    """Get orchestrated sync health and lag status."""
    try:
        orchestrator = get_unicommerce_sync_orchestrator()
        health = orchestrator.get_sync_health()
        if period:
            health["requested_period"] = period
        return health
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/sync/health")
async def get_sync_health():
    """Alias endpoint for sync health checks."""
    try:
        orchestrator = get_unicommerce_sync_orchestrator()
        return orchestrator.get_sync_health()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/sync/readiness")
async def get_sync_readiness():
    """Evaluate release gates: coverage, lag, and dashboard DB-first status."""
    try:
        orchestrator = get_unicommerce_sync_orchestrator()
        return orchestrator.get_release_readiness()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/unicommerce/sync/profile/{profile}")
async def run_sync_profile(
    profile: str,
    background_tasks: BackgroundTasks,
    from_date: str = Query(None, description="YYYY-MM-DD (required for full_backfill)"),
    to_date: str = Query(None, description="YYYY-MM-DD (required for full_backfill)"),
    run_in_background: bool = Query(True, description="Run profile asynchronously"),
):
    """Run a sync profile: incremental | realtime_trigger | full_backfill."""
    try:
        orchestrator = get_unicommerce_sync_orchestrator()
        profile_norm = (profile or "").strip().lower()
        parsed_from = _parse_date_boundary_utc(from_date, end_of_day=False) if from_date else None
        parsed_to = _parse_date_boundary_utc(to_date, end_of_day=True) if to_date else None

        valid_profiles = {"incremental", "realtime_trigger", "full_backfill"}
        if profile_norm not in valid_profiles:
            return {
                "success": False,
                "error": "Unknown profile. Use incremental | realtime_trigger | full_backfill",
            }

        if profile_norm == "full_backfill" and (parsed_from is None or parsed_to is None):
            return {
                "success": False,
                "error": "from_date and to_date are required for full_backfill profile",
            }

        if run_in_background:
            async def _run_profile_task():
                result = await orchestrator.run_profile(profile_norm, parsed_from, parsed_to)
                await _broadcast_sales_refresh(result)

            background_tasks.add_task(_run_profile_task)
            return {
                "success": True,
                "message": f"Profile '{profile_norm}' started in background",
                "profile": profile_norm,
                "from_date": parsed_from.isoformat() if parsed_from else None,
                "to_date": parsed_to.isoformat() if parsed_to else None,
            }

        result = await orchestrator.run_profile(profile_norm, parsed_from, parsed_to)
        await _broadcast_sales_refresh(result)
        return result
    except ValueError as e:
        return {"success": False, "error": f"Invalid date format: {e}"}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/unicommerce/sync/backfill/windows")
async def run_backfill_windows(
    background_tasks: BackgroundTasks,
    windows: str = Query("7,30,90,365", description="Comma-separated day windows"),
    run_in_background: bool = Query(True, description="Run backfill in background"),
):
    """Run staged backfill windows for export-first ingestion validation."""
    try:
        orchestrator = get_unicommerce_sync_orchestrator()
        window_values = [int(part.strip()) for part in windows.split(",") if part.strip()]
        window_values = [value for value in window_values if value > 0]
        if not window_values:
            return {"success": False, "error": "At least one positive window is required"}

        if run_in_background:
            async def _run_backfill_task():
                result = await orchestrator.run_backfill_windows(window_values)
                await _broadcast_sales_refresh(result)

            background_tasks.add_task(_run_backfill_task)
            return {
                "success": True,
                "message": "Backfill windows started in background",
                "windows": window_values,
            }

        result = await orchestrator.run_backfill_windows(window_values)
        await _broadcast_sales_refresh(result)
        return result
    except ValueError as e:
        return {"success": False, "error": f"Invalid windows format: {e}"}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/unicommerce/sync/operator/orders")
async def operator_sync_orders(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
):
    """Operator command: manually sync orders for a date range."""
    try:
        orchestrator = get_unicommerce_sync_orchestrator()
        parsed_from = _parse_date_boundary_utc(from_date, end_of_day=False)
        parsed_to = _parse_date_boundary_utc(to_date, end_of_day=True)
        return await orchestrator.sync_orders_window(parsed_from, parsed_to)
    except ValueError as e:
        return {"success": False, "error": f"Invalid date format: {e}"}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/unicommerce/sync/operator/returns")
async def operator_sync_returns(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
):
    """Operator command: manually sync returns for a date range."""
    try:
        orchestrator = get_unicommerce_sync_orchestrator()
        parsed_from = _parse_date_boundary_utc(from_date, end_of_day=False)
        parsed_to = _parse_date_boundary_utc(to_date, end_of_day=True)
        return await orchestrator.sync_returns_window(parsed_from, parsed_to)
    except ValueError as e:
        return {"success": False, "error": f"Invalid date format: {e}"}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/unicommerce/sync/operator/item-master")
async def operator_sync_item_master():
    """Operator command: manually sync item master export."""
    try:
        orchestrator = get_unicommerce_sync_orchestrator()
        return await orchestrator.sync_item_master()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/unicommerce/sync/operator/inventory")
async def operator_sync_inventory(
    skus: str = Query(None, description="Comma-separated SKUs (optional)"),
    facility_code: str = Query("anthrilo", description="Facility code"),
):
    """Operator command: manually sync inventory snapshots."""
    try:
        orchestrator = get_unicommerce_sync_orchestrator()
        sku_list = [part.strip() for part in (skus or "").split(",") if part.strip()]
        return await orchestrator.sync_inventory(skus=sku_list or None, facility_code=facility_code)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# VALIDATION ENDPOINT

@router.get("/unicommerce/validate")
async def validate_revenue():
    """Run DB-first readiness and revenue coverage validation gates."""
    try:
        orchestrator = get_unicommerce_sync_orchestrator()
        readiness = orchestrator.get_release_readiness()
        return {
            "success": True,
            "validation": readiness,
            "message": "Validation uses DB-first coverage and lag gates",
        }
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# AUTH STATUS

@router.get("/unicommerce/auth/status")
async def get_auth_status():
    """Get Unicommerce authentication status and stats."""
    try:
        token_manager = get_token_manager()
        status = token_manager.get_token_status()
        return {
            "success": True,
            "authentication_status": status,
            "message": "Token lifecycle is managed automatically (60s proactive refresh)"
        }
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/unicommerce/auth/refresh")
async def force_refresh_token():
    """Manually trigger token refresh."""
    try:
        token_manager = get_token_manager()
        token = await token_manager.get_valid_token()

        if token:
            return {
                "success": True,
                "message": "Token refreshed",
                "status": token_manager.get_token_status()
            }
        else:
            return {"success": False, "message": "Failed to refresh token"}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# BACKWARD COMPATIBILITY

@router.get("/unicommerce/search-orders")
async def search_orders(
    from_date: str = Query(...),
    to_date: str = Query(...),
    display_start: int = Query(0),
    display_length: int = Query(100)
):
    """Search orders (backward compatible)."""
    try:
        from_dt = datetime.fromisoformat(from_date.replace('Z', '+00:00'))
        to_dt = datetime.fromisoformat(to_date.replace('Z', '+00:00'))

        data_service = get_unicommerce_data_service()
        return data_service.search_sale_orders(
            from_date=from_dt,
            to_date=to_dt,
            display_start=display_start,
            display_length=display_length
        )
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/order-items/{order_code}")
async def get_order_items(order_code: str):
    """Get order details."""
    try:
        data_service = get_unicommerce_data_service()
        return data_service.get_order_details(order_code)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# CACHE MANAGEMENT

@router.post("/unicommerce/clear-cache")
async def clear_cache():
    """Clear Unicommerce cache state (Redis primary + legacy in-memory cache)."""
    try:
        service = get_unicommerce_service()
        service._cache.clear()
        CacheService.invalidate_all_uc_cache()
        await _broadcast_sales_refresh(
            {
                "success": True,
                "profile": "cache_clear",
                "cache_cleared": True,
            }
        )
        logger.info("Unicommerce cache cleared (Redis + in-memory)")
        return {
            "success": True,
            "message": "Unicommerce cache cleared successfully",
            "redis_cleared": True,
            "memory_cleared": True,
        }
    except Exception as e:
        logger.error(f"Error clearing cache: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/cache-stats")
async def get_cache_stats():
    """Get cache statistics showing what's cached and TTL info."""
    try:
        service = get_unicommerce_service()
        now_ist = datetime.now(IST)
        today_key = f"uc:today:{now_ist.strftime('%Y-%m-%d')}"
        yesterday_key = f"uc:yesterday:{(now_ist - timedelta(days=1)).strftime('%Y-%m-%d')}"
        last7_key = f"uc:last7:{now_ist.strftime('%Y-%m-%d')}"

        redis_entries = []
        for period_name, cache_key in [
            ("today", today_key),
            ("yesterday", yesterday_key),
            ("last_7_days", last7_key),
        ]:
            payload = CacheService.get(cache_key)
            ttl_seconds = None
            if redis_client is not None:
                try:
                    ttl_val = redis_client.ttl(cache_key)
                    ttl_seconds = int(ttl_val) if ttl_val is not None else None
                except Exception:
                    ttl_seconds = None

            redis_entries.append(
                {
                    "period": period_name,
                    "key": cache_key,
                    "cached": payload is not None,
                    "ttl_seconds": ttl_seconds,
                    "data_source": (payload or {}).get("data_source") if isinstance(payload, dict) else None,
                    "last_synced_at": (payload or {}).get("last_synced_at") if isinstance(payload, dict) else None,
                }
            )

        stats = []
        for key, (timestamp, data) in service._cache.items():
            age_seconds = (datetime.now() - timestamp).total_seconds()
            remaining_seconds = max(0, service.CACHE_TTL_SECONDS - age_seconds)

            stats.append({
                "key": key,
                "age_seconds": round(age_seconds, 2),
                "remaining_seconds": round(remaining_seconds, 2),
                "is_expired": age_seconds >= service.CACHE_TTL_SECONDS,
                "cached_at": timestamp.isoformat()
            })

        return {
            "success": True,
            "redis": {
                "enabled": redis_client is not None,
                "tracked_periods": redis_entries,
                "total_cached_periods": sum(1 for item in redis_entries if item["cached"]),
            },
            "legacy_memory": {
                "cache_ttl_seconds": service.CACHE_TTL_SECONDS,
                "total_cached_items": len(stats),
                "items": stats,
            },
        }
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/cache-check")
async def check_cache_status():
    """
    Quickly check cache status for all standard periods without fetching data.
    Returns which periods are cached and ready for instant load.
    """
    try:
        service = get_unicommerce_service()
        now_ist = datetime.now(IST)

        redis_period_keys = {
            "today": f"uc:today:{now_ist.strftime('%Y-%m-%d')}",
            "yesterday": f"uc:yesterday:{(now_ist - timedelta(days=1)).strftime('%Y-%m-%d')}",
            "last_7_days": f"uc:last7:{now_ist.strftime('%Y-%m-%d')}",
        }

        periods = ["today", "yesterday", "last_7_days"]
        cache_status = {}

        for period in periods:
            redis_key = redis_period_keys[period]
            redis_payload = CacheService.get(redis_key)
            if redis_payload is not None:
                ttl_seconds = None
                if redis_client is not None:
                    try:
                        ttl_val = redis_client.ttl(redis_key)
                        ttl_seconds = int(ttl_val) if ttl_val is not None else None
                    except Exception:
                        ttl_seconds = None

                cache_status[period] = {
                    "cached": True,
                    "valid": True,
                    "source": "redis",
                    "age_seconds": None,
                    "remaining_seconds": ttl_seconds,
                    "cached_at": None,
                    "data_source": redis_payload.get("data_source") if isinstance(redis_payload, dict) else None,
                }
                continue

            cache_key = service._get_cache_key(period)
            if cache_key in service._cache:
                timestamp, _ = service._cache[cache_key]
                age_seconds = (datetime.now() - timestamp).total_seconds()
                is_valid = age_seconds < service.CACHE_TTL_SECONDS

                cache_status[period] = {
                    "cached": True,
                    "valid": is_valid,
                    "source": "legacy_memory",
                    "age_seconds": round(age_seconds, 2),
                    "remaining_seconds": round(max(0, service.CACHE_TTL_SECONDS - age_seconds), 2),
                    "cached_at": timestamp.isoformat()
                }
            else:
                cache_status[period] = {
                    "cached": False,
                    "valid": False,
                    "source": "none",
                    "age_seconds": None,
                    "remaining_seconds": 0
                }

        all_cached = all(status["valid"] for status in cache_status.values())

        return {
            "success": True,
            "all_periods_cached": all_cached,
            "redis_enabled": redis_client is not None,
            "cache_ttl_seconds": service.CACHE_TTL_SECONDS,
            "periods": cache_status,
            "message": "All data cached and ready for instant load" if all_cached else "Some periods need fetching"
        }
    except Exception as e:
        logger.error(f"Error checking cache: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# SKU-level sales breakdown

@router.get("/unicommerce/sales-by-sku")
async def get_sales_by_sku(
    period: str = Query(
        "today", description="today, yesterday, last_7_days, last_30_days"),
    from_date: str = Query(None, description="Custom start date YYYY-MM-DD"),
    to_date: str = Query(None, description="Custom end date YYYY-MM-DD"),
):
    """
    Get sales aggregated by SKU with item-level breakdown.
    Uses DB-first sales data with normalized-first and raw fallback.
    """
    try:
        data_service = get_unicommerce_data_service()
        return data_service.get_sales_by_sku(
            period=period,
            from_date=from_date,
            to_date=to_date,
        )

    except Exception as e:
        logger.error(f"Error in sales_by_sku: {e}", exc_info=True)
        return {"success": False, "error": str(e), "skus": []}


# RETURN REPORT (Export Job: Tally Return GST Report 3.0)

@router.get("/unicommerce/return-report")
async def get_return_report(
    date: str | None = Query(None, description="Date for report (YYYY-MM-DD)"),
    from_date: str | None = Query(None, description="Start date for custom report (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date for custom report (YYYY-MM-DD)"),
    period: str = Query("daily", description="daily, weekly, monthly, custom"),
    return_type: str = Query("ALL", description="RTO, CIR, or ALL"),
):
    """
    Return Report with channel-wise + SKU breakdown.
    Uses DB-first returns data (normalized table with raw fallback).
    Supports RTO, CIR, or ALL return types and daily/weekly/monthly/custom ranges.
    """
    try:
        data_service = get_unicommerce_data_service()

        period_norm = (period or "daily").strip().lower()
        today_ist = datetime.now(IST).date()

        if period_norm == "custom" or (from_date and to_date):
            if not from_date or not to_date:
                return {
                    "success": False,
                    "error": "Both from_date and to_date are required for custom range",
                    "period": "custom",
                    "return_type": return_type,
                }
            start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(to_date, "%Y-%m-%d").date()
            period_norm = "custom"
        elif period_norm == "weekly":
            # Last completed Monday-Sunday week
            current_week_start = today_ist - timedelta(days=today_ist.weekday())
            start_date = current_week_start - timedelta(days=7)
            end_date = current_week_start - timedelta(days=1)
        elif period_norm == "monthly":
            # Last completed calendar month
            first_of_current_month = today_ist.replace(day=1)
            end_date = first_of_current_month - timedelta(days=1)
            start_date = end_date.replace(day=1)
        else:
            base_date = datetime.strptime(date, "%Y-%m-%d").date() if date else (today_ist - timedelta(days=1))
            start_date = base_date
            end_date = base_date
            period_norm = "daily"

        if start_date > end_date:
            return {
                "success": False,
                "error": "from_date cannot be greater than to_date",
                "period": period_norm,
                "from_date": start_date.isoformat(),
                "to_date": end_date.isoformat(),
                "return_type": return_type,
            }

        # Build UTC date range for DB-first reads
        from_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=IST).astimezone(timezone.utc)
        to_dt = datetime.combine(end_date, datetime.max.time().replace(microsecond=0)).replace(tzinfo=IST).astimezone(timezone.utc)

        returns_data = data_service.get_returns_data(
            from_date=from_dt,
            to_date=to_dt,
            return_type=return_type,
        )

        if not returns_data.get("success"):
            return {
                "success": False,
                "error": returns_data.get("error", "Failed to fetch return data"),
                "period": period_norm,
                "date": start_date.isoformat(),
                "from_date": start_date.isoformat(),
                "to_date": end_date.isoformat(),
                "return_type": return_type,
            }

        all_items = returns_data.get("items", [])

        # Aggregate into channel-wise and SKU-wise breakdowns
        channel_map = {}
        sku_map = {}
        returns_list = []
        rto_count = 0
        cir_count = 0
        total_value = 0.0
        total_items_count = 0

        # Group items by saleOrderCode to form return entries
        from collections import defaultdict
        order_groups = defaultdict(list)
        for item in all_items:
            so_code = item.get("saleOrderCode", "UNKNOWN")
            order_groups[so_code].append(item)

        for so_code, items in order_groups.items():
            if not items:
                continue

            # Use the first item for return-level info
            first = items[0]
            rtype = first.get("returnType", "UNKNOWN")
            channel = first.get("channel", "UNKNOWN")

            if rtype == "RTO":
                rto_count += 1
            elif rtype == "CIR":
                cir_count += 1

            return_entry = {
                "code": first.get("invoiceCode", so_code),
                "type": rtype,
                "channel": channel,
                "status": "RETURNED",
                "created": "",
                "saleOrderCode": so_code,
                "items": [],
                "total_value": 0.0,
            }

            for item in items:
                sku = item.get("sku", "UNKNOWN")
                item_name = item.get("itemName", "")
                qty = item.get("quantity", 1)
                # Keep return valuation aligned with sales: unit selling price x quantity.
                unit_price = item.get("unitPrice", 0.0) or 0.0
                price = unit_price * qty

                total_items_count += qty
                total_value += price
                return_entry["total_value"] += price
                return_entry["items"].append({
                    "sku": sku,
                    "name": item_name,
                    "quantity": qty,
                    "price": price,
                })

                # SKU aggregation
                if sku not in sku_map:
                    sku_map[sku] = {
                        "sku": sku,
                        "name": item_name,
                        "quantity": 0,
                        "value": 0.0,
                        "return_count": 0,
                    }
                sku_map[sku]["quantity"] += qty
                sku_map[sku]["value"] += price
                sku_map[sku]["return_count"] += 1

            # Channel aggregation at the return level
            if channel not in channel_map:
                channel_map[channel] = {
                    "channel": channel,
                    "returns": 0,
                    "items": 0,
                    "value": 0.0,
                    "rto": 0,
                    "cir": 0,
                }
            channel_map[channel]["returns"] += 1
            channel_map[channel]["items"] += len(items)
            channel_map[channel]["value"] += return_entry["total_value"]
            if rtype == "RTO":
                channel_map[channel]["rto"] += 1
            else:
                channel_map[channel]["cir"] += 1

            returns_list.append(return_entry)

        by_channel = sorted(
            channel_map.values(), key=lambda x: x["value"], reverse=True
        )
        by_sku = sorted(
            sku_map.values(), key=lambda x: x["quantity"], reverse=True
        )

        for ch in by_channel:
            ch["value"] = round(ch["value"], 2)
        for s in by_sku:
            s["value"] = round(s["value"], 2)

        return {
            "success": True,
            "period": period_norm,
            "date": start_date.isoformat(),
            "from_date": start_date.isoformat(),
            "to_date": end_date.isoformat(),
            "return_type": return_type,
            "returns": returns_list,
            "by_channel": by_channel,
            "by_sku": by_sku,
            "totals": {
                "total_returns": len(returns_list),
                "total_items": total_items_count,
                "total_value": round(total_value, 2),
                "rto_count": rto_count,
                "cir_count": cir_count,
            },
            "search_results": {
                "export_items": len(all_items),
                "method": returns_data.get("data_source", "db_first_returns"),
                "total_time": 0,
            },
            "debug_info": {
                "failed_rto_codes": [],
                "failed_cir_codes": [],
                "total_failed_rto": 0,
                "total_failed_cir": 0,
            },
        }

    except Exception as e:
        logger.error(f"Error in return report: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/cancellation-report")
async def get_cancellation_report(
    date: str | None = Query(None, description="Date for report (YYYY-MM-DD)"),
    from_date: str | None = Query(None, description="Start date for custom report (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date for custom report (YYYY-MM-DD)"),
    period: str = Query("daily", description="daily, weekly, monthly, custom"),
):
    """
    Cancellation Report with channel-wise + SKU-wise + item-level breakdown.
    Uses DB-first sales data and includes only CANCELLED/CANCELED orders.
    """
    try:
        data_service = get_unicommerce_data_service()

        period_norm = (period or "daily").strip().lower()
        today_ist = datetime.now(IST).date()

        if period_norm == "custom" or (from_date and to_date):
            if not from_date or not to_date:
                return {
                    "success": False,
                    "error": "Both from_date and to_date are required for custom range",
                    "period": "custom",
                }
            start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(to_date, "%Y-%m-%d").date()
            period_norm = "custom"
        elif period_norm == "weekly":
            current_week_start = today_ist - timedelta(days=today_ist.weekday())
            start_date = current_week_start - timedelta(days=7)
            end_date = current_week_start - timedelta(days=1)
        elif period_norm == "monthly":
            base_date = datetime.strptime(date, "%Y-%m-%d").date() if date else (today_ist - timedelta(days=1))
            start_date = base_date.replace(day=1)

            if base_date.year == today_ist.year and base_date.month == today_ist.month:
                # Current month: use month-to-date so users can load ongoing month data.
                end_date = today_ist - timedelta(days=1)
            else:
                # Past month: use full calendar month of the selected anchor date.
                if base_date.month == 12:
                    first_next_month = date_cls(base_date.year + 1, 1, 1)
                else:
                    first_next_month = date_cls(base_date.year, base_date.month + 1, 1)
                end_date = first_next_month - timedelta(days=1)
        else:
            base_date = datetime.strptime(date, "%Y-%m-%d").date() if date else (today_ist - timedelta(days=1))
            start_date = base_date
            end_date = base_date
            period_norm = "daily"

        if start_date > end_date:
            return {
                "success": False,
                "error": "from_date cannot be greater than to_date",
                "period": period_norm,
                "from_date": start_date.isoformat(),
                "to_date": end_date.isoformat(),
            }

        from_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=IST).astimezone(timezone.utc)
        to_dt = datetime.combine(end_date, datetime.max.time().replace(microsecond=0)).replace(tzinfo=IST).astimezone(timezone.utc)

        sales_result = data_service.get_sales_data(
            period="custom",
            from_date=from_dt,
            to_date=to_dt,
        )
        if not sales_result.get("success", False):
            return {
                "success": False,
                "error": sales_result.get("error", "Failed to fetch orders"),
                "period": period_norm,
                "from_date": start_date.isoformat(),
                "to_date": end_date.isoformat(),
            }

        raw_orders = sales_result.get("_orders", [])
        total_fetch_time = float(sales_result.get("fetch_info", {}).get("total_time_seconds", 0) or 0)
        total_orders_all = len(raw_orders)
        cancelled_statuses = {"CANCELLED", "CANCELED"}

        def _fmt_created(raw_val) -> str:
            raw = str(raw_val or "").strip()
            if not raw:
                return ""
            try:
                numeric = float(raw)
                if numeric > 1e12:
                    numeric = numeric / 1000.0
                dt = datetime.fromtimestamp(numeric, tz=timezone.utc).astimezone(IST)
                return dt.strftime("%d/%m/%Y %H:%M:%S")
            except (ValueError, TypeError, OverflowError, OSError):
                pass
            try:
                iso_raw = raw.replace("Z", "+00:00")
                dt = datetime.fromisoformat(iso_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=IST)
                else:
                    dt = dt.astimezone(IST)
                return dt.strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                return raw

        cancellations = []
        items_flat = []
        channel_map = {}
        sku_map = {}
        daily_map = {}

        total_cancelled_orders = 0
        total_cancelled_items = 0
        total_cancelled_value = 0.0
        cod_orders = 0
        prepaid_orders = 0

        for order in raw_orders:
            status = (order.get("status") or "").upper()
            if status not in cancelled_statuses:
                continue

            total_cancelled_orders += 1
            channel = order.get("channel", "UNKNOWN")
            order_code = order.get("code", "")
            created_raw = order.get("created") or order.get("displayOrderDateTime")
            created_fmt = _fmt_created(created_raw)
            is_cod = bool(order.get("cod") or order.get("cashOnDelivery"))
            if is_cod:
                cod_orders += 1
            else:
                prepaid_orders += 1

            order_entry = {
                "sale_order_code": order_code,
                "channel": channel,
                "status": status,
                "created": created_fmt,
                "cod": is_cod,
                "items": [],
                "total_items": 0,
                "total_value": 0.0,
            }

            if channel not in channel_map:
                channel_map[channel] = {
                    "channel": channel,
                    "cancellations": 0,
                    "items": 0,
                    "value": 0.0,
                    "cod": 0,
                    "prepaid": 0,
                }
            channel_map[channel]["cancellations"] += 1
            if is_cod:
                channel_map[channel]["cod"] += 1
            else:
                channel_map[channel]["prepaid"] += 1

            day_key = created_fmt[:10] if len(created_fmt) >= 10 else str(start_date)
            if day_key not in daily_map:
                daily_map[day_key] = {
                    "date": day_key,
                    "cancellations": 0,
                    "items": 0,
                    "value": 0.0,
                }
            daily_map[day_key]["cancellations"] += 1

            for item in order.get("saleOrderItems", []):
                sku = item.get("itemSku", "")
                name = item.get("itemTypeName") or item.get("itemName") or sku
                soi_code = item.get("code", "")
                try:
                    qty = int(float(item.get("quantity", 1) or 1))
                except (ValueError, TypeError):
                    qty = 1
                if qty <= 0:
                    qty = 1

                try:
                    selling = float(item.get("sellingPrice", 0) or 0)
                except (ValueError, TypeError):
                    selling = 0.0
                line_value = selling * qty

                total_cancelled_items += qty
                total_cancelled_value += line_value
                order_entry["total_items"] += qty
                order_entry["total_value"] += line_value
                channel_map[channel]["items"] += qty
                channel_map[channel]["value"] += line_value
                daily_map[day_key]["items"] += qty
                daily_map[day_key]["value"] += line_value

                order_entry["items"].append({
                    "sale_order_item_code": soi_code,
                    "sku": sku,
                    "name": name,
                    "quantity": qty,
                    "selling_price": round(selling, 2),
                    "line_value": round(line_value, 2),
                })

                items_flat.append({
                    "sale_order_code": order_code,
                    "sale_order_item_code": soi_code,
                    "channel": channel,
                    "status": status,
                    "created": created_fmt,
                    "cod": is_cod,
                    "sku": sku,
                    "name": name,
                    "quantity": qty,
                    "selling_price": round(selling, 2),
                    "line_value": round(line_value, 2),
                })

                if sku not in sku_map:
                    sku_map[sku] = {
                        "sku": sku,
                        "name": name,
                        "quantity": 0,
                        "value": 0.0,
                        "cancellation_count": 0,
                    }
                sku_map[sku]["quantity"] += qty
                sku_map[sku]["value"] += line_value
                sku_map[sku]["cancellation_count"] += 1

            order_entry["total_value"] = round(order_entry["total_value"], 2)
            cancellations.append(order_entry)

        by_channel = sorted(channel_map.values(), key=lambda x: x["value"], reverse=True)
        by_sku = sorted(sku_map.values(), key=lambda x: x["value"], reverse=True)
        daily_trend = sorted(daily_map.values(), key=lambda x: x["date"])

        for c in by_channel:
            c["value"] = round(c["value"], 2)
        for s in by_sku:
            s["value"] = round(s["value"], 2)
        for d in daily_trend:
            d["value"] = round(d["value"], 2)

        cancellation_rate = (
            (total_cancelled_orders / total_orders_all) * 100
            if total_orders_all > 0 else 0.0
        )

        return {
            "success": True,
            "period": period_norm,
            "date": start_date.isoformat(),
            "from_date": start_date.isoformat(),
            "to_date": end_date.isoformat(),
            "cancellations": cancellations,
            "items": items_flat,
            "by_channel": by_channel,
            "by_sku": by_sku,
            "daily_trend": daily_trend,
            "totals": {
                "total_orders": total_orders_all,
                "total_cancellations": total_cancelled_orders,
                "total_items": total_cancelled_items,
                "total_value": round(total_cancelled_value, 2),
                "cod_orders": cod_orders,
                "prepaid_orders": prepaid_orders,
                "cancellation_rate": round(cancellation_rate, 2),
            },
            "search_results": {
                "export_orders": total_orders_all,
                "method": sales_result.get("data_source", "db_first_sales_orders"),
                "total_time": round(total_fetch_time, 2),
                "chunk_count": 1,
            },
        }

    except Exception as e:
        logger.error(f"Error in cancellation report: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# Best performing SKUs (monthly)

@router.get("/unicommerce/best-skus-monthly")
async def get_best_skus_monthly(
    month: int = Query(None, description="Month (1-12), defaults to current"),
    year: int = Query(None, description="Year, defaults to current"),
    limit: int = Query(20, description="Number of top SKUs"),
    force_refresh: bool = Query(
        False, description="Bypass cache and re-fetch"),
    b2c_only: bool = Query(
        False, description="Exclude unpriced wholesale/B2B orders (sellingPrice=0 AND maxRetailPrice=0)"),
):
    """
    Get best performing SKUs for a given month.
    Uses Redis cache: current month=1hr TTL, historical=24hr TTL.
    Revenue uses sellingPrice; falls back to maxRetailPrice (AMAZON_FLEX etc.).
    Wholesale/B2B SHOPIFY bulk orders have genuinely-zero prices in Unicommerce
    (invoicing is handled externally). Use b2c_only=true to exclude them.
    """
    try:
        data_service = get_unicommerce_data_service()
        now = datetime.now(IST)
        m = month or now.month
        y = year or now.year

        # Check Redis cache first (skip if force_refresh)
        cache_suffix = "b2c" if b2c_only else "all"
        cache_key = f"uc:best_skus:{y}:{m}:{limit}:{cache_suffix}"
        if not force_refresh:
            cached = CacheService.get(cache_key)
            if cached:
                logger.info(f"BEST SKUs {y}-{m:02d}: Redis cache hit")
                cached["_cached"] = True
                return cached
        else:
            CacheService.delete(cache_key)
            logger.info(
                f"BEST SKUs {y}-{m:02d}: Force refresh - cache cleared")

        logger.info(f"BEST SKUs {y}-{m:02d}: Cache miss, fetching from DB...")

        from_dt = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
        if m == 12:
            to_dt = datetime(y + 1, 1, 1, 0, 0, 0,
                             tzinfo=timezone.utc) - timedelta(seconds=1)
        else:
            to_dt = datetime(y, m + 1, 1, 0, 0, 0,
                             tzinfo=timezone.utc) - timedelta(seconds=1)

        # Cap to_dt to now if in current month
        if to_dt > now.replace(tzinfo=timezone.utc):
            to_dt = now.replace(tzinfo=timezone.utc)

        sales_result = data_service.get_sales_data(
            period="custom",
            from_date=from_dt,
            to_date=to_dt,
        )
        if not sales_result.get("success", False):
            return {"success": False, "error": "Failed to fetch orders"}

        raw_orders = sales_result.get("_orders", [])

        # Aggregate by SKU
        sku_map = {}
        for order in raw_orders:
            status = order.get("status", "")
            if status in EXCLUDED_REVENUE_STATUSES:
                continue
            channel = order.get("channel", "UNKNOWN")
            for item in order.get("saleOrderItems", []):
                sku = item.get("itemSku", "UNKNOWN")
                qty = item.get("quantity", 1) or 1
                # Use sellingPrice; fall back to maxRetailPrice (e.g. AMAZON_FLEX)
                selling_price = float(item.get("sellingPrice", 0) or 0)
                mrp = float(item.get("maxRetailPrice", 0) or 0)
                price = selling_price if selling_price > 0 else mrp
                price_estimated = (selling_price == 0 and mrp > 0)
                # Unpriced: both sellingPrice and MRP are 0 (wholesale B2B orders
                # where invoicing is handled externally, e.g. SHOPIFY B2B bulk)
                is_unpriced = (selling_price == 0 and mrp == 0)

                # If b2c_only mode, skip unpriced wholesale items entirely
                if b2c_only and is_unpriced:
                    continue

                if sku not in sku_map:
                    sku_map[sku] = {
                        "sku": sku, "name": item.get("itemName", ""),
                        "quantity": 0, "revenue": 0.0, "order_count": 0,
                        "channels": {}, "estimated": False,
                        "_unpriced_qty": 0,  # temporary: items with ₹0 prices
                    }
                sku_map[sku]["quantity"] += qty
                sku_map[sku]["revenue"] += price * qty
                sku_map[sku]["order_count"] += 1
                if is_unpriced:
                    sku_map[sku]["_unpriced_qty"] += qty
                if price_estimated:
                    # Flag MRP-estimated revenue
                    sku_map[sku]["estimated"] = True
                if channel not in sku_map[sku]["channels"]:
                    sku_map[sku]["channels"][channel] = 0
                sku_map[sku]["channels"][channel] += qty

        for s in sku_map.values():
            s["revenue"] = round(s["revenue"], 2)
            s["avg_price"] = round(
                s["revenue"] / s["quantity"], 2) if s["quantity"] > 0 else 0
            # Mark as unpriced if ALL units came from wholesale (₹0 items)
            s["unpriced"] = (s["_unpriced_qty"] >= s["quantity"])
            del s["_unpriced_qty"]  # Remove temp field

        top_skus = sorted(sku_map.values(),
                          key=lambda x: x["quantity"], reverse=True)[:limit]

        unpriced_count = sum(1 for s in top_skus if s.get("unpriced"))
        result = {
            "success": True,
            "month": m, "year": y,
            "period": f"{y}-{m:02d}",
            "total_skus": len(sku_map),
            "total_orders": len(raw_orders),
            "skus": top_skus,
            "b2c_only": b2c_only,
            "unpriced_in_top": unpriced_count,
        }

        # Cache: current month 1hr, historical 24hr
        is_current = (y == now.year and m == now.month)
        ttl = CacheService.TTL_VERY_LONG if is_current else 86400
        CacheService.set(cache_key, result, ttl)
        logger.info(f"BEST SKUs {y}-{m:02d}: Cached (TTL={ttl}s)")

        return result

    except Exception as e:
        logger.error(f"Error in best-skus-monthly: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ── Bundle SKU Catalog (Item Master Export) ───────────────────────────

@router.get("/unicommerce/bundle-skus")
async def get_bundle_skus(
    force_refresh: bool = Query(False, description="Bypass cache and re-fetch"),
):
    """
    Get all BUNDLE type SKUs from Unicommerce Item Master export.
    Returns deduplicated bundle records with aggregated component arrays.
    This is catalogue data — cached for 4 hours.  No date filtering
    because UC's 'Updated' column only reflects item-record edits, not
    business events. Use the frontend category / search filters instead.
    """
    try:
        data_service = get_unicommerce_data_service()
        return await data_service.get_bundle_skus(force_refresh=force_refresh)

    except Exception as e:
        logger.error(f"Error in bundle-skus: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ── Bundle Sales Analysis Dashboard ──────────────────────────────────

@router.get("/unicommerce/bundle-sales-analysis")
async def get_bundle_sales_analysis(
    period: str = Query("last_30_days", description="today|yesterday|last_7_days|last_30_days|custom"),
    from_date: str = Query(None, description="YYYY-MM-DD (required for custom)"),
    to_date: str = Query(None, description="YYYY-MM-DD (required for custom)"),
    force_refresh: bool = Query(False, description="Bypass cache"),
):
    """
    Bundle Sales Analysis: reverse-maps component SKUs in sale orders
    back to their parent bundles.  Returns daily trends, category & channel
    breakdown, and per-bundle sales metrics.
    """
    try:
        data_service = get_unicommerce_data_service()
        return await data_service.get_bundle_sales_analysis(
            period=period,
            from_date=from_date,
            to_date=to_date,
            force_refresh=force_refresh,
        )

    except Exception as e:
        logger.error(f"Error in bundle-sales-analysis: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ── Fabric Sales ──────────────────────────────────────────────────────

@router.get("/unicommerce/fabric-sales")
async def get_fabric_sales(
    month: int = Query(None, description="Month (1-12), defaults to current"),
    year: int = Query(None, description="Year, defaults to current"),
    from_date: str = Query(None, description="Custom start date (YYYY-MM-DD)"),
    to_date: str = Query(None, description="Custom end date (YYYY-MM-DD)"),
    force_refresh: bool = Query(False, description="Bypass cache and re-fetch"),
):
    """
    Get sales data for items in the FABRIC category.
    These are excluded from normal sales endpoints and shown separately.
    Supports monthly (month+year) or custom date range (from_date+to_date).
    """
    try:
        data_service = get_unicommerce_data_service()
        return await data_service.get_fabric_sales(
            month=month,
            year=year,
            from_date=from_date,
            to_date=to_date,
            force_refresh=force_refresh,
        )

    except Exception as e:
        logger.error(f"Error in fabric-sales: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# SKU velocity (monthly)

@router.get("/unicommerce/sku-velocity")
async def get_sku_velocity(
    month: int = Query(None, description="Month (1-12), defaults to current"),
    year: int = Query(None, description="Year, defaults to current"),
    limit: int = Query(
        25, description="Number of SKUs per category (fast/slow)"),
    min_qty: int = Query(
        1, description="Minimum qty sold to be considered 'slow mover' (excludes zero-sale SKUs)"),
    b2c_only: bool = Query(
        False, description="Exclude wholesale/B2B unpriced orders"),
    force_refresh: bool = Query(
        False, description="Bypass cache and re-fetch"),
):
    """
    Get fast-moving and slow-moving SKUs for a given month.
    - Fast movers: top N SKUs by quantity sold.
    - Slow movers: bottom N SKUs by quantity sold (with at least min_qty sales).
    Uses Redis cache: current month 1hr TTL, historical 24hr TTL.
    """
    try:
        data_service = get_unicommerce_data_service()
        now = datetime.now(IST)
        m = month or now.month
        y = year or now.year

        cache_suffix = "b2c" if b2c_only else "all"
        cache_key = f"uc:sku_velocity:{y}:{m}:{limit}:{min_qty}:{cache_suffix}"

        if not force_refresh:
            cached = CacheService.get(cache_key)
            if cached:
                logger.info(f"SKU VELOCITY {y}-{m:02d}: Redis cache hit")
                cached["_cached"] = True
                return cached
        else:
            CacheService.delete(cache_key)
            logger.info(
                f"SKU VELOCITY {y}-{m:02d}: Force refresh - cache cleared")

        logger.info(
            f"SKU VELOCITY {y}-{m:02d}: Cache miss, fetching from DB...")

        from_dt = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
        if m == 12:
            to_dt = datetime(y + 1, 1, 1, 0, 0, 0,
                             tzinfo=timezone.utc) - timedelta(seconds=1)
        else:
            to_dt = datetime(y, m + 1, 1, 0, 0, 0,
                             tzinfo=timezone.utc) - timedelta(seconds=1)

        if to_dt > now.replace(tzinfo=timezone.utc):
            to_dt = now.replace(tzinfo=timezone.utc)

        sales_result = data_service.get_sales_data(
            period="custom",
            from_date=from_dt,
            to_date=to_dt,
        )
        if not sales_result.get("success", False):
            return {"success": False, "error": "Failed to fetch orders"}

        raw_orders = sales_result.get("_orders", [])

        # Aggregate by SKU (same logic as best-skus-monthly)
        sku_map = {}
        for order in raw_orders:
            status = order.get("status", "")
            if status in EXCLUDED_REVENUE_STATUSES:
                continue
            channel = order.get("channel", "UNKNOWN")
            for item in order.get("saleOrderItems", []):
                sku = item.get("itemSku", "UNKNOWN")
                qty = item.get("quantity", 1) or 1
                selling_price = float(item.get("sellingPrice", 0) or 0)
                mrp = float(item.get("maxRetailPrice", 0) or 0)
                price = selling_price if selling_price > 0 else mrp
                price_estimated = (selling_price == 0 and mrp > 0)
                is_unpriced = (selling_price == 0 and mrp == 0)

                if b2c_only and is_unpriced:
                    continue

                if sku not in sku_map:
                    sku_map[sku] = {
                        "sku": sku,
                        "name": item.get("itemName", ""),
                        "quantity": 0,
                        "revenue": 0.0,
                        "order_count": 0,
                        "channels": {},
                        "estimated": False,
                        "unpriced": False,
                        "_unpriced_qty": 0,
                    }
                sku_map[sku]["quantity"] += qty
                sku_map[sku]["revenue"] += price * qty
                sku_map[sku]["order_count"] += 1
                if is_unpriced:
                    sku_map[sku]["_unpriced_qty"] += qty
                if price_estimated:
                    sku_map[sku]["estimated"] = True
                if channel not in sku_map[sku]["channels"]:
                    sku_map[sku]["channels"][channel] = 0
                sku_map[sku]["channels"][channel] += qty

        for s in sku_map.values():
            s["revenue"] = round(s["revenue"], 2)
            s["avg_price"] = round(
                s["revenue"] / s["quantity"], 2) if s["quantity"] > 0 else 0
            s["unpriced"] = (s["_unpriced_qty"] >= s["quantity"])
            del s["_unpriced_qty"]

        all_skus = list(sku_map.values())

        # Fast movers: top N by quantity (descending)
        fast_movers = sorted(
            all_skus, key=lambda x: x["quantity"], reverse=True)[:limit]

        # Slow movers: bottom N with at least min_qty (ascending, exclude zero sellers)
        qualified = [s for s in all_skus if s["quantity"] >= min_qty]
        slow_movers = sorted(qualified, key=lambda x: x["quantity"])[:limit]

        result = {
            "success": True,
            "month": m,
            "year": y,
            "period": f"{y}-{m:02d}",
            "total_skus": len(all_skus),
            "total_orders": len(raw_orders),
            "b2c_only": b2c_only,
            "fast_movers": fast_movers,
            "slow_movers": slow_movers,
            "fast_count": len(fast_movers),
            "slow_count": len(slow_movers),
        }

        is_current = (y == now.year and m == now.month)
        ttl = CacheService.TTL_VERY_LONG if is_current else 86400
        CacheService.set(cache_key, result, ttl)
        logger.info(f"SKU VELOCITY {y}-{m:02d}: Cached (TTL={ttl}s)")

        return result

    except Exception as e:
        logger.error(f"Error in sku-velocity: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# COD vs prepaid (monthly)

@router.get("/unicommerce/cod-vs-prepaid")
async def get_cod_vs_prepaid(
    period: str = Query("monthly", description="daily, weekly, monthly, custom"),
    date: str = Query(None, description="Anchor date for daily/weekly/monthly (YYYY-MM-DD)"),
    from_date: str = Query(None, description="Custom start date (YYYY-MM-DD)"),
    to_date: str = Query(None, description="Custom end date (YYYY-MM-DD)"),
    month: int = Query(None, description="Month (1-12), defaults to current"),
    year: int = Query(None, description="Year, defaults to current"),
):
    """Get COD vs Prepaid breakdown for a date range with Redis caching."""
    try:
        data_service = get_unicommerce_data_service()
        now = datetime.now(IST)

        period_norm = (period or "monthly").strip().lower()

        if from_date and to_date:
            start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(to_date, "%Y-%m-%d").date()
            period_norm = "custom"
        elif period_norm == "custom":
            if not from_date or not to_date:
                return {
                    "success": False,
                    "error": "Both from_date and to_date are required for custom period",
                }
            start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(to_date, "%Y-%m-%d").date()
        elif period_norm in {"daily", "weekly", "monthly"}:
            anchor = datetime.strptime(date, "%Y-%m-%d").date() if date else now.date()
            if period_norm == "daily":
                start_date = anchor
                end_date = anchor
            elif period_norm == "weekly":
                # Last completed Monday-Sunday week
                current_week_start = now.date() - timedelta(days=now.date().weekday())
                start_date = current_week_start - timedelta(days=7)
                end_date = current_week_start - timedelta(days=1)
            else:
                # Last completed calendar month
                first_of_current_month = now.date().replace(day=1)
                end_date = first_of_current_month - timedelta(days=1)
                start_date = end_date.replace(day=1)
        else:
            # Backward compatibility: month/year selectors map to monthly range.
            m = month or now.month
            y = year or now.year
            start_date = datetime(y, m, 1).date()
            if m == 12:
                end_date = datetime(y, 12, 31).date()
            else:
                end_date = (datetime(y, m + 1, 1) - timedelta(days=1)).date()
            period_norm = "monthly"

        if start_date > end_date:
            return {"success": False, "error": "from_date cannot be greater than to_date"}

        # Check Redis cache (persistent across workers/restarts)
        cache_key = f"uc:cod_prepaid:{period_norm}:{start_date.isoformat()}:{end_date.isoformat()}"
        cached = CacheService.get(cache_key)
        if cached:
            logger.info(
                f"COD vs Prepaid {start_date.isoformat()} to {end_date.isoformat()}: Redis cache hit"
            )
            cached["_cached"] = True
            return cached

        from_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=IST).astimezone(timezone.utc)
        to_dt = datetime.combine(end_date, datetime.max.time().replace(microsecond=0)).replace(tzinfo=IST).astimezone(timezone.utc)

        if to_dt > now.replace(tzinfo=timezone.utc):
            to_dt = now.replace(tzinfo=timezone.utc)

        logger.info(
            f"COD vs Prepaid: fetching orders from {from_dt.date()} to {to_dt.date()} from DB")
        sales_result = data_service.get_sales_data(
            period="custom",
            from_date=from_dt,
            to_date=to_dt,
        )
        logger.info(
            f"COD vs Prepaid: fetched {len(sales_result.get('_orders', []))} orders")
        if not sales_result.get("success", False):
            return {"success": False, "error": "Failed to fetch orders"}

        raw_orders = sales_result.get("_orders", [])

        cod_orders = 0
        cod_revenue = 0.0
        cod_items = 0
        prepaid_orders = 0
        prepaid_revenue = 0.0
        prepaid_items = 0
        channel_breakdown = {}

        for order in raw_orders:
            status = order.get("status", "")
            if status in EXCLUDED_REVENUE_STATUSES:
                continue

            # COD detection: use the direct `cod` boolean from the order.
            # Export CSV provides reliable 1/0 column; saleOrderDTO.cod is
            # authoritative.  Previous triple-check (shippingMethod containing
            # "COD" or collectableAmount > 0) caused massive false positives.
            is_cod = bool(order.get("cod", False))
            channel = order.get("channel", "UNKNOWN")
            order_revenue = 0.0
            order_items = 0

            for item in order.get("saleOrderItems", []):
                qty = item.get("quantity", 1) or 1
                price = float(item.get("sellingPrice", 0) or 0)
                order_revenue += price
                order_items += qty

            if is_cod:
                cod_orders += 1
                cod_revenue += order_revenue
                cod_items += order_items
            else:
                prepaid_orders += 1
                prepaid_revenue += order_revenue
                prepaid_items += order_items

            if channel not in channel_breakdown:
                channel_breakdown[channel] = {
                    "cod_orders": 0, "cod_revenue": 0, "prepaid_orders": 0, "prepaid_revenue": 0}
            if is_cod:
                channel_breakdown[channel]["cod_orders"] += 1
                channel_breakdown[channel]["cod_revenue"] += order_revenue
            else:
                channel_breakdown[channel]["prepaid_orders"] += 1
                channel_breakdown[channel]["prepaid_revenue"] += order_revenue

        total_orders = cod_orders + prepaid_orders
        total_revenue = cod_revenue + prepaid_revenue

        logger.info(
            f"COD vs Prepaid: processed {total_orders} orders ({cod_orders} COD, {prepaid_orders} Prepaid) "
            f"for {start_date.isoformat()} to {end_date.isoformat()}")

        for ch in channel_breakdown.values():
            ch["cod_revenue"] = round(ch["cod_revenue"], 2)
            ch["prepaid_revenue"] = round(ch["prepaid_revenue"], 2)

        channels = sorted(
            [{"channel": k, **v} for k, v in channel_breakdown.items()],
            key=lambda x: x["cod_orders"] + x["prepaid_orders"], reverse=True,
        )

        result = {
            "success": True,
            "period": period_norm,
            "from_date": start_date.isoformat(),
            "to_date": end_date.isoformat(),
            "cod": {
                "orders": cod_orders, "revenue": round(cod_revenue, 2), "items": cod_items,
                "percentage": round(cod_orders / total_orders * 100, 1) if total_orders > 0 else 0,
                "avg_order_value": round(cod_revenue / cod_orders, 2) if cod_orders > 0 else 0,
            },
            "prepaid": {
                "orders": prepaid_orders, "revenue": round(prepaid_revenue, 2), "items": prepaid_items,
                "percentage": round(prepaid_orders / total_orders * 100, 1) if total_orders > 0 else 0,
                "avg_order_value": round(prepaid_revenue / prepaid_orders, 2) if prepaid_orders > 0 else 0,
            },
            "total_orders": total_orders,
            "total_revenue": round(total_revenue, 2),
            "channels": channels,
        }

        # Preserve legacy fields for consumers still expecting month/year.
        result["month"] = start_date.month
        result["year"] = start_date.year

        # Redis cache: current month 4hr, historical 24hr
        is_current = (start_date.year == now.year and start_date.month == now.month and end_date >= now.date())
        ttl = 14400 if is_current else 86400
        CacheService.set(cache_key, result, ttl)
        logger.info(
            f"COD vs Prepaid: cached result for {start_date.isoformat()} to {end_date.isoformat()} (TTL={ttl}s)")

        return result

    except Exception as e:
        logger.error(f"Error in cod-vs-prepaid: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# WebSocket endpoints

@router.websocket("/ws/sales")
async def websocket_sales(websocket: WebSocket):
    """
    WebSocket endpoint for real-time sales dashboard updates.
    Sends today's sales summary every 60 seconds automatically.
    Clients can also send requests: {"action": "refresh"} to trigger immediate update.
    """
    await ws_manager.connect(websocket)
    try:
        # Send initial data immediately
        try:
            today_key = f"uc:today:{datetime.now(IST).strftime('%Y-%m-%d')}"
            cached = CacheService.get(today_key)
            if cached:
                await websocket.send_json({"type": "today_sales", "data": cached})
        except Exception:
            pass

        while True:
            try:
                # Wait for client message (with timeout for periodic push)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                msg = json_module.loads(data)

                if msg.get("action") == "refresh":
                    # Client requests fresh data
                    data_service = get_unicommerce_data_service()
                    result = data_service.get_sales_data(period="today")
                    if result.get("success"):
                        today_key = f"uc:today:{datetime.now(IST).strftime('%Y-%m-%d')}"
                        CacheService.set(today_key, result, 180)
                        await websocket.send_json({"type": "today_sales", "data": result})

                elif msg.get("action") == "subscribe":
                    await websocket.send_json({"type": "subscribed", "message": "Connected to live feed"})

            except asyncio.TimeoutError:
                # Periodic push: send cached data every 60s
                try:
                    today_key = f"uc:today:{datetime.now(IST).strftime('%Y-%m-%d')}"
                    cached = CacheService.get(today_key)
                    if cached:
                        await websocket.send_json({"type": "today_sales", "data": cached})
                except Exception as e:
                    logger.warning(f"WebSocket periodic send failed; disconnecting client: {e}")
                    ws_manager.disconnect(websocket)
                    break

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


@router.websocket("/ws/inventory")
async def websocket_inventory(websocket: WebSocket):
    """WebSocket endpoint for real-time inventory updates."""
    from app.services.websocket_manager import ws_manager as global_ws_manager
    await global_ws_manager.connect(websocket, "inventory")
    try:
        await websocket.send_json({"type": "connected", "message": "Connected to inventory updates"})
        while True:
            # Wait for client pings or messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        global_ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket inventory error: {e}")
        global_ws_manager.disconnect(websocket)


@router.websocket("/ws/orders")
async def websocket_orders(websocket: WebSocket):
    """WebSocket endpoint for real-time order status updates."""
    from app.services.websocket_manager import ws_manager as global_ws_manager
    await global_ws_manager.connect(websocket, "orders")
    try:
        await websocket.send_json({"type": "connected", "message": "Connected to order updates"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        global_ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket orders error: {e}")
        global_ws_manager.disconnect(websocket)


@router.websocket("/ws/production")
async def websocket_production(websocket: WebSocket):
    """WebSocket endpoint for real-time production plan updates."""
    from app.services.websocket_manager import ws_manager as global_ws_manager
    await global_ws_manager.connect(websocket, "production")
    try:
        await websocket.send_json({"type": "connected", "message": "Connected to production updates"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        global_ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket production error: {e}")
        global_ws_manager.disconnect(websocket)


@router.websocket("/ws/all")
async def websocket_all(websocket: WebSocket):
    """WebSocket endpoint subscribing to all event types."""
    from app.services.websocket_manager import ws_manager as global_ws_manager
    await global_ws_manager.connect(websocket, "all")
    try:
        await websocket.send_json({"type": "connected", "message": "Connected to all updates"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        global_ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket all events error: {e}")
        global_ws_manager.disconnect(websocket)


# REDIS CACHE MANAGEMENT ENDPOINTS

@router.get("/cache/redis/stats")
async def get_redis_cache_stats():
    """Get Redis cache statistics and keys info."""
    try:
        from app.core.redis import redis_client

        if not redis_client:
            return {"success": False, "error": "Redis not connected"}

        keys = redis_client.keys("uc:*")
        cache_keys = {}
        for key in keys:
            try:
                ttl = redis_client.ttl(key)
                cache_keys[key] = {
                    "ttl_seconds": ttl,
                    "expires_in": f"{ttl // 3600}h {(ttl % 3600) // 60}m" if ttl > 0 else "no-expiry"
                }
            except Exception:
                cache_keys[key] = {"error": "Could not read"}

        info = redis_client.info("stats")
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses

        return {
            "success": True,
            "total_keys": len(keys),
            "keys": cache_keys,
            "stats": {
                "hits": hits,
                "misses": misses,
                "hit_rate": round((hits / total * 100) if total > 0 else 0, 2)
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/cache/redis/invalidate")
async def invalidate_redis_cache(
    pattern: str = Query("uc:*", description="Key pattern to invalidate")
):
    """Invalidate Redis cache keys matching a pattern."""
    try:
        CacheService.delete_pattern(pattern)
        return {"success": True, "message": f"Invalidated keys matching: {pattern}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
