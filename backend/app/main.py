from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import asyncio
from app.core.config import settings
from app.api.v1.api import api_router
from app.core.redis import redis_client
from app.services.unicommerce_sync_orchestrator import get_unicommerce_sync_orchestrator
from app.services.recovery_service import RecoveryService
from app.services.sync_state_service import get_sync_state_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    version="2.0.0",
    description="Anthrilo management system"
)

# GZip responses over 500 bytes
app.add_middleware(GZipMiddleware, minimum_size=500)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
async def on_startup() -> None:
    # Ensure sync_state and related tables exist (idempotent — safe to run on every boot)
    try:
        from app.db.session import engine
        from app.db.sync_models import Base as SyncBase
        SyncBase.metadata.create_all(bind=engine, checkfirst=True)
        logger.info("Sync state tables verified/created")
    except Exception as exc:
        logger.warning(f"Could not auto-create sync tables: {exc}", exc_info=True)

    orchestrator = get_unicommerce_sync_orchestrator()

    if settings.UNICOMMERCE_SYNC_ENABLE_SCHEDULER:
        started = orchestrator.start_scheduler()
        if started:
            logger.info("Unicommerce incremental sync scheduler enabled")

    # Schedule the startup catch-up as a non-blocking background task.
    # A short delay lets the API server finish initialising before we hit
    # the Unicommerce export API.
    async def _delayed_startup_catch_up() -> None:
        delay = max(0, int(getattr(settings, "UNICOMMERCE_RECOVERY_STARTUP_DELAY_SECONDS", 10)))
        if delay:
            await asyncio.sleep(delay)
        try:
            await orchestrator.startup_catch_up_sync()
        except Exception as exc:
            logger.warning(f"Startup catch-up sync failed: {exc}", exc_info=True)

        # Also trigger the Celery/asyncio recovery plan for any remaining gaps
        try:
            RecoveryService().schedule_startup_recovery()
        except Exception as exc:
            logger.warning(f"Startup recovery scheduling failed: {exc}", exc_info=True)

    asyncio.create_task(_delayed_startup_catch_up())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    orchestrator = get_unicommerce_sync_orchestrator()
    await orchestrator.stop_scheduler()


@app.get("/")
async def root():
    return {
        "message": "Anthrilo Management System API",
        "version": "2.0.0",
        "docs": f"{settings.API_V1_STR}/docs",
        "websocket_path": f"{settings.API_V1_STR}/integrations/ws/sales"
    }


@app.get("/health")
async def health_check():
    """Lightweight health check — always returns 200 (used for uptime monitoring)."""
    redis_ok = False
    try:
        if redis_client:
            redis_client.ping()
            redis_ok = True
    except Exception:
        pass

    orchestrator = get_unicommerce_sync_orchestrator()
    scheduler_task = getattr(orchestrator, "_scheduler_task", None)
    scheduler_running = bool(scheduler_task and not scheduler_task.done())
    sync_status = get_sync_state_service().get_system_status()

    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "redis": "connected" if redis_ok else "disconnected",
        "scheduler": "running" if scheduler_running else "stopped",
        "sync_healthy": bool(sync_status.get("healthy", False)),
        "sync_alerts": sync_status.get("alerts", []),
        "last_successful_sync": sync_status.get("last_successful_sync"),
    }


@app.get("/readiness")
async def readiness_check():
    """Readiness probe for load balancers / nginx / systemd.

    Returns 200 when the API can reach the database.
    Returns 503 when DB is unreachable so the process supervisor can restart.
    """
    from fastapi import Response
    from app.db.session import SessionLocal
    from sqlalchemy import text

    db_ok = False
    db_error = None
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception as exc:
        db_error = str(exc)

    if not db_ok:
        logger.critical(f"Readiness check FAILED — DB unreachable: {db_error}")
        return Response(
            content='{"status":"not_ready","db":"unreachable"}',
            status_code=503,
            media_type="application/json",
        )

    return {"status": "ready", "db": "connected"}
