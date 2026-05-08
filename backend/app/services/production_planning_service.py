from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import ProductionPlanningHistory, ProductionPlanningReport


class ProductionPlanningService:
    REQUIRED_COLUMNS = {"sku", "cutting_plan", "cutting", "stitching", "finishing"}
    HISTORY_RETENTION_DAYS = 30

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _normalize_sku(value: Any) -> str:
        sku = str(value or "").strip()
        return sku.upper()

    @staticmethod
    def _normalize_style_code(value: Any) -> Optional[str]:
        style = str(value or "").strip()
        return style or None

    @staticmethod
    def _parse_non_negative_int(value: Any, field_name: str) -> int:
        if value is None:
            return 0
        text = str(value).strip()
        if text == "":
            return 0
        try:
            parsed = int(float(text))
        except (TypeError, ValueError):
            raise ValueError(f"{field_name} must be a number")
        if parsed < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return parsed

    def _cleanup_old_history(self) -> None:
        cutoff = datetime.utcnow() - timedelta(days=self.HISTORY_RETENTION_DAYS)
        (
            self.db.query(ProductionPlanningHistory)
            .filter(ProductionPlanningHistory.updated_at < cutoff)
            .delete(synchronize_session=False)
        )

    def _upsert_additive(
        self,
        *,
        sku: str,
        style_code: Optional[str],
        cutting_plan: int,
        cutting: int,
        stitching: int,
        finishing: int,
        source: str,
    ) -> str:
        sku_norm = self._normalize_sku(sku)
        if not sku_norm:
            raise ValueError("SKU is required")

        old = (
            self.db.query(ProductionPlanningReport)
            .filter(ProductionPlanningReport.sku == sku_norm)
            .with_for_update()
            .first()
        )

        op_type = "updated"
        if old is None:
            row = ProductionPlanningReport(
                sku=sku_norm,
                style_code=style_code,
                cutting_plan=cutting_plan,
                cutting=cutting,
                stitching=stitching,
                finishing=finishing,
            )
            self.db.add(row)
            self.db.flush()
            old_cutting_plan = 0
            old_cutting = 0
            old_stitching = 0
            old_finishing = 0
            new_cutting_plan = row.cutting_plan
            new_cutting = row.cutting
            new_stitching = row.stitching
            new_finishing = row.finishing
            op_type = "created"
        else:
            old_cutting_plan = int(old.cutting_plan or 0)
            old_cutting = int(old.cutting or 0)
            old_stitching = int(old.stitching or 0)
            old_finishing = int(old.finishing or 0)

            old.cutting_plan = old_cutting_plan + cutting_plan
            old.cutting = old_cutting + cutting
            old.stitching = old_stitching + stitching
            old.finishing = old_finishing + finishing
            if style_code:
                old.style_code = style_code

            new_cutting_plan = int(old.cutting_plan or 0)
            new_cutting = int(old.cutting or 0)
            new_stitching = int(old.stitching or 0)
            new_finishing = int(old.finishing or 0)

        self.db.add(
            ProductionPlanningHistory(
                sku=sku_norm,
                old_cutting_plan=old_cutting_plan,
                new_cutting_plan=new_cutting_plan,
                old_cutting=old_cutting,
                new_cutting=new_cutting,
                old_stitching=old_stitching,
                new_stitching=new_stitching,
                old_finishing=old_finishing,
                new_finishing=new_finishing,
                updated_quantity_difference=(cutting_plan + cutting + stitching + finishing),
                update_source=source,
            )
        )
        return op_type

    def upsert_manual(self, payload: dict[str, Any]) -> dict[str, Any]:
        sku = self._normalize_sku(payload.get("sku"))
        style_code = self._normalize_style_code(payload.get("style_code"))
        cutting_plan = self._parse_non_negative_int(payload.get("cutting_plan"), "cutting_plan")
        cutting = self._parse_non_negative_int(payload.get("cutting"), "cutting")
        stitching = self._parse_non_negative_int(payload.get("stitching"), "stitching")
        finishing = self._parse_non_negative_int(payload.get("finishing"), "finishing")

        if not sku:
            raise ValueError("SKU is required")

        self._cleanup_old_history()
        try:
            op_type = self._upsert_additive(
                sku=sku,
                style_code=style_code,
                cutting_plan=cutting_plan,
                cutting=cutting,
                stitching=stitching,
                finishing=finishing,
                source="MANUAL",
            )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            # Rare race on concurrent inserts; retry as update path.
            op_type = self._upsert_additive(
                sku=sku,
                style_code=style_code,
                cutting_plan=cutting_plan,
                cutting=cutting,
                stitching=stitching,
                finishing=finishing,
                source="MANUAL",
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        saved = self.db.query(ProductionPlanningReport).filter(ProductionPlanningReport.sku == sku).first()
        return {
            "success": True,
            "operation": op_type,
            "item": saved,
        }

    def upload_csv(self, file_bytes: bytes) -> dict[str, Any]:
        text = file_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV is empty")

        headers = [str(h or "").strip().lower() for h in reader.fieldnames]
        missing = [c for c in sorted(self.REQUIRED_COLUMNS) if c not in headers]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")

        duplicate_in_file: set[str] = set()
        seen_skus: set[str] = set()
        rows = list(reader)

        new_count = 0
        updated_count = 0
        failed_rows: list[dict[str, Any]] = []
        processed = 0

        self._cleanup_old_history()
        try:
            for idx, raw in enumerate(rows, start=2):
                try:
                    sku = self._normalize_sku(raw.get("sku"))
                    if not sku:
                        raise ValueError("SKU is required")
                    if sku in seen_skus:
                        duplicate_in_file.add(sku)
                        raise ValueError("Duplicate SKU found in CSV")
                    seen_skus.add(sku)

                    style_code = self._normalize_style_code(raw.get("style_code"))
                    cutting_plan = self._parse_non_negative_int(raw.get("cutting_plan"), "cutting_plan")
                    cutting = self._parse_non_negative_int(raw.get("cutting"), "cutting")
                    stitching = self._parse_non_negative_int(raw.get("stitching"), "stitching")
                    finishing = self._parse_non_negative_int(raw.get("finishing"), "finishing")

                    op_type = self._upsert_additive(
                        sku=sku,
                        style_code=style_code,
                        cutting_plan=cutting_plan,
                        cutting=cutting,
                        stitching=stitching,
                        finishing=finishing,
                        source="CSV",
                    )
                    processed += 1
                    if op_type == "created":
                        new_count += 1
                    else:
                        updated_count += 1
                except Exception as exc:
                    failed_rows.append(
                        {
                            "row_number": idx,
                            "sku": str(raw.get("sku") or "").strip(),
                            "error": str(exc),
                        }
                    )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return {
            "success": True,
            "total_rows_processed": processed,
            "new_skus_created": new_count,
            "existing_skus_updated": updated_count,
            "failed_rows_count": len(failed_rows),
            "failed_rows": failed_rows,
            "duplicate_skus_in_file": sorted(duplicate_in_file),
        }

    def list_rows(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        updated_from: Optional[date] = None,
        updated_to: Optional[date] = None,
    ) -> dict[str, Any]:
        q = self.db.query(ProductionPlanningReport)

        if search:
            term = f"%{search.strip()}%"
            q = q.filter(
                (ProductionPlanningReport.sku.ilike(term))
                | (ProductionPlanningReport.style_code.ilike(term))
            )

        if updated_from:
            from_dt = datetime.combine(updated_from, datetime.min.time())
            q = q.filter(ProductionPlanningReport.updated_at >= from_dt)
        if updated_to:
            to_dt = datetime.combine(updated_to + timedelta(days=1), datetime.min.time())
            q = q.filter(ProductionPlanningReport.updated_at < to_dt)

        total = q.count()
        safe_page_size = max(1, min(int(page_size), 200))
        total_pages = max(1, (total + safe_page_size - 1) // safe_page_size) if total else 1
        safe_page = min(max(1, int(page)), total_pages)
        items = (
            q.order_by(ProductionPlanningReport.updated_at.desc(), ProductionPlanningReport.id.desc())
            .offset((safe_page - 1) * safe_page_size)
            .limit(safe_page_size)
            .all()
        )
        return {
            "items": items,
            "page": safe_page,
            "page_size": safe_page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def list_history(self, sku: str, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        sku_norm = self._normalize_sku(sku)
        q = self.db.query(ProductionPlanningHistory).filter(ProductionPlanningHistory.sku == sku_norm)
        total = q.count()
        safe_page_size = max(1, min(int(page_size), 200))
        total_pages = max(1, (total + safe_page_size - 1) // safe_page_size) if total else 1
        safe_page = min(max(1, int(page)), total_pages)
        items = (
            q.order_by(ProductionPlanningHistory.updated_at.desc(), ProductionPlanningHistory.id.desc())
            .offset((safe_page - 1) * safe_page_size)
            .limit(safe_page_size)
            .all()
        )
        return {
            "items": items,
            "page": safe_page,
            "page_size": safe_page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def export_csv(self, *, search: Optional[str], updated_from: Optional[date], updated_to: Optional[date]) -> bytes:
        q = self.db.query(ProductionPlanningReport)
        if search:
            term = f"%{search.strip()}%"
            q = q.filter(
                (ProductionPlanningReport.sku.ilike(term))
                | (ProductionPlanningReport.style_code.ilike(term))
            )
        if updated_from:
            from_dt = datetime.combine(updated_from, datetime.min.time())
            q = q.filter(ProductionPlanningReport.updated_at >= from_dt)
        if updated_to:
            to_dt = datetime.combine(updated_to + timedelta(days=1), datetime.min.time())
            q = q.filter(ProductionPlanningReport.updated_at < to_dt)

        rows = q.order_by(ProductionPlanningReport.updated_at.desc(), ProductionPlanningReport.id.desc()).all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "sku",
                "style_code",
                "cutting_plan",
                "cutting",
                "stitching",
                "finishing",
                "updated_at",
                "created_at",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.sku,
                    row.style_code or "",
                    int(row.cutting_plan or 0),
                    int(row.cutting or 0),
                    int(row.stitching or 0),
                    int(row.finishing or 0),
                    row.updated_at.isoformat() if row.updated_at else "",
                    row.created_at.isoformat() if row.created_at else "",
                ]
            )
        return output.getvalue().encode("utf-8-sig")
