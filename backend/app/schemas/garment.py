from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class GarmentBase(BaseModel):
    style_sku: str
    name: str
    category: str
    sub_category: Optional[str] = None
    sizes: List[str]
    gross_weight_per_size: Optional[dict] = None
    mrp: Decimal
    description: Optional[str] = None
    is_active: bool = True


class GarmentCreate(GarmentBase):
    pass


class GarmentUpdate(BaseModel):
    style_sku: Optional[str] = None
    name: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    sizes: Optional[List[str]] = None
    gross_weight_per_size: Optional[dict] = None
    mrp: Optional[Decimal] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class Garment(GarmentBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InventoryBase(BaseModel):
    garment_id: int
    size: str
    good_stock: int = 0
    virtual_stock: int = 0
    warehouse_location: Optional[str] = None


class InventoryCreate(InventoryBase):
    pass


class InventoryUpdate(BaseModel):
    good_stock: Optional[int] = None
    virtual_stock: Optional[int] = None
    warehouse_location: Optional[str] = None


class Inventory(InventoryBase):
    id: int
    last_updated: datetime
    created_at: datetime

    class Config:
        from_attributes = True
