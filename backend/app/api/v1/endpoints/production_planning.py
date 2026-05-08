from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.production_planning import ProductionPlanningManualEntry
from app.services.production_planning_service import ProductionPlanningService

router = APIRouter()


@router.post("/upload-csv")
async def upload_production_planning_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    payload = await file.read()
    service = ProductionPlanningService(db)
    try:
        return service.upload_csv(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CSV upload failed: {exc}")


@router.post("/manual-entry")
def upsert_production_planning_manual(
    body: ProductionPlanningManualEntry,
    db: Session = Depends(get_db),
):
    service = ProductionPlanningService(db)
    try:
        return service.upsert_manual(body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Manual upsert failed: {exc}")


@router.get("")
def list_production_planning_rows(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: Optional[str] = Query(None),
    updated_from: Optional[date] = Query(None),
    updated_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    service = ProductionPlanningService(db)
    return service.list_rows(
        page=page,
        page_size=page_size,
        search=search,
        updated_from=updated_from,
        updated_to=updated_to,
    )


@router.get("/{sku}/history")
def get_production_planning_history(
    sku: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    service = ProductionPlanningService(db)
    return service.list_history(sku=sku, page=page, page_size=page_size)


@router.get("/export/csv")
def export_production_planning_csv(
    search: Optional[str] = Query(None),
    updated_from: Optional[date] = Query(None),
    updated_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    service = ProductionPlanningService(db)
    body = service.export_csv(search=search, updated_from=updated_from, updated_to=updated_to)
    filename = "production-planning-report.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
