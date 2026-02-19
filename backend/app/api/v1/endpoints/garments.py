from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.db.models import Garment
from app.schemas.garment import Garment as GarmentSchema, GarmentCreate, GarmentUpdate
from app.services.cache_service import CacheService
from app.services.websocket_manager import broadcast_inventory_update
from datetime import datetime

router = APIRouter()


@router.post("/", response_model=GarmentSchema, status_code=status.HTTP_201_CREATED)
def create_garment(garment: GarmentCreate, db: Session = Depends(get_db)):
    """Create a new garment."""
    # Check if SKU already exists
    existing = db.query(Garment).filter(
        Garment.style_sku == garment.style_sku).first()
    if existing:
        raise HTTPException(status_code=400, detail="Style SKU already exists")

    db_garment = Garment(**garment.model_dump())
    db.add(db_garment)
    db.commit()
    db.refresh(db_garment)

    # Invalidate garments cache
    CacheService.invalidate_garment_cache()

    return db_garment


@router.get("/", response_model=List[GarmentSchema])
def list_garments(
    skip: int = 0,
    limit: int = 100,
    category: str = None,
    is_active: bool = None,
    db: Session = Depends(get_db)
):
    """List all garments with optional filtering and Redis caching."""
    # Try cache first
    cache_key = f"garments:list:{skip}:{limit}:{category}:{is_active}"
    cached = CacheService.get(cache_key)
    if cached:
        return cached

    # Fetch from DB
    query = db.query(Garment)
    if category:
        query = query.filter(Garment.category == category)
    if is_active is not None:
        query = query.filter(Garment.is_active == is_active)
    garments = query.offset(skip).limit(limit).all()

    # Cache the result (serialize ORM objects before caching)
    result = [GarmentSchema.from_orm(g).model_dump(mode='json') for g in garments]
    CacheService.set(cache_key, result, CacheService.TTL_LONG)

    return garments


@router.get("/{garment_id}", response_model=GarmentSchema)
def get_garment(garment_id: int, db: Session = Depends(get_db)):
    """Get a specific garment with Redis caching."""
    # Try cache first
    cached = CacheService.get_garment_cache(garment_id)
    if cached:
        return cached

    # Fetch from DB
    garment = db.query(Garment).filter(Garment.id == garment_id).first()
    if not garment:
        raise HTTPException(status_code=404, detail="Garment not found")

    # Cache the result (serialize ORM object before caching)
    CacheService.set_garment_cache(
        GarmentSchema.from_orm(garment).model_dump(mode='json'),
        garment_id,
        CacheService.TTL_LONG
    )

    return garment


@router.get("/sku/{style_sku}", response_model=GarmentSchema)
def get_garment_by_sku(style_sku: str, db: Session = Depends(get_db)):
    """Get a garment by SKU."""
    garment = db.query(Garment).filter(Garment.style_sku == style_sku).first()
    if not garment:
        raise HTTPException(status_code=404, detail="Garment not found")
    return garment


@router.put("/{garment_id}", response_model=GarmentSchema)
async def update_garment(garment_id: int, garment_update: GarmentUpdate, db: Session = Depends(get_db)):
    """Update a garment."""
    db_garment = db.query(Garment).filter(Garment.id == garment_id).first()
    if not db_garment:
        raise HTTPException(status_code=404, detail="Garment not found")

    update_data = garment_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_garment, field, value)

    db.commit()
    db.refresh(db_garment)

    # Invalidate cache
    CacheService.invalidate_garment_cache()

    # Broadcast update
    await broadcast_inventory_update({
        "action": "garment_updated",
        "garment_id": garment_id,
        "timestamp": datetime.now().isoformat()
    })

    return db_garment


@router.delete("/{garment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_garment(garment_id: int, db: Session = Depends(get_db)):
    """Delete a garment."""
    db_garment = db.query(Garment).filter(Garment.id == garment_id).first()
    if not db_garment:
        raise HTTPException(status_code=404, detail="Garment not found")

    db.delete(db_garment)
    db.commit()

    # Invalidate cache
    CacheService.invalidate_garment_cache()

    # Broadcast update
    await broadcast_inventory_update({
        "action": "garment_deleted",
        "garment_id": garment_id,
        "timestamp": datetime.now().isoformat()
    })

    return None
