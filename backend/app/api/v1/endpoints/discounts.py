from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel
from app.db.session import get_db
from app.db.models import Discount

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
    return db_discount


@router.get("/", response_model=List[DiscountSchema])
def list_discounts(
    skip: int = 0,
    limit: int = 100,
    is_active: bool = None,
    db: Session = Depends(get_db)
):
    """List all discounts with optional filtering."""
    query = db.query(Discount)
    if is_active is not None:
        query = query.filter(Discount.is_active == is_active)
    
    discounts = query.offset(skip).limit(limit).all()
    return discounts


@router.get("/{discount_id}", response_model=DiscountSchema)
def get_discount(discount_id: int, db: Session = Depends(get_db)):
    """Get a specific discount."""
    discount = db.query(Discount).filter(Discount.id == discount_id).first()
    if not discount:
        raise HTTPException(status_code=404, detail="Discount not found")
    return discount
