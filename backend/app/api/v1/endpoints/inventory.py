from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime
from app.db.session import get_db
from app.db.models import Inventory, Garment
from app.schemas.garment import Inventory as InventorySchema, InventoryCreate, InventoryUpdate
from app.services.cache_service import CacheService
from app.services.websocket_manager import broadcast_inventory_update

router = APIRouter()


@router.post("/", response_model=InventorySchema, status_code=status.HTTP_201_CREATED)
async def create_inventory(inventory: InventoryCreate, db: Session = Depends(get_db)):
    """Create a new inventory record."""
    # Check if garment exists
    garment = db.query(Garment).filter(
        Garment.id == inventory.garment_id).first()
    if not garment:
        raise HTTPException(status_code=404, detail="Garment not found")

    # Check if inventory already exists for this garment-size combination
    existing = db.query(Inventory).filter(
        Inventory.garment_id == inventory.garment_id,
        Inventory.size == inventory.size
    ).first()
    if existing:
        raise HTTPException(
            status_code=400, detail="Inventory already exists for this garment-size combination")

    db_inventory = Inventory(**inventory.model_dump())
    db.add(db_inventory)
    db.commit()
    db.refresh(db_inventory)

    # Invalidate inventory cache
    CacheService.invalidate_inventory_cache()
    
    # Broadcast update
    await broadcast_inventory_update({
        "action": "inventory_created",
        "inventory_id": db_inventory.id,
        "garment_id": inventory.garment_id,
        "timestamp": datetime.now().isoformat()
    })

    return db_inventory


@router.get("/", response_model=List[InventorySchema])
def list_inventory(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all inventory records with Redis caching."""
    # Try cache first
    cache_key = f"inventory:list:{skip}:{limit}"
    cached = CacheService.get(cache_key)
    if cached:
        return cached

    # Fetch from DB
    inventory = db.query(Inventory).offset(skip).limit(limit).all()
    result = [InventorySchema.from_orm(item) for item in inventory]

    # Cache the result (serialize before caching)
    CacheService.set(cache_key, [item.model_dump(mode='json') for item in result], CacheService.TTL_SHORT)

    return result


@router.get("/garment/{garment_id}", response_model=List[InventorySchema])
def get_inventory_by_garment(garment_id: int, db: Session = Depends(get_db)):
    """Get inventory for a specific garment."""
    inventory = db.query(Inventory).filter(
        Inventory.garment_id == garment_id).all()
    return inventory


@router.put("/{inventory_id}", response_model=InventorySchema)
async def update_inventory(inventory_id: int, inventory_update: InventoryUpdate, db: Session = Depends(get_db)):
    """Update an inventory record."""
    db_inventory = db.query(Inventory).filter(
        Inventory.id == inventory_id).first()
    if not db_inventory:
        raise HTTPException(status_code=404, detail="Inventory not found")

    update_data = inventory_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_inventory, field, value)

    db_inventory.last_updated = datetime.utcnow()
    db.commit()
    db.refresh(db_inventory)
    
    # Invalidate cache
    CacheService.invalidate_inventory_cache()
    
    # Broadcast update
    await broadcast_inventory_update({
        "action": "inventory_updated",
        "inventory_id": inventory_id,
        "garment_id": db_inventory.garment_id,
        "good_stock": db_inventory.good_stock,
        "timestamp": datetime.now().isoformat()
    })
    
    return db_inventory


@router.get("/low-stock/", response_model=List[InventorySchema])
def get_low_stock(threshold: int = 10, db: Session = Depends(get_db)):
    """Get inventory items with low stock."""
    inventory = db.query(Inventory).filter(
        Inventory.good_stock <= threshold).all()
    return inventory
