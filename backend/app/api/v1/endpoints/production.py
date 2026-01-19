from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel
from app.db.session import get_db
from app.db.models import ProductionPlan, ProductionActivity, Garment

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
def create_production_plan(plan: ProductionPlanCreate, db: Session = Depends(get_db)):
    """Create a new production plan."""
    garment = db.query(Garment).filter(Garment.id == plan.garment_id).first()
    if not garment:
        raise HTTPException(status_code=404, detail="Garment not found")
    
    db_plan = ProductionPlan(**plan.model_dump())
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan


@router.get("/plans", response_model=List[ProductionPlanSchema])
def list_production_plans(
    skip: int = 0,
    limit: int = 100,
    status: str = None,
    db: Session = Depends(get_db)
):
    """List all production plans with optional filtering."""
    query = db.query(ProductionPlan)
    if status:
        query = query.filter(ProductionPlan.status == status)
    
    plans = query.order_by(ProductionPlan.target_date.desc()).offset(skip).limit(limit).all()
    return plans


@router.get("/plans/{plan_id}", response_model=ProductionPlanSchema)
def get_production_plan(plan_id: int, db: Session = Depends(get_db)):
    """Get a specific production plan."""
    plan = db.query(ProductionPlan).filter(ProductionPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Production plan not found")
    return plan
