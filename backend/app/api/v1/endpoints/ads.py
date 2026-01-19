from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel
from app.db.session import get_db
from app.db.models import PaidAd, Panel

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
    return db_ad


@router.get("/", response_model=List[PaidAdSchema])
def list_paid_ads(
    skip: int = 0,
    limit: int = 100,
    start_date: date = None,
    end_date: date = None,
    panel_id: int = None,
    db: Session = Depends(get_db)
):
    """List all paid ads with optional filtering."""
    query = db.query(PaidAd)
    if start_date:
        query = query.filter(PaidAd.ad_date >= start_date)
    if end_date:
        query = query.filter(PaidAd.ad_date <= end_date)
    if panel_id:
        query = query.filter(PaidAd.panel_id == panel_id)
    
    ads = query.order_by(PaidAd.ad_date.desc()).offset(skip).limit(limit).all()
    return ads


@router.get("/roi/{panel_id}")
def calculate_roi(
    panel_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db)
):
    """Calculate ROI for a panel's paid ads within a date range."""
    ads = db.query(PaidAd).filter(
        PaidAd.panel_id == panel_id,
        PaidAd.ad_date >= start_date,
        PaidAd.ad_date <= end_date
    ).all()
    
    total_spend = sum(float(ad.daily_spend) for ad in ads)
    total_revenue = sum(float(ad.revenue_generated or 0) for ad in ads)
    
    roi = ((total_revenue - total_spend) / total_spend * 100) if total_spend > 0 else 0
    
    return {
        "panel_id": panel_id,
        "start_date": start_date,
        "end_date": end_date,
        "total_spend": total_spend,
        "total_revenue": total_revenue,
        "roi_percentage": round(roi, 2)
    }
