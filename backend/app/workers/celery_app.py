"""Celery application for background recovery tasks."""

from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "anthrilo",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.recovery_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    timezone=str(settings.UNICOMMERCE_SYNC_TIMEZONE or "UTC"),
    task_default_queue="recovery",
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
