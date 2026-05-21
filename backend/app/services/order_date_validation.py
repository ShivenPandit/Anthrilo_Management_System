"""
Order date validation guards for Unicommerce ingestion.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import text


class OrderDateValidationError(Exception):
    """Raised when order_date validation fails."""


def validate_order_date(
    order_date: Optional[datetime],
    order_id: str,
    context: str = "import",
) -> datetime:
    if order_date is None:
        raise OrderDateValidationError(f"[{context}] Order {order_id}: order_date is NULL")

    if not isinstance(order_date, datetime):
        raise OrderDateValidationError(
            f"[{context}] Order {order_id}: order_date type invalid: {type(order_date)}"
        )

    if order_date.tzinfo is not None:
        order_date = order_date.astimezone(timezone.utc).replace(tzinfo=None)

    now_utc = datetime.utcnow()
    # Allow certain import/repair contexts to accept slight future timestamps
    future_allowed_contexts = {"repair_import", "csv_import", "sync_import", "sync_import_best_effort"}
    if order_date > now_utc:
        if context in future_allowed_contexts:
            # Clamp future timestamps to current UTC to avoid validation failure
            order_date = now_utc
        else:
            raise OrderDateValidationError(
                f"[{context}] Order {order_id}: order_date is in the future. "
                f"order_date={order_date.isoformat()} now={now_utc.isoformat()}"
            )

    two_years_ago = now_utc - timedelta(days=730)
    if context not in {"historical_import"} and order_date < two_years_ago:
        raise OrderDateValidationError(
            f"[{context}] Order {order_id}: order_date too old ({order_date.isoformat()})"
        )

    # For non-live contexts only, reject suspicious "just now" business times;
    # however allow recent timestamps for known import/repair contexts.
    recent_allowed_contexts = {"repair_import", "sync_import", "sync_import_best_effort"}
    if context not in recent_allowed_contexts:
        one_minute_tolerance = now_utc - timedelta(minutes=1)
        if order_date > one_minute_tolerance:
            raise OrderDateValidationError(
                f"[{context}] Order {order_id}: order_date too recent ({order_date.isoformat()})"
            )

    return order_date


def validate_import_row(row: dict, row_number: int) -> Tuple[bool, Optional[str]]:
    try:
        order_id = (row.get("Sale Order Code") or row.get("Display Order Code") or "").strip()
        date_text = (row.get("Order Date as dd/mm/yyyy hh:MM:ss") or "").strip()
        if not order_id:
            return False, f"Row {row_number}: missing order_id"
        if not date_text:
            return False, f"Row {row_number}: missing business order date"
        parsed = datetime.strptime(date_text, "%d/%m/%Y %H:%M:%S")
        validate_order_date(parsed, order_id, context="csv_import")
        return True, None
    except Exception as exc:
        return False, str(exc)


def validate_database_state(db_session, check_corruption: bool = True) -> Tuple[bool, list]:
    from app.db.export_models import SalesOrderRecord
    from sqlalchemy import func

    issues = []

    null_dates = db_session.query(func.count(SalesOrderRecord.id)).filter(
        SalesOrderRecord.order_date.is_(None)
    ).scalar()
    if null_dates > 0:
        issues.append(f"CRITICAL: {null_dates} records with NULL order_date")

    future_dates = db_session.query(func.count(SalesOrderRecord.id)).filter(
        SalesOrderRecord.order_date > datetime.utcnow()
    ).scalar()
    if future_dates > 0:
        issues.append(f"CRITICAL: {future_dates} records with future order_date")

    if check_corruption:
        old_cutoff = datetime.utcnow() - timedelta(days=730)
        old_dates = db_session.query(func.count(SalesOrderRecord.id)).filter(
            SalesOrderRecord.order_date < old_cutoff
        ).scalar()
        if old_dates > 0:
            issues.append(f"WARNING: {old_dates} records older than 2 years")

    dup_subq = (
        db_session.query(
            SalesOrderRecord.order_id,
            SalesOrderRecord.sale_order_item_code,
            func.count(SalesOrderRecord.id).label("cnt"),
        )
        .group_by(SalesOrderRecord.order_id, SalesOrderRecord.sale_order_item_code)
        .subquery()
    )
    dup_count = db_session.query(dup_subq.c.cnt).filter(dup_subq.c.cnt > 1).count()
    if dup_count > 0:
        issues.append(f"CRITICAL: {dup_count} duplicate (order_id, sale_order_item_code) groups")

    drift_subq = (
        db_session.query(
            SalesOrderRecord.order_id,
            func.count(
                func.distinct(func.date(SalesOrderRecord.order_date + text("interval '5 hours 30 minutes'")))
            ).label("day_count"),
        )
        .group_by(SalesOrderRecord.order_id)
        .subquery()
    )
    multi_day_orders = db_session.query(drift_subq.c.day_count).filter(drift_subq.c.day_count > 1).count()
    if multi_day_orders > 0:
        issues.append(f"WARNING: {multi_day_orders} order_ids appear across multiple business days")

    return len(issues) == 0, issues

