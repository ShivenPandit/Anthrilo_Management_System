from datetime import date, datetime
from typing import List, Optional, Dict, Any
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from app.db.models import (
    Fabric, Yarn, Garment, Inventory, Sale, 
    ProductionPlan, ProductionActivity, Panel, PaidAd, Discount
)


class ReportsService:
    """Service for generating all business reports"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ==================== FABRIC REPORTS ====================
    
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
    
    # ==================== SALES REPORTS ====================
    
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
        
        garment = self.db.query(Garment).filter(Garment.id == garment_id).first()
        
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
                size_breakdown[s.size]["returns_value"] += float(s.total_amount)
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
    
    # ==================== INVENTORY REPORTS ====================
    
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
            turnover_rate = float(sales_count) / days_period if sales_count > 0 else 0
            
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
            
            turnover_rate = float(sales_count) / days_period if sales_count > 0 else 0
            
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
        fast_movers.sort(key=lambda x: x["turnover_rate_per_day"], reverse=True)
        
        return {
            "report_type": "Fast Moving Inventory Report",
            "period_days": days_period,
            "criteria": "Turnover rate > 1 unit/day",
            "generated_at": datetime.utcnow().isoformat(),
            "fast_moving_items_count": len(fast_movers),
            "items_needing_reorder": sum(1 for item in fast_movers if item["needs_reorder"]),
            "fast_moving_items": fast_movers
        }
    
    # ==================== PRODUCTION REPORTS ====================
    
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
        status_summary = {
            "PLANNED": [],
            "IN_PROGRESS": [],
            "COMPLETED": []
        }
        
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
                variance_percentage = (variance / calculated * 100) if calculated > 0 else 0
                
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
