from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ShopifyMasterDataItem(BaseModel):
    id: int
    variant_sku: str
    style_code: str
    title: str
    type: str
    gender: Optional[str] = None
    tags: Optional[str] = None
    size: Optional[str]= None
    collection: Optional[str] = None
    subtype: Optional[str] = None
    season: Optional[str] = None
    fabric_type: Optional[str] = None
    print_name: Optional[str] = None
    net_weight: str
    buffer: Optional[str] = None
    simple_bundle: Optional[str] = None
    mrp: Optional[Decimal] = None
    lifecycle: Optional[str] = None
    summer_factor: Optional[float] = None
    winter_factor: Optional[float] = None
    style_factor: Optional[float] = None
    lead_time: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ShopifyMasterDataListResponse(BaseModel):
    items: list[ShopifyMasterDataItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class ShopifyMasterDataImportSummary(BaseModel):
    inserted: int
    updated: int
    skipped: int
    errors: list[dict]
