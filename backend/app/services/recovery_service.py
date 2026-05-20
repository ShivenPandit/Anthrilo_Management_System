"""Recovery orchestration for DB-first sync catch-up."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

from app.core.config import settings
from app.core.redis import redis_client
from app.services.sync_state_service import get_sync_state_service
from app.services.unicommerce import get_unicommerce_service
from app.utils.timezone_utils import IST, normalize_date_range_ist

logger = logging.getLogger(__name__)


RECOVERY_ENTITIES = [
    "sale_orders",
    "sales_returns",
    "inventory_snapshot",
]


@dataclass
class RecoveryStep:
    label: str
    from_date: datetime
    to_date: datetime
    entities: List[str]
    mode: str
    priority: str


class RecoveryService:
    """Plans and enqueues recovery tasks for stale DB-first data."""

    def __init__(self) -> None:
        self.uc_service = get_unicommerce_service()
        self.sync_state = get_sync_state_service()

    def schedule_startup_recovery(self) -> Dict[str, Any]:
        return self.schedule_recovery(reason="startup")

    def schedule_recovery(
        self,
        *,
        reason: str,
        entities: Optional[Sequence[str]] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        if not bool(getattr(settings, "UNICOMMERCE_RECOVERY_ENABLE", True)):
            return {"scheduled": False, "reason": "disabled"}

        if bool(from_date) != bool(to_date):
            return {"scheduled": False, "reason": "invalid_date_range"}

        chosen_entities = [
            entity for entity in (entities or RECOVERY_ENTITIES)
            if entity in RECOVERY_ENTITIES
        ]
        if not chosen_entities:
            return {"scheduled": False, "reason": "no_entities"}

        if not force and self.sync_state.is_recovery_active(chosen_entities):
            return {"scheduled": False, "reason": "already_running"}

        if not force and not self._passes_cooldown(chosen_entities):
            return {"scheduled": False, "reason": "cooldown_active"}

        lock = self._acquire_schedule_lock()
        if not lock:
            return {"scheduled": False, "reason": "lock_busy"}

        try:
            plan = self._build_recovery_plan(
                entities=chosen_entities,
                from_date=from_date,
                to_date=to_date,
            )
            if not plan["steps"]:
                return {"scheduled": False, "reason": "no_gap"}

            self._persist_plan(plan)
            self._enqueue_steps(plan)
            return {
                "scheduled": True,
                "recovery_id": plan["recovery_id"],
                "mode": plan["mode"],
                "step_count": len(plan["steps"]),
                "entities": plan["entities"],
            }
        finally:
            self._release_schedule_lock(lock)

    def _passes_cooldown(self, entities: Iterable[str]) -> bool:
        cooldown_minutes = max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_COOLDOWN_MINUTES", 15)))
        now_utc = datetime.now(timezone.utc)
        for entity in entities:
            snapshot = self.sync_state.get_state_snapshot(entity)
            started = snapshot.get("recovery_started_at")
            if started:
                started_dt = self._parse_utc(started)
                if (now_utc - started_dt).total_seconds() < cooldown_minutes * 60:
                    return False
            retry_at = snapshot.get("recovery_next_retry_at")
            if retry_at:
                retry_dt = self._parse_utc(retry_at)
                if retry_dt > now_utc:
                    return False
        return True

    def _build_recovery_plan(
        self,
        *,
        entities: Sequence[str],
        from_date: Optional[str],
        to_date: Optional[str],
    ) -> Dict[str, Any]:
        recovery_id = uuid4().hex
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc.astimezone(IST)

        steps: List[RecoveryStep] = []
        modes: List[str] = []

        manual_range = None
        if from_date and to_date:
            manual_range = self._normalize_date_range(from_date, to_date)

        include_sales_returns = any(entity in {"sale_orders", "sales_returns"} for entity in entities)
        include_inventory = "inventory_snapshot" in entities

        sales_return_entities = [
            entity for entity in entities
            if entity in {"sale_orders", "sales_returns"}
        ]

        if include_sales_returns:
            sales_mode, sales_steps = self._build_sales_returns_steps(
                entities=sales_return_entities,
                now_utc=now_utc,
                now_ist=now_ist,
                manual_range=manual_range,
            )
            steps.extend(sales_steps)
            modes.append(sales_mode)

        if include_inventory and self._inventory_stale(now_utc):
            inventory_step = RecoveryStep(
                label="inventory_snapshot",
                from_date=now_utc,
                to_date=now_utc,
                entities=["inventory_snapshot"],
                mode="inventory_refresh",
                priority="inventory",
            )
            steps.append(inventory_step)
            modes.append("inventory_refresh")

        mode = "recovery" if not modes else "+".join(sorted(set(modes)))

        total_chunks = self._count_chunks_by_entity(steps)
        return {
            "recovery_id": recovery_id,
            "mode": mode,
            "entities": list(entities),
            "steps": [self._step_to_payload(step) for step in steps],
            "chunks": total_chunks,
        }

    def _build_sales_returns_steps(
        self,
        *,
        entities: Sequence[str],
        now_utc: datetime,
        now_ist: datetime,
        manual_range: Optional[Tuple[datetime, datetime]],
    ) -> Tuple[str, List[RecoveryStep]]:
        step_entities = [
            entity for entity in entities
            if entity in {"sale_orders", "sales_returns"}
        ]
        if not step_entities:
            return "incremental", []

        if manual_range:
            mode = "manual"
            return mode, self._chunk_range_steps(
                manual_range[0],
                manual_range[1],
                entities=step_entities,
                mode=mode,
                priority="manual",
            )

        last_sync_dt = None
        for entity in ("sale_orders", "sales_returns"):
            last_sync = self.sync_state.get_state_snapshot(entity).get("last_successful_sync")
            if not last_sync:
                continue
            parsed = self._parse_utc(last_sync)
            if last_sync_dt is None or parsed < last_sync_dt:
                last_sync_dt = parsed

        if last_sync_dt is None:
            fallback_days = max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_DEFAULT_LOOKBACK_DAYS", 30)))
            last_sync_dt = (now_utc - timedelta(days=fallback_days)).replace(tzinfo=timezone.utc)

        gap_hours = max(0.0, (now_utc - last_sync_dt).total_seconds() / 3600.0)
        min_gap_hours = max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_MIN_GAP_HOURS", 12)))
        if gap_hours < min_gap_hours:
            return "incremental", []

        if gap_hours < 24:
            lookback_hours = max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_INCREMENTAL_LOOKBACK_HOURS", 6)))
            from_dt = (last_sync_dt - timedelta(hours=lookback_hours)).astimezone(timezone.utc)
            to_dt = now_utc
            return "incremental", [
                RecoveryStep(
                    label=self._format_chunk_label(from_dt, to_dt),
                    from_date=from_dt,
                    to_date=to_dt,
                    entities=step_entities,
                    mode="incremental",
                    priority="incremental",
                )
            ]

        gap_days = gap_hours / 24.0
        deep_threshold = max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_DEEP_THRESHOLD_DAYS", 30)))
        chunk_days = max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_BACKFILL_CHUNK_DAYS", 1)))
        mode = "backfill"
        if gap_days > deep_threshold:
            chunk_days = max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_DEEP_CHUNK_DAYS", 3)))
            mode = "deep"

        today_from, today_to = self.uc_service.get_today_range()
        yesterday_from, yesterday_to = self.uc_service.get_yesterday_range()

        steps: List[RecoveryStep] = [
            RecoveryStep(
                label=self._format_chunk_label(today_from, today_to),
                from_date=today_from,
                to_date=today_to,
                entities=step_entities,
                mode=mode,
                priority="today",
            ),
            RecoveryStep(
                label=self._format_chunk_label(yesterday_from, yesterday_to),
                from_date=yesterday_from,
                to_date=yesterday_to,
                entities=step_entities,
                mode=mode,
                priority="yesterday",
            ),
        ]

        last_sync_day = last_sync_dt.astimezone(IST).date()
        historical_start_day = last_sync_day + timedelta(days=1)
        historical_end_day = now_ist.date() - timedelta(days=2)
        if historical_start_day <= historical_end_day:
            steps.extend(
                self._chunk_ist_days(
                    historical_start_day,
                    historical_end_day,
                    chunk_days=chunk_days,
                    entities=step_entities,
                    mode=mode,
                    priority="backfill",
                    newest_first=True,
                )
            )

        return mode, steps

    def _chunk_ist_days(
        self,
        start_day: date,
        end_day: date,
        *,
        chunk_days: int,
        entities: Sequence[str],
        mode: str,
        priority: str,
        newest_first: bool,
    ) -> List[RecoveryStep]:
        chunks: List[RecoveryStep] = []
        cursor = start_day
        while cursor <= end_day:
            chunk_end = min(cursor + timedelta(days=chunk_days - 1), end_day)
            start_utc, end_exclusive, _ = normalize_date_range_ist(cursor.isoformat(), chunk_end.isoformat())
            end_utc = end_exclusive - timedelta(seconds=1)
            chunks.append(
                RecoveryStep(
                    label=self._format_chunk_label(start_utc, end_utc),
                    from_date=start_utc,
                    to_date=end_utc,
                    entities=list(entities),
                    mode=mode,
                    priority=priority,
                )
            )
            cursor = chunk_end + timedelta(days=1)

        if newest_first:
            chunks.sort(key=lambda step: step.from_date, reverse=True)
        return chunks

    def _chunk_range_steps(
        self,
        from_dt: datetime,
        to_dt: datetime,
        *,
        entities: Sequence[str],
        mode: str,
        priority: str,
    ) -> List[RecoveryStep]:
        chunk_days = max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_BACKFILL_CHUNK_DAYS", 1)))
        if mode == "deep":
            chunk_days = max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_DEEP_CHUNK_DAYS", 3)))

        start_day = from_dt.astimezone(IST).date()
        end_day = to_dt.astimezone(IST).date()
        return self._chunk_ist_days(
            start_day,
            end_day,
            chunk_days=chunk_days,
            entities=entities,
            mode=mode,
            priority=priority,
            newest_first=False,
        )

    def _normalize_date_range(self, from_date: str, to_date: str) -> Tuple[datetime, datetime]:
        start_utc, end_exclusive, _ = normalize_date_range_ist(from_date, to_date)
        return start_utc, end_exclusive - timedelta(seconds=1)

    def _inventory_stale(self, now_utc: datetime) -> bool:
        snapshot = self.sync_state.get_state_snapshot("inventory_snapshot")
        last_sync = snapshot.get("last_successful_sync")
        if not last_sync:
            return True
        last_sync_dt = self._parse_utc(last_sync)
        gap_hours = (now_utc - last_sync_dt).total_seconds() / 3600.0
        stale_hours = max(1, int(settings.UNICOMMERCE_SYNC_INVENTORY_INTERVAL_HOURS))
        return gap_hours >= stale_hours

    @staticmethod
    def _parse_utc(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _count_chunks_by_entity(self, steps: Sequence[RecoveryStep]) -> Dict[str, int]:
        counts = {entity: 0 for entity in RECOVERY_ENTITIES}
        for step in steps:
            for entity in step.entities:
                counts[entity] = counts.get(entity, 0) + 1
        return counts

    def _persist_plan(self, plan: Dict[str, Any]) -> None:
        chunk_counts = plan.get("chunks", {})
        for entity, total in chunk_counts.items():
            if entity not in RECOVERY_ENTITIES:
                continue
            self.sync_state.prepare_recovery(
                entity,
                mode=plan.get("mode", "recovery"),
                total_chunks=int(total or 0),
            )

    def _enqueue_steps(self, plan: Dict[str, Any]) -> None:
        from app.workers.recovery_tasks import recovery_step_task

        delay_seconds = max(0, int(getattr(settings, "UNICOMMERCE_RECOVERY_CHUNK_DELAY_SECONDS", 5)))
        for idx, step in enumerate(plan["steps"], start=1):
            payload = dict(step)
            payload["recovery_id"] = plan["recovery_id"]
            payload["step_index"] = idx
            payload["step_total"] = len(plan["steps"])
            recovery_step_task.apply_async(
                kwargs={"step": payload},
                countdown=delay_seconds * (idx - 1),
                queue="recovery",
            )

    def _acquire_schedule_lock(self) -> Optional[str]:
        lock_key = "uc:recovery:schedule"
        token = uuid4().hex
        ttl_seconds = max(60, int(getattr(settings, "UNICOMMERCE_RECOVERY_LOCK_TTL_SECONDS", 1800)))
        if redis_client is None:
            return token
        try:
            acquired = redis_client.set(lock_key, token, nx=True, ex=ttl_seconds)
            return token if acquired else None
        except Exception as exc:
            logger.warning(f"Recovery schedule lock failed: {exc}")
            return None

    def _release_schedule_lock(self, token: Optional[str]) -> None:
        if not token or redis_client is None:
            return
        lock_key = "uc:recovery:schedule"
        try:
            current = redis_client.get(lock_key)
            if current == token:
                redis_client.delete(lock_key)
        except Exception as exc:
            logger.warning(f"Recovery schedule unlock failed: {exc}")

    @staticmethod
    def _format_chunk_label(from_dt: datetime, to_dt: datetime) -> str:
        return f"{from_dt.date().isoformat()} -> {to_dt.date().isoformat()}"

    @staticmethod
    def _step_to_payload(step: RecoveryStep) -> Dict[str, Any]:
        return {
            "label": step.label,
            "from_date": step.from_date.isoformat(),
            "to_date": step.to_date.isoformat(),
            "entities": list(step.entities),
            "mode": step.mode,
            "priority": step.priority,
        }
