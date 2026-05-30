import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.export_models import ExportJob, SalesOrderRecord, SalesReturnRecord, SyncAuditLog
from app.services.unicommerce_data_service import get_unicommerce_data_service

logger = logging.getLogger(__name__)

class ParityValidator:
    """Validates data parity between Unicommerce raw exports and normalized DB rows."""

    @classmethod
    def validate_recent_parity(cls, db: Session, days_back: int = 7) -> Dict[str, Any]:
        """Validates parity for the last N days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # 1. Check ExportJobs coverage
        jobs = db.query(ExportJob).filter(
            ExportJob.completed_at >= cutoff_date,
            ExportJob.status == "completed"
        ).all()
        
        total_csv_returns = sum(j.total_csv_rows for j in jobs if j.export_type == "return_gst")
        total_csv_sales = sum(j.total_csv_rows for j in jobs if j.export_type == "sales_order")
        
        parsed_returns = sum(j.parsed_entities for j in jobs if j.export_type == "return_gst")
        parsed_sales = sum(j.parsed_entities for j in jobs if j.export_type == "sales_order")
        
        # Calculate coverage percent (parsed vs total csv). Note that parsed might be smaller 
        # due to duplicate merging (like same return_code).
        # A more accurate parity check: Are there missing orders?
        
        # Parity is healthy if we successfully parsed > 98% of what was in the CSV
        # (accounting for some valid duplicates that get merged)
        return_parity = (parsed_returns / total_csv_returns * 100) if total_csv_returns > 0 else 100.0
        sales_parity = (parsed_sales / total_csv_sales * 100) if total_csv_sales > 0 else 100.0
        
        # Note: If return_parity drops below 90% (since many SKUs merge into 1 return_code, 
        # parity% might naturally be lower than 100%. We use 80% as a safe lower bound for returns, 
        # but 99% for sales).
        
        is_healthy = sales_parity >= 99.0 and return_parity >= 80.0
        
        return {
            "healthy": is_healthy,
            "sales_parity": round(sales_parity, 2),
            "return_parity": round(return_parity, 2),
            "total_csv_returns": total_csv_returns,
            "total_csv_sales": total_csv_sales,
            "parsed_returns": parsed_returns,
            "parsed_sales": parsed_sales
        }

    @classmethod
    def record_sync_audit(
        cls, 
        db: Session, 
        entity: str, 
        rows_fetched: int, 
        rows_inserted: int, 
        duration: float,
        rows_updated: int = 0,
        duplicates_detected: int = 0,
        missing_rows: int = 0,
        error_count: int = 0
    ) -> SyncAuditLog:
        """Records a sync audit log entry."""
        processed_rows = max(0, int(rows_inserted or 0) + int(rows_updated or 0))
        coverage = (processed_rows / rows_fetched * 100) if rows_fetched > 0 else (0.0 if error_count else 100.0)
        parity = coverage # They are effectively the same for a single job unless we do deeper DB checks
        
        audit = SyncAuditLog(
            sync_time=datetime.utcnow(),
            entity=entity,
            rows_fetched=rows_fetched,
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            duplicates_detected=duplicates_detected,
            missing_rows=missing_rows,
            coverage_percent=coverage,
            sync_duration=duration,
            parity_percent=parity,
            error_count=error_count
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)
        return audit

    @classmethod
    async def validate_inventory_parity(cls, facility_code: str = "anthrilo") -> Dict[str, Any]:
        """Validate the DB inventory snapshot against a fresh live export."""
        from app.services.sync_inventory_snapshot import fetch_inventory_export_preview

        db_result = get_unicommerce_data_service().get_inventory_data(warehouse=facility_code)
        live_result = await fetch_inventory_export_preview(facility_code)

        if not db_result.get("success"):
            return {
                "healthy": False,
                "entity": "inventory_snapshot",
                "facility_code": facility_code,
                "error": db_result.get("error", "DB inventory read failed"),
                "data_source": db_result.get("data_source"),
            }

        if not live_result.get("success"):
            return {
                "healthy": False,
                "entity": "inventory_snapshot",
                "facility_code": facility_code,
                "error": live_result.get("error", "Live inventory export failed"),
                "db": db_result.get("summary", {}),
            }

        db_summary = dict(db_result.get("summary") or {})
        live_summary = {
            "total_skus": int(live_result.get("unique_rows", 0) or 0),
            "total_available_qty": int(live_result.get("total_real_inventory", 0) or 0),
            "total_reserved_qty": int(live_result.get("total_virtual_inventory", 0) or 0),
        }

        db_total_skus = int(db_summary.get("total_skus", 0) or 0)
        db_available_qty = int(db_summary.get("total_available_qty", 0) or 0)
        db_reserved_qty = int(db_summary.get("total_reserved_qty", 0) or 0)

        sku_diff = db_total_skus - live_summary["total_skus"]
        available_diff = db_available_qty - live_summary["total_available_qty"]
        reserved_diff = db_reserved_qty - live_summary["total_reserved_qty"]

        healthy = sku_diff == 0 and available_diff == 0 and reserved_diff == 0
        return {
            "healthy": healthy,
            "entity": "inventory_snapshot",
            "facility_code": facility_code,
            "db": db_summary,
            "live": {
                **live_summary,
                "rows_fetched": int(live_result.get("rows_fetched", 0) or 0),
                "duplicate_rows": int(live_result.get("duplicate_rows", 0) or 0),
                "missing_sku_rows": int(live_result.get("missing_sku_rows", 0) or 0),
                "duration": float(live_result.get("duration", 0.0) or 0.0),
            },
            "differences": {
                "total_skus": sku_diff,
                "total_available_qty": available_diff,
                "total_reserved_qty": reserved_diff,
            },
            "passed": healthy,
        }
