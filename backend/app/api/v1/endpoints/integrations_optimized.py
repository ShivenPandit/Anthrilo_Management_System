"""
Unicommerce Integration API Endpoints - PRODUCTION VERSION (v2)
================================================================
Accurate revenue using sellingPrice ONLY with two-phase fetch.

Includes:
- Summary endpoints (today, yesterday, 7-days, 30-days)
- Paginated order listing
- Background sync endpoints
- Sync status monitoring
- Cache management
- Revenue validation
"""

from fastapi import APIRouter, Query, BackgroundTasks, WebSocket, WebSocketDisconnect
import logging
import asyncio
import json as json_module
from datetime import datetime, timezone, timedelta
from app.services.unicommerce_optimized import get_unicommerce_service
from app.services.sync_service import get_sync_service
from app.core.token_manager import get_token_manager
from app.services.cache_service import CacheService

router = APIRouter()
logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


# =============================================================================
# WEBSOCKET CONNECTION MANAGER
# =============================================================================

class ConnectionManager:
    """Manages WebSocket connections for real-time dashboard updates."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send data to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)


ws_manager = ConnectionManager()


# =============================================================================
# SUMMARY ENDPOINTS (For dashboard cards)
# =============================================================================

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
        service = get_unicommerce_service()
        result = await service.get_today_sales()

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
        service = get_unicommerce_service()
        result = await service.get_yesterday_sales()

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
        service = get_unicommerce_service()
        result = await service.get_last_7_days_sales()

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


# =============================================================================
# PAGINATED ENDPOINTS (For order listing - 12 orders per page)
# =============================================================================

@router.get("/unicommerce/orders/today")
async def get_today_orders_paginated(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(12, ge=1, le=100, description="Orders per page")
):
    """Get today's orders with pagination."""
    try:
        service = get_unicommerce_service()
        return await service.get_today_orders_paginated(page, page_size)
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
        service = get_unicommerce_service()
        return await service.get_yesterday_orders_paginated(page, page_size)
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
        service = get_unicommerce_service()
        return await service.get_last_7_days_orders_paginated(page, page_size)
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

        service = get_unicommerce_service()
        return await service.get_orders_paginated(from_dt, to_dt, page, page_size)

    except ValueError as e:
        return {"success": False, "error": f"Invalid date format: {e}"}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# SALES REPORT ENDPOINT
# =============================================================================

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

        service = get_unicommerce_service()

        if period == "today":
            result = await service.get_today_sales()
        elif period == "yesterday":
            result = await service.get_yesterday_sales()
        elif period == "last_7_days":
            result = await service.get_last_7_days_sales()
        elif period == "custom" and from_date and to_date:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc
            )
            to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
            result = await service.get_custom_range_sales(from_dt, to_dt)
        else:
            result = await service.get_today_sales()

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
    date: str = Query(..., description="Date for report (YYYY-MM-DD)")
):
    """
    Get Daily Sales Report with channel-wise breakdown.

    Returns:
    - Channel Name (unique)
    - Quantity of Items (total items per channel)
    - Selling Price (sum of sellingPrice per channel)

    Uses existing saleorder/get data if available, otherwise fetches fresh data.
    """
    try:
        service = get_unicommerce_service()

        # Parse the date
        report_date = datetime.strptime(date, "%Y-%m-%d").date()
        today = datetime.now(timezone.utc).date()
        yesterday = today - timedelta(days=1)

        # Check if we can reuse existing cached data
        result = None
        if report_date == today:
            result = await service.get_today_sales()
        elif report_date == yesterday:
            result = await service.get_yesterday_sales()
        else:
            # Fetch custom date range (full day)
            from_dt = datetime.strptime(date, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc
            )
            to_dt = datetime.strptime(date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
            result = await service.get_custom_range_sales(from_dt, to_dt)

        if not result.get("success"):
            return result

        # Extract channel breakdown data
        channel_breakdown = result.get(
            "summary", {}).get("channel_breakdown", {})

        # Transform to report format
        # Group by channel with quantity and selling price
        report_data = []
        for channel_name, channel_data in channel_breakdown.items():
            report_data.append({
                "channel_name": channel_name,
                # Total items in channel
                "quantity": channel_data.get("items", 0),
                # Sum of sellingPrice
                "selling_price": channel_data.get("revenue", 0),
                "orders": channel_data.get("orders", 0),  # Number of orders
            })

        # Sort by revenue (highest first)
        report_data.sort(key=lambda x: x["selling_price"], reverse=True)

        # Calculate totals
        total_quantity = sum(item["quantity"] for item in report_data)
        total_revenue = sum(item["selling_price"] for item in report_data)
        total_orders = result.get("summary", {}).get(
            "valid_orders", 0)  # Only valid orders
        total_all_orders = result.get("summary", {}).get(
            "total_orders", 0)  # All orders
        excluded_items = result.get("summary", {}).get(
            "total_items", 0) - total_quantity

        return {
            "success": True,
            "date": date,
            "report": report_data,
            "totals": {
                "total_channels": len(report_data),
                "total_quantity": total_quantity,  # Items from revenue-generating orders only
                "total_revenue": round(total_revenue, 2),
                "total_orders": total_orders,  # Valid orders only
                "excluded_items": excluded_items,  # Items from cancelled/returned orders
                "all_orders": total_all_orders,  # Including excluded orders
            },
            "currency": "INR",
            "data_source": "saleorder/get API",
            "cached": result.get("fetch_info", {}).get("cached", False),
            "note": f"Report shows {total_quantity} items from revenue-generating orders. {excluded_items} items excluded from cancelled/returned orders.",
        }

    except ValueError as e:
        return {"success": False, "error": f"Invalid date format. Use YYYY-MM-DD: {e}"}
    except Exception as e:
        logger.error(
            f"Error generating daily sales report: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# CHANNEL BREAKDOWN ENDPOINT
# =============================================================================

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

        service = get_unicommerce_service()

        if period == "today":
            result = await service.get_today_sales()
        elif period == "yesterday":
            result = await service.get_yesterday_sales()
        else:
            result = await service.get_last_7_days_sales()

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


# =============================================================================
# BACKGROUND SYNC ENDPOINTS
# =============================================================================

@router.post("/unicommerce/sync/{period}")
async def trigger_sync(
    period: str,
    background_tasks: BackgroundTasks
):
    """
    Trigger background sync for a period.
    Orders are fetched from Unicommerce and persisted to DB.

    Valid periods: today, yesterday, last_7_days
    """
    valid_periods = {"today", "yesterday", "last_7_days"}
    if period not in valid_periods:
        return {
            "success": False,
            "error": f"Invalid period. Use: {', '.join(valid_periods)}"
        }

    try:
        sync_service = get_sync_service()

        # Check if already running
        status = sync_service.get_sync_status(period)
        if status.get("status") == "running":
            return {
                "success": False,
                "message": f"Sync for '{period}' is already running",
                "status": status,
            }

        # Run sync in background
        async def _run_sync():
            await sync_service.sync_period(period)

        background_tasks.add_task(_run_sync)

        return {
            "success": True,
            "message": f"Sync started for '{period}' in background",
            "period": period,
        }

    except Exception as e:
        logger.error(f"Error triggering sync: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.post("/unicommerce/sync/all")
async def trigger_sync_all(background_tasks: BackgroundTasks):
    """Trigger background sync for all periods."""
    try:
        sync_service = get_sync_service()

        async def _run_all_syncs():
            for period in ["today", "yesterday", "last_7_days"]:
                try:
                    await sync_service.sync_period(period)
                except Exception as e:
                    logger.error(f"Sync failed for {period}: {e}")

        background_tasks.add_task(_run_all_syncs)

        return {
            "success": True,
            "message": "Sync started for all periods in background",
        }

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/sync/status")
async def get_sync_status(
    period: str = Query(None, description="Period to check, or omit for all")
):
    """Get sync status for a specific period or all periods."""
    try:
        sync_service = get_sync_service()
        return sync_service.get_sync_status(period)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# VALIDATION ENDPOINT
# =============================================================================

@router.get("/unicommerce/validate")
async def validate_revenue():
    """Run revenue validation checks across all periods."""
    try:
        service = get_unicommerce_service()
        return await service.validate_revenue_consistency()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# AUTH STATUS
# =============================================================================

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


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================

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

        service = get_unicommerce_service()
        return await service.search_sale_orders(
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
        service = get_unicommerce_service()
        return await service.get_order_details(order_code)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# CACHE MANAGEMENT
# =============================================================================

@router.post("/unicommerce/clear-cache")
async def clear_cache():
    """Clear the in-memory sales data cache to force fresh data fetch."""
    try:
        service = get_unicommerce_service()
        service._cache.clear()
        logger.info("Sales data cache cleared")
        return {"success": True, "message": "Cache cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing cache: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/unicommerce/cache-stats")
async def get_cache_stats():
    """Get cache statistics showing what's cached and TTL info."""
    try:
        service = get_unicommerce_service()

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
            "cache_ttl_seconds": service.CACHE_TTL_SECONDS,
            "total_cached_items": len(stats),
            "items": stats
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

        periods = ["today", "yesterday", "last_7_days"]
        cache_status = {}

        for period in periods:
            cache_key = service._get_cache_key(period)
            if cache_key in service._cache:
                timestamp, _ = service._cache[cache_key]
                age_seconds = (datetime.now() - timestamp).total_seconds()
                is_valid = age_seconds < service.CACHE_TTL_SECONDS

                cache_status[period] = {
                    "cached": True,
                    "valid": is_valid,
                    "age_seconds": round(age_seconds, 2),
                    "remaining_seconds": round(max(0, service.CACHE_TTL_SECONDS - age_seconds), 2),
                    "cached_at": timestamp.isoformat()
                }
            else:
                cache_status[period] = {
                    "cached": False,
                    "valid": False,
                    "age_seconds": None,
                    "remaining_seconds": 0
                }

        all_cached = all(status["valid"] for status in cache_status.values())

        return {
            "success": True,
            "all_periods_cached": all_cached,
            "cache_ttl_seconds": service.CACHE_TTL_SECONDS,
            "periods": cache_status,
            "message": "All data cached and ready for instant load" if all_cached else "Some periods need fetching"
        }
    except Exception as e:
        logger.error(f"Error checking cache: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# SKU-LEVEL SALES BREAKDOWN (For reports)
# =============================================================================

@router.get("/unicommerce/sales-by-sku")
async def get_sales_by_sku(
    period: str = Query(
        "today", description="today, yesterday, last_7_days, last_30_days"),
    from_date: str = Query(None, description="Custom start date YYYY-MM-DD"),
    to_date: str = Query(None, description="Custom end date YYYY-MM-DD"),
):
    """
    Get sales aggregated by SKU with item-level breakdown.
    Uses cached order data from two-phase fetch.
    """
    try:
        service = get_unicommerce_service()

        if period == "today":
            dt_from, dt_to = service.get_today_range()
        elif period == "yesterday":
            dt_from, dt_to = service.get_yesterday_range()
        elif period == "last_7_days":
            dt_from, dt_to = service.get_last_n_days_range(7)
        elif period == "last_30_days":
            dt_from, dt_to = service.get_last_n_days_range(30)
        elif from_date and to_date:
            dt_from = datetime.strptime(from_date, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc
            )
            dt_to = datetime.strptime(to_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        else:
            dt_from, dt_to = service.get_today_range()

        # Use cached orders if available (same cache as paginated orders)
        cache_key = f"orders_detailed_{dt_from.date()}_{dt_to.date()}"
        cached_orders = service._get_from_cache(cache_key)

        if cached_orders is None:
            # Need to fetch - use two-phase approach
            fetch_result = await service.fetch_all_orders_with_revenue(dt_from, dt_to)
            if not fetch_result.get("successful", False):
                return {"success": False, "error": "Failed to fetch orders", "skus": []}

            raw_orders = fetch_result.get("orders", [])
        else:
            # cached_orders is the processed list (no saleOrderItems) - re-fetch raw
            fetch_result = await service.fetch_all_orders_with_revenue(dt_from, dt_to)
            if not fetch_result.get("successful", False):
                return {"success": False, "error": "Failed to fetch orders", "skus": []}
            raw_orders = fetch_result.get("orders", [])

        # Aggregate by SKU
        sku_map = {}
        for order in raw_orders:
            channel = order.get("channel", "UNKNOWN")
            status = order.get("status", "")
            include = status not in ("CANCELLED", "RETURNED", "UNFULFILLABLE")

            for item in order.get("saleOrderItems", []):
                sku = item.get("itemSku", "UNKNOWN")
                if sku not in sku_map:
                    sku_map[sku] = {
                        "sku": sku,
                        "name": item.get("itemName", ""),
                        "total_quantity": 0,
                        "total_revenue": 0.0,
                        "total_discount": 0.0,
                        "order_count": 0,
                        "channels": {},
                        "avg_selling_price": 0.0,
                    }

                qty = item.get("quantity", 1) or 1
                selling = float(item.get("sellingPrice", 0) or 0)
                discount = float(item.get("discount", 0) or 0)

                if include:
                    sku_map[sku]["total_quantity"] += qty
                    sku_map[sku]["total_revenue"] += selling
                    sku_map[sku]["total_discount"] += discount
                    sku_map[sku]["order_count"] += 1

                    if channel not in sku_map[sku]["channels"]:
                        sku_map[sku]["channels"][channel] = {
                            "quantity": 0, "revenue": 0.0}
                    sku_map[sku]["channels"][channel]["quantity"] += qty
                    sku_map[sku]["channels"][channel]["revenue"] += selling

        # Compute avg selling price and round
        for s in sku_map.values():
            if s["total_quantity"] > 0:
                s["avg_selling_price"] = round(
                    s["total_revenue"] / s["total_quantity"], 2)
            s["total_revenue"] = round(s["total_revenue"], 2)
            s["total_discount"] = round(s["total_discount"], 2)
            for ch in s["channels"].values():
                ch["revenue"] = round(ch["revenue"], 2)

        skus = sorted(sku_map.values(),
                      key=lambda x: x["total_revenue"], reverse=True)
        total_revenue = round(sum(s["total_revenue"] for s in skus), 2)
        total_quantity = sum(s["total_quantity"] for s in skus)
        total_discount = round(sum(s["total_discount"] for s in skus), 2)

        return {
            "success": True,
            "period": period,
            "from_date": dt_from.isoformat(),
            "to_date": dt_to.isoformat(),
            "skus": skus,
            "summary": {
                "total_skus": len(skus),
                "total_quantity": total_quantity,
                "total_revenue": total_revenue,
                "total_discount": total_discount,
                "total_orders": len(raw_orders),
                "avg_discount_pct": round(
                    (total_discount / (total_revenue + total_discount) * 100)
                    if (total_revenue + total_discount) > 0 else 0, 2
                ),
            },
        }

    except Exception as e:
        logger.error(f"Error in sales_by_sku: {e}", exc_info=True)
        return {"success": False, "error": str(e), "skus": []}


# =============================================================================
# DAILY RETURN REPORT (Three-Phase: return/search + return/get + saleorder/get)
# =============================================================================

@router.get("/unicommerce/daily-return-report")
async def get_daily_return_report(
    date: str = Query(..., description="Date for report (YYYY-MM-DD)"),
    return_type: str = Query("ALL", description="RTO, CIR, or ALL"),
):
    """
    Daily Return Report with channel-wise + SKU breakdown.
    Uses Unicommerce return/search then return/get then saleorder/get APIs.
    Supports RTO, CIR, or ALL return types.

    Phase 1: return/search → get return codes (returnOrders[].code)
    Phase 2: return/get   → get items per return (returnSaleOrderItems)
    Phase 3: saleorder/get → get channel + sellingPrice for each sale order
    """
    import httpx

    try:
        token_manager = get_token_manager()
        tenant = token_manager.tenant
        base_url = f"https://{tenant}.unicommerce.com/services/rest/v1"
        headers = await token_manager.get_headers()
        headers["Facility"] = "anthrilo"
        timeout = httpx.Timeout(90.0, connect=15.0)

        # Unicommerce return/search date format: ISO with T separator
        created_from = f"{date}T00:00:00"
        created_to = f"{date}T23:59:59"

        # Determine which return types to fetch
        types_to_fetch = []
        if return_type == "ALL":
            types_to_fetch = ["RTO", "CIR"]
        else:
            types_to_fetch = [return_type.upper()]

        all_return_codes = []
        search_results = {}

        # =====================================================================
        # Phase 1: Search returns for each type
        # API: POST /oms/return/search
        # Response field: returnOrders[] with {code, created, updated}
        # Strategy: Try createdFrom/To first, then updatedFrom/To as fallback
        # =====================================================================
        async with httpx.AsyncClient(timeout=timeout) as client:
            for rtype in types_to_fetch:
                search_url = f"{base_url}/oms/return/search"

                # Try with createdFrom/To first
                search_payload = {
                    "returnType": rtype,
                    "createdFrom": created_from,
                    "createdTo": created_to,
                }
                logger.info(
                    f"Return search {rtype}: POST {search_url} payload={search_payload}")

                found_returns = []
                try:
                    resp = await client.post(search_url, json=search_payload, headers=headers)
                    if resp.status_code == 401:
                        token = await token_manager.get_valid_token()
                        if token:
                            headers = await token_manager.get_headers()
                            headers["Facility"] = "anthrilo"
                            resp = await client.post(search_url, json=search_payload, headers=headers)
                    logger.info(
                        f"Return search {rtype} response status: {resp.status_code}")
                    resp.raise_for_status()
                    data = resp.json()
                    logger.info(
                        f"Return search {rtype} response keys: {list(data.keys())}")
                    if data.get("successful"):
                        # UC return/search returns "returnOrders" list of
                        # {code, created, updated} — NOT "reversePickupCodes"
                        return_orders = data.get("returnOrders", [])
                        logger.info(
                            f"Return search {rtype}: found {len(return_orders)} returns (createdFrom/To)")
                        if return_orders:
                            logger.info(
                                f"Return search {rtype}: sample codes = {[r.get('code') for r in return_orders[:3]]}")
                        found_returns = return_orders
                    else:
                        errors = data.get("errors", [])
                        msg = data.get("message", "")
                        logger.warning(
                            f"Return search {rtype} not successful: message={msg}, errors={errors}")
                except Exception as e:
                    logger.error(
                        f"Return search {rtype} error (createdFrom/To): {e}")

                # Fallback: try updatedFrom/To if createdFrom/To returned empty
                if not found_returns:
                    try:
                        fallback_payload = {
                            "returnType": rtype,
                            "updatedFrom": created_from,
                            "updatedTo": created_to,
                        }
                        logger.info(
                            f"Return search {rtype}: fallback with updatedFrom/To")
                        resp = await client.post(search_url, json=fallback_payload, headers=headers)
                        if resp.status_code == 401:
                            token = await token_manager.get_valid_token()
                            if token:
                                headers = await token_manager.get_headers()
                                headers["Facility"] = "anthrilo"
                                resp = await client.post(search_url, json=fallback_payload, headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                        if data.get("successful"):
                            found_returns = data.get("returnOrders", [])
                            logger.info(
                                f"Return search {rtype}: fallback found {len(found_returns)} returns (updatedFrom/To)")
                            if found_returns:
                                logger.info(
                                    f"Return search {rtype}: fallback sample codes = {[r.get('code') for r in found_returns[:3]]}")
                    except Exception as e:
                        logger.error(
                            f"Return search {rtype} fallback error: {e}")

                for ro in found_returns:
                    code = ro.get("code", "") if isinstance(ro, dict) else ro
                    if code:
                        all_return_codes.append(
                            {"code": code, "type": rtype})
                search_results[rtype] = len(found_returns)
                logger.info(
                    f"Return search {rtype}: total codes collected = {len(all_return_codes)}")

        if not all_return_codes:
            return {
                "success": True,
                "date": date,
                "return_type": return_type,
                "returns": [],
                "by_channel": [],
                "by_sku": [],
                "totals": {
                    "total_returns": 0, "total_items": 0,
                    "total_value": 0, "rto_count": 0, "cir_count": 0,
                },
                "search_results": search_results,
                "debug_info": {
                    "failed_rto_codes": [],
                    "failed_cir_codes": [],
                    "total_failed_rto": 0,
                    "total_failed_cir": 0,
                },
            }

        # =====================================================================
        # Phase 2: Get details for each return
        # API: POST /oms/return/get  (with reversePickupCode)
        # Response fields:
        #   - returnSaleOrderItems[]: {skuCode, itemName, saleOrderCode,
        #       saleOrderItemCode, channelProductId, saleOrderItemStatus, ...}
        #   - returnSaleOrderValue: {returnStatus, saleOrderCode,
        #       reversePickupCode, returnCreatedDate, ...}
        # =====================================================================
        return_details = []
        sale_order_codes = set()
        failed_rto_codes = []
        failed_cir_codes = []

        async with httpx.AsyncClient(timeout=timeout) as client:
            for entry in all_return_codes:
                get_url = f"{base_url}/oms/return/get"

                # RTOs use shipmentCode, CIRs use reversePickupCode
                if entry["type"] == "RTO":
                    get_payload = {
                        "reversePickupCode": None,
                        "shipmentCode": entry["code"],
                    }
                else:
                    get_payload = {
                        "reversePickupCode": entry["code"],
                        "shipmentCode": None,
                    }

                try:
                    resp = await client.post(get_url, json=get_payload, headers=headers)
                    if resp.status_code == 401:
                        token = await token_manager.get_valid_token()
                        if token:
                            headers = await token_manager.get_headers()
                            headers["Facility"] = "anthrilo"
                            resp = await client.post(get_url, json=get_payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("successful"):
                        # Parse the correct response structure
                        items = data.get("returnSaleOrderItems", [])
                        value_info = data.get("returnSaleOrderValue", {})
                        logger.info(
                            f"Return get {entry['code']} ({entry['type']}): "
                            f"{len(items)} items, "
                            f"saleOrderCode={value_info.get('saleOrderCode', '')}, "
                            f"status={value_info.get('returnStatus', '')}"
                        )

                        detail = {
                            "_return_type": entry["type"],
                            "_code": entry["code"],
                            "status": value_info.get("returnStatus", ""),
                            "created": value_info.get("returnCreatedDate", ""),
                            "saleOrderCode": value_info.get("saleOrderCode", ""),
                            "reversePickupCode": value_info.get("reversePickupCode", entry["code"]),
                            "items": items,
                        }
                        return_details.append(detail)

                        # Collect unique sale order codes for Phase 3
                        for item in items:
                            so_code = item.get("saleOrderCode", "")
                            if so_code:
                                sale_order_codes.add(so_code)
                        # Also from value_info
                        so_code_top = value_info.get("saleOrderCode", "")
                        if so_code_top:
                            sale_order_codes.add(so_code_top)
                    else:
                        # Track failed returns
                        errors = data.get("errors", [])
                        msg = data.get("message", "Unknown error")
                        logger.warning(
                            f"Return get {entry['code']} ({entry['type']}) unsuccessful: {msg} | errors={errors}"
                        )
                        if entry["type"] == "RTO":
                            failed_rto_codes.append(entry["code"])
                        else:
                            failed_cir_codes.append(entry["code"])

                except Exception as e:
                    logger.error(
                        f"Return get {entry['code']} ({entry['type']}) error: {e}")
                    if entry["type"] == "RTO":
                        failed_rto_codes.append(entry["code"])
                    else:
                        failed_cir_codes.append(entry["code"])

        # Log summary of failures
        if failed_rto_codes:
            logger.warning(
                f"Failed to get details for {len(failed_rto_codes)} RTO returns: {failed_rto_codes[:5]}")
        if failed_cir_codes:
            logger.warning(
                f"Failed to get details for {len(failed_cir_codes)} CIR returns: {failed_cir_codes[:5]}")

        # =====================================================================
        # Phase 3: Fetch sale order details for channel + pricing
        # API: POST /oms/saleorder/get  (with code)
        # Response: saleOrderDTO.channel, saleOrderDTO.saleOrderItems[].sellingPrice
        # =====================================================================
        so_details = {}  # saleOrderCode -> {channel, items: {saleOrderItemCode -> {sellingPrice, itemSku}}}

        if sale_order_codes:
            async with httpx.AsyncClient(timeout=timeout) as client:
                for so_code in sale_order_codes:
                    so_url = f"{base_url}/oms/saleorder/get"
                    so_payload = {"code": so_code}
                    try:
                        resp = await client.post(so_url, json=so_payload, headers=headers)
                        if resp.status_code == 401:
                            token = await token_manager.get_valid_token()
                            if token:
                                headers = await token_manager.get_headers()
                                headers["Facility"] = "anthrilo"
                                resp = await client.post(so_url, json=so_payload, headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                        if data.get("successful"):
                            so_dto = data.get("saleOrderDTO", {})
                            channel = so_dto.get("channel", "UNKNOWN")

                            # Map saleOrderItemCode -> pricing info
                            items_map = {}
                            for so_item in so_dto.get("saleOrderItems", []):
                                item_code = so_item.get("code", "")
                                items_map[item_code] = {
                                    "sellingPrice": float(so_item.get("sellingPrice", 0) or 0),
                                    "itemSku": so_item.get("itemSku", ""),
                                    "itemName": so_item.get("itemName", ""),
                                    "quantity": so_item.get("quantity", 1) or 1,
                                }
                            so_details[so_code] = {
                                "channel": channel, "items": items_map}
                    except Exception as e:
                        logger.error(f"SaleOrder get {so_code} error: {e}")

        # =====================================================================
        # Aggregate data using return details + sale order details
        # =====================================================================
        channel_map = {}
        sku_map = {}
        returns_list = []
        rto_count = 0
        cir_count = 0
        total_value = 0.0
        total_items = 0

        for rp in return_details:
            rtype = rp.get("_return_type", "UNKNOWN")
            code = rp.get("_code", "")
            items = rp.get("items", [])

            if rtype == "RTO":
                rto_count += 1
            elif rtype == "CIR":
                cir_count += 1

            # Determine channel from sale order details
            so_code = rp.get("saleOrderCode", "")
            so_info = so_details.get(so_code, {})
            channel = so_info.get("channel", "UNKNOWN")

            return_entry = {
                "code": code,
                "type": rtype,
                "channel": channel,
                "status": rp.get("status", ""),
                "created": rp.get("created", ""),
                "saleOrderCode": so_code,
                "items": [],
                "total_value": 0.0,
            }

            for item in items:
                sku = item.get("skuCode", item.get("itemSku", "UNKNOWN"))
                item_name = item.get("itemName", "")
                so_item_code = item.get("saleOrderItemCode", "")
                item_so_code = item.get("saleOrderCode", so_code)

                # Each returnSaleOrderItem represents 1 item
                qty = 1

                # Look up sellingPrice from Phase 3 sale order data
                price = 0.0
                item_so_info = so_details.get(item_so_code, so_info)
                if item_so_info:
                    so_items = item_so_info.get("items", {})
                    if so_item_code and so_item_code in so_items:
                        price = so_items[so_item_code].get("sellingPrice", 0.0)
                    else:
                        # Fallback: match by SKU code across all items
                        for _, si in so_items.items():
                            if si.get("itemSku") == sku:
                                price = si.get("sellingPrice", 0.0)
                                break

                    # Use channel from item's sale order if different
                    if channel == "UNKNOWN":
                        channel = item_so_info.get("channel", "UNKNOWN")

                total_items += qty
                total_value += price
                return_entry["total_value"] += price
                return_entry["items"].append({
                    "sku": sku, "name": item_name, "quantity": qty, "price": price,
                })

                # Channel aggregation (per return, not per item — avoid double-counting)
                # We aggregate channel at the return level below

                # SKU aggregation
                if sku not in sku_map:
                    sku_map[sku] = {"sku": sku, "name": item_name,
                                    "quantity": 0, "value": 0.0, "return_count": 0}
                sku_map[sku]["quantity"] += qty
                sku_map[sku]["value"] += price
                sku_map[sku]["return_count"] += 1

            # Channel aggregation at the return level
            if channel not in channel_map:
                channel_map[channel] = {
                    "channel": channel, "returns": 0, "items": 0,
                    "value": 0.0, "rto": 0, "cir": 0}
            channel_map[channel]["returns"] += 1
            channel_map[channel]["items"] += len(items)
            channel_map[channel]["value"] += return_entry["total_value"]
            if rtype == "RTO":
                channel_map[channel]["rto"] += 1
            else:
                channel_map[channel]["cir"] += 1

            returns_list.append(return_entry)

        by_channel = sorted(channel_map.values(),
                            key=lambda x: x["value"], reverse=True)
        by_sku = sorted(sku_map.values(),
                        key=lambda x: x["quantity"], reverse=True)

        for ch in by_channel:
            ch["value"] = round(ch["value"], 2)
        for s in by_sku:
            s["value"] = round(s["value"], 2)

        return {
            "success": True,
            "date": date,
            "return_type": return_type,
            "returns": returns_list,
            "by_channel": by_channel,
            "by_sku": by_sku,
            "totals": {
                "total_returns": len(return_details),
                "total_items": total_items,
                "total_value": round(total_value, 2),
                "rto_count": rto_count,
                "cir_count": cir_count,
            },
            "search_results": search_results,
            "debug_info": {
                "failed_rto_codes": failed_rto_codes[:10],
                "failed_cir_codes": failed_cir_codes[:10],
                "total_failed_rto": len(failed_rto_codes),
                "total_failed_cir": len(failed_cir_codes),
            },
        }

    except Exception as e:
        logger.error(f"Error in daily return report: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# BEST PERFORMING SKUs (Monthly)
# =============================================================================

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
        service = get_unicommerce_service()
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

        logger.info(f"BEST SKUs {y}-{m:02d}: Cache miss, fetching from API...")

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

        fetch_result = await service.fetch_all_orders_with_revenue(from_dt, to_dt)
        if not fetch_result.get("successful", False):
            return {"success": False, "error": "Failed to fetch orders"}

        raw_orders = fetch_result.get("orders", [])

        # Aggregate by SKU
        sku_map = {}
        for order in raw_orders:
            status = order.get("status", "")
            if status in service.EXCLUDED_STATUSES:
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


# =============================================================================
# SKU VELOCITY - Fast & Slow Movers (Monthly)
# =============================================================================

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
        service = get_unicommerce_service()
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
            f"SKU VELOCITY {y}-{m:02d}: Cache miss, fetching from API...")

        from_dt = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
        if m == 12:
            to_dt = datetime(y + 1, 1, 1, 0, 0, 0,
                             tzinfo=timezone.utc) - timedelta(seconds=1)
        else:
            to_dt = datetime(y, m + 1, 1, 0, 0, 0,
                             tzinfo=timezone.utc) - timedelta(seconds=1)

        if to_dt > now.replace(tzinfo=timezone.utc):
            to_dt = now.replace(tzinfo=timezone.utc)

        fetch_result = await service.fetch_all_orders_with_revenue(from_dt, to_dt)
        if not fetch_result.get("successful", False):
            return {"success": False, "error": "Failed to fetch orders"}

        raw_orders = fetch_result.get("orders", [])

        # Aggregate by SKU (same logic as best-skus-monthly)
        sku_map = {}
        for order in raw_orders:
            status = order.get("status", "")
            if status in service.EXCLUDED_STATUSES:
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


# =============================================================================
# COD vs PREPAID (Monthly)
# =============================================================================

@router.get("/unicommerce/cod-vs-prepaid")
async def get_cod_vs_prepaid(
    month: int = Query(None, description="Month (1-12), defaults to current"),
    year: int = Query(None, description="Year, defaults to current"),
):
    """Get COD vs Prepaid breakdown for a given month with Redis caching."""
    try:
        service = get_unicommerce_service()
        now = datetime.now(IST)
        m = month or now.month
        y = year or now.year

        # Check Redis cache (persistent across workers/restarts)
        cache_key = f"uc:cod_prepaid:{y}:{m}"
        cached = CacheService.get(cache_key)
        if cached:
            logger.info(f"COD vs Prepaid {y}-{m:02d}: Redis cache hit")
            cached["_cached"] = True
            return cached

        from_dt = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
        if m == 12:
            to_dt = datetime(y + 1, 1, 1, 0, 0, 0,
                             tzinfo=timezone.utc) - timedelta(seconds=1)
        else:
            to_dt = datetime(y, m + 1, 1, 0, 0, 0,
                             tzinfo=timezone.utc) - timedelta(seconds=1)

        if to_dt > now.replace(tzinfo=timezone.utc):
            to_dt = now.replace(tzinfo=timezone.utc)

        logger.info(
            f"COD vs Prepaid: fetching orders from {from_dt.date()} to {to_dt.date()}")
        fetch_result = await service.fetch_all_orders_with_revenue(from_dt, to_dt)
        logger.info(
            f"COD vs Prepaid: fetched {len(fetch_result.get('orders', []))} orders")
        if not fetch_result.get("successful", False):
            return {"success": False, "error": "Failed to fetch orders"}

        raw_orders = fetch_result.get("orders", [])

        cod_orders = 0
        cod_revenue = 0.0
        cod_items = 0
        prepaid_orders = 0
        prepaid_revenue = 0.0
        prepaid_items = 0
        channel_breakdown = {}

        for order in raw_orders:
            status = order.get("status", "")
            if status in service.EXCLUDED_STATUSES:
                continue

            # Robust multi-signal COD detection:
            # 1. Direct cod boolean from saleOrderDTO
            # 2. shippingMethod containing "COD" (e.g. "Standard-COD")
            # 3. collectableAmount > 0 (amount collected at delivery)
            cod_flag = order.get("cod", False)
            shipping_method = (order.get("shippingMethod") or "").upper()
            collectable = float(order.get("collectableAmount", 0) or 0)
            is_cod = bool(
                cod_flag) or "COD" in shipping_method or collectable > 0
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
            f"COD vs Prepaid: processed {total_orders} orders ({cod_orders} COD, {prepaid_orders} Prepaid) for {y}-{m:02d}")

        for ch in channel_breakdown.values():
            ch["cod_revenue"] = round(ch["cod_revenue"], 2)
            ch["prepaid_revenue"] = round(ch["prepaid_revenue"], 2)

        channels = sorted(
            [{"channel": k, **v} for k, v in channel_breakdown.items()],
            key=lambda x: x["cod_orders"] + x["prepaid_orders"], reverse=True,
        )

        result = {
            "success": True,
            "month": m, "year": y,
            "period": f"{y}-{m:02d}",
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

        # Redis cache: current month 1hr, historical 24hr
        is_current = (y == now.year and m == now.month)
        ttl = CacheService.TTL_VERY_LONG if is_current else 86400
        CacheService.set(cache_key, result, ttl)
        logger.info(
            f"COD vs Prepaid: cached result for {y}-{m:02d} (TTL={ttl}s)")

        return result

    except Exception as e:
        logger.error(f"Error in cod-vs-prepaid: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# =============================================================================
# WEBSOCKET ENDPOINTS (Real-time updates for different event types)
# =============================================================================

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
            service = get_unicommerce_service()
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
                    service = get_unicommerce_service()
                    result = await service.get_today_sales()
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
                except Exception:
                    pass

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


# =============================================================================
# REDIS CACHE MANAGEMENT ENDPOINTS
# =============================================================================

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
        result = CacheService.delete_pattern(pattern)
        return {"success": True, "message": f"Invalidated keys matching: {pattern}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
