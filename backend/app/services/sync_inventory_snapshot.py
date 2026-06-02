import asyncio
import csv
import io
import logging
import time as time_module
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert

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
    "enabled", "updated", "costPrice", "MRP",
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
        # Fetch item_master attributes to resolve missing SKUs in Inventory Snapshot CSV
        name_to_sku_map: Dict[str, Optional[str]] = {}
        name_size_brand_map: Dict[str, Optional[str]] = {}
        name_size_color_brand_map: Dict[str, Optional[str]] = {}
        ean_to_sku_map: Dict[str, Optional[str]] = {}
        upc_to_sku_map: Dict[str, Optional[str]] = {}
        isbn_to_sku_map: Dict[str, Optional[str]] = {}

        def _record_unique(target: Dict[str, Optional[str]], key: str, sku: str) -> None:
            if not key or not sku:
                return
            if key not in target:
                target[key] = sku
            elif target[key] != sku:
                target[key] = ""

        def _norm_key(value: Any) -> str:
            return str(value or "").strip().lower()
        try:
            with SessionLocal() as db:
                res = db.execute(text("""
                    SELECT
                        er.payload->>'Name' AS name,
                        er.payload->>'Product Code' AS sku,
                        er.payload->>'Size' AS size,
                        er.payload->>'Color' AS color,
                        er.payload->>'Brand' AS brand,
                        er.payload->>'EAN' AS ean,
                        er.payload->>'UPC' AS upc,
                        er.payload->>'ISBN' AS isbn
                    FROM export_rows er
                    JOIN export_jobs ej ON er.export_job_id = ej.id
                    WHERE ej.export_type = 'item_master' AND ej.status = 'completed'
                    ORDER BY ej.id DESC
                """))
                for row in res.mappings():
                    sku = str(row.get("sku") or "").strip()
                    if not sku:
                        continue
                    name = _norm_key(row.get("name"))
                    size = _norm_key(row.get("size"))
                    color = _norm_key(row.get("color"))
                    brand = _norm_key(row.get("brand"))
                    ean = _norm_key(row.get("ean"))
                    upc = _norm_key(row.get("upc"))
                    isbn = _norm_key(row.get("isbn"))

                    _record_unique(name_to_sku_map, name, sku)
                    _record_unique(name_size_brand_map, f"{name}|{size}|{brand}", sku)
                    _record_unique(name_size_color_brand_map, f"{name}|{size}|{color}|{brand}", sku)
                    _record_unique(ean_to_sku_map, ean, sku)
                    _record_unique(upc_to_sku_map, upc, sku)
                    _record_unique(isbn_to_sku_map, isbn, sku)
            logger.info(
                "Loaded item_master mappings: "
                f"name={len(name_to_sku_map)}, "
                f"name_size_brand={len(name_size_brand_map)}, "
                f"name_size_color_brand={len(name_size_color_brand_map)}, "
                f"ean={len(ean_to_sku_map)}, upc={len(upc_to_sku_map)}, isbn={len(isbn_to_sku_map)}"
            )
        except Exception as e:
            logger.error(f"Failed to load name-to-sku map: {e}")

        for row in reader:
            has_sku = any(
                [
                    (row.get("Item SkuCode") or "").strip(),
                    (row.get("itemSkuCode") or "").strip(),
                    (row.get("Item Type SKU") or "").strip(),
                    (row.get("itemTypeSKU") or "").strip(),
                ]
            )

            if not has_sku:
                item_name = _norm_key(row.get("Item Type Name") or row.get("itemTypeName"))
                size = _norm_key(row.get("Size") or row.get("size"))
                color = _norm_key(row.get("Color") or row.get("color"))
                brand = _norm_key(row.get("Brand") or row.get("brand"))
                ean = _norm_key(row.get("EAN"))
                upc = _norm_key(row.get("UPC"))
                isbn = _norm_key(row.get("ISBN"))

                mapped_sku = None
                for key, source in (
                    (ean, ean_to_sku_map),
                    (upc, upc_to_sku_map),
                    (isbn, isbn_to_sku_map),
                    (f"{item_name}|{size}|{color}|{brand}", name_size_color_brand_map),
                    (f"{item_name}|{size}|{brand}", name_size_brand_map),
                    (item_name, name_to_sku_map),
                ):
                    if not key:
                        continue
                    candidate = source.get(key)
                    if candidate:
                        mapped_sku = candidate
                        break

                if mapped_sku:
                    row["Item SkuCode"] = mapped_sku

            # Normalize all SKU fields to uppercase to prevent case-variant
            # duplicates in the DB. The CSV exports "Item Type SKU" in uppercase
            # but "Item SkuCode" (from item_master mapping) in lowercase,
            # which creates duplicate rows since the DB constraint is case-sensitive.
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


def _aggregate_inventory_rows(rows: List[Dict[str, Any]], facility_code: str) -> Dict[str, Any]:
    aggregated_rows: Dict[str, Dict[str, Any]] = {}
    missing_sku_rows = 0
    duplicate_rows = 0

    for row in rows:
        sku_base = (
            row.get("Item SkuCode")
            or row.get("itemSkuCode")
            or row.get("Item Type SKU")
            or row.get("itemTypeSKU")
            or row.get("SKU Code")
            or row.get("skuCode")
            or ""
        ).strip().upper()  # Normalize to uppercase — prevents case-variant duplicates
        if not sku_base:
            missing_sku_rows += 1
            continue

        if sku_base in aggregated_rows:
            duplicate_rows += 1

        aggregated_rows.setdefault(
            sku_base,
            {
                "sku": sku_base,
                "facility_code": facility_code,
                "category": (row.get("Category Name") or row.get("categoryName") or row.get("Category") or "Uncategorized").strip() or "Uncategorized",
                "color": (row.get("Color") or row.get("color") or "").strip() or None,
                "size": (row.get("Size") or row.get("size") or "").strip() or None,
                "brand": (row.get("Brand") or row.get("brand") or "").strip() or None,
                "disabled": False,
                "cost_price": _safe_float(row.get("Cost Price") or row.get("costPrice")),
                "mrp": _safe_float(row.get("MRP") or row.get("Max Retail Price") or row.get("maxRetailPrice") or row.get("mrp")),
                "inventory": 0,
                "available_inventory": 0,
                "reserved_inventory": 0,
                "raw_data": row,
            },
        )

        enabled_raw = (row.get("Enabled") or row.get("enabled") or "").strip().lower()
        if enabled_raw in ("true", "1", "yes", "y"):
            aggregated_rows[sku_base]["disabled"] = False
        elif aggregated_rows[sku_base]["disabled"]:
            aggregated_rows[sku_base]["disabled"] = True

        inv_val = _safe_int(row.get("Inventory") or row.get("inventory"))
        aggregated_rows[sku_base]["inventory"] += inv_val
        aggregated_rows[sku_base]["available_inventory"] += inv_val
        aggregated_rows[sku_base]["reserved_inventory"] += _safe_int(
            row.get("Open Sale") or row.get("openSale") or row.get("Inventory Blocked") or row.get("inventoryBlocked")
        )

    unique_rows = list(aggregated_rows.values())
    return {
        "rows": unique_rows,
        "fetched_rows": len(rows),
        "unique_rows": len(unique_rows),
        "duplicate_rows": duplicate_rows,
        "missing_sku_rows": missing_sku_rows,
        "total_real_inventory": int(sum(item["inventory"] for item in unique_rows)),
        "total_virtual_inventory": int(sum(item["reserved_inventory"] for item in unique_rows)),
    }


async def fetch_inventory_export_preview(facility_code: str = "anthrilo") -> Dict[str, Any]:
    """Fetch and aggregate an inventory export without writing to the database."""
    start_time = time_module.time()

    job_code = await _create_inventory_export_job(facility_code)
    if not job_code:
        return {"success": False, "error": "Failed to create export job"}

    download_url = await _poll_inventory_export(job_code, facility_code)
    if not download_url:
        return {"success": False, "error": "Poll failed or timed out"}

    rows = await _download_parse_inventory_csv(download_url)
    aggregated = _aggregate_inventory_rows(rows, facility_code) if rows else {
        "rows": [],
        "fetched_rows": 0,
        "unique_rows": 0,
        "duplicate_rows": 0,
        "missing_sku_rows": 0,
        "total_real_inventory": 0,
        "total_virtual_inventory": 0,
    }
    duration = time_module.time() - start_time

    return {
        "success": True,
        "job_code": job_code,
        "download_url": download_url,
        "rows_fetched": int(aggregated["fetched_rows"]),
        "unique_rows": int(aggregated["unique_rows"]),
        "duplicate_rows": int(aggregated["duplicate_rows"]),
        "missing_sku_rows": int(aggregated["missing_sku_rows"]),
        "total_real_inventory": int(aggregated["total_real_inventory"]),
        "total_virtual_inventory": int(aggregated["total_virtual_inventory"]),
        "rows": aggregated["rows"],
        "duration": duration,
    }


async def fetch_and_sync_inventory(facility_code: str = "anthrilo") -> Dict[str, Any]:
    """
    Fetch exact Inventory Snapshot from Unicommerce, deduplicate SKUs,
    and upsert them into the facility_inventory_snapshot PostgreSQL table.
    """
    start_time = time_module.time()
    preview = await fetch_inventory_export_preview(facility_code)
    if not preview.get("success"):
        failure_duration = float(preview.get("duration") or (time_module.time() - start_time))
        db = SessionLocal()
        try:
            ParityValidator.record_sync_audit(
                db=db,
                entity="inventory_snapshot",
                rows_fetched=0,
                rows_inserted=0,
                duration=failure_duration,
                rows_updated=0,
                duplicates_detected=0,
                missing_rows=0,
                error_count=1,
            )
        except Exception:
            logger.warning("Failed to record inventory export failure audit", exc_info=True)
        finally:
            db.close()
        return {"success": False, "error": preview.get("error", "Failed to fetch inventory export")}

    unique_skus = list(preview.get("rows") or [])

    db = SessionLocal()
    inserted_count = 0
    updated_count = 0
    now = datetime.utcnow()
    
    try:
        if unique_skus:
            sku_values = [str(item.get("sku") or "").strip() for item in unique_skus if str(item.get("sku") or "").strip()]
            existing_count = 0
            if sku_values:
                existing_count = (
                    db.query(func.count(FacilityInventorySnapshot.id))
                    .filter(
                        FacilityInventorySnapshot.facility_code == facility_code,
                        FacilityInventorySnapshot.sku.in_(sku_values),
                    )
                    .scalar()
                    or 0
                )

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
            updated_count = int(existing_count)
            inserted_count = max(0, len(unique_skus) - updated_count)

        # Audit
        duration = float(preview.get("duration") or (time_module.time() - start_time))
        ParityValidator.record_sync_audit(
            db=db,
            entity="inventory_snapshot",
            rows_fetched=int(preview.get("rows_fetched", 0) or 0),
            rows_inserted=inserted_count,
            rows_updated=updated_count,
            duplicates_detected=int(preview.get("duplicate_rows", 0) or 0),
            missing_rows=int(preview.get("missing_sku_rows", 0) or 0),
            duration=duration
        )

        return {
            "success": True,
            "fetched": int(preview.get("rows_fetched", 0) or 0),
            "inserted": inserted_count,
            "updated": updated_count,
            "duplicates_removed": int(preview.get("duplicate_rows", 0) or 0),
            "missing_rows": int(preview.get("missing_sku_rows", 0) or 0),
            "duration": duration,
        }
    except Exception as e:
        db.rollback()
        duration = float(time_module.time() - start_time)
        try:
            ParityValidator.record_sync_audit(
                db=db,
                entity="inventory_snapshot",
                rows_fetched=int(preview.get("rows_fetched", 0) if isinstance(preview, dict) else 0),
                rows_inserted=0,
                rows_updated=0,
                duplicates_detected=int(preview.get("duplicate_rows", 0) if isinstance(preview, dict) else 0),
                missing_rows=int(preview.get("missing_sku_rows", 0) if isinstance(preview, dict) else 0),
                duration=duration,
                error_count=1,
            )
        except Exception:
            logger.warning("Failed to record inventory sync failure audit", exc_info=True)
        logger.error(f"Failed to upsert inventory snapshot: {e}")
        return {
            "success": False,
            "error": str(e),
            "duration": duration,
            "fetched": int(preview.get("rows_fetched", 0) if isinstance(preview, dict) else 0),
        }
    finally:
        db.close()
