from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.db.models import Yarn
from app.schemas.yarn import Yarn as YarnSchema, YarnCreate, YarnUpdate
from app.schemas.pagination import PaginatedResponse
from app.services.cache_service import CacheService
from app.services.websocket_manager import broadcast_inventory_update
from datetime import datetime

router = APIRouter()


@router.post("/", response_model=YarnSchema, status_code=status.HTTP_201_CREATED)
async def create_yarn(yarn: YarnCreate, db: Session = Depends(get_db)):
    """Create a new yarn entry."""
    db_yarn = Yarn(**yarn.model_dump())
    db.add(db_yarn)
    db.commit()
    db.refresh(db_yarn)
    
    # Invalidate cache
    CacheService.invalidate_yarn_cache()
    
    # Broadcast update
    await broadcast_inventory_update({
        "action": "yarn_created",
        "yarn_id": db_yarn.id,
        "timestamp": datetime.now().isoformat()
    })
    
    return db_yarn


@router.get("/", response_model=PaginatedResponse[YarnSchema])
def list_yarns(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """List all yarn entries with pagination and Redis caching."""
    skip = (page - 1) * page_size
    
    # Check cache
    cache_key = f"yarn:list:{page}:{page_size}"
    cached = CacheService.get(cache_key)
    if cached:
        return PaginatedResponse[YarnSchema](**cached)
    
    # Query database
    total = db.query(Yarn).count()
    yarns = db.query(Yarn).offset(skip).limit(page_size).all()
    
    items = [YarnSchema.from_orm(y) for y in yarns]
    result = {
        "items": [item.model_dump(mode='json') for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }
    
    # Cache result
    CacheService.set(cache_key, result, CacheService.TTL_LONG)
    
    return PaginatedResponse[YarnSchema](**result)


@router.get("/{yarn_id}", response_model=YarnSchema)
def get_yarn(yarn_id: int, db: Session = Depends(get_db)):
    """Get a specific yarn entry with Redis caching."""
    # Check cache
    cached = CacheService.get_yarn_cache(yarn_id)
    if cached:
        return cached
    
    yarn = db.query(Yarn).filter(Yarn.id == yarn_id).first()
    if not yarn:
        raise HTTPException(status_code=404, detail="Yarn not found")
    
    result = YarnSchema.from_orm(yarn)
    
    # Cache result (serialize before caching)
    CacheService.set_yarn_cache(result.model_dump(mode='json'), yarn_id)
    
    return result


@router.put("/{yarn_id}", response_model=YarnSchema)
async def update_yarn(yarn_id: int, yarn_update: YarnUpdate, db: Session = Depends(get_db)):
    """Update a yarn entry."""
    db_yarn = db.query(Yarn).filter(Yarn.id == yarn_id).first()
    if not db_yarn:
        raise HTTPException(status_code=404, detail="Yarn not found")
    
    update_data = yarn_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_yarn, field, value)
    
    db.commit()
    db.refresh(db_yarn)
    
    # Invalidate cache
    CacheService.invalidate_yarn_cache()
    
    # Broadcast update
    await broadcast_inventory_update({
        "action": "yarn_updated",
        "yarn_id": yarn_id,
        "timestamp": datetime.now().isoformat()
    })
    
    return db_yarn


@router.delete("/{yarn_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_yarn(yarn_id: int, db: Session = Depends(get_db)):
    """Delete a yarn entry."""
    db_yarn = db.query(Yarn).filter(Yarn.id == yarn_id).first()
    if not db_yarn:
        raise HTTPException(status_code=404, detail="Yarn not found")
    
    db.delete(db_yarn)
    db.commit()
    
    # Invalidate cache
    CacheService.invalidate_yarn_cache()
    
    # Broadcast update
    await broadcast_inventory_update({
        "action": "yarn_deleted",
        "yarn_id": yarn_id,
        "timestamp": datetime.now().isoformat()
    })
    
    return None
