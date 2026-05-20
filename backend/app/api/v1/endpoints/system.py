"""System-level endpoints for sync recovery status."""

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, model_validator

from app.services.recovery_service import RecoveryService
from app.services.sync_state_service import get_sync_state_service

router = APIRouter()


class RecoveryRequest(BaseModel):
    entities: Optional[List[str]] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    force: bool = False

    @model_validator(mode="after")
    def validate_date_range(self) -> "RecoveryRequest":
        if bool(self.from_date) != bool(self.to_date):
            raise ValueError("from_date and to_date must be provided together")
        return self


@router.get("/sync-status")
def get_system_sync_status():
    return get_sync_state_service().get_system_status()


@router.post("/recover-sync")
def recover_sync(payload: Optional[RecoveryRequest] = None):
    payload = payload or RecoveryRequest()
    return RecoveryService().schedule_recovery(
        reason="manual",
        entities=payload.entities,
        from_date=payload.from_date,
        to_date=payload.to_date,
        force=payload.force,
    )
