from __future__ import annotations

import csv
import io
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.export_models import ShopifyMasterData
from app.db.session import get_db
from app.schemas.shopify_master_data import (
    ShopifyMasterDataImportSummary,
    ShopifyMasterDataItem,
    ShopifyMasterDataListResponse,
)
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)
router = APIRouter()


HEADER_MAP = {
    "variant sku": "variant_sku",
    "variant_sku": "variant_sku",
    "sku": "variant_sku",
    "title": "title",
    "type": "type",
    "tags": "tags",
    "option1 value": "option1_value",
    "option1_value": "option1_value",
    "size": "option1_value",
    "cost per item": "cost_per_item",
    "cost_per_item": "cost_per_item",
    "cost": "cost_per_item",
}


REQUIRED_COLUMNS = {"variant_sku"}


def _normalize_header(h: str) -> str:
    raw = (h or "").strip().lower().replace("_", " ")
    return HEADER_MAP.get(raw, "")


def _parse_csv(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict] = []
    for row in reader:
        mapped: dict = {}
        for hdr, val in row.items():
            canon = _normalize_header(hdr)
            if canon:
                mapped[canon] = val.strip() if isinstance(val, str) else val
        rows.append(mapped)
    return rows


def _parse_xlsx(raw: bytes) -> list[dict]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=400,
            detail="openpyxl is not installed; XLSX upload unavailable. Use CSV instead.",
        ) from exc

    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)

    headers_raw = next(rows_iter, None)
    if not headers_raw:
        return []

    headers = [_normalize_header(str(h) if h is not None else "") for h in headers_raw]
    rows: list[dict] = []
    for vals in rows_iter:
        mapped: dict = {}
        for idx, val in enumerate(vals):
            if idx < len(headers) and headers[idx]:
                mapped[headers[idx]] = str(val).strip() if val is not None else None
        rows.append(mapped)
    return rows


def _to_decimal(value: Optional[str]) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid cost_per_item: {value}")


@router.get("/", response_model=ShopifyMasterDataListResponse)
def list_shopify_master_data(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(ShopifyMasterData)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ShopifyMasterData.variant_sku.ilike(term),
                ShopifyMasterData.title.ilike(term),
                ShopifyMasterData.type.ilike(term),
                ShopifyMasterData.tags.ilike(term),
                ShopifyMasterData.option1_value.ilike(term),
            )
        )

    total = query.count()
    rows = (
        query.order_by(ShopifyMasterData.updated_at.desc(), ShopifyMasterData.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return ShopifyMasterDataListResponse(
        items=[ShopifyMasterDataItem.model_validate(r) for r in rows],
        total=total,
        page=(skip // limit) + 1,
        page_size=limit,
        total_pages=max(1, -(-total // limit)),
    )


@router.post("/import", response_model=ShopifyMasterDataImportSummary)
def import_shopify_master_data(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = (file.filename or "").lower()
    raw = file.file.read()

    if filename.endswith(".csv"):
        rows = _parse_csv(raw)
    elif filename.endswith(".xlsx"):
        rows = _parse_xlsx(raw)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Use .csv or .xlsx")

    if not rows:
        raise HTTPException(status_code=400, detail="File is empty or has no data rows")

    missing = REQUIRED_COLUMNS - set(rows[0].keys())
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing required columns: {', '.join(sorted(missing))}")

    normalized_by_sku: dict[str, dict] = {}
    duplicate_rows_in_file = 0
    for idx, row in enumerate(rows, start=2):
        sku = (row.get("variant_sku") or "").strip()
        if not sku:
            continue
        try:
            normalized = {
                "row": idx,
                "variant_sku": sku,
                "title": (row.get("title") or "").strip() or None,
                "type": (row.get("type") or "").strip() or None,
                "tags": (row.get("tags") or "").strip() or None,
                "option1_value": (row.get("option1_value") or "").strip() or None,
                "cost_per_item": _to_decimal(row.get("cost_per_item")),
            }
            if sku in normalized_by_sku:
                duplicate_rows_in_file += 1
            # Keep the latest occurrence so correction rows in the same file can override earlier rows.
            normalized_by_sku[sku] = normalized
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Row {idx}: {exc}") from exc

    normalized_rows = list(normalized_by_sku.values())

    if not normalized_rows:
        raise HTTPException(status_code=400, detail="No valid data rows found")

    skus = [r["variant_sku"] for r in normalized_rows]
    existing_rows = (
        db.query(ShopifyMasterData)
        .filter(ShopifyMasterData.variant_sku.in_(skus))
        .all()
    )
    existing_map = {r.variant_sku: r for r in existing_rows}

    inserted = 0
    updated = 0
    skipped = duplicate_rows_in_file
    errors: list[dict] = []

    for row in normalized_rows:
        sku = row["variant_sku"]
        existing = existing_map.get(sku)
        if existing is None:
            db.add(
                ShopifyMasterData(
                    variant_sku=sku,
                    title=row["title"],
                    type=row["type"],
                    tags=row["tags"],
                    option1_value=row["option1_value"],
                    cost_per_item=row["cost_per_item"],
                )
            )
            inserted += 1
            continue

        changed = False
        for field in ("title", "type", "tags", "option1_value", "cost_per_item"):
            new_val = row[field]
            if getattr(existing, field) != new_val:
                setattr(existing, field, new_val)
                changed = True

        if changed:
            updated += 1
        else:
            skipped += 1

    try:
        db.commit()
        # Uploaded master rows should be reflected in sales-activity/report responses immediately.
        CacheService.invalidate_all_uc_cache()
    except Exception as exc:
        db.rollback()
        logger.exception("Shopify master import failed")
        errors.append({"error": str(exc)})

    return ShopifyMasterDataImportSummary(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )
