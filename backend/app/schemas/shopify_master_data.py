from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ShopifyMasterDataItem(BaseModel):
    id: int
    variant_sku: str
    style_code: Optional[str] = None
    title: Optional[str] = None
    type: Optional[str] = None
    gender: Optional[str] = None
    tags: Optional[str] = None
    option1_value: Optional[str] = None
    collection: Optional[str] = None
    subtype: Optional[str] = None
    season: Optional[str] = None
    fabric_type: Optional[str] = None
    print_name: Optional[str] = None
    net_weight: Optional[str] = None
    production_time: Optional[str] = None
    simple_bundle: Optional[str] = None
    mrp: Optional[Decimal] = None
    gross_weights_1: Optional[str] = None
    garment_1: Optional[str] = None
    gross_weights_2: Optional[str] = None
    garment_2: Optional[str] = None
    amazon_asin: Optional[str] = None
    amazon_flex_sku: Optional[str] = None
    amazon_fba_sku: Optional[str] = None
    amazon_mfn_sku: Optional[str] = None
    myntra_style_id: Optional[str] = None
    myntra_sku: Optional[str] = None
    fc: Optional[str] = None
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
