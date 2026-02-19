from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel
from app.db.session import get_db
from app.db.models import Discount
from app.services.cache_service import CacheService
from app.schemas.pagination import PaginatedResponse

router = APIRouter()


class DiscountBase(BaseModel):
    discount_name: str
    discount_type: str
    discount_value: Decimal
    applicable_to: str
    panel_id: int | None = None
    garment_id: int | None = None
    category: str | None = None
    valid_from: date
    valid_to: date | None = None
    is_active: bool = True


class DiscountCreate(DiscountBase):
    pass


class DiscountSchema(DiscountBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("/", response_model=DiscountSchema, status_code=status.HTTP_201_CREATED)
def create_discount(discount: DiscountCreate, db: Session = Depends(get_db)):
    """Create a new discount."""
    db_discount = Discount(**discount.model_dump())
    db.add(db_discount)
    db.commit()
    db.refresh(db_discount)
    
    # Invalidate cache
    CacheService.invalidate_discounts_cache()
    
    return db_discount


@router.get("/", response_model=PaginatedResponse[DiscountSchema])
def list_discounts(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    is_active: bool = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db)
):
    """List all discounts with pagination and Redis caching."""
    skip = (page - 1) * page_size
    
    # Check cache
    cache_key = f"discounts:list:{page}:{page_size}:{is_active}"
    cached = CacheService.get(cache_key)
    if cached:
        return PaginatedResponse[DiscountSchema](**cached)
    
    # Build query
    query = db.query(Discount)
    if is_active is not None:
        query = query.filter(Discount.is_active == is_active)
    
    total = query.count()
    discounts = query.offset(skip).limit(page_size).all()
    
    items = [DiscountSchema.from_orm(d) for d in discounts]
    result = {
        "items": [item.model_dump(mode='json') for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }
    
    # Cache result
    CacheService.set(cache_key, result, CacheService.TTL_MEDIUM)
    
    return PaginatedResponse[DiscountSchema](**result)


@router.get("/{discount_id}", response_model=DiscountSchema)
def get_discount(discount_id: int, db: Session = Depends(get_db)):
    """Get a specific discount with Redis caching."""
    # Check cache
    cache_key = f"discounts:{discount_id}"
    cached = CacheService.get(cache_key)
    if cached:
        return cached
    
    discount = db.query(Discount).filter(Discount.id == discount_id).first()
    if not discount:
        raise HTTPException(status_code=404, detail="Discount not found")
    
    result = DiscountSchema.from_orm(discount)
    
    # Cache result (serialize before caching)
    CacheService.set(cache_key, result.model_dump(mode='json'), CacheService.TTL_LONG)
    
    return result
