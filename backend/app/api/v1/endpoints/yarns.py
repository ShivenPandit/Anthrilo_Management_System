from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.db.models import Yarn
from app.schemas.yarn import Yarn as YarnSchema, YarnCreate, YarnUpdate

router = APIRouter()


@router.post("/", response_model=YarnSchema, status_code=status.HTTP_201_CREATED)
def create_yarn(yarn: YarnCreate, db: Session = Depends(get_db)):
    """Create a new yarn entry."""
    db_yarn = Yarn(**yarn.model_dump())
    db.add(db_yarn)
    db.commit()
    db.refresh(db_yarn)
    return db_yarn


@router.get("/", response_model=List[YarnSchema])
def list_yarns(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List all yarn entries."""
    yarns = db.query(Yarn).offset(skip).limit(limit).all()
    return yarns


@router.get("/{yarn_id}", response_model=YarnSchema)
def get_yarn(yarn_id: int, db: Session = Depends(get_db)):
    """Get a specific yarn entry."""
    yarn = db.query(Yarn).filter(Yarn.id == yarn_id).first()
    if not yarn:
        raise HTTPException(status_code=404, detail="Yarn not found")
    return yarn


@router.put("/{yarn_id}", response_model=YarnSchema)
def update_yarn(yarn_id: int, yarn_update: YarnUpdate, db: Session = Depends(get_db)):
    """Update a yarn entry."""
    db_yarn = db.query(Yarn).filter(Yarn.id == yarn_id).first()
    if not db_yarn:
        raise HTTPException(status_code=404, detail="Yarn not found")
    
    update_data = yarn_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_yarn, field, value)
    
    db.commit()
    db.refresh(db_yarn)
    return db_yarn


@router.delete("/{yarn_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_yarn(yarn_id: int, db: Session = Depends(get_db)):
    """Delete a yarn entry."""
    db_yarn = db.query(Yarn).filter(Yarn.id == yarn_id).first()
    if not db_yarn:
        raise HTTPException(status_code=404, detail="Yarn not found")
    
    db.delete(db_yarn)
    db.commit()
    return None
