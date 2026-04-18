from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ShopifyMasterDataItem(BaseModel):
    id: int
    variant_sku: str
    title: Optional[str] = None
    type: Optional[str] = None
    tags: Optional[str] = None
    option1_value: Optional[str] = None
    cost_per_item: Optional[Decimal] = None
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
