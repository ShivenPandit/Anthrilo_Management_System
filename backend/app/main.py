from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.core.config import settings
from app.api.v1.api import api_router
from app.core.redis import redis_client
from app.services.unicommerce_sync_orchestrator import get_unicommerce_sync_orchestrator
from app.services.recovery_service import RecoveryService
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
    if settings.UNICOMMERCE_SYNC_ENABLE_SCHEDULER:
        orchestrator = get_unicommerce_sync_orchestrator()
        started = orchestrator.start_scheduler()
        if started:
            logger.info("Unicommerce incremental sync scheduler enabled")

    try:
        RecoveryService().schedule_startup_recovery()
    except Exception as exc:
        logger.warning(f"Startup recovery scheduling failed: {exc}")


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
    redis_ok = False
    try:
        if redis_client:
            redis_client.ping()
            redis_ok = True
    except Exception:
        pass

    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "redis": "connected" if redis_ok else "disconnected",
    }
