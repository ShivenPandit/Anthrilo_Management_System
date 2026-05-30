import csv
import io
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case
from app.db.models import (
    Fabric, Yarn, Garment, Inventory, Sale,
    ProductionPlan, ProductionActivity, Panel, ProductionPlanningReport
)
from app.db.export_models import InventorySnapshotRecord, SalesOrderRecord, ShopifyMasterData, SalesReturnRecord, FacilityInventorySnapshot


EXCLUDED_ORDER_STATUSES = {
    "CANCELLED",
    "CANCELED",
    "RETURNED",
    "REFUNDED",
    "FAILED",
    "UNFULFILLABLE",
    "ERROR",
    "PENDING_VERIFICATION",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


class ReportsService:
    """Service for generating all business reports"""

    def __init__(self, db: Session):
        self.db = db


    def raw_materials_stock_analysis(self, category: Optional[str] = None) -> list:
        """Combined raw materials stock analysis for yarn + fabric"""
        items = []

        if not category or category.lower() == 'yarn':
            yarns = self.db.query(Yarn).all()
            for y in yarns:
                stock_qty = float(y.stock_quantity or 0)
                unit_price = float(y.unit_price or 0)
                value = stock_qty * unit_price
                status = 'Low' if stock_qty < 50 else (
                    'High' if stock_qty > 500 else 'Normal')
                items.append({
                    "item_name": f"{y.yarn_type} ({y.yarn_count})",
                    "category": "Yarn",
                    "quantity": stock_qty,
                    "unit": y.unit or "kg",
                    "value": value,
                    "stock_status": status,
                })

        if not category or category.lower() == 'fabric':
            fabrics = self.db.query(Fabric).all()
            for f in fabrics:
                stock_qty = float(f.stock_quantity or 0)
                cpu = float(f.cost_per_unit or 0)
                value = stock_qty * cpu
                status = 'Low' if stock_qty < 50 else (
                    'High' if stock_qty > 500 else 'Normal')
                items.append({
                    "item_name": f"{f.fabric_type} - {f.subtype} ({f.gsm} GSM)",
                    "category": "Fabric",
                    "quantity": stock_qty,
                    "unit": f.unit or "kg",
                    "value": value,
                    "stock_status": status,
                })

        return items

    def yarn_forecasting_report(self, forecast_days: int = 30) -> list:
        """Yarn demand forecasting based on production plans and historical data"""

        yarns = self.db.query(Yarn).all()
        result = []

        for y in yarns:
            stock_qty = float(y.stock_quantity or 0)

            # Estimate daily consumption from production plans that need yarn
            # Use recent production plans' yarn_requirement as a proxy
            recent_plans = self.db.query(ProductionPlan).filter(
                ProductionPlan.status.in_(["PLANNED", "IN_PROGRESS"]),
                ProductionPlan.yarn_requirement != None,
                ProductionPlan.yarn_requirement > 0
            ).all()

            # Sum total yarn requirement across active plans, average over their target days
            total_yarn_req = sum(float(p.yarn_requirement or 0)
                                 for p in recent_plans)
            if recent_plans:
                avg_days_to_target = max(1, sum(
                    max(1, (p.target_date - date.today()).days) for p in recent_plans
                ) / len(recent_plans))
                avg_daily = total_yarn_req / avg_days_to_target / \
                    max(1, self.db.query(Yarn).count())
            else:
                # Fallback: estimate from stock level (assume 1% daily consumption)
                avg_daily = stock_qty * 0.01 if stock_qty > 0 else 0

            forecasted_demand = avg_daily * forecast_days
            days_to_stockout = stock_qty / avg_daily if avg_daily > 0 else 999
            recommended = max(0, forecasted_demand - stock_qty +
                              (avg_daily * 14))  # 14 days safety

            result.append({
                "yarn_type": f"{y.yarn_type} ({y.yarn_count})",
                "current_stock": stock_qty,
                "avg_daily_consumption": round(avg_daily, 2),
                "forecasted_demand": round(forecasted_demand, 2),
                "days_until_stockout": round(days_to_stockout, 1),
                "recommended_order": round(recommended, 2),
            })

        return result


    def fabric_stock_sheet_total(self) -> Dict[str, Any]:
        """Generate total fabric stock sheet across all types"""
        fabrics = self.db.query(Fabric).all()

        total_stock = sum(float(f.stock_quantity) for f in fabrics)
        total_value = sum(
            float(f.stock_quantity * (f.cost_per_unit or 0))
            for f in fabrics
        )

        fabric_data = [
            {
                "id": f.id,
                "fabric_type": f.fabric_type,
                "subtype": f.subtype,
                "gsm": f.gsm,
                "composition": f.composition,
                "color": f.color,
                "stock_quantity": float(f.stock_quantity),
                "unit": f.unit,
                "cost_per_unit": float(f.cost_per_unit) if f.cost_per_unit else 0,
                "stock_value": float(f.stock_quantity * (f.cost_per_unit or 0))
            }
            for f in fabrics
        ]

        return {
            "report_type": "Fabric Stock Sheet - Total",
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_fabric_types": len(fabrics),
                "total_stock_quantity": total_stock,
                "total_stock_value": total_value,
                "unit": "kg"
            },
            "fabrics": fabric_data
        }

    def fabric_stock_sheet_by_type(self, fabric_type: str) -> Dict[str, Any]:
        """Generate fabric stock sheet filtered by fabric type"""
        fabrics = self.db.query(Fabric).filter(
            Fabric.fabric_type == fabric_type
        ).all()

        total_stock = sum(float(f.stock_quantity) for f in fabrics)
        total_value = sum(
            float(f.stock_quantity * (f.cost_per_unit or 0))
            for f in fabrics
        )

        fabric_data = [
            {
                "id": f.id,
                "subtype": f.subtype,
                "gsm": f.gsm,
                "composition": f.composition,
                "color": f.color,
                "width": float(f.width) if f.width else None,
                "stock_quantity": float(f.stock_quantity),
                "unit": f.unit,
                "cost_per_unit": float(f.cost_per_unit) if f.cost_per_unit else 0,
                "stock_value": float(f.stock_quantity * (f.cost_per_unit or 0))
            }
            for f in fabrics
        ]

        return {
            "report_type": f"Fabric Stock Sheet - {fabric_type}",
            "fabric_type": fabric_type,
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_subtypes": len(fabrics),
                "total_stock_quantity": total_stock,
                "total_stock_value": total_value,
                "unit": "kg"
            },
            "fabrics": fabric_data
        }

    def fabric_stock_sheet_by_period(
        self,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        Generate fabric stock sheet for a specific time period.
        Shows stock added/updated within the period.
        """
        fabrics = self.db.query(Fabric).filter(
            and_(
                Fabric.updated_at >= start_date,
                Fabric.updated_at <= end_date
            )
        ).all()

        total_stock = sum(float(f.stock_quantity) for f in fabrics)
        total_value = sum(
            float(f.stock_quantity * (f.cost_per_unit or 0))
            for f in fabrics
        )

        fabric_data = [
            {
                "id": f.id,
                "fabric_type": f.fabric_type,
                "subtype": f.subtype,
                "gsm": f.gsm,
                "stock_quantity": float(f.stock_quantity),
                "cost_per_unit": float(f.cost_per_unit) if f.cost_per_unit else 0,
                "stock_value": float(f.stock_quantity * (f.cost_per_unit or 0)),
                "updated_at": f.updated_at.isoformat()
            }
            for f in fabrics
        ]

        return {
            "report_type": "Fabric Stock Sheet - Time Period",
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "fabrics_updated": len(fabrics),
                "total_stock_quantity": total_stock,
                "total_stock_value": total_value
            },
            "fabrics": fabric_data
        }

    def fabric_cost_sheet(self) -> Dict[str, Any]:
        """Generate fabric cost sheet with cost breakdown"""
        fabrics = self.db.query(Fabric).all()

        cost_data = []
        for f in fabrics:
            stock_qty = float(f.stock_quantity)
            cost_per_unit = float(f.cost_per_unit) if f.cost_per_unit else 0
            total_value = stock_qty * cost_per_unit

            cost_data.append({
                "fabric_type": f.fabric_type,
                "subtype": f.subtype,
                "gsm": f.gsm,
                "stock_quantity": stock_qty,
                "unit": f.unit,
                "cost_per_unit": cost_per_unit,
                "total_value": total_value
            })

        # Group by fabric type
        type_summary = {}
        for item in cost_data:
            ftype = item["fabric_type"]
            if ftype not in type_summary:
                type_summary[ftype] = {
                    "total_quantity": 0,
                    "total_value": 0,
                    "count": 0
                }
            type_summary[ftype]["total_quantity"] += item["stock_quantity"]
            type_summary[ftype]["total_value"] += item["total_value"]
            type_summary[ftype]["count"] += 1

        return {
            "report_type": "Fabric Cost Sheet",
            "generated_at": datetime.utcnow().isoformat(),
            "summary_by_type": type_summary,
            "total_stock_value": sum(item["total_value"] for item in cost_data),
            "detailed_costs": cost_data
        }


    def _collect_garment_planning_rows(
        self,
        start_date: date,
        end_date: date,
        season: str = "both",
        type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Collect full garment planning rows for ALL Shopify SKUs from master data."""

        if end_date < start_date:
            start_date, end_date = end_date, start_date

        season_filter = (season or "both").strip().lower()
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        days_count = max((end_date - start_date).days + 1, 1)

        # Query ALL SKUs from master data WITHOUT filtering by season or bundle type
        # This ensures every SKU in the master catalog is included in the report
        masters_query = self.db.query(ShopifyMasterData).order_by(
            ShopifyMasterData.variant_sku.asc(),
        )

        # Include only SIMPLE SKUs; skip BUNDLE or other values.
        masters_query = masters_query.filter(
            func.upper(func.coalesce(ShopifyMasterData.simple_bundle, "")) == "SIMPLE"
        )

        # Apply type filter if provided (comma-separated list of types)
        if type_filter:
            type_list = [t.strip() for t in type_filter.split(",") if t.strip()]
            if type_list:
                masters_query = masters_query.filter(ShopifyMasterData.type.in_(type_list))

        masters = masters_query.all()

        sku_values = [
            (row.variant_sku or "").strip()
            for row in masters
            if (row.variant_sku or "").strip()
        ]
        unique_sku_values = list(dict.fromkeys(sku_values))

        sales_map: Dict[str, Dict[str, Any]] = {}
        if unique_sku_values:
            sales_rows = (
                self.db.query(
                    SalesOrderRecord.sku.label("sku"),
                    func.sum(SalesOrderRecord.qty).label("net_sales"),
                    func.max(SalesOrderRecord.item_type_size).label("size"),
                )
                .filter(
                    SalesOrderRecord.sku.isnot(None),
                    SalesOrderRecord.sku != "",
                    or_(
                        SalesOrderRecord.status.is_(None),
                        SalesOrderRecord.status.notin_(EXCLUDED_ORDER_STATUSES),
                    ),
                    or_(
                        SalesOrderRecord.sale_order_item_status.is_(None),
                        func.upper(SalesOrderRecord.sale_order_item_status).notin_(EXCLUDED_ORDER_STATUSES),
                    ),
                    SalesOrderRecord.order_date >= start_dt,
                    SalesOrderRecord.order_date < end_dt,
                    SalesOrderRecord.sku.in_(unique_sku_values),
                )
                .group_by(SalesOrderRecord.sku)
                .all()
            )
            sales_map = {
                (row.sku or "").strip().upper(): {
                    "net_sales": int(row.net_sales or 0),
                    "size": row.size,
                }
                for row in sales_rows
                if row.sku
            }

        # NOTE: Returns are NOT subtracted separately here because the
        # sales_orders query above already excludes RETURNED / CANCELLED items
        # via EXCLUDED_ORDER_STATUSES.  Previously, returns from the
        # sales_returns table were also subtracted, which caused
        # double-counting and under-reported Net Sale values.

        # Good Inventory: use facility_inventory_snapshot (Unicommerce sync
        # target) instead of the legacy inventory_snapshots table.
        inventory_rows = (
            self.db.query(
                FacilityInventorySnapshot.sku.label("sku"),
                func.coalesce(func.sum(FacilityInventorySnapshot.inventory), 0).label("good_inventory"),
            )
            .filter(
                FacilityInventorySnapshot.sku.isnot(None),
                FacilityInventorySnapshot.sku != "",
            )
            .group_by(FacilityInventorySnapshot.sku)
            .all()
        )
        inventory_map: Dict[str, int] = {
            (row.sku or "").strip().upper(): int(row.good_inventory or 0)
            for row in inventory_rows
            if row.sku
        }

        items: List[Dict[str, Any]] = []

        for master in masters:
            sku = (master.variant_sku or "").strip()
            if not sku:
                continue

            sku_key = sku.upper()
            sales_row = sales_map.get(sku_key, {})
            net_sales = int(sales_row.get("net_sales") or 0)
            good_inventory = int(inventory_map.get(sku_key, 0) or 0)

            season_value = (master.season or "").strip().upper()
            season_factor = 1.2 if "WINTER" in season_value else 1.0
            style_factor = _safe_float(master.garment_2, default=1.0)
            lead_time = _safe_int(master.amazon_asin, default=0)
            buffer_days = _safe_int(master.buffer or master.production_time, default=0)
            average_daily_sales = net_sales / days_count if days_count else 0.0
            adjusted_ads = average_daily_sales * season_factor * style_factor
            required_qty = adjusted_ads * (lead_time + buffer_days)
            plan_qty = required_qty - good_inventory
            percent_available = (good_inventory / required_qty) * 100 if required_qty > 0 else 0.0
            if percent_available < 33:
                status = "RED"
            elif percent_available <= 66:
                status = "YELLOW"
            else:
                status = "GREEN"

            item = {
                "style_code": master.style_code,
                "sku": sku,
                "name": master.title,
                "type": master.type,
                "lifecycle": master.gross_weights_1,
                "size": (master.size or "-").strip() or (sales_row.get("size") or "-"),
                "net_sale_qty": net_sales,
                "net_sales": net_sales,
                "good_inventory": good_inventory,
                "average_daily_sales": round(average_daily_sales, 2),
                "season_factor": round(season_factor, 2),
                "style_factor": round(style_factor, 2),
                "adjusted_ads": round(adjusted_ads, 2),
                "lead_time": lead_time,
                "buffer": buffer_days,
                "required_qty": round(required_qty, 2),
                "plan": round(plan_qty, 2),
                "percent_available": round(percent_available, 2),
                "status": status,
            }
            items.append(item)

        return items

    def garment_planning_report(
        self,
        start_date: date,
        end_date: date,
        season: str = "both",
        type_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """Generate garment planning report with pagination for the dashboard page."""

        if end_date < start_date:
            start_date, end_date = end_date, start_date

        season_filter = (season or "both").strip().lower()
        all_items = self._collect_garment_planning_rows(start_date, end_date, season, type_filter=type_filter)

        status_breakdown = {"RED": 0, "YELLOW": 0, "GREEN": 0}
        total_net_sale_qty = 0
        total_good_inventory = 0
        total_required_qty = 0.0
        total_plan_qty = 0.0

        for row in all_items:
            status_breakdown[row["status"]] += 1
            total_net_sale_qty += int(row["net_sale_qty"])
            total_good_inventory += int(row["good_inventory"])
            total_required_qty += float(row["required_qty"])
            total_plan_qty += float(row["plan"])

        total_skus = len(all_items)
        safe_page_size = max(1, min(int(page_size), 500))
        safe_page = max(1, int(page))
        total_pages = max(1, (total_skus + safe_page_size - 1) // safe_page_size) if total_skus else 1
        safe_page = min(safe_page, total_pages)
        start_idx = (safe_page - 1) * safe_page_size
        page_items = all_items[start_idx : start_idx + safe_page_size]

        return {
            "report_type": "Garment Planning Report",
            "generated_at": datetime.utcnow().isoformat(),
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": max((end_date - start_date).days + 1, 1),
            },
            "season_filter": season_filter,
            "summary": {
                "total_skus": total_skus,
                "total_net_sale_qty": total_net_sale_qty,
                "total_net_sales": total_net_sale_qty,
                "total_good_inventory": total_good_inventory,
                "total_required_qty": round(total_required_qty, 2),
                "total_plan_qty": round(total_plan_qty, 2),
                "status_breakdown": status_breakdown,
            },
            "pagination": {
                "page": safe_page,
                "page_size": safe_page_size,
                "total_skus": total_skus,
                "total_pages": total_pages,
            },
            "items": page_items,
        }

    def garment_planning_report_csv(
        self,
        start_date: date,
        end_date: date,
        season: str = "both",
        type_filter: Optional[str] = None,
    ) -> bytes:
        rows = self._collect_garment_planning_rows(start_date, end_date, season, type_filter=type_filter)
        headers = [
            "style_code",
            "sku",
            "name",
            "type",
            "lifecycle",
            "size",
            "net_sale_qty",
            "good_inventory",
            "average_daily_sales",
            "season_factor",
            "style_factor",
            "adjusted_ads",
            "lead_time",
            "buffer",
            "required_qty",
            "plan",
            "percent_available",
            "status",
        ]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row.get(header, "") for header in headers])
        return buf.getvalue().encode("utf-8-sig")

    def fabric_planning_report(
        self,
        as_of_date: Optional[date] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """Build fabric planning rows using required qty from garment planning over last 30 days."""
        effective_end = as_of_date or date.today()
        effective_start = effective_end - timedelta(days=29)

        garment_rows = self._collect_garment_planning_rows(
            effective_start,
            effective_end,
            season="both",
        )
        required_qty_map: Dict[str, float] = {
            (str(row.get("sku", "")).strip().upper()): float(row.get("required_qty") or 0.0)
            for row in garment_rows
            if str(row.get("sku", "")).strip()
        }

        masters = self.db.query(ShopifyMasterData).order_by(
            ShopifyMasterData.variant_sku.asc(),
        ).all()

        items: List[Dict[str, Any]] = []
        total_required_qty = 0.0
        total_qty_required = 0.0

        for master in masters:
            sku = (master.variant_sku or "").strip()
            if not sku:
                continue

            sku_key = sku.upper()
            required_qty = float(required_qty_map.get(sku_key, 0.0) or 0.0)
            net_weight = _safe_float(master.net_weight, default=0.0)
            base_qty = net_weight * required_qty
            qty_required = base_qty + (0.25 * base_qty)

            total_required_qty += required_qty
            total_qty_required += qty_required

            items.append(
                {
                    "style_code": master.style_code,
                    "sku": sku,
                    "name": master.title,
                    "size": (master.size or "-").strip() or "-",
                    "required_qty": round(required_qty, 2),
                    "fabric": (master.fabric_type or "-").strip() or "-",
                    "print": (master.print_name or "-").strip() or "-",
                    "net_weight": round(net_weight, 4),
                    "qty_required": round(qty_required, 2),
                }
            )

        total_skus = len(items)
        safe_page_size = max(1, min(int(page_size), 500))
        safe_page = max(1, int(page))
        total_pages = max(1, (total_skus + safe_page_size - 1) // safe_page_size) if total_skus else 1
        safe_page = min(safe_page, total_pages)
        start_idx = (safe_page - 1) * safe_page_size
        page_items = items[start_idx : start_idx + safe_page_size]

        return {
            "report_type": "Fabric Planning Report",
            "generated_at": datetime.utcnow().isoformat(),
            "period": {
                "start_date": effective_start.isoformat(),
                "end_date": effective_end.isoformat(),
                "days": 30,
            },
            "summary": {
                "total_skus": total_skus,
                "total_required_qty": round(total_required_qty, 2),
                "total_qty_required": round(total_qty_required, 2),
            },
            "pagination": {
                "page": safe_page,
                "page_size": safe_page_size,
                "total_skus": total_skus,
                "total_pages": total_pages,
            },
            "items": page_items,
        }

    def production_planning_status_report(
        self,
        start_date: date,
        end_date: date,
        type_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Combine production planning raw data with required qty and scanning inventory."""

        if end_date < start_date:
            start_date, end_date = end_date, start_date

        # Required quantity source: garment planning report logic for same date window.
        garment_rows = self._collect_garment_planning_rows(start_date, end_date, season="both", type_filter=type_filter)
        required_qty_map: Dict[str, float] = {
            str(row.get("sku") or "").strip().upper(): float(row.get("required_qty") or 0.0)
            for row in garment_rows
            if str(row.get("sku") or "").strip()
        }

        scanning_rows = (
            self.db.query(
                FacilityInventorySnapshot.sku.label("sku"),
                func.coalesce(func.sum(FacilityInventorySnapshot.inventory), 0).label("scanning"),
            )
            .filter(
                FacilityInventorySnapshot.sku.isnot(None),
                FacilityInventorySnapshot.sku != "",
            )
            .group_by(FacilityInventorySnapshot.sku)
            .all()
        )
        scanning_map: Dict[str, int] = {
            str(row.sku or "").strip().upper(): int(row.scanning or 0)
            for row in scanning_rows
            if row.sku
        }

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())

        planning_rows = (
            self.db.query(ProductionPlanningReport)
            .filter(
                ProductionPlanningReport.updated_at >= start_dt,
                ProductionPlanningReport.updated_at < end_dt,
            )
            .order_by(ProductionPlanningReport.updated_at.desc(), ProductionPlanningReport.sku.asc())
            .all()
        )

        items: List[Dict[str, Any]] = []
        total_required_qty = 0.0
        total_balance = 0.0

        for row in planning_rows:
            sku = str(row.sku or "").strip()
            sku_key = sku.upper()

            required_qty = float(required_qty_map.get(sku_key, 0.0) or 0.0)
            scanning = int(scanning_map.get(sku_key, 0) or 0)

            cutting_plan = int(row.cutting_plan or 0)
            cutting = int(row.cutting or 0)
            stitching = int(row.stitching or 0)
            finishing = int(row.finishing or 0)
            balance = required_qty - cutting_plan - cutting - stitching - finishing - scanning

            total_required_qty += required_qty
            total_balance += balance

            items.append(
                {
                    "date": row.updated_at.date().isoformat() if row.updated_at else "",
                    "style_code": row.style_code or "",
                    "sku": sku,
                    "size": row.size or "",
                    "name": row.name or "",
                    "type": row.type or "",
                    "required_qty": round(required_qty, 2),
                    "cutting_plan": cutting_plan,
                    "cutting": cutting,
                    "stitching": stitching,
                    "finishing": finishing,
                    "scanning": scanning,
                    "balance": round(balance, 2),
                }
            )

        return {
            "report_type": "Production Planning & Status Report",
            "generated_at": datetime.utcnow().isoformat(),
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "summary": {
                "total_rows": len(items),
                "total_required_qty": round(total_required_qty, 2),
                "total_balance": round(total_balance, 2),
            },
            "items": items,
        }

    def production_planning_status_report_csv(
        self,
        start_date: date,
        end_date: date,
        type_filter: Optional[str] = None,
    ) -> bytes:
        payload = self.production_planning_status_report(start_date=start_date, end_date=end_date, type_filter=type_filter)
        rows = payload.get("items") or []

        headers = [
            "DATE",
            "Style_Code",
            "SKU",
            "Size",
            "NAME",
            "TYPE",
            "Required QTY",
            "Cutting Plan",
            "Cutting",
            "stitching",
            "finishing",
            "scanning",
            "BALANCE",
        ]

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(
                [
                    row.get("date", ""),
                    row.get("style_code", ""),
                    row.get("sku", ""),
                    row.get("size", ""),
                    row.get("name", ""),
                    row.get("type", ""),
                    row.get("required_qty", 0),
                    row.get("cutting_plan", 0),
                    row.get("cutting", 0),
                    row.get("stitching", 0),
                    row.get("finishing", 0),
                    row.get("scanning", 0),
                    row.get("balance", 0),
                ]
            )

        return buf.getvalue().encode("utf-8-sig")


    def daily_sales_report(self, report_date: date) -> Dict[str, Any]:
        """Generate daily sales report for a specific date"""
        sales = self.db.query(Sale).filter(
            Sale.transaction_date == report_date
        ).all()

        returns = [s for s in sales if s.is_return]
        actual_sales = [s for s in sales if not s.is_return]

        total_sales_value = sum(float(s.total_amount) for s in actual_sales)
        total_returns_value = sum(float(s.total_amount) for s in returns)
        net_sales = total_sales_value - total_returns_value

        total_units_sold = sum(s.quantity for s in actual_sales)
        total_units_returned = sum(s.quantity for s in returns)

        sales_data = [
            {
                "id": s.id,
                "garment_id": s.garment_id,
                "panel_id": s.panel_id,
                "size": s.size,
                "quantity": s.quantity,
                "unit_price": float(s.unit_price),
                "discount_percentage": float(s.discount_percentage),
                "total_amount": float(s.total_amount),
                "is_return": s.is_return,
                "invoice_number": s.invoice_number
            }
            for s in sales
        ]

        return {
            "report_type": "Daily Sales Report",
            "report_date": report_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_transactions": len(sales),
                "total_sales_transactions": len(actual_sales),
                "total_returns": len(returns),
                "total_units_sold": total_units_sold,
                "total_units_returned": total_units_returned,
                "net_units": total_units_sold - total_units_returned,
                "total_sales_value": total_sales_value,
                "total_returns_value": total_returns_value,
                "net_sales_value": net_sales
            },
            "transactions": sales_data
        }

    def daily_sales_report_single_sku(
        self,
        report_date: date,
        garment_id: int
    ) -> Dict[str, Any]:
        """Generate daily sales report for a single SKU"""
        sales = self.db.query(Sale).filter(
            and_(
                Sale.transaction_date == report_date,
                Sale.garment_id == garment_id
            )
        ).all()

        garment = self.db.query(Garment).filter(
            Garment.id == garment_id).first()

        # Group by size
        size_breakdown = {}
        for s in sales:
            if s.size not in size_breakdown:
                size_breakdown[s.size] = {
                    "quantity_sold": 0,
                    "quantity_returned": 0,
                    "sales_value": 0,
                    "returns_value": 0
                }

            if s.is_return:
                size_breakdown[s.size]["quantity_returned"] += s.quantity
                size_breakdown[s.size]["returns_value"] += float(
                    s.total_amount)
            else:
                size_breakdown[s.size]["quantity_sold"] += s.quantity
                size_breakdown[s.size]["sales_value"] += float(s.total_amount)

        # Calculate net for each size
        for size_data in size_breakdown.values():
            size_data["net_quantity"] = (
                size_data["quantity_sold"] - size_data["quantity_returned"]
            )
            size_data["net_value"] = (
                size_data["sales_value"] - size_data["returns_value"]
            )

        return {
            "report_type": "Daily Sales Report - Single SKU",
            "report_date": report_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "garment": {
                "id": garment.id,
                "style_sku": garment.style_sku,
                "name": garment.name,
                "category": garment.category
            } if garment else None,
            "size_breakdown": size_breakdown,
            "total_summary": {
                "total_quantity_sold": sum(
                    s["quantity_sold"] for s in size_breakdown.values()
                ),
                "total_quantity_returned": sum(
                    s["quantity_returned"] for s in size_breakdown.values()
                ),
                "total_sales_value": sum(
                    s["sales_value"] for s in size_breakdown.values()
                ),
                "total_returns_value": sum(
                    s["returns_value"] for s in size_breakdown.values()
                )
            }
        }

    def panel_wise_sales_report(
        self,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """Generate panel-wise sales report for a date range"""
        sales = self.db.query(Sale).filter(
            and_(
                Sale.transaction_date >= start_date,
                Sale.transaction_date <= end_date
            )
        ).all()

        panels = self.db.query(Panel).all()

        panel_data = {}
        for panel in panels:
            panel_sales = [s for s in sales if s.panel_id == panel.id]
            actual_sales = [s for s in panel_sales if not s.is_return]
            returns = [s for s in panel_sales if s.is_return]

            panel_data[panel.id] = {
                "panel_name": panel.panel_name,
                "panel_type": panel.panel_type,
                "is_active": panel.is_active,
                "total_transactions": len(panel_sales),
                "sales_transactions": len(actual_sales),
                "return_transactions": len(returns),
                "total_units_sold": sum(s.quantity for s in actual_sales),
                "total_units_returned": sum(s.quantity for s in returns),
                "gross_sales_value": sum(float(s.total_amount) for s in actual_sales),
                "returns_value": sum(float(s.total_amount) for s in returns),
                "net_sales_value": sum(
                    float(s.total_amount) for s in actual_sales
                ) - sum(float(s.total_amount) for s in returns)
            }

        return {
            "report_type": "Panel-Wise Sales Report",
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "generated_at": datetime.utcnow().isoformat(),
            "panels": panel_data,
            "grand_total": {
                "total_sales_value": sum(p["gross_sales_value"] for p in panel_data.values()),
                "total_returns_value": sum(p["returns_value"] for p in panel_data.values()),
                "net_sales_value": sum(p["net_sales_value"] for p in panel_data.values())
            }
        }

    def inactive_panel_report(self, days_threshold: int = 30) -> Dict[str, Any]:
        """Report on panels with no activity in the last N days"""
        from datetime import timedelta

        cutoff_date = date.today() - timedelta(days=days_threshold)

        all_panels = self.db.query(Panel).all()
        inactive_panels = []

        for panel in all_panels:
            # Check last sale date
            last_sale = self.db.query(Sale).filter(
                Sale.panel_id == panel.id
            ).order_by(Sale.transaction_date.desc()).first()

            if not last_sale or last_sale.transaction_date < cutoff_date:
                inactive_panels.append({
                    "id": panel.id,
                    "panel_name": panel.panel_name,
                    "panel_type": panel.panel_type,
                    "is_active": panel.is_active,
                    "last_sale_date": last_sale.transaction_date.isoformat() if last_sale else None,
                    "days_since_last_sale": (
                        (date.today() - last_sale.transaction_date).days
                        if last_sale else None
                    )
                })

        return {
            "report_type": "Inactive Panel Report",
            "criteria": f"No sales in last {days_threshold} days",
            "generated_at": datetime.utcnow().isoformat(),
            "inactive_panels_count": len(inactive_panels),
            "inactive_panels": inactive_panels
        }


    def slow_moving_inventory_report(self, days_period: int = 90) -> Dict[str, Any]:
        """Identify slow-moving inventory based on sales velocity"""
        from datetime import timedelta

        start_date = date.today() - timedelta(days=days_period)

        # Get all inventory items
        inventory_items = self.db.query(Inventory).all()
        slow_movers = []

        for inv in inventory_items:
            # Calculate sales for this garment-size in the period
            sales_count = self.db.query(func.sum(Sale.quantity)).filter(
                and_(
                    Sale.garment_id == inv.garment_id,
                    Sale.size == inv.size,
                    Sale.transaction_date >= start_date,
                    Sale.is_return == False
                )
            ).scalar() or 0

            # Calculate turnover rate (sales per day)
            turnover_rate = float(sales_count) / \
                days_period if sales_count > 0 else 0

            # Consider slow if turnover rate < 0.1 units/day and stock > 10
            if turnover_rate < 0.1 and inv.good_stock > 10:
                garment = self.db.query(Garment).filter(
                    Garment.id == inv.garment_id
                ).first()

                slow_movers.append({
                    "garment_id": inv.garment_id,
                    "garment_name": garment.name if garment else "Unknown",
                    "style_sku": garment.style_sku if garment else "Unknown",
                    "size": inv.size,
                    "good_stock": inv.good_stock,
                    "virtual_stock": inv.virtual_stock,
                    "sales_in_period": int(sales_count),
                    "turnover_rate_per_day": round(turnover_rate, 3),
                    "days_of_stock": round(inv.good_stock / turnover_rate, 1) if turnover_rate > 0 else float('inf')
                })

        return {
            "report_type": "Slow Moving Inventory Report",
            "period_days": days_period,
            "criteria": "Turnover rate < 0.1 units/day and stock > 10",
            "generated_at": datetime.utcnow().isoformat(),
            "slow_moving_items_count": len(slow_movers),
            "slow_moving_items": slow_movers
        }

    def fast_moving_inventory_report(self, days_period: int = 90) -> Dict[str, Any]:
        """Identify fast-moving inventory based on sales velocity"""
        from datetime import timedelta

        start_date = date.today() - timedelta(days=days_period)

        inventory_items = self.db.query(Inventory).all()
        fast_movers = []

        for inv in inventory_items:
            sales_count = self.db.query(func.sum(Sale.quantity)).filter(
                and_(
                    Sale.garment_id == inv.garment_id,
                    Sale.size == inv.size,
                    Sale.transaction_date >= start_date,
                    Sale.is_return == False
                )
            ).scalar() or 0

            turnover_rate = float(sales_count) / \
                days_period if sales_count > 0 else 0

            # Consider fast if turnover rate > 1 unit/day
            if turnover_rate > 1.0:
                garment = self.db.query(Garment).filter(
                    Garment.id == inv.garment_id
                ).first()

                # Calculate reorder recommendation
                days_of_stock = inv.good_stock / turnover_rate if turnover_rate > 0 else 0
                needs_reorder = days_of_stock < 30  # Less than 30 days of stock

                fast_movers.append({
                    "garment_id": inv.garment_id,
                    "garment_name": garment.name if garment else "Unknown",
                    "style_sku": garment.style_sku if garment else "Unknown",
                    "size": inv.size,
                    "good_stock": inv.good_stock,
                    "sales_in_period": int(sales_count),
                    "turnover_rate_per_day": round(turnover_rate, 2),
                    "days_of_stock_remaining": round(days_of_stock, 1),
                    "needs_reorder": needs_reorder,
                    "recommended_order_quantity": round(turnover_rate * 60, 0) if needs_reorder else 0
                })

        # Sort by turnover rate descending
        fast_movers.sort(
            key=lambda x: x["turnover_rate_per_day"], reverse=True)

        return {
            "report_type": "Fast Moving Inventory Report",
            "period_days": days_period,
            "criteria": "Turnover rate > 1 unit/day",
            "generated_at": datetime.utcnow().isoformat(),
            "fast_moving_items_count": len(fast_movers),
            "items_needing_reorder": sum(1 for item in fast_movers if item["needs_reorder"]),
            "fast_moving_items": fast_movers
        }


    def production_plan_report(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Generate production plan status report"""
        query = self.db.query(ProductionPlan)

        if start_date:
            query = query.filter(ProductionPlan.target_date >= start_date)
        if end_date:
            query = query.filter(ProductionPlan.target_date <= end_date)

        plans = query.all()

        # Group by status
        status_summary = defaultdict(list)

        for plan in plans:
            garment = self.db.query(Garment).filter(
                Garment.id == plan.garment_id
            ).first()

            # Get activities for this plan
            activities = self.db.query(ProductionActivity).filter(
                ProductionActivity.production_plan_id == plan.id
            ).all()

            actual_quantity = sum(
                float(a.quantity) for a in activities
                if a.activity_type == "CUTTING"
            )

            completion_percentage = (
                (actual_quantity / plan.planned_quantity * 100)
                if plan.planned_quantity > 0 else 0
            )

            plan_data = {
                "id": plan.id,
                "plan_name": plan.plan_name,
                "garment_sku": garment.style_sku if garment else "Unknown",
                "garment_name": garment.name if garment else "Unknown",
                "planned_quantity": plan.planned_quantity,
                "actual_quantity": actual_quantity,
                "completion_percentage": round(completion_percentage, 2),
                "target_date": plan.target_date.isoformat(),
                "fabric_requirement": float(plan.fabric_requirement) if plan.fabric_requirement else 0,
                "yarn_requirement": float(plan.yarn_requirement) if plan.yarn_requirement else 0,
                "activities_count": len(activities)
            }

            status_summary[plan.status].append(plan_data)

        return {
            "report_type": "Production Plan Report",
            "period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            },
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_plans": len(plans),
                "planned": len(status_summary["PLANNED"]),
                "in_progress": len(status_summary["IN_PROGRESS"]),
                "completed": len(status_summary["COMPLETED"])
            },
            "plans_by_status": status_summary
        }

    def daily_production_variance_report(self, report_date: date) -> Dict[str, Any]:
        """Generate daily production report with gross weight variance"""
        activities = self.db.query(ProductionActivity).filter(
            ProductionActivity.activity_date == report_date
        ).all()

        variance_data = []
        total_variance = 0

        for activity in activities:
            if activity.gross_weight_calculated and activity.gross_weight_actual:
                calculated = float(activity.gross_weight_calculated)
                actual = float(activity.gross_weight_actual)
                variance = actual - calculated
                variance_percentage = (
                    variance / calculated * 100) if calculated > 0 else 0

                plan = self.db.query(ProductionPlan).filter(
                    ProductionPlan.id == activity.production_plan_id
                ).first()

                variance_data.append({
                    "activity_id": activity.id,
                    "production_plan": plan.plan_name if plan else "Unknown",
                    "activity_type": activity.activity_type,
                    "quantity": float(activity.quantity),
                    "gross_weight_calculated": calculated,
                    "gross_weight_actual": actual,
                    "variance": round(variance, 3),
                    "variance_percentage": round(variance_percentage, 2),
                    "notes": activity.notes
                })

                total_variance += abs(variance)

        return {
            "report_type": "Daily Production Variance Report",
            "report_date": report_date.isoformat(),
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "total_activities": len(activities),
                "activities_with_variance_data": len(variance_data),
                "total_absolute_variance": round(total_variance, 3),
                "average_variance": round(
                    total_variance / len(variance_data), 3
                ) if variance_data else 0
            },
            "variance_details": variance_data
        }


    def bundle_sku_sales_report(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Generate sales report for bundle SKUs (combo products).
        Note: Requires bundle definition in garments table or separate bundle table.
        For now, identifying bundles by category or naming convention.
        """
        query = self.db.query(Sale).join(Garment)

        if start_date:
            query = query.filter(Sale.transaction_date >= start_date)
        if end_date:
            query = query.filter(Sale.transaction_date <= end_date)

        # Identify bundles - products with "BUNDLE", "COMBO", "SET" in category or name
        query = query.filter(
            or_(
                Garment.category.ilike('%bundle%'),
                Garment.category.ilike('%combo%'),
                Garment.category.ilike('%set%'),
                Garment.name.ilike('%bundle%'),
                Garment.name.ilike('%combo%'),
                Garment.name.ilike('%set%')
            )
        )

        sales = query.all()

        bundle_data = {}
        for sale in sales:
            garment_id = sale.garment_id
            if garment_id not in bundle_data:
                bundle_data[garment_id] = {
                    "garment_id": garment_id,
                    "sku": sale.garment.style_sku,
                    "name": sale.garment.name,
                    "category": sale.garment.category,
                    "mrp": float(sale.garment.mrp or 0),
                    "total_sales": 0,
                    "total_returns": 0,
                    "net_units": 0,
                    "gross_revenue": 0,
                    "net_revenue": 0,
                    "sizes_sold": {}
                }

            qty = sale.quantity if not sale.is_return else -sale.quantity
            amount = float(sale.total_amount or 0)

            bundle_data[garment_id]["total_sales"] += sale.quantity if not sale.is_return else 0
            bundle_data[garment_id]["total_returns"] += sale.quantity if sale.is_return else 0
            bundle_data[garment_id]["net_units"] += qty
            bundle_data[garment_id]["gross_revenue"] += amount if not sale.is_return else 0
            bundle_data[garment_id]["net_revenue"] += amount

            # Track size-wise sales
            size = sale.size
            if size not in bundle_data[garment_id]["sizes_sold"]:
                bundle_data[garment_id]["sizes_sold"][size] = 0
            bundle_data[garment_id]["sizes_sold"][size] += qty

        bundles_list = list(bundle_data.values())
        bundles_list.sort(key=lambda x: x["net_revenue"], reverse=True)

        total_net_revenue = sum(b["net_revenue"] for b in bundles_list)
        total_net_units = sum(b["net_units"] for b in bundles_list)

        return {
            "report_type": "Bundle SKU Sales Report",
            "generated_at": datetime.utcnow().isoformat(),
            "period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            },
            "summary": {
                "total_bundle_skus": len(bundles_list),
                "total_net_units_sold": total_net_units,
                "total_net_revenue": round(total_net_revenue, 2)
            },
            "bundles": bundles_list
        }


    def discount_report_general(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Generate general discount report across all sales"""
        query = self.db.query(Sale).join(Garment)

        if start_date:
            query = query.filter(Sale.transaction_date >= start_date)
        if end_date:
            query = query.filter(Sale.transaction_date <= end_date)

        sales = query.all()

        total_mrp_value = 0
        total_selling_price = 0
        total_discount_amount = 0
        discount_buckets = {
            "0-10%": 0,
            "10-20%": 0,
            "20-30%": 0,
            "30-40%": 0,
            "40%+": 0
        }

        sales_data = []

        for sale in sales:
            mrp = float(sale.garment.mrp or 0)
            unit_price = float(sale.unit_price or 0)
            qty = sale.quantity
            discount_pct = float(sale.discount_percentage or 0)

            mrp_value = mrp * qty
            selling_value = unit_price * qty
            discount_amt = mrp_value - selling_value

            total_mrp_value += mrp_value
            total_selling_price += selling_value
            total_discount_amount += discount_amt

            # Categorize discount
            if discount_pct < 10:
                discount_buckets["0-10%"] += 1
            elif discount_pct < 20:
                discount_buckets["10-20%"] += 1
            elif discount_pct < 30:
                discount_buckets["20-30%"] += 1
            elif discount_pct < 40:
                discount_buckets["30-40%"] += 1
            else:
                discount_buckets["40%+"] += 1

            if not sale.is_return:  # Only include actual sales
                sales_data.append({
                    "sale_id": sale.id,
                    "sale_date": sale.transaction_date.isoformat(),
                    "sku": sale.garment.style_sku,
                    "garment_name": sale.garment.name,
                    "quantity": qty,
                    "mrp": round(mrp, 2),
                    "selling_price": round(unit_price, 2),
                    "discount_percentage": round(discount_pct, 2),
                    "discount_amount": round(discount_amt, 2),
                    "total_mrp_value": round(mrp_value, 2),
                    "total_selling_value": round(selling_value, 2)
                })

        overall_discount_pct = (
            (total_discount_amount / total_mrp_value *
             100) if total_mrp_value > 0 else 0
        )

        return {
            "report_type": "Discount Report - General",
            "generated_at": datetime.utcnow().isoformat(),
            "period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            },
            "summary": {
                "total_transactions": len([s for s in sales if not s.is_return]),
                "total_mrp_value": round(total_mrp_value, 2),
                "total_selling_price": round(total_selling_price, 2),
                "total_discount_amount": round(total_discount_amount, 2),
                "overall_discount_percentage": round(overall_discount_pct, 2),
                "discount_distribution": discount_buckets
            },
            "sales": sales_data
        }

    def discount_report_by_panel(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Generate discount report grouped by sales panel"""
        query = self.db.query(Sale).join(Garment).join(Panel)

        if start_date:
            query = query.filter(Sale.transaction_date >= start_date)
        if end_date:
            query = query.filter(Sale.transaction_date <= end_date)

        sales = query.all()

        panel_data = {}

        for sale in sales:
            if sale.is_return:
                continue

            panel_id = sale.panel_id
            if panel_id not in panel_data:
                panel_data[panel_id] = {
                    "panel_id": panel_id,
                    "panel_name": sale.panel.panel_name,
                    "panel_type": sale.panel.panel_type,
                    "total_transactions": 0,
                    "total_mrp_value": 0,
                    "total_selling_value": 0,
                    "total_discount_amount": 0,
                    "average_discount_percentage": 0
                }

            mrp = float(sale.garment.mrp or 0)
            unit_price = float(sale.unit_price or 0)
            qty = sale.quantity

            mrp_value = mrp * qty
            selling_value = unit_price * qty
            discount_amt = mrp_value - selling_value

            panel_data[panel_id]["total_transactions"] += 1
            panel_data[panel_id]["total_mrp_value"] += mrp_value
            panel_data[panel_id]["total_selling_value"] += selling_value
            panel_data[panel_id]["total_discount_amount"] += discount_amt

        # Calculate average discount percentage for each panel
        for panel_id, data in panel_data.items():
            if data["total_mrp_value"] > 0:
                data["average_discount_percentage"] = round(
                    (data["total_discount_amount"] /
                     data["total_mrp_value"]) * 100, 2
                )
            data["total_mrp_value"] = round(data["total_mrp_value"], 2)
            data["total_selling_value"] = round(data["total_selling_value"], 2)
            data["total_discount_amount"] = round(
                data["total_discount_amount"], 2)

        panels_list = list(panel_data.values())
        panels_list.sort(
            key=lambda x: x["total_discount_amount"], reverse=True)

        return {
            "report_type": "Discount Report - By Panel",
            "generated_at": datetime.utcnow().isoformat(),
            "period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            },
            "summary": {
                "total_panels": len(panels_list),
                "total_discount_amount": round(
                    sum(p["total_discount_amount"] for p in panels_list), 2
                )
            },
            "panels": panels_list
        }

    def settlement_report(
        self,
        panel_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Generate settlement report for panels showing amounts due/payable.
        """
        query = self.db.query(Sale).join(Garment).join(Panel)

        if panel_id:
            query = query.filter(Sale.panel_id == panel_id)
        if start_date:
            query = query.filter(Sale.transaction_date >= start_date)
        if end_date:
            query = query.filter(Sale.transaction_date <= end_date)

        sales = query.all()

        panel_settlements = {}

        for sale in sales:
            pid = sale.panel_id
            if pid not in panel_settlements:
                panel_settlements[pid] = {
                    "panel_id": pid,
                    "panel_name": sale.panel.panel_name,
                    "panel_type": sale.panel.panel_type,
                    "total_sales_value": 0,
                    "total_returns_value": 0,
                    "net_sales_value": 0,
                    "platform_commission": 0,  # Calculate based on panel agreement
                    "logistics_charges": 0,
                    "other_deductions": 0,
                    "amount_payable_to_panel": 0,
                    "transaction_count": 0
                }

            amount = float(sale.total_amount or 0)

            if sale.is_return:
                panel_settlements[pid]["total_returns_value"] += amount
            else:
                panel_settlements[pid]["total_sales_value"] += amount
                panel_settlements[pid]["transaction_count"] += 1

            panel_settlements[pid]["net_sales_value"] = (
                panel_settlements[pid]["total_sales_value"] -
                panel_settlements[pid]["total_returns_value"]
            )

        # Calculate commissions and payables
        for pid, data in panel_settlements.items():
            net_sales = data["net_sales_value"]

            # Assuming 10% platform commission (should be configurable per panel)
            data["platform_commission"] = round(net_sales * 0.10, 2)

            # Assuming 5% logistics (should be actual data)
            data["logistics_charges"] = round(net_sales * 0.05, 2)

            # Calculate final payable amount
            data["amount_payable_to_panel"] = round(
                net_sales - data["platform_commission"] -
                data["logistics_charges"] - data["other_deductions"],
                2
            )

            # Round other values
            data["total_sales_value"] = round(data["total_sales_value"], 2)
            data["total_returns_value"] = round(data["total_returns_value"], 2)
            data["net_sales_value"] = round(data["net_sales_value"], 2)

        settlements_list = list(panel_settlements.values())
        settlements_list.sort(key=lambda x: x["net_sales_value"], reverse=True)

        total_payable = sum(s["amount_payable_to_panel"]
                            for s in settlements_list)

        return {
            "report_type": "Settlement Report",
            "generated_at": datetime.utcnow().isoformat(),
            "period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            },
            "summary": {
                "total_panels": len(settlements_list),
                "total_amount_payable": round(total_payable, 2),
                "total_net_sales": round(
                    sum(s["net_sales_value"] for s in settlements_list), 2
                )
            },
            "settlements": settlements_list
        }
