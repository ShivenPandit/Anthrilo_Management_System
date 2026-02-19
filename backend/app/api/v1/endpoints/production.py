from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel
from app.db.session import get_db
from app.db.models import ProductionPlan, ProductionActivity, Garment
from app.services.cache_service import CacheService
from app.services.websocket_manager import broadcast_production_update
from app.schemas.pagination import PaginatedResponse

router = APIRouter()


class ProductionPlanBase(BaseModel):
    plan_name: str
    garment_id: int
    planned_quantity: int
    target_date: date
    status: str = "PLANNED"
    fabric_requirement: Decimal | None = None
    yarn_requirement: Decimal | None = None
    notes: str | None = None


class ProductionPlanCreate(ProductionPlanBase):
    pass


class ProductionPlanSchema(ProductionPlanBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("/plans", response_model=ProductionPlanSchema, status_code=status.HTTP_201_CREATED)
async def create_production_plan(plan: ProductionPlanCreate, db: Session = Depends(get_db)):
    """Create a new production plan."""
    garment = db.query(Garment).filter(Garment.id == plan.garment_id).first()
    if not garment:
        raise HTTPException(status_code=404, detail="Garment not found")
    
    db_plan = ProductionPlan(**plan.model_dump())
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    
    # Invalidate cache
    CacheService.invalidate_production_cache()
    
    # Broadcast update
    await broadcast_production_update({
        "action": "plan_created",
        "plan_id": db_plan.id,
        "plan_name": db_plan.plan_name,
        "garment_id": db_plan.garment_id,
        "status": db_plan.status,
        "timestamp": datetime.now().isoformat()
    })
    
    return db_plan


@router.get("/plans", response_model=PaginatedResponse[ProductionPlanSchema])
def list_production_plans(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    plan_status: str = Query(None, description="Filter by status"),
    db: Session = Depends(get_db)
):
    """List all production plans with pagination and Redis caching."""
    skip = (page - 1) * page_size
    
    # Check cache
    cache_key = f"production:plans:list:{page}:{page_size}:{plan_status}"
    cached = CacheService.get(cache_key)
    if cached:
        return PaginatedResponse[ProductionPlanSchema](**cached)
    
    # Build query
    query = db.query(ProductionPlan)
    if plan_status:
        query = query.filter(ProductionPlan.status == plan_status)
    
    total = query.count()
    plans = query.order_by(ProductionPlan.target_date.desc()).offset(skip).limit(page_size).all()
    
    items = [ProductionPlanSchema.from_orm(p) for p in plans]
    result = {
        "items": [item.model_dump(mode='json') for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }
    
    # Cache result
    CacheService.set(cache_key, result, CacheService.TTL_MEDIUM)
    
    return PaginatedResponse[ProductionPlanSchema](**result)


@router.get("/plans/{plan_id}", response_model=ProductionPlanSchema)
def get_production_plan(plan_id: int, db: Session = Depends(get_db)):
    """Get a specific production plan with Redis caching."""
    # Check cache
    cache_key = f"production:plan:{plan_id}"
    cached = CacheService.get(cache_key)
    if cached:
        return cached
    
    plan = db.query(ProductionPlan).filter(ProductionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Production plan not found")
    
    result = ProductionPlanSchema.from_orm(plan)
    
    # Cache result (serialize before caching)
    CacheService.set(cache_key, result.model_dump(mode='json'), CacheService.TTL_MEDIUM)
    
    return result
