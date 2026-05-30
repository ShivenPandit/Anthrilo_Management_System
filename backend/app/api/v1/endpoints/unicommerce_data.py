"""DB-first Unicommerce data endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from threading import Lock
from typing import Any, Dict, List, Optional

from sqlalchemy import and_
from fastapi import APIRouter, Body, Query
from fastapi.concurrency import run_in_threadpool

from app.core.redis import redis_client
from app.services.cache_service import CacheService
from app.services.unicommerce import get_unicommerce_service
from app.services.unicommerce_data_service import get_unicommerce_data_service
from app.services.unicommerce_sync_orchestrator import get_unicommerce_sync_orchestrator
from app.utils.timezone_utils import normalize_date_range_ist
from app.db.session import SessionLocal
from app.db.export_models import SalesReturnRecord


router = APIRouter()
IST = timezone(timedelta(hours=5, minutes=30))
_REPORT_PROGRESS_TTL_SECONDS = 60 * 60
_report_progress_store: Dict[str, Dict[str, Any]] = {}
_report_progress_lock = Lock()


def _parse_date_boundary(value: str, end_of_day: bool = False) -> datetime:
    parsed = datetime.strptime(value, "%Y-%m-%d")
    if end_of_day:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=0)
    else:
        parsed = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    return parsed.replace(tzinfo=timezone.utc)


def _progress_cache_key(progress_id: str) -> str:
    return f"uc:report-progress:{progress_id}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup_stale_progress(now_epoch: float) -> None:
    stale_ids = [
        key
        for key, value in _report_progress_store.items()
        if float(value.get("expires_at_epoch", 0)) <= now_epoch
    ]
    for key in stale_ids:
        _report_progress_store.pop(key, None)


def _set_report_progress(
    progress_id: str,
    percent: int,
    label: str,
    status: str = "running",
    error: Optional[str] = None,
) -> Dict[str, Any]:
    now_epoch = datetime.now(timezone.utc).timestamp()
    payload: Dict[str, Any] = {
        "success": status != "failed",
        "progress_id": progress_id,
        "status": status,
        "percent": max(0, min(100, int(percent))),
        "label": label,
        "error": error,
        "updated_at": _utc_now_iso(),
        "expires_at_epoch": now_epoch + _REPORT_PROGRESS_TTL_SECONDS,
    }

    if redis_client is not None:
        CacheService.set(
            _progress_cache_key(progress_id),
            payload,
            _REPORT_PROGRESS_TTL_SECONDS,
        )

    with _report_progress_lock:
        _cleanup_stale_progress(now_epoch)
        _report_progress_store[progress_id] = payload

    return payload


def _get_report_progress(progress_id: str) -> Optional[Dict[str, Any]]:
    if redis_client is not None:
        payload = CacheService.get(_progress_cache_key(progress_id))
        if isinstance(payload, dict):
            return payload

    now_epoch = datetime.now(timezone.utc).timestamp()
    with _report_progress_lock:
        _cleanup_stale_progress(now_epoch)
        payload = _report_progress_store.get(progress_id)

    return dict(payload) if isinstance(payload, dict) else None


def _build_progress_callback(progress_id: Optional[str]):
    if not progress_id:
        return None

    _set_report_progress(progress_id, 1, "Starting report generation…", status="running")

    def _callback(percent: int, label: str) -> None:
        _set_report_progress(progress_id, percent, label, status="running")

    return _callback


def _finish_report_progress(progress_id: Optional[str], success: bool, error: Optional[str] = None) -> None:
    if not progress_id:
        return

    if success:
        _set_report_progress(progress_id, 100, "Report ready", status="completed")
    else:
        _set_report_progress(
            progress_id,
            100,
            "Report failed",
            status="failed",
            error=error or "Report generation failed",
        )


@router.get("/sales")
async def get_sales_data(
    period: str = Query(
        "today",
        description="today | yesterday | last_7_days | last_30_days | custom",
    ),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD (required for custom)"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD (required for custom)"),
    lightweight: bool = Query(
        False,
        description="When true, omits heavy legacy order payload for faster dashboard chart loads",
    ),
):
    service = get_unicommerce_data_service()

    try:
        parsed_from = _parse_date_boundary(from_date, end_of_day=False) if from_date else None
        parsed_to = _parse_date_boundary(to_date, end_of_day=True) if to_date else None
        if period == "custom" and from_date and to_date:
            start_utc, end_exclusive_utc, _ = normalize_date_range_ist(
                from_date,
                to_date,
                closed_window_mode=False,
            )
            parsed_from = start_utc
            parsed_to = end_exclusive_utc - timedelta(seconds=1)
    except ValueError as exc:
        return {
            "success": False,
            "error": f"Invalid date format: {exc}",
            "message": "Use YYYY-MM-DD format for from_date and to_date",
        }

    if period == "custom" and (not parsed_from or not parsed_to):
        return {
            "success": False,
            "error": "from_date and to_date are required when period=custom",
        }

    result = await run_in_threadpool(
        service.get_sales_data,
        period,
        parsed_from,
        parsed_to,
        not lightweight,
        not lightweight,
    )

    return result


@router.get("/orders")
def get_orders_paginated(
    period: str = Query(
        "today",
        description="today | yesterday | last_7_days | last_30_days | custom",
    ),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD (required for custom)"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD (required for custom)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(15, ge=1, le=500, description="Orders per page"),
):
    service = get_unicommerce_data_service()

    try:
        parsed_from = _parse_date_boundary(from_date, end_of_day=False) if from_date else None
        parsed_to = _parse_date_boundary(to_date, end_of_day=True) if to_date else None
        if period == "custom" and from_date and to_date:
            start_utc, end_exclusive_utc, _ = normalize_date_range_ist(
                from_date,
                to_date,
                closed_window_mode=False,
            )
            parsed_from = start_utc
            parsed_to = end_exclusive_utc - timedelta(seconds=1)
    except ValueError as exc:
        return {
            "success": False,
            "error": f"Invalid date format: {exc}",
            "message": "Use YYYY-MM-DD format for from_date and to_date",
        }

    if period == "custom" and (not parsed_from or not parsed_to):
        return {
            "success": False,
            "error": "from_date and to_date are required when period=custom",
        }

    return service.get_orders_paginated(
        period=period,
        from_date=parsed_from,
        to_date=parsed_to,
        page=page,
        page_size=page_size,
    )


@router.get("/inventory")
def get_inventory_data(
    skus: Optional[str] = Query(None, description="Comma-separated SKU list"),
    warehouse: Optional[str] = Query(None, description="Warehouse/facility code"),
):
    service = get_unicommerce_data_service()
    sku_list = [part.strip() for part in (skus or "").split(",") if part.strip()]
    return service.get_inventory_data(
        skus=sku_list or None,
        warehouse=warehouse,
    )


@router.get("/inventory-summary")
async def get_inventory_summary(
    warehouse: Optional[str] = Query(None, description="Warehouse/facility code"),
    force_refresh: bool = Query(False, description="Force refresh cache"),
):
    # Build cache key (warehouse is optional)
    cache_key = f"uc:inventory-summary:v3:{warehouse or 'all'}"
    
    # Try cache first (5 minute TTL)
    if not force_refresh:
        cached = CacheService.get(cache_key)
        if isinstance(cached, dict):
            return cached
    
    service = get_unicommerce_data_service()
    result = await run_in_threadpool(service.get_inventory_summary_db, warehouse)
    
    # Cache successful results
    if result and result.get("successful"):
        CacheService.set(cache_key, result, ttl=300)
    
    return result


@router.post("/catalog-search")
async def search_catalog_data(payload: Optional[Dict[str, Any]] = Body(None)):
    # Build cache key from search parameters
    body = payload or {}
    search_options = body.get("searchOptions") or {}

    display_start = int(search_options.get("displayStart", 0) or 0)
    display_length = int(search_options.get("displayLength", 25) or 25)
    warehouse = body.get("warehouse") or body.get("facilityCode")
    category = body.get("category") or body.get("categoryName")
    stock_filter = body.get("stockFilter") or "all"
    keyword = body.get("keyword") or ""
    
    # Cache key includes pagination to avoid stale page slicing issues.
    cache_key = (
        f"uc:catalog-search:v3:{warehouse or 'all'}:{category or 'all'}:{stock_filter}:{keyword.lower()}:"
        f"{display_start}:{display_length}:{int(bool(body.get('getInventorySnapshot', False)))}"
    )
    
    # Try cache first (5 minute TTL)
    cached = CacheService.get(cache_key)
    if isinstance(cached, dict):
        return cached
    
    service = get_unicommerce_data_service()

    result = await run_in_threadpool(
        service.get_inventory_catalog_search,
        keyword,
        display_start,
        display_length,
        warehouse,
        category,
        stock_filter,
        bool(body.get("getInventorySnapshot", False)),
    )
    
    # Cache page result for 5 minutes.
    if result and result.get("successful"):
        CacheService.set(cache_key, result, ttl=300)

    return result


@router.get("/returns")
def get_returns_data(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    return_type: str = Query("ALL", description="RTO | CIR | ALL"),
):
    service = get_unicommerce_data_service()

    try:
        parsed_from = _parse_date_boundary(from_date, end_of_day=False)
        parsed_to = _parse_date_boundary(to_date, end_of_day=True)
    except ValueError as exc:
        return {
            "success": False,
            "error": f"Invalid date format: {exc}",
            "message": "Use YYYY-MM-DD format for from_date and to_date",
        }

    return service.get_returns_data(
        from_date=parsed_from,
        to_date=parsed_to,
        return_type=return_type,
    )


@router.get("/returns/analyze")
def analyze_returns_data(
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """
    Analyze return data for issues: duplicates, channel problems, missing data.
    """
    db = SessionLocal()
    try:
        # Build query with optional date filters
        query = db.query(SalesReturnRecord)

        parsed_from = None
        parsed_to = None

        if from_date:
            try:
                parsed_from = _parse_date_boundary(from_date, end_of_day=False)
                query = query.filter(SalesReturnRecord.created_at >= parsed_from)
            except ValueError:
                pass

        if to_date:
            try:
                parsed_to = _parse_date_boundary(to_date, end_of_day=True)
                query = query.filter(SalesReturnRecord.created_at <= parsed_to)
            except ValueError:
                pass

        all_returns = query.all()

        # Analyze issues
        issues = {
            "duplicate_return_codes": [],
            "channel_issues": [],
            "missing_data": [],
            "total_records": len(all_returns),
        }

        # Track return_code occurrences to find duplicates
        return_code_map: Dict[str, List[Dict]] = {}

        for rec in all_returns:
            rc = rec.return_code or ""
            if rc not in return_code_map:
                return_code_map[rc] = []
            return_code_map[rc].append(rec)

        # Check for duplicates (same return_code with different data)
        for rc, records in return_code_map.items():
            if len(records) > 1:
                # Check if they have different data
                first = records[0]
                has_diff = any(
                    r.order_id != first.order_id
                    or r.sku != first.sku
                    or r.return_qty != first.return_qty
                    or float(r.refund_amount or 0) != float(first.refund_amount or 0)
                    for r in records[1:]
                )
                if has_diff:
                    issues["duplicate_return_codes"].append({
                        "return_code": rc,
                        "count": len(records),
                        "records": [
                            {
                                "order_id": r.order_id,
                                "sku": r.sku,
                                "return_qty": r.return_qty,
                                "refund_amount": str(r.refund_amount),
                                "channel": r.channel,
                                "created_at": r.created_at.isoformat() if r.created_at else None,
                            }
                            for r in records[:5]  # Limit to 5 records
                        ],
                    })

            # Check channel issues (inconsistent formatting)
            channels = set()
            for r in records:
                if r.channel:
                    channels.add(r.channel)
                if r.channel_entry:
                    channels.add(r.channel_entry)

            # If there are multiple variations of the same channel (e.g., "AMAZON", "Amazon", "amazon")
            normalized_channels = set()
            for ch in channels:
                if ch:
                    normalized_channels.add(ch.lower().replace(" ", "_"))

            if len(channels) > len(normalized_channels):
                issues["channel_issues"].append({
                    "return_code": rc,
                    "channels_found": list(channels),
                    "normalized": list(normalized_channels),
                })

            # Check for missing critical data
            if not rc or rc.startswith("RET-"):
                if not rec.order_id or rec.order_id == "UNKNOWN":
                    issues["missing_data"].append({
                        "return_code": rc,
                        "issue": "missing_order_id",
                        "created_at": rec.created_at.isoformat() if rec.created_at else None,
                    })
            if not rec.channel or rec.channel == "UNKNOWN":
                issues["missing_data"].append({
                    "return_code": rc,
                    "issue": "missing_channel",
                    "created_at": rec.created_at.isoformat() if rec.created_at else None,
                })

        # Limit issues to first 50 for response size
        issues["duplicate_return_codes"] = issues["duplicate_return_codes"][:50]
        issues["channel_issues"] = issues["channel_issues"][:50]
        issues["missing_data"] = issues["missing_data"][:50]

        return {
            "success": True,
            "analysis": issues,
            "date_range": {
                "from": from_date,
                "to": to_date,
            },
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
    finally:
        db.close()


@router.post("/returns/cleanup")
def cleanup_returns_data(
    cleanup_type: str = Body(..., description="deduplicate | fix_channels | all"),
    from_date: Optional[str] = Body(None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Body(None, description="YYYY-MM-DD"),
    dry_run: bool = Body(True, description="If true, only report what would be done"),
):
    """
    Cleanup return data issues: deduplicate, fix channels, etc.
    """
    db = SessionLocal()
    try:
        # Build base query
        query = db.query(SalesReturnRecord)

        if from_date:
            try:
                parsed_from = _parse_date_boundary(from_date, end_of_day=False)
                query = query.filter(SalesReturnRecord.created_at >= parsed_from)
            except ValueError:
                pass

        if to_date:
            try:
                parsed_to = _parse_date_boundary(to_date, end_of_day=True)
                query = query.filter(SalesReturnRecord.created_at <= parsed_to)
            except ValueError:
                pass

        results = {
            "deduplicated": 0,
            "channels_fixed": 0,
            "dry_run": dry_run,
        }

        if cleanup_type in ("deduplicate", "all"):
            # Find and merge duplicates - keep the record with highest return_qty
            return_code_map: Dict[str, List[SalesReturnRecord]] = {}

            for rec in query.all():
                rc = rec.return_code or ""
                if rc not in return_code_map:
                    return_code_map[rc] = []
                return_code_map[rc].append(rec)

            for rc, records in return_code_map.items():
                if len(records) > 1:
                    # Sort by return_qty descending, keep first
                    records.sort(key=lambda r: r.return_qty or 0, reverse=True)
                    keeper = records[0]

                    # Delete others
                    to_delete = records[1:]
                    if not dry_run:
                        for r in to_delete:
                            db.delete(r)
                    results["deduplicated"] += len(to_delete)

        if cleanup_type in ("fix_channels", "all"):
            # Fix channel normalization - match the service logic
            CHANNEL_MAP = {
                "amazon": "Amazon",
                "amazon_flex": "Amazon_Flex",
                "amazon_in_api": "Amazon_In_Api",
                "flipkart": "Flipkart",
                "myntra": "Myntra",
                "meesho": "Meesho",
                "meesho_26": "Meesho",
                "ajio": "Ajio",
                "ajio_omni": "Ajio_Omni",
                "snapdeal": "Snapdeal",
                "shopify": "Shopify",
                "woocommerce": "WooCommerce",
                "custom": "Custom",
                "firstcry_new": "Firstcry",
                "firstcry": "Firstcry",
                "nykaa_fashion_new": "Nykaa Fashion",
                "nykaa_fashion": "Nykaa Fashion",
                "nykaa": "Nykaa Fashion",
            }

            for rec in query.all():
                # Also check channel field in case channel_entry is empty
                source_value = rec.channel_entry or rec.channel or ""
                if source_value:
                    # First try with underscore replacement
                    normalized_with_underscore = source_value.lower().strip().replace(" ", "_")
                    canonical = CHANNEL_MAP.get(normalized_with_underscore)
                    if not canonical:
                        # Fallback to exact match
                        normalized = source_value.lower().strip()
                        canonical = CHANNEL_MAP.get(normalized, source_value.title().replace(" ", "_"))

                    # Also handle completely uppercase variations
                    if not canonical and source_value.isupper():
                        canonical = CHANNEL_MAP.get(source_value.lower())

                    if rec.channel != canonical:
                        if not dry_run:
                            rec.channel = canonical
                        results["channels_fixed"] += 1

        if not dry_run:
            db.commit()

        return {
            "success": True,
            "results": results,
            "message": f"Deduplicated {results['deduplicated']} records, fixed {results['channels_fixed']} channels" +
                       (" (dry run)" if dry_run else ""),
        }

    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": str(e),
        }
    finally:
        db.close()


@router.post("/returns/rebuild-week")
def rebuild_this_week_returns(
    dry_run: bool = Body(False, description="If true, only analyze without truncating or syncing"),
):
    """
    Truncate and rebuild returns for the current week (Monday to Sunday).
    This ensures clean data with no duplicates.
    """
    from datetime import timedelta
    from app.services.unicommerce_sync_orchestrator import get_unicommerce_sync_orchestrator
    from app.services.unicommerce import get_unicommerce_service

    # Calculate current week (Monday to Sunday)
    today = datetime.now(timezone.utc)
    # Find Monday of this week
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    from_date = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    to_date = sunday.replace(hour=23, minute=59, second=59, microsecond=0)

    db = SessionLocal()
    try:
        # Step 1: Analyze current state
        current_count = db.query(SalesReturnRecord).filter(
            and_(
                SalesReturnRecord.created_at >= from_date,
                SalesReturnRecord.created_at <= to_date,
            )
        ).count()

        # Find potential duplicates before truncation
        return_code_map: Dict[str, int] = {}
        for rec in db.query(SalesReturnRecord.return_code).filter(
            and_(
                SalesReturnRecord.created_at >= from_date,
                SalesReturnRecord.created_at <= to_date,
            )
        ).all():
            rc = rec[0] or ""
            return_code_map[rc] = return_code_map.get(rc, 0) + 1

        duplicate_codes = {k: v for k, v in return_code_map.items() if v > 1}

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "week_range": {
                    "from_date": from_date.date().isoformat(),
                    "to_date": to_date.date().isoformat(),
                },
                "current_records": current_count,
                "potential_duplicates": len(duplicate_codes),
                "duplicate_codes": list(duplicate_codes.items())[:10],
                "message": "Dry run - no changes made",
            }

        # Step 2: Truncate returns for this week
        deleted = db.query(SalesReturnRecord).filter(
            and_(
                SalesReturnRecord.created_at >= from_date,
                SalesReturnRecord.created_at <= to_date,
            )
        ).delete(synchronize_session=False)
        db.commit()

        # Step 3: Trigger rebuild from Unicommerce
        # This will fetch fresh data and apply proper deduplication
        result = {
            "success": True,
            "week_range": {
                "from_date": from_date.date().isoformat(),
                "to_date": to_date.date().isoformat(),
            },
            "deleted_records": deleted,
            "synced_from_unicommerce": True,
            "note": "Returns will be synced. Use /returns endpoint to verify after sync completes.",
        }

        # Actually trigger the sync (this is async, but we'll call it directly)
        try:
            orchestrator = get_unicommerce_sync_orchestrator()
            sync_result = asyncio.run(orchestrator.sync_returns_window(from_date, to_date))
            result["sync_result"] = sync_result
        except Exception as sync_err:
            result["sync_warning"] = f"Sync may need manual trigger: {str(sync_err)}"

        return result

    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "error": str(e),
        }
    finally:
        db.close()


@router.get("/channel-revenue")
def get_channel_revenue(
    period: str = Query("last_7_days", description="today | yesterday | last_7_days"),
):
    service = get_unicommerce_data_service()
    return service.get_channel_revenue(period=period)


@router.get("/daily-sales-report")
def get_daily_sales_report(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    progress_id: Optional[str] = Query(None, description="Client-generated progress tracker ID"),
):
    service = get_unicommerce_data_service()
    progress_cb = _build_progress_callback(progress_id)
    result = service.get_daily_sales_report(
        date=date,
        from_date=from_date,
        to_date=to_date,
        progress_cb=progress_cb,
    )
    _finish_report_progress(
        progress_id,
        success=bool(result.get("success")),
        error=result.get("error") if not result.get("success") else None,
    )
    return result


@router.get("/return-report")
def get_return_report(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    period: str = Query("daily", description="daily | weekly | monthly | custom"),
    return_type: str = Query("ALL", description="RTO | CIR | ALL"),
    progress_id: Optional[str] = Query(None, description="Client-generated progress tracker ID"),
):
    cache_key = f"uc:return-report:v3:{date}:{from_date}:{to_date}:{period}:{return_type}"
    cached = CacheService.get(cache_key)
    if isinstance(cached, dict):
        _finish_report_progress(progress_id, success=bool(cached.get("success", True)))
        return cached

    service = get_unicommerce_data_service()
    progress_cb = _build_progress_callback(progress_id)
    result = service.get_return_report(
        date=date,
        from_date=from_date,
        to_date=to_date,
        period=period,
        return_type=return_type,
        progress_cb=progress_cb,
    )
    if bool(result.get("success")):
        CacheService.set(cache_key, result, ttl=120)

    _finish_report_progress(
        progress_id,
        success=bool(result.get("success")),
        error=result.get("error") if not result.get("success") else None,
    )
    return result


@router.get("/cancellation-report")
def get_cancellation_report(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    period: str = Query("daily", description="daily | weekly | monthly | custom"),
    progress_id: Optional[str] = Query(None, description="Client-generated progress tracker ID"),
):
    service = get_unicommerce_data_service()
    progress_cb = _build_progress_callback(progress_id)
    result = service.get_cancellation_report(
        date=date,
        from_date=from_date,
        to_date=to_date,
        period=period,
        progress_cb=progress_cb,
    )
    _finish_report_progress(
        progress_id,
        success=bool(result.get("success")),
        error=result.get("error") if not result.get("success") else None,
    )
    return result


@router.get("/report-progress/{progress_id}")
def get_report_progress(progress_id: str):
    payload = _get_report_progress(progress_id)
    if payload:
        payload["success"] = payload.get("status") != "failed"
        return payload

    return {
        "success": False,
        "progress_id": progress_id,
        "status": "not_found",
        "percent": 0,
        "label": "No active report progress",
        "error": None,
        "updated_at": _utc_now_iso(),
    }


@router.get("/sales-activity")
def get_sales_activity_report(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    channels: Optional[List[str]] = Query(None, description="Optional channel filters"),
    progress_id: Optional[str] = Query(None, description="Client-generated progress tracker ID"),
):
    normalized_channels = sorted({str(ch).strip().upper() for ch in (channels or []) if str(ch).strip()})
    channel_key = "all" if not normalized_channels else ",".join(normalized_channels)
    cache_key = f"uc:sales-activity:{from_date}:{to_date}:{channel_key}"
    cached_payload = CacheService.get(cache_key)
    if isinstance(cached_payload, dict):
        _finish_report_progress(progress_id, success=bool(cached_payload.get("success", True)))
        return cached_payload

    service = get_unicommerce_data_service()
    progress_cb = _build_progress_callback(progress_id)
    result = service.get_sales_activity_report(
        from_date=from_date,
        to_date=to_date,
        channels=normalized_channels,
        progress_cb=progress_cb,
    )

    if bool(result.get("success")):
        CacheService.set(cache_key, result, ttl=CacheService.TTL_SHORT)

    _finish_report_progress(
        progress_id,
        success=bool(result.get("success")),
        error=result.get("error") if not result.get("success") else None,
    )
    return result


@router.get("/sales-activity/channels")
def get_sales_activity_channels(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
):
    cache_key = f"uc:sales-activity:channels:{from_date}:{to_date}"
    cached_payload = CacheService.get(cache_key)
    if isinstance(cached_payload, dict):
        return cached_payload

    service = get_unicommerce_data_service()
    result = service.get_sales_activity_channels(
        from_date=from_date,
        to_date=to_date,
    )

    if bool(result.get("success")):
        CacheService.set(cache_key, result, ttl=CacheService.TTL_SHORT)

    return result


@router.get("/best-skus-monthly")
def get_best_skus_monthly(
    month: Optional[int] = Query(None, description="Month (1-12), defaults to current"),
    year: Optional[int] = Query(None, description="Year, defaults to current"),
    limit: int = Query(20, description="Number of top SKUs"),
    force_refresh: bool = Query(False, description="Compatibility flag; currently ignored"),
    b2c_only: bool = Query(False, description="Exclude unpriced wholesale/B2B orders"),
):
    service = get_unicommerce_data_service()
    return service.get_best_skus_monthly(
        month=month,
        year=year,
        limit=limit,
        b2c_only=b2c_only,
    )


@router.get("/sku-velocity")
def get_sku_velocity(
    month: Optional[int] = Query(None, description="Month (1-12), defaults to current"),
    year: Optional[int] = Query(None, description="Year, defaults to current"),
    limit: int = Query(25, description="Number of SKUs per category"),
    min_qty: int = Query(1, description="Minimum sold quantity for slow movers"),
    b2c_only: bool = Query(False, description="Exclude unpriced wholesale/B2B orders"),
    force_refresh: bool = Query(False, description="Compatibility flag; currently ignored"),
):
    service = get_unicommerce_data_service()
    return service.get_sku_velocity(
        month=month,
        year=year,
        limit=limit,
        min_qty=min_qty,
        b2c_only=b2c_only,
    )


@router.get("/cod-vs-prepaid")
def get_cod_vs_prepaid(
    period: str = Query("monthly", description="daily | weekly | monthly | custom"),
    date: Optional[str] = Query(None, description="Anchor date for daily/weekly/monthly (YYYY-MM-DD)"),
    from_date: Optional[str] = Query(None, description="Custom start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="Custom end date (YYYY-MM-DD)"),
    month: Optional[int] = Query(None, description="Month (1-12), defaults to current"),
    year: Optional[int] = Query(None, description="Year, defaults to current"),
):
    service = get_unicommerce_data_service()
    return service.get_cod_vs_prepaid(
        period=period,
        date=date,
        from_date=from_date,
        to_date=to_date,
        month=month,
        year=year,
    )


@router.get("/sales-by-sku")
def get_sales_by_sku(
    period: str = Query("today", description="today | yesterday | last_7_days | last_30_days | custom"),
    from_date: Optional[str] = Query(None, description="Custom start date YYYY-MM-DD"),
    to_date: Optional[str] = Query(None, description="Custom end date YYYY-MM-DD"),
):
    service = get_unicommerce_data_service()
    return service.get_sales_by_sku(
        period=period,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/bundle-skus")
async def get_bundle_skus(
    force_refresh: bool = Query(False, description="Bypass cache and re-fetch"),
    page: int = Query(0, description="Page number"),
    limit: int = Query(20, description="Items per page"),
    search: Optional[str] = Query(None, description="Search term"),
    category: Optional[str] = Query(None, description="Category filter"),
    enabled_only: bool = Query(False, description="Only show active bundles"),
):
    service = get_unicommerce_data_service()
    return await service.get_bundle_skus(
        force_refresh=force_refresh,
        page=page,
        limit=limit,
        search=search,
        category=category,
        enabled_only=enabled_only
    )


@router.get("/bundle-sales-analysis")
async def get_bundle_sales_analysis(
    period: str = Query("last_30_days", description="today | yesterday | last_7_days | last_30_days | custom"),
    from_date: Optional[str] = Query(None, description="YYYY-MM-DD (required for custom)"),
    to_date: Optional[str] = Query(None, description="YYYY-MM-DD (required for custom)"),
    force_refresh: bool = Query(False, description="Bypass cache"),
):
    service = get_unicommerce_data_service()
    return await service.get_bundle_sales_analysis(
        period=period,
        from_date=from_date,
        to_date=to_date,
        force_refresh=force_refresh,
    )


@router.get("/fabric-sales")
async def get_fabric_sales(
    month: Optional[int] = Query(None, description="Month (1-12), defaults to current"),
    year: Optional[int] = Query(None, description="Year, defaults to current"),
    from_date: Optional[str] = Query(None, description="Custom start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="Custom end date (YYYY-MM-DD)"),
    force_refresh: bool = Query(False, description="Bypass cache and re-fetch"),
):
    service = get_unicommerce_data_service()
    return await service.get_fabric_sales(
        month=month,
        year=year,
        from_date=from_date,
        to_date=to_date,
        force_refresh=force_refresh,
    )


@router.get("/validate")
def validate_revenue():
    """Run DB-first readiness and revenue coverage validation gates."""
    try:
        orchestrator = get_unicommerce_sync_orchestrator()
        readiness = orchestrator.get_release_readiness()
        return {
            "success": True,
            "validation": readiness,
            "message": "Validation uses DB-first coverage and lag gates",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


@router.get("/search-orders")
def search_orders(
    from_date: str = Query(...),
    to_date: str = Query(...),
    display_start: int = Query(0),
    display_length: int = Query(100),
):
    """Search orders with legacy-compatible payload shape."""
    try:
        from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
        to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))

        data_service = get_unicommerce_data_service()
        return data_service.search_sale_orders(
            from_date=from_dt,
            to_date=to_dt,
            display_start=display_start,
            display_length=display_length,
        )
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


@router.get("/order-items/{order_code}")
def get_order_items(order_code: str):
    """Get order details with legacy-compatible payload shape."""
    try:
        data_service = get_unicommerce_data_service()
        return data_service.get_order_details(order_code)
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


@router.post("/clear-cache")
def clear_cache():
    """Clear Unicommerce cache state (Redis primary + legacy in-memory cache)."""
    try:
        service = get_unicommerce_service()
        service._cache.clear()
        CacheService.invalidate_all_uc_cache()
        return {
            "success": True,
            "message": "Unicommerce cache cleared successfully",
            "redis_cleared": True,
            "memory_cleared": True,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


@router.get("/cache-stats")
def get_cache_stats():
    """Get cache statistics showing Redis and legacy in-memory cache state."""
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
        for cache_key, (timestamp, _payload) in service._cache.items():
            age_seconds = (datetime.now() - timestamp).total_seconds()
            remaining_seconds = max(0, service.CACHE_TTL_SECONDS - age_seconds)
            stats.append(
                {
                    "key": cache_key,
                    "age_seconds": round(age_seconds, 2),
                    "remaining_seconds": round(remaining_seconds, 2),
                    "is_expired": age_seconds >= service.CACHE_TTL_SECONDS,
                    "cached_at": timestamp.isoformat(),
                }
            )

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
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


@router.get("/cache-check")
def check_cache_status():
    """Quickly check cache status for standard periods without fetching data."""
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
                    "cached_at": timestamp.isoformat(),
                }
            else:
                cache_status[period] = {
                    "cached": False,
                    "valid": False,
                    "source": "none",
                    "age_seconds": None,
                    "remaining_seconds": 0,
                }

        all_cached = all(status["valid"] for status in cache_status.values())
        return {
            "success": True,
            "all_periods_cached": all_cached,
            "redis_enabled": redis_client is not None,
            "cache_ttl_seconds": service.CACHE_TTL_SECONDS,
            "periods": cache_status,
            "message": "All data cached and ready for instant load" if all_cached else "Some periods need fetching",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }
