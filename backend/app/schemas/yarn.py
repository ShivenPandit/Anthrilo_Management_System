from typing import Optional
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class YarnBase(BaseModel):
    yarn_type: str
    yarn_count: str
    composition: str
    percentage_breakdown: Optional[dict] = None
    supplier: Optional[str] = None
    unit_price: Optional[Decimal] = None
    stock_quantity: Decimal = Decimal(0)
    unit: str = "kg"


class YarnCreate(YarnBase):
    pass


class YarnUpdate(BaseModel):
    yarn_type: Optional[str] = None
    yarn_count: Optional[str] = None
    composition: Optional[str] = None
    percentage_breakdown: Optional[dict] = None
    supplier: Optional[str] = None
    unit_price: Optional[Decimal] = None
    stock_quantity: Optional[Decimal] = None
    unit: Optional[str] = None


class Yarn(YarnBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
