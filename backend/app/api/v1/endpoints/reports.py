from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from app.db.session import get_db
from app.services.reports import ReportsService
from app.services.sales_service import get_daily_sales

router = APIRouter()


@router.get("/raw-materials/stock-analysis")
def get_stock_analysis(
    category: Optional[str] = Query(
        None, description="Filter by category: Yarn, Fabric"),
    db: Session = Depends(get_db)
):
    """Get raw materials stock analysis combining yarn and fabric data"""
    service = ReportsService(db)
    return service.raw_materials_stock_analysis(category)


@router.get("/raw-materials/yarn-forecasting")
def get_yarn_forecasting(
    forecast_days: int = Query(30, description="Forecast period in days"),
    db: Session = Depends(get_db)
):
    """Get yarn demand forecasting based on production plans and consumption"""
    service = ReportsService(db)
    return service.yarn_forecasting_report(forecast_days)


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


@router.get("/sales/daily/{report_date}")
def get_daily_sales_report(
    report_date: date,
    db: Session = Depends(get_db)
):
    """Get daily sales report for a specific date (with Redis caching)"""
    return get_daily_sales(report_date, db)


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
    days_threshold: int = Query(
        30, description="Days of inactivity threshold"),
    db: Session = Depends(get_db)
):
    """Get report on panels with no activity in the last N days"""
    service = ReportsService(db)
    return service.inactive_panel_report(days_threshold)


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


@router.get("/garments/planning-report")
def get_garment_planning_report(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    season: str = Query("both", description="Season filter: summer, winter, or both"),
    type: Optional[str] = Query(None, description="Type filter (comma-separated for multiple)"),
    page: int = Query(1, ge=1, description="Page number (20 SKUs per page)"),
    page_size: int = Query(20, ge=1, le=500, description="Rows per page"),
    db: Session = Depends(get_db)
):
    """Get garment planning report for simple Shopify SKUs with sales in range (paginated)."""
    service = ReportsService(db)
    return service.garment_planning_report(start_date, end_date, season, type_filter=type, page=page, page_size=page_size)


@router.get("/garments/planning-report/export.csv")
def export_garment_planning_report_csv(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    season: str = Query("both", description="Season filter: summer, winter, or both"),
    type: Optional[str] = Query(None, description="Type filter (comma-separated for multiple)"),
    db: Session = Depends(get_db),
):
    """Download full garment planning report as CSV (same filters as the table)."""
    service = ReportsService(db)
    body = service.garment_planning_report_csv(start_date, end_date, season, type_filter=type)
    fname = f"garment-planning_{start_date.isoformat()}_{end_date.isoformat()}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/garments/fabric-planning-report")
def get_fabric_planning_report(
    as_of_date: Optional[date] = Query(None, description="Anchor date for rolling last 30 days (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="Page number (20 SKUs per page)"),
    page_size: int = Query(20, ge=1, le=500, description="Rows per page"),
    db: Session = Depends(get_db),
):
    """Get fabric planning report using required qty from garment planning over last 30 days."""
    service = ReportsService(db)
    return service.fabric_planning_report(as_of_date=as_of_date, page=page, page_size=page_size)


@router.get("/garments/production-planning-status-report")
def get_production_planning_status_report(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    type: Optional[str] = Query(None, description="Type filter (comma-separated for multiple)"),
    db: Session = Depends(get_db),
):
    """Get production planning & status report."""
    service = ReportsService(db)
    return service.production_planning_status_report(start_date=start_date, end_date=end_date, type_filter=type)


@router.get("/garments/production-planning-status-report/export.csv")
def export_production_planning_status_report_csv(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    type: Optional[str] = Query(None, description="Type filter (comma-separated for multiple)"),
    db: Session = Depends(get_db),
):
    """Download production planning & status report as CSV."""
    service = ReportsService(db)
    body = service.production_planning_status_report_csv(start_date=start_date, end_date=end_date, type_filter=type)
    fname = f"production-planning-status_{start_date.isoformat()}_{end_date.isoformat()}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/summary/all")
def get_summary_report(db: Session = Depends(get_db)):
    """Get a comprehensive summary report combining key metrics"""
    service = ReportsService(db)

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


@router.get("/sales/bundle-sku")
def get_bundle_sku_sales_report(
    start_date: Optional[date] = Query(
        None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(
        None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """Get sales report for bundle/combo SKUs"""
    service = ReportsService(db)
    return service.bundle_sku_sales_report(start_date, end_date)


@router.get("/discounts/general")
def get_discount_report_general(
    start_date: Optional[date] = Query(
        None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(
        None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """Get general discount report across all sales"""
    service = ReportsService(db)
    return service.discount_report_general(start_date, end_date)


@router.get("/discounts/by-panel")
def get_discount_report_by_panel(
    start_date: Optional[date] = Query(
        None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(
        None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """Get discount report grouped by sales panel"""
    service = ReportsService(db)
    return service.discount_report_by_panel(start_date, end_date)


@router.get("/settlements/panel-settlement")
def get_settlement_report(
    panel_id: Optional[int] = Query(
        None, description="Filter by specific panel ID"),
    start_date: Optional[date] = Query(
        None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(
        None, description="End date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """Get settlement report for panels showing amounts due/payable"""
    service = ReportsService(db)
    return service.settlement_report(panel_id, start_date, end_date)
