from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.db.models import Fabric
from app.schemas.fabric import Fabric as FabricSchema, FabricCreate, FabricUpdate
from app.schemas.pagination import PaginatedResponse
from app.services.cache_service import CacheService
from app.services.websocket_manager import broadcast_inventory_update
from datetime import datetime

router = APIRouter()


@router.post("/", response_model=FabricSchema, status_code=status.HTTP_201_CREATED)
async def create_fabric(fabric: FabricCreate, db: Session = Depends(get_db)):
    """Create a new fabric entry."""
    db_fabric = Fabric(**fabric.model_dump())
    db.add(db_fabric)
    db.commit()
    db.refresh(db_fabric)
    
    # Invalidate cache
    CacheService.invalidate_fabric_cache()
    
    # Broadcast update
    await broadcast_inventory_update({
        "action": "fabric_created",
        "fabric_id": db_fabric.id,
        "timestamp": datetime.now().isoformat()
    })
    
    return db_fabric


@router.get("/", response_model=PaginatedResponse[FabricSchema])
def list_fabrics(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    fabric_type: str = Query(None, description="Filter by fabric type"),
    db: Session = Depends(get_db)
):
    """List all fabric entries with pagination and Redis caching."""
    # Calculate skip
    skip = (page - 1) * page_size
    
    # Check cache
    cache_key = f"fabric:list:{page}:{page_size}:{fabric_type}"
    cached = CacheService.get(cache_key)
    if cached:
        return PaginatedResponse[FabricSchema](**cached)
    
    # Query database
    query = db.query(Fabric)
    if fabric_type:
        query = query.filter(Fabric.fabric_type == fabric_type)
    
    total = query.count()
    fabrics = query.offset(skip).limit(page_size).all()
    
    items = [FabricSchema.from_orm(f) for f in fabrics]
    result = {
        "items": [item.model_dump(mode='json') for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }
    
    # Cache result
    CacheService.set(cache_key, result, CacheService.TTL_LONG)
    
    return PaginatedResponse[FabricSchema](**result)


@router.get("/{fabric_id}", response_model=FabricSchema)
def get_fabric(fabric_id: int, db: Session = Depends(get_db)):
    """Get a specific fabric entry with Redis caching."""
    # Check cache
    cached = CacheService.get_fabric_cache(fabric_id)
    if cached:
        return cached
    
    fabric = db.query(Fabric).filter(Fabric.id == fabric_id).first()
    if not fabric:
        raise HTTPException(status_code=404, detail="Fabric not found")
    
    result = FabricSchema.from_orm(fabric)
    
    # Cache result (serialize before caching)
    CacheService.set_fabric_cache(result.model_dump(mode='json'), fabric_id)
    
    return result


@router.put("/{fabric_id}", response_model=FabricSchema)
async def update_fabric(fabric_id: int, fabric_update: FabricUpdate, db: Session = Depends(get_db)):
    """Update a fabric entry."""
    db_fabric = db.query(Fabric).filter(Fabric.id == fabric_id).first()
    if not db_fabric:
        raise HTTPException(status_code=404, detail="Fabric not found")
    
    update_data = fabric_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_fabric, field, value)
    
    db.commit()
    db.refresh(db_fabric)
    
    # Invalidate cache
    CacheService.invalidate_fabric_cache()
    
    # Broadcast update
    await broadcast_inventory_update({
        "action": "fabric_updated",
        "fabric_id": fabric_id,
        "timestamp": datetime.now().isoformat()
    })
    
    return db_fabric


@router.delete("/{fabric_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fabric(fabric_id: int, db: Session = Depends(get_db)):
    """Delete a fabric entry."""
    db_fabric = db.query(Fabric).filter(Fabric.id == fabric_id).first()
    if not db_fabric:
        raise HTTPException(status_code=404, detail="Fabric not found")
    
    db.delete(db_fabric)
    db.commit()
    
    # Invalidate cache
    CacheService.invalidate_fabric_cache()
    
    # Broadcast update
    await broadcast_inventory_update({
        "action": "fabric_deleted",
        "fabric_id": fabric_id,
        "timestamp": datetime.now().isoformat()
    })
    
    return None
