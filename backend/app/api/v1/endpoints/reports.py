from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from app.db.session import get_db
from app.services.reports import ReportsService

router = APIRouter()


# ==================== FABRIC REPORTS ====================

@router.get("/fabric/stock-sheet/total")
def get_fabric_stock_sheet_total(db: Session = Depends(get_db)):
    """Get total fabric stock sheet across all types"""
    service = ReportsService(db)
    return service.fabric_stock_sheet_total()


@router.get("/fabric/stock-sheet/by-type/{fabric_type}")
def get_fabric_stock_sheet_by_type(
    fabric_type: str,
    db: Session = Depends(get_db)
):
    """Get fabric stock sheet filtered by fabric type (JERSEY, TERRY, FLEECE)"""
    service = ReportsService(db)
    return service.fabric_stock_sheet_by_type(fabric_type.upper())


@router.get("/fabric/stock-sheet/by-period")
def get_fabric_stock_sheet_by_period(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """Get fabric stock sheet for a specific time period"""
    service = ReportsService(db)
    return service.fabric_stock_sheet_by_period(start_date, end_date)


@router.get("/fabric/cost-sheet")
def get_fabric_cost_sheet(db: Session = Depends(get_db)):
    """Get fabric cost sheet with cost breakdown"""
    service = ReportsService(db)
    return service.fabric_cost_sheet()


# ==================== SALES REPORTS ====================

@router.get("/sales/daily/{report_date}")
def get_daily_sales_report(
    report_date: date,
    db: Session = Depends(get_db)
):
    """Get daily sales report for a specific date"""
    service = ReportsService(db)
    return service.daily_sales_report(report_date)


@router.get("/sales/daily/{report_date}/sku/{garment_id}")
def get_daily_sales_report_single_sku(
    report_date: date,
    garment_id: int,
    db: Session = Depends(get_db)
):
    """Get daily sales report for a single SKU"""
    service = ReportsService(db)
    return service.daily_sales_report_single_sku(report_date, garment_id)


@router.get("/sales/panel-wise")
def get_panel_wise_sales_report(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """Get panel-wise sales report for a date range"""
    service = ReportsService(db)
    return service.panel_wise_sales_report(start_date, end_date)


@router.get("/sales/inactive-panels")
def get_inactive_panel_report(
    days_threshold: int = Query(30, description="Days of inactivity threshold"),
    db: Session = Depends(get_db)
):
    """Get report on panels with no activity in the last N days"""
    service = ReportsService(db)
    return service.inactive_panel_report(days_threshold)


# ==================== INVENTORY REPORTS ====================

@router.get("/inventory/slow-moving")
def get_slow_moving_inventory_report(
    days_period: int = Query(90, description="Period in days to analyze"),
    db: Session = Depends(get_db)
):
    """Get slow-moving inventory report based on sales velocity"""
    service = ReportsService(db)
    return service.slow_moving_inventory_report(days_period)


@router.get("/inventory/fast-moving")
def get_fast_moving_inventory_report(
    days_period: int = Query(90, description="Period in days to analyze"),
    db: Session = Depends(get_db)
):
    """Get fast-moving inventory report with reorder recommendations"""
    service = ReportsService(db)
    return service.fast_moving_inventory_report(days_period)


# ==================== PRODUCTION REPORTS ====================

@router.get("/production/plan-status")
def get_production_plan_report(
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    db: Session = Depends(get_db)
):
    """Get production plan status report"""
    service = ReportsService(db)
    return service.production_plan_report(start_date, end_date)


@router.get("/production/daily-variance/{report_date}")
def get_daily_production_variance_report(
    report_date: date,
    db: Session = Depends(get_db)
):
    """Get daily production variance report (calculated vs actual gross weight)"""
    service = ReportsService(db)
    return service.daily_production_variance_report(report_date)


# ==================== COMBINED REPORTS ====================

@router.get("/summary/all")
def get_summary_report(db: Session = Depends(get_db)):
    """Get a comprehensive summary report combining key metrics"""
    service = ReportsService(db)
    
    from datetime import timedelta
    today = date.today()
    
    return {
        "report_type": "Comprehensive Summary Report",
        "generated_at": today.isoformat(),
        "fabric_stock": service.fabric_stock_sheet_total()["summary"],
        "daily_sales": service.daily_sales_report(today)["summary"],
        "slow_moving_count": service.slow_moving_inventory_report(90)["slow_moving_items_count"],
        "fast_moving_count": service.fast_moving_inventory_report(90)["fast_moving_items_count"],
        "production_plans": service.production_plan_report()["summary"]
    }
