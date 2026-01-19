from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from pydantic import BaseModel, EmailStr
from app.db.session import get_db
from app.db.models import Panel

router = APIRouter()


class PanelBase(BaseModel):
    panel_name: str
    panel_type: str
    contact_person: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    is_active: bool = True


class PanelCreate(PanelBase):
    pass


class PanelSchema(PanelBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("/", response_model=PanelSchema, status_code=status.HTTP_201_CREATED)
def create_panel(panel: PanelCreate, db: Session = Depends(get_db)):
    """Create a new panel."""
    db_panel = Panel(**panel.model_dump())
    db.add(db_panel)
    db.commit()
    db.refresh(db_panel)
    return db_panel


@router.get("/", response_model=List[PanelSchema])
def list_panels(
    skip: int = 0,
    limit: int = 100,
    is_active: bool = None,
    panel_type: str = None,
    db: Session = Depends(get_db)
):
    """List all panels with optional filtering."""
    query = db.query(Panel)
    if is_active is not None:
        query = query.filter(Panel.is_active == is_active)
    if panel_type:
        query = query.filter(Panel.panel_type == panel_type)
    
    panels = query.offset(skip).limit(limit).all()
    return panels


@router.get("/{panel_id}", response_model=PanelSchema)
def get_panel(panel_id: int, db: Session = Depends(get_db)):
    """Get a specific panel."""
    panel = db.query(Panel).filter(Panel.id == panel_id).first()
    if not panel:
        raise HTTPException(status_code=404, detail="Panel not found")
    return panel
