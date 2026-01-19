from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.db.models import Garment
from app.schemas.garment import Garment as GarmentSchema, GarmentCreate, GarmentUpdate

router = APIRouter()


@router.post("/", response_model=GarmentSchema, status_code=status.HTTP_201_CREATED)
def create_garment(garment: GarmentCreate, db: Session = Depends(get_db)):
    """Create a new garment."""
    # Check if SKU already exists
    existing = db.query(Garment).filter(Garment.style_sku == garment.style_sku).first()
    if existing:
        raise HTTPException(status_code=400, detail="Style SKU already exists")
    
    db_garment = Garment(**garment.model_dump())
    db.add(db_garment)
    db.commit()
    db.refresh(db_garment)
    return db_garment


@router.get("/", response_model=List[GarmentSchema])
def list_garments(
    skip: int = 0,
    limit: int = 100,
    category: str = None,
    is_active: bool = None,
    db: Session = Depends(get_db)
):
    """List all garments with optional filtering."""
    query = db.query(Garment)
    if category:
        query = query.filter(Garment.category == category)
    if is_active is not None:
        query = query.filter(Garment.is_active == is_active)
    garments = query.offset(skip).limit(limit).all()
    return garments


@router.get("/{garment_id}", response_model=GarmentSchema)
def get_garment(garment_id: int, db: Session = Depends(get_db)):
    """Get a specific garment."""
    garment = db.query(Garment).filter(Garment.id == garment_id).first()
    if not garment:
        raise HTTPException(status_code=404, detail="Garment not found")
    return garment


@router.get("/sku/{style_sku}", response_model=GarmentSchema)
def get_garment_by_sku(style_sku: str, db: Session = Depends(get_db)):
    """Get a garment by SKU."""
    garment = db.query(Garment).filter(Garment.style_sku == style_sku).first()
    if not garment:
        raise HTTPException(status_code=404, detail="Garment not found")
    return garment


@router.put("/{garment_id}", response_model=GarmentSchema)
def update_garment(garment_id: int, garment_update: GarmentUpdate, db: Session = Depends(get_db)):
    """Update a garment."""
    db_garment = db.query(Garment).filter(Garment.id == garment_id).first()
    if not db_garment:
        raise HTTPException(status_code=404, detail="Garment not found")
    
    update_data = garment_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_garment, field, value)
    
    db.commit()
    db.refresh(db_garment)
    return db_garment


@router.delete("/{garment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_garment(garment_id: int, db: Session = Depends(get_db)):
    """Delete a garment."""
    db_garment = db.query(Garment).filter(Garment.id == garment_id).first()
    if not db_garment:
        raise HTTPException(status_code=404, detail="Garment not found")
    
    db.delete(db_garment)
    db.commit()
    return None
