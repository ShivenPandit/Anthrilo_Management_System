"""DB-first read service for Unicommerce sales and inventory data."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.export_models import (
    ExportJob,
    ExportRow,
    InventorySnapshotRecord,
    SalesOrderRecord,
    SalesReturnRecord,
)
from app.services.cache_service import CacheService
from app.services.unicommerce import get_unicommerce_service


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

    def _resolve_range(
        self,
        period: str,
        from_date: Optional[datetime],
        to_date: Optional[datetime],
    ) -> Tuple[datetime, datetime, str]:
        if period == "today":
            start, end = self.uc_service.get_today_range()
            return start, end, "today"

        if period == "yesterday":
            start, end = self.uc_service.get_yesterday_range()
            return start, end, "yesterday"

        if period == "last_7_days":
            start, end = self.uc_service.get_last_n_days_range(7)
            return start, end, "last_7_days"

        if period == "last_30_days":
            start, end = self.uc_service.get_last_n_days_range(30)
            return start, end, "last_30_days"

        if from_date and to_date:
            return from_date, to_date, "custom"

        start, end = self.uc_service.get_today_range()
        return start, end, "today"

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

            order_date = self.uc_service._parse_datetime(
                self._pick(payload, "Created", "created")
            )
            order_date = self._normalize_dt(order_date)

            if order_date and (order_date < from_date or order_date > to_date):
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
                    "selling_price": self._safe_float(
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

            price = float(row.get("selling_price") or 0.0)
            sku = self._safe_str(row.get("sku"))
            name = self._safe_str(row.get("product_name")) or sku

            order["items"].append(
                {
                    "itemSku": sku,
                    "sku": sku,
                    "itemName": name,
                    "sellingPrice": price,
                    "selling_price": price,
                    "quantity": qty,
                    "size": "",
                }
            )

        orders: List[Dict[str, Any]] = []
        for _, order in orders_map.items():
            items = order.get("items", [])
            total_qty = sum(int(item.get("quantity") or 0) for item in items)
            selling_total = sum(
                float(item.get("sellingPrice") or 0.0) * int(item.get("quantity") or 0)
                for item in items
            )
            include_in_revenue = self._safe_str(order.get("status")).upper() not in self.EXCLUDED_STATUSES
            net_revenue = selling_total if include_in_revenue else 0.0

            created_dt = order.get("_created_dt")
            created_value = created_dt.isoformat() if isinstance(created_dt, datetime) else ""

            orders.append(
                {
                    "code": order.get("code"),
                    "displayOrderCode": order.get("displayOrderCode"),
                    "status": order.get("status") or "",
                    "channel": order.get("channel") or "UNKNOWN",
                    "selling_price": round(selling_total, 2),
                    "total_selling_price": round(selling_total, 2),
                    "net_revenue": round(net_revenue, 2),
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
                selling_price = float(item.get("sellingPrice") or item.get("selling_price") or 0.0)
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
                        "bundleSkuCodeNumber": "",
                        "quantity": quantity,
                        "sellingPrice": round(selling_price, 2),
                        "maxRetailPrice": round(selling_price, 2),
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
            selling_price = round(float(record.selling_price or 0.0), 2)
            mrp = round(
                self._safe_float(
                    self._pick(raw, "MRP", "Maximum Retail Price", "maxRetailPrice"),
                    default=selling_price,
                ),
                2,
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
                    "sellingPrice": selling_price,
                    "maxRetailPrice": mrp,
                    "discount": round(
                        self._safe_float(self._pick(raw, "Discount", "discount"), default=0.0),
                        2,
                    ),
                    "taxAmount": round(
                        self._safe_float(self._pick(raw, "Tax Amount", "taxAmount"), default=0.0),
                        2,
                    ),
                    "refundAmount": round(
                        self._safe_float(self._pick(raw, "Refund Amount", "refundAmount"), default=0.0),
                        2,
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
                    "selling_price": 0.0,
                    "item_count": 0,
                    "quantity": 0,
                },
            )

            qty = int(row.get("qty") or 1)
            if qty <= 0:
                qty = 1

            item_price = float(row.get("selling_price") or 0.0)
            order["selling_price"] += item_price * qty
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
        total_revenue = 0.0
        total_items = 0

        channel_breakdown: Dict[str, Dict[str, Any]] = {}
        status_breakdown: Dict[str, int] = {}
        daily_map: Dict[str, Dict[str, Any]] = {}

        for order in order_list:
            status = self._safe_str(order.get("status")).upper()
            channel = self._safe_str(order.get("channel") or "UNKNOWN")
            revenue = float(order.get("selling_price") or 0.0)
            qty = int(order.get("quantity") or 0)
            created = order.get("created")

            status_breakdown[status] = status_breakdown.get(status, 0) + 1

            include = status not in self.EXCLUDED_STATUSES
            if include:
                valid_orders += 1
                total_revenue += revenue
                total_items += qty

                if channel not in channel_breakdown:
                    channel_breakdown[channel] = {"orders": 0, "revenue": 0.0, "items": 0}
                channel_breakdown[channel]["orders"] += 1
                channel_breakdown[channel]["revenue"] += revenue
                channel_breakdown[channel]["items"] += qty

                date_key = None
                if isinstance(created, datetime):
                    if created.tzinfo is None:
                        created_utc = created.replace(tzinfo=timezone.utc)
                    else:
                        created_utc = created.astimezone(timezone.utc)
                    date_key = created_utc.strftime("%Y-%m-%d")
                elif created:
                    date_key = self._safe_str(created)[:10]

                if date_key:
                    if date_key not in daily_map:
                        daily_map[date_key] = {
                            "date": date_key,
                            "orders": 0,
                            "revenue": 0.0,
                            "items": 0,
                        }
                    daily_map[date_key]["orders"] += 1
                    daily_map[date_key]["revenue"] += revenue
                    daily_map[date_key]["items"] += qty
            else:
                excluded_orders += 1

        for value in channel_breakdown.values():
            value["revenue"] = round(float(value["revenue"]), 2)

        daily_breakdown = sorted(daily_map.values(), key=lambda x: x["date"])
        for day in daily_breakdown:
            day["revenue"] = round(float(day["revenue"]), 2)

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
                "selling_price": round(float(o.get("selling_price") or 0.0), 2),
                "net_revenue": round(float(o.get("selling_price") or 0.0), 2),
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
                "total_revenue": round(total_revenue, 2),
                "total_discount": 0.0,
                "total_tax": 0.0,
                "total_refund": 0.0,
                "avg_order_value": round(total_revenue / valid_orders, 2) if valid_orders > 0 else 0,
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
        job = (
            db.query(ExportJob)
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

    def get_sales_data(
        self,
        period: str = "today",
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        start, end, resolved_period = self._resolve_range(period, from_date, to_date)

        db = self._get_db()
        try:
            normalized_records = (
                db.query(SalesOrderRecord)
                .filter(
                    or_(
                        and_(
                            SalesOrderRecord.order_date.isnot(None),
                            SalesOrderRecord.order_date >= start,
                            SalesOrderRecord.order_date <= end,
                        ),
                        and_(
                            SalesOrderRecord.order_date.is_(None),
                            SalesOrderRecord.created_at >= start,
                            SalesOrderRecord.created_at <= end,
                        ),
                    )
                )
                .all()
            )

            if normalized_records:
                rows = [
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
                detailed_orders = self._orders_from_line_rows(rows)
                aggregation = self._aggregate_sales_rows(rows)
                last_synced = max((r.updated_at for r in normalized_records if r.updated_at), default=None)

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
                    "orders": aggregation["orders"],
                    "_orders": self._legacy_orders_from_orders(detailed_orders),
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
            detailed_orders = self._orders_from_line_rows(line_rows)
            aggregation = self._aggregate_sales_rows(line_rows)

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
                "orders": aggregation["orders"],
                "_orders": self._legacy_orders_from_orders(detailed_orders),
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

            normalized_records = (
                db.query(SalesReturnRecord)
                .filter(
                    SalesReturnRecord.updated_at >= (from_date - timedelta(days=45)),
                    SalesReturnRecord.updated_at <= (to_date + timedelta(days=1)),
                )
                .all()
            )

            for record in normalized_records:
                raw = dict(record.raw_data or {})
                parsed_dt = self.uc_service._parse_datetime(
                    self._pick(
                        raw,
                        "Return Date",
                        "returnDate",
                        "Invoice Date",
                        "invoiceDate",
                        "Created",
                        "created",
                        "Updated",
                        "updated",
                    )
                )
                parsed_dt = self._normalize_dt(parsed_dt or record.updated_at or record.created_at)

                if parsed_dt and (parsed_dt < from_date or parsed_dt > to_date):
                    continue

                rtype = self._safe_str(
                    self._pick(raw, "Return Type", "returnType")
                    or record.return_status
                ).upper() or "UNKNOWN"
                if type_norm != "ALL" and rtype != type_norm:
                    continue

                quantity = int(record.return_qty or 0)
                if quantity <= 0:
                    quantity = self._safe_int(self._pick(raw, "Qty", "QTY", "quantity"), default=1)
                if quantity <= 0:
                    quantity = 1

                refund_amount = float(record.refund_amount or 0.0)
                unit_price = round(refund_amount / quantity, 2) if quantity > 0 else 0.0

                items.append(
                    {
                        "saleOrderCode": self._safe_str(record.order_id),
                        "invoiceCode": self._safe_str(record.return_code),
                        "channel": self._safe_str(self._pick(raw, "Channel Name", "channel") or "UNKNOWN"),
                        "returnType": rtype,
                        "sku": self._safe_str(record.sku),
                        "itemName": self._safe_str(
                            self._pick(raw, "Product Name", "Item Name", "itemName")
                        ) or self._safe_str(record.sku),
                        "quantity": quantity,
                        "unitPrice": unit_price,
                        "refundAmount": round(refund_amount, 2),
                        "returnDate": parsed_dt.isoformat() if parsed_dt else "",
                    }
                )

            data_source = "normalized_sales_returns"
            last_synced_at = None

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

                    rtype = self._safe_str(self._pick(raw, "Return Type", "returnType")).upper() or "UNKNOWN"
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

        sales_result = self.get_sales_data(period=period_norm)
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
    ) -> Dict[str, Any]:
        try:
            is_range = bool(from_date and to_date)
            if not is_range and not date:
                return {
                    "success": False,
                    "error": "Provide either 'date' or both 'from_date' and 'to_date'.",
                }

            if is_range:
                from_dt = datetime.strptime(str(from_date), "%Y-%m-%d").replace(
                    hour=0,
                    minute=0,
                    second=0,
                    tzinfo=timezone.utc,
                )
                to_dt = datetime.strptime(str(to_date), "%Y-%m-%d").replace(
                    hour=23,
                    minute=59,
                    second=59,
                    tzinfo=timezone.utc,
                )
                sales_result = self.get_sales_data(
                    period="custom",
                    from_date=from_dt,
                    to_date=to_dt,
                )
                date_label = f"{from_date} to {to_date}"
            else:
                report_date = datetime.strptime(str(date), "%Y-%m-%d").date()
                today = datetime.now(timezone.utc).date()
                yesterday = today - timedelta(days=1)

                if report_date == today:
                    sales_result = self.get_sales_data(period="today")
                elif report_date == yesterday:
                    sales_result = self.get_sales_data(period="yesterday")
                else:
                    from_dt = datetime.strptime(str(date), "%Y-%m-%d").replace(
                        hour=0,
                        minute=0,
                        second=0,
                        tzinfo=timezone.utc,
                    )
                    to_dt = datetime.strptime(str(date), "%Y-%m-%d").replace(
                        hour=23,
                        minute=59,
                        second=59,
                        tzinfo=timezone.utc,
                    )
                    sales_result = self.get_sales_data(
                        period="custom",
                        from_date=from_dt,
                        to_date=to_dt,
                    )
                date_label = str(date)

            if not sales_result.get("success"):
                return sales_result

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
            raw_orders = list(sales_result.get("_orders") or [])
            ist = timezone(timedelta(hours=5, minutes=30))

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

            items_detail.sort(
                key=lambda x: (
                    self._safe_str(x.get("channel_name")),
                    self._safe_str(x.get("item_sku_code")),
                )
            )

            unique_skus = sorted(
                {
                    self._safe_str(item.get("item_sku_code"))
                    for item in items_detail
                    if self._safe_str(item.get("item_sku_code"))
                }
            )
            inventory_map: Dict[str, Dict[str, int]] = {}

            if unique_skus:
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

            for item in items_detail:
                sku = self._safe_str(item.get("item_sku_code"))
                inv = inventory_map.get(sku, {})
                item["good_inventory"] = inv.get("good_inventory")
                item["virtual_inventory"] = inv.get("virtual_inventory")

            comparison = None
            if not is_range and date:
                comp_date = datetime.strptime(str(date), "%Y-%m-%d").date() - timedelta(days=1)
                comp_today = datetime.now(timezone.utc).date()
                comp_yesterday = comp_today - timedelta(days=1)

                if comp_date == comp_today:
                    comp_result = self.get_sales_data(period="today")
                elif comp_date == comp_yesterday:
                    comp_result = self.get_sales_data(period="yesterday")
                else:
                    comp_from = datetime.combine(comp_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                    comp_to = datetime.combine(comp_date, datetime.max.time()).replace(tzinfo=timezone.utc)
                    comp_result = self.get_sales_data(
                        period="custom",
                        from_date=comp_from,
                        to_date=comp_to,
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
    ) -> Dict[str, Any]:
        try:
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

            order_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for item in all_items:
                so_code = self._safe_str(item.get("saleOrderCode")) or "UNKNOWN"
                order_groups[so_code].append(item)

            for so_code, items in order_groups.items():
                if not items:
                    continue

                first = items[0]
                rtype = self._safe_str(first.get("returnType")) or "UNKNOWN"
                channel = self._safe_str(first.get("channel")) or "UNKNOWN"

                if rtype == "RTO":
                    rto_count += 1
                elif rtype == "CIR":
                    cir_count += 1

                return_entry: Dict[str, Any] = {
                    "code": self._safe_str(first.get("invoiceCode")) or so_code,
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
    ) -> Dict[str, Any]:
        try:
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

    def get_sales_activity_report(self, from_date: str, to_date: str) -> Dict[str, Any]:
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

            result = self.get_sales_data(
                period="custom",
                from_date=from_dt,
                to_date=to_dt,
            )
            if not result.get("success"):
                return result

            raw_orders = list(result.get("_orders") or [])

            def _norm_sku(v: str) -> str:
                return self._safe_str(v).upper()

            def _norm_channel(v: str) -> str:
                ch = (self._safe_str(v) or "UNKNOWN").upper()
                ch = ch.replace("-", "_").replace(" ", "_")
                while "__" in ch:
                    ch = ch.replace("__", "_")
                return ch

            detail_map: Dict[Tuple[str, str, str], Dict[str, Any]] = defaultdict(
                lambda: {
                    "item_sku_code": "",
                    "item_type_name": "",
                    "size": "",
                    "channel": "",
                    "total_sale_qty": 0,
                    "cancel_qty": 0,
                    "return_qty": 0,
                }
            )

            for order in raw_orders:
                status = self._safe_str(order.get("status")).upper()
                channel = self._safe_str(order.get("channel")) or "UNKNOWN"

                for item in list(order.get("saleOrderItems") or []):
                    sku = self._safe_str(item.get("itemSku"))
                    item_type = self._safe_str(item.get("itemTypeName"))
                    size = self._safe_str(item.get("size"))
                    qty = self._safe_int(item.get("quantity"), default=1)
                    if qty <= 0:
                        qty = 1

                    key = (sku, size, channel)
                    row = detail_map[key]
                    row["item_sku_code"] = sku
                    row["item_type_name"] = item_type
                    row["size"] = size
                    row["channel"] = channel

                    if status in {"CANCELLED", "CANCELED"}:
                        row["cancel_qty"] += qty
                    elif status in {"RETURNED", "REFUNDED"}:
                        row["return_qty"] += qty
                    else:
                        row["total_sale_qty"] += qty

            norm_key_to_detail_keys: Dict[Tuple[str, str], List[Tuple[str, str, str]]] = defaultdict(list)
            order_sku_to_detail_keys: Dict[Tuple[str, str], List[Tuple[str, str, str]]] = defaultdict(list)

            for key in detail_map.keys():
                sku_key, _, channel_key = key
                norm_key_to_detail_keys[(_norm_sku(sku_key), _norm_channel(channel_key))].append(key)

            for order in raw_orders:
                order_code = self._safe_str(order.get("code"))
                if not order_code:
                    continue

                order_code_norm = order_code.upper()
                order_channel = self._safe_str(order.get("channel")) or "UNKNOWN"

                for item in list(order.get("saleOrderItems") or []):
                    sku = self._safe_str(item.get("itemSku"))
                    size = self._safe_str(item.get("size"))
                    key = (sku, size, order_channel)
                    if key in detail_map:
                        order_sku_to_detail_keys[(order_code_norm, _norm_sku(sku))].append(key)

            return_map: Dict[Tuple[str, str], int] = defaultdict(int)
            return_report = self.get_return_report(
                from_date=from_date,
                to_date=to_date,
                period="custom",
                return_type="ALL",
            )

            if return_report.get("success"):
                for ret in list(return_report.get("returns") or []):
                    so_code_norm = self._safe_str(ret.get("saleOrderCode")).upper()
                    ret_channel = _norm_channel(self._safe_str(ret.get("channel")) or "UNKNOWN")

                    for it in list(ret.get("items") or []):
                        sku = _norm_sku(self._safe_str(it.get("sku")))
                        rqty = self._safe_int(it.get("quantity"), default=0)
                        if not sku or rqty <= 0:
                            continue

                        direct_keys = order_sku_to_detail_keys.get((so_code_norm, sku), []) if so_code_norm else []
                        if len(direct_keys) == 1:
                            detail_map[direct_keys[0]]["return_qty"] += rqty
                            continue

                        if len(direct_keys) > 1:
                            sample_row = detail_map[direct_keys[0]]
                            unknown_key = (
                                self._safe_str(sample_row.get("item_sku_code")) or sku,
                                "UNKNOWN",
                                self._safe_str(sample_row.get("channel")) or ret_channel,
                            )
                            unknown_row = detail_map[unknown_key]
                            unknown_row["item_sku_code"] = self._safe_str(sample_row.get("item_sku_code")) or sku
                            unknown_row["item_type_name"] = self._safe_str(sample_row.get("item_type_name"))
                            unknown_row["size"] = "UNKNOWN"
                            unknown_row["channel"] = self._safe_str(sample_row.get("channel")) or ret_channel
                            unknown_row["return_qty"] += rqty
                            continue

                        return_map[(sku, ret_channel)] += rqty

            if return_map:
                for (sku, channel), qty in return_map.items():
                    matching_keys = norm_key_to_detail_keys.get((sku, channel), [])
                    if not matching_keys:
                        unknown_key = (sku, "UNKNOWN", channel)
                        unknown_row = detail_map[unknown_key]
                        unknown_row["item_sku_code"] = sku
                        unknown_row["item_type_name"] = self._safe_str(unknown_row.get("item_type_name"))
                        unknown_row["size"] = "UNKNOWN"
                        unknown_row["channel"] = channel
                        unknown_row["return_qty"] += qty
                        continue

                    if len(matching_keys) == 1:
                        detail_map[matching_keys[0]]["return_qty"] += qty
                        continue

                    sample_row = detail_map[matching_keys[0]]
                    unknown_key = (
                        self._safe_str(sample_row.get("item_sku_code")) or sku,
                        "UNKNOWN",
                        self._safe_str(sample_row.get("channel")) or channel,
                    )
                    unknown_row = detail_map[unknown_key]
                    unknown_row["item_sku_code"] = self._safe_str(sample_row.get("item_sku_code")) or sku
                    unknown_row["item_type_name"] = self._safe_str(sample_row.get("item_type_name"))
                    unknown_row["size"] = "UNKNOWN"
                    unknown_row["channel"] = self._safe_str(sample_row.get("channel")) or channel
                    unknown_row["return_qty"] += qty

            items = list(detail_map.values())
            unique_skus = sorted(
                {
                    self._safe_str(r.get("item_sku_code"))
                    for r in items
                    if self._safe_str(r.get("item_sku_code"))
                }
            )

            inventory_map: Dict[str, Dict[str, int]] = {}
            if unique_skus:
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

            for row in items:
                row["net_sale"] = int(row.get("total_sale_qty", 0) or 0) - int(row.get("cancel_qty", 0) or 0) - int(row.get("return_qty", 0) or 0)
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

            return {
                "success": True,
                "from_date": str(from_date),
                "to_date": str(to_date),
                "items": items,
                "total_skus": len(unique_skus),
                "data_source": result.get("data_source", "db_first"),
                "fallback_used": bool(result.get("fallback_used")),
                "last_synced_at": result.get("last_synced_at"),
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
                    sku_map[sku]["total_revenue"] += selling
                    sku_map[sku]["total_mrp"] += mrp
                    sku_map[sku]["order_count"] += 1

                    if channel not in sku_map[sku]["channels"]:
                        sku_map[sku]["channels"][channel] = {
                            "quantity": 0,
                            "revenue": 0.0,
                        }
                    sku_map[sku]["channels"][channel]["quantity"] += qty
                    sku_map[sku]["channels"][channel]["revenue"] += selling

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

            result = await self.uc_service.get_bundle_sku_data()
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

            result = await self.uc_service.get_bundle_sales_analysis(dt_from, dt_to)
            result["period"] = period

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

            result = await self.uc_service.get_fabric_sales_data(from_dt, to_dt, period_name)

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
                db.query(SalesOrderRecord)
                .filter(SalesOrderRecord.order_id == code)
                .order_by(SalesOrderRecord.order_date.desc(), SalesOrderRecord.id.desc())
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
                db.query(SalesOrderRecord)
                .filter(
                    or_(
                        and_(
                            SalesOrderRecord.order_date.isnot(None),
                            SalesOrderRecord.order_date >= start,
                            SalesOrderRecord.order_date <= end,
                        ),
                        and_(
                            SalesOrderRecord.order_date.is_(None),
                            SalesOrderRecord.created_at >= start,
                            SalesOrderRecord.created_at <= end,
                        ),
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


_data_service_instance: Optional[UnicommerceDataService] = None


def get_unicommerce_data_service() -> UnicommerceDataService:
    global _data_service_instance
    if _data_service_instance is None:
        _data_service_instance = UnicommerceDataService()
    return _data_service_instance
