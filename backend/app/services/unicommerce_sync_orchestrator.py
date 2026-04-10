"""Sync orchestration service for export-first Unicommerce ingestion."""

from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import distinct, func
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.redis import redis_client
from app.db.session import SessionLocal
from app.db.export_models import ExportRow, SalesOrderRecord, SyncLog
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

    def _discover_recent_skus(self, lookback_days: int = 30, limit: int = 5000) -> List[str]:
        db = SessionLocal()
        try:
            since = self._utcnow() - timedelta(days=max(1, int(lookback_days)))
            rows = (
                db.query(SalesOrderRecord.sku)
                .filter(
                    SalesOrderRecord.sku.isnot(None),
                    SalesOrderRecord.sku != "",
                    SalesOrderRecord.updated_at >= since,
                )
                .group_by(SalesOrderRecord.sku)
                .limit(max(1, int(limit)))
                .all()
            )
            return [str(row[0]).strip() for row in rows if row and row[0]]
        finally:
            db.close()

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
                clean_skus = self._discover_recent_skus(
                    lookback_days=max(7, int(settings.UNICOMMERCE_SYNC_LOOKBACK_DAYS * 7)),
                    limit=settings.UNICOMMERCE_SYNC_DISCOVERY_SKU_LIMIT,
                )

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
        include_returns: bool = True,
        include_inventory: bool = True,
    ) -> Dict[str, Any]:
        start = self._ensure_utc(from_date)
        end = self._ensure_utc(to_date)
        chunks = self._chunk_range(start, end, int(chunk_days or settings.UNICOMMERCE_SYNC_BACKFILL_CHUNK_DAYS))

        chunk_results: List[Dict[str, Any]] = []
        total_orders = 0
        total_returns = 0

        for chunk_start, chunk_end in chunks:
            orders = await self.sync_orders_window(chunk_start, chunk_end)
            returns = None
            if include_returns:
                returns = await self.sync_returns_window(chunk_start, chunk_end)

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
            inventory = await self.sync_inventory()

        success = all(bool(chunk.get("orders", {}).get("success")) for chunk in chunk_results)
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
            "total_orders": total_orders,
            "total_returns": total_returns,
            "inventory": inventory,
            "chunks": chunk_results,
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

    def get_sync_health(self) -> Dict[str, Any]:
        now_utc = self._utcnow()
        max_lag = int(settings.UNICOMMERCE_SYNC_MAX_LAG_MINUTES)

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
                elif lag_minutes > max_lag:
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
                "max_lag_minutes": max_lag,
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
            lag_values = [
                float(item["lag_minutes"])
                for item in entities
                if item.get("lag_minutes") is not None and item.get("entity") in required_entities
            ]
            max_observed_lag = max(lag_values) if lag_values else None

            lag_blockers = [
                item.get("entity", "unknown")
                for item in entities
                if item.get("entity") in required_entities and item.get("status") != "healthy"
            ]
            lag_gate_passed = (
                bool([item for item in entities if item.get("entity") in required_entities])
                and not lag_blockers
                and max_observed_lag is not None
                and max_observed_lag <= settings.UNICOMMERCE_SYNC_MAX_LAG_MINUTES
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
                "target": settings.UNICOMMERCE_SYNC_MAX_LAG_MINUTES,
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
        logger.info("Unicommerce sync scheduler stopped")
        return True

    async def _scheduler_loop(self) -> None:
        interval_seconds = max(60, int(settings.UNICOMMERCE_SYNC_INCREMENTAL_MINUTES) * 60)
        while self._scheduler_stop_event is not None and not self._scheduler_stop_event.is_set():
            try:
                await self.run_incremental_sync()
            except Exception as exc:
                logger.error(f"Incremental scheduler sync failed: {exc}", exc_info=True)

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
