from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.session import get_db
from app.db.models import Process
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime

router = APIRouter()


class ProcessBase(BaseModel):
    process_type: str
    process_name: str
    process_rate: Decimal
    rate_unit: str = "per_kg"
    vendor: str | None = None
    description: str | None = None
    is_active: bool = True


class ProcessCreate(ProcessBase):
    pass


class ProcessSchema(ProcessBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("/", response_model=ProcessSchema, status_code=status.HTTP_201_CREATED)
def create_process(process: ProcessCreate, db: Session = Depends(get_db)):
    """Create a new process entry."""
    db_process = Process(**process.model_dump())
    db.add(db_process)
    db.commit()
    db.refresh(db_process)
    return db_process


@router.get("/", response_model=List[ProcessSchema])
def list_processes(
    skip: int = 0,
    limit: int = 100,
    process_type: str = None,
    db: Session = Depends(get_db)
):
    """List all process entries with optional filtering."""
    query = db.query(Process)
    if process_type:
        query = query.filter(Process.process_type == process_type)
    processes = query.offset(skip).limit(limit).all()
    return processes


@router.get("/{process_id}", response_model=ProcessSchema)
def get_process(process_id: int, db: Session = Depends(get_db)):
    """Get a specific process entry."""
    process = db.query(Process).filter(Process.id == process_id).first()
    if not process:
        raise HTTPException(status_code=404, detail="Process not found")
    return process
