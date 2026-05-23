"""System-level endpoints for sync recovery status."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, model_validator

from app.services.recovery_service import RecoveryService
from app.services.sync_state_service import get_sync_state_service
from app.services.unicommerce_sync_orchestrator import get_unicommerce_sync_orchestrator

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
    """Return the global sync state for all critical entities."""
    return get_sync_state_service().get_system_status()


@router.post("/recover-sync")
def recover_sync(payload: Optional[RecoveryRequest] = None):
    """Trigger a manual recovery plan (Celery or asyncio fallback)."""
    payload = payload or RecoveryRequest()
    return RecoveryService().schedule_recovery(
        reason="manual",
        entities=payload.entities,
        from_date=payload.from_date,
        to_date=payload.to_date,
        force=payload.force,
    )


@router.get("/catch-up-status")
def get_catch_up_status() -> Dict[str, Any]:
    """Return per-entity gap information, scheduler state, and recovery progress.

    Useful for the frontend to show a "Data Health" banner and for ops
    to quickly diagnose whether catch-up is running.
    """
    sync_state_svc = get_sync_state_service()
    orchestrator = get_unicommerce_sync_orchestrator()

    now_utc = datetime.now(timezone.utc)

    # Per-entity gaps
    try:
        gaps: Dict[str, Optional[float]] = sync_state_svc.get_all_entity_gaps()
    except Exception as exc:
        gaps = {}

    # System-level status (recovery progress, healthy flag, etc.)
    try:
        system_status = sync_state_svc.get_system_status()
    except Exception:
        system_status = {}

    # Per-entity detail
    entity_detail: Dict[str, Any] = {}
    for entity, gap_hours in gaps.items():
        try:
            snapshot = sync_state_svc.get_state_snapshot(entity)
        except Exception:
            snapshot = {}
        entity_detail[entity] = {
            "gap_hours": round(gap_hours, 2) if gap_hours is not None else None,
            "never_synced": gap_hours is None,
            "status": snapshot.get("sync_status", "unknown"),
            "last_successful_sync": snapshot.get("last_successful_sync"),
            "recovery_mode": snapshot.get("recovery_mode"),
            "recovery_progress": (
                {
                    "completed": snapshot.get("recovery_completed_chunks", 0),
                    "total": snapshot.get("recovery_total_chunks", 0),
                    "current_chunk": snapshot.get("recovery_current_chunk"),
                }
                if snapshot.get("recovery_total_chunks")
                else None
            ),
        }

    # Scheduler liveness
    scheduler_task = orchestrator._scheduler_task
    scheduler_running = bool(scheduler_task and not scheduler_task.done())

    # Recovery mode active?
    catch_up_active = system_status.get("mode") == "recovery" or orchestrator.is_in_recovery_mode()

    # Estimate worst-case time to completion
    worst_gap_hours = max(
        (v for v in gaps.values() if v is not None), default=0.0
    )
    estimated_completion_minutes: Optional[float] = None
    if catch_up_active and worst_gap_hours > 0:
        # Very rough heuristic: ~2 min per day of gap
        estimated_completion_minutes = round((worst_gap_hours / 24.0) * 2.0, 1)

    return {
        "catch_up_active": catch_up_active,
        "scheduler_running": scheduler_running,
        "overall_healthy": bool(system_status.get("healthy", False)),
        "recovery_mode": system_status.get("mode", "normal"),
        "recovery_progress_pct": system_status.get("recovery_progress", 0),
        "sync_gap_days": system_status.get("sync_gap_days"),
        "last_successful_sync": system_status.get("last_successful_sync"),
        "estimated_completion_minutes": estimated_completion_minutes,
        "entities": entity_detail,
        "evaluated_at": now_utc.isoformat(),
    }


@router.post("/trigger-catch-up")
async def trigger_catch_up(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Manually trigger the startup catch-up logic.

    Runs the same gap-detection + backfill/incremental dispatch as the
    automatic startup handler.  Useful after a long outage or when the
    "Data Health" badge is red and you want immediate recovery without
    restarting the server.
    """
    orchestrator = get_unicommerce_sync_orchestrator()

    async def _run_catch_up() -> None:
        await orchestrator.startup_catch_up_sync()

    background_tasks.add_task(_run_catch_up)

    return {
        "success": True,
        "message": "Catch-up sync dispatched in background",
        "scheduler_running": bool(
            orchestrator._scheduler_task and not orchestrator._scheduler_task.done()
        ),
    }
