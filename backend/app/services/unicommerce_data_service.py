"""DB-first read service for Unicommerce sales and inventory data."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import Float, and_, bindparam, case, func, or_, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.export_models import (
    ExportJob,
    ExportRow,
    InventorySnapshotRecord,
    ShopifyMasterData,
    SalesOrderRecord,
    SalesReturnRecord,
)
from app.db.models import ProductMaster
from app.services.cache_service import CacheService
from app.services.unicommerce import get_unicommerce_service
from app.utils.timezone_utils import IST, normalize_date_range_ist


logger = logging.getLogger(__name__)


class UnicommerceDataService:
    """Serves Unicommerce data from DB with raw-row fallback."""

    EXCLUDED_STATUSES = {
        "CANCELLED",
        "CANCELED",
        "RETURNED",
        "REFUNDED",
        "FAILED",
        "UNFULFILLABLE",
        "ERROR",
        "PENDING_VERIFICATION",
    }

    def __init__(self) -> None:
        self.uc_service = get_unicommerce_service()

    def _get_db(self) -> Session:
        return SessionLocal()

    @staticmethod
    def _emit_progress(
        progress_cb: Optional[Callable[[int, str], None]],
        percent: int,
        label: str,
    ) -> None:
        if progress_cb is None:
            return
        try:
            progress_cb(max(0, min(100, int(percent))), label)
        except Exception:
            pass

    @staticmethod
    def _safe_str(value: Any) -> str:
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(float(str(value).replace(",", "").strip()))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
        try:
            if value is None or value == "":
                return default
            if isinstance(value, Decimal):
                return value
            return Decimal(str(value).replace(",", "").strip())
        except (TypeError, ValueError, InvalidOperation):
            return default

    @staticmethod
    def _to_money_float(value: Decimal) -> float:
        return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _resolve_inventory_snapshot_table_name(db: Session) -> Optional[str]:
        """Resolve the inventory snapshot source table, preferring the required singular name."""
        try:
            if db.execute(text("SELECT to_regclass('public.inventory_snapshot')")).scalar():
                return "inventory_snapshot"
            if db.execute(text("SELECT to_regclass('public.inventory_snapshots')")).scalar():
                return "inventory_snapshots"
        except Exception:
            return None
        return None

    def _fetch_inventory_snapshot_map_by_sku(self, skus: List[str]) -> Dict[str, Dict[str, int]]:
        """Load SKU inventory map using direct DB query from inventory snapshot table."""
        clean_skus = [self._safe_str(sku) for sku in (skus or []) if self._safe_str(sku)]
        if not clean_skus:
            return {}

        db = self._get_db()
        try:
            table_name = self._resolve_inventory_snapshot_table_name(db)
            if not table_name:
                return {}

            # Required source query shape:
            # SELECT sku, available_qty, reserved_qty FROM inventory_snapshot;
            stmt = text(
                f"""
                SELECT
                    sku,
                    available_qty,
                    reserved_qty
                FROM {table_name}
                WHERE sku IN :skus
                """
            ).bindparams(bindparam("skus", expanding=True))

            rows = db.execute(stmt, {"skus": clean_skus}).mappings().all()
            inventory_map: Dict[str, Dict[str, int]] = {}
            for row in rows:
                sku_code = self._safe_str(row.get("sku"))
                if not sku_code:
                    continue

                bucket = inventory_map.setdefault(
                    sku_code,
                    {
                        "good_inventory": 0,
                        "virtual_inventory": 0,
                    },
                )
                bucket["good_inventory"] += self._safe_int(row.get("available_qty"), default=0)
                bucket["virtual_inventory"] += self._safe_int(row.get("reserved_qty"), default=0)

            return inventory_map
        finally:
            db.close()

    @staticmethod
    def _safe_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value

        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y"}:
            return True
        if text in {"0", "false", "no", "n"}:
            return False
        return default

    @staticmethod
    def _normalize_dt(value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _db_filter_dt(value: Optional[datetime]) -> Optional[datetime]:
        """Convert aware UTC datetimes to naive UTC for timestamp-without-time-zone DB filters."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _pick(payload: Dict[str, Any], *keys: str) -> Optional[Any]:
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return value

        lowered = {str(k).strip().lower(): v for k, v in payload.items()}
        for key in keys:
            value = lowered.get(str(key).strip().lower())
            if value not in (None, ""):
                return value

        return None

    @staticmethod
    def _normalize_return_type(value: str) -> str:
        text = str(value or "").strip().upper()
        if not text:
            return "UNKNOWN"
        if "COURIER" in text or "RTO" in text:
            return "RTO"
        if "CUSTOMER" in text or "CIR" in text or "REVERSE" in text:
            return "CIR"
        return text

    @staticmethod
    def _parse_return_report_dt(value: Any) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def _resolve_range(
        self,
        period: str,
        from_date: Optional[datetime],
        to_date: Optional[datetime],
    ) -> Tuple[datetime, datetime, str]:
        def _normalize_window(start_dt: datetime, end_dt: datetime) -> Tuple[datetime, datetime]:
            start_utc, end_exclusive_utc, _ = normalize_date_range_ist(
                start_dt,
                end_dt,
                closed_window_mode=False,
            )
            return self._db_filter_dt(start_utc), self._db_filter_dt(end_exclusive_utc)

        if period == "today":
            start, end = self.uc_service.get_today_range()
            # Preserve the partial-day cutoff for "today".
            # Normalizing to IST day bounds would incorrectly widen this to the full day.
            return self._db_filter_dt(start), self._db_filter_dt(end + timedelta(microseconds=1)), "today"

        if period == "yesterday":
            start, end = self.uc_service.get_yesterday_range()
            norm_start, norm_end_exclusive = _normalize_window(start, end)
            return norm_start, norm_end_exclusive, "yesterday"

        if period == "last_7_days":
            start, end = self.uc_service.get_last_n_days_range(7)
            norm_start, norm_end_exclusive = _normalize_window(start, end)
            return norm_start, norm_end_exclusive, "last_7_days"

        if period == "last_30_days":
            start, end = self.uc_service.get_last_n_days_range(30)
            norm_start, norm_end_exclusive = _normalize_window(start, end)
            return norm_start, norm_end_exclusive, "last_30_days"

        if from_date and to_date:
            norm_start, norm_end_exclusive, _ = normalize_date_range_ist(
                from_date,
                to_date,
                closed_window_mode=False,
            )
            return self._db_filter_dt(norm_start), self._db_filter_dt(norm_end_exclusive), "custom"

        start, end = self.uc_service.get_today_range()
        norm_start, norm_end_exclusive = _normalize_window(start, end)
        return norm_start, norm_end_exclusive, "today"

    def _raw_line_rows_from_sales_payloads(
        self,
        payloads: List[Dict[str, Any]],
        from_date: datetime,
        to_date: datetime,
    ) -> List[Dict[str, Any]]:
        line_rows: List[Dict[str, Any]] = []

        for payload in payloads:
            order_id = self._safe_str(
                self._pick(payload, "Sale Order Code", "saleOrderCode", "code")
            )
            if not order_id:
                continue

            order_date = self.uc_service._parse_business_order_datetime(payload)
            order_date = self._normalize_dt(order_date)

            if order_date and (order_date < from_date or order_date >= to_date):
                continue

            qty = self._safe_int(
                self._pick(
                    payload,
                    "Quantity",
                    "Qty",
                    "QTY",
                    "quantity",
                    "Sale Order Item Quantity",
                ),
                default=1,
            )
            if qty <= 0:
                qty = 1

            line_rows.append(
                {
                    "order_id": order_id,
                    "status": self._safe_str(
                        self._pick(payload, "Sale Order Status", "status", "saleOrderStatus")
                    ).upper(),
                    "channel": self._safe_str(
                        self._pick(payload, "Channel Name", "channel")
                    ).replace(" ", "_"),
                    "qty": qty,
                    "selling_price": self._safe_decimal(
                        self._pick(payload, "Selling Price", "sellingPrice")
                    ),
                    "order_date": order_date,
                    "sku": self._safe_str(
                        self._pick(payload, "Item SKU Code", "skuCode", "itemSku")
                    ),
                    "product_name": self._safe_str(
                        self._pick(payload, "Item Details", "itemDetails", "itemTypeName")
                    ),
                    "cod": self._safe_bool(
                        self._pick(payload, "COD", "cod", "cashOnDelivery"),
                        default=False,
                    ),
                }
            )

        return line_rows

    def _orders_from_line_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        orders_map: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            order_id = self._safe_str(row.get("order_id"))
            if not order_id:
                continue

            created_dt = self._normalize_dt(row.get("order_date"))

            order = orders_map.setdefault(
                order_id,
                {
                    "code": order_id,
                    "displayOrderCode": order_id,
                    "status": self._safe_str(row.get("status")).upper(),
                    "channel": self._safe_str(row.get("channel") or "UNKNOWN"),
                    "_created_dt": created_dt,
                    "cashOnDelivery": self._safe_bool(row.get("cod"), default=False),
                    "cod": self._safe_bool(row.get("cod"), default=False),
                    "items": [],
                },
            )

            if not order.get("status"):
                order["status"] = self._safe_str(row.get("status")).upper()
            if order.get("channel") in (None, "", "UNKNOWN") and row.get("channel"):
                order["channel"] = self._safe_str(row.get("channel"))
            if order.get("_created_dt") is None and created_dt is not None:
                order["_created_dt"] = created_dt

            qty = int(row.get("qty") or 1)
            if qty <= 0:
                qty = 1

            price = self._safe_decimal(row.get("selling_price"))
            sku = self._safe_str(row.get("sku"))
            name = self._safe_str(row.get("product_name")) or sku

            order["items"].append(
                {
                    "code": self._safe_str(row.get("sale_order_item_code")),
                    "itemSku": sku,
                    "sku": sku,
                    "itemName": name,
                    "bundle_sku_code_number": self._safe_str(row.get("bundle_sku_code_number")),
                    "sellingPrice": self._to_money_float(price),
                    "selling_price": self._to_money_float(price),
                    "quantity": qty,
                    "size": "",
                }
            )

        orders: List[Dict[str, Any]] = []
        for _, order in orders_map.items():
            items = order.get("items", [])
            total_qty = sum(int(item.get("quantity") or 0) for item in items)
            selling_total = sum(
                self._safe_decimal(item.get("sellingPrice") or item.get("selling_price"))
                * Decimal(int(item.get("quantity") or 0))
                for item in items
            )
            include_in_revenue = self._safe_str(order.get("status")).upper() not in self.EXCLUDED_STATUSES
            net_revenue = selling_total if include_in_revenue else Decimal("0")

            created_dt = order.get("_created_dt")
            created_value = created_dt.isoformat() if isinstance(created_dt, datetime) else ""

            orders.append(
                {
                    "code": order.get("code"),
                    "displayOrderCode": order.get("displayOrderCode"),
                    "status": order.get("status") or "",
                    "channel": order.get("channel") or "UNKNOWN",
                    "selling_price": self._to_money_float(selling_total),
                    "total_selling_price": self._to_money_float(selling_total),
                    "net_revenue": self._to_money_float(net_revenue),
                    "created": created_value,
                    "displayOrderDateTime": created_value,
                    "item_count": len(items),
                    "quantity": total_qty,
                    "include_in_revenue": include_in_revenue,
                    "cashOnDelivery": bool(order.get("cashOnDelivery")),
                    "cod": bool(order.get("cod")),
                    "items": items,
                }
            )

        def _sort_key(entry: Dict[str, Any]) -> float:
            created = entry.get("created")
            if not created:
                return 0.0
            try:
                parsed = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                else:
                    parsed = parsed.astimezone(timezone.utc)
                return parsed.timestamp()
            except ValueError:
                return 0.0

        orders.sort(key=_sort_key, reverse=True)
        return orders

    def _legacy_orders_from_orders(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        legacy_orders: List[Dict[str, Any]] = []

        for order in orders:
            sale_items: List[Dict[str, Any]] = []
            for item in order.get("items", []):
                selling_price = self._safe_decimal(item.get("sellingPrice") or item.get("selling_price"))
                quantity = int(item.get("quantity") or 0)
                if quantity <= 0:
                    quantity = 1

                item_name = self._safe_str(item.get("itemName") or item.get("name") or item.get("sku"))
                sale_items.append(
                    {
                        "code": self._safe_str(item.get("code")),
                        "itemSku": self._safe_str(item.get("itemSku") or item.get("sku")),
                        "itemName": item_name,
                        "itemTypeName": item_name,
                        "bundleSkuCodeNumber": self._safe_str(
                            item.get("bundle_sku_code_number") or item.get("bundleSkuCodeNumber")
                        ),
                        "quantity": quantity,
                        "sellingPrice": self._to_money_float(selling_price),
                        "maxRetailPrice": self._to_money_float(selling_price),
                        "size": self._safe_str(item.get("size")),
                    }
                )

            legacy_orders.append(
                {
                    "code": self._safe_str(order.get("code")),
                    "displayOrderCode": self._safe_str(order.get("displayOrderCode") or order.get("code")),
                    "status": self._safe_str(order.get("status")),
                    "channel": self._safe_str(order.get("channel") or "UNKNOWN"),
                    "created": self._safe_str(order.get("created")),
                    "displayOrderDateTime": self._safe_str(
                        order.get("displayOrderDateTime") or order.get("created")
                    ),
                    "cod": bool(order.get("cod")),
                    "cashOnDelivery": bool(order.get("cashOnDelivery") or order.get("cod")),
                    "saleOrderItems": sale_items,
                }
            )

        return legacy_orders

    def _order_detail_from_normalized_rows(
        self,
        order_code: str,
        records: List[SalesOrderRecord],
    ) -> Dict[str, Any]:
        first = records[0]
        created_dt = self._normalize_dt(first.order_date or first.created_at)
        created_value = created_dt.isoformat() if created_dt else ""

        sale_items: List[Dict[str, Any]] = []
        total_quantity = 0
        for record in records:
            raw = dict(record.raw_data or {})
            quantity = int(record.qty or 0)
            if quantity <= 0:
                quantity = 1
            total_quantity += quantity

            item_name = self._safe_str(
                self._pick(raw, "Item Details", "itemDetails", "itemTypeName")
                or record.product_name
                or record.sku
            )
            selling_price = self._safe_decimal(record.selling_price)
            mrp = self._safe_decimal(
                self._pick(raw, "MRP", "Maximum Retail Price", "maxRetailPrice"),
                default=selling_price,
            )

            sale_items.append(
                {
                    "code": self._safe_str(record.sale_order_item_code),
                    "itemSku": self._safe_str(record.sku),
                    "itemName": item_name,
                    "itemTypeName": item_name,
                    "bundleSkuCodeNumber": self._safe_str(
                        self._pick(raw, "bundleSkuCodeNumber", "Bundle SKU")
                    ),
                    "quantity": quantity,
                    "sellingPrice": self._to_money_float(selling_price),
                    "maxRetailPrice": self._to_money_float(mrp),
                    "discount": self._to_money_float(
                        self._safe_decimal(self._pick(raw, "Discount", "discount"))
                    ),
                    "taxAmount": self._to_money_float(
                        self._safe_decimal(self._pick(raw, "Tax Amount", "taxAmount"))
                    ),
                    "refundAmount": self._to_money_float(
                        self._safe_decimal(self._pick(raw, "Refund Amount", "refundAmount"))
                    ),
                    "size": self._safe_str(self._pick(raw, "Size", "size")),
                }
            )

        cod = any(
            self._safe_bool((record.raw_data or {}).get("COD") or (record.raw_data or {}).get("cod"), False)
            for record in records
        )

        return {
            "code": order_code,
            "displayOrderCode": order_code,
            "status": self._safe_str(first.status),
            "channel": self._safe_str(first.channel),
            "created": created_value,
            "displayOrderDateTime": created_value,
            "cashOnDelivery": cod,
            "cod": cod,
            "totalQuantity": total_quantity,
            "saleOrderItems": sale_items,
        }

    def _aggregate_sales_rows(
        self,
        rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        orders_map: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            order_id = self._safe_str(row.get("order_id"))
            if not order_id:
                continue

            order = orders_map.setdefault(
                order_id,
                {
                    "code": order_id,
                    "status": self._safe_str(row.get("status")).upper(),
                    "channel": self._safe_str(row.get("channel") or "UNKNOWN"),
                    "created": row.get("order_date"),
                    "selling_price": Decimal("0"),
                    "discount": Decimal("0"),
                    "tax": Decimal("0"),
                    "refund": Decimal("0"),
                    "item_count": 0,
                    "quantity": 0,
                },
            )

            # Skip FABRIC category items (non-product entries)
            category_val = self._safe_str(row.get("category") or "").upper()
            if category_val == "FABRIC":
                continue

            qty = int(row.get("qty") or 1)
            if qty <= 0:
                qty = 1

            item_price = self._safe_decimal(row.get("selling_price"))
            item_discount = self._safe_decimal(row.get("discount"))
            item_tax = self._safe_decimal(row.get("tax"))
            item_refund = self._safe_decimal(row.get("refund"))
            # Unicommerce export rows already store row totals for selling/discount/tax/refund.
            # Multiplying by qty inflates revenue whenever one row represents multiple units.
            order["selling_price"] += item_price
            order["discount"] += item_discount
            order["tax"] += item_tax
            order["refund"] += item_refund
            order["item_count"] += 1
            order["quantity"] += qty

            if not order.get("status"):
                order["status"] = self._safe_str(row.get("status")).upper()
            if not order.get("created") and row.get("order_date"):
                order["created"] = row.get("order_date")
            if (order.get("channel") in (None, "", "UNKNOWN")) and row.get("channel"):
                order["channel"] = self._safe_str(row.get("channel"))

        order_list = list(orders_map.values())
        total_orders = len(order_list)
        valid_orders = 0
        excluded_orders = 0
        total_revenue = Decimal("0")
        total_items = 0

        total_discount = Decimal("0")
        total_tax = Decimal("0")
        total_refund = Decimal("0")

        channel_breakdown: Dict[str, Dict[str, Any]] = {}
        status_breakdown: Dict[str, int] = {}
        daily_map: Dict[str, Dict[str, Any]] = {}

        for order in order_list:
            status = self._safe_str(order.get("status")).upper()
            channel = self._safe_str(order.get("channel") or "UNKNOWN")
            revenue = self._safe_decimal(order.get("selling_price"))
            discount = self._safe_decimal(order.get("discount"))
            tax = self._safe_decimal(order.get("tax"))
            refund = self._safe_decimal(order.get("refund"))
            qty = int(order.get("quantity") or 0)
            item_count = int(order.get("item_count") or 0)
            created = order.get("created")

            status_breakdown[status] = status_breakdown.get(status, 0) + 1

            # If an order only contained FABRIC rows (which are excluded above),
            # it should not count toward valid orders (it has no real sellable items).
            if item_count <= 0:
                excluded_orders += 1
                continue

            include = status not in self.EXCLUDED_STATUSES
            if include:
                valid_orders += 1
                total_revenue += revenue
                total_discount += discount
                total_tax += tax
                total_refund += refund
                total_items += item_count

                if channel not in channel_breakdown:
                    channel_breakdown[channel] = {"orders": 0, "revenue": Decimal("0"), "items": 0}
                channel_breakdown[channel]["orders"] += 1
                channel_breakdown[channel]["revenue"] += revenue
                channel_breakdown[channel]["items"] += item_count

                date_key = None
                if isinstance(created, datetime):
                    if created.tzinfo is None:
                        created_utc = created.replace(tzinfo=timezone.utc)
                    else:
                        created_utc = created.astimezone(timezone.utc)
                    date_key = created_utc.astimezone(IST).strftime("%Y-%m-%d")
                elif created:
                    date_key = self._safe_str(created)[:10]

                if date_key:
                    if date_key not in daily_map:
                        daily_map[date_key] = {
                            "date": date_key,
                            "orders": 0,
                            "revenue": Decimal("0"),
                            "items": 0,
                        }
                    daily_map[date_key]["orders"] += 1
                    daily_map[date_key]["revenue"] += revenue
                    daily_map[date_key]["items"] += item_count
            else:
                excluded_orders += 1

        for value in channel_breakdown.values():
            value["revenue"] = self._to_money_float(self._safe_decimal(value["revenue"]))

        daily_breakdown = sorted(daily_map.values(), key=lambda x: x["date"])
        for day in daily_breakdown:
            day["revenue"] = self._to_money_float(self._safe_decimal(day["revenue"]))

        def _sort_key(order: Dict[str, Any]) -> float:
            created_value = order.get("created")
            if isinstance(created_value, datetime):
                if created_value.tzinfo is None:
                    created_value = created_value.replace(tzinfo=timezone.utc)
                return created_value.timestamp()
            return 0.0

        sample_orders = sorted(order_list, key=_sort_key, reverse=True)[:10]

        orders_payload = [
            {
                "code": o["code"],
                "status": o.get("status", ""),
                "channel": o.get("channel", "UNKNOWN"),
                "selling_price": self._to_money_float(self._safe_decimal(o.get("selling_price"))),
                "net_revenue": self._to_money_float(self._safe_decimal(o.get("selling_price"))),
                "created": o.get("created").isoformat() if isinstance(o.get("created"), datetime) else self._safe_str(o.get("created")),
                "item_count": int(o.get("item_count") or 0),
                "quantity": int(o.get("quantity") or 0),
                "include_in_revenue": self._safe_str(o.get("status")).upper() not in self.EXCLUDED_STATUSES,
            }
            for o in sample_orders
        ]

        return {
            "orders": orders_payload,
            "summary": {
                "total_orders": total_orders,
                "valid_orders": valid_orders,
                "excluded_orders": excluded_orders,
                "total_items": total_items,
                "total_revenue": self._to_money_float(total_revenue),
                "total_discount": self._to_money_float(total_discount),
                "total_tax": self._to_money_float(total_tax),
                "total_refund": self._to_money_float(total_refund),
                "avg_order_value": self._to_money_float(total_revenue / Decimal(valid_orders)) if valid_orders > 0 else 0,
                "channel_breakdown": channel_breakdown,
                "daily_breakdown": daily_breakdown,
                "status_breakdown": status_breakdown,
                "currency": "INR",
                "calculation_method": "db_normalized_or_raw_fallback",
                "reconciliation_passed": True,
            },
            "order_count": total_orders,
        }

    def _raw_sales_rows_from_job(
        self,
        db: Session,
        from_date: datetime,
        to_date: datetime,
    ) -> Tuple[List[Dict[str, Any]], Optional[datetime]]:
        job = (
            db.query(ExportJob)
            .filter(
                ExportJob.export_type == "sale_orders",
                ExportJob.status == "completed",
                ExportJob.requested_from.isnot(None),
                ExportJob.requested_to.isnot(None),
                ExportJob.requested_from <= from_date,
                ExportJob.requested_to >= to_date,
            )
            .order_by(ExportJob.completed_at.desc(), ExportJob.id.desc())
            .first()
        )

        if not job:
            job = (
                db.query(ExportJob)
                .filter(
                    ExportJob.export_type == "sale_orders",
                    ExportJob.status == "completed",
                    ExportJob.requested_from.isnot(None),
                    ExportJob.requested_to.isnot(None),
                    and_(
                        ExportJob.requested_from <= to_date,
                        ExportJob.requested_to >= from_date,
                    ),
                )
                .order_by(ExportJob.completed_at.desc(), ExportJob.id.desc())
                .first()
            )

        if not job:
            return [], None

        row_payloads = (
            db.query(ExportRow.payload)
            .filter(ExportRow.export_job_id == job.id)
            .order_by(ExportRow.row_number.asc())
            .all()
        )
        rows = [dict(r[0] or {}) for r in row_payloads]
        return rows, job.completed_at

    def _raw_return_rows_from_job(
        self,
        db: Session,
        from_date: datetime,
        to_date: datetime,
    ) -> Tuple[List[Dict[str, Any]], Optional[datetime]]:
        covering_job = (
            db.query(ExportJob.id, ExportJob.completed_at)
            .filter(
                ExportJob.export_type == "return_gst",
                ExportJob.status == "completed",
                ExportJob.requested_from.isnot(None),
                ExportJob.requested_to.isnot(None),
                ExportJob.requested_from <= from_date,
                ExportJob.requested_to >= to_date,
            )
            .order_by(ExportJob.completed_at.desc(), ExportJob.id.desc())
            .first()
        )
        if covering_job:
            job_id, completed_at = covering_job
            row_payloads = (
                db.query(ExportRow.payload)
                .filter(ExportRow.export_job_id == job_id)
                .order_by(ExportRow.row_number.asc())
                .all()
            )
            rows = [dict(payload or {}) for payload, in row_payloads]
            return rows, completed_at

        latest_overlap_job = (
            db.query(ExportJob.id, ExportJob.completed_at)
            .filter(
                ExportJob.export_type == "return_gst",
                ExportJob.status == "completed",
                ExportJob.requested_from.isnot(None),
                ExportJob.requested_to.isnot(None),
                and_(
                    ExportJob.requested_from <= to_date,
                    ExportJob.requested_to >= from_date,
                ),
            )
            .order_by(ExportJob.completed_at.desc(), ExportJob.id.desc())
            .first()
        )
        if not latest_overlap_job:
            return [], None
        job_id, completed_at = latest_overlap_job
        row_payloads = (
            db.query(ExportRow.payload)
            .filter(ExportRow.export_job_id == job_id)
            .order_by(ExportRow.row_number.asc())
            .all()
        )
        rows = [dict(payload or {}) for payload, in row_payloads]
        return rows, completed_at

    def get_sales_data(
        self,
        period: str = "today",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        include_legacy_orders: bool = True,
        include_orders: bool = True,
        include_summary: bool = True,
    ) -> Dict[str, Any]:
        start, end, resolved_period = self._resolve_range(period, from_date, to_date)

        db = self._get_db()
        try:
            # Period filtering uses order_date (business event time), NOT created_at (sync ingestion time).
            # This is CRITICAL: order_date is when customer placed order; created_at is when we synced it.
            # If we used created_at, a batch sync from April 2026 could mis-report as Sept 2023 (sync date).
            # Always use order_date for period bucketing to avoid cross-period drift.
            date_filter = and_(
                SalesOrderRecord.order_date.isnot(None),
                SalesOrderRecord.order_date >= start,
                SalesOrderRecord.order_date < end,
            )

            if include_legacy_orders:
                normalized_records = (
                    db.query(
                        SalesOrderRecord.order_id,
                        SalesOrderRecord.sale_order_item_code,
                        SalesOrderRecord.status,
                        SalesOrderRecord.channel,
                        SalesOrderRecord.qty,
                        SalesOrderRecord.selling_price,
                        SalesOrderRecord.discount,
                        SalesOrderRecord.tax,
                        SalesOrderRecord.refund,
                        SalesOrderRecord.category,
                        SalesOrderRecord.order_date,
                        SalesOrderRecord.created_at,
                        SalesOrderRecord.sku,
                        SalesOrderRecord.product_name,
                        SalesOrderRecord.raw_data["Item Details"].astext.label("raw_item_details"),
                        SalesOrderRecord.raw_data["itemDetails"].astext.label("raw_item_details_alt"),
                        SalesOrderRecord.raw_data["Item Type Name"].astext.label("raw_item_type_name"),
                        SalesOrderRecord.raw_data["itemTypeName"].astext.label("raw_item_type_name_alt"),
                        SalesOrderRecord.raw_data["Item Name"].astext.label("raw_item_name"),
                        SalesOrderRecord.raw_data["itemName"].astext.label("raw_item_name_alt"),
                        SalesOrderRecord.raw_data["Name"].astext.label("raw_name"),
                        SalesOrderRecord.raw_data["Bundle SKU Code Number"].astext.label("raw_bundle_sku_code_number"),
                        SalesOrderRecord.raw_data["bundleSkuCodeNumber"].astext.label("raw_bundle_sku_code_number_alt"),
                        SalesOrderRecord.raw_data["Bundle SKU"].astext.label("raw_bundle_sku"),
                        SalesOrderRecord.raw_data["COD"].astext.label("raw_cod"),
                        SalesOrderRecord.raw_data["cod"].astext.label("raw_cod_alt"),
                        SalesOrderRecord.updated_at,
                    )
                    .filter(date_filter)
                    .all()
                )

                if normalized_records:
                    rows = [
                        {
                            "order_id": r.order_id,
                            "sale_order_item_code": r.sale_order_item_code,
                            "status": r.status,
                            "channel": r.channel,
                            "qty": r.qty,
                            "selling_price": self._safe_decimal(r.selling_price),
                            "discount": self._safe_decimal(r.discount),
                            "tax": self._safe_decimal(r.tax),
                            "refund": self._safe_decimal(r.refund),
                            "category": self._safe_str(r.category) if hasattr(r, 'category') else "",
                            "order_date": self._normalize_dt(r.order_date or r.created_at),
                            "sku": r.sku,
                            "product_name": self._safe_str(
                                r.raw_item_details
                                or r.raw_item_details_alt
                                or r.raw_item_type_name
                                or r.raw_item_type_name_alt
                                or r.raw_item_name
                                or r.raw_item_name_alt
                                or r.raw_name
                            ) or self._safe_str(r.product_name),
                            "bundle_sku_code_number": self._safe_str(
                                r.raw_bundle_sku_code_number
                                or r.raw_bundle_sku_code_number_alt
                                or r.raw_bundle_sku
                            ),
                            "cod": self._safe_bool(r.raw_cod or r.raw_cod_alt, default=False),
                        }
                        for r in normalized_records
                    ]
                    legacy_orders: List[Dict[str, Any]] = []
                    detailed_orders = self._orders_from_line_rows(rows)
                    legacy_orders = self._legacy_orders_from_orders(detailed_orders)
                    aggregation: Optional[Dict[str, Any]] = None
                    if include_summary or include_orders:
                        aggregation = self._aggregate_sales_rows(rows)
                    last_synced = max((r.updated_at for r in normalized_records if r.updated_at), default=None)
                    order_count = int((aggregation or {}).get("order_count") or len(legacy_orders))

                    return {
                        "success": True,
                        "period": resolved_period,
                        "from_date": start.isoformat(),
                        "to_date": end.isoformat(),
                        "data_source": "normalized_sales_orders",
                        "fallback_used": False,
                        "last_synced_at": self._normalize_dt(last_synced).isoformat() if last_synced else None,
                        "data_health": {
                            "coverage": "normalized",
                            "normalized_rows": len(normalized_records),
                            "raw_rows": 0,
                        },
                        "fetch_info": {
                            "total_available": order_count,
                            "fetched_count": order_count,
                            "failed_codes": 0,
                            "phase1_time_seconds": 0,
                            "phase2_time_seconds": 0,
                            "total_time_seconds": 0,
                            "retry_recovered": 0,
                            "phase1_dedup": 0,
                            "phase2_dedup": 0,
                            "reconciliation_passed": True,
                        },
                        "summary": (aggregation or {}).get("summary") if include_summary else {},
                        "orders": (aggregation or {}).get("orders", []) if include_orders else [],
                        "_orders": legacy_orders,
                        "revenue_method": "db_first_normalized",
                    }
            else:
                lightweight_records = (
                    db.query(
                        SalesOrderRecord.order_id,
                        SalesOrderRecord.status,
                        SalesOrderRecord.channel,
                        SalesOrderRecord.qty,
                        SalesOrderRecord.selling_price,
                        SalesOrderRecord.discount,
                        SalesOrderRecord.tax,
                        SalesOrderRecord.refund,
                        SalesOrderRecord.category,
                        SalesOrderRecord.order_date,
                        SalesOrderRecord.created_at,
                        SalesOrderRecord.updated_at,
                    )
                    .filter(date_filter)
                    .all()
                )

                if lightweight_records:
                    rows = [
                        {
                            "order_id": r.order_id,
                            "status": r.status,
                            "channel": r.channel,
                            "qty": r.qty,
                            "selling_price": self._safe_decimal(r.selling_price),
                            "discount": self._safe_decimal(r.discount) if hasattr(r, 'discount') else Decimal("0"),
                            "tax": self._safe_decimal(r.tax) if hasattr(r, 'tax') else Decimal("0"),
                            "refund": self._safe_decimal(r.refund) if hasattr(r, 'refund') else Decimal("0"),
                            "category": self._safe_str(r.category) if hasattr(r, 'category') else "",
                            "order_date": self._normalize_dt(r.order_date or r.created_at),
                        }
                        for r in lightweight_records
                    ]
                    aggregation: Optional[Dict[str, Any]] = None
                    if include_summary or include_orders:
                        aggregation = self._aggregate_sales_rows(rows)
                    last_synced = max((r.updated_at for r in lightweight_records if r.updated_at), default=None)
                    order_count = int((aggregation or {}).get("order_count") or len(lightweight_records))

                    return {
                        "success": True,
                        "period": resolved_period,
                        "from_date": start.isoformat(),
                        "to_date": end.isoformat(),
                        "data_source": "normalized_sales_orders",
                        "fallback_used": False,
                        "last_synced_at": self._normalize_dt(last_synced).isoformat() if last_synced else None,
                        "data_health": {
                            "coverage": "normalized",
                            "normalized_rows": len(lightweight_records),
                            "raw_rows": 0,
                        },
                        "fetch_info": {
                            "total_available": order_count,
                            "fetched_count": order_count,
                            "failed_codes": 0,
                            "phase1_time_seconds": 0,
                            "phase2_time_seconds": 0,
                            "total_time_seconds": 0,
                            "retry_recovered": 0,
                            "phase1_dedup": 0,
                            "phase2_dedup": 0,
                            "reconciliation_passed": True,
                        },
                        "summary": (aggregation or {}).get("summary") if include_summary else {},
                        "orders": (aggregation or {}).get("orders", []) if include_orders else [],
                        "_orders": [],
                        "revenue_method": "db_first_normalized",
                    }

            raw_rows, completed_at = self._raw_sales_rows_from_job(db, start, end)
            if not raw_rows:
                return {
                    "success": True,
                    "period": resolved_period,
                    "from_date": start.isoformat(),
                    "to_date": end.isoformat(),
                    "data_source": "none",
                    "fallback_used": False,
                    "last_synced_at": None,
                    "data_health": {
                        "coverage": "empty",
                        "normalized_rows": 0,
                        "raw_rows": 0,
                    },
                    "fetch_info": {
                        "total_available": 0,
                        "fetched_count": 0,
                        "failed_codes": 0,
                        "phase1_time_seconds": 0,
                        "phase2_time_seconds": 0,
                        "total_time_seconds": 0,
                        "retry_recovered": 0,
                        "phase1_dedup": 0,
                        "phase2_dedup": 0,
                        "reconciliation_passed": True,
                    },
                    "summary": {
                        "total_orders": 0,
                        "valid_orders": 0,
                        "excluded_orders": 0,
                        "total_items": 0,
                        "total_revenue": 0,
                        "total_discount": 0,
                        "total_tax": 0,
                        "total_refund": 0,
                        "avg_order_value": 0,
                        "channel_breakdown": {},
                        "daily_breakdown": [],
                        "status_breakdown": {},
                        "currency": "INR",
                        "calculation_method": "db_normalized_or_raw_fallback",
                        "reconciliation_passed": True,
                    },
                    "orders": [],
                    "_orders": [],
                    "revenue_method": "db_first_normalized",
                }

            line_rows = self._raw_line_rows_from_sales_payloads(raw_rows, start, end)
            legacy_orders: List[Dict[str, Any]] = []
            if include_legacy_orders:
                detailed_orders = self._orders_from_line_rows(line_rows)
                legacy_orders = self._legacy_orders_from_orders(detailed_orders)
            aggregation = self._aggregate_sales_rows(line_rows)

            return {
                "success": True,
                "period": resolved_period,
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "data_source": "raw_export_rows_fallback",
                "fallback_used": True,
                "last_synced_at": self._normalize_dt(completed_at).isoformat() if completed_at else None,
                "data_health": {
                    "coverage": "raw_fallback",
                    "normalized_rows": 0,
                    "raw_rows": len(line_rows),
                },
                "fetch_info": {
                    "total_available": aggregation["order_count"],
                    "fetched_count": aggregation["order_count"],
                    "failed_codes": 0,
                    "phase1_time_seconds": 0,
                    "phase2_time_seconds": 0,
                    "total_time_seconds": 0,
                    "retry_recovered": 0,
                    "phase1_dedup": 0,
                    "phase2_dedup": 0,
                    "reconciliation_passed": True,
                },
                "summary": aggregation["summary"],
                "orders": aggregation["orders"] if include_orders else [],
                "_orders": legacy_orders,
                "revenue_method": "db_first_normalized",
            }
        finally:
            db.close()

    def get_returns_data(
        self,
        from_date: datetime,
        to_date: datetime,
        return_type: str = "ALL",
    ) -> Dict[str, Any]:
        type_norm = self._safe_str(return_type or "ALL").upper()
        if type_norm not in {"RTO", "CIR", "ALL"}:
            type_norm = "ALL"

        db = self._get_db()
        try:
            items: List[Dict[str, Any]] = []
            last_synced_at = None
            raw_rows, completed_at = self._raw_return_rows_from_job(db, from_date, to_date)
            if raw_rows:
                last_synced_at = completed_at.isoformat() if completed_at else None
                for raw in raw_rows:
                    parsed_dt = self._parse_return_report_dt(
                        self._pick(raw, "Date", "Return Date", "returnDate", "Dispatch Date/Cancellation Date")
                    )
                    if parsed_dt is None:
                        continue
                    if parsed_dt < from_date or parsed_dt > to_date:
                        continue
                    rtype = self._normalize_return_type(self._safe_str(self._pick(raw, "Return Type", "returnType")))
                    if type_norm != "ALL" and rtype != type_norm:
                        continue
                    quantity = self._safe_int(self._pick(raw, "Qty", "QTY", "quantity"), default=1)
                    if quantity <= 0:
                        quantity = 1
                    total_value = self._safe_float(self._pick(raw, "Total", "total", "Sales"), default=0.0)
                    unit_price = round(total_value / quantity, 2) if quantity > 0 else 0.0
                    items.append(
                        {
                            "saleOrderCode": self._safe_str(
                                self._pick(raw, "Sale Order Number", "Sale Order Code", "saleOrderCode")
                            ),
                            "invoiceCode": self._safe_str(
                                self._pick(raw, "RP Code", "rpcode", "returnCode", "Invoice number", "invoiceCode")
                            ),
                            "channel": self._safe_str(
                                self._pick(raw, "Channel entry", "Channel Name", "channel") or "UNKNOWN"
                            ),
                            "returnType": rtype,
                            "sku": self._safe_str(self._pick(raw, "Product SKU Code", "Product SKU", "sku")),
                            "itemName": self._safe_str(self._pick(raw, "Product Name", "Item Name", "itemName")),
                            "quantity": quantity,
                            "unitPrice": unit_price,
                            "refundAmount": round(total_value, 2),
                            "returnDate": parsed_dt.isoformat(),
                        }
                    )

            from_day = from_date.date()
            to_day = to_date.date()
            dispatch_date_text = func.nullif(SalesReturnRecord.dispatch_or_cancellation_date, "")
            return_event_date = case(
                (
                    dispatch_date_text.op("~")(r"^\d{2}-\d{2}-\d{4}$"),
                    func.to_date(dispatch_date_text, "DD-MM-YYYY"),
                ),
                (
                    dispatch_date_text.op("~")(r"^\d{4}-\d{2}-\d{2}$"),
                    func.to_date(dispatch_date_text, "YYYY-MM-DD"),
                ),
                (
                    dispatch_date_text.op("~")(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$"),
                    func.to_date(func.substring(dispatch_date_text, 1, 10), "YYYY-MM-DD"),
                ),
                else_=None,
            )
            normalized_records = [] if items else (
                db.query(
                    SalesReturnRecord.order_id,
                    SalesReturnRecord.return_code,
                    SalesReturnRecord.channel_entry,
                    SalesReturnRecord.return_type,
                    SalesReturnRecord.return_status,
                    SalesReturnRecord.sku,
                    SalesReturnRecord.product_name,
                    SalesReturnRecord.return_qty,
                    SalesReturnRecord.refund_amount,
                    SalesReturnRecord.dispatch_or_cancellation_date,
                    SalesReturnRecord.created_at,
                    SalesReturnRecord.updated_at,
                )
                .filter(
                    or_(
                        and_(
                            return_event_date.isnot(None),
                            return_event_date >= from_day,
                            return_event_date <= to_day,
                        ),
                        and_(
                            return_event_date.is_(None),
                            or_(
                                and_(
                                    SalesReturnRecord.updated_at >= from_date,
                                    SalesReturnRecord.updated_at <= to_date,
                                ),
                                and_(
                                    SalesReturnRecord.created_at >= from_date,
                                    SalesReturnRecord.created_at <= to_date,
                                ),
                            ),
                        ),
                    )
                )
                .all()
            )

            for record in normalized_records:
                parsed_dt = self.uc_service._parse_datetime(record.dispatch_or_cancellation_date)
                parsed_dt = self._normalize_dt(parsed_dt or record.updated_at or record.created_at)
                if parsed_dt and (parsed_dt < from_date or parsed_dt > to_date):
                    continue
                rtype = self._normalize_return_type(record.return_type or record.return_status)
                if type_norm != "ALL" and rtype != type_norm:
                    continue
                quantity = int(record.return_qty or 0)
                if quantity <= 0:
                    quantity = 1
                refund_amount = float(record.refund_amount or 0.0)
                unit_price = round(refund_amount / quantity, 2) if quantity > 0 else 0.0
                items.append(
                    {
                        "saleOrderCode": self._safe_str(record.order_id),
                        "invoiceCode": self._safe_str(record.return_code),
                        "channel": self._safe_str(record.channel_entry or "UNKNOWN"),
                        "returnType": rtype,
                        "sku": self._safe_str(record.sku),
                        "itemName": self._safe_str(record.product_name) or self._safe_str(record.sku),
                        "quantity": quantity,
                        "unitPrice": unit_price,
                        "refundAmount": round(refund_amount, 2),
                        "returnDate": parsed_dt.isoformat() if parsed_dt else "",
                    }
                )

            data_source = "raw_export_rows" if items else "normalized_sales_returns"

            if not items:
                raw_rows, completed_at = self._raw_return_rows_from_job(db, from_date, to_date)
                last_synced_at = completed_at.isoformat() if completed_at else None
                for raw in raw_rows:
                    parsed_dt = self.uc_service._parse_datetime(
                        self._pick(
                            raw,
                            "Return Date",
                            "returnDate",
                            "Invoice Date",
                            "invoiceDate",
                            "Created",
                            "created",
                        )
                    )
                    parsed_dt = self._normalize_dt(parsed_dt)

                    if parsed_dt and (parsed_dt < from_date or parsed_dt > to_date):
                        continue

                    rtype = self._normalize_return_type(
                        self._safe_str(self._pick(raw, "Return Type", "returnType"))
                    )
                    if type_norm != "ALL" and rtype != type_norm:
                        continue

                    quantity = self._safe_int(self._pick(raw, "Qty", "QTY", "quantity"), default=1)
                    if quantity <= 0:
                        quantity = 1

                    total_value = self._safe_float(self._pick(raw, "Total", "total", "Sales"), default=0.0)
                    unit_price = round(total_value / quantity, 2) if quantity > 0 else 0.0

                    items.append(
                        {
                            "saleOrderCode": self._safe_str(
                                self._pick(raw, "Sale Order Number", "Sale Order Code", "saleOrderCode")
                            ),
                            "invoiceCode": self._safe_str(
                                self._pick(raw, "Invoice number", "Invoice Code", "invoiceCode")
                            ),
                            "channel": self._safe_str(self._pick(raw, "Channel Name", "channel") or "UNKNOWN"),
                            "returnType": rtype,
                            "sku": self._safe_str(self._pick(raw, "Product SKU Code", "Product SKU", "sku")),
                            "itemName": self._safe_str(
                                self._pick(raw, "Product Name", "Item Name", "itemName")
                            ),
                            "quantity": quantity,
                            "unitPrice": unit_price,
                            "refundAmount": round(total_value, 2),
                            "returnDate": parsed_dt.isoformat() if parsed_dt else "",
                        }
                    )

                if raw_rows:
                    data_source = "raw_export_rows_fallback"

            items.sort(
                key=lambda x: (
                    self._safe_str(x.get("returnDate")),
                    self._safe_str(x.get("saleOrderCode")),
                    self._safe_str(x.get("sku")),
                ),
                reverse=True,
            )

            rto_count = sum(1 for item in items if self._safe_str(item.get("returnType")).upper() == "RTO")
            cir_count = sum(1 for item in items if self._safe_str(item.get("returnType")).upper() == "CIR")
            total_value = round(sum(float(item.get("refundAmount") or 0.0) for item in items), 2)

            return {
                "success": True,
                "data_source": data_source,
                "fallback_used": data_source == "raw_export_rows_fallback",
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "return_type": type_norm,
                "items": items,
                "totals": {
                    "total_items": len(items),
                    "total_value": total_value,
                    "rto_count": rto_count,
                    "cir_count": cir_count,
                },
                "last_synced_at": last_synced_at,
            }
        finally:
            db.close()

    def get_channel_revenue(self, period: str = "last_7_days") -> Dict[str, Any]:
        period_norm = self._safe_str(period or "last_7_days").lower()
        if period_norm not in {"today", "yesterday", "last_7_days"}:
            period_norm = "last_7_days"

        sales_result = self.get_sales_data(period=period_norm, include_legacy_orders=False)
        if not sales_result.get("success"):
            return sales_result

        summary = dict(sales_result.get("summary") or {})
        channel_breakdown = dict(summary.get("channel_breakdown") or {})
        total_revenue = float(summary.get("total_revenue") or 0.0)

        channels: List[Dict[str, Any]] = []
        for channel, data in sorted(
            channel_breakdown.items(),
            key=lambda x: float((x[1] or {}).get("revenue", 0) or 0),
            reverse=True,
        ):
            revenue = float((data or {}).get("revenue", 0) or 0.0)
            channels.append(
                {
                    "channel": channel,
                    "orders": int((data or {}).get("orders", 0) or 0),
                    "revenue": round(revenue, 2),
                    "percentage": round((revenue / total_revenue * 100) if total_revenue > 0 else 0.0, 2),
                }
            )

        channel_sum = round(sum(float(ch.get("revenue") or 0.0) for ch in channels), 2)

        return {
            "success": True,
            "period": period_norm,
            "total_revenue": round(total_revenue, 2),
            "total_orders": int(summary.get("total_orders", 0) or 0),
            "total_items": int(summary.get("total_items", 0) or 0),
            "channels": channels,
            "validation": {
                "channel_sum": channel_sum,
                "total_revenue": round(total_revenue, 2),
                "passed": abs(channel_sum - round(total_revenue, 2)) < 1,
            },
            "revenue_method": "sellingPrice_only",
            "data_source": sales_result.get("data_source", "db_first"),
            "fallback_used": bool(sales_result.get("fallback_used")),
            "last_synced_at": sales_result.get("last_synced_at"),
        }

    @staticmethod
    def _format_order_datetime_display(raw_value: Any, target_tz: timezone) -> str:
        raw = str(raw_value or "").strip()
        if not raw:
            return ""

        try:
            numeric = float(raw)
            if numeric > 1e12:
                numeric = numeric / 1000.0
            dt = datetime.fromtimestamp(numeric, tz=timezone.utc).astimezone(target_tz)
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except (ValueError, TypeError, OverflowError, OSError):
            pass

        try:
            iso_raw = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso_raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=target_tz)
            else:
                dt = dt.astimezone(target_tz)
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            pass

        for fmt in ("%Y-%m-%d %H:%M:%S", "%d %b %Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                dt = datetime.strptime(raw, fmt).replace(tzinfo=target_tz)
                return dt.strftime("%d/%m/%Y %H:%M:%S")
            except ValueError:
                continue

        return raw

    def get_daily_sales_report(
        self,
        date: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Any]:
        try:
            self._emit_progress(progress_cb, 5, "Validating date range…")
            is_range = bool(from_date and to_date)
            if not is_range and not date:
                return {
                    "success": False,
                    "error": "Provide either 'date' or both 'from_date' and 'to_date'.",
                }

            if is_range:
                from_dt, to_exclusive_dt, _ = normalize_date_range_ist(
                    str(from_date),
                    str(to_date),
                    closed_window_mode=False,
                )
                to_dt = to_exclusive_dt - timedelta(seconds=1)
                date_label = f"{from_date} to {to_date}"
            else:
                report_date = datetime.strptime(str(date), "%Y-%m-%d").date()
                from_dt, to_exclusive_dt, _ = normalize_date_range_ist(
                    str(date),
                    str(date),
                    closed_window_mode=False,
                )
                to_dt = to_exclusive_dt - timedelta(seconds=1)
                date_label = str(date)

            self._emit_progress(progress_cb, 15, "Loading sales rows for selected range…")
            # For single-day today/yesterday views, prefer live export parity with Unicommerce UI.
            if not is_range and date:
                report_day = datetime.strptime(str(date), "%Y-%m-%d").date()
                today_ist = datetime.now(IST).date()
                if report_day in {today_ist, today_ist - timedelta(days=1)}:
                    sales_result = asyncio.run(
                        self.uc_service.get_sales_data(
                            from_date=from_dt,
                            to_date=to_dt,
                            period_name="custom",
                        )
                    )
                    if isinstance(sales_result, dict):
                        sales_result["data_source"] = "live_export_api"
                        sales_result["fallback_used"] = False
                else:
                    sales_result = self.get_sales_data(
                        period="custom",
                        from_date=from_dt,
                        to_date=to_dt,
                        include_legacy_orders=False,
                    )
            else:
                sales_result = self.get_sales_data(
                    period="custom",
                    from_date=from_dt,
                    to_date=to_dt,
                    include_legacy_orders=False,
                )

            if not sales_result.get("success"):
                return sales_result

            self._emit_progress(progress_cb, 35, "Building channel summary…")

            summary = dict(sales_result.get("summary") or {})
            channel_breakdown = dict(summary.get("channel_breakdown") or {})

            report_data: List[Dict[str, Any]] = []
            for channel_name, channel_data in channel_breakdown.items():
                report_data.append(
                    {
                        "channel_name": channel_name,
                        "quantity": int((channel_data or {}).get("items", 0) or 0),
                        "selling_price": round(float((channel_data or {}).get("revenue", 0) or 0.0), 2),
                        "orders": int((channel_data or {}).get("orders", 0) or 0),
                    }
                )

            report_data.sort(key=lambda x: float(x.get("selling_price") or 0.0), reverse=True)

            total_quantity = sum(int(item.get("quantity") or 0) for item in report_data)
            total_revenue = sum(float(item.get("selling_price") or 0.0) for item in report_data)
            total_orders = int(summary.get("valid_orders", 0) or 0)
            total_all_orders = int(summary.get("total_orders", 0) or 0)
            excluded_items = int(summary.get("total_items", 0) or 0) - total_quantity

            items_detail: List[Dict[str, Any]] = []
            ist = timezone(timedelta(hours=5, minutes=30))

            self._emit_progress(progress_cb, 55, "Preparing item-level sales details…")

            if sales_result.get("data_source") == "normalized_sales_orders":
                db = self._get_db()
                try:
                    item_rows = (
                        db.query(
                            SalesOrderRecord.sku,
                            SalesOrderRecord.sale_order_item_code,
                            SalesOrderRecord.product_name,
                            SalesOrderRecord.channel,
                            SalesOrderRecord.order_date,
                            SalesOrderRecord.created_at,
                            SalesOrderRecord.selling_price,
                            SalesOrderRecord.status,
                        )
                        .filter(
                            and_(
                                SalesOrderRecord.order_date.isnot(None),
                                SalesOrderRecord.order_date >= from_dt,
                                SalesOrderRecord.order_date < to_dt,
                            )
                        )
                        .all()
                    )
                finally:
                    db.close()

                for row in item_rows:
                    status = self._safe_str(row.status).upper()
                    if status in self.EXCLUDED_STATUSES:
                        continue

                    order_dt = self._normalize_dt(row.order_date or row.created_at)
                    order_date = (
                        order_dt.astimezone(ist).strftime("%d/%m/%Y %H:%M:%S")
                        if order_dt is not None
                        else ""
                    )

                    items_detail.append(
                        {
                            "item_sku_code": self._safe_str(row.sku),
                            "sale_order_item_code": self._safe_str(row.sale_order_item_code),
                            "item_type_name": self._safe_str(row.product_name),
                            "size": "",
                            "channel_name": self._safe_str(row.channel) or "UNKNOWN",
                            "order_date": order_date,
                            "bundle_sku_code_number": "",
                            "selling_price": round(self._safe_float(row.selling_price, default=0.0), 2),
                        }
                    )
            else:
                legacy_sales_result = self.get_sales_data(
                    period="custom",
                    from_date=from_dt,
                    to_date=to_dt,
                    include_legacy_orders=True,
                )
                raw_orders = list(legacy_sales_result.get("_orders") or [])

                for order in raw_orders:
                    status = self._safe_str(order.get("status")).upper()
                    if status in self.EXCLUDED_STATUSES:
                        continue

                    channel = self._safe_str(order.get("channel")) or "UNKNOWN"
                    order_date = self._format_order_datetime_display(order.get("created"), ist)

                    for item in list(order.get("saleOrderItems") or []):
                        selling_price = self._safe_float(item.get("sellingPrice"), default=0.0)
                        items_detail.append(
                            {
                                "item_sku_code": self._safe_str(item.get("itemSku")),
                                "sale_order_item_code": self._safe_str(item.get("code")),
                                "item_type_name": self._safe_str(item.get("itemTypeName")),
                                "size": self._safe_str(item.get("size")),
                                "channel_name": channel,
                                "order_date": order_date,
                                "bundle_sku_code_number": self._safe_str(item.get("bundleSkuCodeNumber")),
                                "selling_price": round(selling_price, 2),
                            }
                        )

            unique_skus = sorted(
                {
                    self._safe_str(item.get("item_sku_code"))
                    for item in items_detail
                    if self._safe_str(item.get("item_sku_code"))
                }
            )
            inventory_map: Dict[str, Dict[str, int]] = {}

            max_inventory_skus = 1200
            if unique_skus and len(unique_skus) <= max_inventory_skus:
                self._emit_progress(progress_cb, 70, "Fetching inventory snapshot for SKUs…")
                inventory_result = self.get_inventory_data(skus=unique_skus)
                if inventory_result.get("success"):
                    for inventory_item in list(inventory_result.get("items") or []):
                        sku_code = self._safe_str(inventory_item.get("sku"))
                        if not sku_code:
                            continue
                        inventory_map[sku_code] = {
                            "good_inventory": int(inventory_item.get("available_qty", 0) or 0),
                            "virtual_inventory": int(inventory_item.get("reserved_qty", 0) or 0),
                        }
            elif unique_skus:
                self._emit_progress(progress_cb, 70, "Skipping inventory enrichment for large SKU set…")

            for item in items_detail:
                sku = self._safe_str(item.get("item_sku_code"))
                inv = inventory_map.get(sku, {})
                item["good_inventory"] = inv.get("good_inventory")
                item["virtual_inventory"] = inv.get("virtual_inventory")

            comparison = None
            if not is_range and date:
                self._emit_progress(progress_cb, 82, "Preparing comparison with previous day…")
                comp_date = datetime.strptime(str(date), "%Y-%m-%d").date() - timedelta(days=1)
                comp_from, comp_to_exclusive, _ = normalize_date_range_ist(
                    comp_date.isoformat(),
                    comp_date.isoformat(),
                    closed_window_mode=False,
                )
                comp_to = comp_to_exclusive - timedelta(seconds=1)
                comp_result = self.get_sales_data(
                    period="custom",
                    from_date=comp_from,
                    to_date=comp_to,
                    include_legacy_orders=False,
                )

                if comp_result.get("success"):
                    comp_breakdown = dict((comp_result.get("summary") or {}).get("channel_breakdown") or {})
                    comp_report: List[Dict[str, Any]] = []
                    for ch_name, ch_data in comp_breakdown.items():
                        comp_report.append(
                            {
                                "channel_name": ch_name,
                                "quantity": int((ch_data or {}).get("items", 0) or 0),
                                "selling_price": round(float((ch_data or {}).get("revenue", 0) or 0.0), 2),
                                "orders": int((ch_data or {}).get("orders", 0) or 0),
                            }
                        )
                    comp_report.sort(key=lambda x: float(x.get("selling_price") or 0.0), reverse=True)
                    comp_total_qty = sum(int(i.get("quantity") or 0) for i in comp_report)
                    comp_total_rev = sum(float(i.get("selling_price") or 0.0) for i in comp_report)
                    comp_total_ord = int((comp_result.get("summary") or {}).get("valid_orders", 0) or 0)

                    comparison = {
                        "date": comp_date.strftime("%Y-%m-%d"),
                        "report": comp_report,
                        "totals": {
                            "total_channels": len(comp_report),
                            "total_quantity": comp_total_qty,
                            "total_revenue": round(comp_total_rev, 2),
                            "total_orders": comp_total_ord,
                        },
                    }

            self._emit_progress(progress_cb, 96, "Finalizing report payload…")

            return {
                "success": True,
                "date": date_label,
                "from_date": str(from_date) if is_range else str(date),
                "to_date": str(to_date) if is_range else str(date),
                "report": report_data,
                "items": items_detail,
                "comparison": comparison,
                "totals": {
                    "total_channels": len(report_data),
                    "total_quantity": total_quantity,
                    "total_revenue": round(total_revenue, 2),
                    "total_orders": total_orders,
                    "excluded_items": excluded_items,
                    "all_orders": total_all_orders,
                },
                "currency": "INR",
                "data_source": sales_result.get("data_source", "db_first"),
                "cached": False,
                "note": f"Report shows {total_quantity} items from revenue-generating orders. {excluded_items} items excluded from cancelled/returned orders.",
                "fallback_used": bool(sales_result.get("fallback_used")),
                "last_synced_at": sales_result.get("last_synced_at"),
            }
        except ValueError as exc:
            return {
                "success": False,
                "error": f"Invalid date format. Use YYYY-MM-DD: {exc}",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def get_return_report(
        self,
        date: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        period: str = "daily",
        return_type: str = "ALL",
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Any]:
        try:
            self._emit_progress(progress_cb, 5, "Validating return report parameters…")
            period_norm = self._safe_str(period or "daily").lower()
            ist = timezone(timedelta(hours=5, minutes=30))
            today_ist = datetime.now(ist).date()

            if period_norm == "custom" or (from_date and to_date):
                if not from_date or not to_date:
                    return {
                        "success": False,
                        "error": "Both from_date and to_date are required for custom range",
                        "period": "custom",
                        "return_type": return_type,
                    }
                start_date = datetime.strptime(str(from_date), "%Y-%m-%d").date()
                end_date = datetime.strptime(str(to_date), "%Y-%m-%d").date()
                period_norm = "custom"
            elif period_norm == "weekly":
                current_week_start = today_ist - timedelta(days=today_ist.weekday())
                start_date = current_week_start - timedelta(days=7)
                end_date = current_week_start - timedelta(days=1)
            elif period_norm == "monthly":
                first_of_current_month = today_ist.replace(day=1)
                end_date = first_of_current_month - timedelta(days=1)
                start_date = end_date.replace(day=1)
            else:
                base_date = datetime.strptime(str(date), "%Y-%m-%d").date() if date else (today_ist - timedelta(days=1))
                start_date = base_date
                end_date = base_date
                period_norm = "daily"

            if start_date > end_date:
                return {
                    "success": False,
                    "error": "from_date cannot be greater than to_date",
                    "period": period_norm,
                    "from_date": start_date.isoformat(),
                    "to_date": end_date.isoformat(),
                    "return_type": return_type,
                }

            from_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=ist).astimezone(timezone.utc)
            to_dt = datetime.combine(end_date, datetime.max.time().replace(microsecond=0)).replace(tzinfo=ist).astimezone(timezone.utc)

            self._emit_progress(progress_cb, 20, "Fetching return items…")
            returns_data = self.get_returns_data(
                from_date=from_dt,
                to_date=to_dt,
                return_type=return_type,
            )

            if not returns_data.get("success"):
                return {
                    "success": False,
                    "error": returns_data.get("error", "Failed to fetch return data"),
                    "period": period_norm,
                    "date": start_date.isoformat(),
                    "from_date": start_date.isoformat(),
                    "to_date": end_date.isoformat(),
                    "return_type": return_type,
                }

            all_items = list(returns_data.get("items") or [])
            channel_map: Dict[str, Dict[str, Any]] = {}
            sku_map: Dict[str, Dict[str, Any]] = {}
            returns_list: List[Dict[str, Any]] = []
            rto_count = 0
            cir_count = 0
            total_value = 0.0
            total_items_count = 0

            return_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for item in all_items:
                invoice_code = self._safe_str(item.get("invoiceCode"))
                so_code = self._safe_str(item.get("saleOrderCode"))
                sku = self._safe_str(item.get("sku"))
                group_key = invoice_code or f"{so_code}:{sku}" or "UNKNOWN"
                return_groups[group_key].append(item)

            self._emit_progress(progress_cb, 52, "Classifying RTO vs CIR and grouping by channel…")

            for group_key, items in return_groups.items():
                if not items:
                    continue

                first = items[0]
                rtype = self._safe_str(first.get("returnType")) or "UNKNOWN"
                channel = self._safe_str(first.get("channel")) or "UNKNOWN"
                so_code = self._safe_str(first.get("saleOrderCode")) or "UNKNOWN"
                invoice_code = self._safe_str(first.get("invoiceCode")) or group_key

                if rtype == "RTO":
                    rto_count += 1
                elif rtype == "CIR":
                    cir_count += 1

                return_entry: Dict[str, Any] = {
                    "code": invoice_code,
                    "type": rtype,
                    "channel": channel,
                    "status": "RETURNED",
                    "created": "",
                    "saleOrderCode": so_code,
                    "items": [],
                    "total_value": 0.0,
                }

                for item in items:
                    sku = self._safe_str(item.get("sku")) or "UNKNOWN"
                    item_name = self._safe_str(item.get("itemName"))
                    qty = self._safe_int(item.get("quantity"), default=1)
                    if qty <= 0:
                        qty = 1

                    unit_price = self._safe_float(item.get("unitPrice"), default=0.0)
                    price = unit_price * qty

                    total_items_count += qty
                    total_value += price
                    return_entry["total_value"] += price
                    return_entry["items"].append(
                        {
                            "sku": sku,
                            "name": item_name,
                            "quantity": qty,
                            "price": price,
                        }
                    )

                    if sku not in sku_map:
                        sku_map[sku] = {
                            "sku": sku,
                            "name": item_name,
                            "quantity": 0,
                            "value": 0.0,
                            "return_count": 0,
                        }
                    sku_map[sku]["quantity"] += qty
                    sku_map[sku]["value"] += price
                    sku_map[sku]["return_count"] += 1

                if channel not in channel_map:
                    channel_map[channel] = {
                        "channel": channel,
                        "returns": 0,
                        "items": 0,
                        "value": 0.0,
                        "rto": 0,
                        "cir": 0,
                    }
                channel_map[channel]["returns"] += 1
                channel_map[channel]["items"] += len(items)
                channel_map[channel]["value"] += float(return_entry["total_value"] or 0.0)
                if rtype == "RTO":
                    channel_map[channel]["rto"] += 1
                else:
                    channel_map[channel]["cir"] += 1

                returns_list.append(return_entry)

            self._emit_progress(progress_cb, 84, "Finalizing return summary metrics…")

            by_channel = sorted(channel_map.values(), key=lambda x: float(x.get("value") or 0.0), reverse=True)
            by_sku = sorted(sku_map.values(), key=lambda x: int(x.get("quantity") or 0), reverse=True)

            for ch in by_channel:
                ch["value"] = round(float(ch.get("value") or 0.0), 2)
            for sku_data in by_sku:
                sku_data["value"] = round(float(sku_data.get("value") or 0.0), 2)

            return {
                "success": True,
                "period": period_norm,
                "date": start_date.isoformat(),
                "from_date": start_date.isoformat(),
                "to_date": end_date.isoformat(),
                "return_type": return_type,
                "returns": returns_list,
                "by_channel": by_channel,
                "by_sku": by_sku,
                "totals": {
                    "total_returns": len(returns_list),
                    "total_items": total_items_count,
                    "total_value": round(total_value, 2),
                    "rto_count": rto_count,
                    "cir_count": cir_count,
                },
                "search_results": {
                    "export_items": len(all_items),
                    "method": returns_data.get("data_source", "db_first_returns"),
                    "total_time": 0,
                },
                "debug_info": {
                    "failed_rto_codes": [],
                    "failed_cir_codes": [],
                    "total_failed_rto": 0,
                    "total_failed_cir": 0,
                },
                "data_source": returns_data.get("data_source", "db_first_returns"),
                "fallback_used": bool(returns_data.get("fallback_used")),
                "last_synced_at": returns_data.get("last_synced_at"),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def get_cancellation_report(
        self,
        date: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        period: str = "daily",
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Any]:
        try:
            self._emit_progress(progress_cb, 5, "Validating cancellation report parameters…")
            period_norm = self._safe_str(period or "daily").lower()
            ist = timezone(timedelta(hours=5, minutes=30))
            today_ist = datetime.now(ist).date()

            if period_norm == "custom" or (from_date and to_date):
                if not from_date or not to_date:
                    return {
                        "success": False,
                        "error": "Both from_date and to_date are required for custom range",
                        "period": "custom",
                    }
                start_date = datetime.strptime(str(from_date), "%Y-%m-%d").date()
                end_date = datetime.strptime(str(to_date), "%Y-%m-%d").date()
                period_norm = "custom"
            elif period_norm == "weekly":
                current_week_start = today_ist - timedelta(days=today_ist.weekday())
                start_date = current_week_start - timedelta(days=7)
                end_date = current_week_start - timedelta(days=1)
            elif period_norm == "monthly":
                base_date = datetime.strptime(str(date), "%Y-%m-%d").date() if date else (today_ist - timedelta(days=1))
                start_date = base_date.replace(day=1)

                if base_date.year == today_ist.year and base_date.month == today_ist.month:
                    end_date = today_ist - timedelta(days=1)
                else:
                    if base_date.month == 12:
                        first_next_month = datetime(base_date.year + 1, 1, 1).date()
                    else:
                        first_next_month = datetime(base_date.year, base_date.month + 1, 1).date()
                    end_date = first_next_month - timedelta(days=1)
            else:
                base_date = datetime.strptime(str(date), "%Y-%m-%d").date() if date else (today_ist - timedelta(days=1))
                start_date = base_date
                end_date = base_date
                period_norm = "daily"

            if start_date > end_date:
                return {
                    "success": False,
                    "error": "from_date cannot be greater than to_date",
                    "period": period_norm,
                    "from_date": start_date.isoformat(),
                    "to_date": end_date.isoformat(),
                }

            from_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=ist).astimezone(timezone.utc)
            to_dt = datetime.combine(end_date, datetime.max.time().replace(microsecond=0)).replace(tzinfo=ist).astimezone(timezone.utc)

            self._emit_progress(progress_cb, 20, "Fetching sales rows for cancellation analysis…")
            sales_result = self.get_sales_data(
                period="custom",
                from_date=from_dt,
                to_date=to_dt,
            )
            if not sales_result.get("success"):
                return {
                    "success": False,
                    "error": sales_result.get("error", "Failed to fetch orders"),
                    "period": period_norm,
                    "from_date": start_date.isoformat(),
                    "to_date": end_date.isoformat(),
                }

            raw_orders = list(sales_result.get("_orders") or [])
            total_fetch_time = float((sales_result.get("fetch_info") or {}).get("total_time_seconds", 0) or 0)
            total_orders_all = len(raw_orders)
            cancelled_statuses = {"CANCELLED", "CANCELED"}

            cancellations: List[Dict[str, Any]] = []
            items_flat: List[Dict[str, Any]] = []
            channel_map: Dict[str, Dict[str, Any]] = {}
            sku_map: Dict[str, Dict[str, Any]] = {}
            daily_map: Dict[str, Dict[str, Any]] = {}

            total_cancelled_orders = 0
            total_cancelled_items = 0
            total_cancelled_value = 0.0
            cod_orders = 0
            prepaid_orders = 0

            self._emit_progress(progress_cb, 50, "Extracting cancelled orders and item details…")

            for order in raw_orders:
                status = self._safe_str(order.get("status")).upper()
                if status not in cancelled_statuses:
                    continue

                total_cancelled_orders += 1
                channel = self._safe_str(order.get("channel")) or "UNKNOWN"
                order_code = self._safe_str(order.get("code"))
                created_raw = order.get("created") or order.get("displayOrderDateTime")
                created_fmt = self._format_order_datetime_display(created_raw, ist)
                is_cod = bool(order.get("cod") or order.get("cashOnDelivery"))
                if is_cod:
                    cod_orders += 1
                else:
                    prepaid_orders += 1

                order_entry: Dict[str, Any] = {
                    "sale_order_code": order_code,
                    "channel": channel,
                    "status": status,
                    "created": created_fmt,
                    "cod": is_cod,
                    "items": [],
                    "total_items": 0,
                    "total_value": 0.0,
                }

                if channel not in channel_map:
                    channel_map[channel] = {
                        "channel": channel,
                        "cancellations": 0,
                        "items": 0,
                        "value": 0.0,
                        "cod": 0,
                        "prepaid": 0,
                    }
                channel_map[channel]["cancellations"] += 1
                if is_cod:
                    channel_map[channel]["cod"] += 1
                else:
                    channel_map[channel]["prepaid"] += 1

                day_key = created_fmt[:10] if len(created_fmt) >= 10 else str(start_date)
                if day_key not in daily_map:
                    daily_map[day_key] = {
                        "date": day_key,
                        "cancellations": 0,
                        "items": 0,
                        "value": 0.0,
                    }
                daily_map[day_key]["cancellations"] += 1

                for item in list(order.get("saleOrderItems") or []):
                    sku = self._safe_str(item.get("itemSku"))
                    name = self._safe_str(item.get("itemTypeName") or item.get("itemName") or sku)
                    soi_code = self._safe_str(item.get("code"))
                    qty = self._safe_int(item.get("quantity"), default=1)
                    if qty <= 0:
                        qty = 1

                    selling = self._safe_float(item.get("sellingPrice"), default=0.0)
                    line_value = selling * qty

                    total_cancelled_items += qty
                    total_cancelled_value += line_value
                    order_entry["total_items"] += qty
                    order_entry["total_value"] += line_value
                    channel_map[channel]["items"] += qty
                    channel_map[channel]["value"] += line_value
                    daily_map[day_key]["items"] += qty
                    daily_map[day_key]["value"] += line_value

                    order_entry["items"].append(
                        {
                            "sale_order_item_code": soi_code,
                            "sku": sku,
                            "name": name,
                            "quantity": qty,
                            "selling_price": round(selling, 2),
                            "line_value": round(line_value, 2),
                        }
                    )

                    items_flat.append(
                        {
                            "sale_order_code": order_code,
                            "sale_order_item_code": soi_code,
                            "channel": channel,
                            "status": status,
                            "created": created_fmt,
                            "cod": is_cod,
                            "sku": sku,
                            "name": name,
                            "quantity": qty,
                            "selling_price": round(selling, 2),
                            "line_value": round(line_value, 2),
                        }
                    )

                    if sku not in sku_map:
                        sku_map[sku] = {
                            "sku": sku,
                            "name": name,
                            "quantity": 0,
                            "value": 0.0,
                            "cancellation_count": 0,
                        }
                    sku_map[sku]["quantity"] += qty
                    sku_map[sku]["value"] += line_value
                    sku_map[sku]["cancellation_count"] += 1

                order_entry["total_value"] = round(float(order_entry.get("total_value") or 0.0), 2)
                cancellations.append(order_entry)

            self._emit_progress(progress_cb, 84, "Computing channel, SKU and trend summaries…")

            by_channel = sorted(channel_map.values(), key=lambda x: float(x.get("value") or 0.0), reverse=True)
            by_sku = sorted(sku_map.values(), key=lambda x: float(x.get("value") or 0.0), reverse=True)
            daily_trend = sorted(daily_map.values(), key=lambda x: self._safe_str(x.get("date")))

            for channel_data in by_channel:
                channel_data["value"] = round(float(channel_data.get("value") or 0.0), 2)
            for sku_data in by_sku:
                sku_data["value"] = round(float(sku_data.get("value") or 0.0), 2)
            for day_data in daily_trend:
                day_data["value"] = round(float(day_data.get("value") or 0.0), 2)

            cancellation_rate = ((total_cancelled_orders / total_orders_all) * 100) if total_orders_all > 0 else 0.0

            return {
                "success": True,
                "period": period_norm,
                "date": start_date.isoformat(),
                "from_date": start_date.isoformat(),
                "to_date": end_date.isoformat(),
                "cancellations": cancellations,
                "items": items_flat,
                "by_channel": by_channel,
                "by_sku": by_sku,
                "daily_trend": daily_trend,
                "totals": {
                    "total_orders": total_orders_all,
                    "total_cancellations": total_cancelled_orders,
                    "total_items": total_cancelled_items,
                    "total_value": round(total_cancelled_value, 2),
                    "cod_orders": cod_orders,
                    "prepaid_orders": prepaid_orders,
                    "cancellation_rate": round(cancellation_rate, 2),
                },
                "search_results": {
                    "export_orders": total_orders_all,
                    "method": sales_result.get("data_source", "db_first_sales_orders"),
                    "total_time": round(total_fetch_time, 2),
                    "chunk_count": 1,
                },
                "data_source": sales_result.get("data_source", "db_first_sales_orders"),
                "fallback_used": bool(sales_result.get("fallback_used")),
                "last_synced_at": sales_result.get("last_synced_at"),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def get_sales_activity_report(
        self,
        from_date: str,
        to_date: str,
        channels: Optional[List[str]] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> Dict[str, Any]:
        try:
            report_started_at = datetime.now(timezone.utc)
            self._emit_progress(progress_cb, 5, "Validating sales activity date range…")

            ist = timezone(timedelta(hours=5, minutes=30))
            from_dt = datetime.strptime(str(from_date), "%Y-%m-%d").replace(
                hour=0,
                minute=0,
                second=0,
                tzinfo=ist,
            ).astimezone(timezone.utc)
            to_dt = datetime.strptime(str(to_date), "%Y-%m-%d").replace(
                hour=23,
                minute=59,
                second=59,
                tzinfo=ist,
            ).astimezone(timezone.utc)

            sales_fetch_started_at = datetime.now(timezone.utc)
            self._emit_progress(progress_cb, 18, "Fetching sales rows for selected range…")
            result = self.get_sales_data(
                period="custom",
                from_date=from_dt,
                to_date=to_dt,
                include_orders=False,
                include_summary=False,
            )
            sales_fetch_seconds = (datetime.now(timezone.utc) - sales_fetch_started_at).total_seconds()
            if not result.get("success"):
                return result

            raw_orders = list(result.get("_orders") or [])

            def _normalize_channel_filter(value: str) -> str:
                channel = (self._safe_str(value) or "UNKNOWN").upper()
                channel = channel.replace("-", "_").replace(" ", "_")
                while "__" in channel:
                    channel = channel.replace("__", "_")
                return channel

            selected_channels_norm = {
                _normalize_channel_filter(ch) for ch in (channels or []) if self._safe_str(ch)
            }
            if selected_channels_norm:
                raw_orders = [
                    order
                    for order in raw_orders
                    if _normalize_channel_filter(order.get("channel")) in selected_channels_norm
                ]

            self._emit_progress(progress_cb, 40, "Aggregating SKU, channel and size rows…")

            def _norm_sku(v: str) -> str:
                return self._safe_str(v).upper()

            def _norm_channel(v: str) -> str:
                ch = (self._safe_str(v) or "UNKNOWN").upper()
                ch = ch.replace("-", "_").replace(" ", "_")
                while "__" in ch:
                    ch = ch.replace("__", "_")
                return ch

            def _derive_item_type_size(item_type_name: str, size: str) -> str:
                size_norm = self._safe_str(size)
                if size_norm and size_norm.upper() != "UNKNOWN":
                    return size_norm
                item_type_norm = self._safe_str(item_type_name)
                if " - " in item_type_norm:
                    tail = self._safe_str(item_type_norm.rsplit(" - ", 1)[-1])
                    if tail:
                        return tail
                return "UNKNOWN"

            def _derive_style_name(item_type_name: str, item_type_size: str) -> str:
                name = self._safe_str(item_type_name)
                size_norm = self._safe_str(item_type_size)
                if not name:
                    return "UNKNOWN"

                if size_norm and size_norm.upper() != "UNKNOWN":
                    suffix = f" - {size_norm}"
                    if name.endswith(suffix):
                        style = self._safe_str(name[: -len(suffix)])
                        if style:
                            return style

                if " - " in name:
                    style = self._safe_str(name.rsplit(" - ", 1)[0])
                    if style:
                        return style

                return name

            def _is_placeholder_item_name(value: str, sku: str = "") -> bool:
                normalized = self._safe_str(value)
                if not normalized:
                    return True

                upper_value = normalized.upper()
                upper_sku = self._safe_str(sku).upper()

                if upper_value == "UNKNOWN":
                    return True
                if upper_sku and upper_value == upper_sku:
                    return True
                if normalized.startswith("{") and normalized.endswith("}"):
                    return True

                return False

            detail_map: Dict[Tuple[str, str, str], Dict[str, Any]] = defaultdict(
                lambda: {
                    "item_sku_code": "",
                    "item_type_name": "",
                    "bundle_sku_code_number": "",
                    "type": "UNKNOWN",
                    "tags": "",
                    "item_type_size": "UNKNOWN",
                    "style_name": "UNKNOWN",
                    "size": "",
                    "channel": "",
                    "selling_price": Decimal("0"),
                    "mrp": Decimal("0"),
                    "cost": Decimal("0"),
                    "total_sale_qty": 0,
                    "cancel_qty": 0,
                    "return_qty": 0,
                    "sale_amount": Decimal("0"),
                    "cancel_amount": Decimal("0"),
                    "return_amount": Decimal("0"),
                }
            )

            for order in raw_orders:
                status = self._safe_str(order.get("status")).upper()
                channel = self._safe_str(order.get("channel")) or "UNKNOWN"

                for item in list(order.get("saleOrderItems") or []):
                    sku = self._safe_str(item.get("itemSku"))
                    item_type = self._safe_str(item.get("itemTypeName") or item.get("itemName") or item.get("name"))
                    bundle_sku_code_number = self._safe_str(
                        item.get("bundleSkuCodeNumber") or item.get("bundle_sku_code_number")
                    )
                    size = self._safe_str(item.get("size"))
                    qty = self._safe_int(item.get("quantity"), default=1)
                    if qty <= 0:
                        qty = 1

                    if _is_placeholder_item_name(item_type, sku):
                        fallback_item_name = self._safe_str(item.get("itemName") or item.get("name"))
                        if not _is_placeholder_item_name(fallback_item_name, sku):
                            item_type = fallback_item_name

                    selling_price = self._safe_decimal(item.get("sellingPrice"), default=Decimal("0"))
                    line_amount = selling_price * Decimal(qty)

                    key = (sku, size, channel)
                    row = detail_map[key]
                    row["item_sku_code"] = sku
                    row["item_type_name"] = item_type
                    item_type_size = _derive_item_type_size(item_type, size)
                    item_type_style = _derive_style_name(item_type, item_type_size)
                    row["style_name"] = item_type_style
                    if not self._safe_str(row.get("bundle_sku_code_number")) and bundle_sku_code_number:
                        row["bundle_sku_code_number"] = bundle_sku_code_number
                    if self._safe_str(row.get("type")).upper() in {"", "UNKNOWN"}:
                        row["type"] = item_type_style
                    row["size"] = size
                    row["channel"] = channel
                    if self._safe_str(row.get("item_type_size")).upper() == "UNKNOWN":
                        row["item_type_size"] = item_type_size
                    if self._safe_decimal(row.get("selling_price"), default=Decimal("0")) <= 0 and selling_price > 0:
                        row["selling_price"] = selling_price

                    unit_mrp = self._safe_decimal(
                        self._pick(item, "maxRetailPrice", "MRP", "mrp"),
                        default=Decimal("0"),
                    )
                    unit_cost = self._safe_decimal(
                        self._pick(item, "costPrice", "Cost Price", "cost"),
                        default=Decimal("0"),
                    )
                    if self._safe_decimal(row.get("mrp"), default=Decimal("0")) <= 0 and unit_mrp > 0:
                        row["mrp"] = unit_mrp
                    if self._safe_decimal(row.get("cost"), default=Decimal("0")) <= 0 and unit_cost > 0:
                        row["cost"] = unit_cost

                    tags_val = self._safe_str(self._pick(item, "Tags", "tags"))
                    if not self._safe_str(row.get("tags")) and tags_val:
                        row["tags"] = tags_val

                    if status in {"CANCELLED", "CANCELED"}:
                        row["cancel_qty"] += qty
                        row["cancel_amount"] += line_amount
                    elif status in {"RETURNED", "REFUNDED"}:
                        row["return_qty"] += qty
                        row["return_amount"] += line_amount
                    else:
                        row["total_sale_qty"] += qty
                        row["sale_amount"] += line_amount

            norm_key_to_detail_keys: Dict[Tuple[str, str], List[Tuple[str, str, str]]] = defaultdict(list)
            order_sku_to_detail_keys: Dict[Tuple[str, str], List[Tuple[str, str, str]]] = defaultdict(list)
            order_code_to_channels: Dict[str, set[str]] = defaultdict(set)
            sku_to_channels: Dict[str, set[str]] = defaultdict(set)
            sku_channel_qty_in_range: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

            def _pick_top_channel(channel_counts: Dict[str, int]) -> str:
                ranked = sorted(
                    [
                        (self._safe_str(ch).upper(), int(cnt or 0))
                        for ch, cnt in (channel_counts or {}).items()
                        if self._safe_str(ch).upper() not in {"", "UNKNOWN"}
                    ],
                    key=lambda item: (-item[1], item[0]),
                )
                return ranked[0][0] if ranked else "UNKNOWN"

            for key in detail_map.keys():
                sku_key, _, channel_key = key
                norm_sku = _norm_sku(sku_key)
                norm_channel = _norm_channel(channel_key)
                norm_key_to_detail_keys[(norm_sku, norm_channel)].append(key)
                sku_to_channels[norm_sku].add(norm_channel)

            for order in raw_orders:
                order_code = self._safe_str(order.get("code"))
                if not order_code:
                    continue

                order_code_norm = order_code.upper()
                order_channel = self._safe_str(order.get("channel")) or "UNKNOWN"
                order_code_to_channels[order_code_norm].add(_norm_channel(order_channel))

                for item in list(order.get("saleOrderItems") or []):
                    sku = self._safe_str(item.get("itemSku"))
                    size = self._safe_str(item.get("size"))
                    qty = self._safe_int(item.get("quantity"), default=1)
                    if qty <= 0:
                        qty = 1
                    key = (sku, size, order_channel)
                    if key in detail_map:
                        order_sku_to_detail_keys[(order_code_norm, _norm_sku(sku))].append(key)

                    norm_sku = _norm_sku(sku)
                    norm_order_channel = _norm_channel(order_channel)
                    if norm_sku and norm_order_channel != "UNKNOWN":
                        sku_channel_qty_in_range[norm_sku][norm_order_channel] += qty

            return_map: Dict[Tuple[str, str], Dict[str, Any]] = defaultdict(
                lambda: {"qty": 0, "amount": Decimal("0")}
            )

            return_reconcile_started_at = datetime.now(timezone.utc)
            self._emit_progress(progress_cb, 58, "Reconciling return quantities…")
            db = self._get_db()
            return_order_channel_map: Dict[str, set[str]] = defaultdict(set)
            return_order_channel_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
            return_sku_channel_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
            sku_global_channel_pref: Dict[str, str] = {}
            default_return_channel = "UNKNOWN"
            try:
                return_records = (
                    db.query(
                        SalesReturnRecord.order_id,
                        SalesReturnRecord.sku,
                        SalesReturnRecord.return_qty,
                        SalesReturnRecord.refund_amount,
                        SalesReturnRecord.channel_entry,
                        SalesReturnRecord.created_at,
                        SalesReturnRecord.updated_at,
                    )
                    .filter(
                        or_(
                            and_(
                                SalesReturnRecord.updated_at >= from_dt,
                                SalesReturnRecord.updated_at <= to_dt,
                            ),
                            and_(
                                SalesReturnRecord.created_at >= from_dt,
                                SalesReturnRecord.created_at <= to_dt,
                            ),
                        )
                    )
                    .all()
                )

                unknown_return_order_ids = set()
                unknown_return_skus = set()
                for row in return_records:
                    row_order_code = self._safe_str(row.order_id).upper()
                    row_sku = _norm_sku(self._safe_str(row.sku))
                    row_channel = _norm_channel(self._safe_str(row.channel_entry))
                    row_qty = int(row.return_qty or 0) or 1
                    row_amount = self._safe_decimal(row.refund_amount, default=Decimal("0"))

                    if not row_sku:
                        continue

                    if row_channel != "UNKNOWN":
                        if row_order_code:
                            return_order_channel_counts[row_order_code][row_channel] += row_qty
                        return_sku_channel_counts[row_sku][row_channel] += row_qty
                    else:
                        if row_order_code:
                            unknown_return_order_ids.add(row_order_code)
                        unknown_return_skus.add(row_sku)

                    pending = return_map[(row_sku, row_channel)]
                    pending["qty"] += row_qty
                    pending["amount"] += row_amount

                return_order_ids = sorted(unknown_return_order_ids)
                if return_order_ids:
                    order_channel_rows = (
                        db.query(
                            SalesOrderRecord.order_id,
                            SalesOrderRecord.channel,
                        )
                        .filter(SalesOrderRecord.order_id.in_(return_order_ids))
                        .all()
                    )
                    for order_row in order_channel_rows:
                        mapped_order_id = self._safe_str(order_row.order_id).upper()
                        if mapped_order_id:
                            return_order_channel_map[mapped_order_id].add(
                                _norm_channel(order_row.channel)
                            )

                if unknown_return_skus:
                    global_channel_rows = (
                        db.query(
                            SalesOrderRecord.sku,
                            SalesOrderRecord.channel,
                            func.count(SalesOrderRecord.id).label("row_count"),
                        )
                        .filter(SalesOrderRecord.sku.in_(sorted(unknown_return_skus)))
                        .group_by(SalesOrderRecord.sku, SalesOrderRecord.channel)
                        .all()
                    )

                    sku_global_channel_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
                    global_channel_counts: Dict[str, int] = defaultdict(int)
                    for g_row in global_channel_rows:
                        g_sku = _norm_sku(g_row.sku)
                        g_channel = _norm_channel(g_row.channel)
                        g_count = int(g_row.row_count or 0)
                        if g_channel == "UNKNOWN" or g_count <= 0:
                            continue
                        if g_sku:
                            sku_global_channel_counts[g_sku][g_channel] += g_count
                        global_channel_counts[g_channel] += g_count

                    for g_sku, counts in sku_global_channel_counts.items():
                        top_channel = _pick_top_channel(counts)
                        if top_channel != "UNKNOWN":
                            sku_global_channel_pref[g_sku] = top_channel

                    default_return_channel = _pick_top_channel(global_channel_counts)
            finally:
                db.close()

            return_reconcile_seconds = (datetime.now(timezone.utc) - return_reconcile_started_at).total_seconds()

            if return_map:
                for (sku, channel), payload in return_map.items():
                    qty = int(payload.get("qty") or 0)
                    amount = self._safe_decimal(payload.get("amount"), default=Decimal("0"))

                    # If channel remains unknown, infer only for SKUs that map to a single channel.
                    effective_channel = channel
                    if effective_channel == "UNKNOWN":
                        top_return_sku_channel = _pick_top_channel(return_sku_channel_counts.get(sku) or {})
                        if top_return_sku_channel != "UNKNOWN":
                            effective_channel = top_return_sku_channel

                    if effective_channel == "UNKNOWN":
                        top_in_range_sku_channel = _pick_top_channel(sku_channel_qty_in_range.get(sku) or {})
                        if top_in_range_sku_channel != "UNKNOWN":
                            effective_channel = top_in_range_sku_channel

                    if effective_channel == "UNKNOWN":
                        sku_channels = [ch for ch in (sku_to_channels.get(sku) or set()) if ch != "UNKNOWN"]
                        if sku_channels:
                            effective_channel = sorted(sku_channels)[0]

                    if effective_channel == "UNKNOWN":
                        global_pref_channel = sku_global_channel_pref.get(sku) or "UNKNOWN"
                        if global_pref_channel != "UNKNOWN":
                            effective_channel = global_pref_channel

                    if effective_channel == "UNKNOWN" and default_return_channel != "UNKNOWN":
                        effective_channel = default_return_channel

                    matching_keys = norm_key_to_detail_keys.get((sku, effective_channel), [])
                    if not matching_keys:
                        unknown_key = (sku, "UNKNOWN", effective_channel)
                        unknown_row = detail_map[unknown_key]
                        unknown_row["item_sku_code"] = sku
                        unknown_row["item_type_name"] = self._safe_str(unknown_row.get("item_type_name"))
                        unknown_row["size"] = "UNKNOWN"
                        unknown_row["item_type_size"] = _derive_item_type_size(
                            self._safe_str(unknown_row.get("item_type_name")),
                            "UNKNOWN",
                        )
                        unknown_row["channel"] = effective_channel
                        unknown_row["return_qty"] += qty
                        unknown_row["return_amount"] += amount
                        continue

                    if len(matching_keys) == 1:
                        detail_map[matching_keys[0]]["return_qty"] += qty
                        detail_map[matching_keys[0]]["return_amount"] += amount
                        continue

                    sample_row = detail_map[matching_keys[0]]
                    unknown_key = (
                        self._safe_str(sample_row.get("item_sku_code")) or sku,
                        "UNKNOWN",
                        self._safe_str(sample_row.get("channel")) or effective_channel,
                    )
                    unknown_row = detail_map[unknown_key]
                    unknown_row["item_sku_code"] = self._safe_str(sample_row.get("item_sku_code")) or sku
                    unknown_row["item_type_name"] = self._safe_str(sample_row.get("item_type_name"))
                    unknown_row["size"] = "UNKNOWN"
                    unknown_row["item_type_size"] = _derive_item_type_size(
                        self._safe_str(sample_row.get("item_type_name")),
                        "UNKNOWN",
                    )
                    unknown_row["channel"] = self._safe_str(sample_row.get("channel")) or effective_channel
                    unknown_row["return_qty"] += qty
                    unknown_row["return_amount"] += amount

            items = list(detail_map.values())
            if selected_channels_norm:
                items = [
                    rec for rec in items
                    if _norm_channel(self._safe_str(rec.get("channel"))) in selected_channels_norm
                ]

            sku_preferred_name: Dict[str, str] = {}
            for rec in items:
                sku_code = self._safe_str(rec.get("item_sku_code"))
                item_name = self._safe_str(rec.get("item_type_name"))
                if sku_code and not _is_placeholder_item_name(item_name, sku_code) and sku_code not in sku_preferred_name:
                    sku_preferred_name[sku_code] = item_name

            unique_skus = sorted(
                {
                    self._safe_str(r.get("item_sku_code"))
                    for r in items
                    if self._safe_str(r.get("item_sku_code"))
                }
            )

            inventory_map: Dict[str, Dict[str, int]] = {}
            inventory_lookup_seconds = 0.0
            if unique_skus:
                inventory_lookup_started_at = datetime.now(timezone.utc)
                self._emit_progress(progress_cb, 80, "Loading current inventory snapshot…")
                inventory_map = self._fetch_inventory_snapshot_map_by_sku(unique_skus)
                inventory_lookup_seconds = (datetime.now(timezone.utc) - inventory_lookup_started_at).total_seconds()

            sku_metadata_map: Dict[str, Dict[str, Any]] = {}
            shopify_master_map: Dict[str, Dict[str, Any]] = {}
            if unique_skus:
                db = self._get_db()
                try:
                    shopify_rows = (
                        db.query(
                            ShopifyMasterData.variant_sku,
                            ShopifyMasterData.title,
                            ShopifyMasterData.type,
                            ShopifyMasterData.tags,
                            ShopifyMasterData.option1_value,
                            ShopifyMasterData.cost_per_item,
                        )
                        .filter(ShopifyMasterData.variant_sku.in_(unique_skus))
                        .all()
                    )

                    for shopify_row in shopify_rows:
                        sku_code = self._safe_str(shopify_row.variant_sku)
                        if not sku_code:
                            continue
                        shopify_master_map[sku_code] = {
                            "title": self._safe_str(shopify_row.title),
                            "type": self._safe_str(shopify_row.type),
                            "tags": self._safe_str(shopify_row.tags),
                            "option1_value": self._safe_str(shopify_row.option1_value),
                            "cost_per_item": self._safe_decimal(shopify_row.cost_per_item, default=Decimal("0")),
                        }

                    def _meta_pick_text(meta_row: Any, *attrs: str) -> str:
                        for attr in attrs:
                            val = self._safe_str(getattr(meta_row, attr, ""))
                            if val:
                                return val
                        return ""

                    date_filter = and_(
                        SalesOrderRecord.order_date.isnot(None),
                        SalesOrderRecord.order_date >= from_dt,
                        SalesOrderRecord.order_date <= to_dt,
                    )

                    latest_ids_subquery = (
                        db.query(
                            SalesOrderRecord.sku.label("sku"),
                            func.max(SalesOrderRecord.id).label("latest_id"),
                        )
                        .filter(SalesOrderRecord.sku.in_(unique_skus))
                        .filter(date_filter)
                        .group_by(SalesOrderRecord.sku)
                        .subquery()
                    )

                    metadata_rows = (
                        db.query(
                            SalesOrderRecord.sku,
                            SalesOrderRecord.product_name,
                            SalesOrderRecord.selling_price,
                            SalesOrderRecord.raw_data["Item Details"].astext.label("raw_item_details"),
                            SalesOrderRecord.raw_data["itemDetails"].astext.label("raw_item_details_alt"),
                            SalesOrderRecord.raw_data["Item Type Name"].astext.label("raw_item_type_name"),
                            SalesOrderRecord.raw_data["itemTypeName"].astext.label("raw_item_type_name_alt"),
                            SalesOrderRecord.raw_data["Item Name"].astext.label("raw_item_name"),
                            SalesOrderRecord.raw_data["itemName"].astext.label("raw_item_name_alt"),
                            SalesOrderRecord.raw_data["Name"].astext.label("raw_name"),
                            SalesOrderRecord.raw_data["Type"].astext.label("raw_type"),
                            SalesOrderRecord.raw_data["type"].astext.label("raw_type_alt"),
                            SalesOrderRecord.raw_data["Item Type"].astext.label("raw_item_type"),
                            SalesOrderRecord.raw_data["itemType"].astext.label("raw_item_type_alt"),
                            SalesOrderRecord.raw_data["Tags"].astext.label("raw_tags"),
                            SalesOrderRecord.raw_data["tags"].astext.label("raw_tags_alt"),
                            SalesOrderRecord.raw_data["MRP"].astext.label("raw_mrp"),
                            SalesOrderRecord.raw_data["Maximum Retail Price"].astext.label("raw_mrp_alt"),
                            SalesOrderRecord.raw_data["maxRetailPrice"].astext.label("raw_mrp_alt2"),
                            SalesOrderRecord.raw_data["Cost Price"].astext.label("raw_cost"),
                            SalesOrderRecord.raw_data["costPrice"].astext.label("raw_cost_alt"),
                            SalesOrderRecord.raw_data["cost"].astext.label("raw_cost_alt2"),
                            SalesOrderRecord.updated_at,
                            SalesOrderRecord.id,
                        )
                        .join(latest_ids_subquery, SalesOrderRecord.id == latest_ids_subquery.c.latest_id)
                        .all()
                    )

                    for meta_row in metadata_rows:
                        sku_code = self._safe_str(meta_row.sku)
                        if not sku_code:
                            continue

                        metadata = sku_metadata_map.setdefault(
                            sku_code,
                            {
                                "name": "",
                                "type": "",
                                "tags": "",
                                "selling_price": Decimal("0"),
                                "mrp": Decimal("0"),
                                "cost": Decimal("0"),
                            },
                        )

                        raw_name = _meta_pick_text(
                            meta_row,
                            "raw_item_details",
                            "raw_item_details_alt",
                            "raw_item_type_name",
                            "raw_item_type_name_alt",
                            "raw_item_name",
                            "raw_item_name_alt",
                            "raw_name",
                        )
                        raw_type = _meta_pick_text(meta_row, "raw_type", "raw_type_alt", "raw_item_type", "raw_item_type_alt")
                        raw_tags = _meta_pick_text(meta_row, "raw_tags", "raw_tags_alt")
                        raw_mrp = self._safe_decimal(
                            _meta_pick_text(meta_row, "raw_mrp", "raw_mrp_alt", "raw_mrp_alt2"),
                            default=Decimal("0"),
                        )
                        raw_cost = self._safe_decimal(
                            _meta_pick_text(meta_row, "raw_cost", "raw_cost_alt", "raw_cost_alt2"),
                            default=Decimal("0"),
                        )
                        raw_selling = self._safe_decimal(meta_row.selling_price, default=Decimal("0"))

                        candidate_name = raw_name or self._safe_str(meta_row.product_name)
                        if not metadata["name"] and not _is_placeholder_item_name(candidate_name, sku_code):
                            metadata["name"] = candidate_name
                        if not metadata["type"] and raw_type:
                            metadata["type"] = raw_type
                        if not metadata["tags"] and raw_tags:
                            metadata["tags"] = raw_tags
                        if metadata["selling_price"] <= 0 and raw_selling > 0:
                            metadata["selling_price"] = raw_selling
                        if metadata["mrp"] <= 0 and raw_mrp > 0:
                            metadata["mrp"] = raw_mrp
                        if metadata["cost"] <= 0 and raw_cost > 0:
                            metadata["cost"] = raw_cost

                        if metadata["mrp"] <= 0 and raw_selling > 0:
                            metadata["mrp"] = raw_selling
                        if metadata["cost"] <= 0 and metadata["mrp"] > 0:
                            metadata["cost"] = metadata["mrp"]

                    unresolved_name_skus = {
                        sku
                        for sku in unique_skus
                        if _is_placeholder_item_name(
                            self._safe_str((sku_metadata_map.get(sku) or {}).get("name")),
                            sku,
                        )
                    }

                    if unresolved_name_skus:
                        fallback_latest_ids_subquery = (
                            db.query(
                                SalesOrderRecord.sku.label("sku"),
                                func.max(SalesOrderRecord.id).label("latest_id"),
                            )
                            .filter(SalesOrderRecord.sku.in_(list(unresolved_name_skus)))
                            .group_by(SalesOrderRecord.sku)
                            .subquery()
                        )

                        fallback_rows = (
                            db.query(
                                SalesOrderRecord.sku,
                                SalesOrderRecord.product_name,
                                SalesOrderRecord.selling_price,
                                SalesOrderRecord.raw_data["Item Details"].astext.label("raw_item_details"),
                                SalesOrderRecord.raw_data["itemDetails"].astext.label("raw_item_details_alt"),
                                SalesOrderRecord.raw_data["Item Type Name"].astext.label("raw_item_type_name"),
                                SalesOrderRecord.raw_data["itemTypeName"].astext.label("raw_item_type_name_alt"),
                                SalesOrderRecord.raw_data["Item Name"].astext.label("raw_item_name"),
                                SalesOrderRecord.raw_data["itemName"].astext.label("raw_item_name_alt"),
                                SalesOrderRecord.raw_data["Name"].astext.label("raw_name"),
                                SalesOrderRecord.raw_data["Type"].astext.label("raw_type"),
                                SalesOrderRecord.raw_data["type"].astext.label("raw_type_alt"),
                                SalesOrderRecord.raw_data["Item Type"].astext.label("raw_item_type"),
                                SalesOrderRecord.raw_data["itemType"].astext.label("raw_item_type_alt"),
                                SalesOrderRecord.raw_data["Tags"].astext.label("raw_tags"),
                                SalesOrderRecord.raw_data["tags"].astext.label("raw_tags_alt"),
                                SalesOrderRecord.raw_data["MRP"].astext.label("raw_mrp"),
                                SalesOrderRecord.raw_data["Maximum Retail Price"].astext.label("raw_mrp_alt"),
                                SalesOrderRecord.raw_data["maxRetailPrice"].astext.label("raw_mrp_alt2"),
                                SalesOrderRecord.raw_data["Cost Price"].astext.label("raw_cost"),
                                SalesOrderRecord.raw_data["costPrice"].astext.label("raw_cost_alt"),
                                SalesOrderRecord.raw_data["cost"].astext.label("raw_cost_alt2"),
                                SalesOrderRecord.updated_at,
                                SalesOrderRecord.id,
                            )
                            .join(
                                fallback_latest_ids_subquery,
                                SalesOrderRecord.id == fallback_latest_ids_subquery.c.latest_id,
                            )
                            .all()
                        )

                        for meta_row in fallback_rows:
                            sku_code = self._safe_str(meta_row.sku)
                            if not sku_code:
                                continue

                            metadata = sku_metadata_map.setdefault(
                                sku_code,
                                {
                                    "name": "",
                                    "type": "",
                                    "tags": "",
                                    "selling_price": Decimal("0"),
                                    "mrp": Decimal("0"),
                                    "cost": Decimal("0"),
                                },
                            )

                            raw_name = _meta_pick_text(
                                meta_row,
                                "raw_item_details",
                                "raw_item_details_alt",
                                "raw_item_type_name",
                                "raw_item_type_name_alt",
                                "raw_item_name",
                                "raw_item_name_alt",
                                "raw_name",
                            )
                            raw_type = _meta_pick_text(meta_row, "raw_type", "raw_type_alt", "raw_item_type", "raw_item_type_alt")
                            raw_tags = _meta_pick_text(meta_row, "raw_tags", "raw_tags_alt")
                            raw_mrp = self._safe_decimal(
                                _meta_pick_text(meta_row, "raw_mrp", "raw_mrp_alt", "raw_mrp_alt2"),
                                default=Decimal("0"),
                            )
                            raw_cost = self._safe_decimal(
                                _meta_pick_text(meta_row, "raw_cost", "raw_cost_alt", "raw_cost_alt2"),
                                default=Decimal("0"),
                            )
                            raw_selling = self._safe_decimal(meta_row.selling_price, default=Decimal("0"))

                            candidate_name = raw_name or self._safe_str(meta_row.product_name)
                            if _is_placeholder_item_name(metadata.get("name"), sku_code) and not _is_placeholder_item_name(candidate_name, sku_code):
                                metadata["name"] = candidate_name

                            if not metadata["type"] and raw_type:
                                metadata["type"] = raw_type
                            if not metadata["tags"] and raw_tags:
                                metadata["tags"] = raw_tags
                            if metadata["selling_price"] <= 0 and raw_selling > 0:
                                metadata["selling_price"] = raw_selling
                            if metadata["mrp"] <= 0 and raw_mrp > 0:
                                metadata["mrp"] = raw_mrp
                            if metadata["cost"] <= 0 and raw_cost > 0:
                                metadata["cost"] = raw_cost

                            if metadata["mrp"] <= 0 and raw_selling > 0:
                                metadata["mrp"] = raw_selling
                            if metadata["cost"] <= 0 and metadata["mrp"] > 0:
                                metadata["cost"] = metadata["mrp"]
                finally:
                    db.close()

            self._emit_progress(progress_cb, 92, "Preparing final rows and totals…")
            for row in items:
                row["net_sale"] = int(row.get("total_sale_qty", 0) or 0) - int(row.get("cancel_qty", 0) or 0) - int(row.get("return_qty", 0) or 0)
                sale_amount = self._safe_decimal(row.get("sale_amount"), default=Decimal("0"))
                cancel_amount = self._safe_decimal(row.get("cancel_amount"), default=Decimal("0"))
                return_amount = self._safe_decimal(row.get("return_amount"), default=Decimal("0"))
                net_sale_amount = sale_amount - cancel_amount - return_amount

                row["sale_amount"] = self._to_money_float(sale_amount)
                row["cancel_amount"] = self._to_money_float(cancel_amount)
                row["return_amount"] = self._to_money_float(return_amount)
                row["net_sale_amount"] = self._to_money_float(net_sale_amount)

                sku_code = self._safe_str(row.get("item_sku_code"))
                metadata = sku_metadata_map.get(sku_code, {})
                shopify_master = shopify_master_map.get(sku_code, {})

                current_name = self._safe_str(row.get("item_type_name"))
                metadata_name = self._safe_str(metadata.get("name"))
                preferred_name = self._safe_str(sku_preferred_name.get(sku_code))
                sku_upper = sku_code.upper()
                metadata_upper = metadata_name.upper()

                if _is_placeholder_item_name(current_name, sku_code) and preferred_name and not _is_placeholder_item_name(preferred_name, sku_code):
                    row["item_type_name"] = preferred_name
                    current_name = preferred_name

                # Replace missing or SKU-like names with Item Type Name resolved from sales raw data.
                if _is_placeholder_item_name(current_name, sku_code) and metadata_name and (not sku_upper or metadata_upper != sku_upper):
                    row["item_type_name"] = metadata_name

                if _is_placeholder_item_name(self._safe_str(row.get("item_type_name")), sku_code):
                    row["item_type_name"] = "UNKNOWN"

                if _is_placeholder_item_name(self._safe_str(row.get("item_type_name")), sku_code):
                    shopify_title = self._safe_str(shopify_master.get("title"))
                    if shopify_title and not _is_placeholder_item_name(shopify_title, sku_code):
                        row["item_type_name"] = shopify_title

                row["item_type_size"] = _derive_item_type_size(
                    self._safe_str(row.get("item_type_name")),
                    self._safe_str(row.get("size")),
                )
                row["style_name"] = _derive_style_name(
                    self._safe_str(row.get("item_type_name")),
                    self._safe_str(row.get("item_type_size")),
                )
                if not self._safe_str(row.get("size")) or self._safe_str(row.get("size")).upper() == "UNKNOWN":
                    row["size"] = self._safe_str(row.get("item_type_size"))

                shopify_type = self._safe_str(shopify_master.get("type"))
                if shopify_type:
                    row["type"] = shopify_type
                elif self._safe_str(row.get("type")).upper() in {"", "UNKNOWN"}:
                    row["type"] = (
                        self._safe_str(metadata.get("type"))
                        or self._safe_str(row.get("style_name"))
                        or "UNKNOWN"
                    )
                if not self._safe_str(row.get("tags")):
                    row["tags"] = self._safe_str(shopify_master.get("tags")) or self._safe_str(metadata.get("tags"))

                current_mrp = self._safe_decimal(row.get("mrp"), default=Decimal("0"))
                current_cost = self._safe_decimal(row.get("cost"), default=Decimal("0"))
                current_selling_price = self._safe_decimal(row.get("selling_price"), default=Decimal("0"))
                meta_selling_price = self._safe_decimal(metadata.get("selling_price"), default=Decimal("0"))
                meta_mrp = self._safe_decimal(metadata.get("mrp"), default=Decimal("0"))
                meta_cost = self._safe_decimal(metadata.get("cost"), default=Decimal("0"))
                shopify_cost = self._safe_decimal(shopify_master.get("cost_per_item"), default=Decimal("0"))

                sale_qty = int(row.get("total_sale_qty", 0) or 0)
                per_unit_from_sales = (sale_amount / Decimal(sale_qty)) if sale_qty > 0 else Decimal("0")

                if current_selling_price <= 0:
                    if per_unit_from_sales > 0:
                        current_selling_price = per_unit_from_sales
                    elif meta_selling_price > 0:
                        current_selling_price = meta_selling_price

                if current_mrp <= 0:
                    if meta_mrp > 0:
                        current_mrp = meta_mrp
                    elif per_unit_from_sales > 0:
                        current_mrp = per_unit_from_sales
                    elif current_cost > 0:
                        current_mrp = current_cost

                # Business requirement for this report: MRP and selling price must match.
                # Use selling price as the primary display value, with MRP as fallback when needed.
                display_price = current_selling_price if current_selling_price > 0 else current_mrp
                if display_price > 0:
                    current_selling_price = display_price
                    current_mrp = display_price

                if current_cost <= 0:
                    if shopify_cost > 0:
                        current_cost = shopify_cost
                    elif meta_cost > 0:
                        current_cost = meta_cost
                    elif current_mrp > 0:
                        current_cost = current_mrp

                row["selling_price"] = self._to_money_float(current_selling_price)
                row["mrp"] = self._to_money_float(current_mrp)
                row["cost"] = self._to_money_float(current_cost)

                inv = inventory_map.get(self._safe_str(row.get("item_sku_code")), {})
                row["stock_good"] = inv.get("good_inventory", 0)
                row["stock_virtual"] = inv.get("virtual_inventory", 0)

            items.sort(
                key=lambda x: (
                    self._safe_str(x.get("item_sku_code")),
                    self._safe_str(x.get("size")),
                    self._safe_str(x.get("channel")),
                )
            )

            total_elapsed_seconds = (datetime.now(timezone.utc) - report_started_at).total_seconds()
            self._emit_progress(progress_cb, 98, "Finalizing sales activity response…")

            return {
                "success": True,
                "from_date": str(from_date),
                "to_date": str(to_date),
                "items": items,
                "total_skus": len(unique_skus),
                "data_source": result.get("data_source", "db_first"),
                "fallback_used": bool(result.get("fallback_used")),
                "last_synced_at": result.get("last_synced_at"),
                "diagnostics": {
                    "raw_orders_count": len(raw_orders),
                    "unique_skus_count": len(unique_skus),
                    "sales_fetch_seconds": round(sales_fetch_seconds, 2),
                    "return_reconcile_seconds": round(return_reconcile_seconds, 2),
                    "inventory_lookup_seconds": round(inventory_lookup_seconds, 2),
                    "total_elapsed_seconds": round(total_elapsed_seconds, 2),
                },
            }
        except ValueError as exc:
            return {
                "success": False,
                "error": f"Invalid date format. Use YYYY-MM-DD: {exc}",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def get_sales_activity_channels(self, from_date: str, to_date: str) -> Dict[str, Any]:
        """Return distinct channel names for a sales activity date range."""
        try:
            ist = timezone(timedelta(hours=5, minutes=30))
            from_dt = datetime.strptime(str(from_date), "%Y-%m-%d").replace(
                hour=0,
                minute=0,
                second=0,
                tzinfo=ist,
            ).astimezone(timezone.utc)
            to_dt = datetime.strptime(str(to_date), "%Y-%m-%d").replace(
                hour=23,
                minute=59,
                second=59,
                tzinfo=ist,
            ).astimezone(timezone.utc)

            db = self._get_db()
            try:
                date_filter = and_(
                    SalesOrderRecord.order_date.isnot(None),
                    SalesOrderRecord.order_date >= from_dt,
                    SalesOrderRecord.order_date <= to_dt,
                )

                rows = (
                    db.query(SalesOrderRecord.channel)
                    .filter(date_filter)
                    .distinct()
                    .all()
                )
            finally:
                db.close()

            channels = sorted(
                {
                    self._safe_str(row.channel)
                    for row in rows
                    if self._safe_str(row.channel)
                }
            )

            return {
                "success": True,
                "from_date": from_date,
                "to_date": to_date,
                "channels": channels,
            }
        except Exception as exc:
            logger.error("Error fetching sales activity channels: %s", exc, exc_info=True)
            return {
                "success": False,
                "from_date": from_date,
                "to_date": to_date,
                "channels": [],
                "error": str(exc),
            }

    def _aggregate_skus_from_orders(
        self,
        raw_orders: List[Dict[str, Any]],
        b2c_only: bool = False,
    ) -> List[Dict[str, Any]]:
        sku_map: Dict[str, Dict[str, Any]] = {}

        for order in raw_orders:
            status = self._safe_str(order.get("status")).upper()
            if status in self.EXCLUDED_STATUSES:
                continue

            channel = self._safe_str(order.get("channel")) or "UNKNOWN"
            for item in list(order.get("saleOrderItems") or []):
                sku = self._safe_str(item.get("itemSku")) or "UNKNOWN"
                qty = self._safe_int(item.get("quantity"), default=1)
                if qty <= 0:
                    qty = 1

                selling_price = self._safe_float(item.get("sellingPrice"), default=0.0)
                mrp = self._safe_float(item.get("maxRetailPrice"), default=0.0)
                price = selling_price if selling_price > 0 else mrp
                price_estimated = selling_price == 0 and mrp > 0
                is_unpriced = selling_price == 0 and mrp == 0

                if b2c_only and is_unpriced:
                    continue

                if sku not in sku_map:
                    sku_map[sku] = {
                        "sku": sku,
                        "name": self._safe_str(item.get("itemName")),
                        "quantity": 0,
                        "revenue": 0.0,
                        "order_count": 0,
                        "channels": {},
                        "estimated": False,
                        "unpriced": False,
                        "_unpriced_qty": 0,
                    }

                sku_map[sku]["quantity"] += qty
                sku_map[sku]["revenue"] += price * qty
                sku_map[sku]["order_count"] += 1
                if is_unpriced:
                    sku_map[sku]["_unpriced_qty"] += qty
                if price_estimated:
                    sku_map[sku]["estimated"] = True

                if channel not in sku_map[sku]["channels"]:
                    sku_map[sku]["channels"][channel] = 0
                sku_map[sku]["channels"][channel] += qty

        for sku_data in sku_map.values():
            sku_data["revenue"] = round(float(sku_data.get("revenue") or 0.0), 2)
            quantity = int(sku_data.get("quantity") or 0)
            sku_data["avg_price"] = round(
                (float(sku_data.get("revenue") or 0.0) / quantity),
                2,
            ) if quantity > 0 else 0.0
            sku_data["unpriced"] = int(sku_data.get("_unpriced_qty") or 0) >= quantity if quantity > 0 else False
            sku_data.pop("_unpriced_qty", None)

        return list(sku_map.values())

    def get_best_skus_monthly(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        limit: int = 20,
        b2c_only: bool = False,
    ) -> Dict[str, Any]:
        try:
            now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
            now_utc = now_ist.astimezone(timezone.utc)
            m = int(month or now_ist.month)
            y = int(year or now_ist.year)
            safe_limit = max(1, int(limit or 20))

            from_dt = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
            if m == 12:
                to_dt = datetime(y + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc) - timedelta(seconds=1)
            else:
                to_dt = datetime(y, m + 1, 1, 0, 0, 0, tzinfo=timezone.utc) - timedelta(seconds=1)

            if to_dt > now_utc:
                to_dt = now_utc

            sales_result = self.get_sales_data(
                period="custom",
                from_date=from_dt,
                to_date=to_dt,
            )
            if not sales_result.get("success"):
                return {
                    "success": False,
                    "error": sales_result.get("error", "Failed to fetch orders"),
                }

            raw_orders = list(sales_result.get("_orders") or [])
            all_skus = self._aggregate_skus_from_orders(raw_orders, b2c_only=b2c_only)
            top_skus = sorted(all_skus, key=lambda x: int(x.get("quantity") or 0), reverse=True)[:safe_limit]
            unpriced_count = sum(1 for sku in top_skus if bool(sku.get("unpriced")))

            return {
                "success": True,
                "month": m,
                "year": y,
                "period": f"{y}-{m:02d}",
                "total_skus": len(all_skus),
                "total_orders": len(raw_orders),
                "skus": top_skus,
                "b2c_only": bool(b2c_only),
                "unpriced_in_top": unpriced_count,
                "data_source": sales_result.get("data_source", "db_first"),
                "fallback_used": bool(sales_result.get("fallback_used")),
                "last_synced_at": sales_result.get("last_synced_at"),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def get_sku_velocity(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        limit: int = 25,
        min_qty: int = 1,
        b2c_only: bool = False,
    ) -> Dict[str, Any]:
        try:
            now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
            now_utc = now_ist.astimezone(timezone.utc)
            m = int(month or now_ist.month)
            y = int(year or now_ist.year)
            safe_limit = max(1, int(limit or 25))
            safe_min_qty = max(1, int(min_qty or 1))

            from_dt = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
            if m == 12:
                to_dt = datetime(y + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc) - timedelta(seconds=1)
            else:
                to_dt = datetime(y, m + 1, 1, 0, 0, 0, tzinfo=timezone.utc) - timedelta(seconds=1)

            if to_dt > now_utc:
                to_dt = now_utc

            sales_result = self.get_sales_data(
                period="custom",
                from_date=from_dt,
                to_date=to_dt,
            )
            if not sales_result.get("success"):
                return {
                    "success": False,
                    "error": sales_result.get("error", "Failed to fetch orders"),
                }

            raw_orders = list(sales_result.get("_orders") or [])
            all_skus = self._aggregate_skus_from_orders(raw_orders, b2c_only=b2c_only)

            fast_movers = sorted(all_skus, key=lambda x: int(x.get("quantity") or 0), reverse=True)[:safe_limit]
            qualified = [sku for sku in all_skus if int(sku.get("quantity") or 0) >= safe_min_qty]
            slow_movers = sorted(qualified, key=lambda x: int(x.get("quantity") or 0))[:safe_limit]

            return {
                "success": True,
                "month": m,
                "year": y,
                "period": f"{y}-{m:02d}",
                "total_skus": len(all_skus),
                "total_orders": len(raw_orders),
                "b2c_only": bool(b2c_only),
                "fast_movers": fast_movers,
                "slow_movers": slow_movers,
                "fast_count": len(fast_movers),
                "slow_count": len(slow_movers),
                "data_source": sales_result.get("data_source", "db_first"),
                "fallback_used": bool(sales_result.get("fallback_used")),
                "last_synced_at": sales_result.get("last_synced_at"),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def get_cod_vs_prepaid(
        self,
        period: str = "monthly",
        date: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        month: Optional[int] = None,
        year: Optional[int] = None,
    ) -> Dict[str, Any]:
        try:
            ist = timezone(timedelta(hours=5, minutes=30))
            now_ist = datetime.now(ist)
            now_date = now_ist.date()

            period_norm = self._safe_str(period or "monthly").lower()

            if from_date and to_date:
                start_date = datetime.strptime(str(from_date), "%Y-%m-%d").date()
                end_date = datetime.strptime(str(to_date), "%Y-%m-%d").date()
                period_norm = "custom"
            elif period_norm == "custom":
                if not from_date or not to_date:
                    return {
                        "success": False,
                        "error": "Both from_date and to_date are required for custom period",
                    }
                start_date = datetime.strptime(str(from_date), "%Y-%m-%d").date()
                end_date = datetime.strptime(str(to_date), "%Y-%m-%d").date()
            elif period_norm in {"daily", "weekly", "monthly"}:
                anchor = datetime.strptime(str(date), "%Y-%m-%d").date() if date else now_date
                if period_norm == "daily":
                    start_date = anchor
                    end_date = anchor
                elif period_norm == "weekly":
                    current_week_start = now_date - timedelta(days=now_date.weekday())
                    start_date = current_week_start - timedelta(days=7)
                    end_date = current_week_start - timedelta(days=1)
                else:
                    first_of_current_month = now_date.replace(day=1)
                    end_date = first_of_current_month - timedelta(days=1)
                    start_date = end_date.replace(day=1)
            else:
                m = int(month or now_ist.month)
                y = int(year or now_ist.year)
                start_date = datetime(y, m, 1).date()
                if m == 12:
                    end_date = datetime(y, 12, 31).date()
                else:
                    end_date = (datetime(y, m + 1, 1) - timedelta(days=1)).date()
                period_norm = "monthly"

            if start_date > end_date:
                return {
                    "success": False,
                    "error": "from_date cannot be greater than to_date",
                }

            from_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=ist).astimezone(timezone.utc)
            to_dt = datetime.combine(end_date, datetime.max.time().replace(microsecond=0)).replace(tzinfo=ist).astimezone(timezone.utc)
            now_utc = now_ist.astimezone(timezone.utc)
            if to_dt > now_utc:
                to_dt = now_utc

            sales_result = self.get_sales_data(
                period="custom",
                from_date=from_dt,
                to_date=to_dt,
            )
            if not sales_result.get("success"):
                return {
                    "success": False,
                    "error": sales_result.get("error", "Failed to fetch orders"),
                }

            raw_orders = list(sales_result.get("_orders") or [])

            cod_orders = 0
            cod_revenue = 0.0
            cod_items = 0
            prepaid_orders = 0
            prepaid_revenue = 0.0
            prepaid_items = 0
            channel_breakdown: Dict[str, Dict[str, Any]] = {}

            for order in raw_orders:
                status = self._safe_str(order.get("status")).upper()
                if status in self.EXCLUDED_STATUSES:
                    continue

                is_cod = bool(order.get("cod", False))
                channel = self._safe_str(order.get("channel")) or "UNKNOWN"
                order_revenue = 0.0
                order_items = 0

                for item in list(order.get("saleOrderItems") or []):
                    qty = self._safe_int(item.get("quantity"), default=1)
                    if qty <= 0:
                        qty = 1
                    price = self._safe_float(item.get("sellingPrice"), default=0.0)
                    order_revenue += price
                    order_items += qty

                if is_cod:
                    cod_orders += 1
                    cod_revenue += order_revenue
                    cod_items += order_items
                else:
                    prepaid_orders += 1
                    prepaid_revenue += order_revenue
                    prepaid_items += order_items

                if channel not in channel_breakdown:
                    channel_breakdown[channel] = {
                        "cod_orders": 0,
                        "cod_revenue": 0.0,
                        "prepaid_orders": 0,
                        "prepaid_revenue": 0.0,
                    }

                if is_cod:
                    channel_breakdown[channel]["cod_orders"] += 1
                    channel_breakdown[channel]["cod_revenue"] += order_revenue
                else:
                    channel_breakdown[channel]["prepaid_orders"] += 1
                    channel_breakdown[channel]["prepaid_revenue"] += order_revenue

            total_orders = cod_orders + prepaid_orders
            total_revenue = cod_revenue + prepaid_revenue

            for channel_data in channel_breakdown.values():
                channel_data["cod_revenue"] = round(float(channel_data.get("cod_revenue") or 0.0), 2)
                channel_data["prepaid_revenue"] = round(float(channel_data.get("prepaid_revenue") or 0.0), 2)

            channels = sorted(
                [{"channel": key, **value} for key, value in channel_breakdown.items()],
                key=lambda x: int(x.get("cod_orders", 0) or 0) + int(x.get("prepaid_orders", 0) or 0),
                reverse=True,
            )

            result = {
                "success": True,
                "period": period_norm,
                "from_date": start_date.isoformat(),
                "to_date": end_date.isoformat(),
                "cod": {
                    "orders": cod_orders,
                    "revenue": round(cod_revenue, 2),
                    "items": cod_items,
                    "percentage": round(cod_orders / total_orders * 100, 1) if total_orders > 0 else 0,
                    "avg_order_value": round(cod_revenue / cod_orders, 2) if cod_orders > 0 else 0,
                },
                "prepaid": {
                    "orders": prepaid_orders,
                    "revenue": round(prepaid_revenue, 2),
                    "items": prepaid_items,
                    "percentage": round(prepaid_orders / total_orders * 100, 1) if total_orders > 0 else 0,
                    "avg_order_value": round(prepaid_revenue / prepaid_orders, 2) if prepaid_orders > 0 else 0,
                },
                "total_orders": total_orders,
                "total_revenue": round(total_revenue, 2),
                "channels": channels,
                "month": start_date.month,
                "year": start_date.year,
                "data_source": sales_result.get("data_source", "db_first"),
                "fallback_used": bool(sales_result.get("fallback_used")),
                "last_synced_at": sales_result.get("last_synced_at"),
            }

            return result
        except ValueError as exc:
            return {
                "success": False,
                "error": f"Invalid date format. Use YYYY-MM-DD: {exc}",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def get_sales_by_sku(
        self,
        period: str = "today",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate sales by SKU from DB-first order payloads."""
        try:
            custom_from = None
            custom_to = None
            resolved_period = period

            if from_date and to_date:
                custom_from = datetime.strptime(from_date, "%Y-%m-%d").replace(
                    hour=0,
                    minute=0,
                    second=0,
                    tzinfo=timezone.utc,
                )
                custom_to = datetime.strptime(to_date, "%Y-%m-%d").replace(
                    hour=23,
                    minute=59,
                    second=59,
                    tzinfo=timezone.utc,
                )
                resolved_period = "custom"

            sales_result = self.get_sales_data(
                period=resolved_period,
                from_date=custom_from,
                to_date=custom_to,
            )
            if not sales_result.get("success", False):
                return {
                    "success": False,
                    "error": sales_result.get("error", "Failed to fetch orders"),
                    "skus": [],
                }

            dt_from = datetime.fromisoformat(
                str(sales_result.get("from_date")).replace("Z", "+00:00")
            )
            dt_to = datetime.fromisoformat(
                str(sales_result.get("to_date")).replace("Z", "+00:00")
            )
            raw_orders = list(sales_result.get("_orders") or [])

            sku_map: Dict[str, Dict[str, Any]] = {}
            for order in raw_orders:
                channel = self._safe_str(order.get("channel")) or "UNKNOWN"
                status = self._safe_str(order.get("status")).upper()
                if status in self.EXCLUDED_STATUSES:
                    continue

                for item in list(order.get("saleOrderItems") or []):
                    sku = self._safe_str(item.get("itemSku")) or "UNKNOWN"
                    if sku not in sku_map:
                        sku_map[sku] = {
                            "sku": sku,
                            "name": self._safe_str(item.get("itemTypeName") or item.get("itemName")),
                            "total_quantity": 0,
                            "total_revenue": 0.0,
                            "total_mrp": 0.0,
                            "total_discount": 0.0,
                            "order_count": 0,
                            "channels": {},
                            "avg_selling_price": 0.0,
                        }

                    qty = self._safe_int(item.get("quantity"), default=1)
                    if qty <= 0:
                        qty = 1

                    selling = self._safe_float(item.get("sellingPrice"), default=0.0)
                    mrp = self._safe_float(item.get("maxRetailPrice"), default=0.0)
                    if mrp <= 0:
                        mrp = selling

                    sku_map[sku]["total_quantity"] += qty
                    sku_map[sku]["total_revenue"] += selling * qty
                    sku_map[sku]["total_mrp"] += mrp * qty
                    sku_map[sku]["order_count"] += 1

                    if channel not in sku_map[sku]["channels"]:
                        sku_map[sku]["channels"][channel] = {
                            "quantity": 0,
                            "revenue": 0.0,
                        }
                    sku_map[sku]["channels"][channel]["quantity"] += qty
                    sku_map[sku]["channels"][channel]["revenue"] += selling * qty

            for sku_data in sku_map.values():
                sku_data["total_discount"] = round(
                    sku_data["total_mrp"] - sku_data["total_revenue"],
                    2,
                )
                if sku_data["total_discount"] < 0:
                    sku_data["total_discount"] = 0.0

                sku_data["discount_pct"] = round(
                    (sku_data["total_discount"] / sku_data["total_mrp"] * 100)
                    if sku_data["total_mrp"] > 0
                    else 0.0,
                    1,
                )

                if sku_data["total_quantity"] > 0:
                    sku_data["avg_selling_price"] = round(
                        sku_data["total_revenue"] / sku_data["total_quantity"],
                        2,
                    )
                    sku_data["avg_mrp"] = round(
                        sku_data["total_mrp"] / sku_data["total_quantity"],
                        2,
                    )
                else:
                    sku_data["avg_mrp"] = 0.0

                sku_data["total_revenue"] = round(sku_data["total_revenue"], 2)
                sku_data["total_mrp"] = round(sku_data["total_mrp"], 2)
                for channel_data in sku_data["channels"].values():
                    channel_data["revenue"] = round(channel_data["revenue"], 2)

            skus = sorted(
                sku_map.values(),
                key=lambda x: (-x["total_revenue"], -x["total_quantity"], x["sku"]),
            )

            total_revenue = round(sum(s["total_revenue"] for s in skus), 2)
            total_mrp = round(sum(s["total_mrp"] for s in skus), 2)
            total_quantity = sum(s["total_quantity"] for s in skus)
            total_discount = round(total_mrp - total_revenue, 2)
            if total_discount < 0:
                total_discount = 0.0

            return {
                "success": True,
                "period": period,
                "from_date": dt_from.isoformat(),
                "to_date": dt_to.isoformat(),
                "skus": skus,
                "summary": {
                    "total_skus": len(skus),
                    "total_quantity": total_quantity,
                    "total_revenue": total_revenue,
                    "total_mrp": total_mrp,
                    "total_discount": total_discount,
                    "total_orders": len(raw_orders),
                    "avg_discount_pct": round(
                        (total_discount / total_mrp * 100) if total_mrp > 0 else 0,
                        1,
                    ),
                },
                "data_source": sales_result.get("data_source", "db_first"),
                "fallback_used": bool(sales_result.get("fallback_used")),
                "last_synced_at": sales_result.get("last_synced_at"),
            }
        except Exception as exc:
            logger.error(f"Error in get_sales_by_sku: {exc}", exc_info=True)
            return {
                "success": False,
                "error": str(exc),
                "skus": [],
            }

    async def get_bundle_skus(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get bundle SKU catalogue with cache compatibility."""
        try:
            cache_key = "uc:bundle_skus:all"

            if not force_refresh:
                cached = CacheService.get(cache_key)
                if cached:
                    logger.info("BUNDLE SKUs: Redis cache hit")
                    cached["_cached"] = True
                    return cached
            else:
                CacheService.delete(cache_key)

            result = self._build_bundle_catalog_from_db()
            if result.get("success"):
                CacheService.set(cache_key, result, 14400)
                logger.info(
                    "BUNDLE SKUs: Cached (%s bundles)",
                    (result.get("summary") or {}).get("total_bundles", 0),
                )
            return result
        except Exception as exc:
            logger.error(f"Error in get_bundle_skus: {exc}", exc_info=True)
            return {
                "success": False,
                "error": str(exc),
            }

    def _is_fabric_payload(self, payload: Dict[str, Any]) -> bool:
        category = self._safe_str(
            self._pick(
                payload,
                "Category",
                "category",
                "Item Type Category",
                "categoryName",
                "Category Name",
                "categoryCode",
            )
        ).upper()
        return category == "FABRIC"

    def _build_bundle_catalog_from_db(self) -> Dict[str, Any]:
        empty_summary = {
            "total_bundles": 0,
            "enabled": 0,
            "disabled": 0,
            "avg_mrp": 0,
            "avg_cost": 0,
            "total_categories": 0,
            "categories": {},
        }

        db = self._get_db()
        try:
            item_master_job = (
                db.query(ExportJob)
                .filter(
                    ExportJob.export_type == "item_master",
                    ExportJob.status == "completed",
                )
                .order_by(ExportJob.completed_at.desc(), ExportJob.id.desc())
                .first()
            )

            if not item_master_job:
                return {
                    "success": True,
                    "bundles": [],
                    "summary": empty_summary,
                    "data_source": "none",
                    "fallback_used": False,
                    "last_synced_at": None,
                }

            row_payloads = (
                db.query(ExportRow.payload)
                .filter(ExportRow.export_job_id == item_master_job.id)
                .order_by(ExportRow.row_number.asc())
                .all()
            )

            bundle_map: Dict[str, Dict[str, Any]] = {}

            for wrapped_payload in row_payloads:
                row = dict(wrapped_payload[0] or {})
                row_type = self._safe_str(self._pick(row, "Type", "type")).upper()
                if row_type != "BUNDLE":
                    continue

                sku_code = self._safe_str(
                    self._pick(row, "Product Code", "SKU Code", "skuCode")
                )
                if not sku_code:
                    continue

                bundle = bundle_map.get(sku_code)
                if bundle is None:
                    bundle = {
                        "skuCode": sku_code,
                        "itemName": self._safe_str(
                            self._pick(row, "Name", "Item Name", "itemName")
                        )
                        or sku_code,
                        "category": self._safe_str(
                            self._pick(row, "Category Name", "Category", "category")
                        ),
                        "categoryCode": self._safe_str(
                            self._pick(row, "Category Code", "categoryCode")
                        ),
                        "costPrice": self._safe_float(
                            self._pick(row, "Cost Price", "costPrice")
                        ),
                        "mrp": self._safe_float(self._pick(row, "MRP", "mrp")),
                        "basePrice": self._safe_float(
                            self._pick(row, "Base Price", "basePrice")
                        ),
                        "color": self._safe_str(self._pick(row, "Color", "color")),
                        "size": self._safe_str(self._pick(row, "Size", "size")),
                        "brand": self._safe_str(self._pick(row, "Brand", "brand")),
                        "enabled": self._safe_bool(
                            self._pick(row, "Enabled", "enabled"),
                            default=True,
                        ),
                        "hsnCode": self._safe_str(self._pick(row, "HSN CODE", "hsnCode")),
                        "weight": self._safe_str(
                            self._pick(row, "Weight (gms)", "weight")
                        ),
                        "imageUrl": self._safe_str(
                            self._pick(row, "Image Url", "imageUrl")
                        ),
                        "updated": self._safe_str(self._pick(row, "Updated", "updated")),
                        "components": [],
                    }
                    bundle_map[sku_code] = bundle

                component_sku = self._safe_str(
                    self._pick(
                        row,
                        "Component Product Code",
                        "componentSku",
                        "Component SKU",
                    )
                )
                if component_sku:
                    bundle["components"].append(
                        {
                            "sku": component_sku,
                            "quantity": self._safe_str(
                                self._pick(
                                    row,
                                    "Component Quantity",
                                    "componentQuantity",
                                )
                            )
                            or "1",
                            "price": self._safe_str(
                                self._pick(
                                    row,
                                    "Component Price",
                                    "componentPrice",
                                )
                            ),
                        }
                    )

            bundles = sorted(
                bundle_map.values(),
                key=lambda item: self._safe_str(item.get("skuCode")),
            )
            for bundle in bundles:
                bundle["componentCount"] = len(bundle.get("components") or [])

            total_bundles = len(bundles)
            enabled_count = sum(1 for bundle in bundles if bool(bundle.get("enabled")))
            disabled_count = total_bundles - enabled_count

            mrp_values = [
                float(bundle.get("mrp") or 0.0)
                for bundle in bundles
                if float(bundle.get("mrp") or 0.0) > 0
            ]
            cost_values = [
                float(bundle.get("costPrice") or 0.0)
                for bundle in bundles
                if float(bundle.get("costPrice") or 0.0) > 0
            ]

            category_counts: Dict[str, int] = {}
            for bundle in bundles:
                category_name = self._safe_str(bundle.get("category")) or "Unknown"
                category_counts[category_name] = category_counts.get(category_name, 0) + 1

            summary = {
                "total_bundles": total_bundles,
                "enabled": enabled_count,
                "disabled": disabled_count,
                "avg_mrp": round(sum(mrp_values) / len(mrp_values), 2) if mrp_values else 0,
                "avg_cost": round(sum(cost_values) / len(cost_values), 2) if cost_values else 0,
                "total_categories": len(category_counts),
                "categories": dict(
                    sorted(category_counts.items(), key=lambda item: item[1], reverse=True)
                ),
            }

            return {
                "success": True,
                "bundles": bundles,
                "summary": summary,
                "export_job_id": int(item_master_job.id),
                "archived_rows": int(item_master_job.total_csv_rows or 0),
                "data_source": "archived_item_master_export_rows",
                "fallback_used": False,
                "last_synced_at": item_master_job.completed_at.isoformat()
                if item_master_job.completed_at
                else None,
            }
        finally:
            db.close()

    @staticmethod
    def _order_date_key(raw_value: Any) -> str:
        text = str(raw_value or "").strip()
        if not text:
            return ""
        return text[:10]

    async def get_bundle_sales_analysis(
        self,
        period: str = "last_30_days",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Run bundle sales analysis with compatibility cache behavior."""
        try:
            ist = timezone(timedelta(hours=5, minutes=30))
            now = datetime.now(ist)
            period_norm = self._safe_str(period or "last_30_days").lower()

            if period_norm == "today":
                dt_from, dt_to = self.uc_service.get_today_range()
                cache_suffix = f"today:{now.strftime('%Y-%m-%d')}"
                ttl = 300
            elif period_norm == "yesterday":
                dt_from, dt_to = self.uc_service.get_yesterday_range()
                cache_suffix = f"yesterday:{(now - timedelta(days=1)).strftime('%Y-%m-%d')}"
                ttl = 3600
            elif period_norm == "last_7_days":
                dt_from, dt_to = self.uc_service.get_last_n_days_range(7)
                cache_suffix = f"7d:{now.strftime('%Y-%m-%d')}"
                ttl = 1800
            elif period_norm == "last_30_days":
                dt_from, dt_to = self.uc_service.get_last_n_days_range(30)
                cache_suffix = f"30d:{now.strftime('%Y-%m-%d')}"
                ttl = 3600
            elif period_norm == "custom" and from_date and to_date:
                dt_from = datetime.strptime(from_date, "%Y-%m-%d").replace(
                    hour=0,
                    minute=0,
                    second=0,
                    tzinfo=ist,
                ).astimezone(timezone.utc)
                dt_to = datetime.strptime(to_date, "%Y-%m-%d").replace(
                    hour=23,
                    minute=59,
                    second=59,
                    tzinfo=ist,
                ).astimezone(timezone.utc)
                cache_suffix = f"custom:{from_date}_{to_date}"
                ttl = 3600
            else:
                return {
                    "success": False,
                    "error": "Invalid period. Use today|yesterday|last_7_days|last_30_days|custom",
                }

            now_utc = datetime.now(timezone.utc)
            if dt_to > now_utc:
                dt_to = now_utc

            cache_key = f"uc:bundle_analysis:{cache_suffix}"
            if not force_refresh:
                cached = CacheService.get(cache_key)
                if cached:
                    logger.info("Bundle Analysis: cache hit (%s)", cache_suffix)
                    cached["_cached"] = True
                    cached["period"] = period
                    return cached
            else:
                CacheService.delete(cache_key)

            bundle_catalog = await self.get_bundle_skus(force_refresh=False)
            if not bundle_catalog.get("success"):
                return {
                    "success": False,
                    "error": bundle_catalog.get("error", "Bundle catalogue unavailable"),
                    "bundle_sales": [],
                    "daily_trend": [],
                    "category_breakdown": {},
                    "channel_breakdown": {},
                    "summary": {},
                }

            bundles = list(bundle_catalog.get("bundles") or [])
            if not bundles:
                result = {
                    "success": True,
                    "period": period,
                    "from_date": dt_from.isoformat(),
                    "to_date": dt_to.isoformat(),
                    "bundle_sales": [],
                    "daily_trend": [],
                    "category_breakdown": {},
                    "channel_breakdown": {},
                    "summary": {
                        "total_orders": 0,
                        "orders_with_bundles": 0,
                        "total_bundle_units": 0,
                        "total_bundle_revenue": 0,
                        "unique_bundles_sold": 0,
                        "bundle_attach_rate": 0,
                        "avg_revenue_per_bundle": 0,
                        "analysis_time": 0,
                    },
                    "data_source": "db_first_empty_bundle_catalog",
                    "fallback_used": False,
                    "last_synced_at": bundle_catalog.get("last_synced_at"),
                }
                CacheService.set(cache_key, result, ttl)
                return result

            started_at = datetime.now(timezone.utc)

            reverse_index: Dict[str, set[str]] = {}
            component_map: Dict[str, Dict[str, int]] = {}
            bundle_meta: Dict[str, Dict[str, Any]] = {}

            for bundle in bundles:
                if not self._safe_bool(bundle.get("enabled"), default=True):
                    continue

                bundle_sku = self._safe_str(bundle.get("skuCode"))
                if not bundle_sku:
                    continue

                component_requirements: Dict[str, int] = {}
                for component in list(bundle.get("components") or []):
                    component_sku = self._safe_str(component.get("sku"))
                    if not component_sku:
                        continue
                    required_qty = self._safe_int(component.get("quantity"), default=1)
                    if required_qty <= 0:
                        required_qty = 1
                    component_requirements[component_sku] = required_qty

                if not component_requirements:
                    continue

                component_map[bundle_sku] = component_requirements
                bundle_meta[bundle_sku] = bundle
                for component_sku in component_requirements.keys():
                    reverse_index.setdefault(component_sku, set()).add(bundle_sku)

            sales_result = self.get_sales_data(
                period="custom",
                from_date=dt_from,
                to_date=dt_to,
            )
            if not sales_result.get("success"):
                return {
                    "success": False,
                    "error": sales_result.get("error", "Failed to fetch sales data"),
                    "bundle_sales": [],
                    "daily_trend": [],
                    "category_breakdown": {},
                    "channel_breakdown": {},
                    "summary": {},
                }

            raw_orders = list(sales_result.get("_orders") or [])

            if not raw_orders:
                elapsed = round(
                    (datetime.now(timezone.utc) - started_at).total_seconds(),
                    1,
                )
                result = {
                    "success": True,
                    "period": period,
                    "from_date": dt_from.isoformat(),
                    "to_date": dt_to.isoformat(),
                    "bundle_sales": [],
                    "daily_trend": [],
                    "category_breakdown": {},
                    "channel_breakdown": {},
                    "summary": {
                        "total_orders": 0,
                        "orders_with_bundles": 0,
                        "total_bundle_units": 0,
                        "total_bundle_revenue": 0,
                        "unique_bundles_sold": 0,
                        "bundle_attach_rate": 0,
                        "avg_revenue_per_bundle": 0,
                        "analysis_time": elapsed,
                    },
                    "data_source": sales_result.get("data_source", "db_first"),
                    "fallback_used": bool(sales_result.get("fallback_used")),
                    "last_synced_at": sales_result.get("last_synced_at"),
                }
                CacheService.set(cache_key, result, ttl)
                return result

            bundle_sales_agg: Dict[str, Dict[str, Any]] = {}
            daily_agg: Dict[str, Dict[str, Any]] = {}
            channel_agg: Dict[str, Dict[str, Any]] = {}
            orders_with_bundles = 0

            for order in raw_orders:
                status = self._safe_str(order.get("status")).upper()
                if status in self.EXCLUDED_STATUSES:
                    continue

                items = list(order.get("saleOrderItems") or order.get("items") or [])
                if not items:
                    continue

                channel = self._safe_str(order.get("channel")) or "UNKNOWN"
                date_key = self._order_date_key(order.get("created") or order.get("displayOrderDateTime"))

                sku_pool: Dict[str, int] = {}
                sku_prices: Dict[str, float] = {}
                for item in items:
                    sku = self._safe_str(item.get("itemSku") or item.get("sku"))
                    if not sku:
                        continue

                    qty = self._safe_int(item.get("quantity"), default=1)
                    if qty <= 0:
                        qty = 1
                    sku_pool[sku] = sku_pool.get(sku, 0) + qty

                    selling_price = self._safe_float(
                        item.get("sellingPrice") or item.get("selling_price"),
                        default=0.0,
                    )
                    if selling_price <= 0:
                        selling_price = self._safe_float(item.get("maxRetailPrice"), default=0.0)
                    if selling_price > 0:
                        sku_prices[sku] = selling_price

                if not sku_pool:
                    continue

                candidate_bundles: set[str] = set()
                for component_sku in sku_pool.keys():
                    candidate_bundles.update(reverse_index.get(component_sku, set()))

                if not candidate_bundles:
                    continue

                sorted_candidates = sorted(
                    candidate_bundles,
                    key=lambda sku: len(component_map.get(sku, {})),
                    reverse=True,
                )

                remaining_pool = dict(sku_pool)
                matched_bundles: set[str] = set()
                order_match_units = 0
                order_match_revenue = 0.0

                for bundle_sku in sorted_candidates:
                    requirements = component_map.get(bundle_sku, {})
                    if not requirements:
                        continue

                    while all(
                        remaining_pool.get(component_sku, 0) >= required_qty
                        for component_sku, required_qty in requirements.items()
                    ):
                        for component_sku, required_qty in requirements.items():
                            remaining_pool[component_sku] = (
                                remaining_pool.get(component_sku, 0) - required_qty
                            )

                        unit_revenue = 0.0
                        for component_sku, required_qty in requirements.items():
                            unit_revenue += sku_prices.get(component_sku, 0.0) * required_qty

                        meta = bundle_meta.get(bundle_sku, {})
                        agg = bundle_sales_agg.setdefault(
                            bundle_sku,
                            {
                                "skuCode": bundle_sku,
                                "itemName": self._safe_str(meta.get("itemName")) or bundle_sku,
                                "category": self._safe_str(meta.get("category")),
                                "mrp": self._safe_float(meta.get("mrp"), default=0.0),
                                "componentCount": self._safe_int(
                                    meta.get("componentCount"),
                                    default=len(list(meta.get("components") or [])),
                                ),
                                "units_sold": 0,
                                "revenue": 0.0,
                                "order_count": 0,
                                "channels": {},
                            },
                        )

                        agg["units_sold"] += 1
                        agg["revenue"] += unit_revenue
                        agg["channels"][channel] = agg["channels"].get(channel, 0) + 1

                        matched_bundles.add(bundle_sku)
                        order_match_units += 1
                        order_match_revenue += unit_revenue

                if order_match_units <= 0:
                    continue

                orders_with_bundles += 1
                for bundle_sku in matched_bundles:
                    bundle_sales_agg[bundle_sku]["order_count"] += 1

                if date_key:
                    day_bucket = daily_agg.setdefault(
                        date_key,
                        {"units": 0, "orders": 0, "revenue": 0.0},
                    )
                    day_bucket["units"] += order_match_units
                    day_bucket["orders"] += 1
                    day_bucket["revenue"] += order_match_revenue

                channel_bucket = channel_agg.setdefault(
                    channel,
                    {"units": 0, "orders": 0, "revenue": 0.0},
                )
                channel_bucket["units"] += order_match_units
                channel_bucket["orders"] += 1
                channel_bucket["revenue"] += order_match_revenue

            top_bundles = sorted(
                bundle_sales_agg.values(),
                key=lambda item: int(item.get("units_sold") or 0),
                reverse=True,
            )

            category_breakdown: Dict[str, Dict[str, Any]] = {}
            for bundle in top_bundles:
                category_name = self._safe_str(bundle.get("category")) or "Unknown"
                bucket = category_breakdown.setdefault(
                    category_name,
                    {"units": 0, "revenue": 0.0, "bundle_count": 0},
                )
                bucket["units"] += int(bundle.get("units_sold") or 0)
                bucket["revenue"] += float(bundle.get("revenue") or 0.0)
                bucket["bundle_count"] += 1

            for bucket in category_breakdown.values():
                bucket["revenue"] = round(float(bucket.get("revenue") or 0.0), 2)

            sorted_category_breakdown = dict(
                sorted(
                    category_breakdown.items(),
                    key=lambda item: float((item[1] or {}).get("revenue", 0) or 0),
                    reverse=True,
                )
            )

            daily_trend = []
            for date_key in sorted(daily_agg.keys()):
                row = daily_agg[date_key]
                daily_trend.append(
                    {
                        "date": date_key,
                        "units": int(row.get("units") or 0),
                        "orders": int(row.get("orders") or 0),
                        "revenue": round(float(row.get("revenue") or 0.0), 2),
                    }
                )

            channel_breakdown = {}
            for channel_name, channel_data in sorted(
                channel_agg.items(),
                key=lambda item: float((item[1] or {}).get("revenue", 0) or 0),
                reverse=True,
            ):
                channel_breakdown[channel_name] = {
                    "units": int((channel_data or {}).get("units", 0) or 0),
                    "orders": int((channel_data or {}).get("orders", 0) or 0),
                    "revenue": round(float((channel_data or {}).get("revenue", 0.0) or 0.0), 2),
                }

            bundle_sales = []
            for bundle in top_bundles:
                units_sold = int(bundle.get("units_sold") or 0)
                revenue = round(float(bundle.get("revenue") or 0.0), 2)
                bundle_sales.append(
                    {
                        "skuCode": self._safe_str(bundle.get("skuCode")),
                        "itemName": self._safe_str(bundle.get("itemName")),
                        "category": self._safe_str(bundle.get("category")),
                        "mrp": round(float(bundle.get("mrp") or 0.0), 2),
                        "componentCount": int(bundle.get("componentCount") or 0),
                        "units_sold": units_sold,
                        "revenue": revenue,
                        "order_count": int(bundle.get("order_count") or 0),
                        "avg_selling_price": round(revenue / units_sold, 2) if units_sold > 0 else 0,
                        "channels": dict(bundle.get("channels") or {}),
                    }
                )

            total_bundle_units = sum(int(bundle.get("units_sold") or 0) for bundle in bundle_sales)
            total_bundle_revenue = round(
                sum(float(bundle.get("revenue") or 0.0) for bundle in bundle_sales),
                2,
            )

            elapsed = round(
                (datetime.now(timezone.utc) - started_at).total_seconds(),
                1,
            )

            result = {
                "success": True,
                "period": period,
                "from_date": dt_from.isoformat(),
                "to_date": dt_to.isoformat(),
                "bundle_sales": bundle_sales,
                "daily_trend": daily_trend,
                "category_breakdown": sorted_category_breakdown,
                "channel_breakdown": channel_breakdown,
                "summary": {
                    "total_orders": len(raw_orders),
                    "orders_with_bundles": orders_with_bundles,
                    "total_bundle_units": total_bundle_units,
                    "total_bundle_revenue": total_bundle_revenue,
                    "unique_bundles_sold": len(bundle_sales),
                    "bundle_attach_rate": round(
                        (orders_with_bundles / len(raw_orders) * 100) if raw_orders else 0,
                        1,
                    ),
                    "avg_revenue_per_bundle": round(
                        (total_bundle_revenue / total_bundle_units) if total_bundle_units > 0 else 0,
                        2,
                    ),
                    "analysis_time": elapsed,
                },
                "data_source": sales_result.get("data_source", "db_first"),
                "fallback_used": bool(sales_result.get("fallback_used")),
                "last_synced_at": sales_result.get("last_synced_at"),
                "catalog_last_synced_at": bundle_catalog.get("last_synced_at"),
            }

            if result.get("success"):
                CacheService.set(cache_key, result, ttl)
                summary = result.get("summary", {})
                logger.info(
                    "Bundle Analysis: cached (%s units, Rs%s revenue in %ss)",
                    summary.get("total_bundle_units", 0),
                    summary.get("total_bundle_revenue", 0),
                    summary.get("analysis_time", 0),
                )

            return result
        except Exception as exc:
            logger.error(f"Error in get_bundle_sales_analysis: {exc}", exc_info=True)
            return {
                "success": False,
                "error": str(exc),
            }

    async def get_fabric_sales(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Get fabric-only sales report with compatibility cache behavior."""
        try:
            now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
            now_utc = datetime.now(timezone.utc)

            if from_date and to_date:
                from_dt = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                to_dt = datetime.strptime(to_date, "%Y-%m-%d").replace(
                    hour=23,
                    minute=59,
                    second=59,
                    tzinfo=timezone.utc,
                )
                period_name = f"custom_{from_date}_{to_date}"
                cache_key = f"uc:fabric_sales:custom:{from_date}_{to_date}"
            else:
                m = int(month or now_ist.month)
                y = int(year or now_ist.year)
                from_dt = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
                if m == 12:
                    to_dt = datetime(y + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc) - timedelta(seconds=1)
                else:
                    to_dt = datetime(y, m + 1, 1, 0, 0, 0, tzinfo=timezone.utc) - timedelta(seconds=1)
                period_name = f"{y}-{m:02d}"
                cache_key = f"uc:fabric_sales:{y}:{m}"

            if to_dt > now_utc:
                to_dt = now_utc

            if not force_refresh:
                cached = CacheService.get(cache_key)
                if cached:
                    logger.info("FABRIC SALES %s: Redis cache hit", period_name)
                    cached["_cached"] = True
                    return cached
            else:
                CacheService.delete(cache_key)

            db = self._get_db()
            try:
                normalized_records = (
                    db.query(
                        SalesOrderRecord.id,
                        SalesOrderRecord.order_id,
                        SalesOrderRecord.sale_order_item_code,
                        SalesOrderRecord.status,
                        SalesOrderRecord.channel,
                        SalesOrderRecord.sku,
                        SalesOrderRecord.product_name,
                        SalesOrderRecord.qty,
                        SalesOrderRecord.selling_price,
                        SalesOrderRecord.order_date,
                        SalesOrderRecord.created_at,
                        SalesOrderRecord.raw_data,
                        SalesOrderRecord.updated_at,
                    )
                    .filter(
                        and_(
                            SalesOrderRecord.order_date.isnot(None),
                            SalesOrderRecord.order_date >= from_dt,
                            SalesOrderRecord.order_date <= to_dt,
                        )
                    )
                    .all()
                )

                items_list: List[Dict[str, Any]] = []
                order_codes: set[str] = set()
                last_synced_at: Optional[str] = None

                if normalized_records:
                    last_synced = max(
                        (record.updated_at for record in normalized_records if record.updated_at),
                        default=None,
                    )
                    if last_synced:
                        last_synced_at = last_synced.isoformat()

                    for record in normalized_records:
                        status = self._safe_str(record.status).upper()
                        if status in self.EXCLUDED_STATUSES:
                            continue

                        raw = dict(record.raw_data or {})
                        if not self._is_fabric_payload(raw):
                            continue

                        quantity = int(record.qty or 0)
                        if quantity <= 0:
                            quantity = self._safe_int(
                                self._pick(raw, "Quantity", "Qty", "QTY", "quantity"),
                                default=1,
                            )
                        if quantity <= 0:
                            quantity = 1

                        created_dt = self._normalize_dt(record.order_date or record.created_at)
                        created_value = created_dt.isoformat() if created_dt else ""
                        order_code = self._safe_str(record.order_id)
                        if not order_code:
                            continue

                        order_codes.add(order_code)
                        items_list.append(
                            {
                                "soiCode": self._safe_str(record.sale_order_item_code),
                                "sku": self._safe_str(record.sku),
                                "orderCode": order_code,
                                "created": created_value,
                                "quantity": quantity,
                            }
                        )

                    data_source = "normalized_sales_orders"
                    fallback_used = False
                else:
                    raw_rows, completed_at = self._raw_sales_rows_from_job(db, from_dt, to_dt)
                    data_source = "raw_export_rows_fallback" if raw_rows else "none"
                    fallback_used = bool(raw_rows)
                    if completed_at is not None:
                        last_synced_at = completed_at.isoformat()

                    for raw in raw_rows:
                        status = self._safe_str(
                            self._pick(raw, "Sale Order Status", "status")
                        ).upper()
                        if status in self.EXCLUDED_STATUSES:
                            continue

                        if not self._is_fabric_payload(raw):
                            continue

                        created_dt = self._normalize_dt(
                            self.uc_service._parse_datetime(
                                self._pick(raw, "Created", "created")
                            )
                        )
                        if created_dt and (created_dt < from_dt or created_dt > to_dt):
                            continue

                        order_code = self._safe_str(
                            self._pick(raw, "Sale Order Code", "saleOrderCode", "code")
                        )
                        if not order_code:
                            continue

                        quantity = self._safe_int(
                            self._pick(
                                raw,
                                "Quantity",
                                "Qty",
                                "QTY",
                                "quantity",
                                "Sale Order Item Quantity",
                            ),
                            default=1,
                        )
                        if quantity <= 0:
                            quantity = 1

                        order_codes.add(order_code)
                        items_list.append(
                            {
                                "soiCode": self._safe_str(
                                    self._pick(raw, "Sale Order Item Code", "soicode")
                                ),
                                "sku": self._safe_str(
                                    self._pick(raw, "Item SKU Code", "skuCode", "itemSku")
                                ),
                                "orderCode": order_code,
                                "created": created_dt.isoformat() if created_dt else "",
                                "quantity": quantity,
                            }
                        )

                items_list.sort(
                    key=lambda row: (
                        self._safe_str(row.get("created")),
                        self._safe_str(row.get("orderCode")),
                        self._safe_str(row.get("soiCode")),
                    ),
                    reverse=True,
                )

                total_items = sum(int(row.get("quantity") or 0) for row in items_list)

                result = {
                    "success": True,
                    "period": period_name,
                    "from_date": from_dt.isoformat(),
                    "to_date": to_dt.isoformat(),
                    "summary": {
                        "total_orders": len(order_codes),
                        "total_items": total_items,
                    },
                    "items": items_list,
                    "total_items_count": len(items_list),
                    "data_source": data_source,
                    "fallback_used": fallback_used,
                    "last_synced_at": last_synced_at,
                }
            finally:
                db.close()

            if result.get("success"):
                is_current = from_date is None and (
                    int(month or now_ist.month) == now_ist.month
                    and int(year or now_ist.year) == now_ist.year
                )
                ttl = CacheService.TTL_VERY_LONG if is_current else 86400
                CacheService.set(cache_key, result, ttl)
                logger.info("FABRIC SALES %s: Cached (TTL=%ss)", period_name, ttl)

            return result
        except Exception as exc:
            logger.error(f"Error in get_fabric_sales: {exc}", exc_info=True)
            return {
                "success": False,
                "error": str(exc),
            }

    def search_sale_orders(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        display_start: int = 0,
        display_length: int = 100,
    ) -> Dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        start = self._normalize_dt(from_date) or (now_utc - timedelta(hours=24))
        end = self._normalize_dt(to_date) or now_utc

        if end < start:
            return {
                "successful": False,
                "error": "to_date cannot be earlier than from_date",
                "elements": [],
                "totalRecords": 0,
            }

        sales_data = self.get_sales_data(period="custom", from_date=start, to_date=end)
        if not sales_data.get("success"):
            return {
                "successful": False,
                "error": sales_data.get("error", "Failed to fetch orders"),
                "elements": [],
                "totalRecords": 0,
            }

        all_orders = list(sales_data.get("_orders", []))
        total_records = len(all_orders)

        safe_start = max(0, int(display_start or 0))
        safe_length = max(1, int(display_length or 100))
        paged_orders = all_orders[safe_start:safe_start + safe_length]

        return {
            "successful": True,
            "elements": paged_orders,
            "totalRecords": total_records,
            "data_source": sales_data.get("data_source", "db_first"),
            "fallback_used": bool(sales_data.get("fallback_used")),
            "last_synced_at": sales_data.get("last_synced_at"),
        }

    def get_order_details(self, order_code: str) -> Dict[str, Any]:
        code = self._safe_str(order_code)
        if not code:
            return {"successful": False, "error": "Order code is required"}

        db = self._get_db()
        try:
            normalized_records = (
                db.query(
                    SalesOrderRecord.id,
                    SalesOrderRecord.order_id,
                    SalesOrderRecord.sale_order_item_code,
                    SalesOrderRecord.status,
                    SalesOrderRecord.channel,
                    SalesOrderRecord.sku,
                    SalesOrderRecord.product_name,
                    SalesOrderRecord.qty,
                    SalesOrderRecord.selling_price,
                    SalesOrderRecord.order_date,
                    SalesOrderRecord.created_at,
                    SalesOrderRecord.raw_data,
                    SalesOrderRecord.updated_at,
                )
                .filter(
                    SalesOrderRecord.order_id == code,
                )
                .order_by(SalesOrderRecord.updated_at.desc(), SalesOrderRecord.id.desc())
                .all()
            )

            if normalized_records:
                order_dto = self._order_detail_from_normalized_rows(code, normalized_records)
                revenue_calc = self.uc_service.calculate_order_revenue(order_dto)
                return {
                    "successful": True,
                    "order": order_dto,
                    "revenue_info": revenue_calc,
                    "data_source": "normalized_sales_orders",
                    "fallback_used": False,
                    "last_synced_at": max(
                        (
                            record.updated_at.isoformat()
                            for record in normalized_records
                            if record.updated_at is not None
                        ),
                        default=None,
                    ),
                }

            raw_rows = (
                db.query(ExportRow.payload, ExportJob.completed_at)
                .join(ExportJob, ExportJob.id == ExportRow.export_job_id)
                .filter(
                    ExportJob.status == "completed",
                    ExportRow.entity_type == "sale_order",
                    ExportRow.entity_key == code,
                )
                .order_by(ExportJob.completed_at.desc(), ExportRow.row_number.asc())
                .all()
            )

            if raw_rows:
                payloads = [dict(row[0] or {}) for row in raw_rows]
                range_start = datetime(1970, 1, 1, tzinfo=timezone.utc)
                range_end = datetime.now(timezone.utc) + timedelta(days=1)
                line_rows = self._raw_line_rows_from_sales_payloads(payloads, range_start, range_end)
                orders = self._orders_from_line_rows(line_rows)
                legacy_orders = self._legacy_orders_from_orders(orders)
                target = next(
                    (order for order in legacy_orders if self._safe_str(order.get("code")) == code),
                    None,
                )
                if target:
                    revenue_calc = self.uc_service.calculate_order_revenue(target)
                    return {
                        "successful": True,
                        "order": target,
                        "revenue_info": revenue_calc,
                        "data_source": "raw_export_rows_fallback",
                        "fallback_used": True,
                        "last_synced_at": raw_rows[0][1].isoformat() if raw_rows[0][1] else None,
                    }

            return {
                "successful": False,
                "error": f"Order '{code}' not found in DB",
            }
        finally:
            db.close()

    def get_orders_paginated(
        self,
        period: str = "today",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 15,
    ) -> Dict[str, Any]:
        start, end, resolved_period = self._resolve_range(period, from_date, to_date)

        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 15), 500))

        db = self._get_db()
        try:
            normalized_records = (
                db.query(
                    SalesOrderRecord.id,
                    SalesOrderRecord.order_id,
                    SalesOrderRecord.status,
                    SalesOrderRecord.channel,
                    SalesOrderRecord.qty,
                    SalesOrderRecord.selling_price,
                    SalesOrderRecord.order_date,
                    SalesOrderRecord.created_at,
                    SalesOrderRecord.sku,
                    SalesOrderRecord.product_name,
                    SalesOrderRecord.raw_data,
                    SalesOrderRecord.updated_at,
                )
                .filter(
                    and_(
                        SalesOrderRecord.order_date.isnot(None),
                        SalesOrderRecord.order_date >= start,
                        SalesOrderRecord.order_date <= end,
                    )
                )
                .all()
            )

            if normalized_records:
                line_rows = [
                    {
                        "order_id": r.order_id,
                        "status": r.status,
                        "channel": r.channel,
                        "qty": r.qty,
                        "selling_price": float(r.selling_price or 0),
                        "order_date": self._normalize_dt(r.order_date),
                        "sku": r.sku,
                        "product_name": r.product_name,
                        "cod": self._safe_bool((r.raw_data or {}).get("COD") or (r.raw_data or {}).get("cod"), default=False),
                    }
                    for r in normalized_records
                ]
                orders = self._orders_from_line_rows(line_rows)
                last_synced = max((r.updated_at for r in normalized_records if r.updated_at), default=None)

                total_orders = len(orders)
                total_pages = max(1, (total_orders + page_size - 1) // page_size)
                safe_page = min(page, total_pages)
                start_idx = (safe_page - 1) * page_size
                end_idx = start_idx + page_size
                page_orders = orders[start_idx:end_idx]
                page_revenue = sum(float(o.get("net_revenue") or 0.0) for o in page_orders)

                return {
                    "success": True,
                    "period": resolved_period,
                    "from_date": start.isoformat(),
                    "to_date": end.isoformat(),
                    "data_source": "normalized_sales_orders",
                    "fallback_used": False,
                    "last_synced_at": last_synced.isoformat() if last_synced else None,
                    "data_health": {
                        "coverage": "normalized",
                        "normalized_rows": len(normalized_records),
                        "raw_rows": 0,
                    },
                    "orders": page_orders,
                    "pagination": {
                        "current_page": safe_page,
                        "page_size": page_size,
                        "total_orders": total_orders,
                        "total_pages": total_pages,
                        "has_next": safe_page < total_pages,
                        "has_previous": safe_page > 1,
                    },
                    "page_summary": {
                        "orders_on_page": len(page_orders),
                        "page_revenue": round(page_revenue, 2),
                    },
                    "revenue_method": "db_first_normalized",
                }

            raw_rows, completed_at = self._raw_sales_rows_from_job(db, start, end)
            line_rows = self._raw_line_rows_from_sales_payloads(raw_rows, start, end)

            if line_rows:
                orders = self._orders_from_line_rows(line_rows)
                total_orders = len(orders)
                total_pages = max(1, (total_orders + page_size - 1) // page_size)
                safe_page = min(page, total_pages)
                start_idx = (safe_page - 1) * page_size
                end_idx = start_idx + page_size
                page_orders = orders[start_idx:end_idx]
                page_revenue = sum(float(o.get("net_revenue") or 0.0) for o in page_orders)

                return {
                    "success": True,
                    "period": resolved_period,
                    "from_date": start.isoformat(),
                    "to_date": end.isoformat(),
                    "data_source": "raw_export_rows_fallback",
                    "fallback_used": True,
                    "last_synced_at": completed_at.isoformat() if completed_at else None,
                    "data_health": {
                        "coverage": "raw_fallback",
                        "normalized_rows": 0,
                        "raw_rows": len(line_rows),
                    },
                    "orders": page_orders,
                    "pagination": {
                        "current_page": safe_page,
                        "page_size": page_size,
                        "total_orders": total_orders,
                        "total_pages": total_pages,
                        "has_next": safe_page < total_pages,
                        "has_previous": safe_page > 1,
                    },
                    "page_summary": {
                        "orders_on_page": len(page_orders),
                        "page_revenue": round(page_revenue, 2),
                    },
                    "revenue_method": "db_first_normalized",
                }

            return {
                "success": True,
                "period": resolved_period,
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "data_source": "none",
                "fallback_used": False,
                "last_synced_at": None,
                "data_health": {
                    "coverage": "empty",
                    "normalized_rows": 0,
                    "raw_rows": 0,
                },
                "orders": [],
                "pagination": {
                    "current_page": 1,
                    "page_size": page_size,
                    "total_orders": 0,
                    "total_pages": 1,
                    "has_next": False,
                    "has_previous": False,
                },
                "page_summary": {
                    "orders_on_page": 0,
                    "page_revenue": 0.0,
                },
                "revenue_method": "db_first_normalized",
            }
        finally:
            db.close()

    def get_inventory_data(
        self,
        skus: Optional[List[str]] = None,
        warehouse: Optional[str] = None,
    ) -> Dict[str, Any]:
        db = self._get_db()
        try:
            query = db.query(InventorySnapshotRecord)

            warehouse_norm = self._safe_str(warehouse)
            if warehouse_norm:
                query = query.filter(InventorySnapshotRecord.warehouse == warehouse_norm)

            clean_skus = [self._safe_str(sku) for sku in (skus or []) if self._safe_str(sku)]
            if clean_skus:
                query = query.filter(InventorySnapshotRecord.sku.in_(clean_skus))

            records = query.all()
            if records:
                last_synced = max((r.updated_at for r in records if r.updated_at), default=None)
                items = [
                    {
                        "sku": r.sku,
                        "warehouse": r.warehouse,
                        "available_qty": int(r.available_qty or 0),
                        "reserved_qty": int(r.reserved_qty or 0),
                        "blocked_qty": int(r.blocked_qty or 0),
                        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                    }
                    for r in records
                ]

                return {
                    "success": True,
                    "data_source": "normalized_inventory_snapshots",
                    "fallback_used": False,
                    "last_synced_at": last_synced.isoformat() if last_synced else None,
                    "data_health": {
                        "coverage": "normalized",
                        "normalized_rows": len(records),
                        "raw_rows": 0,
                    },
                    "summary": {
                        "total_skus": len(items),
                        "total_available_qty": sum(i["available_qty"] for i in items),
                        "total_reserved_qty": sum(i["reserved_qty"] for i in items),
                        "total_blocked_qty": sum(i["blocked_qty"] for i in items),
                    },
                    "items": items,
                }

            inventory_job = (
                db.query(ExportJob)
                .filter(
                    ExportJob.export_type == "inventory_snapshot",
                    ExportJob.status == "completed",
                )
                .order_by(ExportJob.completed_at.desc(), ExportJob.id.desc())
                .first()
            )

            if not inventory_job:
                return {
                    "success": True,
                    "data_source": "none",
                    "fallback_used": False,
                    "last_synced_at": None,
                    "data_health": {
                        "coverage": "empty",
                        "normalized_rows": 0,
                        "raw_rows": 0,
                    },
                    "summary": {
                        "total_skus": 0,
                        "total_available_qty": 0,
                        "total_reserved_qty": 0,
                        "total_blocked_qty": 0,
                    },
                    "items": [],
                }

            row_payloads = (
                db.query(ExportRow.payload)
                .filter(ExportRow.export_job_id == inventory_job.id)
                .order_by(ExportRow.row_number.asc())
                .all()
            )

            snapshot_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for payload_wrap in row_payloads:
                payload = dict(payload_wrap[0] or {})
                sku = self._safe_str(self._pick(payload, "itemTypeSKU", "sku"))
                if not sku:
                    continue

                row_warehouse = self._safe_str(
                    self._pick(payload, "facilityCode", "warehouse")
                ) or warehouse_norm or "anthrilo"

                if warehouse_norm and row_warehouse != warehouse_norm:
                    continue
                if clean_skus and sku not in clean_skus:
                    continue

                key = (sku, row_warehouse)
                snapshot_map[key] = {
                    "sku": sku,
                    "warehouse": row_warehouse,
                    "available_qty": self._safe_int(self._pick(payload, "inventory", "available_qty")),
                    "reserved_qty": self._safe_int(
                        self._pick(payload, "openSale", "virtualInventory", "reserved_qty")
                    ),
                    "blocked_qty": self._safe_int(
                        self._pick(payload, "inventoryBlocked", "blocked_qty", "badInventory")
                    ),
                    "updated_at": inventory_job.completed_at.isoformat() if inventory_job.completed_at else None,
                }

            items = list(snapshot_map.values())

            return {
                "success": True,
                "data_source": "raw_export_rows_fallback",
                "fallback_used": True,
                "last_synced_at": inventory_job.completed_at.isoformat() if inventory_job.completed_at else None,
                "data_health": {
                    "coverage": "raw_fallback",
                    "normalized_rows": 0,
                    "raw_rows": len(row_payloads),
                },
                "summary": {
                    "total_skus": len(items),
                    "total_available_qty": sum(i["available_qty"] for i in items),
                    "total_reserved_qty": sum(i["reserved_qty"] for i in items),
                    "total_blocked_qty": sum(i["blocked_qty"] for i in items),
                },
                "items": items,
            }
        finally:
            db.close()

    def _get_item_master_catalog_metadata_map(self) -> Dict[str, Dict[str, Any]]:
        cache_key = "uc:item-master:catalog-metadata"
        cached = CacheService.get(cache_key)
        if isinstance(cached, dict):
            return cached

        db = self._get_db()
        try:
            item_master_job = (
                db.query(ExportJob)
                .filter(
                    ExportJob.export_type == "item_master",
                    ExportJob.status == "completed",
                )
                .order_by(ExportJob.completed_at.desc(), ExportJob.id.desc())
                .first()
            )

            if not item_master_job:
                return {}

            row_payloads = (
                db.query(ExportRow.payload)
                .filter(ExportRow.export_job_id == item_master_job.id)
                .order_by(ExportRow.row_number.asc())
                .all()
            )

            metadata: Dict[str, Dict[str, Any]] = {}
            for wrapped_payload in row_payloads:
                row = dict(wrapped_payload[0] or {})
                sku_code = self._safe_str(
                    self._pick(
                        row,
                        "Product Code",
                        "SKU Code",
                        "itemTypeSKU",
                        "skuCode",
                        "sku",
                    )
                )
                if not sku_code:
                    continue

                existing = metadata.get(sku_code, {})

                name = self._safe_str(existing.get("name")) or self._safe_str(
                    self._pick(row, "Name", "Item Name", "itemName", "name")
                )
                category_name = self._safe_str(existing.get("categoryName")) or self._safe_str(
                    self._pick(row, "Category Name", "Category", "categoryName", "category")
                )
                category_code = self._safe_str(existing.get("categoryCode")) or self._safe_str(
                    self._pick(row, "Category Code", "categoryCode")
                )
                color = self._safe_str(existing.get("color")) or self._safe_str(self._pick(row, "Color", "color"))
                size = self._safe_str(existing.get("size")) or self._safe_str(self._pick(row, "Size", "size"))
                brand = self._safe_str(existing.get("brand")) or self._safe_str(self._pick(row, "Brand", "brand"))
                hsn_code = self._safe_str(existing.get("hsnCode")) or self._safe_str(
                    self._pick(row, "HSN CODE", "HSN Code", "hsnCode")
                )
                description = self._safe_str(existing.get("description")) or self._safe_str(
                    self._pick(row, "Description", "description")
                )

                existing_price = existing.get("price")
                row_price = self._safe_float(
                    self._pick(row, "MRP", "mrp", "Base Price", "basePrice", "price"),
                    default=0.0,
                )
                price = float(existing_price) if existing_price not in (None, "") else row_price

                existing_cost = existing.get("costPrice")
                row_cost = self._safe_float(self._pick(row, "Cost Price", "costPrice"), default=0.0)
                cost_price = float(existing_cost) if existing_cost not in (None, "") else row_cost

                existing_weight = existing.get("weight")
                row_weight = self._safe_float(self._pick(row, "Weight (gms)", "weight"), default=0.0)
                weight = float(existing_weight) if existing_weight not in (None, "") else row_weight

                existing_enabled = existing.get("enabled")
                if existing_enabled is None:
                    enabled = self._safe_bool(self._pick(row, "Enabled", "enabled"), default=True)
                else:
                    enabled = bool(existing_enabled)

                ean = self._safe_str(existing.get("ean")) or self._safe_str(
                    self._pick(row, "EAN", "ean", "scanIdentifier", "UPC", "ISBN")
                )
                scan_identifier = self._safe_str(existing.get("scanIdentifier")) or self._safe_str(
                    self._pick(row, "scanIdentifier", "UPC", "ISBN")
                )

                metadata[sku_code] = {
                    "name": name,
                    "categoryName": category_name,
                    "categoryCode": category_code,
                    "color": color,
                    "size": size,
                    "brand": brand,
                    "hsnCode": hsn_code,
                    "description": description,
                    "price": round(price, 2),
                    "costPrice": round(cost_price, 2),
                    "weight": weight,
                    "enabled": enabled,
                    "ean": ean,
                    "scanIdentifier": scan_identifier,
                }

            CacheService.set(cache_key, metadata, 6 * 60 * 60)
            return metadata
        finally:
            db.close()

    def _get_product_master_metadata_map(
        self,
        db: Session,
        skus: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        clean_skus = [self._safe_str(sku) for sku in skus if self._safe_str(sku)]
        if not clean_skus:
            return {}

        try:
            rows = (
                db.query(
                    ProductMaster.sku,
                    ProductMaster.name,
                    ProductMaster.size,
                    ProductMaster.type,
                    ProductMaster.net_weight,
                )
                .filter(ProductMaster.sku.in_(clean_skus))
                .all()
            )
        except Exception as exc:
            logger.warning("Catalog metadata: product_master lookup skipped: %s", exc)
            return {}

        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            sku = self._safe_str(row.sku)
            if not sku:
                continue
            result[sku] = {
                "name": self._safe_str(row.name),
                "size": self._safe_str(row.size),
                "categoryName": self._safe_str(row.type),
                "weight": self._safe_float(row.net_weight, default=0.0),
            }
        return result

    def _get_sales_order_catalog_metadata_map(
        self,
        db: Session,
        skus: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        clean_skus = [self._safe_str(sku) for sku in skus if self._safe_str(sku)]
        if not clean_skus:
            return {}
        # Prevent pathological IN-list queries on very large SKU sets.
        if len(clean_skus) > 1000:
            return {}

        rows = (
            db.query(
                SalesOrderRecord.sku,
                SalesOrderRecord.product_name,
                SalesOrderRecord.raw_data,
                SalesOrderRecord.updated_at,
            )
            .filter(SalesOrderRecord.sku.in_(clean_skus))
            .order_by(SalesOrderRecord.updated_at.desc())
            .all()
        )

        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            sku = self._safe_str(row.sku)
            if not sku or sku in result:
                continue

            raw = dict(row.raw_data or {})
            result[sku] = {
                "name": self._safe_str(row.product_name)
                or self._safe_str(self._pick(raw, "Item Details", "itemName", "itemTypeName", "Name")),
                "categoryName": self._safe_str(
                    self._pick(raw, "Category Name", "Category", "categoryName", "category")
                ),
                "categoryCode": self._safe_str(self._pick(raw, "Category Code", "categoryCode")),
                "color": self._safe_str(self._pick(raw, "Color", "color")),
                "size": self._safe_str(self._pick(raw, "Size", "size")),
                "brand": self._safe_str(self._pick(raw, "Brand", "brand")),
                "hsnCode": self._safe_str(self._pick(raw, "HSN CODE", "HSN Code", "hsnCode")),
            }

        return result

    def _inventory_record_to_catalog_element(
        self,
        record: InventorySnapshotRecord,
        item_master_meta: Optional[Dict[str, Any]] = None,
        product_master_meta: Optional[Dict[str, Any]] = None,
        sales_order_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raw: Dict[str, Any] = {}
        item_master_meta = item_master_meta or {}
        product_master_meta = product_master_meta or {}
        sales_order_meta = sales_order_meta or {}

        inventory = int(record.available_qty or 0)
        reserved = int(record.reserved_qty or 0)
        blocked = int(record.blocked_qty or 0)

        category_name = self._safe_str(
            self._safe_str(record.category_name)
            or self._pick(raw, "categoryName", "Category Name", "category")
            or item_master_meta.get("categoryName")
            or product_master_meta.get("categoryName")
            or sales_order_meta.get("categoryName")
        ) or "Uncategorized"

        item_name = self._safe_str(
            self._safe_str(record.item_type_name)
            or self._pick(raw, "itemTypeName", "itemName", "name")
            or item_master_meta.get("name")
            or product_master_meta.get("name")
            or sales_order_meta.get("name")
        ) or self._safe_str(record.sku)

        price = self._safe_float(
            self._safe_str(record.cost_price_csv)
            or self._pick(raw, "price", "mrp", "MRP", "costPrice", "Cost Price")
            or item_master_meta.get("price"),
            default=0.0,
        )

        cost_price = self._safe_float(
            self._pick(raw, "costPrice", "Cost Price", "price", "mrp", "MRP")
            or item_master_meta.get("costPrice"),
            default=0.0,
        )

        return {
            "skuCode": self._safe_str(record.sku),
            "name": item_name,
            "description": self._safe_str(self._pick(raw, "description", "Description") or item_master_meta.get("description")),
            "categoryName": category_name,
            "categoryCode": self._safe_str(
                self._pick(raw, "categoryCode", "Category Code", "category")
                or item_master_meta.get("categoryCode")
                or sales_order_meta.get("categoryCode")
            ) or category_name,
            "color": self._safe_str(
                self._safe_str(record.color)
                or self._pick(raw, "color", "Color")
                or item_master_meta.get("color")
                or sales_order_meta.get("color")
            ) or "-",
            "size": self._safe_str(
                self._safe_str(record.size)
                or self._pick(raw, "size", "Size")
                or item_master_meta.get("size")
                or product_master_meta.get("size")
                or sales_order_meta.get("size")
            ) or "-",
            "brand": self._safe_str(
                self._safe_str(record.brand)
                or self._pick(raw, "brand", "Brand")
                or item_master_meta.get("brand")
                or sales_order_meta.get("brand")
            ) or "-",
            "price": round(price, 2),
            "costPrice": round(cost_price, 2),
            "hsnCode": self._safe_str(
                self._pick(raw, "hsnCode", "HSN Code")
                or item_master_meta.get("hsnCode")
                or sales_order_meta.get("hsnCode")
            ) or "-",
            "weight": self._safe_float(
                self._pick(raw, "weight", "Weight")
                or item_master_meta.get("weight")
                or product_master_meta.get("weight"),
                default=0.0,
            ),
            "enabled": self._safe_bool(
                self._pick(raw, "enabled", "Enabled")
                if self._pick(raw, "enabled", "Enabled") is not None
                else item_master_meta.get("enabled"),
                default=True,
            ),
            "ean": self._safe_str(record.ean) or self._safe_str(self._pick(raw, "ean", "EAN") or item_master_meta.get("ean")) or "-",
            "scanIdentifier": self._safe_str(
                self._pick(raw, "scanIdentifier", "UPC", "ISBN")
                or item_master_meta.get("scanIdentifier")
            ),
            "warehouse": self._safe_str(record.warehouse),
            "inventorySnapshots": [
                {
                    "inventory": inventory,
                    "goodInventory": inventory,
                    "availableInventory": inventory,
                    "virtualInventory": reserved,
                    "openSale": reserved,
                    "badInventory": blocked,
                    "inventoryBlocked": blocked,
                    "putawayPending": self._safe_int(self._pick(raw, "putawayPending", "Putaway Pending")),
                }
            ],
        }

    def get_inventory_catalog_search(
        self,
        keyword: Optional[str] = None,
        display_start: int = 0,
        display_length: int = 25,
        warehouse: Optional[str] = None,
        category: Optional[str] = None,
        stock_filter: str = "all",
        include_inventory_snapshot: bool = True,
    ) -> Dict[str, Any]:
        db = self._get_db()
        try:
            safe_start = max(0, int(display_start or 0))
            safe_length = max(1, min(500, int(display_length or 25)))
            keyword_norm = self._safe_str(keyword).lower()
            category_norm = self._safe_str(category).lower()
            stock_filter_norm = self._safe_str(stock_filter).lower() or "all"
            warehouse_norm = self._safe_str(warehouse) or "anthrilo"

            item_master_job = (
                db.query(ExportJob)
                .filter(
                    ExportJob.export_type == "item_master",
                    ExportJob.status == "completed",
                )
                .order_by(ExportJob.completed_at.desc(), ExportJob.id.desc())
                .first()
            )
            if not item_master_job:
                return {
                    "successful": True,
                    "data_source": "none",
                    "fallback_used": False,
                    "last_synced_at": None,
                    "totalRecords": 0,
                    "displayStart": safe_start,
                    "displayLength": safe_length,
                    "elements": [],
                }

            inv_table = self._resolve_inventory_snapshot_table_name(db)
            inv_table = inv_table or "inventory_snapshots"

            like = f"%{keyword_norm}%"
            base_where = """
                er.export_job_id = :job_id
                AND (:keyword = '' OR (
                    COALESCE(NULLIF(er.payload->>'SKU Code',''), NULLIF(er.payload->>'Product Code',''), NULLIF(er.payload->>'itemTypeSKU','')) ILIKE :like
                    OR COALESCE(NULLIF(er.payload->>'Name',''), NULLIF(er.payload->>'Item Name',''), NULLIF(er.payload->>'itemName','')) ILIKE :like
                    OR COALESCE(NULLIF(er.payload->>'Category Name',''), NULLIF(er.payload->>'Category',''), NULLIF(er.payload->>'categoryName','')) ILIKE :like
                    OR COALESCE(NULLIF(er.payload->>'Brand',''), NULLIF(er.payload->>'brand','')) ILIKE :like
                ))
                AND (:category = '' OR lower(COALESCE(NULLIF(er.payload->>'Category Name',''), NULLIF(er.payload->>'Category',''), NULLIF(er.payload->>'categoryName',''))) = :category)
            """

            stock_join = ""
            stock_where = ""
            if stock_filter_norm in {"in_stock", "out_of_stock"}:
                stock_join = f"""
                    LEFT JOIN (
                        SELECT sku, SUM(available_qty)::bigint AS inv
                        FROM {inv_table}
                        WHERE warehouse = :warehouse
                        GROUP BY sku
                    ) inv ON inv.sku = COALESCE(NULLIF(er.payload->>'SKU Code',''), NULLIF(er.payload->>'Product Code',''), NULLIF(er.payload->>'itemTypeSKU',''))
                """
                if stock_filter_norm == "in_stock":
                    stock_where = " AND COALESCE(inv.inv, 0) > 0 "
                else:
                    stock_where = " AND COALESCE(inv.inv, 0) <= 0 "

            count_stmt = text(
                f"""
                WITH items AS (
                    SELECT
                        sku,
                        MAX(name) AS name,
                        MAX(description) AS description,
                        MAX(category_name) AS category_name,
                        MAX(category_code) AS category_code,
                        MAX(color) AS color,
                        MAX(size) AS size,
                        MAX(brand) AS brand,
                        MAX(hsn) AS hsn,
                        MAX(mrp) AS mrp,
                        MAX(weight_gms) AS weight_gms,
                        MAX(enabled) AS enabled
                    FROM (
                        SELECT
                            COALESCE(NULLIF(er.payload->>'SKU Code',''), NULLIF(er.payload->>'Product Code',''), NULLIF(er.payload->>'itemTypeSKU','')) AS sku,
                            COALESCE(NULLIF(er.payload->>'Name',''), NULLIF(er.payload->>'Item Name',''), NULLIF(er.payload->>'itemName','')) AS name,
                            COALESCE(NULLIF(er.payload->>'Description',''), NULLIF(er.payload->>'description','')) AS description,
                            COALESCE(NULLIF(er.payload->>'Category Name',''), NULLIF(er.payload->>'Category',''), NULLIF(er.payload->>'categoryName','')) AS category_name,
                            COALESCE(NULLIF(er.payload->>'Category Code',''), NULLIF(er.payload->>'categoryCode','')) AS category_code,
                            COALESCE(NULLIF(er.payload->>'Color',''), NULLIF(er.payload->>'color','')) AS color,
                            COALESCE(NULLIF(er.payload->>'Size',''), NULLIF(er.payload->>'size','')) AS size,
                            COALESCE(NULLIF(er.payload->>'Brand',''), NULLIF(er.payload->>'brand','')) AS brand,
                            COALESCE(NULLIF(er.payload->>'HSN CODE',''), NULLIF(er.payload->>'HSN Code',''), NULLIF(er.payload->>'hsnCode','')) AS hsn,
                            COALESCE(NULLIF(er.payload->>'MRP',''), NULLIF(er.payload->>'mrp',''), NULLIF(er.payload->>'Base Price',''), NULLIF(er.payload->>'basePrice','')) AS mrp,
                            COALESCE(NULLIF(er.payload->>'Weight (gms)',''), NULLIF(er.payload->>'weight','')) AS weight_gms,
                            lower(trim(COALESCE(NULLIF(er.payload->>'Enabled',''), NULLIF(er.payload->>'enabled','')))) AS enabled,
                            upper(trim(COALESCE(NULLIF(er.payload->>'Sku Type',''), NULLIF(er.payload->>'SkuType','')))) AS sku_type,
                            upper(trim(COALESCE(NULLIF(er.payload->>'Type',''), NULLIF(er.payload->>'type','')))) AS itype
                        FROM export_rows er
                        WHERE er.export_job_id = :job_id
                    ) t
                    WHERE t.sku IS NOT NULL
                      AND t.sku <> ''
                      AND lower(trim(t.sku)) NOT IN ('zeroskuu','0','-')
                      AND t.enabled IN ('true','1','yes','y')
                      AND t.sku_type = 'GOODS'
                      AND t.itype = 'SIMPLE'
                      AND (t.mrp IS NOT NULL AND t.mrp <> '' AND (t.mrp)::numeric > 0)
                    GROUP BY sku
                )
                SELECT COUNT(*)::bigint
                FROM items
                {stock_join}
                WHERE (:keyword = '' OR (
                    items.sku ILIKE :like
                    OR COALESCE(items.name,'') ILIKE :like
                    OR COALESCE(items.category_name,'') ILIKE :like
                    OR COALESCE(items.brand,'') ILIKE :like
                ))
                AND (:category = '' OR lower(COALESCE(items.category_name,'')) = :category)
                {stock_where}
                """
            )
            total_records = int(
                db.execute(
                    count_stmt,
                    {
                        "job_id": int(item_master_job.id),
                        "keyword": keyword_norm,
                        "like": like,
                        "category": category_norm,
                        "warehouse": warehouse_norm,
                    },
                ).scalar()
                or 0
            )

            page_stmt = text(
                f"""
                WITH items AS (
                    SELECT
                        sku,
                        MAX(name) AS name,
                        MAX(description) AS description,
                        MAX(category_name) AS category_name,
                        MAX(category_code) AS category_code,
                        MAX(color) AS color,
                        MAX(size) AS size,
                        MAX(brand) AS brand,
                        MAX(hsn) AS hsn,
                        MAX(mrp) AS mrp,
                        MAX(weight_gms) AS weight_gms,
                        MAX(enabled) AS enabled
                    FROM (
                        SELECT
                            COALESCE(NULLIF(er.payload->>'SKU Code',''), NULLIF(er.payload->>'Product Code',''), NULLIF(er.payload->>'itemTypeSKU','')) AS sku,
                            COALESCE(NULLIF(er.payload->>'Name',''), NULLIF(er.payload->>'Item Name',''), NULLIF(er.payload->>'itemName','')) AS name,
                            COALESCE(NULLIF(er.payload->>'Description',''), NULLIF(er.payload->>'description','')) AS description,
                            COALESCE(NULLIF(er.payload->>'Category Name',''), NULLIF(er.payload->>'Category',''), NULLIF(er.payload->>'categoryName','')) AS category_name,
                            COALESCE(NULLIF(er.payload->>'Category Code',''), NULLIF(er.payload->>'categoryCode','')) AS category_code,
                            COALESCE(NULLIF(er.payload->>'Color',''), NULLIF(er.payload->>'color','')) AS color,
                            COALESCE(NULLIF(er.payload->>'Size',''), NULLIF(er.payload->>'size','')) AS size,
                            COALESCE(NULLIF(er.payload->>'Brand',''), NULLIF(er.payload->>'brand','')) AS brand,
                            COALESCE(NULLIF(er.payload->>'HSN CODE',''), NULLIF(er.payload->>'HSN Code',''), NULLIF(er.payload->>'hsnCode','')) AS hsn,
                            COALESCE(NULLIF(er.payload->>'MRP',''), NULLIF(er.payload->>'mrp',''), NULLIF(er.payload->>'Base Price',''), NULLIF(er.payload->>'basePrice','')) AS mrp,
                            COALESCE(NULLIF(er.payload->>'Weight (gms)',''), NULLIF(er.payload->>'weight','')) AS weight_gms,
                            lower(trim(COALESCE(NULLIF(er.payload->>'Enabled',''), NULLIF(er.payload->>'enabled','')))) AS enabled,
                            upper(trim(COALESCE(NULLIF(er.payload->>'Sku Type',''), NULLIF(er.payload->>'SkuType','')))) AS sku_type,
                            upper(trim(COALESCE(NULLIF(er.payload->>'Type',''), NULLIF(er.payload->>'type','')))) AS itype
                        FROM export_rows er
                        WHERE er.export_job_id = :job_id
                    ) t
                    WHERE t.sku IS NOT NULL
                      AND t.sku <> ''
                      AND lower(trim(t.sku)) NOT IN ('zeroskuu','0','-')
                      AND t.enabled IN ('true','1','yes','y')
                      AND t.sku_type = 'GOODS'
                      AND t.itype = 'SIMPLE'
                      AND (t.mrp IS NOT NULL AND t.mrp <> '' AND (t.mrp)::numeric > 0)
                    GROUP BY sku
                )
                SELECT
                    items.sku,
                    items.name,
                    items.description,
                    regexp_replace(COALESCE(items.category_name,''), '\\s+-\\s+.*$', '') AS category_name,
                    items.category_code,
                    items.color,
                    items.size,
                    items.brand,
                    items.hsn,
                    items.mrp,
                    items.weight_gms,
                    items.enabled
                FROM items
                {stock_join}
                WHERE (:keyword = '' OR (
                    items.sku ILIKE :like
                    OR COALESCE(items.name,'') ILIKE :like
                    OR COALESCE(items.category_name,'') ILIKE :like
                    OR COALESCE(items.brand,'') ILIKE :like
                ))
                AND (:category = '' OR lower(regexp_replace(COALESCE(items.category_name,''), '\\s+-\\s+.*$', '')) = :category)
                {stock_where}
                ORDER BY sku DESC NULLS LAST
                OFFSET :off
                LIMIT :lim
                """
            )
            rows = db.execute(
                page_stmt,
                {
                    "job_id": int(item_master_job.id),
                    "keyword": keyword_norm,
                    "like": like,
                    "category": category_norm,
                    "warehouse": warehouse_norm,
                    "off": safe_start,
                    "lim": safe_length,
                },
            ).mappings().all()

            skus = [self._safe_str(r.get("sku")) for r in rows if self._safe_str(r.get("sku"))]
            inventory_map = {}
            if include_inventory_snapshot or stock_filter_norm in {"in_stock", "out_of_stock"}:
                inventory_map = self._fetch_inventory_snapshot_map_by_sku(skus)

            elements: List[Dict[str, Any]] = []
            for r in rows:
                sku = self._safe_str(r.get("sku"))
                if not sku:
                    continue
                inv_bucket = inventory_map.get(sku) or {}
                inv = int(inv_bucket.get("good_inventory") or 0)
                virt = int(inv_bucket.get("virtual_inventory") or 0)

                enabled_text = self._safe_str(r.get("enabled")).strip().lower()
                enabled = True if enabled_text in {"", "1", "true", "yes", "y"} else enabled_text in {"1", "true", "yes", "y"}

                price = self._safe_float(r.get("mrp"), default=0.0)
                weight = self._safe_float(r.get("weight_gms"), default=0.0)

                entry = {
                    "skuCode": sku,
                    "name": self._safe_str(r.get("name")) or "-",
                    "description": self._safe_str(r.get("description")) or "",
                    "categoryName": self._safe_str(r.get("category_name")) or "Uncategorized",
                    "categoryCode": self._safe_str(r.get("category_code")) or "",
                    "color": self._safe_str(r.get("color")) or "-",
                    "size": self._safe_str(r.get("size")) or "-",
                    "brand": self._safe_str(r.get("brand")) or "-",
                    "price": round(price, 2),
                    "hsnCode": self._safe_str(r.get("hsn")) or "-",
                    "weight": weight,
                    "enabled": enabled,
                    "ean": "-",
                    "scanIdentifier": "",
                    "warehouse": warehouse_norm,
                    "inventorySnapshots": [
                        {
                            "inventory": inv,
                            "goodInventory": inv,
                            "availableInventory": inv,
                            "virtualInventory": virt,
                            "openSale": virt,
                            "badInventory": 0,
                            "inventoryBlocked": 0,
                            "putawayPending": 0,
                        }
                    ],
                }
                if not include_inventory_snapshot:
                    entry.pop("inventorySnapshots", None)
                elements.append(entry)

            return {
                "successful": True,
                "data_source": "archived_item_master_export_rows",
                "fallback_used": False,
                "last_synced_at": item_master_job.completed_at.isoformat() if item_master_job.completed_at else None,
                "totalRecords": total_records,
                "displayStart": safe_start,
                "displayLength": safe_length,
                "elements": elements,
            }
        finally:
            db.close()

    def get_inventory_summary_db(self, warehouse: Optional[str] = None) -> Dict[str, Any]:
        db = self._get_db()
        try:
            warehouse_norm = self._safe_str(warehouse)
            warehouse_norm = warehouse_norm or "anthrilo"

            item_master_job = (
                db.query(ExportJob)
                .filter(
                    ExportJob.export_type == "item_master",
                    ExportJob.status == "completed",
                )
                .order_by(ExportJob.completed_at.desc(), ExportJob.id.desc())
                .first()
            )
            if not item_master_job:
                return {
                    "successful": True,
                    "data_source": "none",
                    "fallback_used": False,
                    "last_synced_at": None,
                    "totalProducts": 0,
                    "totalSKUs": 0,
                    "activeSKUs": 0,
                    "facilitySKUs": 0,
                    "skusWithStock": 0,
                    "skusOutOfStock": 0,
                    "outOfStockPercent": 0,
                    "totalRealInventory": 0,
                    "totalVirtualInventory": 0,
                    "totalStockValue": 0.0,
                    "categories": [],
                }

            inv_table = self._resolve_inventory_snapshot_table_name(db)
            inv_table = inv_table or "inventory_snapshots"

            summary_stmt = text(
                f"""
                WITH items AS (
                    SELECT
                        sku,
                        MAX(regexp_replace(COALESCE(category_name,''), '\\s+-\\s+.*$', '')) AS category_name
                    FROM (
                        SELECT
                            trim(COALESCE(NULLIF(payload->>'SKU Code',''), NULLIF(payload->>'Product Code',''), NULLIF(payload->>'itemTypeSKU',''))) AS sku,
                            COALESCE(NULLIF(payload->>'Category Name',''), NULLIF(payload->>'Category',''), NULLIF(payload->>'categoryName','')) AS category_name,
                            lower(trim(COALESCE(NULLIF(payload->>'Enabled',''), NULLIF(payload->>'enabled','')))) AS enabled,
                            upper(trim(COALESCE(NULLIF(payload->>'Sku Type',''), NULLIF(payload->>'SkuType','')))) AS sku_type,
                            upper(trim(COALESCE(NULLIF(payload->>'Type',''), NULLIF(payload->>'type','')))) AS itype,
                            COALESCE(NULLIF(payload->>'MRP',''), NULLIF(payload->>'mrp',''), NULLIF(payload->>'Base Price',''), NULLIF(payload->>'basePrice','')) AS mrp
                        FROM export_rows
                        WHERE export_job_id = :job_id
                    ) t
                    WHERE t.sku IS NOT NULL
                      AND t.sku <> ''
                      AND lower(t.sku) NOT IN ('zeroskuu','0','-')
                      AND t.enabled IN ('true','1','yes','y')
                      AND t.sku_type = 'GOODS'
                      AND t.itype = 'SIMPLE'
                      AND (t.mrp IS NOT NULL AND t.mrp <> '' AND (t.mrp)::numeric > 0)
                    GROUP BY t.sku
                ),
                inv AS (
                    SELECT sku, SUM(available_qty)::bigint AS inv_qty, SUM(reserved_qty)::bigint AS virt_qty
                    FROM {inv_table}
                    WHERE warehouse = :warehouse
                    GROUP BY sku
                )
                SELECT
                    COUNT(*)::bigint AS total_skus,
                    COUNT(*)::bigint AS enabled_skus,
                    SUM(CASE WHEN COALESCE(inv.inv_qty,0) > 0 THEN 1 ELSE 0 END)::bigint AS in_stock_skus,
                    SUM(COALESCE(inv.inv_qty,0))::bigint AS total_inventory,
                    SUM(COALESCE(inv.virt_qty,0))::bigint AS total_virtual,
                    COUNT(DISTINCT lower(COALESCE(category_name,'Uncategorized')))::bigint AS category_count
                FROM items
                LEFT JOIN inv ON inv.sku = items.sku
                WHERE items.sku IS NOT NULL AND items.sku <> ''
                """
            )
            srow = db.execute(
                summary_stmt,
                {
                    "job_id": int(item_master_job.id),
                    "warehouse": warehouse_norm,
                },
            ).mappings().first() or {}

            cat_stmt = text(
                f"""
                WITH items AS (
                    SELECT
                        sku,
                        MAX(regexp_replace(COALESCE(category_name,''), '\\s+-\\s+.*$', '')) AS category_name
                    FROM (
                        SELECT
                            trim(COALESCE(NULLIF(payload->>'SKU Code',''), NULLIF(payload->>'Product Code',''), NULLIF(payload->>'itemTypeSKU',''))) AS sku,
                            COALESCE(NULLIF(payload->>'Category Name',''), NULLIF(payload->>'Category',''), NULLIF(payload->>'categoryName','')) AS category_name,
                            lower(trim(COALESCE(NULLIF(payload->>'Enabled',''), NULLIF(payload->>'enabled','')))) AS enabled,
                            upper(trim(COALESCE(NULLIF(payload->>'Sku Type',''), NULLIF(payload->>'SkuType','')))) AS sku_type,
                            upper(trim(COALESCE(NULLIF(payload->>'Type',''), NULLIF(payload->>'type','')))) AS itype,
                            COALESCE(NULLIF(payload->>'MRP',''), NULLIF(payload->>'mrp',''), NULLIF(payload->>'Base Price',''), NULLIF(payload->>'basePrice','')) AS mrp
                        FROM export_rows
                        WHERE export_job_id = :job_id
                    ) t
                    WHERE t.sku IS NOT NULL
                      AND t.sku <> ''
                      AND lower(t.sku) NOT IN ('zeroskuu','0','-')
                      AND t.enabled IN ('true','1','yes','y')
                      AND t.sku_type = 'GOODS'
                      AND t.itype = 'SIMPLE'
                      AND (t.mrp IS NOT NULL AND t.mrp <> '' AND (t.mrp)::numeric > 0)
                    GROUP BY t.sku
                ),
                inv AS (
                    SELECT sku, SUM(available_qty)::bigint AS inv_qty
                    FROM {inv_table}
                    WHERE warehouse = :warehouse
                    GROUP BY sku
                )
                SELECT
                    COALESCE(NULLIF(items.category_name,''), 'Uncategorized') AS category,
                    COUNT(*)::bigint AS skus,
                    SUM(COALESCE(inv.inv_qty,0))::bigint AS inventory,
                    SUM(CASE WHEN COALESCE(inv.inv_qty,0) > 0 THEN 1 ELSE 0 END)::bigint AS in_stock
                FROM items
                LEFT JOIN inv ON inv.sku = items.sku
                WHERE items.sku IS NOT NULL AND items.sku <> ''
                GROUP BY 1
                ORDER BY inventory DESC
                """
            )
            cat_rows = db.execute(
                cat_stmt,
                {
                    "job_id": int(item_master_job.id),
                    "warehouse": warehouse_norm,
                },
            ).mappings().all()

            categories = [
                {
                    "name": self._safe_str(r.get("category")) or "Uncategorized",
                    "skus": int(r.get("skus") or 0),
                    "inventory": int(r.get("inventory") or 0),
                    "inStock": int(r.get("in_stock") or 0),
                    "outOfStock": int((r.get("skus") or 0) - (r.get("in_stock") or 0)),
                }
                for r in cat_rows
            ]

            total_skus = int(srow.get("total_skus") or 0)
            enabled_count = int(srow.get("enabled_skus") or 0)
            in_stock = int(srow.get("in_stock_skus") or 0)
            out_of_stock = total_skus - in_stock
            total_inventory = int(srow.get("total_inventory") or 0)
            total_virtual = int(srow.get("total_virtual") or 0)
            total_value = 0.0
            last_synced = item_master_job.completed_at

            return {
                "successful": True,
                "data_source": "archived_item_master_export_rows",
                "fallback_used": False,
                "last_synced_at": last_synced.isoformat() if last_synced else None,
                "totalProducts": total_skus,
                "totalSKUs": total_skus,
                "activeSKUs": enabled_count,
                "facilitySKUs": int(srow.get("in_stock_skus") or 0),
                "skusWithStock": in_stock,
                "skusOutOfStock": out_of_stock,
                "outOfStockPercent": round((out_of_stock / total_skus) * 100) if total_skus else 0,
                "totalRealInventory": total_inventory,
                "totalVirtualInventory": total_virtual,
                "totalStockValue": round(total_value, 2),
                "categories": categories,
            }
        finally:
            db.close()


_data_service_instance: Optional[UnicommerceDataService] = None


def get_unicommerce_data_service() -> UnicommerceDataService:
    global _data_service_instance
    if _data_service_instance is None:
        _data_service_instance = UnicommerceDataService()
    return _data_service_instance
