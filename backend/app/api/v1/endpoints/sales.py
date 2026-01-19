from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel
from app.db.session import get_db
from app.db.models import Sale, Garment, Panel

router = APIRouter()


class SaleBase(BaseModel):
    transaction_date: date
    garment_id: int
    panel_id: int
    size: str
    quantity: int
    unit_price: Decimal
    discount_percentage: Decimal = Decimal(0)
    total_amount: Decimal
    is_return: bool = False
    invoice_number: str | None = None


class SaleCreate(SaleBase):
    pass


class SaleSchema(SaleBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/", response_model=SaleSchema, status_code=status.HTTP_201_CREATED)
def create_sale(sale: SaleCreate, db: Session = Depends(get_db)):
    """Create a new sale record."""
    # Verify garment and panel exist
    garment = db.query(Garment).filter(Garment.id == sale.garment_id).first()
    if not garment:
        raise HTTPException(status_code=404, detail="Garment not found")
    
    panel = db.query(Panel).filter(Panel.id == sale.panel_id).first()
    if not panel:
        raise HTTPException(status_code=404, detail="Panel not found")
    
    db_sale = Sale(**sale.model_dump())
    db.add(db_sale)
    db.commit()
    db.refresh(db_sale)
    return db_sale


@router.get("/", response_model=List[SaleSchema])
def list_sales(
    skip: int = 0,
    limit: int = 100,
    start_date: date = None,
    end_date: date = None,
    panel_id: int = None,
    db: Session = Depends(get_db)
):
    """List all sales with optional filtering."""
    query = db.query(Sale)
    if start_date:
        query = query.filter(Sale.transaction_date >= start_date)
    if end_date:
        query = query.filter(Sale.transaction_date <= end_date)
    if panel_id:
        query = query.filter(Sale.panel_id == panel_id)
    
    sales = query.order_by(Sale.transaction_date.desc()).offset(skip).limit(limit).all()
    return sales


@router.get("/daily/{transaction_date}", response_model=List[SaleSchema])
def get_daily_sales(transaction_date: date, db: Session = Depends(get_db)):
    """Get sales for a specific date."""
    sales = db.query(Sale).filter(Sale.transaction_date == transaction_date).all()
    return sales
