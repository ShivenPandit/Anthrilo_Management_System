import asyncio
import csv
import io
import logging
import time as time_module
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import text

from app.core.token_manager import get_token_manager
from app.db.export_models import FacilityInventorySnapshot
from app.db.session import SessionLocal
from app.services.parity_validator import ParityValidator

logger = logging.getLogger(__name__)

# Export columns matching the working curl — every field we need
INVENTORY_EXPORT_COLUMNS = [
    "facility", "itemTypeName", "ean", "upc", "isbn",
    "color", "size", "brand", "categoryName",
    "openSale", "inventory", "inventoryBlocked", "badInventory",
    "putawayPending", "pendingInventoryAssessment", "openPurchase",
    "enabled", "updated", "costPrice", "maxRetailPrice",
]

EXPORT_MAX_POLL_SECONDS = 300
EXPORT_INITIAL_POLL_INTERVAL = 2
EXPORT_MAX_POLL_INTERVAL = 10
EXPORT_POLL_BACKOFF = 1.5


async def _create_inventory_export_job(facility_code: str) -> Optional[str]:
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
            headers["Facility"] = facility_code

            resp = await client.post(url, json=payload, headers=headers)

            if resp.status_code == 401:
                tm.invalidate_token()
                await tm.get_valid_token()
                headers = await tm.get_headers()
                headers["Facility"] = facility_code
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


async def _poll_inventory_export(job_code: str, facility_code: str) -> Optional[str]:
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
                headers["Facility"] = facility_code

                resp = await client.post(url, json=payload, headers=headers)

                if resp.status_code == 401:
                    tm.invalidate_token()
                    await tm.get_valid_token()
                    headers = await tm.get_headers()
                    headers["Facility"] = facility_code
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
        rows: List[Dict[str, Any]] = []
        # Fetch name-to-sku mapping from latest item_master export to resolve missing SKUs in Inventory Snapshot CSV
        name_to_sku_map = {}
        try:
            with SessionLocal() as db:
                res = db.execute(text("""
                    SELECT er.payload->>'Name', er.payload->>'Product Code'
                    FROM export_rows er
                    JOIN export_jobs ej ON er.export_job_id = ej.id
                    WHERE ej.export_type = 'item_master' AND ej.status = 'completed'
                    ORDER BY ej.id DESC
                """))
                for r_name, r_sku in res:
                    if r_name and r_sku:
                        name_to_sku_map[r_name.strip().lower()] = r_sku.strip()
            logger.info(f"Loaded {len(name_to_sku_map)} name-to-sku mappings from item_master")
        except Exception as e:
            logger.error(f"Failed to load name-to-sku map: {e}")

        for row in reader:
            item_name = (row.get("Item Type Name") or row.get("itemTypeName") or "").strip().lower()
            mapped_sku = name_to_sku_map.get(item_name)
            if mapped_sku:
                row["Item Type SKU"] = mapped_sku
            rows.append(row)

        logger.info(f"Inventory export: Parsed {len(rows)} inventory rows from CSV")
        return rows

    except Exception as e:
        logger.error(f"Inventory export: CSV download/parse error: {e}", exc_info=True)
        return []


async def fetch_and_sync_inventory(facility_code: str = "anthrilo") -> Dict[str, Any]:
    """
    Fetch exact Inventory Snapshot from Unicommerce, deduplicate SKUs,
    and upsert them into the facility_inventory_snapshot PostgreSQL table.
    """
    start_time = time_module.time()
    
    # Step 1: Trigger Unicommerce Export
    job_code = await _create_inventory_export_job(facility_code)
    if not job_code:
        return {"success": False, "error": "Failed to create export job"}

    # Step 2: Poll
    download_url = await _poll_inventory_export(job_code, facility_code)
    if not download_url:
        return {"success": False, "error": "Poll failed or timed out"}

    # Step 3: Download & Parse
    rows = await _download_parse_inventory_csv(download_url)
    if not rows:
        return {"success": True, "inserted": 0, "fetched": 0, "duplicates_removed": 0}

    # Step 4: Map every CSV row to a distinct DB row to match Unicommerce export exactly.
    # Unicommerce allows duplicate 'Item Type Name's (e.g. same name but different colors).
    # To bypass the DB UniqueConstraint(sku, facility) and match the row counts exactly, 
    # we append a counter to duplicate SKUs.
    aggregated_rows = {}
    for row in rows:
        sku_base = (row.get("Item Type SKU") or row.get("itemTypeSKU") or "").strip()
        if not sku_base:
            continue
            
        sku = sku_base
        if sku not in aggregated_rows:
            aggregated_rows[sku] = {
                "sku": sku,
                "facility_code": facility_code,
                "category": (row.get("Category Name") or row.get("categoryName") or row.get("Category") or "Uncategorized").strip() or "Uncategorized",
                "color": (row.get("Color") or row.get("color") or "").strip() or None,
                "size": (row.get("Size") or row.get("size") or "").strip() or None,
                "brand": (row.get("Brand") or row.get("brand") or "").strip() or None,
                "disabled": False,
                "cost_price": _safe_float(row.get("Cost Price") or row.get("costPrice")),
                "mrp": _safe_float(row.get("Max Retail Price") or row.get("maxRetailPrice") or row.get("mrp")),
                "inventory": 0,
                "available_inventory": 0,
                "reserved_inventory": 0,
                "raw_data": row
            }
            
        # Global enabled check (if any of the duplicates is enabled, keep it enabled)
        enabled_raw = (row.get("Enabled") or row.get("enabled") or "").strip().lower()
        if enabled_raw in ("true", "1", "yes", "y"):
            aggregated_rows[sku]["disabled"] = False
        elif sku not in aggregated_rows or aggregated_rows[sku]["disabled"]:
            # Only set to disabled if it's currently disabled or newly created
            aggregated_rows[sku]["disabled"] = True
            
        inv_val = _safe_int(row.get("Inventory") or row.get("inventory"))
        aggregated_rows[sku]["inventory"] += inv_val
        aggregated_rows[sku]["available_inventory"] += inv_val  # Usually 1:1 in this export
        aggregated_rows[sku]["reserved_inventory"] += _safe_int(row.get("Open Sale") or row.get("openSale") or row.get("Inventory Blocked") or row.get("inventoryBlocked"))

    unique_skus = list(aggregated_rows.values())
    
    # Step 5: Upsert into PostgreSQL
    db = SessionLocal()
    inserted_count = 0
    now = datetime.utcnow()
    
    try:
        if unique_skus:
            insert_stmt = insert(FacilityInventorySnapshot).values([
                {
                    "sku": item["sku"],
                    "facility_code": item["facility_code"],
                    "category": item["category"],
                    "color": item["color"],
                    "size": item["size"],
                    "brand": item["brand"],
                    "inventory": item["inventory"],
                    "available_inventory": item["available_inventory"],
                    "reserved_inventory": item["reserved_inventory"],
                    "disabled": item["disabled"],
                    "archived": False,
                    "cost_price": item["cost_price"],
                    "mrp": item["mrp"],
                    "snapshot_date": now,
                    "raw_data": item["raw_data"],
                    "synced_at": now
                }
                for item in unique_skus
            ])
            
            # Upsert logic
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["sku", "facility_code"],
                set_={
                    "category": insert_stmt.excluded.category,
                    "color": insert_stmt.excluded.color,
                    "size": insert_stmt.excluded.size,
                    "brand": insert_stmt.excluded.brand,
                    "inventory": insert_stmt.excluded.inventory,
                    "available_inventory": insert_stmt.excluded.available_inventory,
                    "reserved_inventory": insert_stmt.excluded.reserved_inventory,
                    "disabled": insert_stmt.excluded.disabled,
                    "archived": insert_stmt.excluded.archived,
                    "cost_price": insert_stmt.excluded.cost_price,
                    "mrp": insert_stmt.excluded.mrp,
                    "snapshot_date": insert_stmt.excluded.snapshot_date,
                    "raw_data": insert_stmt.excluded.raw_data,
                    "synced_at": insert_stmt.excluded.synced_at,
                }
            )
            
            db.execute(upsert_stmt)
            db.commit()
            inserted_count = len(unique_skus)

        # Audit
        duration = time_module.time() - start_time
        ParityValidator.record_sync_audit(
            db=db,
            entity="inventory_snapshot",
            rows_fetched=len(rows),
            rows_inserted=inserted_count,
            duration=duration
        )

        return {
            "success": True,
            "fetched": len(rows),
            "inserted": inserted_count,
            "duplicates_removed": len(rows) - inserted_count,
            "duration": duration
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to upsert inventory snapshot: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()
