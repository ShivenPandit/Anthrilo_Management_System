from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.db.models import Fabric
from app.schemas.fabric import Fabric as FabricSchema, FabricCreate, FabricUpdate

router = APIRouter()


@router.post("/", response_model=FabricSchema, status_code=status.HTTP_201_CREATED)
def create_fabric(fabric: FabricCreate, db: Session = Depends(get_db)):
    """Create a new fabric entry."""
    db_fabric = Fabric(**fabric.model_dump())
    db.add(db_fabric)
    db.commit()
    db.refresh(db_fabric)
    return db_fabric


@router.get("/", response_model=List[FabricSchema])
def list_fabrics(
    skip: int = 0,
    limit: int = 100,
    fabric_type: str = None,
    db: Session = Depends(get_db)
):
    """List all fabric entries with optional filtering."""
    query = db.query(Fabric)
    if fabric_type:
        query = query.filter(Fabric.fabric_type == fabric_type)
    fabrics = query.offset(skip).limit(limit).all()
    return fabrics


@router.get("/{fabric_id}", response_model=FabricSchema)
def get_fabric(fabric_id: int, db: Session = Depends(get_db)):
    """Get a specific fabric entry."""
    fabric = db.query(Fabric).filter(Fabric.id == fabric_id).first()
    if not fabric:
        raise HTTPException(status_code=404, detail="Fabric not found")
    return fabric


@router.put("/{fabric_id}", response_model=FabricSchema)
def update_fabric(fabric_id: int, fabric_update: FabricUpdate, db: Session = Depends(get_db)):
    """Update a fabric entry."""
    db_fabric = db.query(Fabric).filter(Fabric.id == fabric_id).first()
    if not db_fabric:
        raise HTTPException(status_code=404, detail="Fabric not found")
    
    update_data = fabric_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_fabric, field, value)
    
    db.commit()
    db.refresh(db_fabric)
    return db_fabric


@router.delete("/{fabric_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fabric(fabric_id: int, db: Session = Depends(get_db)):
    """Delete a fabric entry."""
    db_fabric = db.query(Fabric).filter(Fabric.id == fabric_id).first()
    if not db_fabric:
        raise HTTPException(status_code=404, detail="Fabric not found")
    
    db.delete(db_fabric)
    db.commit()
    return None
