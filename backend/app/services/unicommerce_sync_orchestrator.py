"""Sync orchestration service for export-first Unicommerce ingestion."""

from __future__ import annotations

import asyncio
import logging
import secrets
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
    InventorySnapshotRecord,
    SalesOrderRecord,
    SalesReturnRecord,
    SyncLog,
)
from app.services.unicommerce_data_service import get_unicommerce_data_service
from app.services.unicommerce import get_unicommerce_service

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
            next_due = now_utc + timedelta(hours=max(1, int(interval_hours)))
        else:
            retry_minutes = max(1, int(settings.UNICOMMERCE_SYNC_RETRY_MINUTES))
            next_due = now_utc + timedelta(minutes=retry_minutes)

        self._scheduler_next_run_at[job_key] = next_due
        return next_due

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
        return await self.sync_inventory(facility_code=facility)

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

    async def sync_orders_window(self, from_date: datetime, to_date: datetime) -> Dict[str, Any]:
        lock = await self._acquire_lock("orders")
        if not lock:
            return {
                "success": False,
                "message": "Order sync lock is already held",
                "from_date": self._ensure_utc(from_date).isoformat(),
                "to_date": self._ensure_utc(to_date).isoformat(),
            }

        try:
            result = await self.uc_service.fetch_orders_via_export(
                self._ensure_utc(from_date),
                self._ensure_utc(to_date),
            )
            return {
                "success": bool(result.get("successful")),
                "from_date": self._ensure_utc(from_date).isoformat(),
                "to_date": self._ensure_utc(to_date).isoformat(),
                "total_records": int(result.get("totalRecords", 0) or 0),
                "archived_rows": int(result.get("archived_rows", 0) or 0),
                "normalized_rows": int(result.get("normalized_rows", 0) or 0),
                "total_time": float(result.get("total_time", 0) or 0),
                "error": result.get("error"),
            }
        finally:
            await self._release_lock(lock)

    async def sync_returns_window(self, from_date: datetime, to_date: datetime) -> Dict[str, Any]:
        lock = await self._acquire_lock("returns")
        if not lock:
            return {
                "success": False,
                "message": "Returns sync lock is already held",
                "from_date": self._ensure_utc(from_date).isoformat(),
                "to_date": self._ensure_utc(to_date).isoformat(),
            }

        try:
            result = await self.uc_service.fetch_returns_via_export(
                self._ensure_utc(from_date),
                self._ensure_utc(to_date),
            )
            return {
                "success": bool(result.get("successful")),
                "from_date": self._ensure_utc(from_date).isoformat(),
                "to_date": self._ensure_utc(to_date).isoformat(),
                "total_items": int(result.get("total_items", 0) or 0),
                "archived_rows": int(result.get("archived_rows", 0) or 0),
                "normalized_rows": int(result.get("normalized_rows", 0) or 0),
                "total_time": float(result.get("total_time", 0) or 0),
                "error": result.get("error"),
            }
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
    ) -> Dict[str, Any]:
        lock = await self._acquire_lock("inventory")
        if not lock:
            return {
                "success": False,
                "message": "Inventory sync lock is already held",
            }

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
                return {
                    "success": True,
                    "message": "No SKUs available for inventory sync",
                    "requested_skus": 0,
                    "fetched_skus": 0,
                }

            snapshots = await self.uc_service.get_inventory_snapshot(clean_skus, facility_code=facility_code)
            return {
                "success": True,
                "requested_skus": len(clean_skus),
                "fetched_skus": len(snapshots or {}),
                "facility_code": facility_code,
                "full_discovery": bool(full_discovery),
            }
        finally:
            await self._release_lock(lock)

    async def run_incremental_sync(self, lookback_days: Optional[int] = None) -> Dict[str, Any]:
        days = int(lookback_days or settings.UNICOMMERCE_SYNC_LOOKBACK_DAYS)
        now_utc = self._utcnow()
        from_date = now_utc - timedelta(days=max(1, days))

        orders = await self.sync_orders_window(from_date, now_utc)
        returns = await self.sync_returns_window(from_date, now_utc)
        inventory = await self.sync_inventory()

        return {
            "success": bool(orders.get("success")) and bool(returns.get("success")) and bool(inventory.get("success")),
            "profile": "incremental",
            "from_date": from_date.isoformat(),
            "to_date": now_utc.isoformat(),
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
                inventory_query = db.query(InventorySnapshotRecord)
                facility = str(inventory_facility_code or "").strip()
                if facility:
                    inventory_query = inventory_query.filter(InventorySnapshotRecord.warehouse == facility)
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
        chunk_days: Optional[int] = None,
        full_inventory_discovery: bool = True,
        inventory_discovery_limit: Optional[int] = None,
        inventory_facility_code: str = "anthrilo",
    ) -> Dict[str, Any]:
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

        truncate_result = {
            "success": True,
            "skipped": True,
            "deleted_orders": 0,
            "deleted_returns": 0,
            "deleted_inventory": 0,
        }
        if truncate_period:
            truncate_result = self._truncate_window_data(
                from_date=start,
                to_date=end,
                truncate_orders=include_orders,
                truncate_returns=include_returns,
                truncate_inventory=include_inventory and bool(truncate_inventory),
                inventory_facility_code=inventory_facility_code,
            )
            truncate_result["skipped"] = False
            if not truncate_result.get("success"):
                return {
                    "success": False,
                    "profile": "repair_rebuild",
                    "from_date": start.isoformat(),
                    "to_date": end.isoformat(),
                    "truncate_result": truncate_result,
                }

        rebuild_result = await self.run_backfill(
            from_date=start,
            to_date=end,
            chunk_days=chunk_days,
            include_orders=include_orders,
            include_returns=include_returns,
            include_inventory=include_inventory,
            full_inventory_discovery=bool(full_inventory_discovery and include_inventory),
            inventory_discovery_limit=inventory_discovery_limit,
            inventory_facility_code=inventory_facility_code,
        )

        return {
            "success": bool(rebuild_result.get("success")),
            "profile": "repair_rebuild",
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
            "entities": {
                "sales": include_orders,
                "returns": include_returns,
                "inventory": include_inventory,
            },
            "truncate_period": bool(truncate_period),
            "truncate_inventory": bool(truncate_inventory),
            "truncate_result": truncate_result,
            "rebuild_result": rebuild_result,
        }

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
