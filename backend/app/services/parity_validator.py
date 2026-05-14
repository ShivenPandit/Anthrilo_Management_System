import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.export_models import ExportJob, SalesOrderRecord, SalesReturnRecord, SyncAuditLog

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
        error_count: int = 0
    ) -> SyncAuditLog:
        """Records a sync audit log entry."""
        coverage = (rows_inserted / rows_fetched * 100) if rows_fetched > 0 else 100.0
        parity = coverage # They are effectively the same for a single job unless we do deeper DB checks
        
        audit = SyncAuditLog(
            sync_time=datetime.utcnow(),
            entity=entity,
            rows_fetched=rows_fetched,
            rows_inserted=rows_inserted,
            coverage_percent=coverage,
            sync_duration=duration,
            parity_percent=parity,
            error_count=error_count
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)
        return audit
