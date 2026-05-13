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

CACHE_PREFIX = "shopify_master_data"


def _invalidate_cache():
    CacheService.delete_pattern(f"{CACHE_PREFIX}*")


@router.get("/meta/filter-options", response_model=dict)
def get_filter_options(db: Session = Depends(get_db)):
    """Return distinct values for type."""
    cache_key = f"{CACHE_PREFIX}:filter_options"
    cached = CacheService.get(cache_key)
    if cached:
        return cached

    def distinct_vals(col):
        return sorted([r[0] for r in db.query(col).distinct().all() if r[0]])

    result = {
        "types": distinct_vals(ShopifyMasterData.type),
    }
    CacheService.set(cache_key, result, CacheService.TTL_MEDIUM)
    return result


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
    "size": "size", 
    "collection": "collection",
    "subtype": "subtype",
    "season": "season",
    "fabric type": "fabric_type",
    "fabric_type": "fabric_type",
    "print": "print_name",
    "net weight": "net_weight",
    "neight": "net_weight",
    "buffer": "buffer",
    "simple/bundle": "simple_bundle",
    "mrp": "mrp",
    "lifecycle": "lifecycle",
    "summer factor": "summer_factor",
    "winter factor": "winter_factor",
    "style factor": "style_factor",
    "lead_time": "lead_time",
    "lead time": "lead_time",
    "amazon asin": "lead_time",
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
    6: "size",
    7: "collection",
    8: "subtype",
    9: "season",
    10: "fabric_type",
    11: "print_name",
    12: "net_weight",
    13: "buffer",
    14: "simple_bundle",
    15: "mrp",
    16: "lifecycle",
    17: "summer_factor",
    18: "winter_factor",
    19: "style_factor",
    20: "lead_time",
}


REQUIRED_COLUMNS = {
    "variant_sku",
    "style_code",
    "title",
    "type",
    "net_weight",
}


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


def _to_float(value: Optional[str], *, field_name: str) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {field_name}: {value}")


def _to_int(value: Optional[str], *, field_name: str) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {field_name}: {value}")


def _safe_float_from_db(value: Optional[str]) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _safe_int_from_db(value: Optional[str]) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


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
                ShopifyMasterData.collection.ilike(term),
                ShopifyMasterData.subtype.ilike(term),
                ShopifyMasterData.season.ilike(term),
                ShopifyMasterData.fabric_type.ilike(term),
                ShopifyMasterData.print_name.ilike(term),
                ShopifyMasterData.net_weight.ilike(term),
                ShopifyMasterData.simple_bundle.ilike(term),
                ShopifyMasterData.gross_weights_1.ilike(term),
                ShopifyMasterData.garment_1.ilike(term),
                ShopifyMasterData.gross_weights_2.ilike(term),
                ShopifyMasterData.garment_2.ilike(term),
                ShopifyMasterData.amazon_asin.ilike(term),
            )
        )

    total = query.count()
    rows = (
        query.order_by(ShopifyMasterData.updated_at.desc(), ShopifyMasterData.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [
        ShopifyMasterDataItem(
            id=r.id,
            variant_sku=r.variant_sku,
            style_code=r.style_code or "",
            title=r.title or "",
            type=r.type or "",
            gender=r.gender,
            tags=r.tags,
            size=r.size,
            collection=r.collection,
            subtype=r.subtype,
            season=r.season,
            fabric_type=r.fabric_type,
            print_name=r.print_name,
            net_weight=r.net_weight or "",
            buffer=r.buffer,
            production_time=r.production_time,
            simple_bundle=r.simple_bundle,
            mrp=r.mrp,
            lifecycle=r.gross_weights_1,
            summer_factor=_safe_float_from_db(r.garment_1),
            winter_factor=_safe_float_from_db(r.gross_weights_2),
            style_factor=_safe_float_from_db(r.garment_2),
            lead_time=_safe_int_from_db(r.amazon_asin),
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]

    return ShopifyMasterDataListResponse(
        items=items,
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

        missing_required = [
            col
            for col in REQUIRED_COLUMNS
            if not str(row.get(col) or "").strip()
        ]
        if missing_required:
            raise HTTPException(
                status_code=400,
                detail=f"Row {idx}: Missing mandatory values: {', '.join(sorted(missing_required))}",
            )

        sku_key = sku.lower()
        try:
            mrp = _to_decimal(row.get("mrp"), field_name="mrp")
            summer_factor = _to_float(row.get("summer_factor"), field_name="summer_factor")
            winter_factor = _to_float(row.get("winter_factor"), field_name="winter_factor")
            style_factor = _to_float(row.get("style_factor"), field_name="style_factor")
            lead_time = _to_int(row.get("lead_time"), field_name="lead_time")
            normalized = {
                "row": idx,
                "variant_sku": sku,
                "style_code": row.get("style_code"),
                "title": row.get("title"),
                "type": row.get("type"),
                "gender": row.get("gender"),
                "tags": row.get("tags"),
                "size": row.get("size"),
                "collection": row.get("collection"),
                "subtype": row.get("subtype"),
                "season": row.get("season"),
                "fabric_type": row.get("fabric_type"),
                "print_name": row.get("print_name"),
                "net_weight": row.get("net_weight"),
                "buffer": row.get("buffer"),
                "production_time": row.get("production_time"),
                "simple_bundle": row.get("simple_bundle"),
                "mrp": mrp,
                "gross_weights_1": row.get("lifecycle"),
                "garment_1": str(summer_factor) if summer_factor is not None else None,
                "gross_weights_2": str(winter_factor) if winter_factor is not None else None,
                "garment_2": str(style_factor) if style_factor is not None else None,
                "amazon_asin": str(lead_time) if lead_time is not None else None,
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

    existing_rows = db.query(ShopifyMasterData).all()
    existing_by_sku = {
        (record.variant_sku or "").strip().lower(): record
        for record in existing_rows
        if (record.variant_sku or "").strip()
    }

    mutable_fields = [
        "variant_sku",
        "style_code",
        "title",
        "type",
        "gender",
        "tags",
        "size",
        "collection",
        "subtype",
        "season",
        "fabric_type",
        "print_name",
        "net_weight",
        "buffer",
        "production_time",
        "simple_bundle",
        "mrp",
        "gross_weights_1",
        "garment_1",
        "gross_weights_2",
        "garment_2",
        "amazon_asin",
        "cost_per_item",
    ]

    for row in normalized_rows:
        sku_key = row["variant_sku"].strip().lower()
        existing = existing_by_sku.get(sku_key)
        if existing is None:
            db.add(
                ShopifyMasterData(
                    variant_sku=row["variant_sku"],
                    style_code=row["style_code"],
                    title=row["title"],
                    type=row["type"],
                    gender=row["gender"],
                    tags=row["tags"],
                    size=row["size"],
                    collection=row["collection"],
                    subtype=row["subtype"],
                    season=row["season"],
                    fabric_type=row["fabric_type"],
                    print_name=row["print_name"],
                    net_weight=row["net_weight"],
                    buffer=row["buffer"],
                    production_time=row["production_time"],
                    simple_bundle=row["simple_bundle"],
                    mrp=row["mrp"],
                    gross_weights_1=row["gross_weights_1"],
                    garment_1=row["garment_1"],
                    gross_weights_2=row["gross_weights_2"],
                    garment_2=row["garment_2"],
                    amazon_asin=row["amazon_asin"],
                    cost_per_item=row["cost_per_item"],
                )
            )
            inserted += 1
            continue

        changed = False
        for field in mutable_fields:
            new_value = row[field]
            old_value = getattr(existing, field)
            if old_value != new_value:
                setattr(existing, field, new_value)
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
        inserted = 0
        updated = 0
        errors.append({"error": str(exc)})

    return ShopifyMasterDataImportSummary(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )
