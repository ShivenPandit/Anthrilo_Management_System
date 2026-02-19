from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel
from app.db.session import get_db
from app.db.models import PaidAd, Panel
from app.services.cache_service import CacheService
from app.schemas.pagination import PaginatedResponse

router = APIRouter()


class PaidAdBase(BaseModel):
    ad_date: date
    panel_id: int
    platform: str
    campaign_name: str
    daily_spend: Decimal
    impressions: int | None = None
    clicks: int | None = None
    conversions: int | None = None
    revenue_generated: Decimal | None = None
    notes: str | None = None


class PaidAdCreate(PaidAdBase):
    pass


class PaidAdSchema(PaidAdBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/", response_model=PaidAdSchema, status_code=status.HTTP_201_CREATED)
def create_paid_ad(ad: PaidAdCreate, db: Session = Depends(get_db)):
    """Create a new paid ad record."""
    panel = db.query(Panel).filter(Panel.id == ad.panel_id).first()
    if not panel:
        raise HTTPException(status_code=404, detail="Panel not found")
    
    db_ad = PaidAd(**ad.model_dump())
    db.add(db_ad)
    db.commit()
    db.refresh(db_ad)
    
    # Invalidate cache
    CacheService.invalidate_ads_cache()
    
    return db_ad


@router.get("/", response_model=PaginatedResponse[PaidAdSchema])
def list_paid_ads(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    start_date: date = Query(None, description="Filter from date"),
    end_date: date = Query(None, description="Filter to date"),
    panel_id: int = Query(None, description="Filter by panel"),
    db: Session = Depends(get_db)
):
    """List all paid ads with pagination and Redis caching."""
    skip = (page - 1) * page_size
    
    # Check cache
    cache_key = f"ads:list:{page}:{page_size}:{start_date}:{end_date}:{panel_id}"
    cached = CacheService.get(cache_key)
    if cached:
        return PaginatedResponse[PaidAdSchema](**cached)
    
    # Build query
    query = db.query(PaidAd)
    if start_date:
        query = query.filter(PaidAd.ad_date >= start_date)
    if end_date:
        query = query.filter(PaidAd.ad_date <= end_date)
    if panel_id:
        query = query.filter(PaidAd.panel_id == panel_id)
    
    total = query.count()
    ads = query.order_by(PaidAd.ad_date.desc()).offset(skip).limit(page_size).all()
    
    items = [PaidAdSchema.from_orm(ad) for ad in ads]
    result = {
        "items": [item.model_dump(mode='json') for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }
    
    # Cache result
    CacheService.set(cache_key, result, CacheService.TTL_MEDIUM)
    
    return PaginatedResponse[PaidAdSchema](**result)


@router.get("/roi/{panel_id}")
def calculate_roi(
    panel_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db)
):
    """Calculate ROI for a panel's paid ads within a date range with Redis caching."""
    # Check cache
    cache_key = f"ads:roi:{panel_id}:{start_date}:{end_date}"
    cached = CacheService.get(cache_key)
    if cached:
        return cached
    
    ads = db.query(PaidAd).filter(
        PaidAd.panel_id == panel_id,
        PaidAd.ad_date >= start_date,
        PaidAd.ad_date <= end_date
    ).all()
    
    total_spend = sum(float(ad.daily_spend) for ad in ads)
    total_revenue = sum(float(ad.revenue_generated or 0) for ad in ads)
    
    roi = ((total_revenue - total_spend) / total_spend * 100) if total_spend > 0 else 0
    
    result = {
        "panel_id": panel_id,
        "start_date": start_date,
        "end_date": end_date,
        "total_spend": total_spend,
        "total_revenue": total_revenue,
        "roi_percentage": round(roi, 2)
    }
    
    # Cache for 1 hour
    CacheService.set(cache_key, result, CacheService.TTL_VERY_LONG)
    
    return result
