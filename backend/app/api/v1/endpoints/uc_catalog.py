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
    Search items with filters.
    Payload: {
        keyword?, productCode?, categoryCode?,
        getInventorySnapshot?, updatedSinceInHour?, skuType?,
        searchOptions?: { searchKey?, displayLength?, displayStart?, ... },
        getAggregates?: boolean (to fetch totals across all pages)
    }
    """
    try:
        svc = get_uc_api_service()
        get_aggregates = payload.pop("getAggregates", False)

        result = await svc.post("/product/itemType/search", payload)

        # Log sample if inventory snapshot requested
        if payload.get("getInventorySnapshot") and result.get("successful"):
            elements = result.get("elements", [])
            if elements:
                first_item = elements[0]
                logger.info(f"Sample item structure: SKU={first_item.get('skuCode')}, "
                            f"has inventorySnapshots: {bool(first_item.get('inventorySnapshots'))}")
                if first_item.get("inventorySnapshots"):
                    snap = first_item["inventorySnapshots"][0]
                    logger.info(
                        f"Sample inventory snapshot keys: {list(snap.keys())}")
                    logger.info(f"Sample inventory values: inventory={snap.get('inventory')}, "
                                f"goodInventory={snap.get('goodInventory')}, "
                                f"availableInventory={snap.get('availableInventory')}, "
                                f"virtualInventory={snap.get('virtualInventory')}")

        # Transform response to ensure consistent field naming
        if result.get("successful") and payload.get("getInventorySnapshot"):
            elements = result.get("elements", [])

            # Collect SKU codes for dedicated inventory snapshot lookup
            sku_codes = [item.get("skuCode")
                         for item in elements if item.get("skuCode")]

            # Fetch accurate virtualInventory from dedicated snapshot API
            vi_map = {}
            if sku_codes:
                try:
                    snap_result = await svc.post(
                        "/inventory/inventorySnapshot/get",
                        {"itemTypeSKUs": sku_codes},
                        facility_code="anthrilo",
                    )
                    if snap_result.get("successful"):
                        for snap in snap_result.get("inventorySnapshots", []):
                            sku = snap.get("itemTypeSKU", "")
                            vi_map[sku] = {
                                "virtualInventory": snap.get("virtualInventory", 0) or 0,
                                "inventory": snap.get("inventory", 0) or 0,
                                "openSale": snap.get("openSale", 0) or 0,
                                "badInventory": snap.get("badInventory", 0) or 0,
                                "putawayPending": snap.get("putawayPending", 0) or 0,
                                "inventoryBlocked": snap.get("inventoryBlocked", 0) or 0,
                            }
                except Exception as e:
                    logger.warning(f"Failed to fetch dedicated snapshot: {e}")

            for item in elements:
                snapshots = item.get("inventorySnapshots", [])
                sku = item.get("skuCode", "")

                # If we have dedicated snapshot data, use it (more accurate)
                if sku in vi_map:
                    if snapshots:
                        snap = snapshots[0]
                        snap.update(vi_map[sku])
                    else:
                        item["inventorySnapshots"] = [vi_map[sku]]
                        snapshots = item["inventorySnapshots"]

                for snap in snapshots:
                    # Normalize field names - try multiple possible field names
                    if "goodInventory" in snap and "inventory" not in snap:
                        snap["inventory"] = snap["goodInventory"]
                    if "availableInventory" in snap and "inventory" not in snap:
                        snap["inventory"] = snap["availableInventory"]
                    # Ensure numeric values for all inventory fields
                    snap["inventory"] = snap.get("inventory", 0) or 0
                    snap["virtualInventory"] = snap.get(
                        "virtualInventory", 0) or 0
                    snap["badInventory"] = snap.get("badInventory", 0) or 0
                    snap["openSale"] = snap.get("openSale", 0) or 0
                    snap["inventoryBlocked"] = snap.get(
                        "inventoryBlocked", 0) or 0
                    snap["putawayPending"] = snap.get("putawayPending", 0) or 0

        # Compute aggregates if requested
        if get_aggregates and result.get("successful") and payload.get("getInventorySnapshot"):
            logger.info("Computing aggregates across all pages...")
            aggregates = await _compute_inventory_aggregates(svc, payload)
            result["aggregates"] = aggregates

        return result
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"successful": False, "error": str(e)}


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
            rows.append(row)

        logger.info(f"Inventory export: Parsed {len(rows)} inventory rows from CSV")
        return rows

    except Exception as e:
        logger.error(f"Inventory export: CSV download/parse error: {e}", exc_info=True)
        return []


@router.get("/inventory/summary")
async def get_inventory_summary(force_refresh: bool = False):
    """
    Aggregated inventory summary across ALL SKUs using the
    Unicommerce **Export Job API** (Inventory Snapshot export).

    Flow:
      1. Create export job   1 API call
      2. Poll until COMPLETE  ~3-8 polls
      3. Download CSV         1 HTTP GET
      4. Parse & aggregate in-memory

    ~3 API calls total regardless of catalog size. ~10-30s.
    Redis-cached for 4 hours.
    """
    from app.services.cache_service import CacheService

    cache_key = "uc:inventory:summary:v3"

    # Clean up old cache keys
    CacheService.delete("uc:inventory:summary:all")
    CacheService.delete("uc:inventory:summary:v2")

    if not force_refresh:
        cached = CacheService.get(cache_key)
        if cached:
            logger.info("Returning cached inventory summary (v3-export)")
            return cached

    try:
        # ── Step 1: Create export job ──
        job_code = await _create_inventory_export_job()
        if not job_code:
            return {"successful": False, "error": "Failed to create inventory export job"}

        # ── Step 2: Poll until complete ──
        download_url = await _poll_inventory_export(job_code)
        if not download_url:
            return {"successful": False, "error": "Inventory export job failed or timed out"}

        # ── Step 3: Download & parse CSV ──
        rows = await _download_parse_inventory_csv(download_url)
        if not rows:
            return {"successful": False, "error": "Inventory export CSV was empty"}

        # ── Step 4: Aggregate ──
        # The CSV may contain multiple rows per SKU (e.g., if present in multiple facilities)
        # We must deduplicate by 'itemTypeName' (SKU code) and sum their inventory
        aggregated_rows = {}
        for row in rows:
            sku = (row.get("Item Type Name") or row.get("itemTypeName") or "").strip()
            if not sku:
                continue
                
            if sku not in aggregated_rows:
                aggregated_rows[sku] = {
                    "cat": (row.get("Category Name") or row.get("categoryName") or row.get("Category") or "Uncategorized").strip() or "Uncategorized",
                    "enabled": False,
                    "cost_price": _safe_float(row.get("Cost Price") or row.get("costPrice")),
                    "inv": 0,
                    "open_sale": 0,
                    "inv_blocked": 0,
                    "bad_inv": 0,
                    "putaway": 0,
                    "open_purchase": 0,
                    "pending_assess": 0,
                }
                
            # If any row says it's enabled, we consider it enabled globally
            enabled_raw = (row.get("Enabled") or row.get("enabled") or "").strip().lower()
            if enabled_raw in ("true", "1", "yes", "y"):
                aggregated_rows[sku]["enabled"] = True
                
            # Accumulate
            aggregated_rows[sku]["inv"] += _safe_int(row.get("Inventory") or row.get("inventory"))
            aggregated_rows[sku]["open_sale"] += _safe_int(row.get("Open Sale") or row.get("openSale"))
            aggregated_rows[sku]["inv_blocked"] += _safe_int(row.get("Inventory Blocked") or row.get("inventoryBlocked"))
            aggregated_rows[sku]["bad_inv"] += _safe_int(row.get("Bad Inventory") or row.get("badInventory"))
            aggregated_rows[sku]["putaway"] += _safe_int(row.get("Putaway Pending") or row.get("putawayPending"))
            aggregated_rows[sku]["open_purchase"] += _safe_int(row.get("Open Purchase") or row.get("openPurchase"))
            aggregated_rows[sku]["pending_assess"] += _safe_int(row.get("Pending Inventory Assessment") or row.get("pendingInventoryAssessment"))

        unique_skus = list(aggregated_rows.values())
        total_skus = len(unique_skus)
        
        active_count = 0
        facility_skus = 0
        skus_with_stock = 0
        skus_out_of_stock = 0
        total_real_inventory = 0
        total_virtual_inventory = 0  # not in this export; will stay 0
        total_stock_value = 0.0

        category_totals: Dict[str, Dict[str, int]] = {}

        for item in unique_skus:
            cat = item["cat"]
            enabled = item["enabled"]
            inv = item["inv"]
            open_sale = item["open_sale"]
            inv_blocked = item["inv_blocked"]
            bad_inv = item["bad_inv"]
            putaway = item["putaway"]
            open_purchase = item["open_purchase"]
            pending_assess = item["pending_assess"]
            cost_price = item["cost_price"]

            if enabled:
                active_count += 1

            # A SKU is "at facility" if any inventory-related field is non-zero
            has_activity = any(x != 0 for x in [
                inv, open_sale, inv_blocked, bad_inv,
                putaway, open_purchase, pending_assess,
            ])
            if has_activity:
                facility_skus += 1

            total_real_inventory += inv
            total_stock_value += inv * cost_price

            # Category breakdown
            if cat not in category_totals:
                category_totals[cat] = {
                    "skus": 0, "inventory": 0, "inStock": 0, "outOfStock": 0,
                }
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
            key=lambda c: c["inventory"],
            reverse=True,
        )

        result = {
            "successful": True,
            "totalProducts": total_skus,
            "totalSKUs": total_skus,
            "activeSKUs": active_count,
            "facilitySKUs": facility_skus,
            "skusWithStock": skus_with_stock,
            "skusOutOfStock": skus_out_of_stock,
            "outOfStockPercent": oos_pct,
            "totalRealInventory": total_real_inventory,
            "totalVirtualInventory": total_virtual_inventory,
            "totalStockValue": round(total_stock_value, 2),
            "categories": categories_list,
        }

        logger.info(
            f"INV_EXPORT: Summary done — {total_skus} SKUs, "
            f"{skus_with_stock} in-stock, {len(categories_list)} categories"
        )

        CacheService.set(cache_key, result, 14400)  # 4h TTL
        return result

    except Exception as e:
        logger.error(f"Error computing inventory summary: {e}", exc_info=True)
        return {"successful": False, "error": str(e)}
