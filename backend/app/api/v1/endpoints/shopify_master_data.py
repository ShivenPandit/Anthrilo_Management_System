from __future__ import annotations

import csv
import io
import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import text
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
    "style code": "style_code",
    "style_code": "style_code",
    "name": "title",
    "title": "title",
    "type": "type",
    "gender": "gender",
    "tag": "tags",
    "tags": "tags",
    "size": "option1_value",
    "option1 value": "option1_value",
    "option1_value": "option1_value",
    "collection": "collection",
    "subtype": "subtype",
    "season": "season",
    "fabric type": "fabric_type",
    "fabric_type": "fabric_type",
    "print": "print_name",
    "net weight": "net_weight",
    "production time": "production_time",
    "simple/bundle": "simple_bundle",
    "mrp": "mrp",
    "amazon asin": "amazon_asin",
    "amazo flex sku": "amazon_flex_sku",
    "amazon flex sku": "amazon_flex_sku",
    "amazon fba sku": "amazon_fba_sku",
    "amazon mfn sku": "amazon_mfn_sku",
    "myntra style id": "myntra_style_id",
    "myntra sku": "myntra_sku",
    "fc": "fc",
    "cost per item": "cost_per_item",
    "cost_per_item": "cost_per_item",
    "cost": "cost_per_item",
}


POSITIONAL_HEADERS = {
    0: "variant_sku",
    1: "style_code",
    2: "title",
    3: "type",
    4: "gender",
    5: "tags",
    6: "option1_value",
    7: "collection",
    8: "subtype",
    9: "season",
    10: "fabric_type",
    11: "print_name",
    12: "net_weight",
    13: "production_time",
    14: "simple_bundle",
    15: "mrp",
    16: "gross_weights_1",
    17: "garment_1",
    18: "gross_weights_2",
    19: "garment_2",
    20: "amazon_asin",
    21: "amazon_flex_sku",
    22: "amazon_fba_sku",
    23: "amazon_mfn_sku",
    24: "myntra_style_id",
    25: "myntra_sku",
    26: "fc",
}


REQUIRED_COLUMNS = {"variant_sku"}


def _clean_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    upper = text.upper()
    if upper in {"#N/A", "N/A", "NA", "NULL", "NONE", "-"}:
        return None
    return text


def _normalize_header(h: str) -> str:
    raw = " ".join((h or "").strip().lower().replace("_", " ").split())
    return HEADER_MAP.get(raw, "")


def _canonical_header(index: int, header: str) -> str:
    # Prefer positional mapping so duplicate headers like "gross weights" can be represented distinctly.
    if index in POSITIONAL_HEADERS:
        return POSITIONAL_HEADERS[index]
    return _normalize_header(header)


def _parse_csv(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    headers_raw = next(reader, None)
    if not headers_raw:
        return []

    rows: list[dict] = []
    canonical_headers = [_canonical_header(idx, str(hdr)) for idx, hdr in enumerate(headers_raw)]
    for row in reader:
        mapped: dict = {}
        for idx, val in enumerate(row):
            if idx >= len(canonical_headers):
                continue
            canon = canonical_headers[idx]
            if canon:
                mapped[canon] = _clean_text(val)
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

    headers = [_canonical_header(idx, str(h) if h is not None else "") for idx, h in enumerate(headers_raw)]
    rows: list[dict] = []
    for vals in rows_iter:
        mapped: dict = {}
        for idx, val in enumerate(vals):
            if idx < len(headers) and headers[idx]:
                mapped[headers[idx]] = _clean_text(str(val) if val is not None else None)
        rows.append(mapped)
    return rows


def _to_decimal(value: Optional[str], *, field_name: str) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid {field_name}: {value}")


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
                ShopifyMasterData.style_code.ilike(term),
                ShopifyMasterData.title.ilike(term),
                ShopifyMasterData.type.ilike(term),
                ShopifyMasterData.gender.ilike(term),
                ShopifyMasterData.tags.ilike(term),
                ShopifyMasterData.option1_value.ilike(term),
                ShopifyMasterData.collection.ilike(term),
                ShopifyMasterData.subtype.ilike(term),
                ShopifyMasterData.season.ilike(term),
                ShopifyMasterData.fabric_type.ilike(term),
                ShopifyMasterData.print_name.ilike(term),
                ShopifyMasterData.simple_bundle.ilike(term),
                ShopifyMasterData.amazon_asin.ilike(term),
                ShopifyMasterData.amazon_flex_sku.ilike(term),
                ShopifyMasterData.amazon_fba_sku.ilike(term),
                ShopifyMasterData.amazon_mfn_sku.ilike(term),
                ShopifyMasterData.myntra_style_id.ilike(term),
                ShopifyMasterData.myntra_sku.ilike(term),
                ShopifyMasterData.fc.ilike(term),
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
    blank_sku_rows = 0
    for idx, row in enumerate(rows, start=2):
        sku = (row.get("variant_sku") or "").strip()
        if not sku:
            blank_sku_rows += 1
            continue
        sku_key = sku.lower()
        try:
            mrp = _to_decimal(row.get("mrp"), field_name="mrp")
            normalized = {
                "row": idx,
                "variant_sku": sku,
                "style_code": row.get("style_code"),
                "title": row.get("title"),
                "type": row.get("type"),
                "gender": row.get("gender"),
                "tags": row.get("tags"),
                "option1_value": row.get("option1_value"),
                "collection": row.get("collection"),
                "subtype": row.get("subtype"),
                "season": row.get("season"),
                "fabric_type": row.get("fabric_type"),
                "print_name": row.get("print_name"),
                "net_weight": row.get("net_weight"),
                "production_time": row.get("production_time"),
                "simple_bundle": row.get("simple_bundle"),
                "mrp": mrp,
                "gross_weights_1": row.get("gross_weights_1"),
                "garment_1": row.get("garment_1"),
                "gross_weights_2": row.get("gross_weights_2"),
                "garment_2": row.get("garment_2"),
                "amazon_asin": row.get("amazon_asin"),
                "amazon_flex_sku": row.get("amazon_flex_sku"),
                "amazon_fba_sku": row.get("amazon_fba_sku"),
                "amazon_mfn_sku": row.get("amazon_mfn_sku"),
                "myntra_style_id": row.get("myntra_style_id"),
                "myntra_sku": row.get("myntra_sku"),
                "fc": row.get("fc"),
                # Backward compatibility for report enrichment code that still consumes legacy keys.
                "cost_per_item": mrp,
            }
            if sku_key in normalized_by_sku:
                duplicate_rows_in_file += 1
            # Keep the latest occurrence so correction rows in the same file can override earlier rows.
            normalized_by_sku[sku_key] = normalized
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Row {idx}: {exc}") from exc

    normalized_rows = list(normalized_by_sku.values())

    if not normalized_rows:
        raise HTTPException(status_code=400, detail="No valid data rows found")

    inserted = 0
    updated = 0
    skipped = duplicate_rows_in_file + blank_sku_rows
    errors: list[dict] = []

    # Replace mode: clear previous master dataset and load only current upload.
    db.execute(text("TRUNCATE TABLE shopify_master_data RESTART IDENTITY"))

    for row in normalized_rows:
        db.add(
            ShopifyMasterData(
                variant_sku=row["variant_sku"],
                style_code=row["style_code"],
                title=row["title"],
                type=row["type"],
                gender=row["gender"],
                tags=row["tags"],
                option1_value=row["option1_value"],
                collection=row["collection"],
                subtype=row["subtype"],
                season=row["season"],
                fabric_type=row["fabric_type"],
                print_name=row["print_name"],
                net_weight=row["net_weight"],
                production_time=row["production_time"],
                simple_bundle=row["simple_bundle"],
                mrp=row["mrp"],
                gross_weights_1=row["gross_weights_1"],
                garment_1=row["garment_1"],
                gross_weights_2=row["gross_weights_2"],
                garment_2=row["garment_2"],
                amazon_asin=row["amazon_asin"],
                amazon_flex_sku=row["amazon_flex_sku"],
                amazon_fba_sku=row["amazon_fba_sku"],
                amazon_mfn_sku=row["amazon_mfn_sku"],
                myntra_style_id=row["myntra_style_id"],
                myntra_sku=row["myntra_sku"],
                fc=row["fc"],
                cost_per_item=row["cost_per_item"],
            )
        )
        inserted += 1

    try:
        db.commit()
        # Uploaded master rows should be reflected in sales-activity/report responses immediately.
        CacheService.invalidate_all_uc_cache()
    except Exception as exc:
        db.rollback()
        logger.exception("Shopify master import failed")
        inserted = 0
        updated = 0
        errors.append({"error": str(exc)})

    return ShopifyMasterDataImportSummary(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )
