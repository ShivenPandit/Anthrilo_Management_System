from typing import Optional
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class FabricBase(BaseModel):
    fabric_type: str
    subtype: str
    gsm: int
    composition: str
    width: Optional[Decimal] = None
    color: Optional[str] = None
    stock_quantity: Decimal = Decimal(0)
    unit: str = "kg"
    cost_per_unit: Optional[Decimal] = None


class FabricCreate(FabricBase):
    pass


class FabricUpdate(BaseModel):
    fabric_type: Optional[str] = None
    subtype: Optional[str] = None
    gsm: Optional[int] = None
    composition: Optional[str] = None
    width: Optional[Decimal] = None
    color: Optional[str] = None
    stock_quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    cost_per_unit: Optional[Decimal] = None


class Fabric(FabricBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
