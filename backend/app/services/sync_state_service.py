"""Persistence helpers for sync_state tracking."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.export_models import SyncLog
from app.db.session import SessionLocal
from app.db.sync_models import SyncState

logger = logging.getLogger(__name__)


CRITICAL_ENTITIES = [
    "sale_orders",
    "sales_returns",
    "inventory_snapshot",
]


def _naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _aware_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SyncStateService:
    """Tracks sync freshness and recovery progress in sync_state."""

    def _get_db(self) -> Session:
        return SessionLocal()

    def _ensure_state(self, db: Session, entity: str) -> SyncState:
        state = db.query(SyncState).filter(SyncState.entity == entity).first()
        if state is None:
            state = SyncState(entity=entity, sync_status="idle")
            db.add(state)
            db.commit()
            db.refresh(state)
        return state

    def _bootstrap_from_sync_logs(self, db: Session, state: SyncState) -> None:
        if state.last_successful_sync is not None:
            return

        latest = (
            db.query(SyncLog)
            .filter(SyncLog.entity == state.entity, SyncLog.status == "completed")
            .order_by(SyncLog.id.desc())
            .first()
        )
        if not latest:
            return

        completed = latest.completed_at or latest.started_at
        if completed:
            state.last_successful_sync = _naive_utc(completed)
            db.commit()

    def get_state_snapshot(self, entity: str) -> Dict[str, Any]:
        db = self._get_db()
        try:
            state = self._ensure_state(db, entity)
            self._bootstrap_from_sync_logs(db, state)
            return self._state_to_dict(state)
        finally:
            db.close()

    def update_state(self, entity: str, **fields: Any) -> Dict[str, Any]:
        db = self._get_db()
        try:
            state = self._ensure_state(db, entity)
            for key, value in fields.items():
                setattr(state, key, value)
            db.commit()
            db.refresh(state)
            return self._state_to_dict(state)
        finally:
            db.close()

    def record_sync_start(
        self,
        entity: str,
        *,
        sync_mode: str = "normal",
        current_chunk: Optional[str] = None,
    ) -> None:
        db = self._get_db()
        try:
            state = self._ensure_state(db, entity)
            if sync_mode == "recovery":
                state.sync_status = "recovery_running"
                if current_chunk:
                    state.recovery_current_chunk = current_chunk
            else:
                if state.sync_status not in {"recovery_running", "recovery_queued"}:
                    state.sync_status = "running"
            db.commit()
        finally:
            db.close()

    def record_sync_result(
        self,
        entity: str,
        *,
        success: bool,
        completed_at: Optional[datetime],
        duration_seconds: float,
        rows_synced: int,
        sync_mode: str = "normal",
        error_message: Optional[str] = None,
        full_sync: bool = False,
    ) -> None:
        db = self._get_db()
        try:
            state = self._ensure_state(db, entity)
            completed_at = _naive_utc(completed_at)
            state.sync_duration_seconds = float(duration_seconds or 0.0)
            state.rows_synced = int(rows_synced or 0)
            if success and completed_at:
                state.last_successful_sync = completed_at
                if full_sync:
                    state.last_full_sync = completed_at
                state.last_error = None
            elif not success and error_message:
                state.last_error = str(error_message)

            if sync_mode == "recovery":
                state.sync_status = "recovery_running" if success else "recovery_failed"
            elif state.sync_status not in {"recovery_running", "recovery_queued"}:
                state.sync_status = "idle" if success else "failed"

            db.commit()
        finally:
            db.close()

    def prepare_recovery(
        self,
        entity: str,
        *,
        mode: str,
        total_chunks: int,
    ) -> None:
        db = self._get_db()
        try:
            state = self._ensure_state(db, entity)
            state.sync_status = "recovery_queued"
            state.recovery_mode = mode
            state.recovery_total_chunks = int(total_chunks)
            state.recovery_completed_chunks = 0
            state.recovery_current_chunk = None
            state.recovery_started_at = datetime.utcnow()
            state.recovery_last_chunk_at = None
            state.recovery_retry_count = 0
            state.recovery_next_retry_at = None
            state.last_error = None
            db.commit()
        finally:
            db.close()

    def advance_recovery_progress(
        self,
        entity: str,
        *,
        chunk_label: str,
        success: bool,
        increment_completed: bool = True,
        completed_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
    ) -> None:
        db = self._get_db()
        try:
            state = self._ensure_state(db, entity)
            state.recovery_current_chunk = chunk_label
            state.recovery_last_chunk_at = datetime.utcnow()
            if success:
                if increment_completed:
                    state.recovery_completed_chunks = int(state.recovery_completed_chunks or 0) + 1
                state.last_error = None
            else:
                state.recovery_retry_count = int(state.recovery_retry_count or 0) + 1
                state.last_error = str(error_message or "recovery_failed")

            if completed_at and success:
                state.last_successful_sync = _naive_utc(completed_at)

            total_chunks = int(state.recovery_total_chunks or 0)
            if success and increment_completed and total_chunks and state.recovery_completed_chunks >= total_chunks:
                state.recovery_current_chunk = None
                state.sync_status = "idle"
                if state.recovery_mode in {"backfill", "deep"} and state.last_successful_sync:
                    state.last_full_sync = state.last_successful_sync
            else:
                state.sync_status = "recovery_running" if success else "recovery_failed"

            db.commit()
        finally:
            db.close()

    def set_recovery_next_retry(self, entity: str, retry_at: datetime) -> None:
        db = self._get_db()
        try:
            state = self._ensure_state(db, entity)
            state.recovery_next_retry_at = _naive_utc(retry_at)
            db.commit()
        finally:
            db.close()

    def get_all_entity_gaps(self) -> Dict[str, Optional[float]]:
        """Return gap_hours since last_successful_sync for each critical entity.

        Returns None for an entity that has never successfully synced.
        Bootstraps from sync_logs on first access so the value is always
        populated even before the first explicit sync_state write.
        """
        db = self._get_db()
        try:
            now_utc = datetime.now(timezone.utc)
            gaps: Dict[str, Optional[float]] = {}
            for entity in CRITICAL_ENTITIES:
                state = self._ensure_state(db, entity)
                self._bootstrap_from_sync_logs(db, state)
                if state.last_successful_sync is None:
                    gaps[entity] = None
                else:
                    last_sync = _aware_utc(state.last_successful_sync)
                    gaps[entity] = (now_utc - last_sync).total_seconds() / 3600.0
            return gaps
        finally:
            db.close()

    def mark_recovery_complete(self, entity: str) -> None:
        """Mark a recovery as fully complete for an entity — transitions to idle."""
        db = self._get_db()
        try:
            state = self._ensure_state(db, entity)
            state.sync_status = "idle"
            state.recovery_current_chunk = None
            db.commit()
        finally:
            db.close()

    def is_recovery_active(self, entities: Optional[Iterable[str]] = None) -> bool:
        db = self._get_db()
        try:
            query = db.query(SyncState)
            if entities:
                query = query.filter(SyncState.entity.in_(list(entities)))
            states = query.all()
            return any(state.sync_status in {"recovery_running", "recovery_queued"} for state in states)
        finally:
            db.close()

    def get_system_status(self) -> Dict[str, Any]:
        db = self._get_db()
        try:
            states = db.query(SyncState).filter(SyncState.entity.in_(CRITICAL_ENTITIES)).all()
            if not states:
                return {
                    "mode": "normal",
                    "last_successful_sync": None,
                    "sync_gap_days": None,
                    "recovery_progress": 0,
                    "current_chunk": None,
                    "healthy": False,
                    "entities": [],
                }

            now_utc = datetime.now(timezone.utc)
            gaps: List[float] = []
            total_chunks = 0
            completed_chunks = 0
            current_chunk = None
            recovery_active = False
            unhealthy = False

            entity_payloads = []
            for state in states:
                self._bootstrap_from_sync_logs(db, state)
                last_sync = _aware_utc(state.last_successful_sync)
                gap_days = None
                if last_sync:
                    gap_days = (now_utc - last_sync).total_seconds() / 86400.0
                    gaps.append(gap_days)

                total_chunks += int(state.recovery_total_chunks or 0)
                completed_chunks += int(state.recovery_completed_chunks or 0)
                if not current_chunk and state.recovery_current_chunk:
                    current_chunk = state.recovery_current_chunk
                if state.sync_status in {"recovery_running", "recovery_queued"}:
                    recovery_active = True
                if state.sync_status in {"failed", "recovery_failed"}:
                    unhealthy = True

                entity_payloads.append(self._state_to_dict(state))

            gap_days_value = round(max(gaps), 2) if gaps else None
            if gap_days_value is not None:
                min_gap_hours = max(1, int(settings.UNICOMMERCE_RECOVERY_MIN_GAP_HOURS))
                if gap_days_value * 24 > min_gap_hours:
                    unhealthy = True

            recovery_progress = 0
            if total_chunks:
                recovery_progress = int(round((completed_chunks / total_chunks) * 100))

            latest_sync = max((s.last_successful_sync for s in states if s.last_successful_sync), default=None)
            return {
                "mode": "recovery" if recovery_active else "normal",
                "last_successful_sync": latest_sync.isoformat() if latest_sync else None,
                "sync_gap_days": gap_days_value,
                "recovery_progress": recovery_progress,
                "current_chunk": current_chunk,
                "healthy": not unhealthy,
                "entities": entity_payloads,
            }
        finally:
            db.close()

    def _state_to_dict(self, state: SyncState) -> Dict[str, Any]:
        return {
            "entity": state.entity,
            "last_successful_sync": state.last_successful_sync.isoformat() if state.last_successful_sync else None,
            "last_full_sync": state.last_full_sync.isoformat() if state.last_full_sync else None,
            "sync_status": state.sync_status,
            "sync_duration_seconds": float(state.sync_duration_seconds or 0.0),
            "rows_synced": int(state.rows_synced or 0),
            "recovery_mode": state.recovery_mode,
            "recovery_total_chunks": int(state.recovery_total_chunks or 0),
            "recovery_completed_chunks": int(state.recovery_completed_chunks or 0),
            "recovery_current_chunk": state.recovery_current_chunk,
            "recovery_started_at": state.recovery_started_at.isoformat() if state.recovery_started_at else None,
            "recovery_last_chunk_at": state.recovery_last_chunk_at.isoformat() if state.recovery_last_chunk_at else None,
            "recovery_retry_count": int(state.recovery_retry_count or 0),
            "recovery_next_retry_at": state.recovery_next_retry_at.isoformat() if state.recovery_next_retry_at else None,
            "last_error": state.last_error,
        }


_sync_state_service: Optional[SyncStateService] = None


def get_sync_state_service() -> SyncStateService:
    global _sync_state_service
    if _sync_state_service is None:
        _sync_state_service = SyncStateService()
    return _sync_state_service
