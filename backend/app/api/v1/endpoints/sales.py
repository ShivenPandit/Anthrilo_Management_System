from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel
from app.db.session import get_db
from app.db.models import Sale, Garment, Panel
from app.schemas.pagination import PaginatedResponse
from app.services.sales_service import invalidate_daily_sales_cache
from app.services.cache_service import CacheService
from app.services.websocket_manager import broadcast_sales_update

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
    sku: str | None = None
    sale_date: date | None = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        # Map transaction_date to sale_date
        data = {
            "id": obj.id,
            "transaction_date": obj.transaction_date,
            "sale_date": obj.transaction_date,  # Add sale_date alias
            "garment_id": obj.garment_id,
            "panel_id": obj.panel_id,
            "size": obj.size,
            "quantity": obj.quantity,
            "unit_price": obj.unit_price,
            "discount_percentage": obj.discount_percentage,
            "total_amount": obj.total_amount,
            "is_return": obj.is_return,
            "invoice_number": obj.invoice_number,
            "created_at": obj.created_at,
            "sku": obj.garment.style_sku if obj.garment else None  # Add SKU from garment
        }
        return cls(**data)


@router.post("/", response_model=SaleSchema, status_code=status.HTTP_201_CREATED)
async def create_sale(sale: SaleCreate, db: Session = Depends(get_db)):
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

    # Invalidate cache for the sale date
    invalidate_daily_sales_cache(sale.transaction_date)
    CacheService.invalidate_sales_cache()
    
    # Broadcast update
    await broadcast_sales_update({
        "action": "sale_created",
        "sale_id": db_sale.id,
        "garment_id": sale.garment_id,
        "panel_id": sale.panel_id,
        "total_amount": float(sale.total_amount),
        "timestamp": datetime.now().isoformat()
    })

    # Use from_orm to ensure sku and sale_date fields are properly mapped
    return SaleSchema.from_orm(db_sale)


@router.get("/", response_model=PaginatedResponse[SaleSchema])
def list_sales(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    start_date: date = Query(None, description="Filter from date"),
    end_date: date = Query(None, description="Filter to date"),
    panel_id: int = Query(None, description="Filter by panel"),
    db: Session = Depends(get_db)
):
    """List all sales with pagination and Redis caching."""
    skip = (page - 1) * page_size
    
    # Check cache
    cache_key = f"sales:list:{page}:{page_size}:{start_date}:{end_date}:{panel_id}"
    cached = CacheService.get(cache_key)
    if cached:
        return cached
    
    # Build query
    query = db.query(Sale).join(Garment)  # Join garment to get SKU
    if start_date:
        query = query.filter(Sale.transaction_date >= start_date)
    if end_date:
        query = query.filter(Sale.transaction_date <= end_date)
    if panel_id:
        query = query.filter(Sale.panel_id == panel_id)

    total = query.count()
    sales = query.order_by(Sale.transaction_date.desc()).offset(skip).limit(page_size).all()
    
    items = [SaleSchema.from_orm(sale) for sale in sales]
    result = {
        "items": [item.model_dump(mode='json') for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }
    
    # Cache result
    CacheService.set(cache_key, result, CacheService.TTL_SHORT)
    
    return PaginatedResponse[SaleSchema](**result)


@router.get("/daily/{transaction_date}", response_model=List[SaleSchema])
def get_daily_sales(transaction_date: date, db: Session = Depends(get_db)):
    """Get sales for a specific date with Redis caching."""
    # Check cache
    cache_key = f"sales:daily:{transaction_date}"
    cached = CacheService.get(cache_key)
    if cached:
        return cached
    
    sales = db.query(Sale).join(Garment).filter(
        Sale.transaction_date == transaction_date).all()
    
    result = [SaleSchema.from_orm(sale) for sale in sales]
    
    # Cache result (serialize before caching)
    CacheService.set(cache_key, [item.model_dump(mode='json') for item in result], CacheService.TTL_MEDIUM)
    
    return result
