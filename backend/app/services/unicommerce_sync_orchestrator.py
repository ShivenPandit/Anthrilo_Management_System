"""Sync orchestration service for export-first Unicommerce ingestion."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import and_, distinct, func, or_
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.redis import redis_client
from app.db.session import SessionLocal
from app.db.export_models import (
    ExportJob,
    ExportRow,
    FacilityInventorySnapshot,
    SalesOrderRecord,
    SalesReturnRecord,
    SyncLog,
)
from app.services.cache_service import CacheService
from app.services.sync_state_service import get_sync_state_service
from app.services.websocket_manager import ws_manager
from app.services.unicommerce_data_service import get_unicommerce_data_service
from app.services.unicommerce import get_unicommerce_service
from app.services.parity_validator import ParityValidator

logger = logging.getLogger(__name__)


@dataclass
class _LockHandle:
    mode: str
    name: str
    token: str


class UnicommerceSyncOrchestrator:
    """Coordinates incremental, realtime-triggered, and backfill sync profiles."""

    _process_locks: Dict[str, asyncio.Lock] = {}

    def __init__(self) -> None:
        self.uc_service = get_unicommerce_service()
        self._scheduler_task: Optional[asyncio.Task] = None
        self._scheduler_stop_event: Optional[asyncio.Event] = None
        self._scheduler_next_run_at: Dict[str, datetime] = {}
        self._scheduler_bootstrapped = False

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _chunk_range(
        self,
        start: datetime,
        end: datetime,
        chunk_days: int,
    ) -> List[Tuple[datetime, datetime]]:
        cursor = self._ensure_utc(start)
        end_utc = self._ensure_utc(end)
        chunks: List[Tuple[datetime, datetime]] = []

        while cursor <= end_utc:
            chunk_end = min(cursor + timedelta(days=max(1, int(chunk_days))) - timedelta(seconds=1), end_utc)
            chunks.append((cursor, chunk_end))
            cursor = chunk_end + timedelta(seconds=1)

        return chunks

    async def _acquire_lock(self, lock_name: str, ttl_seconds: Optional[int] = None) -> Optional[_LockHandle]:
        ttl = int(ttl_seconds or settings.UNICOMMERCE_SYNC_LOCK_TTL_SECONDS)
        token = secrets.token_hex(16)

        redis_key = f"uc:sync:lock:{lock_name}"
        if redis_client is not None:
            try:
                acquired = redis_client.set(redis_key, token, nx=True, ex=ttl)
                if acquired:
                    return _LockHandle(mode="redis", name=redis_key, token=token)
            except Exception as exc:
                logger.warning(f"Redis lock acquisition failed for {lock_name}: {exc}")

        process_lock = self._process_locks.setdefault(lock_name, asyncio.Lock())
        if process_lock.locked():
            return None

        await process_lock.acquire()
        return _LockHandle(mode="process", name=lock_name, token=token)

    async def _release_lock(self, handle: Optional[_LockHandle]) -> None:
        if handle is None:
            return

        if handle.mode == "redis":
            if redis_client is not None:
                try:
                    current_token = redis_client.get(handle.name)
                    if current_token == handle.token:
                        redis_client.delete(handle.name)
                except Exception as exc:
                    logger.warning(f"Redis lock release failed for {handle.name}: {exc}")
            return

        process_lock = self._process_locks.get(handle.name)
        if process_lock is not None and process_lock.locked():
            process_lock.release()

    def _discover_recent_skus(self, lookback_days: int = 30, limit: Optional[int] = 5000) -> List[str]:
        db = SessionLocal()
        try:
            since = self._utcnow() - timedelta(days=max(1, int(lookback_days)))
            query = (
                db.query(SalesOrderRecord.sku)
                .filter(
                    SalesOrderRecord.sku.isnot(None),
                    SalesOrderRecord.sku != "",
                    SalesOrderRecord.updated_at >= since,
                )
                .group_by(SalesOrderRecord.sku)
            )

            if limit is not None and int(limit) > 0:
                query = query.limit(max(1, int(limit)))

            rows = query.all()
            return [str(row[0]).strip() for row in rows if row and row[0]]
        finally:
            db.close()

    def _discover_item_master_skus(self, limit: Optional[int] = 5000) -> List[str]:
        db = SessionLocal()
        try:
            item_master_job = (
                db.query(ExportJob)
                .filter(
                    ExportJob.export_type == "item_master",
                    ExportJob.status == "completed",
                )
                .order_by(ExportJob.completed_at.desc(), ExportJob.id.desc())
                .first()
            )

            if not item_master_job:
                return []

            row_payloads = (
                db.query(ExportRow.payload)
                .filter(ExportRow.export_job_id == item_master_job.id)
                .order_by(ExportRow.row_number.asc())
                .all()
            )

            max_items: Optional[int]
            if limit is None or int(limit) <= 0:
                max_items = None
            else:
                max_items = max(1, int(limit))

            seen: set[str] = set()
            skus: List[str] = []
            for wrapped in row_payloads:
                row = dict(wrapped[0] or {})
                sku = str(
                    row.get("Product Code")
                    or row.get("SKU Code")
                    or row.get("skuCode")
                    or row.get("itemTypeSKU")
                    or row.get("sku")
                    or ""
                ).strip()
                if not sku or sku in seen:
                    continue
                seen.add(sku)
                skus.append(sku)
                if max_items is not None and len(skus) >= max_items:
                    break

            return skus
        finally:
            db.close()

    def _set_repair_progress(self, progress_key: Optional[str], payload: Dict[str, Any]) -> None:
        if not progress_key:
            return
        try:
            CacheService.set(progress_key, payload, ttl=60 * 60 * 6)
        except Exception as exc:
            logger.warning(f"Failed to persist repair progress key={progress_key}: {exc}")

    def _create_repair_sync_log(
        self,
        from_date: datetime,
        to_date: datetime,
        entities: List[str],
        truncate_period: bool,
        truncate_inventory: bool,
        dry_run: bool,
    ) -> Optional[int]:
        db = SessionLocal()
        try:
            log = SyncLog(
                sync_type="repair_rebuild",
                entity="repair_rebuild",
                status="running",
                started_at=self._utcnow().replace(tzinfo=None),
                details={
                    "from_date": from_date.isoformat(),
                    "to_date": to_date.isoformat(),
                    "entities": entities,
                    "truncate_period": bool(truncate_period),
                    "truncate_inventory": bool(truncate_inventory),
                    "dry_run": bool(dry_run),
                },
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            return int(log.id)
        except Exception as exc:
            db.rollback()
            logger.warning(f"Failed to create repair sync log row: {exc}")
            return None
        finally:
            db.close()

    def _finalize_repair_sync_log(
        self,
        log_id: Optional[int],
        success: bool,
        details: Dict[str, Any],
        error_message: Optional[str] = None,
    ) -> None:
        if not log_id:
            return
        db = SessionLocal()
        try:
            status = "completed" if success else "failed"
            db.query(SyncLog).filter(SyncLog.id == log_id).update(
                {
                    "status": status,
                    "completed_at": self._utcnow().replace(tzinfo=None),
                    "processed_count": int(success),
                    "failed_count": 0 if success else 1,
                    "error_message": error_message,
                    "details": details,
                }
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning(f"Failed to finalize repair sync log row={log_id}: {exc}")
        finally:
            db.close()

    def _truncate_repair_targets(
        self,
        from_date: datetime,
        to_date: datetime,
        truncate_sales: bool,
        truncate_returns: bool,
        truncate_inventory: bool,
        dry_run: bool,
    ) -> Dict[str, Any]:
        start = self._ensure_utc(from_date)
        end = self._ensure_utc(to_date)

        db = SessionLocal()
        try:
            sales_query = db.query(SalesOrderRecord).filter(
                or_(
                    and_(
                        SalesOrderRecord.order_date.isnot(None),
                        SalesOrderRecord.order_date >= start,
                        SalesOrderRecord.order_date <= end,
                    ),
                    and_(
                        SalesOrderRecord.order_date.is_(None),
                        SalesOrderRecord.created_at >= start,
                        SalesOrderRecord.created_at <= end,
                    ),
                )
            )
            returns_query = db.query(SalesReturnRecord).filter(
                or_(
                    and_(
                        SalesReturnRecord.created_at >= start,
                        SalesReturnRecord.created_at <= end,
                    ),
                    and_(
                        SalesReturnRecord.updated_at >= start,
                        SalesReturnRecord.updated_at <= end,
                    ),
                )
            )
            inventory_query = db.query(FacilityInventorySnapshot).filter(
                FacilityInventorySnapshot.snapshot_date >= start,
                FacilityInventorySnapshot.snapshot_date <= end,
            )

            deleted_sales = int(sales_query.count()) if truncate_sales else 0
            deleted_returns = int(returns_query.count()) if truncate_returns else 0
            deleted_inventory = int(inventory_query.count()) if truncate_inventory else 0

            if not dry_run:
                if truncate_sales:
                    sales_query.delete(synchronize_session=False)
                if truncate_returns:
                    returns_query.delete(synchronize_session=False)
                if truncate_inventory:
                    inventory_query.delete(synchronize_session=False)
                db.commit()

            return {
                "success": True,
                "dry_run": bool(dry_run),
                "deleted_sales_orders": deleted_sales,
                "deleted_sales_returns": deleted_returns,
                "deleted_inventory_snapshots": deleted_inventory,
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
            }
        except Exception as exc:
            db.rollback()
            return {
                "success": False,
                "dry_run": bool(dry_run),
                "deleted_sales_orders": 0,
                "deleted_sales_returns": 0,
                "deleted_inventory_snapshots": 0,
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "error": str(exc),
            }
        finally:
            db.close()

    def _scheduler_plan(self) -> Dict[str, Dict[str, Any]]:
        return {
            "sales": {
                "sync_entity": "sale_orders",
                "interval_hours": max(1, int(settings.UNICOMMERCE_SYNC_SALES_INTERVAL_HOURS)),
            },
            "returns": {
                "sync_entity": "sales_returns",
                "interval_hours": max(1, int(settings.UNICOMMERCE_SYNC_RETURNS_INTERVAL_HOURS)),
            },
            "inventory": {
                "sync_entity": "inventory_snapshot",
                "interval_hours": max(1, int(settings.UNICOMMERCE_SYNC_INVENTORY_INTERVAL_HOURS)),
            },
            "inventory_parity": {
                "sync_entity": "inventory_snapshot_parity",
                "interval_hours": max(1, int(getattr(settings, "UNICOMMERCE_PARITY_VALIDATION_INTERVAL_HOURS", 24))),
            },
        }

    def _get_last_completed_sync_time(self, entity: str) -> Optional[datetime]:
        db = SessionLocal()
        try:
            latest = (
                db.query(SyncLog)
                .filter(SyncLog.entity == entity, SyncLog.status == "completed")
                .order_by(SyncLog.id.desc())
                .first()
            )
            if not latest:
                return None

            completed = latest.completed_at or latest.started_at
            return self._ensure_utc(completed) if completed else None
        finally:
            db.close()

    def _bootstrap_scheduler_state(self) -> None:
        if self._scheduler_bootstrapped:
            return

        now_utc = self._utcnow()
        for job_key, cfg in self._scheduler_plan().items():
            interval = timedelta(hours=int(cfg["interval_hours"]))
            last_completed = self._get_last_completed_sync_time(str(cfg["sync_entity"]))

            if last_completed is None:
                self._scheduler_next_run_at[job_key] = now_utc
                continue

            next_due = last_completed + interval
            self._scheduler_next_run_at[job_key] = next_due if next_due > now_utc else now_utc

        self._scheduler_bootstrapped = True

        timezone_name = str(settings.UNICOMMERCE_SYNC_TIMEZONE or "UTC").strip() or "UTC"
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = timezone.utc

        local_schedule = {
            key: value.astimezone(tz).isoformat()
            for key, value in self._scheduler_next_run_at.items()
        }
        logger.info(f"Unicommerce scheduler bootstrapped ({timezone_name}): {local_schedule}")

    def _schedule_next_run(self, job_key: str, success: bool, interval_hours: int) -> datetime:
        now_utc = self._utcnow()
        if success:
            # Accelerate cadence while recovery is active so we pick up fresh
            # data faster, then revert to the normal configured interval once caught up.
            if self.is_in_recovery_mode():
                recovery_interval_minutes = max(
                    10, int(getattr(settings, "UNICOMMERCE_SYNC_RECOVERY_CADENCE_MINUTES", 30))
                )
                next_due = now_utc + timedelta(minutes=recovery_interval_minutes)
                logger.debug(
                    f"Scheduler '{job_key}': recovery mode active, next run in "
                    f"{recovery_interval_minutes}min"
                )
            else:
                next_due = now_utc + timedelta(hours=max(1, int(interval_hours)))
        else:
            retry_minutes = max(1, int(settings.UNICOMMERCE_SYNC_RETRY_MINUTES))
            next_due = now_utc + timedelta(minutes=retry_minutes)

        self._scheduler_next_run_at[job_key] = next_due
        return next_due

    def is_in_recovery_mode(self) -> bool:
        """Return True when any critical entity is actively recovering."""
        try:
            sync_state = get_sync_state_service()
            return sync_state.is_recovery_active()
        except Exception:
            return False

    async def _run_sales_scheduler_job(self) -> Dict[str, Any]:
        lookback_days = max(
            1,
            int(
                settings.UNICOMMERCE_SYNC_SALES_LOOKBACK_DAYS
                or settings.UNICOMMERCE_SYNC_LOOKBACK_DAYS
            ),
        )
        now_utc = self._utcnow()
        from_date = now_utc - timedelta(days=lookback_days)
        return await self.sync_orders_window(from_date, now_utc)

    async def _run_returns_scheduler_job(self) -> Dict[str, Any]:
        lookback_days = max(
            1,
            int(
                settings.UNICOMMERCE_SYNC_RETURNS_LOOKBACK_DAYS
                or settings.UNICOMMERCE_SYNC_LOOKBACK_DAYS
            ),
        )
        now_utc = self._utcnow()
        from_date = now_utc - timedelta(days=lookback_days)
        return await self.sync_returns_window(from_date, now_utc)

    async def _run_inventory_scheduler_job(self) -> Dict[str, Any]:
        facility = str(settings.UNICOMMERCE_SYNC_INVENTORY_FACILITY_CODE or "anthrilo").strip() or "anthrilo"
        
        lock = await self._acquire_lock("inventory")
        if not lock:
            return {
                "success": False,
                "message": "Inventory sync lock is already held",
            }
            
        sync_state = get_sync_state_service()
        sync_state.record_sync_start("inventory_snapshot", sync_mode="normal")
        start_time = time.perf_counter()
        try:
            # Check retry safety limit
            retry_key = f"uc:sync:retries:inventory_snapshot:{facility}"
            if redis_client:
                retries = int(redis_client.get(retry_key) or 0)
                if retries >= 3:
                    logger.error(f"Inventory sync blocked: exceeded max retries (3) for facility {facility}")
                    return {"success": False, "error": "Max retries exceeded"}

            from app.services.sync_inventory_snapshot import fetch_and_sync_inventory
            res = await fetch_and_sync_inventory(facility)
            
            if res.get("success"):
                if redis_client:
                    redis_client.delete(retry_key)  # Reset on success
            else:
                if redis_client:
                    redis_client.incr(retry_key)
                    redis_client.expire(retry_key, 3600)  # 1 hour cooldown window

            duration = time.perf_counter() - start_time
            sync_state.record_sync_result(
                "inventory_snapshot",
                success=bool(res.get("success")),
                completed_at=self._utcnow(),
                duration_seconds=duration,
                rows_synced=int(res.get("inserted", 0) or res.get("fetched", 0) or 0),
                sync_mode="normal",
                error_message=res.get("error"),
            )
            return res
        finally:
            await self._release_lock(lock)

    async def _run_inventory_parity_scheduler_job(self) -> Dict[str, Any]:
        return await self.run_inventory_parity_check()

    async def run_due_scheduler_jobs(self) -> Dict[str, Any]:
        self._bootstrap_scheduler_state()

        now_utc = self._utcnow()
        schedule = self._scheduler_plan()
        jobs: Dict[str, Dict[str, Any]] = {}
        executed = 0

        for job_key, cfg in schedule.items():
            next_due = self._scheduler_next_run_at.get(job_key, now_utc)
            if now_utc < next_due:
                jobs[job_key] = {
                    "success": True,
                    "skipped": True,
                    "next_due_at": next_due.isoformat(),
                    "reason": "not_due",
                }
                continue

            executed += 1
            try:
                if job_key == "sales":
                    result = await self._run_sales_scheduler_job()
                elif job_key == "returns":
                    result = await self._run_returns_scheduler_job()
                elif job_key == "inventory_parity":
                    result = await self._run_inventory_parity_scheduler_job()
                else:
                    result = await self._run_inventory_scheduler_job()
            except Exception as exc:
                logger.error(f"Scheduled sync job '{job_key}' failed: {exc}", exc_info=True)
                result = {
                    "success": False,
                    "error": str(exc),
                }

            success = bool(result.get("success"))
            next_run = self._schedule_next_run(
                job_key,
                success=success,
                interval_hours=int(cfg["interval_hours"]),
            )

            jobs[job_key] = {
                **result,
                "skipped": False,
                "next_due_at": next_run.isoformat(),
                "interval_hours": int(cfg["interval_hours"]),
            }

        ran_jobs = [item for item in jobs.values() if not item.get("skipped")]
        return {
            "success": all(bool(item.get("success")) for item in ran_jobs) if ran_jobs else True,
            "executed_jobs": executed,
            "jobs": jobs,
            "evaluated_at": now_utc.isoformat(),
        }

    async def sync_orders_window(
        self,
        from_date: datetime,
        to_date: datetime,
        *,
        sync_mode: str = "normal",
    ) -> Dict[str, Any]:
        lock = await self._acquire_lock("orders")
        if not lock:
            return {
                "success": False,
                "message": "Order sync lock is already held",
                "from_date": self._ensure_utc(from_date).isoformat(),
                "to_date": self._ensure_utc(to_date).isoformat(),
            }

        sync_state = get_sync_state_service()
        sync_state.record_sync_start("sale_orders", sync_mode=sync_mode)
        start_time = time.perf_counter()
        try:
            result = await self.uc_service.fetch_orders_via_export(
                self._ensure_utc(from_date),
                self._ensure_utc(to_date),
            )
            success = bool(result.get("successful"))
            duration = time.perf_counter() - start_time
            rows_synced = int(result.get("normalized_rows", 0) or 0)
            sync_state.record_sync_result(
                "sale_orders",
                success=success,
                completed_at=self._ensure_utc(to_date),
                duration_seconds=duration,
                rows_synced=rows_synced,
                sync_mode=sync_mode,
                error_message=result.get("error"),
            )
            return {
                "success": success,
                "from_date": self._ensure_utc(from_date).isoformat(),
                "to_date": self._ensure_utc(to_date).isoformat(),
                "total_records": int(result.get("totalRecords", 0) or 0),
                "archived_rows": int(result.get("archived_rows", 0) or 0),
                "normalized_rows": rows_synced,
                "total_time": float(result.get("total_time", 0) or 0),
                "error": result.get("error"),
            }
        except Exception as exc:
            duration = time.perf_counter() - start_time
            sync_state.record_sync_result(
                "sale_orders",
                success=False,
                completed_at=self._ensure_utc(to_date),
                duration_seconds=duration,
                rows_synced=0,
                sync_mode=sync_mode,
                error_message=str(exc),
            )
            raise
        finally:
            await self._release_lock(lock)

    async def sync_returns_window(
        self,
        from_date: datetime,
        to_date: datetime,
        *,
        sync_mode: str = "normal",
    ) -> Dict[str, Any]:
        lock = await self._acquire_lock("returns")
        if not lock:
            return {
                "success": False,
                "message": "Returns sync lock is already held",
                "from_date": self._ensure_utc(from_date).isoformat(),
                "to_date": self._ensure_utc(to_date).isoformat(),
            }

        sync_state = get_sync_state_service()
        sync_state.record_sync_start("sales_returns", sync_mode=sync_mode)
        start_time = time.perf_counter()
        try:
            result = await self.uc_service.fetch_returns_via_export(
                self._ensure_utc(from_date),
                self._ensure_utc(to_date),
            )
            success = bool(result.get("successful"))
            duration = time.perf_counter() - start_time
            rows_synced = int(result.get("normalized_rows", 0) or 0)
            sync_state.record_sync_result(
                "sales_returns",
                success=success,
                completed_at=self._ensure_utc(to_date),
                duration_seconds=duration,
                rows_synced=rows_synced,
                sync_mode=sync_mode,
                error_message=result.get("error"),
            )
            return {
                "success": success,
                "from_date": self._ensure_utc(from_date).isoformat(),
                "to_date": self._ensure_utc(to_date).isoformat(),
                "total_items": int(result.get("total_items", 0) or 0),
                "archived_rows": int(result.get("archived_rows", 0) or 0),
                "normalized_rows": rows_synced,
                "total_time": float(result.get("total_time", 0) or 0),
                "error": result.get("error"),
            }
        except Exception as exc:
            duration = time.perf_counter() - start_time
            sync_state.record_sync_result(
                "sales_returns",
                success=False,
                completed_at=self._ensure_utc(to_date),
                duration_seconds=duration,
                rows_synced=0,
                sync_mode=sync_mode,
                error_message=str(exc),
            )
            raise
        finally:
            await self._release_lock(lock)

    async def sync_item_master(self) -> Dict[str, Any]:
        lock = await self._acquire_lock("item_master")
        if not lock:
            return {
                "success": False,
                "message": "Item master sync lock is already held",
            }

        try:
            result = await self.uc_service.get_bundle_sku_data()
            summary = result.get("summary", {}) if isinstance(result, dict) else {}
            return {
                "success": bool(result.get("success")) if isinstance(result, dict) else False,
                "total_bundles": int(summary.get("total_bundles", 0) or 0),
                "archived_rows": int(result.get("archived_rows", 0) or 0),
                "error": result.get("error") if isinstance(result, dict) else "Unknown response",
            }
        finally:
            await self._release_lock(lock)

    async def sync_inventory(
        self,
        skus: Optional[List[str]] = None,
        facility_code: str = "anthrilo",
        full_discovery: bool = False,
        discovery_limit: Optional[int] = None,
        *,
        sync_mode: str = "normal",
    ) -> Dict[str, Any]:
        lock = await self._acquire_lock("inventory")
        if not lock:
            return {
                "success": False,
                "message": "Inventory sync lock is already held",
            }

        sync_state = get_sync_state_service()
        sync_state.record_sync_start("inventory_snapshot", sync_mode=sync_mode)
        start_time = time.perf_counter()
        try:
            clean_skus = [str(sku).strip() for sku in (skus or []) if str(sku).strip()]
            if not clean_skus:
                configured_limit = max(1, int(discovery_limit or settings.UNICOMMERCE_SYNC_DISCOVERY_SKU_LIMIT))
                effective_limit: Optional[int] = None if full_discovery else configured_limit

                item_master_skus = self._discover_item_master_skus(limit=effective_limit)
                recent_skus = self._discover_recent_skus(
                    lookback_days=max(7, int(settings.UNICOMMERCE_SYNC_LOOKBACK_DAYS * 7)),
                    limit=effective_limit,
                )

                clean_skus = []
                seen: set[str] = set()
                for sku in item_master_skus + recent_skus:
                    normalized = str(sku).strip()
                    if not normalized or normalized in seen:
                        continue
                    seen.add(normalized)
                    clean_skus.append(normalized)
                    if effective_limit is not None and len(clean_skus) >= effective_limit:
                        break

            if not clean_skus:
                duration = time.perf_counter() - start_time
                sync_state.record_sync_result(
                    "inventory_snapshot",
                    success=True,
                    completed_at=self._utcnow(),
                    duration_seconds=duration,
                    rows_synced=0,
                    sync_mode=sync_mode,
                )
                return {
                    "success": True,
                    "message": "No SKUs available for inventory sync",
                    "requested_skus": 0,
                    "fetched_skus": 0,
                }

            snapshots = await self.uc_service.get_inventory_snapshot(clean_skus, facility_code=facility_code)
            success = True
            duration = time.perf_counter() - start_time
            rows_synced = len(snapshots or {})
            sync_state.record_sync_result(
                "inventory_snapshot",
                success=success,
                completed_at=self._utcnow(),
                duration_seconds=duration,
                rows_synced=rows_synced,
                sync_mode=sync_mode,
            )
            return {
                "success": True,
                "requested_skus": len(clean_skus),
                "fetched_skus": rows_synced,
                "facility_code": facility_code,
                "full_discovery": bool(full_discovery),
            }
        except Exception as exc:
            duration = time.perf_counter() - start_time
            sync_state.record_sync_result(
                "inventory_snapshot",
                success=False,
                completed_at=self._utcnow(),
                duration_seconds=duration,
                rows_synced=0,
                sync_mode=sync_mode,
                error_message=str(exc),
            )
            raise
        finally:
            await self._release_lock(lock)

    async def run_inventory_parity_check(self) -> Dict[str, Any]:
        """Compare the DB inventory snapshot against a fresh live export and cache the result."""
        facility = str(settings.UNICOMMERCE_SYNC_INVENTORY_FACILITY_CODE or "anthrilo").strip() or "anthrilo"
        try:
            parity_results = await ParityValidator.validate_inventory_parity(facility)
            CacheService.set("system:parity_health", parity_results, ttl=86400)
            return {
                "success": bool(parity_results.get("healthy", False)),
                "entity": "inventory_snapshot",
                "facility_code": facility,
                **parity_results,
            }
        except Exception as exc:
            logger.error(f"Inventory parity validation failed: {exc}", exc_info=True)
            failure = {
                "success": False,
                "entity": "inventory_snapshot",
                "facility_code": facility,
                "healthy": False,
                "error": str(exc),
            }
            CacheService.set("system:parity_health", failure, ttl=3600)
            return failure

    async def run_incremental_sync(self, lookback_days: Optional[int] = None) -> Dict[str, Any]:
        days = int(lookback_days or settings.UNICOMMERCE_SYNC_LOOKBACK_DAYS)
        safe_days = max(1, days)
        now_utc = self._utcnow()

        # Use IST business-day boundaries (not rolling UTC hours) so daily parity
        # for dates like 26/27/28 remains stable after manual sync.
        ist = ZoneInfo("Asia/Kolkata")
        now_ist = now_utc.astimezone(ist)
        start_day_ist = now_ist.date() - timedelta(days=safe_days)
        from_date = datetime.combine(start_day_ist, datetime.min.time(), tzinfo=ist).astimezone(timezone.utc)

        orders = await self.sync_orders_window(from_date, now_utc)
        returns = await self.sync_returns_window(from_date, now_utc)
        inventory = await self.sync_inventory()

        # --- Data Parity Validation & Auto Recovery ---
        db = SessionLocal()
        parity_results = {}
        try:
            parity_results = ParityValidator.validate_recent_parity(db, days_back=safe_days)
            
            # Cache for API to avoid synchronous heavy queries
            CacheService.set("system:parity_health", parity_results, ttl=86400)
            
            # Record audit log
            total_fetched = int((orders.get("total_records") or 0) + (returns.get("total_items") or 0))
            total_inserted = int((orders.get("normalized_rows") or 0) + (returns.get("normalized_rows") or 0))
            ParityValidator.record_sync_audit(
                db=db,
                entity="incremental_sync",
                rows_fetched=total_fetched,
                rows_inserted=total_inserted,
                duration=0.0, 
            )
            
            if not parity_results.get("healthy", True):
                window_key = f"uc:sync:auto_recover:{start_day_ist.isoformat()}"
                retry_count = int(CacheService.get(window_key) or 0)
                
                if retry_count < 3:
                    logger.warning(f"Parity mismatch detected: {parity_results}. Triggering automatic recovery (Attempt {retry_count + 1}/3).")
                    CacheService.set(window_key, retry_count + 1, ttl=86400)
                    await self.run_backfill(
                        from_date=from_date - timedelta(days=2), # deeper backfill
                        to_date=now_utc,
                        include_inventory=False,
                    )
                else:
                    logger.error(f"Auto-recovery aborted: Max retries (3) reached for window {window_key}. System overload protection active.")
        except Exception as e:
            logger.error(f"Failed to run parity validation: {e}")
        finally:
            db.close()

        return {
            "success": bool(orders.get("success")) and bool(returns.get("success")) and bool(inventory.get("success")),
            "profile": "incremental",
            "from_date": from_date.isoformat(),
            "to_date": now_utc.isoformat(),
            "parity": parity_results,
            "orders": orders,
            "returns": returns,
            "inventory": inventory,
        }

    async def run_realtime_trigger_sync(self, hours: int = 6) -> Dict[str, Any]:
        now_utc = self._utcnow()
        from_date = now_utc - timedelta(hours=max(1, int(hours)))

        orders = await self.sync_orders_window(from_date, now_utc)
        returns = await self.sync_returns_window(from_date, now_utc)

        return {
            "success": bool(orders.get("success")) and bool(returns.get("success")),
            "profile": "realtime_trigger",
            "from_date": from_date.isoformat(),
            "to_date": now_utc.isoformat(),
            "orders": orders,
            "returns": returns,
        }

    async def run_backfill(
        self,
        from_date: datetime,
        to_date: datetime,
        chunk_days: Optional[int] = None,
        include_orders: bool = True,
        include_returns: bool = True,
        include_inventory: bool = True,
        full_inventory_discovery: bool = False,
        inventory_discovery_limit: Optional[int] = None,
        inventory_facility_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        start = self._ensure_utc(from_date)
        end = self._ensure_utc(to_date)
        chunks = self._chunk_range(start, end, int(chunk_days or settings.UNICOMMERCE_SYNC_BACKFILL_CHUNK_DAYS))

        chunk_results: List[Dict[str, Any]] = []
        total_orders = 0
        total_returns = 0

        for chunk_start, chunk_end in chunks:
            orders = None
            if include_orders:
                orders = await self.sync_orders_window(chunk_start, chunk_end)
            returns = None
            if include_returns:
                returns = await self.sync_returns_window(chunk_start, chunk_end)

            if orders is not None:
                total_orders += int(orders.get("total_records", 0) or 0)
            if returns is not None:
                total_returns += int(returns.get("total_items", 0) or 0)

            chunk_results.append(
                {
                    "from_date": chunk_start.isoformat(),
                    "to_date": chunk_end.isoformat(),
                    "orders": orders,
                    "returns": returns,
                }
            )

        inventory = None
        if include_inventory:
            inventory = await self.sync_inventory(
                facility_code=(
                    str(inventory_facility_code or settings.UNICOMMERCE_SYNC_INVENTORY_FACILITY_CODE or "anthrilo").strip()
                    or "anthrilo"
                ),
                full_discovery=full_inventory_discovery,
                discovery_limit=inventory_discovery_limit,
            )

        success = True
        if include_orders:
            success = success and all(bool((chunk.get("orders") or {}).get("success")) for chunk in chunk_results)
        if include_returns:
            success = success and all(
                bool((chunk.get("returns") or {}).get("success"))
                for chunk in chunk_results
            )
        if inventory is not None:
            success = success and bool(inventory.get("success"))

        return {
            "success": success,
            "profile": "full_backfill",
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
            "chunk_days": int(chunk_days or settings.UNICOMMERCE_SYNC_BACKFILL_CHUNK_DAYS),
            "chunk_count": len(chunks),
            "include_orders": bool(include_orders),
            "include_returns": bool(include_returns),
            "include_inventory": bool(include_inventory),
            "total_orders": total_orders,
            "total_returns": total_returns,
            "inventory": inventory,
            "chunks": chunk_results,
        }

    def _truncate_window_data(
        self,
        from_date: datetime,
        to_date: datetime,
        truncate_orders: bool,
        truncate_returns: bool,
        truncate_inventory: bool,
        inventory_facility_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        start = self._ensure_utc(from_date)
        end = self._ensure_utc(to_date)

        db = SessionLocal()
        try:
            deleted_orders = 0
            deleted_returns = 0
            deleted_inventory = 0

            if truncate_orders:
                deleted_orders = (
                    db.query(SalesOrderRecord)
                    .filter(
                        or_(
                            and_(
                                SalesOrderRecord.order_date.isnot(None),
                                SalesOrderRecord.order_date >= start,
                                SalesOrderRecord.order_date <= end,
                            ),
                            and_(
                                SalesOrderRecord.order_date.is_(None),
                                SalesOrderRecord.created_at >= start,
                                SalesOrderRecord.created_at <= end,
                            ),
                        )
                    )
                    .delete(synchronize_session=False)
                )

            if truncate_returns:
                deleted_returns = (
                    db.query(SalesReturnRecord)
                    .filter(
                        or_(
                            and_(
                                SalesReturnRecord.created_at >= start,
                                SalesReturnRecord.created_at <= end,
                            ),
                            and_(
                                SalesReturnRecord.updated_at >= start,
                                SalesReturnRecord.updated_at <= end,
                            ),
                        )
                    )
                    .delete(synchronize_session=False)
                )

            if truncate_inventory:
                inventory_query = db.query(FacilityInventorySnapshot)
                facility = str(inventory_facility_code or "").strip()
                if facility:
                    inventory_query = inventory_query.filter(FacilityInventorySnapshot.facility_code == facility)
                deleted_inventory = inventory_query.delete(synchronize_session=False)

            db.commit()
            return {
                "success": True,
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "deleted_orders": int(deleted_orders),
                "deleted_returns": int(deleted_returns),
                "deleted_inventory": int(deleted_inventory),
            }
        except Exception as exc:
            db.rollback()
            return {
                "success": False,
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "deleted_orders": 0,
                "deleted_returns": 0,
                "deleted_inventory": 0,
                "error": str(exc),
            }
        finally:
            db.close()

    async def run_repair_rebuild(
        self,
        from_date: datetime,
        to_date: datetime,
        entities: Optional[List[str]] = None,
        truncate_period: bool = False,
        truncate_inventory: bool = False,
        full_inventory_discovery: bool = False,
        inventory_discovery_limit: Optional[int] = None,
        inventory_facility_code: str = "anthrilo",
        dry_run: bool = False,
        progress_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        started_at = time.perf_counter()
        start = self._ensure_utc(from_date)
        end = self._ensure_utc(to_date)

        if end < start:
            return {
                "success": False,
                "error": "to_date cannot be earlier than from_date",
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
            }

        selected = {
            (token or "").strip().lower()
            for token in (entities or ["sales", "returns", "inventory"])
            if str(token or "").strip()
        }

        include_orders = bool(selected & {"sales", "sale_orders", "orders"})
        include_returns = bool(selected & {"returns", "sales_returns", "return_gst"})
        include_inventory = bool(selected & {"inventory", "inventory_snapshot", "snapshots"})

        if not (include_orders or include_returns or include_inventory):
            return {
                "success": False,
                "error": "No valid entities selected. Use sales, returns, inventory",
                "entities": sorted(selected),
            }

        selected_entities = [
            entity
            for entity, enabled in (
                ("sales", include_orders),
                ("returns", include_returns),
                ("inventory", include_inventory),
            )
            if enabled
        ]
        lock = await self._acquire_lock("repair_rebuild")
        if not lock:
            return {
                "success": False,
                "profile": "repair_rebuild",
                "error": "Repair rebuild lock is already held",
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
            }

        log_id = self._create_repair_sync_log(
            from_date=start,
            to_date=end,
            entities=selected_entities,
            truncate_period=truncate_period,
            truncate_inventory=truncate_inventory,
            dry_run=dry_run,
        )
        entity_status: Dict[str, Dict[str, Any]] = {}
        truncate_result = {
            "success": True,
            "skipped": True,
            "dry_run": bool(dry_run),
            "deleted_sales_orders": 0,
            "deleted_sales_returns": 0,
            "deleted_inventory_snapshots": 0,
        }

        self._set_repair_progress(
            progress_key,
            {
                "status": "running",
                "phase": "started",
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "entities": selected_entities,
            },
        )

        try:
            if truncate_period or truncate_inventory:
                self._set_repair_progress(
                    progress_key,
                    {
                        "status": "running",
                        "phase": "truncate",
                        "from_date": start.isoformat(),
                        "to_date": end.isoformat(),
                        "entities": selected_entities,
                    },
                )
                truncate_result = self._truncate_repair_targets(
                    from_date=start,
                    to_date=end,
                    truncate_sales=bool(truncate_period and include_orders),
                    truncate_returns=bool(truncate_period and include_returns),
                    truncate_inventory=bool(truncate_inventory and include_inventory),
                    dry_run=dry_run,
                )
                truncate_result["skipped"] = False
                if not truncate_result.get("success"):
                    duration = round(time.perf_counter() - started_at, 3)
                    response = {
                        "success": False,
                        "profile": "repair_rebuild",
                        "from_date": start.isoformat(),
                        "to_date": end.isoformat(),
                        "sales": {"status": "skipped"},
                        "returns": {"status": "skipped"},
                        "inventory": {"status": "skipped"},
                        "truncate_result": truncate_result,
                        "duration": duration,
                        "dry_run": bool(dry_run),
                    }
                    self._finalize_repair_sync_log(
                        log_id,
                        success=False,
                        details=response,
                        error_message=str(truncate_result.get("error") or "truncate_failed"),
                    )
                    self._set_repair_progress(progress_key, {"status": "failed", "phase": "truncate", **response})
                    return response

            if dry_run:
                for entity in ("sales", "returns", "inventory"):
                    if entity in selected_entities:
                        entity_status[entity] = {"status": "dry_run_skipped", "success": True}
                    else:
                        entity_status[entity] = {"status": "not_selected", "success": True}
            else:
                if include_orders:
                    self._set_repair_progress(progress_key, {"status": "running", "phase": "sales", "entity": "sales"})
                    sales_result = await self.sync_orders_window(start, end)
                    entity_status["sales"] = {
                        "status": "completed" if sales_result.get("success") else "failed",
                        **sales_result,
                    }
                else:
                    entity_status["sales"] = {"status": "not_selected", "success": True}

                if include_returns:
                    self._set_repair_progress(progress_key, {"status": "running", "phase": "returns", "entity": "returns"})
                    returns_result = await self.sync_returns_window(start, end)
                    entity_status["returns"] = {
                        "status": "completed" if returns_result.get("success") else "failed",
                        **returns_result,
                    }
                else:
                    entity_status["returns"] = {"status": "not_selected", "success": True}

                if include_inventory:
                    self._set_repair_progress(
                        progress_key,
                        {"status": "running", "phase": "inventory", "entity": "inventory"},
                    )
                    inventory_result = await self.sync_inventory(
                        facility_code=(str(inventory_facility_code or "anthrilo").strip() or "anthrilo"),
                        full_discovery=bool(full_inventory_discovery),
                        discovery_limit=inventory_discovery_limit,
                    )
                    entity_status["inventory"] = {
                        "status": "completed" if inventory_result.get("success") else "failed",
                        **inventory_result,
                    }
                else:
                    entity_status["inventory"] = {"status": "not_selected", "success": True}

                # Invalidate report caches and notify listeners only after actual writes.
                CacheService.invalidate_all_uc_cache()
                await ws_manager.broadcast(
                    "all",
                    {
                        "type": "repair_rebuild_completed",
                        "data": {
                            "from_date": start.isoformat(),
                            "to_date": end.isoformat(),
                            "entities": selected_entities,
                        },
                    },
                )

            duration = round(time.perf_counter() - started_at, 3)
            success = all(bool((entity_status.get(entity) or {}).get("success", False)) for entity in ("sales", "returns", "inventory"))
            response = {
                "success": success,
                "profile": "repair_rebuild",
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "sales": entity_status.get("sales", {"status": "unknown", "success": False}),
                "returns": entity_status.get("returns", {"status": "unknown", "success": False}),
                "inventory": entity_status.get("inventory", {"status": "unknown", "success": False}),
                "truncate_period": bool(truncate_period),
                "truncate_inventory": bool(truncate_inventory),
                "truncate_result": truncate_result,
                "dry_run": bool(dry_run),
                "duration": duration,
            }
            self._finalize_repair_sync_log(log_id, success=success, details=response)
            self._set_repair_progress(
                progress_key,
                {
                    "status": "completed" if success else "failed",
                    "phase": "completed",
                    **response,
                },
            )
            return response
        except Exception as exc:
            duration = round(time.perf_counter() - started_at, 3)
            failure_response = {
                "success": False,
                "profile": "repair_rebuild",
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "error": str(exc),
                "duration": duration,
                "dry_run": bool(dry_run),
            }
            self._finalize_repair_sync_log(log_id, success=False, details=failure_response, error_message=str(exc))
            self._set_repair_progress(progress_key, {"status": "failed", "phase": "error", **failure_response})
            logger.error(f"Repair rebuild failed: {exc}", exc_info=True)
            return failure_response
        finally:
            await self._release_lock(lock)

    async def run_backfill_windows(
        self,
        windows: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        now_utc = self._utcnow()
        window_list = sorted({int(w) for w in (windows or [7, 30, 90, 365]) if int(w) > 0})

        results: List[Dict[str, Any]] = []
        for days in window_list:
            start = now_utc - timedelta(days=days)
            result = await self.run_backfill(
                from_date=start,
                to_date=now_utc,
                include_returns=True,
                include_inventory=False,
            )
            result["window_days"] = days
            results.append(result)

        overall_success = all(bool(result.get("success")) for result in results)
        return {
            "success": overall_success,
            "windows": results,
        }

    async def run_profile(
        self,
        profile: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        profile_norm = (profile or "incremental").strip().lower()

        if profile_norm == "incremental":
            return await self.run_incremental_sync()

        if profile_norm == "realtime_trigger":
            return await self.run_realtime_trigger_sync()

        if profile_norm == "full_backfill":
            if from_date is None or to_date is None:
                return {
                    "success": False,
                    "error": "from_date and to_date are required for full_backfill profile",
                }
            return await self.run_backfill(from_date=from_date, to_date=to_date)

        return {
            "success": False,
            "error": "Unknown profile. Use incremental | realtime_trigger | full_backfill",
        }

    def _entity_max_lag_minutes(self, entity: str) -> int:
        retry_minutes = max(0, int(settings.UNICOMMERCE_SYNC_RETRY_MINUTES))
        entity_norm = str(entity or "").strip().lower()

        if entity_norm == "sale_orders":
            return max(1, int(settings.UNICOMMERCE_SYNC_SALES_INTERVAL_HOURS) * 60 + retry_minutes)

        if entity_norm == "sales_returns":
            return max(1, int(settings.UNICOMMERCE_SYNC_RETURNS_INTERVAL_HOURS) * 60 + retry_minutes)

        if entity_norm == "inventory_snapshot":
            return max(1, int(settings.UNICOMMERCE_SYNC_INVENTORY_INTERVAL_HOURS) * 60 + retry_minutes)

        return max(1, int(settings.UNICOMMERCE_SYNC_MAX_LAG_MINUTES))

    def get_sync_health(self) -> Dict[str, Any]:
        now_utc = self._utcnow()
        default_max_lag = int(settings.UNICOMMERCE_SYNC_MAX_LAG_MINUTES)

        db = SessionLocal()
        try:
            entities = [
                "sale_orders",
                "sales_returns",
                "inventory_snapshot",
                "bundle_sku_catalog",
                "sale_orders_fabric",
            ]

            entity_health: List[Dict[str, Any]] = []
            for entity in entities:
                entity_target_lag = self._entity_max_lag_minutes(entity)
                latest = (
                    db.query(SyncLog)
                    .filter(SyncLog.entity == entity)
                    .order_by(SyncLog.id.desc())
                    .first()
                )

                if not latest:
                    entity_health.append(
                        {
                            "entity": entity,
                            "status": "never_synced",
                            "last_completed_at": None,
                            "lag_minutes": None,
                            "target_lag_minutes": entity_target_lag,
                            "processed_count": 0,
                            "failed_count": 0,
                        }
                    )
                    continue

                completed_at = latest.completed_at or latest.started_at
                lag_minutes = None
                if completed_at:
                    completed_utc = self._ensure_utc(completed_at)
                    lag_minutes = round((now_utc - completed_utc).total_seconds() / 60.0, 2)

                if latest.status == "failed":
                    health_status = "failed"
                elif lag_minutes is None:
                    health_status = "unknown"
                elif lag_minutes > entity_target_lag:
                    health_status = "sync_lag"
                elif latest.status == "running":
                    health_status = "running"
                else:
                    health_status = "healthy"

                entity_health.append(
                    {
                        "entity": entity,
                        "status": health_status,
                        "last_completed_at": completed_at.isoformat() if completed_at else None,
                        "lag_minutes": lag_minutes,
                        "target_lag_minutes": entity_target_lag,
                        "processed_count": int(latest.processed_count or 0),
                        "failed_count": int(latest.failed_count or 0),
                        "error_message": latest.error_message,
                    }
                )

            overall_status = "healthy"
            if any(item["status"] == "failed" for item in entity_health):
                overall_status = "failed"
            elif any(item["status"] == "sync_lag" for item in entity_health):
                overall_status = "sync_lag"
            elif any(item["status"] in {"never_synced", "unknown"} for item in entity_health):
                overall_status = "not_ready"
            elif any(item["status"] == "running" for item in entity_health):
                overall_status = "running"

            return {
                "success": True,
                "status": overall_status,
                "max_lag_minutes": default_max_lag,
                "entities": entity_health,
            }
        finally:
            db.close()

    def get_runtime_sync_status(self) -> Dict[str, Any]:
        """Lightweight runtime snapshot for UI status endpoint."""
        now_utc = self._utcnow()
        scheduler_running = bool(self._scheduler_task and not self._scheduler_task.done())
        runtime_status = "running" if scheduler_running else "idle"
        current_step: Optional[str] = "scheduler_loop" if scheduler_running else None
        progress_pct = 10 if scheduler_running else 0
        last_synced_at: Optional[str] = None

        db = SessionLocal()
        try:
            latest = (
                db.query(SyncLog)
                .filter(SyncLog.status.in_(["completed", "running", "failed"]))
                .order_by(SyncLog.id.desc())
                .first()
            )
            if latest:
                timestamp = latest.completed_at or latest.started_at
                if timestamp:
                    last_synced_at = self._ensure_utc(timestamp).isoformat()
                if latest.status == "running":
                    runtime_status = "running"
                    current_step = f"sync:{latest.entity}"
                    progress_pct = 50
                elif latest.status == "failed":
                    runtime_status = "error"
                    current_step = f"failed:{latest.entity}"
                    progress_pct = 100
                elif latest.status == "completed":
                    runtime_status = "idle"
                    current_step = "completed"
                    progress_pct = 100
        finally:
            db.close()

        return {
            "status": runtime_status,
            "current_step": current_step,
            "progress_pct": progress_pct,
            "last_synced_at": last_synced_at,
            "updated_at": now_utc.isoformat(),
        }

    def get_release_readiness(self) -> Dict[str, Any]:
        now_utc = self._utcnow()
        since = now_utc - timedelta(days=30)
        readiness_errors: List[str] = []

        normalized_rows = 0
        raw_rows = 0
        coverage_gate: Dict[str, Any]

        db = SessionLocal()
        try:
            normalized_rows = (
                db.query(func.count(SalesOrderRecord.id))
                .filter(SalesOrderRecord.updated_at >= since)
                .scalar()
                or 0
            )
            raw_rows = (
                db.query(func.count(distinct(ExportRow.row_hash)))
                .filter(
                    ExportRow.entity_type == "sale_order",
                    ExportRow.created_at >= since,
                )
                .scalar()
                or 0
            )

            # Coverage ratio is only meaningful after at least one export archival run.
            if raw_rows == 0:
                coverage_ratio = None
                coverage_passed = False
                coverage_error = "No raw export rows found in readiness window"
            else:
                coverage_ratio = float(normalized_rows) / float(raw_rows)
                coverage_passed = coverage_ratio >= 0.98
                coverage_error = None

            coverage_gate = {
                "target": 0.98,
                "value": round(coverage_ratio, 4) if coverage_ratio is not None else None,
                "passed": coverage_passed,
            }
            if coverage_error:
                coverage_gate["error"] = coverage_error
        except SQLAlchemyError as exc:
            readiness_errors.append(f"Coverage query failed: {exc}")
            coverage_gate = {
                "target": 0.98,
                "value": None,
                "passed": False,
                "error": str(exc),
            }
        finally:
            db.close()

        max_observed_lag = None
        lag_gate_passed = False
        lag_blockers: List[str] = []
        health: Dict[str, Any]
        try:
            health = self.get_sync_health()
            entities = health.get("entities", [])
            required_entities = {
                "sale_orders",
                "sales_returns",
                "inventory_snapshot",
            }
            required_entity_rows = [
                item for item in entities if item.get("entity") in required_entities
            ]

            entity_targets = {
                str(item.get("entity")): int(
                    item.get("target_lag_minutes")
                    or self._entity_max_lag_minutes(str(item.get("entity") or ""))
                )
                for item in required_entity_rows
            }

            lag_values = [
                float(item["lag_minutes"])
                for item in required_entity_rows
                if item.get("lag_minutes") is not None and item.get("entity") in required_entities
            ]
            max_observed_lag = max(lag_values) if lag_values else None

            lag_blockers = [
                item.get("entity", "unknown")
                for item in required_entity_rows
                if item.get("entity") in required_entities and item.get("status") != "healthy"
            ]
            lag_gate_passed = (
                bool(required_entity_rows)
                and not lag_blockers
                and all(item.get("lag_minutes") is not None for item in required_entity_rows)
            )
        except Exception as exc:
            readiness_errors.append(f"Sync health query failed: {exc}")
            health = {
                "success": False,
                "status": "unknown",
                "error": str(exc),
                "entities": [],
            }
            lag_blockers = ["health_probe_failed"]
            entity_targets = {
                "sale_orders": self._entity_max_lag_minutes("sale_orders"),
                "sales_returns": self._entity_max_lag_minutes("sales_returns"),
                "inventory_snapshot": self._entity_max_lag_minutes("inventory_snapshot"),
            }

        dashboard_gate = {
            "target": True,
            "value": False,
            "passed": False,
        }
        try:
            sales_probe = get_unicommerce_data_service().get_sales_data(period="today")
            data_source = str(sales_probe.get("data_source") or "").strip().lower()
            has_db_source = data_source not in {"", "none", "unknown"}
            dashboard_gate["value"] = bool(sales_probe.get("success")) and has_db_source
            dashboard_gate["data_source"] = data_source
            dashboard_gate["fallback_used"] = bool(sales_probe.get("fallback_used"))
            dashboard_gate["total_orders"] = int((sales_probe.get("summary") or {}).get("total_orders", 0) or 0)
            dashboard_gate["passed"] = bool(dashboard_gate["value"])
        except Exception as exc:
            readiness_errors.append(f"Dashboard probe failed: {exc}")
            dashboard_gate["error"] = str(exc)

        gates = {
            "coverage_ratio": coverage_gate,
            "sync_lag_minutes": {
                "target": max(entity_targets.values()) if entity_targets else settings.UNICOMMERCE_SYNC_MAX_LAG_MINUTES,
                "target_by_entity_minutes": entity_targets,
                "value": round(max_observed_lag, 2) if max_observed_lag is not None else None,
                "passed": lag_gate_passed,
                "blockers": lag_blockers,
                "required_entities": ["sale_orders", "sales_returns", "inventory_snapshot"],
            },
            "dashboard_paths_db_first": dashboard_gate,
        }

        response = {
            "success": True,
            "evaluated_at": now_utc.isoformat(),
            "window_days": 30,
            "normalized_rows": int(normalized_rows),
            "raw_rows": int(raw_rows),
            "gates": gates,
            "overall_passed": all(bool(gate["passed"]) for gate in gates.values()),
            "health": health,
        }
        if readiness_errors:
            response["errors"] = readiness_errors
        return response

    async def startup_catch_up_sync(self) -> None:
        """Detect and fill data gaps after startup — runs fully in background.

        This is called once after startup with a short delay.  It inspects
        the gap between ``last_successful_sync`` and now for each critical
        entity and chooses the appropriate recovery mode:

        * gap < min_gap_hours : nothing to do
        * gap ≤ 1 day         : extended incremental (uses existing lookback)
        * gap 1 – 30 days     : chunked backfill (1 day at a time)
        * gap > 30 days       : deep backfill (3 days at a time)

        All work is dispatched as a non-blocking asyncio task so the API
        is immediately available for requests.
        """
        logger.info("Startup catch-up: checking entity gaps...")
        sync_state = get_sync_state_service()

        try:
            gaps = sync_state.get_all_entity_gaps()
        except Exception as exc:
            logger.error(f"Startup catch-up: failed to read entity gaps: {exc}", exc_info=True)
            return

        min_gap_hours = max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_MIN_GAP_HOURS", 12)))
        now_utc = self._utcnow()
        deep_threshold_days = max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_DEEP_THRESHOLD_DAYS", 30)))

        needs_sales_recovery = False
        needs_inventory_refresh = False
        sales_gap_hours: float = 0.0

        for entity, gap_hours in gaps.items():
            if gap_hours is None:
                # Never synced — treat as infinite gap
                gap_hours = float(deep_threshold_days * 24 + 1)
                logger.info(
                    f"Startup catch-up: entity '{entity}' has never been synced — "
                    f"scheduling full backfill"
                )
            else:
                logger.info(
                    f"Startup catch-up: entity '{entity}' gap = {gap_hours:.1f}h"
                )

            if entity == "inventory_snapshot":
                inventory_interval = max(1, int(settings.UNICOMMERCE_SYNC_INVENTORY_INTERVAL_HOURS))
                if gap_hours >= inventory_interval:
                    needs_inventory_refresh = True
            else:
                if gap_hours >= min_gap_hours:
                    needs_sales_recovery = True
                    sales_gap_hours = max(sales_gap_hours, gap_hours)

        if not needs_sales_recovery and not needs_inventory_refresh:
            logger.info("Startup catch-up: all entities within tolerance — no action needed")
            return

        # --- Inventory refresh (always a point-in-time snapshot) ---
        if needs_inventory_refresh:
            asyncio.create_task(self._catch_up_inventory())

        # --- Sales / returns gap fill ---
        if needs_sales_recovery:
            gap_days = sales_gap_hours / 24.0

            if gap_days <= 1.0:
                # Small gap: run a single incremental sync with extended lookback
                logger.info(
                    f"Startup catch-up: gap {sales_gap_hours:.1f}h — running incremental sync"
                )
                asyncio.create_task(self._catch_up_incremental())

            else:
                chunk_days = (
                    max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_DEEP_CHUNK_DAYS", 3)))
                    if gap_days > deep_threshold_days
                    else max(1, int(getattr(settings, "UNICOMMERCE_RECOVERY_BACKFILL_CHUNK_DAYS", 1)))
                )
                mode = "deep" if gap_days > deep_threshold_days else "backfill"
                from_date = now_utc - timedelta(hours=sales_gap_hours)
                logger.info(
                    f"Startup catch-up: gap {gap_days:.1f} days — scheduling {mode} "
                    f"backfill in {chunk_days}-day chunks from {from_date.date().isoformat()}"
                )
                asyncio.create_task(
                    self._run_chunked_catchup_background(from_date, now_utc, chunk_days)
                )

    async def _catch_up_incremental(self) -> None:
        """Run a single incremental sync to cover a short gap."""
        try:
            lookback_days = max(
                2, int(getattr(settings, "UNICOMMERCE_SYNC_LOOKBACK_DAYS", 2)) + 1
            )
            logger.info(f"Startup catch-up (incremental): lookback {lookback_days} days")
            await self.run_incremental_sync(lookback_days=lookback_days)
            logger.info("Startup catch-up (incremental): completed")
        except Exception as exc:
            logger.error(f"Startup catch-up (incremental) failed: {exc}", exc_info=True)

    async def _catch_up_inventory(self) -> None:
        """Refresh inventory snapshot as part of catch-up."""
        try:
            logger.info("Startup catch-up (inventory): refreshing snapshot")
            from app.services.sync_inventory_snapshot import fetch_and_sync_inventory
            facility = str(
                getattr(settings, "UNICOMMERCE_SYNC_INVENTORY_FACILITY_CODE", "anthrilo")
            ).strip() or "anthrilo"
            await fetch_and_sync_inventory(facility)
            await self.run_inventory_parity_check()
            logger.info("Startup catch-up (inventory): completed")
        except Exception as exc:
            logger.error(f"Startup catch-up (inventory) failed: {exc}", exc_info=True)

    async def _run_chunked_catchup_background(
        self,
        from_date: datetime,
        to_date: datetime,
        chunk_days: int,
    ) -> None:
        """Run a chunked backfill (newest-first) in-process without blocking the API.

        Chunks are processed sequentially with a small sleep between them to
        avoid overloading the VPS or the Unicommerce export API.
        """
        from zoneinfo import ZoneInfo
        ist = ZoneInfo("Asia/Kolkata")
        chunk_delay = max(2, int(getattr(settings, "UNICOMMERCE_RECOVERY_CHUNK_DELAY_SECONDS", 5)))

        start = self._ensure_utc(from_date)
        end = self._ensure_utc(to_date)

        # Build today + yesterday priority chunks first, then remaining history.
        now_utc = self._utcnow()
        uc_service = self.uc_service
        today_from, today_to = uc_service.get_today_range()
        yesterday_from, yesterday_to = uc_service.get_yesterday_range()

        priority_chunks: List[Tuple[datetime, datetime]] = []
        historical_chunks: List[Tuple[datetime, datetime]] = []

        for chunk_start, chunk_end in self._chunk_range(start, end, chunk_days):
            if chunk_start >= today_from:
                priority_chunks.insert(0, (chunk_start, chunk_end))
            elif chunk_start >= yesterday_from:
                priority_chunks.append((chunk_start, chunk_end))
            else:
                historical_chunks.append((chunk_start, chunk_end))

        # Process newest historical first.
        historical_chunks.sort(key=lambda c: c[0], reverse=True)
        all_chunks = priority_chunks + historical_chunks

        total = len(all_chunks)
        logger.info(
            f"Startup catch-up (backfill): processing {total} chunk(s) of {chunk_days}d each"
        )

        for idx, (chunk_start, chunk_end) in enumerate(all_chunks, start=1):
            try:
                logger.info(
                    f"Startup catch-up chunk {idx}/{total}: "
                    f"{chunk_start.astimezone(ist).date()} → "
                    f"{chunk_end.astimezone(ist).date()}"
                )
                orders_result = await self.sync_orders_window(
                    chunk_start, chunk_end, sync_mode="recovery"
                )
                returns_result = await self.sync_returns_window(
                    chunk_start, chunk_end, sync_mode="recovery"
                )
                if not orders_result.get("success") or not returns_result.get("success"):
                    logger.warning(
                        f"Startup catch-up chunk {idx}/{total} partially failed: "
                        f"orders={orders_result.get('success')}, "
                        f"returns={returns_result.get('success')}"
                    )
            except Exception as exc:
                logger.error(
                    f"Startup catch-up chunk {idx}/{total} failed: {exc}", exc_info=True
                )

            if idx < total:
                await asyncio.sleep(chunk_delay)

        logger.info("Startup catch-up (backfill): all chunks completed")

    def start_scheduler(self) -> bool:
        if self._scheduler_task and not self._scheduler_task.done():
            return False

        self._bootstrap_scheduler_state()
        self._scheduler_stop_event = asyncio.Event()
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Unicommerce sync scheduler started")
        return True

    async def stop_scheduler(self) -> bool:
        if not self._scheduler_task:
            return False

        if self._scheduler_stop_event:
            self._scheduler_stop_event.set()

        try:
            await self._scheduler_task
        except Exception:
            pass

        self._scheduler_task = None
        self._scheduler_stop_event = None
        self._scheduler_next_run_at = {}
        self._scheduler_bootstrapped = False
        logger.info("Unicommerce sync scheduler stopped")
        return True

    async def _scheduler_loop(self) -> None:
        interval_seconds = max(15, int(settings.UNICOMMERCE_SYNC_SCHEDULER_TICK_SECONDS))
        while self._scheduler_stop_event is not None and not self._scheduler_stop_event.is_set():
            try:
                run_result = await self.run_due_scheduler_jobs()
                if not run_result.get("success"):
                    logger.warning(f"Scheduled sync cycle finished with failures: {run_result}")
            except Exception as exc:
                logger.error(f"Scheduler loop failed: {exc}", exc_info=True)

            try:
                await asyncio.wait_for(self._scheduler_stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                continue


_orchestrator_instance: Optional[UnicommerceSyncOrchestrator] = None


def get_unicommerce_sync_orchestrator() -> UnicommerceSyncOrchestrator:
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = UnicommerceSyncOrchestrator()
    return _orchestrator_instance
