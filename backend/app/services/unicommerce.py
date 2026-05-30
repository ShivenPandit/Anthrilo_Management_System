"""Unicommerce integration service.

Handles fetching and processing sale orders via the Unicommerce API.
Uses the export job API exclusively for bulk CSV downloads.
"""

import csv
import hashlib
import json
import re
import io
import time as time_module
import httpx
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.services.order_date_validation import validate_order_date

from app.core.token_manager import get_token_manager
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.export_models import (
    ExportJob,
    ExportRow,
    SalesOrderRecord,
    SalesReturnRecord,
    SyncLog,
)
from app.services.schema_drift_checker import SchemaDriftChecker

logger = logging.getLogger(__name__)

# IST timezone offset
IST = timezone(timedelta(hours=5, minutes=30))
TZ_SUFFIX_RE = re.compile(r"(Z|[+-]\d{2}:\d{2})$")


class UnicommerceService:
    """Fetches and aggregates Unicommerce sale orders."""

    CACHE_TTL_SECONDS = 900  # 15 min

    EXCLUDED_STATUSES = {
        "CANCELLED", "CANCELED", "RETURNED", "REFUNDED",
        "FAILED", "UNFULFILLABLE", "ERROR", "PENDING_VERIFICATION"
    }

    # Item categories to exclude from sales data (faulty/non-product entries)
    EXCLUDED_CATEGORIES = {"FABRIC"}

    EXPORT_MAX_POLL_SECONDS = 1200
    EXPORT_INITIAL_POLL_INTERVAL = 2
    EXPORT_MAX_POLL_INTERVAL = 10     # Max poll interval (backoff cap)
    EXPORT_POLL_BACKOFF = 1.5         # Polling backoff multiplier

    # Columns for the export job (note: UC spells it "exportColums")
    EXPORT_COLUMNS = [
        "saleOrderCode",
        "channel",
        "status",
        "created",
        "updated",
        "shippingMethod",
        "cod",              # 1 = COD, 0 = Prepaid
        "soicode",
        "skuCode",
        "sellingPrice",
        "maxRetailPrice",
        "discount",
        "totalPrice",
        "channelProductId",
        "bundleSkuCode",
        "itemDetails",
        "itemTypeName",
        "category",
    ]

    def __init__(self):
        self.token_manager = get_token_manager()
        self.access_code = self.token_manager.access_code
        self.tenant = self.token_manager.tenant
        self.base_url = f"https://{self.tenant}.unicommerce.com/services/rest/v1"

        # HTTP client settings — read timeout 120s for slow UC status responses
        self.timeout = httpx.Timeout(120.0, connect=10.0)
        self.limits = httpx.Limits(
            max_connections=150,
            max_keepalive_connections=50
        )

        # In-memory cache
        self._cache: Dict[str, Tuple[datetime, Any]] = {}

        # Serialize export job creation — UC allows only one at a time
        self._export_lock = asyncio.Lock()

        self.export_max_no_filepath_retries = max(
            1, int(settings.UNICOMMERCE_EXPORT_MAX_NO_FILEPATH_RETRIES)
        )
        self.export_status_retry_grace_seconds = max(
            0, int(settings.UNICOMMERCE_EXPORT_STATUS_RETRY_GRACE_SECONDS)
        )
        self.export_max_consecutive_poll_errors = max(
            1, int(settings.UNICOMMERCE_EXPORT_MAX_CONSECUTIVE_POLL_ERRORS)
        )
        self.export_download_max_retries = max(
            1, int(settings.UNICOMMERCE_EXPORT_DOWNLOAD_MAX_RETRIES)
        )
        self.export_download_backoff_seconds = max(
            1, int(settings.UNICOMMERCE_EXPORT_DOWNLOAD_BACKOFF_SECONDS)
        )

        logger.info(
            f"UnicommerceService v3 initialized | "
            f"Tenant: {self.tenant} | "
            f"Method: Export Job API only | "
            f"Cache TTL: {self.CACHE_TTL_SECONDS}s"
        )


    async def _get_headers(self) -> Dict[str, str]:
        """Build auth headers."""
        return await self.token_manager.get_headers()


    def _get_cache_key(self, period: str) -> str:
        return f"sales_data_{period}"

    def _get_from_cache(self, key: str) -> Optional[Any]:
        if key in self._cache:
            timestamp, data = self._cache[key]
            age = (datetime.now() - timestamp).total_seconds()
            if age < self.CACHE_TTL_SECONDS:
                logger.debug(
                    f"Cache hit for {key} (age: {age:.1f}s / {self.CACHE_TTL_SECONDS}s)")
                return data
            else:
                del self._cache[key]
        return None

    def _set_cache(self, key: str, data: Any):
        self._cache[key] = (datetime.now(), data)

    @staticmethod
    def _extract_export_file_path(payload: Dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            return ""

        candidate_keys = (
            "filePath",
            "filepath",
            "fileUrl",
            "fileURL",
            "downloadUrl",
            "downloadURL",
            "signedUrl",
            "signedURL",
            "url",
        )

        containers: List[Dict[str, Any]] = [payload]
        nested_payload = payload.get("data")
        if isinstance(nested_payload, dict):
            containers.append(nested_payload)

        for container in containers:
            for key in candidate_keys:
                value = container.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    async def _download_csv_text(self, download_url: str, label: str) -> Optional[str]:
        download_timeout = httpx.Timeout(120.0, connect=15.0)
        max_retries = max(1, int(self.export_download_max_retries))
        base_backoff_seconds = max(1, int(self.export_download_backoff_seconds))

        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=download_timeout) as client:
                    response = await client.get(download_url)

                    if response.status_code in (401, 403):
                        self.token_manager.invalidate_token()
                        await self.token_manager.get_valid_token()
                        headers = await self._get_headers()
                        response = await client.get(download_url, headers=headers)

                    response.raise_for_status()
                    return response.text

            except (
                httpx.ReadTimeout,
                httpx.ConnectTimeout,
                httpx.PoolTimeout,
                httpx.TransportError,
            ) as exc:
                retryable = attempt < max_retries
                logger.warning(
                    f"{label}: download transport error attempt {attempt}/{max_retries}: {exc}"
                )
                if retryable:
                    await asyncio.sleep(base_backoff_seconds * attempt)
                    continue
                return None

            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                retryable = (
                    status_code in {401, 403, 429, 500, 502, 503, 504}
                    and attempt < max_retries
                )
                logger.warning(
                    f"{label}: download HTTP {status_code} attempt {attempt}/{max_retries}"
                )
                if retryable:
                    await asyncio.sleep(base_backoff_seconds * attempt)
                    continue
                return None

            except Exception as exc:
                retryable = attempt < max_retries
                logger.warning(
                    f"{label}: download unexpected error attempt {attempt}/{max_retries}: {exc}"
                )
                if retryable:
                    await asyncio.sleep(base_backoff_seconds * attempt)
                    continue
                return None

        return None

    @staticmethod
    def _safe_str(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _clean_code(value: Any) -> str:
        """
        Normalize IDs coming from CSV exports.
        Some exports include Excel-safe prefixes like ` or '.
        """
        text_value = str(value).strip() if value is not None else ""
        return text_value.lstrip("`'").strip()

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            cleaned = str(value).strip().replace(",", "")
            return int(float(cleaned))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            cleaned = str(value).strip().replace(",", "")
            return float(cleaned)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value

        raw = str(value).strip()
        if not raw:
            return None

        try:
            numeric = float(raw)
            if numeric > 1e12:
                numeric /= 1000.0
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (ValueError, TypeError, OverflowError, OSError):
            pass

        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            pass

        formats = [
            "%d %b %Y %H:%M:%S",
            "%d/%m/%Y %H:%M:%S",
            "%d-%m-%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
        ]
        for fmt in formats:
            try:
                parsed = datetime.strptime(raw, fmt)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return None

    def _parse_business_order_datetime(self, row: Dict[str, Any]) -> Optional[datetime]:
        """Use only the business event timestamp field for order_date."""
        candidates = (
            row.get("Order Date as dd/mm/yyyy hh:MM:ss"),
            row.get("orderDate"),
            row.get("order_date"),
            row.get("Order Date"),
        )
        for candidate in candidates:
            parsed = self._parse_datetime(candidate)
            if parsed is not None:
                raw = str(candidate).strip() if candidate is not None else ""
                if raw and not TZ_SUFFIX_RE.search(raw):
                    return parsed.replace(tzinfo=IST).astimezone(timezone.utc)
                return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return None

    @staticmethod
    def _partition_month_from_dt(value: Optional[datetime]):
        if value is None:
            return datetime(2000, 1, 1, tzinfo=timezone.utc).date()
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).date().replace(day=1)

    @staticmethod
    def _normalize_csv_row(row: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in row.items():
            key_str = str(key) if key is not None else ""
            if not key_str:
                continue
            normalized[key_str] = "" if value is None else str(value)
        return normalized

    @staticmethod
    def _to_snake_key(key: Any) -> str:
        if not isinstance(key, str):
            return ""
        key = key.lower().strip()
        key = re.sub(r"[^\w]+", "_", key)
        key = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
        key = re.sub(r"_+", "_", key).strip("_").lower()
        return key

    def _normalized_extra_fields(
        self,
        row: Dict[str, Any],
        *,
        known_keys: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in row.items():
            sk = self._to_snake_key(k)
            if not sk:
                continue
            if known_keys and sk in known_keys:
                continue
            out[sk] = v
        return out

    @staticmethod
    def _row_hash(payload: Dict[str, Any]) -> str:
        serialized = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _auto_sale_order_item_code(self, order_id: str, row: Dict[str, Any]) -> str:
        """
        Deterministic fallback item-code when the export does not provide one.

        IMPORTANT: This must be stable across re-syncs even if the CSV contains Excel-safe prefixes
        (like ` or ') or minor string formatting differences in unrelated columns.
        """
        sku = self._clean_code(row.get("Item SKU Code") or row.get("skuCode") or row.get("itemSku") or "")
        name = self._safe_str(row.get("Item Details") or row.get("itemDetails") or row.get("itemTypeName") or "")
        qty = self._safe_int(row.get("Quantity") or row.get("Qty") or row.get("QTY") or row.get("quantity") or 1, default=1)
        price = self._safe_str(row.get("Selling Price") or row.get("sellingPrice") or "0")
        key = f"{order_id}|{sku}|{qty}|{price}|{name}".strip()
        return f"AUTO-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]}"

    def _derive_export_entity(
        self,
        export_type: str,
        row: Dict[str, Any],
    ) -> Tuple[str, Optional[str]]:
        et = export_type.lower()
        if et == "sale_orders":
            entity_key = (
                self._safe_str(row.get("Sale Order Code"))
                or self._safe_str(row.get("saleOrderCode"))
                or self._safe_str(row.get("code"))
            )
            return "sale_order", entity_key or None

        if et == "return_gst":
            order_code = (
                self._safe_str(row.get("Sale Order Number"))
                or self._safe_str(row.get("Sale Order Code"))
                or self._safe_str(row.get("saleOrderCode"))
            )
            invoice_code = (
                self._safe_str(row.get("Invoice number"))
                or self._safe_str(row.get("Invoice Code"))
                or self._safe_str(row.get("invoiceCode"))
            )
            entity_key = f"{order_code}:{invoice_code}" if (order_code or invoice_code) else None
            return "sales_return", entity_key

        if et == "item_master":
            entity_key = (
                self._safe_str(row.get("Product Code"))
                or self._safe_str(row.get("SKU Code"))
            )
            return "item_master", entity_key or None

        if et == "inventory_snapshot":
            entity_key = self._safe_str(row.get("itemTypeSKU")) or self._safe_str(row.get("sku"))
            return "inventory_snapshot", entity_key or None

        return et, None

    def _create_export_job_record(
        self,
        export_type: str,
        requested_from: Optional[datetime],
        requested_to: Optional[datetime],
        requested_columns: Optional[List[str]],
        job_code: Optional[str] = None,
    ) -> Optional[int]:
        db = SessionLocal()
        try:
            job = ExportJob(
                export_type=export_type,
                job_code=job_code,
                status="running",
                requested_from=requested_from,
                requested_to=requested_to,
                requested_columns=requested_columns,
                started_at=datetime.utcnow(),
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            return job.id
        except Exception as exc:
            db.rollback()
            logger.warning(f"Export archival: failed to create export_jobs row: {exc}")
            return None
        finally:
            db.close()

    def _update_export_job_record(self, export_job_id: Optional[int], **fields: Any) -> None:
        if not export_job_id:
            return

        db = SessionLocal()
        try:
            fields["updated_at"] = datetime.utcnow()
            db.query(ExportJob).filter(ExportJob.id == export_job_id).update(fields)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning(f"Export archival: failed to update export job {export_job_id}: {exc}")
        finally:
            db.close()

    def _create_sync_log_record(
        self,
        sync_type: str,
        entity: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        db = SessionLocal()
        try:
            sync_log = SyncLog(
                sync_type=sync_type,
                entity=entity,
                status="running",
                started_at=datetime.utcnow(),
                details=details or {},
            )
            db.add(sync_log)
            db.commit()
            db.refresh(sync_log)
            return sync_log.id
        except Exception as exc:
            db.rollback()
            logger.warning(f"Sync log: failed to create row: {exc}")
            return None
        finally:
            db.close()

    def _update_sync_log_record(self, sync_log_id: Optional[int], **fields: Any) -> None:
        if not sync_log_id:
            return

        db = SessionLocal()
        try:
            db.query(SyncLog).filter(SyncLog.id == sync_log_id).update(fields)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning(f"Sync log: failed to update row {sync_log_id}: {exc}")
        finally:
            db.close()

    def _archive_export_rows(
        self,
        export_job_id: Optional[int],
        export_type: str,
        rows: List[Dict[str, Any]],
        row_number_start: int = 1,
    ) -> Tuple[int, Optional[str]]:
        if not export_job_id or not rows:
            return 0, None

        payloads: List[Dict[str, Any]] = []
        checksum = hashlib.sha256()

        safe_row_start = max(1, int(row_number_start))
        for row_number, raw_row in enumerate(rows, start=safe_row_start):
            normalized_row = self._normalize_csv_row(raw_row)
            row_hash = self._row_hash(normalized_row)
            entity_type, entity_key = self._derive_export_entity(export_type, normalized_row)
            created_at = datetime.utcnow()

            checksum.update(f"{row_number}:{row_hash}".encode("utf-8"))
            payloads.append(
                {
                    "export_job_id": export_job_id,
                    "row_number": row_number,
                    "entity_type": entity_type,
                    "entity_key": entity_key,
                    "row_hash": row_hash,
                    "payload": normalized_row,
                    "created_at": created_at,
                    "partition_month": created_at.date().replace(day=1),
                }
            )

        db = SessionLocal()
        try:
            chunk_size = 2000
            for start in range(0, len(payloads), chunk_size):
                chunk = payloads[start:start + chunk_size]
                stmt = (
                    pg_insert(ExportRow)
                    .values(chunk)
                    .on_conflict_do_nothing(
                        index_elements=["export_job_id", "row_number", "partition_month"]
                    )
                )
                db.execute(stmt)

            db.commit()
            return len(payloads), checksum.hexdigest()
        except Exception as exc:
            db.rollback()
            logger.warning(f"Export archival: failed to persist export rows: {exc}")
            return 0, checksum.hexdigest()
        finally:
            db.close()

    def _upsert_sales_order_rows(
        self,
        rows: List[Dict[str, Any]],
        *,
        validation_context: str = "sync_import",
    ) -> int:
        if not rows:
            return 0

        payloads: List[Dict[str, Any]] = []
        known_sales_keys = {
            "sale_order_item_code", "display_order_code", "sale_order_code", "channel_name", "item_sku_code",
            "item_details", "selling_price", "discount", "tax", "refund", "category", "sale_order_status",
            "order_date_as_dd_mm_yyyy_hh_mm_ss", "dispatch_date", "delivery_date", "cancel_date", "return_date",
            "warehouse", "facility", "customer_name", "shipping_address_name", "shipping_address_city",
            "invoice_code", "invoice_created", "sale_order_item_status", "shipping_provider", "tracking_number",
            "payment_instrument", "currency", "currency_conversion_rate", "total_price", "mrp", "cost_price",
            "subtotal", "tax", "tax_value", "tax_percent", "shipping_charges", "shipping_method_charges",
            "cod_service_charges", "channel_product_id", "item_type_name", "item_type_color", "item_type_size",
            "item_type_brand", "hsn_code", "bundle_sku_code_number", "seller_sku_code", "item_type_ean",
            "parent_sale_order_code",
        }

        for raw_row in rows:
            row = self._normalize_csv_row(raw_row)

            order_id = (
                self._clean_code(row.get("Sale Order Code"))
                or self._clean_code(row.get("saleOrderCode"))
                or self._clean_code(row.get("code"))
            )
            if not order_id:
                continue

            sale_order_item_code = (
                self._clean_code(row.get("Sale Order Item Code"))
                or self._clean_code(row.get("soicode"))
            )
            if not sale_order_item_code:
                sale_order_item_code = self._auto_sale_order_item_code(order_id, row)

            qty = self._safe_int(
                row.get("Quantity")
                or row.get("Qty")
                or row.get("QTY")
                or row.get("quantity")
                or 1,
                default=1,
            )
            if qty <= 0:
                qty = 1

            channel_raw = self._safe_str(row.get("Channel Name") or row.get("channel") or "UNKNOWN")
            order_date = self._parse_business_order_datetime(row)
            if order_date is None:
                raise ValueError(
                    f"Missing business order timestamp for order {order_id}. "
                    "Expected Order Date field; refusing Created fallback."
                )
            order_date = validate_order_date(
                order_date.replace(tzinfo=None),
                order_id,
                context=validation_context,
            ).replace(tzinfo=timezone.utc)

            # Normalize status and channel to prevent case/whitespace fragmentation
            status_raw = self._safe_str(
                row.get("Sale Order Status") or row.get("status") or "CREATED"
            ).upper()
            channel_normalized = channel_raw.replace(" ", "_")

            # Extract financial fields from CSV data
            discount_val = self._safe_float(
                row.get("Discount") or row.get("discount") or 0
            )
            tax_val = self._safe_float(
                row.get("Tax Amount") or row.get("taxAmount")
                or row.get("Tax") or row.get("tax") or 0
            )
            refund_val = self._safe_float(
                row.get("Refund Amount") or row.get("refundAmount")
                or row.get("Refund") or row.get("refund") or 0
            )
            category_val = self._safe_str(
                row.get("Category") or row.get("category") or ""
            )

            payloads.append(
                {
                    "order_id": order_id,
                    "sale_order_item_code": sale_order_item_code,
                    "channel": channel_normalized,
                    "sku": self._safe_str(
                        row.get("Item SKU Code")
                        or row.get("skuCode")
                        or row.get("itemSku")
                    ),
                    "product_name": self._safe_str(
                        row.get("Item Details")
                        or row.get("itemDetails")
                        or row.get("itemTypeName")
                    ),
                    "qty": qty,
                    "selling_price": self._safe_float(row.get("Selling Price") or row.get("sellingPrice") or 0),
                    "discount": discount_val,
                    "tax": tax_val,
                    "refund": refund_val,
                    "category": category_val or None,
                    "status": status_raw,
                    "order_date": order_date,
                    "dispatch_date": self._parse_datetime(row.get("Dispatch Date") or row.get("dispatchdate")),
                    "delivery_date": self._parse_datetime(row.get("Delivery Date") or row.get("deliverydate")),
                    "cancel_date": self._parse_datetime(row.get("Cancel Date") or row.get("cancelDate")),
                    "return_date": self._parse_datetime(row.get("Return Date") or row.get("returnDate")),
                    "warehouse": self._safe_str(
                        row.get("Warehouse")
                        or row.get("Facility")
                        or row.get("godDown")
                    ),
                    "customer_name": self._safe_str(
                        row.get("Customer Name")
                        or row.get("customerName")
                        or row.get("shippingAddressName")
                    ),
                    "customer_city": self._safe_str(
                        row.get("Shipping Address City")
                        or row.get("shippingAddressCity")
                    ),
                    "display_order_code": self._safe_str(row.get("Display Order Code")),
                    "invoice_code": self._safe_str(row.get("Invoice Code")),
                    "invoice_created": self._safe_str(row.get("Invoice Created")),
                    "sale_order_item_status": self._safe_str(row.get("Sale Order Item Status")),
                    "shipping_provider": self._safe_str(row.get("Shipping provider") or row.get("Shipping Provider")),
                    "tracking_number": self._safe_str(row.get("Tracking Number")),
                    "payment_instrument": self._safe_str(row.get("Payment Instrument")),
                    "currency": self._safe_str(row.get("Currency")),
                    "currency_conversion_rate": self._safe_str(row.get("Currency Conversion Rate")),
                    "total_price": self._safe_str(row.get("Total Price")),
                    "mrp": self._safe_str(row.get("MRP")),
                    "cost_price": self._safe_str(row.get("Cost Price")),
                    "subtotal": self._safe_str(row.get("Subtotal")),
                    "tax_percent": self._safe_str(row.get("Tax %")),
                    "tax_value": self._safe_str(row.get("Tax Value")),
                    "shipping_charges": self._safe_str(row.get("Shipping Charges")),
                    "shipping_method_charges": self._safe_str(row.get("Shipping Method Charges")),
                    "cod_service_charges": self._safe_str(row.get("COD Service Charges")),
                    "channel_product_id": self._safe_str(row.get("Channel Product Id")),
                    "item_type_name": self._safe_str(row.get("Item Type Name")),
                    "item_type_color": self._safe_str(row.get("Item Type Color")),
                    "item_type_size": self._safe_str(row.get("Item Type Size")),
                    "item_type_brand": self._safe_str(row.get("Item Type Brand")),
                    "hsn_code": self._safe_str(row.get("HSN Code")),
                    "facility": self._safe_str(row.get("Facility")),
                    "bundle_sku_code_number": self._safe_str(row.get("Bundle SKU Code Number")),
                    "seller_sku_code": self._safe_str(row.get("Seller SKU Code")),
                    "item_type_ean": self._safe_str(row.get("Item Type EAN")),
                    "parent_sale_order_code": self._safe_str(row.get("Parent Sale Order Code")),
                    "extra_fields": self._normalized_extra_fields(row, known_keys=known_sales_keys),
                    "raw_data": row,
                    "updated_at": datetime.utcnow(),
                    "partition_month": self._partition_month_from_dt(order_date),
                }
            )

        if not payloads:
            return 0

        db = SessionLocal()
        try:
            chunk_size = 1000
            for start in range(0, len(payloads), chunk_size):
                chunk = payloads[start:start + chunk_size]
                stmt = pg_insert(SalesOrderRecord).values(chunk)
                upsert_stmt = stmt.on_conflict_do_update(
                    index_elements=["order_id", "sale_order_item_code"],
                    set_={
                        "channel": stmt.excluded.channel,
                        "sku": stmt.excluded.sku,
                        "product_name": stmt.excluded.product_name,
                        "qty": stmt.excluded.qty,
                        "selling_price": stmt.excluded.selling_price,
                        "discount": stmt.excluded.discount,
                        "tax": stmt.excluded.tax,
                        "refund": stmt.excluded.refund,
                        "category": stmt.excluded.category,
                        "status": stmt.excluded.status,
                        "order_date": stmt.excluded.order_date,
                        "dispatch_date": stmt.excluded.dispatch_date,
                        "delivery_date": stmt.excluded.delivery_date,
                        "cancel_date": stmt.excluded.cancel_date,
                        "return_date": stmt.excluded.return_date,
                        "warehouse": stmt.excluded.warehouse,
                        "customer_name": stmt.excluded.customer_name,
                        "customer_city": stmt.excluded.customer_city,
                        "display_order_code": stmt.excluded.display_order_code,
                        "invoice_code": stmt.excluded.invoice_code,
                        "invoice_created": stmt.excluded.invoice_created,
                        "sale_order_item_status": stmt.excluded.sale_order_item_status,
                        "shipping_provider": stmt.excluded.shipping_provider,
                        "tracking_number": stmt.excluded.tracking_number,
                        "payment_instrument": stmt.excluded.payment_instrument,
                        "currency": stmt.excluded.currency,
                        "currency_conversion_rate": stmt.excluded.currency_conversion_rate,
                        "total_price": stmt.excluded.total_price,
                        "mrp": stmt.excluded.mrp,
                        "cost_price": stmt.excluded.cost_price,
                        "subtotal": stmt.excluded.subtotal,
                        "tax_percent": stmt.excluded.tax_percent,
                        "tax_value": stmt.excluded.tax_value,
                        "shipping_charges": stmt.excluded.shipping_charges,
                        "shipping_method_charges": stmt.excluded.shipping_method_charges,
                        "cod_service_charges": stmt.excluded.cod_service_charges,
                        "channel_product_id": stmt.excluded.channel_product_id,
                        "item_type_name": stmt.excluded.item_type_name,
                        "item_type_color": stmt.excluded.item_type_color,
                        "item_type_size": stmt.excluded.item_type_size,
                        "item_type_brand": stmt.excluded.item_type_brand,
                        "hsn_code": stmt.excluded.hsn_code,
                        "facility": stmt.excluded.facility,
                        "bundle_sku_code_number": stmt.excluded.bundle_sku_code_number,
                        "seller_sku_code": stmt.excluded.seller_sku_code,
                        "item_type_ean": stmt.excluded.item_type_ean,
                        "parent_sale_order_code": stmt.excluded.parent_sale_order_code,
                        "extra_fields": stmt.excluded.extra_fields,
                        "raw_data": stmt.excluded.raw_data,
                        "updated_at": datetime.utcnow(),
                    },
                )
                db.execute(upsert_stmt)

            db.commit()
            return len(payloads)
        except Exception as exc:
            db.rollback()
            logger.warning(f"Export archival: failed to upsert normalized sales orders: {exc}")
            return 0
        finally:
            db.close()

    def _upsert_sales_order_rows_best_effort(
        self,
        rows: List[Dict[str, Any]],
        *,
        requested_from: datetime,
        requested_to: datetime,
        validation_context: str = "sync_import_best_effort",
    ) -> tuple[int, int]:
        """
        Best-effort upsert for a specific export window.

        - Prefers business order timestamp fields for order_date.
        - If business timestamp is missing, falls back to Created/created ONLY if the parsed
          Created timestamp lies within [requested_from, requested_to]. This avoids cross-day drift.

        Returns (upserted_rows, skipped_rows).
        """
        if not rows:
            return 0, 0

        req_from = requested_from if requested_from.tzinfo else requested_from.replace(tzinfo=timezone.utc)
        req_to = requested_to if requested_to.tzinfo else requested_to.replace(tzinfo=timezone.utc)

        payloads: List[Dict[str, Any]] = []
        known_sales_keys = {
            "sale_order_item_code", "display_order_code", "sale_order_code", "channel_name", "item_sku_code",
            "item_details", "selling_price", "discount", "tax", "refund", "category", "sale_order_status",
            "order_date_as_dd_mm_yyyy_hh_mm_ss", "dispatch_date", "delivery_date", "cancel_date", "return_date",
            "warehouse", "facility", "customer_name", "shipping_address_name", "shipping_address_city",
            "invoice_code", "invoice_created", "sale_order_item_status", "shipping_provider", "tracking_number",
            "payment_instrument", "currency", "currency_conversion_rate", "total_price", "mrp", "cost_price",
            "subtotal", "tax", "tax_value", "tax_percent", "shipping_charges", "shipping_method_charges",
            "cod_service_charges", "channel_product_id", "item_type_name", "item_type_color", "item_type_size",
            "item_type_brand", "hsn_code", "bundle_sku_code_number", "seller_sku_code", "item_type_ean",
            "parent_sale_order_code",
        }
        skipped = 0

        for raw_row in rows:
            errors = SchemaDriftChecker.validate_integrity("sales_order", raw_row)
            if errors:
                logger.warning(f"Integrity check failed for sales row {raw_row.get('Sale Order Code')}: {errors}")
            
            row = self._normalize_csv_row(raw_row)

            order_id = (
                self._clean_code(row.get("Sale Order Code"))
                or self._clean_code(row.get("saleOrderCode"))
                or self._clean_code(row.get("code"))
            )
            if not order_id:
                skipped += 1
                continue

            sale_order_item_code = (
                self._clean_code(row.get("Sale Order Item Code"))
                or self._clean_code(row.get("soicode"))
            )
            if not sale_order_item_code:
                sale_order_item_code = self._auto_sale_order_item_code(order_id, row)

            qty = self._safe_int(
                row.get("Quantity")
                or row.get("Qty")
                or row.get("QTY")
                or row.get("quantity")
                or 1,
                default=1,
            )
            if qty <= 0:
                qty = 1

            channel_raw = self._safe_str(row.get("Channel Name") or row.get("channel") or "UNKNOWN")
            order_date = self._parse_business_order_datetime(row)
            if order_date is None:
                created_candidate = row.get("Created") or row.get("created")
                created_dt = self._parse_datetime(created_candidate)
                if created_dt is None:
                    skipped += 1
                    continue
                raw_created = str(created_candidate).strip() if created_candidate is not None else ""
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
                # If Created is a naive string (no TZ suffix), treat it as IST-local (business system time)
                if raw_created and not TZ_SUFFIX_RE.search(raw_created):
                    created_dt = created_dt.replace(tzinfo=IST)
                created_utc = created_dt.astimezone(timezone.utc)
                if not (req_from <= created_utc <= req_to):
                    skipped += 1
                    continue
                order_date = created_utc

            # Store as naive UTC in DB
            validated = validate_order_date(
                order_date.astimezone(timezone.utc).replace(tzinfo=None),
                order_id,
                context=validation_context,
            )

            status_raw = self._safe_str(
                row.get("Sale Order Status") or row.get("status") or "CREATED"
            ).upper()
            channel_normalized = channel_raw.replace(" ", "_")

            payloads.append(
                {
                    "order_id": order_id,
                    "sale_order_item_code": sale_order_item_code,
                    "channel": channel_normalized,
                    "sku": self._safe_str(
                        row.get("Item SKU Code")
                        or row.get("skuCode")
                        or row.get("itemSku")
                    ),
                    "product_name": self._safe_str(
                        row.get("Item Details")
                        or row.get("itemDetails")
                        or row.get("itemTypeName")
                    ),
                    "qty": qty,
                    "selling_price": self._safe_float(row.get("Selling Price") or row.get("sellingPrice") or 0),
                    "discount": self._safe_float(row.get("Discount") or row.get("discount") or 0),
                    "tax": self._safe_float(
                        row.get("Tax Amount") or row.get("taxAmount")
                        or row.get("Tax") or row.get("tax") or 0
                    ),
                    "refund": self._safe_float(
                        row.get("Refund Amount") or row.get("refundAmount")
                        or row.get("Refund") or row.get("refund") or 0
                    ),
                    "category": (self._safe_str(row.get("Category") or row.get("category") or "") or None),
                    "status": status_raw,
                    "order_date": validated,
                    "dispatch_date": self._parse_datetime(row.get("Dispatch Date") or row.get("dispatchdate")),
                    "delivery_date": self._parse_datetime(row.get("Delivery Date") or row.get("deliverydate")),
                    "cancel_date": self._parse_datetime(row.get("Cancel Date") or row.get("cancelDate")),
                    "return_date": self._parse_datetime(row.get("Return Date") or row.get("returnDate")),
                    "warehouse": self._safe_str(
                        row.get("Warehouse")
                        or row.get("Facility")
                        or row.get("godDown")
                    ),
                    "customer_name": self._safe_str(
                        row.get("Customer Name")
                        or row.get("customerName")
                        or row.get("shippingAddressName")
                    ),
                    "customer_city": self._safe_str(
                        row.get("Shipping Address City")
                        or row.get("shippingAddressCity")
                    ),
                    "display_order_code": self._safe_str(row.get("Display Order Code")),
                    "invoice_code": self._safe_str(row.get("Invoice Code")),
                    "invoice_created": self._safe_str(row.get("Invoice Created")),
                    "sale_order_item_status": self._safe_str(row.get("Sale Order Item Status")),
                    "shipping_provider": self._safe_str(row.get("Shipping provider") or row.get("Shipping Provider")),
                    "tracking_number": self._safe_str(row.get("Tracking Number")),
                    "payment_instrument": self._safe_str(row.get("Payment Instrument")),
                    "currency": self._safe_str(row.get("Currency")),
                    "currency_conversion_rate": self._safe_str(row.get("Currency Conversion Rate")),
                    "total_price": self._safe_str(row.get("Total Price")),
                    "mrp": self._safe_str(row.get("MRP")),
                    "cost_price": self._safe_str(row.get("Cost Price")),
                    "subtotal": self._safe_str(row.get("Subtotal")),
                    "tax_percent": self._safe_str(row.get("Tax %")),
                    "tax_value": self._safe_str(row.get("Tax Value")),
                    "shipping_charges": self._safe_str(row.get("Shipping Charges")),
                    "shipping_method_charges": self._safe_str(row.get("Shipping Method Charges")),
                    "cod_service_charges": self._safe_str(row.get("COD Service Charges")),
                    "channel_product_id": self._safe_str(row.get("Channel Product Id")),
                    "item_type_name": self._safe_str(row.get("Item Type Name")),
                    "item_type_color": self._safe_str(row.get("Item Type Color")),
                    "item_type_size": self._safe_str(row.get("Item Type Size")),
                    "item_type_brand": self._safe_str(row.get("Item Type Brand")),
                    "hsn_code": self._safe_str(row.get("HSN Code")),
                    "facility": self._safe_str(row.get("Facility")),
                    "bundle_sku_code_number": self._safe_str(row.get("Bundle SKU Code Number")),
                    "seller_sku_code": self._safe_str(row.get("Seller SKU Code")),
                    "item_type_ean": self._safe_str(row.get("Item Type EAN")),
                    "parent_sale_order_code": self._safe_str(row.get("Parent Sale Order Code")),
                    "extra_fields": self._normalized_extra_fields(row, known_keys=known_sales_keys),
                    "raw_data": row,
                    "updated_at": datetime.utcnow(),
                    "partition_month": self._partition_month_from_dt(validated.replace(tzinfo=timezone.utc)),
                }
            )

        if not payloads:
            return 0, skipped

        db = SessionLocal()
        try:
            chunk_size = 1000
            for start in range(0, len(payloads), chunk_size):
                chunk = payloads[start:start + chunk_size]
                stmt = pg_insert(SalesOrderRecord).values(chunk)
                upsert_stmt = stmt.on_conflict_do_update(
                    index_elements=["order_id", "sale_order_item_code"],
                    set_={
                        "channel": stmt.excluded.channel,
                        "sku": stmt.excluded.sku,
                        "product_name": stmt.excluded.product_name,
                        "qty": stmt.excluded.qty,
                        "selling_price": stmt.excluded.selling_price,
                        "discount": stmt.excluded.discount,
                        "tax": stmt.excluded.tax,
                        "refund": stmt.excluded.refund,
                        "category": stmt.excluded.category,
                        "status": stmt.excluded.status,
                        "order_date": stmt.excluded.order_date,
                        "dispatch_date": stmt.excluded.dispatch_date,
                        "delivery_date": stmt.excluded.delivery_date,
                        "cancel_date": stmt.excluded.cancel_date,
                        "return_date": stmt.excluded.return_date,
                        "warehouse": stmt.excluded.warehouse,
                        "customer_name": stmt.excluded.customer_name,
                        "customer_city": stmt.excluded.customer_city,
                        "display_order_code": stmt.excluded.display_order_code,
                        "invoice_code": stmt.excluded.invoice_code,
                        "invoice_created": stmt.excluded.invoice_created,
                        "sale_order_item_status": stmt.excluded.sale_order_item_status,
                        "shipping_provider": stmt.excluded.shipping_provider,
                        "tracking_number": stmt.excluded.tracking_number,
                        "payment_instrument": stmt.excluded.payment_instrument,
                        "currency": stmt.excluded.currency,
                        "currency_conversion_rate": stmt.excluded.currency_conversion_rate,
                        "total_price": stmt.excluded.total_price,
                        "mrp": stmt.excluded.mrp,
                        "cost_price": stmt.excluded.cost_price,
                        "subtotal": stmt.excluded.subtotal,
                        "tax_percent": stmt.excluded.tax_percent,
                        "tax_value": stmt.excluded.tax_value,
                        "shipping_charges": stmt.excluded.shipping_charges,
                        "shipping_method_charges": stmt.excluded.shipping_method_charges,
                        "cod_service_charges": stmt.excluded.cod_service_charges,
                        "channel_product_id": stmt.excluded.channel_product_id,
                        "item_type_name": stmt.excluded.item_type_name,
                        "item_type_color": stmt.excluded.item_type_color,
                        "item_type_size": stmt.excluded.item_type_size,
                        "item_type_brand": stmt.excluded.item_type_brand,
                        "hsn_code": stmt.excluded.hsn_code,
                        "facility": stmt.excluded.facility,
                        "bundle_sku_code_number": stmt.excluded.bundle_sku_code_number,
                        "seller_sku_code": stmt.excluded.seller_sku_code,
                        "item_type_ean": stmt.excluded.item_type_ean,
                        "parent_sale_order_code": stmt.excluded.parent_sale_order_code,
                        "extra_fields": stmt.excluded.extra_fields,
                        "raw_data": stmt.excluded.raw_data,
                        "partition_month": stmt.excluded.partition_month,
                        "updated_at": datetime.utcnow(),
                    },
                )
                db.execute(upsert_stmt)
            db.commit()
            return len(payloads), skipped
        except Exception as exc:
            db.rollback()
            logger.warning(f"Export archival: failed to upsert normalized sales orders (best effort): {exc}")
            return 0, skipped
        finally:
            db.close()

    # Channel name standardization map
    CHANNEL_NORMALIZATION_MAP = {
        "amazon": "Amazon",
        "flipkart": "Flipkart",
        "myntra": "Myntra",
        "meesho": "Meesho",
        "meesho_26": "Meesho",
        "ajio": "Ajio",
        "snapdeal": "Snapdeal",
        "shopify": "Shopify",
        "woocommerce": "WooCommerce",
        "custom": "Custom",
        "amazon_in": "Amazon",
        "fk": "Flipkart",
        "mt": "Myntra",
        "firstcry_new": "Firstcry",
        "firstcry": "Firstcry",
        "nykaa_fashion_new": "Nykaa Fashion",
        "nykaa_fashion": "Nykaa Fashion",
        "nykaa": "Nykaa Fashion",
    }

    def _normalize_channel(self, channel_raw: str) -> str:
        """Normalize channel name to standard format."""
        if not channel_raw:
            return "UNKNOWN"

        # First, normalize by replacing spaces with underscores, then try mapping
        normalized_with_underscore = channel_raw.lower().strip().replace(" ", "_")
        if normalized_with_underscore in self.CHANNEL_NORMALIZATION_MAP:
            return self.CHANNEL_NORMALIZATION_MAP[normalized_with_underscore]

        # Try exact mapping without underscore replacement
        normalized_lower = channel_raw.lower().strip()
        if normalized_lower in self.CHANNEL_NORMALIZATION_MAP:
            return self.CHANNEL_NORMALIZATION_MAP[normalized_lower]

        # Fallback: title case and replace spaces with underscores
        return channel_raw.strip().title().replace(" ", "_")

    def _upsert_sales_return_rows(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0

        payload_map: Dict[str, Dict[str, Any]] = {}
        known_return_keys = {
            "date", "sale_order_number", "product_sku_code", "return_reason", "qty", "total", "sales", "return_type",
            "rp_code", "invoice_number", "channel_entry", "product_name", "unit_price", "currency", "cgst", "sgst",
            "igst", "utgst", "cess", "dispatch_date_cancellation_date", "customer_gstin", "channel_party_gstin",
            "product_hsn_code",
        }

        for raw_row in rows:
            errors = SchemaDriftChecker.validate_integrity("return_gst", raw_row)
            if errors:
                logger.warning(f"Integrity check failed for return row {raw_row.get('rpcode')}: {errors}")
                
            row = self._normalize_csv_row(raw_row)

            order_id = (
                self._safe_str(row.get("Sale Order Number"))
                or self._safe_str(row.get("Sale Order Code"))
                or self._safe_str(row.get("saleOrderCode"))
            )
            sku = (
                self._safe_str(row.get("Product SKU Code"))
                or self._safe_str(row.get("Product SKU"))
                or self._safe_str(row.get("productSKU"))
            )

            return_code = (
                self._safe_str(row.get("rpcode"))
                or self._safe_str(row.get("RP Code"))
                or self._safe_str(row.get("returnCode"))
            )
            row_hash = self._row_hash(row)
            if not return_code:
                return_code = f"RET-{row_hash[:24]}"

            # Normalize return_code to uppercase for consistent deduplication
            return_code = return_code.upper().strip() if return_code else return_code

            # Also get invoice number for better deduplication
            invoice_number = self._safe_str(row.get("Invoice number") or row.get("invoiceNumber"))

            # Extract base return code (remove :SKU suffix if present)
            base_return_code = return_code.split(":")[0] if return_code else ""

            # Use invoice number as primary deduplication key if available, otherwise return code
            dedup_key = invoice_number.upper().strip() if invoice_number else base_return_code

            # A single return code can contain multiple SKUs in one export,
            # so compose a deterministic per-line key for idempotent upserts.
            return_key_parts = [dedup_key]
            if sku:
                return_key_parts.append(sku.upper().strip())
            elif order_id:
                return_key_parts.append(order_id.upper().strip())
            else:
                return_key_parts.append(row_hash[:12])

            normalized_return_code = ":".join(return_key_parts)
            if len(normalized_return_code) > 120:
                normalized_return_code = f"{dedup_key[:80]}:{row_hash[:32]}"

            qty = self._safe_int(row.get("Qty") or row.get("QTY") or row.get("quantity") or 1, default=1)
            if qty <= 0:
                qty = 1

            # Use Refund Amount as primary source, fall back to Total/Sales only if not available
            refund_amount = self._safe_float(
                row.get("Refund Amount") or row.get("refundAmount") or
                row.get("Total") or row.get("total") or
                row.get("Sales") or 0
            )
            return_status = self._safe_str(row.get("Return Type") or row.get("returnType"))
            return_type_upper = return_status.upper()
            if "COURIER" in return_type_upper or "RTO" in return_type_upper:
                normalized_return_type = "RTO"
            elif (
                "CUSTOMER" in return_type_upper
                or "CIR" in return_type_upper
                or "REVERSE" in return_type_upper
            ):
                normalized_return_type = "CIR"
            else:
                normalized_return_type = return_status or "UNKNOWN"

            payload = payload_map.get(normalized_return_code)
            if payload is None:
                channel_raw = self._safe_str(
                    row.get("Channel entry")
                    or row.get("Channel Name")
                    or row.get("channelName")
                    or "UNKNOWN"
                )
                # Use improved channel normalization
                channel_normalized = self._normalize_channel(channel_raw)

                payload_map[normalized_return_code] = {
                    "return_code": normalized_return_code,
                    "order_id": order_id.upper().strip() if order_id else "UNKNOWN",
                    "sku": sku.upper().strip() if sku else "",
                    "reason": self._safe_str(
                        row.get("Return Reason")
                        or row.get("returnReason")
                        or row.get("narration")
                        or return_status
                    ),
                    "return_qty": qty,
                    "refund_amount": refund_amount,
                    "return_status": return_status,
                    "invoice_number": self._safe_str(row.get("Invoice number")),
                    "channel_entry": channel_raw,
                    "channel": channel_normalized,
                    "product_name": self._safe_str(row.get("Product Name")),
                    "unit_price": self._safe_str(row.get("Unit Price")),
                    "currency": self._safe_str(row.get("Currency")),
                    "sales": self._safe_str(row.get("Sales")),
                    "cgst": self._safe_str(row.get("CGST")),
                    "sgst": self._safe_str(row.get("SGST")),
                    "igst": self._safe_str(row.get("IGST")),
                    "utgst": self._safe_str(row.get("UTGST")),
                    "cess": self._safe_str(row.get("CESS")),
                    "dispatch_or_cancellation_date": self._safe_str(
                        row.get("Dispatch Date/Cancellation Date")
                        or row.get("Return Date")
                        or row.get("returnDate")
                        or row.get("Invoice Date")
                        or row.get("invoiceDate")
                    ),
                    "return_date": self._safe_str(
                        row.get("Date")
                        or row.get("date")
                        or row.get("Return Date")
                        or row.get("returnDate")
                    ),
                    "customer_gstin": self._safe_str(row.get("Customer GSTIN")),
                    "channel_party_gstin": self._safe_str(row.get("Channel_Party GSTIN")),
                    "product_hsn_code": self._safe_str(row.get("Product HSN Code")),
                    "return_type": normalized_return_type,
                    "raw_data": row,
                    "updated_at": datetime.utcnow(),
                }
            else:
                # Merge duplicate rows for the same return line key within the same batch.
                payload["return_qty"] = int(payload.get("return_qty", 0) or 0) + qty
                payload["refund_amount"] = float(payload.get("refund_amount", 0) or 0.0) + refund_amount
                payload["updated_at"] = datetime.utcnow()

        payloads: List[Dict[str, Any]] = list(payload_map.values())

        db = SessionLocal()
        try:
            chunk_size = 1000
            for start in range(0, len(payloads), chunk_size):
                chunk = payloads[start:start + chunk_size]
                stmt = pg_insert(SalesReturnRecord).values(chunk)
                upsert_stmt = stmt.on_conflict_do_update(
                    index_elements=["return_code"],
                    set_={
                        "order_id": stmt.excluded.order_id,
                        "sku": stmt.excluded.sku,
                        "reason": stmt.excluded.reason,
                        "return_qty": stmt.excluded.return_qty,
                        "refund_amount": stmt.excluded.refund_amount,
                        "return_status": stmt.excluded.return_status,
                        "invoice_number": stmt.excluded.invoice_number,
                        "channel_entry": stmt.excluded.channel_entry,
                        "channel": stmt.excluded.channel,
                        "product_name": stmt.excluded.product_name,
                        "unit_price": stmt.excluded.unit_price,
                        "currency": stmt.excluded.currency,
                        "sales": stmt.excluded.sales,
                        "cgst": stmt.excluded.cgst,
                        "sgst": stmt.excluded.sgst,
                        "igst": stmt.excluded.igst,
                        "utgst": stmt.excluded.utgst,
                        "cess": stmt.excluded.cess,
                        "dispatch_or_cancellation_date": stmt.excluded.dispatch_or_cancellation_date,
                        "return_date": stmt.excluded.return_date,
                        "customer_gstin": stmt.excluded.customer_gstin,
                        "channel_party_gstin": stmt.excluded.channel_party_gstin,
                        "product_hsn_code": stmt.excluded.product_hsn_code,
                        "return_type": stmt.excluded.return_type,
                        "raw_data": stmt.excluded.raw_data,
                        "updated_at": datetime.utcnow(),
                    },
                )
                db.execute(upsert_stmt)

            db.commit()
            return len(payloads)
        except Exception as exc:
            db.rollback()
            logger.warning(f"Export archival: failed to upsert normalized returns: {exc}")
            return 0
        finally:
            db.close()

    def _upsert_inventory_snapshot_rows(self, snapshots: List[Dict[str, Any]], facility_code: str) -> int:
        if not snapshots:
            return 0

        payloads: List[Dict[str, Any]] = []
        normalized_warehouse = self._safe_str(facility_code or "anthrilo")

        for snap in snapshots:
            sku = self._safe_str(snap.get("itemTypeSKU") or snap.get("sku"))
            if not sku:
                continue

            payloads.append(
                {
                    "sku": sku,
                    "warehouse": normalized_warehouse,
                    "available_qty": self._safe_int(snap.get("inventory"), default=0),
                    "reserved_qty": self._safe_int(
                        snap.get("openSale")
                        or snap.get("virtualInventory")
                        or snap.get("reservedInventory")
                        or 0,
                        default=0,
                    ),
                    "blocked_qty": self._safe_int(
                        snap.get("inventoryBlocked")
                        or snap.get("blockedInventory")
                        or snap.get("badInventory")
                        or 0,
                        default=0,
                    ),
                    "facility": self._safe_str(snap.get("Facility") or snap.get("facility") or facility_code),
                    "color": self._safe_str(snap.get("Color") or snap.get("color")),
                    "size": self._safe_str(snap.get("Size") or snap.get("size")),
                    "brand": self._safe_str(snap.get("Brand") or snap.get("brand")),
                    "category": self._safe_str(
                        snap.get("Category Name")
                        or snap.get("categoryName")
                        or snap.get("Category")
                    ),
                    "mrp": self._safe_float(
                        snap.get("MRP")
                        or snap.get("mrp")
                        or snap.get("maxRetailPrice")
                        or 0.0,
                        default=0.0,
                    ),
                    "cost_price": self._safe_float(
                        snap.get("Cost Price")
                        or snap.get("costPrice")
                        or 0.0,
                        default=0.0,
                    ),
                    "updated_at": datetime.utcnow(),
                }
            )

        if not payloads:
            return 0

        db = SessionLocal()
        try:
            stmt = pg_insert().values(payloads)
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=["sku", "warehouse"],
                set_={
                    "available_qty": stmt.excluded.available_qty,
                    "reserved_qty": stmt.excluded.reserved_qty,
                    "blocked_qty": stmt.excluded.blocked_qty,
                    "facility": func.coalesce(stmt.excluded.facility, .facility),
                    "color": func.coalesce(stmt.excluded.color, .color),
                    "size": func.coalesce(stmt.excluded.size, .size),
                    "brand": func.coalesce(stmt.excluded.brand, .brand),
                    "category": func.coalesce(stmt.excluded.category, .category),
                    "mrp": func.coalesce(stmt.excluded.mrp, .mrp),
                    "cost_price": func.coalesce(stmt.excluded.cost_price, .cost_price),
                    "updated_at": datetime.utcnow(),
                },
            )
            db.execute(upsert_stmt)
            db.commit()
            return len(payloads)
        except Exception as exc:
            db.rollback()
            logger.warning(f"Export archival: failed to upsert inventory snapshots: {exc}")
            return 0
        finally:
            db.close()


    async def _create_export_job(
        self, from_date: datetime, to_date: datetime
    ) -> Optional[str]:
        """
        Create a Unicommerce export job for Sale Orders.
        Returns the jobCode on success, None on failure.
        Retries up to 3 times on transient errors (timeout, 400, 5xx).
        If UC reports a duplicate job (error 100014), offset the date range
        slightly and retry so UC treats it as a new configuration.
        """
        url = f"{self.base_url}/export/job/create"

        # Convert dates to epoch milliseconds for the filter
        start_ms = int(from_date.timestamp() * 1000)
        end_ms = int(to_date.timestamp() * 1000)

        def _build_payload(s_ms: int, e_ms: int) -> dict:
            return {
                "exportJobTypeName": "Sale Orders",
                "frequency": "ONETIME",
                "exportColums": self.EXPORT_COLUMNS,
                "exportFilters": [
                    {
                        "id": "addedOn",
                        "dateRange": {
                            "start": s_ms,
                            "end": e_ms,
                        },
                    }
                ],
            }

        payload = _build_payload(start_ms, end_ms)

        MAX_RETRIES = 3
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    headers = await self._get_headers()
                    headers["Facility"] = "anthrilo"

                    response = await client.post(url, json=payload, headers=headers)

                    # Handle auth failures with token refresh/re-auth
                    if response.status_code in (401, 403):
                        try:
                            auth_error_body = response.json()
                        except Exception:
                            auth_error_body = response.text[:500]
                        logger.warning(
                            f"Export: Job creation auth HTTP {response.status_code} "
                            f"attempt {attempt}/{MAX_RETRIES}: {auth_error_body}"
                        )
                        self.token_manager.invalidate_token()
                        await self.token_manager.get_valid_token()
                        headers = await self._get_headers()
                        headers["Facility"] = "anthrilo"
                        response = await client.post(url, json=payload, headers=headers)

                        if response.status_code in (401, 403):
                            if attempt < MAX_RETRIES:
                                await asyncio.sleep(3 * attempt)
                                continue
                            try:
                                auth_error_body = response.json()
                            except Exception:
                                auth_error_body = response.text[:500]
                            logger.error(
                                f"Export: Job creation auth still failing HTTP {response.status_code}: "
                                f"{auth_error_body}"
                            )
                            return None

                    # Handle 400 - may be transient; retry with fresh token
                    if response.status_code == 400:
                        try:
                            error_body = response.json()
                        except Exception:
                            error_body = response.text[:500]
                        logger.warning(
                            f"Export: Job creation HTTP 400 attempt {attempt}/{MAX_RETRIES}: {error_body}"
                        )
                        if attempt < MAX_RETRIES:
                            self.token_manager.invalidate_token()
                            await asyncio.sleep(3 * attempt)
                            continue
                        return None

                    # Handle 5xx
                    if response.status_code >= 500:
                        logger.warning(
                            f"Export: Job creation HTTP {response.status_code} attempt {attempt}/{MAX_RETRIES}"
                        )
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(3 * attempt)
                            continue
                        return None

                    # Other errors
                    if response.status_code >= 400:
                        try:
                            error_body = response.json()
                        except Exception:
                            error_body = response.text[:500]
                        logger.error(
                            f"Export: Job creation HTTP {response.status_code}: {error_body}"
                        )
                        return None

                    data = response.json()

                    if data.get("successful"):
                        job_code = data.get("jobCode")
                        logger.info(f"Export: Job created successfully {job_code}")
                        return job_code
                    else:
                        errors = data.get("errors", [])
                        msg = data.get("message", "Unknown error")

                        # UC error 100014: an export job is already running
                        already_running = any(
                            str(e.get("code", "")) == "100014"
                            or "already" in str(e.get("description", "")).lower()
                            for e in errors
                        ) if errors else "already" in msg.lower()

                        if already_running:
                            logger.warning(
                                f"Export: Duplicate job detected (100014), offsetting date range to bypass"
                            )
                            # Offset start_ms by 1ms each retry to create a "new" configuration
                            for retry in range(5):
                                offset_start = start_ms + retry + 1
                                new_payload = _build_payload(offset_start, end_ms)
                                await asyncio.sleep(2)
                                headers = await self._get_headers()
                                headers["Facility"] = "anthrilo"
                                retry_resp = await client.post(url, json=new_payload, headers=headers)
                                retry_data = retry_resp.json()
                                if retry_data.get("successful"):
                                    jc = retry_data.get("jobCode")
                                    logger.info(f"Export: Job created on offset retry {retry+1}: {jc}")
                                    return jc
                                r_errors = retry_data.get("errors", [])
                                logger.info(f"Export: Offset retry {retry+1}/5 — {r_errors}")
                            logger.error("Export: Job still busy after all retries")
                            return None

                        logger.error(f"Export: Job creation failed: {msg} | errors={errors}")
                        return None

            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as e:
                logger.warning(
                    f"Export: Job creation timeout attempt {attempt}/{MAX_RETRIES}: {type(e).__name__}"
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(3 * attempt)
                    continue
                return None

            except Exception as e:
                logger.error(f"Export: Job creation exception: {e}", exc_info=True)
                return None

        return None

    async def _poll_export_status(
        self, job_code: str, max_wait: int = None
    ) -> Optional[str]:
        """Poll export job until complete; return download URL or None.

        Individual poll requests that timeout or fail are retried — only
        persistent failures or the overall max_wait budget cause a return None.
        """
        if max_wait is None:
            max_wait = self.EXPORT_MAX_POLL_SECONDS

        url = f"{self.base_url}/export/job/status"
        payload = {"jobCode": job_code}

        start_time = time_module.time()
        poll_interval = self.EXPORT_INITIAL_POLL_INTERVAL
        no_filepath_retries = 0
        MAX_NO_FILEPATH_RETRIES = self.export_max_no_filepath_retries
        consecutive_errors = 0
        MAX_CONSECUTIVE_ERRORS = self.export_max_consecutive_poll_errors

        while (time_module.time() - start_time) < max_wait:
            elapsed = time_module.time() - start_time
            try:
                # Fresh client per request avoids stale connection pool issues
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    headers = await self._get_headers()
                    headers["Facility"] = "anthrilo"

                    response = await client.post(url, json=payload, headers=headers)

                    if response.status_code in (401, 403):
                        self.token_manager.invalidate_token()
                        await self.token_manager.get_valid_token()
                        headers = await self._get_headers()
                        headers["Facility"] = "anthrilo"
                        response = await client.post(url, json=payload, headers=headers)

                    response.raise_for_status()

                # Successful request — reset error counter
                consecutive_errors = 0
                data = response.json()

                if data.get("successful"):
                    status = str(data.get("status", "")).strip().upper()
                    file_path = self._extract_export_file_path(data)

                    if status == "COMPLETE":
                        if file_path:
                            logger.info(
                                f"Export: Job {job_code} COMPLETE in {elapsed:.1f}s {file_path}"
                            )
                            return file_path
                        else:
                            no_filepath_retries += 1
                            should_retry = (
                                no_filepath_retries <= MAX_NO_FILEPATH_RETRIES
                                or elapsed < self.export_status_retry_grace_seconds
                            )
                            if should_retry:
                                logger.warning(
                                    f"Export: Job {job_code} COMPLETE but no filePath "
                                    f"(attempt {no_filepath_retries}/{MAX_NO_FILEPATH_RETRIES}, {elapsed:.1f}s)"
                                )
                                await asyncio.sleep(5)
                                continue
                            else:
                                logger.error(
                                    f"Export: Job {job_code} COMPLETE but no filePath after "
                                    f"{MAX_NO_FILEPATH_RETRIES} retries ({elapsed:.1f}s). "
                                    "Treating as empty export window."
                                )
                                return ""
                    elif status in ("FAILED", "CANCELLED", "ABORTED"):
                        logger.error(
                            f"Export: Job {job_code} {status} after {elapsed:.1f}s"
                        )
                        return None
                    else:
                        logger.debug(
                            f"Export: Job {job_code} status={status}, "
                            f"elapsed={elapsed:.1f}s, next poll in {poll_interval:.1f}s"
                        )
                else:
                    status = str(data.get("status", "")).strip().upper()
                    if status in {"QUEUED", "PENDING", "PROCESSING", "IN_PROGRESS", "RUNNING"}:
                        logger.debug(
                            f"Export: Job {job_code} status={status}, "
                            f"elapsed={elapsed:.1f}s, next poll in {poll_interval:.1f}s"
                        )
                    else:
                        logger.warning(
                            f"Export: Status check not successful for {job_code}: "
                            f"status={status or 'unknown'} message={data.get('message', '')}"
                        )

            except (
                httpx.ReadTimeout,
                httpx.ConnectTimeout,
                httpx.PoolTimeout,
                httpx.TransportError,
            ) as e:
                consecutive_errors += 1
                logger.warning(
                    f"Export: Poll transport error for {job_code} ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}, "
                    f"{elapsed:.0f}s elapsed): {type(e).__name__}"
                )
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.error(
                        f"Export: Job {job_code} — {MAX_CONSECUTIVE_ERRORS} consecutive "
                        f"transport errors, giving up after {elapsed:.0f}s"
                    )
                    return None
                # Wait longer after a timeout before retrying
                await asyncio.sleep(poll_interval * 2)
                continue

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code if e.response is not None else None
                if status_code in {429, 500, 502, 503, 504}:
                    consecutive_errors += 1
                    logger.warning(
                        f"Export: Poll transient HTTP {status_code} for {job_code} "
                        f"({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS})"
                    )
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logger.error(
                            f"Export: Job {job_code} — {MAX_CONSECUTIVE_ERRORS} consecutive "
                            f"transient HTTP errors, giving up after {elapsed:.0f}s"
                        )
                        return None
                    await asyncio.sleep(poll_interval * 2)
                    continue

                logger.error(
                    f"Export: Poll non-retryable HTTP {status_code} for {job_code}, "
                    f"aborting after {elapsed:.0f}s"
                )
                return None

            except Exception as e:
                consecutive_errors += 1
                logger.warning(
                    f"Export: Poll error for {job_code} ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}"
                )
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.error(
                        f"Export: Job {job_code} — {MAX_CONSECUTIVE_ERRORS} consecutive "
                        f"errors, giving up after {elapsed:.0f}s"
                    )
                    return None
                await asyncio.sleep(poll_interval)
                continue

            await asyncio.sleep(poll_interval)
            poll_interval = min(
                poll_interval * self.EXPORT_POLL_BACKOFF,
                self.EXPORT_MAX_POLL_INTERVAL,
            )

        elapsed = time_module.time() - start_time
        logger.error(f"Export: Job {job_code} timed out after {elapsed:.0f}s")
        return None

    async def _download_parse_export(
        self,
        download_url: str,
        include_rows: bool = False,
    ) -> Any:
        """Download export CSV and group rows by order code into order dicts."""
        try:
            csv_text = await self._download_csv_text(download_url, label="Export")
            if csv_text is None:
                logger.error("Export: Failed to download CSV after retries")
                if include_rows:
                    return [], [], []
                return []

            if not csv_text or not csv_text.strip():
                logger.warning("Export: Downloaded CSV is empty")
                if include_rows:
                    return [], [], []
                return []

            reader = csv.DictReader(io.StringIO(csv_text))
            fieldnames = reader.fieldnames or []
            logger.info(f"Export: CSV columns ({len(fieldnames)}): {fieldnames}")

            # Group rows by order code nested order structure
            orders_map: Dict[str, Dict] = {}
            raw_rows: List[Dict[str, Any]] = []
            row_count = 0
            fabric_skipped = 0

            for row in reader:
                row_count += 1
                if include_rows:
                    raw_rows.append(dict(row))

                # Skip items with excluded categories (e.g. FABRIC)
                item_category = (
                    row.get("Category")
                    or row.get("category")
                    or row.get("Item Type Category")
                    or row.get("categoryCode")
                    or ""
                ).strip().upper()
                if item_category in self.EXCLUDED_CATEGORIES:
                    fabric_skipped += 1
                    continue

                # Order code
                order_code = (
                    row.get("Sale Order Code")
                    or row.get("saleOrderCode")
                    or row.get("code")
                    or ""
                ).strip()
                if not order_code:
                    continue

                if order_code not in orders_map:
                    # Channel name: normalize spaces underscores for consistency
                    channel_raw = (
                        row.get("Channel Name")
                        or row.get("channel")
                        or "UNKNOWN"
                    ).strip()
                    channel = channel_raw.replace(" ", "_")

                    # COD: "1" = COD, "0" = Prepaid
                    cod_raw = (
                        row.get("COD")
                        or row.get("cod")
                        or "0"
                    ).strip()
                    is_cod = cod_raw in ("1", "true", "True", "yes")

                    orders_map[order_code] = {
                        "code": order_code,
                        "displayOrderCode": order_code,
                        "channel": channel,
                        "status": (
                            row.get("Sale Order Status")
                            or row.get("status")
                            or ""
                        ).strip(),
                        "created": (
                            row.get("Created")
                            or row.get("created")
                            or ""
                        ).strip(),
                        "updated": (
                            row.get("Updated")
                            or row.get("updated")
                            or ""
                        ).strip(),
                        "cod": is_cod,
                        "cashOnDelivery": is_cod,
                        "shippingMethod": (
                            row.get("Shipping Method")
                            or row.get("shippingMethod")
                            or ""
                        ).strip(),
                        "collectableAmount": 0.0,
                        "saleOrderItems": [],
                    }

                # Parse item fields â€” each CSV row = 1 unit
                try:
                    selling_price = float(
                        row.get("Selling Price")
                        or row.get("sellingPrice")
                        or 0
                    )
                except (ValueError, TypeError):
                    selling_price = 0.0

                try:
                    mrp = float(
                        row.get("MRP")
                        or row.get("maxRetailPrice")
                        or 0
                    )
                except (ValueError, TypeError):
                    mrp = 0.0

                try:
                    discount = float(
                        row.get("Discount")
                        or row.get("discount")
                        or 0
                    )
                except (ValueError, TypeError):
                    discount = 0.0

                sku_code = (
                    row.get("Item SKU Code")
                    or row.get("skuCode")
                    or row.get("itemSku")
                    or ""
                ).strip()

                item_details = (
                    row.get("Item Details")
                    or row.get("itemDetails")
                    or ""
                ).strip()

                item_code = (
                    row.get("Sale Order Item Code")
                    or row.get("soicode")
                    or ""
                ).strip()

                item_type_name = (
                    row.get("Item Type Name")
                    or row.get("itemTypeName")
                    or ""
                ).strip()

                size = (
                    row.get("Size")
                    or row.get("size")
                    or ""
                ).strip()

                bundle_sku_code_number = (
                    row.get("Bundle SKU Code Number")
                    or row.get("Bundle SKU Code Number ")
                    or row.get("Bundle Sku Code Number")
                    or row.get("bundle sku code number")
                    or row.get("Bundle SKU Code")
                    or row.get("bundleSkuCode")
                    or row.get("bundleSkuCodeNumber")
                    or ""
                ).strip()

                channel_product_id = (
                    row.get("Channel Product Id")
                    or row.get("Channel Product ID")
                    or row.get("channelProductId")
                    or ""
                ).strip()

                if not bundle_sku_code_number:
                    for k, v in row.items():
                        nk = str(k or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
                        if nk in {
                            "bundleskucodenumber",
                            "bundleskucode",
                        }:
                            bundle_sku_code_number = str(v or "").strip()
                            if bundle_sku_code_number:
                                break

                # Parse size from item type name if not in a dedicated column
                # Handles: "SET - AQUA - 12-14 YEARS", "DRESS - OFF WHITE - 6-12 MONTHS"
                resolved_name = item_type_name or item_details or sku_code
                if not size and resolved_name:
                    size_match = re.search(
                        r'[\s\-]*(\d+(?:\s*-\s*\d+)?\s*(?:YEARS|MONTHS|YRS|MOS|Y|M))\s*$',
                        resolved_name, re.IGNORECASE,
                    )
                    if size_match:
                        size = size_match.group(1).strip()
                        resolved_name = resolved_name[:size_match.start()].rstrip(' -')

                item = {
                    "code": item_code,
                    "itemSku": sku_code,
                    "itemName": item_details or sku_code,
                    "itemTypeName": resolved_name,
                    "size": size,
                    "bundleSkuCodeNumber": bundle_sku_code_number,
                    "channelProductId": channel_product_id,
                    "sellingPrice": selling_price,
                    "maxRetailPrice": mrp,
                    "quantity": 1,  # Each CSV row = 1 unit
                    "discount": discount,
                }

                orders_map[order_code]["saleOrderItems"].append(item)

            # Remove orders with 0 items after filtering
            orders = [o for o in orders_map.values() if o["saleOrderItems"]]
            total_items = sum(len(o["saleOrderItems"]) for o in orders)

            if fabric_skipped:
                logger.info(
                    f"Export: Excluded {fabric_skipped} FABRIC category rows"
                )
            logger.info(
                f"Export: Parsed {row_count} CSV rows "
                f"{len(orders)} orders, {total_items} items"
            )
            if include_rows:
                return orders, raw_rows, fieldnames
            return orders

        except Exception as e:
            logger.error(f"Export: Download/parse failed: {e}", exc_info=True)
            if include_rows:
                return [], [], []
            return []

    async def fetch_orders_via_export(
        self, from_date: datetime, to_date: datetime
    ) -> Dict[str, Any]:
        """Fetch orders via export job API (serialized with lock)."""
        async with self._export_lock:
            return await self._fetch_orders_via_export_inner(from_date, to_date)

    async def _fetch_orders_via_export_inner(
        self, from_date: datetime, to_date: datetime
    ) -> Dict[str, Any]:
        """Inner export fetch — runs under _export_lock."""
        start_time = time_module.time()
        logger.info("Starting export job fetch")
        logger.info(f"  Range: {from_date.isoformat()} {to_date.isoformat()}")

        sync_log_id = self._create_sync_log_record(
            sync_type="export_job",
            entity="sale_orders",
            details={
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
            },
        )

        export_job_id = self._create_export_job_record(
            export_type="sale_orders",
            requested_from=from_date,
            requested_to=to_date,
            requested_columns=self.EXPORT_COLUMNS,
        )

        try:
            # Step 1: Create export job
            job_code = await self._create_export_job(from_date, to_date)
            create_time = time_module.time() - start_time

            if not job_code:
                logger.error("Export: Job creation failed")
                self._update_export_job_record(
                    export_job_id,
                    status="failed",
                    error_message="Export job creation failed",
                    completed_at=datetime.utcnow(),
                )
                self._update_sync_log_record(
                    sync_log_id,
                    status="failed",
                    failed_count=1,
                    error_message="Export job creation failed",
                    completed_at=datetime.utcnow(),
                )
                return {
                    "successful": False,
                    "error": "Export job creation failed",
                    "orders": [],
                    "totalRecords": 0,
                }

            self._update_export_job_record(
                export_job_id,
                job_code=job_code,
                status="running",
            )

            logger.info(f"  Step 1 done in {create_time:.1f}s job={job_code}")

            # Step 2: Poll until complete
            download_url = await self._poll_export_status(job_code)
            poll_time = time_module.time() - start_time - create_time

            if download_url is None:
                logger.error("Export: Job failed or timed out")
                self._update_export_job_record(
                    export_job_id,
                    status="failed",
                    error_message="Export job timed out or failed",
                    completed_at=datetime.utcnow(),
                )
                self._update_sync_log_record(
                    sync_log_id,
                    status="failed",
                    failed_count=1,
                    error_message="Export job timed out or failed",
                    completed_at=datetime.utcnow(),
                )
                return {
                    "successful": False,
                    "error": "Export job timed out or failed",
                    "orders": [],
                    "totalRecords": 0,
                }

            logger.info(f"  Step 2 done in {poll_time:.1f}s file ready")

            if download_url == "":
                logger.info(
                    "Export: Completed with no filePath; treating as empty window %s -> %s",
                    from_date.isoformat(),
                    to_date.isoformat(),
                )
                self._update_export_job_record(
                    export_job_id,
                    status="completed",
                    download_url=None,
                    total_csv_rows=0,
                    parsed_entities=0,
                    completed_at=datetime.utcnow(),
                )
                self._update_sync_log_record(
                    sync_log_id,
                    status="completed",
                    processed_count=0,
                    failed_count=0,
                    completed_at=datetime.utcnow(),
                    details={
                        "from_date": from_date.isoformat(),
                        "to_date": to_date.isoformat(),
                        "export_job_id": export_job_id,
                        "archived_rows": 0,
                        "normalized_rows": 0,
                        "total_csv_rows": 0,
                        "empty_window": True,
                    },
                )
                return {
                    "successful": True,
                    "orders": [],
                    "totalRecords": 0,
                    "export_job_id": export_job_id,
                    "archived_rows": 0,
                    "normalized_rows": 0,
                    "phase1_time": round(create_time + poll_time, 2),
                    "phase2_time": 0,
                    "total_time": round(time_module.time() - start_time, 2),
                    "method": "export_job",
                    "failed_codes": [],
                    "retry_recovered": 0,
                    "phase1_dedup": 0,
                    "phase2_dedup": 0,
                }

            # Step 3: Download and parse CSV
            orders, raw_rows, csv_headers = await self._download_parse_export(
                download_url,
                include_rows=True,
            )

            archived_rows, file_checksum = self._archive_export_rows(
                export_job_id,
                "sale_orders",
                raw_rows,
            )
            normalization_error = None
            normalized_rows = 0
            skipped_rows = 0
            try:
                normalized_rows, skipped_rows = self._upsert_sales_order_rows_best_effort(
                    raw_rows,
                    requested_from=from_date,
                    requested_to=to_date,
                )
            except Exception as exc:
                normalization_error = str(exc)
                logger.warning(
                    "Export archival: best-effort upsert failed: %s",
                    exc,
                )

            self._update_export_job_record(
                export_job_id,
                status="completed",
                download_url=download_url,
                csv_headers=csv_headers,
                file_checksum=file_checksum,
                total_csv_rows=len(raw_rows),
                parsed_entities=normalized_rows,
                error_message=normalization_error,
                completed_at=datetime.utcnow(),
            )

            self._update_sync_log_record(
                sync_log_id,
                status="completed",
                processed_count=normalized_rows,
                failed_count=max(0, len(raw_rows) - normalized_rows),
                completed_at=datetime.utcnow(),
                details={
                    "from_date": from_date.isoformat(),
                    "to_date": to_date.isoformat(),
                    "export_job_id": export_job_id,
                    "archived_rows": archived_rows,
                    "normalized_rows": normalized_rows,
                    "skipped_rows": skipped_rows,
                    "total_csv_rows": len(raw_rows),
                    "normalization_error": normalization_error,
                },
            )

            download_time = time_module.time() - start_time - create_time - poll_time
            total_time = time_module.time() - start_time

            if not orders:
                if not raw_rows:
                    logger.info(
                        "Export: No sale-order rows for range %s -> %s (likely empty chunk)",
                        from_date.isoformat(),
                        to_date.isoformat(),
                    )
                elif normalized_rows > 0:
                    logger.info(
                        "Export: Grouped orders=0 but normalized rows=%s for range %s -> %s",
                        normalized_rows,
                        from_date.isoformat(),
                        to_date.isoformat(),
                    )
                else:
                    logger.warning(
                        "Export: CSV rows present but no grouped/normalized orders for range %s -> %s; check headers/mapping",
                        from_date.isoformat(),
                        to_date.isoformat(),
                    )

            logger.info(
                f"  Step 3 done in {download_time:.1f}s {len(orders)} orders"
            )
            logger.info(
                f"Export done: {len(orders)} orders in {total_time:.1f}s total"
            )

            return {
                "successful": True,
                "orders": orders,
                "totalRecords": len(orders),
                "export_job_id": export_job_id,
                "archived_rows": archived_rows,
                "normalized_rows": normalized_rows,
                "phase1_time": round(create_time + poll_time, 2),
                "phase2_time": round(download_time, 2),
                "total_time": round(total_time, 2),
                "method": "export_job",
                "failed_codes": [],
                "retry_recovered": 0,
                "phase1_dedup": 0,
                "phase2_dedup": 0,
            }

        except Exception as e:
            total_time = time_module.time() - start_time
            logger.error(
                f"Export: Failed after {total_time:.1f}s: {e}", exc_info=True
            )
            self._update_export_job_record(
                export_job_id,
                status="failed",
                error_message=f"Export failed: {str(e)}",
                completed_at=datetime.utcnow(),
            )
            self._update_sync_log_record(
                sync_log_id,
                status="failed",
                failed_count=1,
                error_message=f"Export failed: {str(e)}",
                completed_at=datetime.utcnow(),
            )
            return {
                "successful": False,
                "error": f"Export failed: {str(e)}",
                "orders": [],
                "totalRecords": 0,
            }

    # Date range helpers

    def get_today_range(self) -> Tuple[datetime, datetime]:
        """Get today's date range in UTC (IST 00:00:00 to current time - 1 min)"""
        now_ist = datetime.now(IST)
        start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        end_ist = now_ist - timedelta(minutes=1)
        return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)

    def get_yesterday_range(self) -> Tuple[datetime, datetime]:
        """Get yesterday's date range in UTC (IST 00:00:00 to 23:59:59)"""
        now_ist = datetime.now(IST)
        yesterday_ist = now_ist - timedelta(days=1)
        start_ist = yesterday_ist.replace(
            hour=0, minute=0, second=0, microsecond=0)
        end_ist = yesterday_ist.replace(
            hour=23, minute=59, second=59, microsecond=0)
        return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)

    def get_last_n_days_range(self, days: int) -> Tuple[datetime, datetime]:
        """Get last N complete days (not including today)."""
        now_ist = datetime.now(IST)
        yesterday_ist = now_ist - timedelta(days=1)
        start_ist = now_ist - timedelta(days=days)
        start = start_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        end = yesterday_ist.replace(
            hour=23, minute=59, second=59, microsecond=0)
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


    async def fetch_all_orders_with_revenue(
        self,
        from_date: datetime,
        to_date: datetime,
        max_orders: int = 100000
    ) -> Dict[str, Any]:
        """
        Fetch all orders with revenue data using Export Job API.

        Uses Export Job API exclusively (~3 API calls, any volume).
        Items with category FABRIC are excluded during CSV parsing.

        Returns dict with:
            successful, orders, totalRecords, phase1_time, phase2_time,
            total_time, failed_codes, retry_recovered, method, etc.
        """
        return await self.fetch_orders_via_export(from_date, to_date)

    # Revenue helpers

    @staticmethod
    def _extract_date_key(created_raw) -> Optional[str]:
        """Extract a YYYY-MM-DD date key from epoch ms, ISO string, or date string."""
        if created_raw is None or created_raw == "":
            return None

        val = str(created_raw).strip()
        if not val:
            return None

        # Check if it's a purely numeric value epoch ms or epoch seconds
        try:
            numeric = float(val)
            # Epoch milliseconds (>= 1e12) vs seconds (< 1e12)
            if numeric > 1e12:
                numeric = numeric / 1000.0
            dt = datetime.fromtimestamp(numeric, tz=IST)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OverflowError, OSError):
            pass

        # Already a proper YYYY-MM-DD or YYYY-MM-DD ... string
        if len(val) >= 10 and val[4] == "-" and val[7] == "-":
            return val[:10]

        # Try common datetime parsing as fallback
        for fmt in ("%d %b %Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
            try:
                dt = datetime.strptime(val, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        logger.debug(f"Could not parse created date: {val!r}")
        return None

    def calculate_order_revenue(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate revenue for a single order from sellingPrice, excluding cancelled/returned.
        """
        def safe_float(value, default=0.0) -> float:
            if value is None:
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default

        order_code = order.get("code", "UNKNOWN")
        status = (order.get("status") or "").upper()
        channel = order.get("channel", "UNKNOWN")
        created = order.get("created") or order.get("displayOrderDateTime")
        items = order.get("saleOrderItems", [])

        total_selling_price = 0.0
        total_discount = 0.0
        total_tax = 0.0
        total_refund = 0.0
        item_count = len(items)
        # Get pre-calculated quantity, or compute from items
        total_quantity = order.get("totalQuantity", 0)
        if total_quantity == 0 and items:
            total_quantity = sum(
                int(safe_float(item.get("quantity", 1)) or 1)
                for item in items
            )

        for item in items:
            selling_price = safe_float(item.get("sellingPrice", 0))
            quantity = safe_float(item.get("quantity", 1))
            # Export/API item rows already carry the row total in sellingPrice.
            item_revenue = selling_price
            total_selling_price += item_revenue

            # Multiply by quantity for per-item values
            total_discount += safe_float(item.get("discount", 0)) * quantity
            total_tax += safe_float(item.get("taxAmount", 0)) * quantity
            total_refund += safe_float(item.get("refundAmount", 0)) * quantity

        include_in_revenue = status not in self.EXCLUDED_STATUSES
        excluded_reason = f"Status: {status}" if status in self.EXCLUDED_STATUSES else None

        net_revenue = 0.0
        if include_in_revenue:
            net_revenue = total_selling_price - total_refund

        return {
            "order_code": order_code,
            "status": status,
            "channel": channel,
            "created": created,
            "selling_price": round(total_selling_price, 2),
            "discount": round(total_discount, 2),
            "tax": round(total_tax, 2),
            "refund": round(total_refund, 2),
            "net_revenue": round(net_revenue, 2),
            "include_in_revenue": include_in_revenue,
            "excluded_reason": excluded_reason,
            "item_count": item_count,
            "quantity": total_quantity,
        }

    # Aggregation with reconciliation
    def aggregate_orders(self, orders: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregate orders into summary statistics with channel reconciliation.
        """
        total_orders = len(orders)
        valid_orders = 0
        excluded_orders = 0

        total_revenue = 0.0
        total_discount = 0.0
        total_tax = 0.0
        total_refund = 0.0
        total_items = 0

        channel_stats: Dict[str, Dict[str, Any]] = {}
        status_stats: Dict[str, int] = {}
        daily_stats: Dict[str, Dict[str, Any]] = {}  # day-level aggregation

        # Single-pass aggregation
        for order in orders:
            calc = self.calculate_order_revenue(order)

            status = calc["status"]
            status_stats[status] = status_stats.get(status, 0) + 1

            total_discount += calc["discount"]
            total_tax += calc["tax"]
            total_refund += calc["refund"]

            if calc["include_in_revenue"]:
                valid_orders += 1
                total_revenue += calc["net_revenue"]
                total_items += calc.get("quantity", 0)  # Only count valid orders' items

                channel = calc["channel"]
                if channel not in channel_stats:
                    # Initialize channel stats with orders, revenue, and items
                    channel_stats[channel] = {
                        "orders": 0, "revenue": 0.0, "items": 0}
                channel_stats[channel]["orders"] += 1
                channel_stats[channel]["revenue"] += calc["net_revenue"]
                # Track items per channel
                channel_stats[channel]["items"] += calc.get("quantity", 0)

                # Daily breakdown (YYYY-MM-DD)
                day_key = self._extract_date_key(calc.get("created"))
                if day_key:
                    if day_key not in daily_stats:
                        daily_stats[day_key] = {
                            "date": day_key, "orders": 0, "revenue": 0.0, "items": 0}
                    daily_stats[day_key]["orders"] += 1
                    daily_stats[day_key]["revenue"] += calc["net_revenue"]
                    daily_stats[day_key]["items"] += calc.get("quantity", 0)
            else:
                excluded_orders += 1

        channel_total = sum(ch["revenue"] for ch in channel_stats.values())
        reconciliation_passed = abs(channel_total - total_revenue) < 0.01

        if not reconciliation_passed:
            logger.error(
                f"REVENUE RECONCILIATION FAILED: "
                f"Channel sum={channel_total:.2f}, Total={total_revenue:.2f}, "
                f"Diff={abs(channel_total - total_revenue):.2f}"
            )
        else:
            logger.debug("Revenue reconciliation passed")

        # Round channel revenues
        for ch_data in channel_stats.values():
            ch_data["revenue"] = round(ch_data["revenue"], 2)

        # Round daily revenues and sort by date
        for day_data in daily_stats.values():
            day_data["revenue"] = round(day_data["revenue"], 2)
        daily_breakdown = sorted(daily_stats.values(), key=lambda d: d["date"])

        logger.info(
            f"AGGREGATION: {total_orders} orders, "
            f"{valid_orders} valid, {excluded_orders} excluded, "
            f"{total_items} items, "
            f"Revenue: INR {total_revenue:,.2f}"
        )

        return {
            "total_orders": total_orders,
            "valid_orders": valid_orders,
            "excluded_orders": excluded_orders,
            "total_items": total_items,
            "total_revenue": round(total_revenue, 2),
            "total_discount": round(total_discount, 2),
            "total_tax": round(total_tax, 2),
            "total_refund": round(total_refund, 2),
            "avg_order_value": round(
                total_revenue / valid_orders, 2
            ) if valid_orders > 0 else 0,
            "channel_breakdown": channel_stats,
            "daily_breakdown": daily_breakdown,
            "status_breakdown": status_stats,
            "currency": "INR",
            "calculation_method": "sellingPrice_only",
            "reconciliation_passed": reconciliation_passed,
        }

    # Paginated API for frontend (12 orders per page)

    async def get_orders_paginated(
        self,
        from_date: datetime,
        to_date: datetime,
        page: int = 1,
        page_size: int = 12
    ) -> Dict[str, Any]:
        """
        Return a page of orders using cached full-fetch and in-memory slicing.
        """

        # Build a cache key for this date range + details
        cache_key = f"orders_detailed_{from_date.date()}_{to_date.date()}"

        # Check cache
        cached_orders = self._get_from_cache(cache_key)

        if cached_orders is None:
            # Fetch ALL orders with details (one-time cost, then cached)
            logger.info(
                f"Fetching all orders for {from_date.date()} to {to_date.date()}")
            logger.info(
                "Initial fetch may take a while")

            fetch_result = await self.fetch_all_orders_with_revenue(
                from_date, to_date, max_orders=100000
            )

            if not fetch_result.get("successful", False):
                return {
                    "success": False,
                    "error": fetch_result.get("error", "Failed to fetch orders"),
                    "orders": [],
                    "pagination": {},
                }

            all_orders = fetch_result.get("orders", [])

            # Process all orders
            processed_all = []
            for order in all_orders:
                calc = self.calculate_order_revenue(order)
                # Extract items with SKU and size information
                items = []
                for item in order.get("saleOrderItems", []):
                    item_name = item.get("itemName", "")
                    # Extract size from itemName - common patterns: "SIZE YEARS/MONTHS", "XS/S/M/L/XL", numbers
                    size = ""
                    if item_name:
                        # Try to extract size from end of name (e.g., "- 3-4 YEARS", "- XL", "- 10")
                            # Pattern 1: X-Y YEARS/MONTHS (e.g., "3-4 YEARS", "6-9 MONTHS")
                        match = re.search(
                            r'-?\s*(\d+-\d+\s+(?:YEARS?|MONTHS?))\s*$', item_name, re.IGNORECASE)
                        if not match:
                            # Pattern 2: Single size (e.g., "XS", "S", "M", "L", "XL", "XXL", "XXXL")
                            match = re.search(
                                r'-?\s*(XXX?L|XX?L|[SMLX])\s*$', item_name, re.IGNORECASE)
                        if not match:
                            # Pattern 3: Number size (e.g., "- 2", "- 10", "- 12-14")
                            match = re.search(
                                r'-?\s*(\d+(?:-\d+)?)\s*$', item_name)
                        if match:
                            size = match.group(1).strip()

                    items.append({
                        "itemSku": item.get("itemSku", ""),
                        "itemName": item_name,
                        "sku": item.get("itemSku", ""),
                        "sellingPrice": item.get("sellingPrice", 0),
                        "selling_price": item.get("sellingPrice", 0),
                        "quantity": item.get("quantity", 1),
                        # Fallback to SKU
                        "size": size if size else item.get("itemSku", "").split("-")[-1],
                    })
                processed_all.append({
                    "code": calc["order_code"],
                    "displayOrderCode": calc["order_code"],
                    "status": calc["status"],
                    "channel": calc["channel"],
                    "selling_price": calc["selling_price"],
                    "total_selling_price": calc["selling_price"],
                    "net_revenue": calc["net_revenue"],
                    "created": calc["created"],
                    "displayOrderDateTime": calc["created"],
                    "item_count": calc["item_count"],
                    "quantity": calc["quantity"],
                    "include_in_revenue": calc["include_in_revenue"],
                    "cashOnDelivery": order.get("cod", False),
                    "cod": order.get("cod", False),
                    "items": items,  # Add items array with SKU and size
                })

            # Cache the processed orders
            self._set_cache(cache_key, processed_all)
            cached_orders = processed_all
            logger.info(
                f"Cached {len(cached_orders)} orders")
        else:
            logger.info(
                f"Cache hit, using {len(cached_orders)} cached orders (instant load < 2s)")

        # Client-side pagination
        total_orders = len(cached_orders)
        total_pages = (total_orders + page_size -
                       1) // page_size if total_orders > 0 else 1

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_orders = cached_orders[start_idx:end_idx]

        page_revenue = sum(order["net_revenue"] for order in page_orders)

        return {
            "success": True,
            "orders": page_orders,
            "pagination": {
                "current_page": page,
                "page_size": page_size,
                "total_orders": total_orders,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1,
            },
            "page_summary": {
                "orders_on_page": len(page_orders),
                "page_revenue": round(page_revenue, 2),
            },
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "revenue_method": "sellingPrice_export_job",
            "cache_used": cached_orders is not None,
        }

    MAX_CHUNK_DAYS = 15  # Smaller chunks = faster UC export generation
    MAX_CONCURRENT_CHUNKS = 2  # Process up to 2 chunks in parallel (avoids UC rate limits)

    def _split_date_range(
        self, from_date: datetime, to_date: datetime
    ) -> List[Tuple[datetime, datetime]]:
        """Split a date range into chunks of MAX_CHUNK_DAYS."""
        chunks: List[Tuple[datetime, datetime]] = []
        cursor = from_date
        while cursor < to_date:
            chunk_end = min(
                cursor + timedelta(days=self.MAX_CHUNK_DAYS - 1,
                                   hours=23, minutes=59, seconds=59),
                to_date,
            )
            # Ensure chunk_end has end-of-day time
            chunk_end = chunk_end.replace(
                hour=23, minute=59, second=59, microsecond=0,
                tzinfo=to_date.tzinfo,
            )
            chunks.append((
                cursor.replace(hour=0, minute=0, second=0, microsecond=0,
                               tzinfo=from_date.tzinfo),
                chunk_end,
            ))
            cursor = (chunk_end + timedelta(seconds=1)).replace(
                hour=0, minute=0, second=0, microsecond=0,
                tzinfo=from_date.tzinfo,
            )
        return chunks

    # Main sales data method - uses export job API
    async def get_sales_data(
        self,
        from_date: datetime,
        to_date: datetime,
        period_name: str = "custom"
    ) -> Dict[str, Any]:
        """
        Get complete sales data for a date range.

        Revenue = SUM of item.sellingPrice from detail responses.
        Fetches ALL orders (no limits) for accurate business data.
        Uses 15-min cache to avoid repeated fetches.
        Auto-chunks ranges > 90 days (Unicommerce export limit).
        """
        # Check cache (also cache custom ranges keyed by date)
        if period_name != "custom":
            cache_key = self._get_cache_key(period_name)
        else:
            cache_key = f"uc_sales_custom_{from_date.date()}_{to_date.date()}"
        cached_data = self._get_from_cache(cache_key)
        if cached_data is not None:
            logger.info(
                f"Cache hit, returning {period_name} data instantly (no API calls)")
            return cached_data
        logger.info(f"Getting {period_name.upper()} SALES DATA")
        logger.info(f"  Date range: {from_date} to {to_date}")
        logger.info("  Method: Export Job API")

        if not self.access_code:
            return {
                "success": False,
                "message": "Unicommerce access code not configured",
                "period": period_name,
            }

        try:
            total_days = (to_date - from_date).days
            failed_chunks = 0

            if total_days > self.MAX_CHUNK_DAYS:
                # Auto-chunk: split into smaller batches for faster UC processing
                chunks = self._split_date_range(from_date, to_date)
                logger.info(
                    f"  Range is {total_days} days -> splitting into {len(chunks)} chunks "
                    f"(max {self.MAX_CONCURRENT_CHUNKS} concurrent)"
                )
                all_orders: List[Dict] = []
                total_time = 0.0
                failed_chunks = 0

                semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_CHUNKS)

                async def _process_chunk(idx: int, c_from: datetime, c_to: datetime) -> Tuple[int, List[Dict], float, bool]:
                    """Process a single chunk under the semaphore."""
                    async with semaphore:
                        # Stagger start to avoid hitting UC simultaneously
                        if idx > 0:
                            await asyncio.sleep(2)
                        logger.info(
                            f"  Chunk {idx + 1}/{len(chunks)}: "
                            f"{c_from.strftime('%Y-%m-%d')} -> {c_to.strftime('%Y-%m-%d')}"
                        )
                        result = await self.fetch_all_orders_with_revenue(
                            c_from, c_to, max_orders=100000
                        )
                        chunk_time = result.get("total_time", 0)
                        if not result.get("successful", False):
                            logger.warning(
                                f"  Chunk {idx + 1} failed: "
                                f"{result.get('error', 'unknown')}"
                            )
                            return (idx, [], chunk_time, False)
                        chunk_orders = result.get("orders", [])
                        logger.info(
                            f"  Chunk {idx + 1} OK: {len(chunk_orders)} orders in {chunk_time:.1f}s"
                        )
                        return (idx, chunk_orders, chunk_time, True)

                tasks = [
                    _process_chunk(idx, c_from, c_to)
                    for idx, (c_from, c_to) in enumerate(chunks)
                ]
                results = await asyncio.gather(*tasks)

                # Merge results in order
                for idx, chunk_orders, chunk_time, ok in sorted(results, key=lambda r: r[0]):
                    total_time += chunk_time
                    if ok:
                        all_orders.extend(chunk_orders)
                    else:
                        failed_chunks += 1

                if not all_orders:
                    return {
                        "success": False,
                        "message": f"All {len(chunks)} chunks failed",
                        "period": period_name,
                    }

                if failed_chunks:
                    logger.warning(
                        f"  {failed_chunks}/{len(chunks)} chunks failed, "
                        f"proceeding with {len(all_orders)} orders from successful chunks"
                    )

                orders = all_orders
                total_records = len(orders)
            else:
                # Single fetch (≤ 90 days)
                fetch_result = await self.fetch_all_orders_with_revenue(
                    from_date, to_date, max_orders=100000
                )

                if not fetch_result.get("successful", False):
                    return {
                        "success": False,
                        "message": fetch_result.get("error", "Failed to fetch orders"),
                        "period": period_name,
                    }

                orders = fetch_result.get("orders", [])
                total_records = fetch_result.get("totalRecords", 0)
                total_time = fetch_result.get("total_time", 0)

            logger.info(
                f"Retrieved {len(orders)} orders with full pricing data")

            # Aggregate using sellingPrice ONLY
            aggregation = self.aggregate_orders(orders)
            logger.info("Revenue summary")
            logger.info(
                f"  Valid orders: {aggregation['valid_orders']} / {total_records} total")
            logger.info(
                f"  REVENUE: INR {aggregation['total_revenue']:,.2f}")
            logger.info(
                f"  AVG: INR {aggregation['avg_order_value']:,.2f}")
            logger.info(
                f"  Reconciliation: {'PASSED' if aggregation.get('reconciliation_passed') else 'FAILED'}")

            # Sample orders for display (first 10)
            sample_orders = []
            for order in orders[:10]:
                calc = self.calculate_order_revenue(order)
                sample_orders.append({
                    "code": calc["order_code"],
                    "status": calc["status"],
                    "channel": calc["channel"],
                    "selling_price": calc["selling_price"],
                    "net_revenue": calc["net_revenue"],
                    "created": calc["created"],
                    "item_count": calc["item_count"],
                    "quantity": calc["quantity"],
                    "include_in_revenue": calc["include_in_revenue"],
                })

            result = {
                "success": True,
                "period": period_name,
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "data_accuracy": "complete" if not (total_days > self.MAX_CHUNK_DAYS and failed_chunks) else "partial",
                "revenue_method": "sellingPrice_export_job",
                "fetch_info": {
                    "total_available": total_records,
                    "fetched_count": len(orders),
                    "total_time_seconds": round(total_time, 2),
                    "reconciliation_passed": aggregation.get("reconciliation_passed", True),
                },
                "summary": aggregation,
                "orders": sample_orders,
                "_orders": orders,
            }

            # Cache the result (all periods including custom)
            self._set_cache(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"Error in get_sales_data: {e}", exc_info=True)
            return {
                "success": False,
                "message": str(e),
                "period": period_name,
            }

    # Time-based convenience methods
    async def get_today_sales(self) -> Dict[str, Any]:
        """Get today's sales (00:00:00 to current time - 1 minute)"""
        from_date, to_date = self.get_today_range()
        return await self.get_sales_data(from_date, to_date, "today")

    async def get_yesterday_sales(self) -> Dict[str, Any]:
        """Get yesterday's sales (00:00:00 to 23:59:59)"""
        from_date, to_date = self.get_yesterday_range()
        return await self.get_sales_data(from_date, to_date, "yesterday")

    async def get_last_7_days_sales(self) -> Dict[str, Any]:
        """Get last 7 complete days (not including today)"""
        from_date, to_date = self.get_last_n_days_range(7)
        return await self.get_sales_data(from_date, to_date, "last_7_days")

    async def get_custom_range_sales(
        self, from_date: datetime, to_date: datetime
    ) -> Dict[str, Any]:
        """Get sales for custom date range"""
        return await self.get_sales_data(from_date, to_date, "custom")

    # ── Inventory Snapshot ─────────────────────────────────────────────

    async def get_inventory_snapshot(
        self, item_skus: List[str], facility_code: str = "anthrilo"
    ) -> Dict[str, Dict[str, int]]:
        """
        Fetch current inventory snapshot for a list of SKUs.

        Returns a dict keyed by SKU with good_inventory and virtual_inventory.
        Unicommerce API: POST /inventory/inventorySnapshot/get
        Batches in groups of 100 to avoid payload limits.
        """
        if not item_skus:
            return {}

        BATCH_SIZE = 100
        url = f"{self.base_url}/inventory/inventorySnapshot/get"
        result: Dict[str, Dict[str, int]] = {}
        raw_snapshot_rows: List[Dict[str, Any]] = []
        batch_failures = 0

        export_job_id = self._create_export_job_record(
            export_type="inventory_snapshot",
            requested_from=None,
            requested_to=None,
            requested_columns=[
                "itemTypeSKU",
                "inventory",
                "virtualInventory",
                "openSale",
                "inventoryBlocked",
            ],
        )

        unique_skus = list(set(item_skus))
        sync_log_id = self._create_sync_log_record(
            sync_type="snapshot_api",
            entity="inventory_snapshot",
            details={
                "facility_code": facility_code,
                "requested_skus": len(unique_skus),
            },
        )

        batches = [
            unique_skus[i:i + BATCH_SIZE]
            for i in range(0, len(unique_skus), BATCH_SIZE)
        ]

        logger.info(
            f"Inventory: Fetching snapshot for {len(unique_skus)} unique SKUs "
            f"in {len(batches)} batches"
        )

        for batch_idx, batch in enumerate(batches):
            payload = {
                "itemTypeSKUs": batch,
            }

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    headers = await self._get_headers()
                    headers["Facility"] = facility_code

                    response = await client.post(url, json=payload, headers=headers)

                    if response.status_code == 401:
                        self.token_manager.invalidate_token()
                        await self.token_manager.get_valid_token()
                        headers = await self._get_headers()
                        headers["Facility"] = facility_code
                        response = await client.post(url, json=payload, headers=headers)

                    if response.status_code != 200:
                        batch_failures += 1
                        logger.warning(
                            f"Inventory: Batch {batch_idx + 1}/{len(batches)} "
                            f"HTTP {response.status_code}"
                        )
                        continue

                    data = response.json()

                    if not data.get("successful"):
                        batch_failures += 1
                        logger.warning(
                            f"Inventory: Batch {batch_idx + 1} not successful: "
                            f"{data.get('message', '')}"
                        )
                        continue

                    snapshots = data.get("inventorySnapshots", [])
                    for snap in snapshots:
                        sku = snap.get("itemTypeSKU", "")
                        if not sku:
                            continue
                        raw_snapshot_rows.append(
                            {
                                **snap,
                                "facilityCode": facility_code,
                            }
                        )
                        inventory = snap.get("inventory", 0)
                        virtual_inv = snap.get("virtualInventory", 0)
                        # inventory = total physical available (good) inventory
                        # virtualInventory = stock available for sale across channels
                        result[sku] = {
                            "good_inventory": int(inventory) if inventory else 0,
                            "virtual_inventory": int(virtual_inv) if virtual_inv else 0,
                        }

                    logger.info(
                        f"Inventory: Batch {batch_idx + 1}/{len(batches)} "
                        f"got {len(snapshots)} snapshots"
                    )

            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as e:
                batch_failures += 1
                logger.warning(
                    f"Inventory: Batch {batch_idx + 1} timeout: {type(e).__name__}"
                )
                continue
            except Exception as e:
                batch_failures += 1
                logger.warning(
                    f"Inventory: Batch {batch_idx + 1} error: {e}"
                )
                continue

            # Brief delay between batches
            if batch_idx < len(batches) - 1:
                await asyncio.sleep(0.5)

        logger.info(
            f"Inventory: Got data for {len(result)}/{len(unique_skus)} SKUs"
        )

        archived_rows, file_checksum = self._archive_export_rows(
            export_job_id,
            "inventory_snapshot",
            raw_snapshot_rows,
        )
        normalized_rows = self._upsert_inventory_snapshot_rows(raw_snapshot_rows, facility_code)

        sync_status = "completed" if raw_snapshot_rows or batch_failures == 0 else "failed"

        self._update_export_job_record(
            export_job_id,
            status=sync_status,
            error_message=None if (raw_snapshot_rows or batch_failures == 0) else "No inventory snapshots fetched",
            csv_headers=list(raw_snapshot_rows[0].keys()) if raw_snapshot_rows else [],
            file_checksum=file_checksum,
            total_csv_rows=len(raw_snapshot_rows),
            parsed_entities=normalized_rows,
            completed_at=datetime.utcnow(),
        )

        self._update_sync_log_record(
            sync_log_id,
            status=sync_status,
            processed_count=normalized_rows,
            failed_count=batch_failures,
            error_message=None if sync_status == "completed" else "No inventory snapshots fetched",
            completed_at=datetime.utcnow(),
            details={
                "facility_code": facility_code,
                "requested_skus": len(unique_skus),
                "archived_rows": archived_rows,
                "normalized_rows": normalized_rows,
                "batch_failures": batch_failures,
            },
        )

        logger.info(
            "Inventory archival: "
            f"archived_rows={archived_rows}, normalized_rows={normalized_rows}"
        )
        return result


    async def get_today_orders_paginated(
        self, page: int = 1, page_size: int = 12
    ) -> Dict[str, Any]:
        from_date, to_date = self.get_today_range()
        return await self.get_orders_paginated(from_date, to_date, page, page_size)

    async def get_yesterday_orders_paginated(
        self, page: int = 1, page_size: int = 12
    ) -> Dict[str, Any]:
        from_date, to_date = self.get_yesterday_range()
        return await self.get_orders_paginated(from_date, to_date, page, page_size)

    async def get_last_7_days_orders_paginated(
        self, page: int = 1, page_size: int = 12
    ) -> Dict[str, Any]:
        from_date, to_date = self.get_last_n_days_range(7)
        return await self.get_orders_paginated(from_date, to_date, page, page_size)

    # Validation & reconciliation
    async def validate_revenue_consistency(self) -> Dict[str, Any]:
        """
        Run sanity checks on revenue data across periods.
        """
        logger.info("Running revenue validation checks...")

        today = await self.get_today_sales()
        yesterday = await self.get_yesterday_sales()
        last_7 = await self.get_last_7_days_sales()

        issues = []

        today_rev = today.get("summary", {}).get(
            "total_revenue", 0) if today.get("success") else 0
        yesterday_rev = yesterday.get("summary", {}).get(
            "total_revenue", 0) if yesterday.get("success") else 0
        rev_7d = last_7.get("summary", {}).get(
            "total_revenue", 0) if last_7.get("success") else 0

        # Check 1: Channel totals for 7-day
        if last_7.get("success"):
            summary = last_7.get("summary", {})
            channel_breakdown = summary.get("channel_breakdown", {})
            channel_total = sum(ch.get("revenue", 0)
                                for ch in channel_breakdown.values())
            if abs(channel_total - rev_7d) > 1:
                issues.append(
                    f"Channel total ({channel_total:,.2f}) != "
                    f"Overall total ({rev_7d:,.2f})"
                )

        # Check 2: Reconciliation flags
        for period_data, period_name in [
            (today, "today"), (yesterday, "yesterday"),
            (last_7, "last_7_days")
        ]:
            fetch_info = period_data.get("fetch_info", {})
            if not fetch_info.get("reconciliation_passed", True):
                issues.append(
                    f"Revenue reconciliation failed for {period_name}")

        return {
            "success": len(issues) == 0,
            "checks_passed": 2 - len(issues),
            "issues": issues,
            "revenues": {
                "today": today_rev,
                "yesterday": yesterday_rev,
                "last_7_days": rev_7d,
            },
            "message": "All validations passed" if not issues else f"{len(issues)} issues found",
        }

    # Backward compatibility
    async def search_sale_orders(
        self,
        from_date: datetime = None,
        to_date: datetime = None,
        display_start: int = 0,
        display_length: int = 100
    ) -> Dict[str, Any]:
        """Backward compatible search method — uses export job API."""
        now = datetime.now(timezone.utc)
        if to_date is None:
            to_date = now
        if from_date is None:
            from_date = now - timedelta(hours=24)

        try:
            fetch_result = await self.fetch_orders_via_export(from_date, to_date)

            if not fetch_result.get("successful", False):
                return {
                    "successful": False,
                    "error": fetch_result.get("error", "Failed to fetch orders"),
                    "elements": [],
                    "totalRecords": 0,
                }

            all_orders = fetch_result.get("orders", [])
            total = len(all_orders)

            # Apply pagination via in-memory slicing
            page_orders = all_orders[display_start:display_start + display_length]

            return {
                "successful": True,
                "elements": page_orders,
                "totalRecords": total,
            }
        except Exception as e:
            logger.error(f"search_sale_orders failed: {e}", exc_info=True)
            return {
                "successful": False,
                "error": str(e),
                "elements": [],
                "totalRecords": 0,
            }

    async def get_order_details(self, order_code: str) -> Dict[str, Any]:
        """Get full order details including payment info."""
        url = f"{self.base_url}/oms/saleorder/get"

        async with httpx.AsyncClient(timeout=self.timeout, limits=self.limits) as client:
            try:
                headers = await self._get_headers()
                response = await client.post(
                    url,
                    json={
                        "code": order_code,
                        "paymentDetailRequired": True,
                    },
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()

                if data.get("successful"):
                    order_dto = data.get("saleOrderDTO")
                    if order_dto:
                        revenue_calc = self.calculate_order_revenue(order_dto)
                        return {
                            "successful": True,
                            "order": order_dto,
                            "revenue_info": revenue_calc,
                        }
                    return {"successful": True, "order": order_dto}
                else:
                    return {
                        "successful": False,
                        "error": data.get("message", "Unknown error"),
                    }
            except Exception as e:
                logger.error(f"Error fetching order {order_code}: {e}")
                return {"successful": False, "error": str(e)}

    # ── Fabric-only sales data ────────────────────────────────────────

    async def _download_parse_export_fabric(
        self,
        download_url: str,
        include_rows: bool = False,
    ) -> Any:
        """Download export CSV and return ONLY rows where category = FABRIC."""
        try:
            csv_text = await self._download_csv_text(download_url, label="Fabric Export")
            if csv_text is None:
                logger.error("Fabric export: Failed to download CSV after retries")
                if include_rows:
                    return [], [], []
                return []

            if not csv_text or not csv_text.strip():
                if include_rows:
                    return [], [], []
                return []

            reader = csv.DictReader(io.StringIO(csv_text))
            fieldnames = reader.fieldnames or []
            orders_map: Dict[str, Dict] = {}
            fabric_count = 0
            raw_rows: List[Dict[str, Any]] = []

            for row in reader:
                if include_rows:
                    raw_rows.append(dict(row))
                item_category = (
                    row.get("Category") or row.get("category")
                    or row.get("Item Type Category") or row.get("categoryCode") or ""
                ).strip().upper()
                if item_category not in self.EXCLUDED_CATEGORIES:
                    continue  # skip non-fabric

                fabric_count += 1
                order_code = (
                    row.get("Sale Order Code") or row.get("saleOrderCode")
                    or row.get("code") or ""
                ).strip()
                if not order_code:
                    continue

                if order_code not in orders_map:
                    channel_raw = (row.get("Channel Name") or row.get("channel") or "UNKNOWN").strip()
                    cod_raw = (row.get("COD") or row.get("cod") or "0").strip()
                    is_cod = cod_raw in ("1", "true", "True", "yes")
                    orders_map[order_code] = {
                        "code": order_code,
                        "channel": channel_raw.replace(" ", "_"),
                        "status": (row.get("Sale Order Status") or row.get("status") or "").strip(),
                        "created": (row.get("Created") or row.get("created") or "").strip(),
                        "cod": is_cod,
                        "saleOrderItems": [],
                    }

                try:
                    selling_price = float(row.get("Selling Price") or row.get("sellingPrice") or 0)
                except (ValueError, TypeError):
                    selling_price = 0.0
                try:
                    mrp = float(row.get("MRP") or row.get("maxRetailPrice") or 0)
                except (ValueError, TypeError):
                    mrp = 0.0
                try:
                    discount = float(row.get("Discount") or row.get("discount") or 0)
                except (ValueError, TypeError):
                    discount = 0.0

                try:
                    quantity = int(float(
                        row.get("Quantity")
                        or row.get("Qty")
                        or row.get("QTY")
                        or row.get("quantity")
                        or row.get("Sale Order Item Quantity")
                        or 1
                    ))
                except (ValueError, TypeError):
                    quantity = 1
                if quantity <= 0:
                    quantity = 1

                sku_code = (row.get("Item SKU Code") or row.get("skuCode") or row.get("itemSku") or "").strip()
                item_details = (row.get("Item Details") or row.get("itemDetails") or "").strip()
                soi_code = (row.get("Sale Order Item Code") or row.get("soicode") or "").strip()

                orders_map[order_code]["saleOrderItems"].append({
                    "soiCode": soi_code,
                    "itemSku": sku_code,
                    "itemName": item_details or sku_code,
                    "sellingPrice": selling_price,
                    "maxRetailPrice": mrp,
                    "quantity": quantity,
                    "discount": discount,
                })

            orders = [o for o in orders_map.values() if o["saleOrderItems"]]
            logger.info(f"Fabric export: {fabric_count} rows → {len(orders)} orders")
            if include_rows:
                return orders, raw_rows, fieldnames
            return orders

        except Exception as e:
            logger.error(f"Fabric export parse failed: {e}", exc_info=True)
            if include_rows:
                return [], [], []
            return []

    async def get_fabric_sales_data(
        self,
        from_date: datetime,
        to_date: datetime,
        period_name: str = "custom"
    ) -> Dict[str, Any]:
        """Get sales data for FABRIC category items only."""
        cache_key = f"uc:fabric:{period_name}:{from_date.date()}_{to_date.date()}"
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            logger.info(f"Fabric data: cache hit for {period_name}")
            return cached

        logger.info(f"Fetching FABRIC sales data for {period_name}")

        sync_log_id = self._create_sync_log_record(
            sync_type="export_job",
            entity="sale_orders_fabric",
            details={
                "period": period_name,
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
            },
        )

        export_job_id = self._create_export_job_record(
            export_type="sale_orders",
            requested_from=from_date,
            requested_to=to_date,
            requested_columns=self.EXPORT_COLUMNS,
        )

        try:
            job_code = await self._create_export_job(from_date, to_date)
            if not job_code:
                self._update_export_job_record(
                    export_job_id,
                    status="failed",
                    error_message="Export job creation failed",
                    completed_at=datetime.utcnow(),
                )
                self._update_sync_log_record(
                    sync_log_id,
                    status="failed",
                    failed_count=1,
                    error_message="Export job creation failed",
                    completed_at=datetime.utcnow(),
                )
                return {"success": False, "error": "Export job creation failed", "orders": [], "summary": {}}

            self._update_export_job_record(
                export_job_id,
                job_code=job_code,
                status="running",
            )

            download_url = await self._poll_export_status(job_code)
            if not download_url:
                self._update_export_job_record(
                    export_job_id,
                    status="failed",
                    error_message="Export job timed out",
                    completed_at=datetime.utcnow(),
                )
                self._update_sync_log_record(
                    sync_log_id,
                    status="failed",
                    failed_count=1,
                    error_message="Export job timed out",
                    completed_at=datetime.utcnow(),
                )
                return {"success": False, "error": "Export job timed out", "orders": [], "summary": {}}

            orders, raw_rows, csv_headers = await self._download_parse_export_fabric(
                download_url,
                include_rows=True,
            )

            archived_rows, file_checksum = self._archive_export_rows(
                export_job_id,
                "sale_orders",
                raw_rows,
            )
            normalized_rows = self._upsert_sales_order_rows(raw_rows)

            self._update_export_job_record(
                export_job_id,
                status="completed",
                download_url=download_url,
                csv_headers=csv_headers,
                file_checksum=file_checksum,
                total_csv_rows=len(raw_rows),
                parsed_entities=normalized_rows,
                completed_at=datetime.utcnow(),
            )

            self._update_sync_log_record(
                sync_log_id,
                status="completed",
                processed_count=normalized_rows,
                failed_count=max(0, len(raw_rows) - normalized_rows),
                completed_at=datetime.utcnow(),
                details={
                    "period": period_name,
                    "from_date": from_date.isoformat(),
                    "to_date": to_date.isoformat(),
                    "archived_rows": archived_rows,
                    "normalized_rows": normalized_rows,
                },
            )

            # Build flat item-level rows and aggregate summary
            total_orders = 0
            total_items = 0
            items_list: List[Dict] = []
            seen_orders: set = set()

            for order in orders:
                status = order.get("status", "")
                if status in self.EXCLUDED_STATUSES:
                    continue
                order_code = order.get("code", "")
                created = order.get("created", "")
                if order_code not in seen_orders:
                    seen_orders.add(order_code)
                    total_orders += 1
                for item in order.get("saleOrderItems", []):
                    qty = int(item.get("quantity", 1) or 1)
                    total_items += qty
                    items_list.append({
                        "soiCode": item.get("soiCode", ""),
                        "sku": item.get("itemSku", ""),
                        "orderCode": order_code,
                        "created": created,
                        "quantity": qty,
                    })

            result = {
                "success": True,
                "period": period_name,
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "export_job_id": export_job_id,
                "archived_rows": archived_rows,
                "normalized_rows": normalized_rows,
                "summary": {
                    "total_orders": total_orders,
                    "total_items": total_items,
                },
                "items": items_list,
                "total_items_count": len(items_list),
            }

            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Fabric sales data error: {e}", exc_info=True)
            self._update_export_job_record(
                export_job_id,
                status="failed",
                error_message=str(e),
                completed_at=datetime.utcnow(),
            )
            self._update_sync_log_record(
                sync_log_id,
                status="failed",
                failed_count=1,
                error_message=str(e),
                completed_at=datetime.utcnow(),
            )
            return {"success": False, "error": str(e), "orders": [], "summary": {}}

    # ── Bundle SKU data (Item Master export) ──────────────────────────

    async def _create_item_master_export_job(self) -> Optional[str]:
        """
        Create a Unicommerce export job for Item Master (all items).
        Item Master does not support date filters — we fetch all and filter
        by Type=BUNDLE during CSV parsing.
        Returns the jobCode on success, None on failure.
        """
        url = f"{self.base_url}/export/job/create"

        payload = {
            "exportJobTypeName": "Item Master",
            "exportColums": ["All"],
            "exportFilters": [],
            "frequency": "ONETIME",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout, limits=self.limits) as client:
                headers = await self._get_headers()
                headers["Facility"] = "anthrilo"

                response = await client.post(url, json=payload, headers=headers)

                if response.status_code == 401:
                    self.token_manager.invalidate_token()
                    await self.token_manager.get_valid_token()
                    headers = await self._get_headers()
                    headers["Facility"] = "anthrilo"
                    response = await client.post(url, json=payload, headers=headers)

                if response.status_code >= 400:
                    try:
                        error_body = response.json()
                    except Exception:
                        error_body = response.text[:500]
                    logger.error(
                        f"Item Master Export: Job creation HTTP {response.status_code}: {error_body}"
                    )
                    return None

                data = response.json()

                if data.get("successful"):
                    job_code = data.get("jobCode")
                    logger.info(f"Item Master Export: Job created successfully {job_code}")
                    return job_code
                else:
                    errors = data.get("errors", [])
                    msg = data.get("message", "Unknown error")
                    logger.error(f"Item Master Export: Job creation failed: {msg} | errors={errors}")
                    return None

        except Exception as e:
            logger.error(f"Item Master Export: Job creation exception: {e}", exc_info=True)
            return None

    async def _download_parse_bundle_export(
        self,
        download_url: str,
        include_rows: bool = False,
    ) -> Any:
        """
        Download Item Master export CSV, keep only Type=BUNDLE rows,
        and aggregate multiple component rows per SKU into a single record
        with a 'components' array.

        UC CSV has one row per (bundle SKU × component), so a bundle with
        3 components produces 3 CSV rows sharing the same Product Code.
        """
        try:
            csv_text = await self._download_csv_text(download_url, label="Bundle Export")
            if csv_text is None:
                logger.error("Bundle export: Failed to download CSV after retries")
                if include_rows:
                    return [], [], []
                return []

            if not csv_text or not csv_text.strip():
                logger.warning("Bundle Export: Downloaded CSV is empty")
                if include_rows:
                    return [], [], []
                return []

            reader = csv.DictReader(io.StringIO(csv_text))
            fieldnames = reader.fieldnames or []
            logger.info(f"Bundle Export: CSV columns ({len(fieldnames)}): {fieldnames[:10]}...")

            # Aggregate: dict keyed by SKU code → single bundle record
            bundle_map: Dict[str, Dict] = {}
            raw_rows: List[Dict[str, Any]] = []
            skipped_type = 0
            total_rows = 0

            for row in reader:
                total_rows += 1
                if include_rows:
                    raw_rows.append(dict(row))
                row_type = (row.get("Type") or row.get("type") or "").strip().upper()
                if row_type != "BUNDLE":
                    skipped_type += 1
                    continue

                sku_code = (row.get("Product Code") or row.get("SKU Code") or "").strip()
                if not sku_code:
                    continue

                # Component info from this row
                comp_sku = (row.get("Component Product Code") or "").strip()
                comp_qty = (row.get("Component Quantity") or "").strip()
                comp_price = (row.get("Component Price") or "").strip()

                if sku_code in bundle_map:
                    # SKU already seen — just append this component
                    if comp_sku:
                        bundle_map[sku_code]["components"].append({
                            "sku": comp_sku,
                            "quantity": comp_qty,
                            "price": comp_price,
                        })
                    continue

                # First row for this SKU — extract all fields
                item_name = (row.get("Name") or row.get("Item Name") or "").strip()
                category = (row.get("Category Name") or row.get("Category") or "").strip()
                category_code = (row.get("Category Code") or "").strip()
                updated_raw = (row.get("Updated") or "").strip()

                try:
                    cost_price = float(row.get("Cost Price") or 0)
                except (ValueError, TypeError):
                    cost_price = 0.0
                try:
                    mrp = float(row.get("MRP") or 0)
                except (ValueError, TypeError):
                    mrp = 0.0
                try:
                    base_price = float(row.get("Base Price") or 0)
                except (ValueError, TypeError):
                    base_price = 0.0

                color = (row.get("Color") or "").strip()
                size = (row.get("Size") or "").strip()
                brand = (row.get("Brand") or "").strip()
                enabled_str = (row.get("Enabled") or "").strip()
                hsn_code = (row.get("HSN CODE") or "").strip()
                weight = (row.get("Weight (gms)") or "").strip()
                image_url = (row.get("Image Url") or "").strip()

                components = []
                if comp_sku:
                    components.append({
                        "sku": comp_sku,
                        "quantity": comp_qty,
                        "price": comp_price,
                    })

                bundle_map[sku_code] = {
                    "skuCode": sku_code,
                    "itemName": item_name or sku_code,
                    "category": category,
                    "categoryCode": category_code,
                    "costPrice": cost_price,
                    "mrp": mrp,
                    "basePrice": base_price,
                    "color": color,
                    "size": size,
                    "brand": brand,
                    "enabled": enabled_str.lower() in ("true", "1", "yes", "y"),
                    "hsnCode": hsn_code,
                    "weight": weight,
                    "imageUrl": image_url,
                    "updated": updated_raw,
                    "components": components,
                }

            bundles = list(bundle_map.values())
            # Add componentCount for convenience
            for b in bundles:
                b["componentCount"] = len(b["components"])

            logger.info(
                f"Bundle Export: {total_rows} CSV rows → {len(bundles)} unique bundles "
                f"(skipped {skipped_type} non-bundle rows)"
            )
            if include_rows:
                return bundles, raw_rows, fieldnames
            return bundles

        except Exception as e:
            logger.error(f"Bundle Export: Download/parse failed: {e}", exc_info=True)
            if include_rows:
                return [], [], []
            return []

    async def get_bundle_sku_data(self) -> Dict[str, Any]:
        """
        Get all BUNDLE type items from the Item Master export.
        This is catalogue data — no date filtering (UC doesn't support
        date filters for Item Master, and the 'Updated' column only
        reflects when the item record was last modified in UC).
        Components are aggregated into each bundle record.
        """
        cache_key = "uc:bundle_skus:all"

        cached = self._get_from_cache(cache_key)
        if cached is not None:
            logger.info("Bundle SKU data: cache hit")
            return cached

        logger.info("Fetching BUNDLE SKU data via Item Master export")

        sync_log_id = self._create_sync_log_record(
            sync_type="export_job",
            entity="bundle_sku_catalog",
            details={
                "export_type": "item_master",
            },
        )

        export_job_id = self._create_export_job_record(
            export_type="item_master",
            requested_from=None,
            requested_to=None,
            requested_columns=["All"],
        )

        try:
            job_code = await self._create_item_master_export_job()
            if not job_code:
                self._update_export_job_record(
                    export_job_id,
                    status="failed",
                    error_message="Item Master export job creation failed",
                    completed_at=datetime.utcnow(),
                )
                self._update_sync_log_record(
                    sync_log_id,
                    status="failed",
                    failed_count=1,
                    error_message="Item Master export job creation failed",
                    completed_at=datetime.utcnow(),
                )
                return {"success": False, "error": "Item Master export job creation failed", "bundles": [], "summary": {}}

            self._update_export_job_record(
                export_job_id,
                job_code=job_code,
                status="running",
            )

            download_url = await self._poll_export_status(job_code)
            if not download_url:
                self._update_export_job_record(
                    export_job_id,
                    status="failed",
                    error_message="Item Master export job timed out",
                    completed_at=datetime.utcnow(),
                )
                self._update_sync_log_record(
                    sync_log_id,
                    status="failed",
                    failed_count=1,
                    error_message="Item Master export job timed out",
                    completed_at=datetime.utcnow(),
                )
                return {"success": False, "error": "Item Master export job timed out", "bundles": [], "summary": {}}

            bundles, raw_rows, csv_headers = await self._download_parse_bundle_export(
                download_url,
                include_rows=True,
            )

            archived_rows, file_checksum = self._archive_export_rows(
                export_job_id,
                "item_master",
                raw_rows,
            )

            total_bundles = len(bundles)
            enabled_count = sum(1 for b in bundles if b.get("enabled"))
            disabled_count = total_bundles - enabled_count
            mrp_values = [b["mrp"] for b in bundles if b["mrp"] > 0]
            cost_values = [b["costPrice"] for b in bundles if b["costPrice"] > 0]
            avg_mrp = round(sum(mrp_values) / len(mrp_values), 2) if mrp_values else 0
            avg_cost = round(sum(cost_values) / len(cost_values), 2) if cost_values else 0

            # Category breakdown
            category_map: Dict[str, int] = {}
            for b in bundles:
                cat = b.get("category") or "Unknown"
                category_map[cat] = category_map.get(cat, 0) + 1

            # Sort categories by count descending
            sorted_categories = dict(
                sorted(category_map.items(), key=lambda x: x[1], reverse=True)
            )

            result = {
                "success": True,
                "bundles": bundles,
                "export_job_id": export_job_id,
                "archived_rows": archived_rows,
                "summary": {
                    "total_bundles": total_bundles,
                    "enabled": enabled_count,
                    "disabled": disabled_count,
                    "avg_mrp": avg_mrp,
                    "avg_cost": avg_cost,
                    "total_categories": len(category_map),
                    "categories": sorted_categories,
                },
            }

            self._update_export_job_record(
                export_job_id,
                status="completed",
                download_url=download_url,
                csv_headers=csv_headers,
                file_checksum=file_checksum,
                total_csv_rows=len(raw_rows),
                parsed_entities=total_bundles,
                completed_at=datetime.utcnow(),
            )

            self._update_sync_log_record(
                sync_log_id,
                status="completed",
                processed_count=total_bundles,
                failed_count=max(0, len(raw_rows) - total_bundles),
                completed_at=datetime.utcnow(),
                details={
                    "archived_rows": archived_rows,
                    "bundle_count": total_bundles,
                },
            )

            # Cache — this is static catalogue data
            self._set_cache(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Bundle SKU data error: {e}", exc_info=True)
            self._update_export_job_record(
                export_job_id,
                status="failed",
                error_message=str(e),
                completed_at=datetime.utcnow(),
            )
            self._update_sync_log_record(
                sync_log_id,
                status="failed",
                failed_count=1,
                error_message=str(e),
                completed_at=datetime.utcnow(),
            )
            return {"success": False, "error": str(e), "bundles": [], "summary": {}}

    # ── Bundle Sales Analysis ─────────────────────────────────────────

    async def get_bundle_sales_analysis(
        self, from_date: datetime, to_date: datetime
    ) -> Dict[str, Any]:
        """
        Analyse bundle-level sales by reverse-mapping component SKUs in
        sale orders back to their parent bundles.

        UC explodes bundles into component line items at order creation,
        so no order ever contains the bundle SKU directly.  We rebuild
        bundle sales from the component→bundle mapping.

        Algorithm
        ---------
        1.  Load bundle catalogue (cached) to build a reverse index:
                component_sku → [(bundle_sku, required_qty, bundle_obj), …]
        2.  Fetch sale orders for the period via CSV export.
        3.  For each order, group items by SKU and tally quantities.
        4.  For every candidate bundle whose **all** components appear
            in the order with sufficient quantity, record a bundle sale.
            Greedy: consume the components that form the match so they
            aren't double-counted.
        5.  Aggregate into daily trends, category breakdown, channel
            performance, and a top-bundles ranking.
        """
        start = time_module.time()
        logger.info(
            f"Bundle Sales Analysis: {from_date.isoformat()} → {to_date.isoformat()}"
        )

        # ---- 1. Load catalogue & build reverse index ----
        catalog = await self.get_bundle_sku_data()
        bundles_list = catalog.get("bundles", [])
        if not bundles_list:
            return {
                "success": False,
                "error": "Bundle catalogue is empty",
                "bundle_sales": [], "daily_trend": [],
                "category_breakdown": {}, "channel_breakdown": {},
                "summary": {},
            }

        # reverse_idx:  component_sku → list of (bundle_obj, {comp_sku: qty_needed})
        reverse_idx: Dict[str, List[tuple]] = {}
        # Pre-parse component requirements per bundle
        bundle_comp_map: Dict[str, Dict[str, int]] = {}  # bundle_sku → {comp_sku: qty}

        for b in bundles_list:
            if not b.get("enabled"):
                continue
            bsku = b["skuCode"]
            comp_req: Dict[str, int] = {}
            for c in b.get("components", []):
                try:
                    qty = int(float(c.get("quantity", 1)))
                except (ValueError, TypeError):
                    qty = 1
                comp_req[c["sku"]] = qty
            if not comp_req:
                continue
            bundle_comp_map[bsku] = comp_req
            for csku in comp_req:
                reverse_idx.setdefault(csku, []).append((b, comp_req))

        logger.info(
            f"Bundle Sales: reverse index built — "
            f"{len(bundle_comp_map)} bundles, {len(reverse_idx)} component SKUs"
        )

        # ---- 2. Fetch sale orders ----
        export_result = await self.fetch_orders_via_export(from_date, to_date)
        orders = export_result.get("orders", [])
        if not orders:
            elapsed = round(time_module.time() - start, 1)
            logger.info(f"Bundle Sales: 0 orders in range ({elapsed}s)")
            return {
                "success": True,
                "bundle_sales": [], "daily_trend": [],
                "category_breakdown": {}, "channel_breakdown": {},
                "summary": {
                    "total_orders": 0, "orders_with_bundles": 0,
                    "total_bundle_units": 0, "total_bundle_revenue": 0,
                    "unique_bundles_sold": 0, "analysis_time": elapsed,
                },
            }

        # ---- 3 & 4. Match orders → bundles ----
        # Accumulators
        bundle_sales_agg: Dict[str, Dict[str, Any]] = {}  # bsku → agg
        daily_agg: Dict[str, Dict[str, float]] = {}       # date → {units, revenue}
        channel_agg: Dict[str, Dict[str, float]] = {}     # channel → {units, revenue}
        orders_with_bundles = 0

        for order in orders:
            status = (order.get("status") or "").upper()
            if status in self.EXCLUDED_STATUSES:
                continue

            items = order.get("saleOrderItems", [])
            if not items:
                continue

            channel = order.get("channel", "UNKNOWN")
            date_key = self._extract_date_key(order.get("created"))

            # Build SKU → available quantity map for this order
            sku_pool: Dict[str, float] = {}
            sku_price: Dict[str, float] = {}  # track selling price per SKU
            for it in items:
                sku = it.get("itemSku", "")
                if not sku:
                    continue
                qty = float(it.get("quantity", 1))
                sku_pool[sku] = sku_pool.get(sku, 0) + qty
                sp = float(it.get("sellingPrice", 0) or 0)
                if sp > 0:
                    sku_price[sku] = sp

            # Find all candidate bundles from the SKUs in this order
            candidate_bundles: Dict[str, Dict[str, int]] = {}
            for sku in sku_pool:
                if sku in reverse_idx:
                    for (b_obj, comp_req) in reverse_idx[sku]:
                        bsku = b_obj["skuCode"]
                        if bsku not in candidate_bundles:
                            candidate_bundles[bsku] = comp_req

            if not candidate_bundles:
                continue

            # Sort candidates: prefer bundles with MORE components first
            # (a 4-pack should match before a 2-pack when both fit)
            sorted_candidates = sorted(
                candidate_bundles.items(),
                key=lambda x: len(x[1]),
                reverse=True,
            )

            order_bundle_matches = 0

            # Work on a mutable copy of the pool
            pool = dict(sku_pool)

            for bsku, comp_req in sorted_candidates:
                # Greedy: how many times can this bundle be fulfilled?
                while True:
                    # Check all components are available
                    can_match = True
                    for csku, needed in comp_req.items():
                        if pool.get(csku, 0) < needed:
                            can_match = False
                            break
                    if not can_match:
                        break

                    # Consume components
                    for csku, needed in comp_req.items():
                        pool[csku] -= needed

                    # Calculate revenue for this bundle unit from component prices
                    unit_revenue = sum(
                        sku_price.get(csku, 0) * needed
                        for csku, needed in comp_req.items()
                    )

                    # Record match
                    order_bundle_matches += 1

                    if bsku not in bundle_sales_agg:
                        # Find the bundle obj for metadata
                        b_meta = None
                        for (bobj, _) in reverse_idx.get(list(comp_req.keys())[0], []):
                            if bobj["skuCode"] == bsku:
                                b_meta = bobj
                                break
                        bundle_sales_agg[bsku] = {
                            "skuCode": bsku,
                            "itemName": b_meta["itemName"] if b_meta else bsku,
                            "category": b_meta.get("category", "") if b_meta else "",
                            "mrp": b_meta.get("mrp", 0) if b_meta else 0,
                            "componentCount": b_meta.get("componentCount", 0) if b_meta else 0,
                            "units_sold": 0,
                            "revenue": 0.0,
                            "order_count": 0,
                            "channels": {},
                            "daily": {},
                        }

                    agg = bundle_sales_agg[bsku]
                    agg["units_sold"] += 1
                    agg["revenue"] += unit_revenue

                    # Channel
                    ch = agg["channels"]
                    ch[channel] = ch.get(channel, 0) + 1

                    # Daily
                    if date_key:
                        dl = agg["daily"]
                        dl[date_key] = dl.get(date_key, 0) + 1

            if order_bundle_matches > 0:
                orders_with_bundles += 1
                # Also increment order_count per bundle
                seen_bundles_this_order: Set[str] = set()
                for bsku, _ in sorted_candidates:
                    if bsku in bundle_sales_agg and bsku not in seen_bundles_this_order:
                        if bundle_sales_agg[bsku]["units_sold"] > 0:
                            seen_bundles_this_order.add(bsku)

                for bsku in seen_bundles_this_order:
                    bundle_sales_agg[bsku]["order_count"] += 1

            # Aggregate daily / channel totals
            if date_key and order_bundle_matches > 0:
                if date_key not in daily_agg:
                    daily_agg[date_key] = {"units": 0, "orders": 0}
                daily_agg[date_key]["units"] += order_bundle_matches
                daily_agg[date_key]["orders"] += 1

            if order_bundle_matches > 0:
                if channel not in channel_agg:
                    channel_agg[channel] = {"units": 0, "orders": 0}
                channel_agg[channel]["units"] += order_bundle_matches
                channel_agg[channel]["orders"] += 1

        # ---- 5. Build final response ----
        # Sort bundles by units sold desc
        top_bundles = sorted(
            bundle_sales_agg.values(),
            key=lambda x: x["units_sold"],
            reverse=True,
        )

        # Category breakdown
        category_breakdown: Dict[str, Dict[str, Any]] = {}
        for b in top_bundles:
            cat = b.get("category") or "Unknown"
            if cat not in category_breakdown:
                category_breakdown[cat] = {"units": 0, "revenue": 0.0, "bundle_count": 0}
            category_breakdown[cat]["units"] += b["units_sold"]
            category_breakdown[cat]["revenue"] += b["revenue"]
            category_breakdown[cat]["bundle_count"] += 1

        # Sort category by revenue desc
        category_breakdown = dict(
            sorted(category_breakdown.items(), key=lambda x: x[1]["revenue"], reverse=True)
        )

        # Daily trend sorted by date
        daily_trend = [
            {"date": d, "units": v["units"], "revenue": 0.0, "orders": v["orders"]}
            for d, v in sorted(daily_agg.items())
        ]

        # Fix daily revenue — recompute from bundle-level daily data
        daily_rev_recompute: Dict[str, float] = {}
        for b in top_bundles:
            for d, cnt in b.get("daily", {}).items():
                unit_rev = b["revenue"] / b["units_sold"] if b["units_sold"] > 0 else 0
                daily_rev_recompute[d] = daily_rev_recompute.get(d, 0) + (unit_rev * cnt)
        for dt_entry in daily_trend:
            dt_entry["revenue"] = round(daily_rev_recompute.get(dt_entry["date"], dt_entry["revenue"]), 2)

        # Channel breakdown
        channel_result = {}
        for ch, v in channel_agg.items():
            # Recalculate channel revenue from bundle-level channel data
            ch_rev = sum(
                b["revenue"] / b["units_sold"] * b["channels"].get(ch, 0)
                for b in top_bundles
                if b["units_sold"] > 0 and ch in b.get("channels", {})
            )
            channel_result[ch] = {
                "units": v["units"],
                "revenue": round(ch_rev, 2),
                "orders": v["orders"],
            }
        channel_result = dict(
            sorted(channel_result.items(), key=lambda x: x[1]["revenue"], reverse=True)
        )

        total_bundle_units = sum(b["units_sold"] for b in top_bundles)
        total_bundle_revenue = round(sum(b["revenue"] for b in top_bundles), 2)
        elapsed = round(time_module.time() - start, 1)

        # Clean bundle objects for response (remove internal daily/channels detail)
        bundle_sales_list = []
        for b in top_bundles:
            bundle_sales_list.append({
                "skuCode": b["skuCode"],
                "itemName": b["itemName"],
                "category": b["category"],
                "mrp": b["mrp"],
                "componentCount": b["componentCount"],
                "units_sold": b["units_sold"],
                "revenue": round(b["revenue"], 2),
                "order_count": b["order_count"],
                "avg_selling_price": round(b["revenue"] / b["units_sold"], 2) if b["units_sold"] > 0 else 0,
                "channels": b.get("channels", {}),
            })

        logger.info(
            f"Bundle Sales Analysis done in {elapsed}s — "
            f"{len(orders)} orders, {orders_with_bundles} with bundles, "
            f"{total_bundle_units} bundle units, ₹{total_bundle_revenue} revenue"
        )

        return {
            "success": True,
            "bundle_sales": bundle_sales_list,
            "daily_trend": daily_trend,
            "category_breakdown": category_breakdown,
            "channel_breakdown": channel_result,
            "summary": {
                "total_orders": len(orders),
                "orders_with_bundles": orders_with_bundles,
                "total_bundle_units": total_bundle_units,
                "total_bundle_revenue": total_bundle_revenue,
                "unique_bundles_sold": len(bundle_sales_list),
                "bundle_attach_rate": round(
                    orders_with_bundles / len(orders) * 100, 1
                ) if orders else 0,
                "avg_revenue_per_bundle": round(
                    total_bundle_revenue / total_bundle_units, 2
                ) if total_bundle_units > 0 else 0,
                "analysis_time": elapsed,
            },
        }


    # ── Return Export Job (Tally Return GST Report 3.0) ──────────────

    RETURN_EXPORT_COLUMNS = [
        "invoiceDate", "saleOrderCode", "invoiceCode", "channelName",
        "channelLedgerName", "productCode", "productSKU", "QTY",
        "unitPrice", "Currency", "currencyConversionRate", "total",
        "customerName", "shippingAddressName", "shippingAddressLine1",
        "shippingAddressLine2", "shippingAddressCity",
        "shippingAddressState", "shippingAddressCountry",
        "shippingAddressPincode", "shippingAddressPhone",
        "shippingProvider", "trackingNumber", "sales", "salesLedger",
        "cgst", "cgstRate", "sgst", "sgstRate", "igst", "igstRate",
        "utgst", "utgstRate", "cess", "cessRate", "OtherCharges",
        "OtherChargesLedger", "OtherCharges1", "OtherChargesLedger1",
        "Servicetax", "ServicetaxLedger", "discountLedger",
        "discountAmount", "imei", "godDown", "dispatchdate",
        "narration", "entity", "voucherTypeName", "tin", "original",
        "original1", "channelInvoiceDate", "channelState",
        "channelPartyGSTIN", "customerGSTIN", "billingPartyCode",
        "taxVerification", "gstregistrationtype", "rpcode", "irn",
        "acknowledgementNumber", "productHSNCode", "returnType",
    ]

    async def _create_return_export_job(
        self, from_date: datetime, to_date: datetime
    ) -> Optional[str]:
        """
        Create a Unicommerce export job for Tally Return GST Report 3.0.
        Returns the jobCode on success, None on failure.
        Uses dateRange filter with epoch milliseconds.
        """
        url = f"{self.base_url}/export/job/create"

        start_ms = int(from_date.timestamp() * 1000)
        end_ms = int(to_date.timestamp() * 1000)

        def _build_payload(s_ms: int, e_ms: int) -> dict:
            return {
                "exportJobTypeName": "Tally Return GST Report 3.0",
                "frequency": "ONETIME",
                "exportColums": self.RETURN_EXPORT_COLUMNS,
                "exportFilters": [
                    {
                        "id": "dateRange",
                        "dateRange": {
                            "start": s_ms,
                            "end": e_ms,
                        },
                    }
                ],
            }

        payload = _build_payload(start_ms, end_ms)

        MAX_RETRIES = 3
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    headers = await self._get_headers()
                    headers["Facility"] = "anthrilo"

                    response = await client.post(url, json=payload, headers=headers)

                    if response.status_code in (401, 403):
                        try:
                            auth_error_body = response.json()
                        except Exception:
                            auth_error_body = response.text[:500]
                        logger.warning(
                            f"Return Export: Job creation auth HTTP {response.status_code} "
                            f"attempt {attempt}/{MAX_RETRIES}: {auth_error_body}"
                        )
                        self.token_manager.invalidate_token()
                        await self.token_manager.get_valid_token()
                        headers = await self._get_headers()
                        headers["Facility"] = "anthrilo"
                        response = await client.post(url, json=payload, headers=headers)

                        if response.status_code in (401, 403):
                            if attempt < MAX_RETRIES:
                                await asyncio.sleep(3 * attempt)
                                continue
                            try:
                                auth_error_body = response.json()
                            except Exception:
                                auth_error_body = response.text[:500]
                            logger.error(
                                f"Return Export: Job creation auth still failing HTTP {response.status_code}: "
                                f"{auth_error_body}"
                            )
                            return None

                    if response.status_code == 400:
                        try:
                            error_body = response.json()
                        except Exception:
                            error_body = response.text[:500]
                        logger.warning(
                            f"Return Export: Job creation HTTP 400 attempt {attempt}/{MAX_RETRIES}: {error_body}"
                        )
                        if attempt < MAX_RETRIES:
                            self.token_manager.invalidate_token()
                            await asyncio.sleep(3 * attempt)
                            continue
                        return None

                    if response.status_code >= 500:
                        logger.warning(
                            f"Return Export: Job creation HTTP {response.status_code} attempt {attempt}/{MAX_RETRIES}"
                        )
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(3 * attempt)
                            continue
                        return None

                    if response.status_code >= 400:
                        try:
                            error_body = response.json()
                        except Exception:
                            error_body = response.text[:500]
                        logger.error(
                            f"Return Export: Job creation HTTP {response.status_code}: {error_body}"
                        )
                        return None

                    data = response.json()

                    if data.get("successful"):
                        job_code = data.get("jobCode")
                        logger.info(f"Return Export: Job created successfully {job_code}")
                        return job_code
                    else:
                        errors = data.get("errors", [])
                        msg = data.get("message", "Unknown error")

                        already_running = any(
                            str(e.get("code", "")) == "100014"
                            or "already" in str(e.get("description", "")).lower()
                            for e in errors
                        ) if errors else "already" in msg.lower()

                        if already_running:
                            logger.warning(
                                "Return Export: Duplicate job detected (100014), offsetting date range"
                            )
                            for retry in range(5):
                                offset_start = start_ms + retry + 1
                                new_payload = _build_payload(offset_start, end_ms)
                                await asyncio.sleep(2)
                                headers = await self._get_headers()
                                headers["Facility"] = "anthrilo"
                                retry_resp = await client.post(url, json=new_payload, headers=headers)
                                retry_data = retry_resp.json()
                                if retry_data.get("successful"):
                                    jc = retry_data.get("jobCode")
                                    logger.info(f"Return Export: Job created on offset retry {retry+1}: {jc}")
                                    return jc
                                logger.info(f"Return Export: Offset retry {retry+1}/5 — {retry_data.get('errors', [])}")
                            logger.error("Return Export: Job still busy after all retries")
                            return None

                        logger.error(f"Return Export: Job creation failed: {msg} | errors={errors}")
                        return None

            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as e:
                logger.warning(
                    f"Return Export: Job creation timeout attempt {attempt}/{MAX_RETRIES}: {type(e).__name__}"
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(3 * attempt)
                    continue
                return None
            except Exception as e:
                logger.error(f"Return Export: Job creation exception: {e}", exc_info=True)
                return None

        return None

    async def _download_parse_return_export(
        self,
        download_url: str,
        include_rows: bool = False,
    ) -> Any:
        """
        Download Tally Return GST Report CSV and parse into return item records.
        Each CSV row represents one returned item with channel, SKU, price, qty,
        return type, GST breakdown, etc.
        """
        try:
            csv_text = await self._download_csv_text(download_url, label="Return Export")
            if csv_text is None:
                logger.error("Return export: Failed to download CSV after retries")
                if include_rows:
                    return [], [], []
                return []

            if not csv_text or not csv_text.strip():
                logger.warning("Return Export: Downloaded CSV is empty")
                if include_rows:
                    return [], [], []
                return []

            reader = csv.DictReader(io.StringIO(csv_text))
            fieldnames = reader.fieldnames or []
            logger.info(f"Return Export: CSV columns ({len(fieldnames)}): {fieldnames[:15]}...")

            items = []
            raw_rows: List[Dict[str, Any]] = []
            row_count = 0

            for row in reader:
                row_count += 1
                if include_rows:
                    raw_rows.append(dict(row))

                sale_order_code = (
                    row.get("Sale Order Number")
                    or row.get("Sale Order Code")
                    or row.get("saleOrderCode")
                    or ""
                ).strip()

                channel = (
                    row.get("Channel entry")
                    or row.get("Channel Name")
                    or row.get("channelName")
                    or "UNKNOWN"
                ).strip().replace(" ", "_")

                sku = (
                    row.get("Product SKU Code")
                    or row.get("Product SKU")
                    or row.get("productSKU")
                    or ""
                ).strip()

                invoice_code = (
                    row.get("Invoice number")
                    or row.get("Invoice Code")
                    or row.get("invoiceCode")
                    or ""
                ).strip()

                return_type_raw = (
                    row.get("Return Type")
                    or row.get("returnType")
                    or ""
                ).strip().upper()

                try:
                    qty = int(float(
                        row.get("Qty")
                        or row.get("QTY")
                        or row.get("quantity")
                        or 1
                    ))
                except (ValueError, TypeError):
                    qty = 1

                try:
                    unit_price = float(
                        row.get("Unit Price")
                        or row.get("unitPrice")
                        or 0
                    )
                except (ValueError, TypeError):
                    unit_price = 0.0

                try:
                    total = float(
                        row.get("Total")
                        or row.get("total")
                        or 0
                    )
                except (ValueError, TypeError):
                    total = unit_price * qty

                try:
                    sales_value = float(
                        row.get("Sales")
                        or row.get("sales")
                        or 0
                    )
                except (ValueError, TypeError):
                    sales_value = 0.0

                # Classify RTO vs CIR
                # Actual UC values: "COURIER RETURN" → RTO, "CUSTOMER RETURN" → CIR
                if "COURIER" in return_type_raw or "RTO" in return_type_raw:
                    classified_type = "RTO"
                elif "CUSTOMER" in return_type_raw or "CIR" in return_type_raw or "REVERSE" in return_type_raw:
                    classified_type = "CIR"
                else:
                    classified_type = "RTO" if return_type_raw else "UNKNOWN"

                item_name = (
                    row.get("Product Name")
                    or row.get("Product Code")
                    or row.get("productCode")
                    or sku
                )

                items.append({
                    "saleOrderCode": sale_order_code,
                    "invoiceCode": invoice_code,
                    "channel": channel,
                    "sku": sku,
                    "itemName": item_name,
                    "quantity": qty,
                    "unitPrice": unit_price,
                    "total": total,
                    "salesValue": sales_value,
                    "returnType": classified_type,
                    "returnTypeRaw": return_type_raw,
                })

            logger.info(
                f"Return Export: Parsed {row_count} CSV rows → {len(items)} return items"
            )
            if include_rows:
                return items, raw_rows, fieldnames
            return items

        except Exception as e:
            logger.error(f"Return Export: Download/parse failed: {e}", exc_info=True)
            if include_rows:
                return [], [], []
            return []

    # Maximum days per return export chunk — UC returns empty for very large ranges
    RETURN_EXPORT_MAX_CHUNK_DAYS = 30

    async def fetch_returns_via_export(
        self, from_date: datetime, to_date: datetime
    ) -> Dict[str, Any]:
        """
        Fetch returns via the Export Job API (Tally Return GST Report 3.0).

        For date ranges > RETURN_EXPORT_MAX_CHUNK_DAYS, automatically splits
        into smaller chunks and merges results. Each chunk acquires _export_lock
        since UC allows only one export at a time.

        Returns dict with: successful, items (list of return item records),
        total_items, total_time, method.
        """
        total_days = (to_date - from_date).total_seconds() / 86400

        if total_days <= self.RETURN_EXPORT_MAX_CHUNK_DAYS:
            # Small range — single export job
            async with self._export_lock:
                return await self._fetch_returns_via_export_inner(from_date, to_date)

        # Large range — split into chunks
        logger.info(
            f"Return Export: Range is {total_days:.0f} days, "
            f"splitting into {self.RETURN_EXPORT_MAX_CHUNK_DAYS}-day chunks"
        )

        all_items = []
        chunk_start = from_date
        chunk_num = 0
        total_start = time_module.time()

        while chunk_start < to_date:
            chunk_num += 1
            chunk_end = min(
                chunk_start + timedelta(days=self.RETURN_EXPORT_MAX_CHUNK_DAYS),
                to_date,
            )

            logger.info(
                f"Return Export: Chunk {chunk_num} — "
                f"{chunk_start.isoformat()} → {chunk_end.isoformat()}"
            )

            try:
                async with self._export_lock:
                    result = await self._fetch_returns_via_export_inner(
                        chunk_start, chunk_end
                    )

                if result.get("successful"):
                    chunk_items = result.get("items", [])
                    all_items.extend(chunk_items)
                    logger.info(
                        f"Return Export: Chunk {chunk_num} returned {len(chunk_items)} items"
                    )
                else:
                    logger.warning(
                        f"Return Export: Chunk {chunk_num} failed: "
                        f"{result.get('error', 'unknown')}"
                    )
            except Exception as e:
                logger.warning(
                    f"Return Export: Chunk {chunk_num} exception: {e}",
                    exc_info=True,
                )

            chunk_start = chunk_end

        total_time = time_module.time() - total_start
        logger.info(
            f"Return Export: All {chunk_num} chunks done — "
            f"{len(all_items)} total items in {total_time:.1f}s"
        )

        return {
            "successful": True,
            "items": all_items,
            "total_items": len(all_items),
            "total_time": round(total_time, 2),
            "method": "export_job_tally_return",
            "chunks": chunk_num,
        }

    async def _fetch_returns_via_export_inner(
        self, from_date: datetime, to_date: datetime
    ) -> Dict[str, Any]:
        """Inner return export fetch — runs under _export_lock."""
        start_time = time_module.time()
        logger.info("Starting return export job fetch")
        logger.info(f"  Range: {from_date.isoformat()} → {to_date.isoformat()}")

        sync_log_id = self._create_sync_log_record(
            sync_type="export_job",
            entity="sales_returns",
            details={
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
            },
        )

        export_job_id = self._create_export_job_record(
            export_type="return_gst",
            requested_from=from_date,
            requested_to=to_date,
            requested_columns=self.RETURN_EXPORT_COLUMNS,
        )

        try:
            # Step 1: Create export job
            job_code = await self._create_return_export_job(from_date, to_date)
            create_time = time_module.time() - start_time

            if not job_code:
                logger.error("Return Export: Job creation failed")
                self._update_export_job_record(
                    export_job_id,
                    status="failed",
                    error_message="Return export job creation failed",
                    completed_at=datetime.utcnow(),
                )
                self._update_sync_log_record(
                    sync_log_id,
                    status="failed",
                    failed_count=1,
                    error_message="Return export job creation failed",
                    completed_at=datetime.utcnow(),
                )
                return {
                    "successful": False,
                    "error": "Return export job creation failed",
                    "items": [],
                    "total_items": 0,
                }

            self._update_export_job_record(
                export_job_id,
                job_code=job_code,
                status="running",
            )

            logger.info(f"  Step 1 done in {create_time:.1f}s — job={job_code}")

            # Step 2: Poll until complete (reuse existing _poll_export_status)
            download_url = await self._poll_export_status(job_code)
            poll_time = time_module.time() - start_time - create_time

            if not download_url:
                logger.error("Return Export: Job failed or timed out")
                self._update_export_job_record(
                    export_job_id,
                    status="failed",
                    error_message="Return export job timed out or failed",
                    completed_at=datetime.utcnow(),
                )
                self._update_sync_log_record(
                    sync_log_id,
                    status="failed",
                    failed_count=1,
                    error_message="Return export job timed out or failed",
                    completed_at=datetime.utcnow(),
                )
                return {
                    "successful": False,
                    "error": "Return export job timed out or failed",
                    "items": [],
                    "total_items": 0,
                }

            logger.info(f"  Step 2 done in {poll_time:.1f}s — file ready")

            # Step 3: Download and parse CSV
            items, raw_rows, csv_headers = await self._download_parse_return_export(
                download_url,
                include_rows=True,
            )

            archived_rows, file_checksum = self._archive_export_rows(
                export_job_id,
                "return_gst",
                raw_rows,
            )
            normalized_rows = self._upsert_sales_return_rows(raw_rows)

            self._update_export_job_record(
                export_job_id,
                status="completed",
                download_url=download_url,
                csv_headers=csv_headers,
                file_checksum=file_checksum,
                total_csv_rows=len(raw_rows),
                parsed_entities=normalized_rows,
                completed_at=datetime.utcnow(),
            )

            self._update_sync_log_record(
                sync_log_id,
                status="completed",
                processed_count=normalized_rows,
                failed_count=max(0, len(raw_rows) - normalized_rows),
                completed_at=datetime.utcnow(),
                details={
                    "from_date": from_date.isoformat(),
                    "to_date": to_date.isoformat(),
                    "export_job_id": export_job_id,
                    "archived_rows": archived_rows,
                    "normalized_rows": normalized_rows,
                    "total_csv_rows": len(raw_rows),
                },
            )

            download_time = time_module.time() - start_time - create_time - poll_time
            total_time = time_module.time() - start_time

            logger.info(
                f"  Step 3 done in {download_time:.1f}s — {len(items)} return items"
            )
            logger.info(
                f"Return Export done: {len(items)} items in {total_time:.1f}s total"
            )

            return {
                "successful": True,
                "items": items,
                "total_items": len(items),
                "export_job_id": export_job_id,
                "archived_rows": archived_rows,
                "normalized_rows": normalized_rows,
                "phase1_time": round(create_time + poll_time, 2),
                "phase2_time": round(download_time, 2),
                "total_time": round(total_time, 2),
                "method": "export_job_tally_return",
            }

        except Exception as e:
            total_time = time_module.time() - start_time
            logger.error(
                f"Return Export: Failed after {total_time:.1f}s: {e}", exc_info=True
            )
            self._update_export_job_record(
                export_job_id,
                status="failed",
                error_message=f"Return export failed: {str(e)}",
                completed_at=datetime.utcnow(),
            )
            self._update_sync_log_record(
                sync_log_id,
                status="failed",
                failed_count=1,
                error_message=f"Return export failed: {str(e)}",
                completed_at=datetime.utcnow(),
            )
            return {
                "successful": False,
                "error": f"Return export failed: {str(e)}",
                "items": [],
                "total_items": 0,
            }


# Singleton factory
_service_instance: Optional[UnicommerceService] = None


def get_unicommerce_service() -> UnicommerceService:
    """Get or create the Unicommerce service singleton"""
    global _service_instance
    if _service_instance is None:
        _service_instance = UnicommerceService()
    return _service_instance
