"""Celery tasks for recovery sync workflows."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import uuid4

from celery.exceptions import Retry
from celery.utils.log import get_task_logger

from app.core.config import settings
from app.core.redis import redis_client
from app.services.sync_state_service import get_sync_state_service
from app.services.unicommerce_sync_orchestrator import get_unicommerce_sync_orchestrator
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)


def _acquire_recovery_lock() -> str | None:
    if redis_client is None:
        return uuid4().hex
    token = uuid4().hex
    ttl_seconds = max(60, int(getattr(settings, "UNICOMMERCE_RECOVERY_LOCK_TTL_SECONDS", 1800)))
    try:
        acquired = redis_client.set("uc:recovery:lock", token, nx=True, ex=ttl_seconds)
        return token if acquired else None
    except Exception as exc:
        logger.warning(f"Recovery lock acquisition failed: {exc}")
        return None


def _release_recovery_lock(token: str | None) -> None:
    if redis_client is None or not token:
        return
    try:
        current = redis_client.get("uc:recovery:lock")
        if current == token:
            redis_client.delete("uc:recovery:lock")
    except Exception as exc:
        logger.warning(f"Recovery lock release failed: {exc}")


@celery_app.task(
    bind=True,
    name="app.workers.recovery_tasks.recovery_step_task",
    max_retries=max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_MAX_RETRIES", 3))),
)
def recovery_step_task(self, step: Dict[str, Any]) -> Dict[str, Any]:
    lock_token = _acquire_recovery_lock()
    if not lock_token:
        retry_delay = max(10, int(getattr(settings, "UNICOMMERCE_RECOVERY_RETRY_COOLDOWN_MINUTES", 5))) * 60
        raise self.retry(countdown=retry_delay)

    sync_state = get_sync_state_service()
    orchestrator = get_unicommerce_sync_orchestrator()

    from_dt = datetime.fromisoformat(step["from_date"])
    to_dt = datetime.fromisoformat(step["to_date"])
    entities = step.get("entities", [])
    chunk_label = step.get("label", "unknown")

    for entity in entities:
        sync_state.record_sync_start(entity, sync_mode="recovery", current_chunk=chunk_label)

    results: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    try:
        if "sale_orders" in entities:
            results["sale_orders"] = asyncio.run(
                orchestrator.sync_orders_window(from_dt, to_dt, sync_mode="recovery")
            )
        if "sales_returns" in entities:
            results["sales_returns"] = asyncio.run(
                orchestrator.sync_returns_window(from_dt, to_dt, sync_mode="recovery")
            )
        if "inventory_snapshot" in entities:
            results["inventory_snapshot"] = asyncio.run(
                orchestrator.sync_inventory(sync_mode="recovery")
            )

        for entity in entities:
            entity_result = results.get(entity, {})
            success = bool(entity_result.get("success", False))
            if not success:
                errors[entity] = str(entity_result.get("error") or entity_result.get("message") or "failed")

        for entity in entities:
            success = entity not in errors
            sync_state.advance_recovery_progress(
                entity,
                chunk_label=chunk_label,
                success=success,
                increment_completed=not bool(errors),
                completed_at=to_dt if success else None,
                error_message=errors.get(entity),
            )

        if errors:
            retry_minutes = max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_RETRY_COOLDOWN_MINUTES", 5)))
            retry_at = datetime.now(timezone.utc) + timedelta(minutes=retry_minutes)
            for entity in errors:
                sync_state.set_recovery_next_retry(entity, retry_at)
            raise self.retry(countdown=retry_minutes * 60)

        return {
            "success": True,
            "label": chunk_label,
            "entities": entities,
            "results": results,
        }
    except Exception as exc:
        if isinstance(exc, Retry):
            raise
        logger.error(f"Recovery step failed: {exc}")
        for entity in entities:
            sync_state.advance_recovery_progress(
                entity,
                chunk_label=chunk_label,
                success=False,
                error_message=str(exc),
            )
        raise
    finally:
        _release_recovery_lock(lock_token)
