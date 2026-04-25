from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import List, Optional
import io
import csv
import logging

from app.db.session import get_db
from app.db.models import ProductMaster
from app.schemas.product_master import (
    ProductMaster as ProductMasterSchema,
    ProductMasterCreate,
    ProductMasterUpdate,
    ProductImportSummary,
)
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

router = APIRouter()

CACHE_PREFIX = "product_master"


def _invalidate_cache():
    """Invalidate all product master caches."""
    try:
        CacheService.delete_pattern(f"{CACHE_PREFIX}:*")
    except Exception:
        pass


# ── LIST with search, sort, pagination ──────────────────────

@router.get("/", response_model=dict)
def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    search: Optional[str] = None,
    sort_by: Optional[str] = "id",
    sort_order: Optional[str] = "desc",
    collection: Optional[str] = None,
    season: Optional[str] = None,
    fabric_type: Optional[str] = None,
    type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List products with search, filter, sort and pagination."""
    cache_key = f"{CACHE_PREFIX}:list:{skip}:{limit}:{search}:{sort_by}:{sort_order}:{collection}:{season}:{fabric_type}:{type}"
    cached = CacheService.get(cache_key)
    if cached:
        return cached

    query = db.query(ProductMaster)

    # Search across sku and name
    if search:
        term = f"%{search}%"
        query = query.filter(
            or_(
                ProductMaster.sku.ilike(term),
                ProductMaster.name.ilike(term),
            )
        )

    # Filters
    if collection:
        query = query.filter(ProductMaster.collection == collection)
    if season:
        query = query.filter(ProductMaster.season == season)
    if fabric_type:
        query = query.filter(ProductMaster.fabric_type == fabric_type)
    if type:
        query = query.filter(ProductMaster.type == type)

    total = query.count()

    # Sort
    allowed_sort = {
        "id", "sku", "name", "size", "collection", "type",
        "season", "fabric_type", "net_weight", "production_time", "created_at",
    }
    if sort_by not in allowed_sort:
        sort_by = "id"
    sort_col = getattr(ProductMaster, sort_by)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    products = query.offset(skip).limit(limit).all()

    result = {
        "items": [ProductMasterSchema.from_orm(p).model_dump(mode="json") for p in products],
        "total": total,
        "page": (skip // limit) + 1,
        "page_size": limit,
        "total_pages": max(1, -(-total // limit)),
    }
    CacheService.set(cache_key, result, CacheService.TTL_MEDIUM)
    return result


# ── GET single ──────────────────────────────────────────────

@router.get("/{product_id}", response_model=ProductMasterSchema)
def get_product(product_id: int, db: Session = Depends(get_db)):
    """Get a single product by ID."""
    product = db.query(ProductMaster).filter(ProductMaster.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# ── CREATE ──────────────────────────────────────────────────

@router.post("/", response_model=ProductMasterSchema, status_code=status.HTTP_201_CREATED)
def create_product(product: ProductMasterCreate, db: Session = Depends(get_db)):
    """Create a new product."""
    sku_clean = (product.sku or "").strip()
    existing = (
        db.query(ProductMaster)
        .filter(func.lower(ProductMaster.sku) == sku_clean.lower())
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists")

    payload = product.model_dump()
    payload["sku"] = sku_clean
    db_product = ProductMaster(**payload)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    _invalidate_cache()
    return db_product


# ── UPDATE ──────────────────────────────────────────────────

@router.put("/{product_id}", response_model=ProductMasterSchema)
def update_product(product_id: int, product_update: ProductMasterUpdate, db: Session = Depends(get_db)):
    """Update an existing product."""
    db_product = db.query(ProductMaster).filter(ProductMaster.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")

    update_data = product_update.model_dump(exclude_unset=True)

    # Check SKU uniqueness if being updated
    if "sku" in update_data and update_data["sku"] != db_product.sku:
        next_sku = (update_data["sku"] or "").strip()
        conflict = (
            db.query(ProductMaster)
            .filter(func.lower(ProductMaster.sku) == next_sku.lower())
            .first()
        )
        if conflict:
            raise HTTPException(status_code=400, detail="SKU already exists")
        update_data["sku"] = next_sku

    for field, value in update_data.items():
        setattr(db_product, field, value)

    db.commit()
    db.refresh(db_product)

    _invalidate_cache()
    return db_product


# ── DELETE ──────────────────────────────────────────────────

@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """Delete a product."""
    db_product = db.query(ProductMaster).filter(ProductMaster.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")

    db.delete(db_product)
    db.commit()

    _invalidate_cache()
    return None


# ── BULK IMPORT (CSV / XLSX) ────────────────────────────────

REQUIRED_COLUMNS = {"sku", "name"}
ALL_COLUMNS = {
    "sku", "name", "size", "collection", "type", "season",
    "fabric_type", "print", "net_weight", "production_time",
}

# Map header variations to canonical field names
HEADER_MAP = {
    "sku": "sku",
    "name": "name",
    "size": "size",
    "collection": "collection",
    "type": "type",
    "season": "season",
    "fabric_type": "fabric_type",
    "fabric type": "fabric_type",
    "fabrictype": "fabric_type",
    "print": "print",
    "net_weight": "net_weight",
    "net weight": "net_weight",
    "netweight": "net_weight",
    "production_time": "production_time",
    "production time": "production_time",
    "productiontime": "production_time",
}


def _normalise_header(h: str) -> str:
    return HEADER_MAP.get(h.strip().lower().replace("_", " ").replace("-", " "), "").replace(" ", "_") or HEADER_MAP.get(h.strip().lower(), "")


def _parse_csv(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig")  # handles BOM
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        mapped = {}
        for hdr, val in row.items():
            canon = _normalise_header(hdr)
            if canon:
                mapped[canon] = val.strip() if val else None
        rows.append(mapped)
    return rows


def _parse_xlsx(raw: bytes) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        raise HTTPException(status_code=400, detail="openpyxl is not installed; XLSX import unavailable. Use CSV instead.")

    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers_raw = next(rows_iter, None)
    if not headers_raw:
        return []

    headers = [_normalise_header(str(h) if h else "") for h in headers_raw]
    rows = []
    for row_vals in rows_iter:
        mapped = {}
        for idx, val in enumerate(row_vals):
            if idx < len(headers) and headers[idx]:
                mapped[headers[idx]] = str(val).strip() if val is not None else None
        rows.append(mapped)
    return rows


@router.post("/import", response_model=ProductImportSummary)
def import_products(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Bulk import products from CSV or XLSX file."""
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

    # Validate column headers
    first_row_keys = set(rows[0].keys())
    missing_required = REQUIRED_COLUMNS - first_row_keys
    if missing_required:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing_required)}",
        )

    # Pre-fetch existing SKUs for dedup
    existing_skus = {((s[0] or "").strip().lower()) for s in db.query(ProductMaster.sku).all()}
    seen_skus_in_file: set[str] = set()

    inserted = 0
    skipped = 0
    errors = []

    for idx, row in enumerate(rows, start=2):  # start=2 because row 1 is header
        sku = (row.get("sku") or "").strip()
        sku_key = sku.lower()
        name = (row.get("name") or "").strip()

        if not sku:
            errors.append({"row": idx, "error": "SKU is required"})
            continue
        if not name:
            errors.append({"row": idx, "error": "Name is required"})
            continue

        if sku_key in seen_skus_in_file:
            skipped += 1
            continue

        if sku_key in existing_skus:
            skipped += 1
            continue

        # Validate numeric fields
        net_weight = None
        raw_weight = row.get("net_weight")
        if raw_weight:
            try:
                net_weight = float(raw_weight)
            except (ValueError, TypeError):
                errors.append({"row": idx, "error": f"Invalid net_weight: {raw_weight}"})
                continue

        production_time = None
        raw_pt = row.get("production_time")
        if raw_pt:
            try:
                production_time = int(float(raw_pt))
            except (ValueError, TypeError):
                errors.append({"row": idx, "error": f"Invalid production_time: {raw_pt}"})
                continue

        db_product = ProductMaster(
            sku=sku,
            name=name,
            size=row.get("size"),
            collection=row.get("collection"),
            type=row.get("type"),
            season=row.get("season"),
            fabric_type=row.get("fabric_type"),
            print=row.get("print"),
            net_weight=net_weight,
            production_time=production_time,
        )
        db.add(db_product)
        seen_skus_in_file.add(sku_key)
        existing_skus.add(sku_key)
        inserted += 1

    db.commit()
    _invalidate_cache()

    logger.info(f"Product import: inserted={inserted}, skipped={skipped}, errors={len(errors)}")

    return ProductImportSummary(inserted=inserted, skipped=skipped, errors=errors)


# ── FILTER OPTIONS (for dropdowns) ─────────────────────────

@router.get("/meta/filter-options", response_model=dict)
def get_filter_options(db: Session = Depends(get_db)):
    """Return distinct values for collection, season, fabric_type, type."""
    cache_key = f"{CACHE_PREFIX}:filter_options"
    cached = CacheService.get(cache_key)
    if cached:
        return cached

    def distinct_vals(col):
        return sorted([r[0] for r in db.query(col).distinct().all() if r[0]])

    result = {
        "collections": distinct_vals(ProductMaster.collection),
        "seasons": distinct_vals(ProductMaster.season),
        "fabric_types": distinct_vals(ProductMaster.fabric_type),
        "types": distinct_vals(ProductMaster.type),
    }
    CacheService.set(cache_key, result, CacheService.TTL_MEDIUM)
    return result
