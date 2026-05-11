from datetime import datetime, date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ProductionPlanningManualEntry(BaseModel):
    sku: str = Field(min_length=1)
    style_code: Optional[str] = None
    name: Optional[str] = None
    size: Optional[str] = None
    type: Optional[str] = None
    cutting_plan: int = 0
    cutting: int = 0
    stitching: int = 0
    finishing: int = 0


class ProductionPlanningRow(BaseModel):
    sku: str
    style_code: Optional[str] = None
    name: Optional[str] = None
    size: Optional[str] = None
    type: Optional[str] = None
    cutting_plan: int
    cutting: int
    stitching: int
    finishing: int
    created_at: datetime
    updated_at: datetime


class ProductionPlanningHistoryRow(BaseModel):
    sku: str
    old_cutting_plan: int
    new_cutting_plan: int
    old_cutting: int
    new_cutting: int
    old_stitching: int
    new_stitching: int
    old_finishing: int
    new_finishing: int
    updated_quantity_difference: int
    update_source: Literal["CSV", "MANUAL"]
    updated_at: datetime


class ProductionPlanningListResponse(BaseModel):
    items: list[ProductionPlanningRow]
    page: int
    page_size: int
    total: int
    total_pages: int


class ProductionPlanningHistoryResponse(BaseModel):
    items: list[ProductionPlanningHistoryRow]
    page: int
    page_size: int
    total: int
    total_pages: int


class ProductionPlanningUploadSummary(BaseModel):
    total_rows_processed: int
    new_skus_created: int
    existing_skus_updated: int
    failed_rows_count: int
    failed_rows: list[dict]


class ProductionPlanningTableFilters(BaseModel):
    search: Optional[str] = None
    updated_from: Optional[date] = None
    updated_to: Optional[date] = None
