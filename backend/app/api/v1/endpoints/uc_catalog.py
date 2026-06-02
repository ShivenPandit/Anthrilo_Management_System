"""Unicommerce catalog and item type endpoints."""

from fastapi import APIRouter, Body
import csv
import io
import httpx
import asyncio
import time as time_module
import logging
from typing import Any, Dict, List, Optional

from app.services.unicommerce_api_service import get_uc_api_service
from app.core.token_manager import get_token_manager

router = APIRouter()
logger = logging.getLogger(__name__)


# Categories
@router.post("/category/create-or-edit")
async def create_or_update_category(payload: Dict[str, Any] = Body(...)):
    """
    Create or update product category.
    Payload: {
        category: {
            code, name, gstTaxTypeCode,
            taxTypeCode?, hsnCode?, expirable?, shelfLife?, ...
        }
    }
    """
    try:
        svc = get_uc_api_service()
        return await svc.post("/product/category/addOrEdit", payload)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"successful": False, "error": str(e)}


# Items (single)
@router.post("/item/create-or-edit")
async def create_or_update_item(payload: Dict[str, Any] = Body(...)):
    """
    Create or update a single item.
    Payload: {
        itemType: {
            categoryCode, skuCode, name, type?, description?,
            length?, width?, height?, weight?, color?, size?, brand?,
            maxRetailPrice?, basePrice?, costPrice?, gstTaxTypeCode?, hsnCode?,
            imageUrl?, productPageUrl?, tags?, customFieldValues?, ...
        }
    }
    """
    try:
        svc = get_uc_api_service()
        return await svc.post("/catalog/itemType/createOrEdit", payload)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"successful": False, "error": str(e)}


# Items (multiple)
@router.post("/items/create-or-edit")
async def create_or_update_items(payload: Dict[str, Any] = Body(...)):
    """
    Create or update multiple items.
    Payload: {
        itemTypes: [
            { categoryCode, skuCode, name, ... },
            { categoryCode, skuCode, name, ... }
        ]
    }
    """
    try:
        svc = get_uc_api_service()
        return await svc.post("/catalog/itemTypes/createOrEdit", payload)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"successful": False, "error": str(e)}


# Channel item type
@router.post("/channel-item/create-or-edit")
async def create_or_update_channel_item_type(payload: Dict[str, Any] = Body(...)):
    """
    Link Uniware product SKU with channel SKU.
    Payload: {
        channelItemType: {
            channelCode, channelProductId, sellerSkuCode, skuCode,
            blockedInventory?, live?, verified?, disabled?
        }
    }
    """
    try:
        svc = get_uc_api_service()
        return await svc.post("/channel/createChannelItemType", payload)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"successful": False, "error": str(e)}


# Get item details
@router.post("/item/get")
async def get_item_details(payload: Dict[str, Any] = Body(...)):
    """
    Get item details by SKU code.
    Payload: { skuCode, cartonScanIdentifier?, kitSku? }
    """
    try:
        svc = get_uc_api_service()
        return await svc.post("/catalog/itemType/get", payload)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"successful": False, "error": str(e)}


@router.post("/item/barcode")
async def get_item_barcode_details(payload: Dict[str, Any] = Body(...)):
    """
    Get item barcode details.
    Payload: { itemCode, facility_code? }
    """
    try:
        svc = get_uc_api_service()
        fc = payload.pop("facility_code", None)
        return await svc.post("/product/item/get", payload, facility_code=fc)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"successful": False, "error": str(e)}


# Search items
@router.post("/item/search")
async def search_items(payload: Dict[str, Any] = Body(...)):
    """
    Search items with filters (DB-first).
    Payload: {
        keyword?, productCode?, categoryCode?,
        stockFilter?,
        searchOptions?: { searchKey?, displayLength?, displayStart?, ... },
        getAggregates?: boolean
    }
    """
    from app.db.session import SessionLocal
    from app.db.export_models import FacilityInventorySnapshot
    from sqlalchemy import or_, String
    from sqlalchemy.sql import cast

    db = SessionLocal()
    try:
        keyword = payload.get("keyword") or ""
        stock_filter = payload.get("stockFilter") or "all"
        opts = payload.get("searchOptions") or {}
        display_start = opts.get("displayStart", 0)
        display_length = opts.get("displayLength", 25)

        query = db.query(FacilityInventorySnapshot)

        if stock_filter == "in_stock":
            query = query.filter(FacilityInventorySnapshot.inventory > 0)
        elif stock_filter == "out_of_stock":
            query = query.filter(FacilityInventorySnapshot.inventory <= 0)

        if keyword:
            kw = f"%{keyword}%"
            query = query.filter(
                or_(
                    FacilityInventorySnapshot.sku.ilike(kw),
                    FacilityInventorySnapshot.category.ilike(kw),
                    FacilityInventorySnapshot.brand.ilike(kw),
                    FacilityInventorySnapshot.color.ilike(kw),
                    cast(FacilityInventorySnapshot.raw_data, String).ilike(kw)
                )
            )

        total_records = query.count()
        rows = query.order_by(FacilityInventorySnapshot.sku).offset(display_start).limit(display_length).all()

        elements = []
        for row in rows:
            raw = row.raw_data or {}
            
            elements.append({
                "skuCode": row.sku,
                "name": raw.get("Item Type Name", ""),
                "description": "",
                "categoryName": row.category or "",
                "color": row.color or "",
                "size": row.size or "",
                "brand": row.brand or "",
                "price": float(row.mrp or row.cost_price or 0),
                "weight": float(raw.get("Weight", 0) or 0),
                "enabled": not row.disabled,
                "inventorySnapshots": [
                    {
                        "inventory": row.inventory or 0,
                    }
                ]
            })

        return {
            "successful": True,
            "totalRecords": total_records,
            "elements": elements
        }
    except Exception as e:
        logger.error(f"Error in search_items: {e}", exc_info=True)
        return {"successful": False, "error": str(e)}
    finally:
        db.close()


async def _compute_inventory_aggregates(svc, base_payload: Dict[str, Any]) -> Dict[str, int]:
    """
    Fetch all pages and compute aggregate totals.
    Returns totals for: inventory, virtualInventory, openSale, badInventory, etc.
    """
    try:
        # First, get total records count
        initial_payload = {
            **base_payload,
            "searchOptions": {
                **base_payload.get("searchOptions", {}),
                "displayStart": 0,
                "displayLength": 1
            }
        }
        initial_result = await svc.post("/product/itemType/search", initial_payload)

        if not initial_result.get("successful"):
            logger.warning(f"Initial aggregate query failed: {initial_result}")
            return {}

        total_records = initial_result.get("totalRecords", 0)
        logger.info(f"Total records for aggregates: {total_records}")

        if total_records == 0:
            return {
                "totalInventory": 0,
                "totalVirtualInventory": 0,
                "totalOpenSale": 0,
                "totalBadInventory": 0,
                "totalPutawayPending": 0,
                "totalValue": 0,
                "skusWithStock": 0,
                "skusOutOfStock": 0
            }

        # Fetch in batches of 100
        batch_size = 100
        totals = {
            "totalInventory": 0,
            "totalVirtualInventory": 0,
            "totalOpenSale": 0,
            "totalBadInventory": 0,
            "totalPutawayPending": 0,
            "totalValue": 0,
            "skusWithStock": 0,
            "skusOutOfStock": 0
        }

        # Limit to first 10,000 items for performance (configurable)
        # For accurate totals across ALL SKUs, use /inventory/summary endpoint instead
        max_items = min(total_records, 10000)

        for start in range(0, max_items, batch_size):
            batch_payload = {
                **base_payload,
                "searchOptions": {
                    **base_payload.get("searchOptions", {}),
                    "displayStart": start,
                    "displayLength": min(batch_size, max_items - start)
                }
            }

            batch_result = await svc.post("/product/itemType/search", batch_payload)

            if not batch_result.get("successful"):
                logger.warning(f"Batch query failed at start={start}")
                continue

            elements = batch_result.get("elements", [])
            for item in elements:
                snapshots = item.get("inventorySnapshots", [])
                if snapshots:
                    snap = snapshots[0]
                    # Normalize inventory field
                    inv = snap.get("inventory", 0) or snap.get(
                        "goodInventory", 0) or snap.get("availableInventory", 0) or 0

                    totals["totalInventory"] += inv
                    totals["totalVirtualInventory"] += snap.get(
                        "virtualInventory", 0) or 0
                    totals["totalOpenSale"] += snap.get("openSale", 0) or 0
                    totals["totalBadInventory"] += snap.get(
                        "badInventory", 0) or 0
                    totals["totalPutawayPending"] += snap.get(
                        "putawayPending", 0) or 0

                    # Count SKUs with/without stock
                    if inv > 0:
                        totals["skusWithStock"] += 1
                    else:
                        totals["skusOutOfStock"] += 1

                    # Calculate value (inventory * price)
                    price = item.get("price", 0) or 0
                    totals["totalValue"] += inv * price

        logger.info(f"Aggregates computed: {totals}")
        return totals

    except Exception as e:
        logger.error(f"Error computing aggregates: {e}", exc_info=True)
        return {}


# Inventory summary via export job

# Export columns matching the working curl — every field we need
INVENTORY_EXPORT_COLUMNS = [
    "facility", "itemTypeName", "ean", "upc", "isbn",
    "color", "size", "brand", "categoryName",
    "openSale", "inventory", "inventoryBlocked", "badInventory",
    "putawayPending", "pendingInventoryAssessment", "openPurchase",
    "enabled", "updated", "costPrice",
]

EXPORT_MAX_POLL_SECONDS = 300
EXPORT_INITIAL_POLL_INTERVAL = 2
EXPORT_MAX_POLL_INTERVAL = 10
EXPORT_POLL_BACKOFF = 1.5


async def _create_inventory_export_job() -> Optional[str]:
    """Create an 'Inventory Snapshot' export job on Unicommerce. Returns jobCode."""
    tm = get_token_manager()
    base_url = f"https://{tm.tenant}.unicommerce.com/services/rest/v1"
    url = f"{base_url}/export/job/create"
    timeout = httpx.Timeout(60.0, connect=15.0)

    payload = {
        "exportJobTypeName": "Inventory Snapshot",
        "frequency": "ONETIME",
        "exportColums": INVENTORY_EXPORT_COLUMNS,
        "exportFilters": [],
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            headers = await tm.get_headers()
            headers["Facility"] = "anthrilo"

            resp = await client.post(url, json=payload, headers=headers)

            if resp.status_code == 401:
                tm.invalidate_token()
                await tm.get_valid_token()
                headers = await tm.get_headers()
                headers["Facility"] = "anthrilo"
                resp = await client.post(url, json=payload, headers=headers)

            if resp.status_code >= 400:
                logger.error(f"Inventory export: Job create HTTP {resp.status_code}: {resp.text[:500]}")
                return None

            data = resp.json()
            if data.get("successful"):
                job_code = data.get("jobCode")
                logger.info(f"Inventory export: Job created {job_code}")
                return job_code
            else:
                logger.error(f"Inventory export: Job create failed: {data}")
                return None
    except Exception as e:
        logger.error(f"Inventory export: Job create exception: {e}", exc_info=True)
        return None


async def _poll_inventory_export(job_code: str) -> Optional[str]:
    """Poll until COMPLETE, return download URL."""
    tm = get_token_manager()
    base_url = f"https://{tm.tenant}.unicommerce.com/services/rest/v1"
    url = f"{base_url}/export/job/status"
    timeout = httpx.Timeout(60.0, connect=15.0)
    payload = {"jobCode": job_code}

    t0 = time_module.time()
    interval = EXPORT_INITIAL_POLL_INTERVAL

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            while (time_module.time() - t0) < EXPORT_MAX_POLL_SECONDS:
                headers = await tm.get_headers()
                headers["Facility"] = "anthrilo"

                resp = await client.post(url, json=payload, headers=headers)

                if resp.status_code == 401:
                    tm.invalidate_token()
                    await tm.get_valid_token()
                    headers = await tm.get_headers()
                    headers["Facility"] = "anthrilo"
                    resp = await client.post(url, json=payload, headers=headers)

                resp.raise_for_status()
                data = resp.json()

                if data.get("successful"):
                    status = data.get("status", "")
                    elapsed = time_module.time() - t0

                    if status == "COMPLETE":
                        file_path = data.get("filePath", "")
                        logger.info(f"Inventory export: COMPLETE in {elapsed:.1f}s {file_path}")
                        return file_path
                    elif status in ("FAILED", "CANCELLED"):
                        logger.error(f"Inventory export: {status} after {elapsed:.1f}s")
                        return None
                    else:
                        logger.debug(f"Inventory export: status={status} ({elapsed:.1f}s)")

                await asyncio.sleep(interval)
                interval = min(interval * EXPORT_POLL_BACKOFF, EXPORT_MAX_POLL_INTERVAL)

    except Exception as e:
        logger.error(f"Inventory export: Poll exception: {e}", exc_info=True)
        return None

    logger.error(f"Inventory export: Timed out after {EXPORT_MAX_POLL_SECONDS}s")
    return None


def _safe_int(val) -> int:
    """Parse a CSV cell to int, handling floats like '3.0' and blanks."""
    if val is None or val == "":
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def _safe_float(val) -> float:
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


async def _download_parse_inventory_csv(download_url: str) -> List[Dict[str, Any]]:
    """Download the Inventory Snapshot CSV and return a list of row dicts."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            resp = await client.get(download_url)

            if resp.status_code in (401, 403):
                tm = get_token_manager()
                headers = await tm.get_headers()
                resp = await client.get(download_url, headers=headers)

            resp.raise_for_status()
            csv_text = resp.text

        if not csv_text or not csv_text.strip():
            logger.warning("Inventory export: Downloaded CSV is empty")
            return []

        reader = csv.DictReader(io.StringIO(csv_text))
        logger.info(f"Inventory export: CSV columns: {reader.fieldnames}")

        rows: List[Dict[str, Any]] = []
        for row in reader:
            # Normalize all SKU fields to uppercase to prevent case-variant
            # duplicates. The CSV has "Item Type SKU" (uppercase) and
            # "Item SkuCode" (lowercase) which must be treated as the same SKU.
            for sku_field in ("Item SkuCode", "itemSkuCode", "Item Type SKU", "itemTypeSKU", "SKU Code", "skuCode"):
                val = (row.get(sku_field) or "").strip()
                if val:
                    row[sku_field] = val.upper()
            rows.append(row)

        logger.info(f"Inventory export: Parsed {len(rows)} inventory rows from CSV")
        return rows

    except Exception as e:
        logger.error(f"Inventory export: CSV download/parse error: {e}", exc_info=True)
        return []


# ── DB-first inventory summary ────────────────────────────────────────────────

def _build_summary_from_db() -> dict:
    """Compute inventory summary from facility_inventory_snapshot (no API call)."""
    from app.db.session import SessionLocal
    from app.db.export_models import FacilityInventorySnapshot
    from sqlalchemy import func

    db = SessionLocal()
    try:
        rows = db.query(FacilityInventorySnapshot).all()
        if not rows:
            return {}
        last_sync = db.query(func.max(FacilityInventorySnapshot.synced_at)).scalar()
        total_skus = len(rows)
        active_count = 0
        facility_skus = 0
        skus_with_stock = 0
        skus_out_of_stock = 0
        total_real_inventory = 0
        total_stock_value = 0.0
        category_totals: Dict[str, Dict] = {}

        for row in rows:
            if not row.disabled:
                active_count += 1
            inv = row.inventory or 0
            inv_blocked = row.reserved_inventory or 0
            raw = row.raw_data or {}
            open_sale = _safe_int(raw.get("Open Sale") or raw.get("openSale"))
            bad_inv = _safe_int(raw.get("Bad Inventory") or raw.get("badInventory"))
            putaway = _safe_int(raw.get("Putaway Pending") or raw.get("putawayPending"))
            open_purchase = _safe_int(raw.get("Open Purchase") or raw.get("openPurchase"))
            pending_assess = _safe_int(
                raw.get("Pending Inventory Assessment") or raw.get("pendingInventoryAssessment")
            )
            if any(x != 0 for x in [inv, open_sale, inv_blocked, bad_inv, putaway, open_purchase, pending_assess]):
                facility_skus += 1
            total_real_inventory += inv
            total_stock_value += inv * float(row.cost_price or 0.0)
            cat = row.category or "Uncategorized"
            if cat not in category_totals:
                category_totals[cat] = {"skus": 0, "inventory": 0, "inStock": 0, "outOfStock": 0}
            category_totals[cat]["skus"] += 1
            category_totals[cat]["inventory"] += inv
            if inv > 0:
                skus_with_stock += 1
                category_totals[cat]["inStock"] += 1
            else:
                skus_out_of_stock += 1
                category_totals[cat]["outOfStock"] += 1

        oos_pct = round((skus_out_of_stock / total_skus) * 100) if total_skus > 0 else 0
        categories_list = sorted(
            [{"name": n, **d} for n, d in category_totals.items()],
            key=lambda c: c["inventory"], reverse=True,
        )
        return {
            "successful": True,
            "source": "db_snapshot",
            "last_synced_at": last_sync.isoformat() if last_sync else None,
            "totalProducts": total_skus,
            "totalSKUs": total_skus,
            "activeSKUs": active_count,
            "facilitySKUs": facility_skus,
            "skusWithStock": skus_with_stock,
            "skusOutOfStock": skus_out_of_stock,
            "outOfStockPercent": oos_pct,
            "totalRealInventory": total_real_inventory,
            "totalVirtualInventory": 0,
            "totalStockValue": round(total_stock_value, 2),
            "categories": categories_list,
        }
    finally:
        db.close()


def _db_snapshot_age_seconds() -> float:
    """Seconds since last inventory snapshot sync. Returns inf if never synced."""
    from app.db.session import SessionLocal
    from app.db.export_models import FacilityInventorySnapshot
    from sqlalchemy import func
    from datetime import datetime

    db = SessionLocal()
    try:
        last_sync = db.query(func.max(FacilityInventorySnapshot.synced_at)).scalar()
        if last_sync is None:
            return float("inf")
        return (datetime.utcnow() - last_sync).total_seconds()
    finally:
        db.close()


_INVENTORY_REFRESH_RUNNING = False


async def _background_refresh_inventory():
    """Fire-and-forget: sync inventory from Unicommerce export, then rebuild cache."""
    global _INVENTORY_REFRESH_RUNNING
    if _INVENTORY_REFRESH_RUNNING:
        return
    _INVENTORY_REFRESH_RUNNING = True
    try:
        from app.services.sync_inventory_snapshot import fetch_and_sync_inventory
        from app.services.cache_service import CacheService
        logger.info("INV_SUMMARY: background refresh starting")
        result = await fetch_and_sync_inventory(facility_code="anthrilo")
        if result.get("success"):
            logger.info(f"INV_SUMMARY: refresh done — {result.get('inserted', 0)} SKUs upserted")
            fresh = _build_summary_from_db()
            if fresh:
                CacheService.set("uc:inventory:summary:v3", fresh, 3600)
        else:
            logger.warning(f"INV_SUMMARY: refresh failed: {result.get('error')}")
    except Exception as exc:
        logger.error(f"INV_SUMMARY: background refresh error: {exc}", exc_info=True)
    finally:
        _INVENTORY_REFRESH_RUNNING = False


@router.get("/inventory/summary")
async def get_inventory_summary(force_refresh: bool = False):
    """Inventory summary — DB-first with background refresh when stale.

    Normal path (< 5 ms):
      1. Check in-process/Redis cache.
      2. Read ``facility_inventory_snapshot`` DB table directly.
      3. If snapshot > 1 h old, fire a background Unicommerce export so the
         *next* request gets fresh data — current caller is not blocked.

    ``?force_refresh=true`` (blocking, ~15-30 s):
      Runs a full Unicommerce export job NOW, upserts DB, rebuilds cache.

    Stats cards and the catalog table now read from the SAME DB snapshot,
    eliminating the live-vs-stale count discrepancy.
    """
    from app.services.cache_service import CacheService
    from app.services.sync_inventory_snapshot import fetch_and_sync_inventory
    from app.core.config import settings
    import asyncio

    stale_threshold = settings.UNICOMMERCE_INVENTORY_SUMMARY_CACHE_TTL_SECONDS
    cache_key = "uc:inventory:summary:v3"

    # Purge legacy cache keys (idempotent)
    for old_key in ("uc:inventory:summary:all", "uc:inventory:summary:v2"):
        CacheService.delete(old_key)

    # ── Force-refresh: blocking live export ─────────────────────────────────
    if force_refresh:
        logger.info("INV_SUMMARY: force_refresh=true — running blocking live export")
        try:
            await fetch_and_sync_inventory(facility_code="anthrilo")
        except Exception as exc:
            logger.error(f"INV_SUMMARY: force refresh error: {exc}", exc_info=True)
        summary = _build_summary_from_db()
        if summary:
            CacheService.set(cache_key, summary, stale_threshold)
            return summary
        return {"successful": False, "error": "Force refresh completed but DB read failed"}

    # ── In-process / Redis cache (fastest path) ──────────────────────────────
    cached = CacheService.get(cache_key)
    age = _db_snapshot_age_seconds()
    if cached and age <= stale_threshold:
        return cached

    if age > stale_threshold:
        logger.info(
            f"INV_SUMMARY: snapshot is {age / 3600:.1f}h old — refreshing from Unicommerce"
        )
        try:
            sync_result = await fetch_and_sync_inventory(facility_code="anthrilo")
            if not sync_result.get("success"):
                logger.warning(
                    f"INV_SUMMARY: live refresh reported failure — returning latest DB snapshot: {sync_result.get('error')}"
                )
        except Exception as exc:
            logger.error(f"INV_SUMMARY: live refresh error: {exc}", exc_info=True)

    # ── DB-first (< 5 ms) ────────────────────────────────────────────────────
    db_summary = _build_summary_from_db()

    if db_summary:
        refreshed_age = _db_snapshot_age_seconds()
        db_summary["stale"] = refreshed_age > stale_threshold
        db_summary["snapshot_age_minutes"] = round(refreshed_age / 60, 1)
        # Cache for shorter of stale_threshold or 15 min (avoids serving stale data forever)
        CacheService.set(cache_key, db_summary, min(stale_threshold, 900))
        return db_summary

    # ── Cold start: DB empty — run synchronous export once ───────────────────
    logger.warning("INV_SUMMARY: facility_inventory_snapshot is empty — cold-start export")
    try:
        sync_result = await fetch_and_sync_inventory(facility_code="anthrilo")
        if not sync_result.get("success"):
            return {"successful": False, "error": "Initial inventory export failed", "totalSKUs": 0}
    except Exception as exc:
        logger.error(f"INV_SUMMARY: cold-start export error: {exc}", exc_info=True)
        return {"successful": False, "error": str(exc), "totalSKUs": 0}

    summary = _build_summary_from_db()
    if summary:
        CacheService.set(cache_key, summary, stale_threshold)
        return summary

    return {"successful": False, "error": "Summary build failed after export", "totalSKUs": 0}

