"""Celery application for DocFlow background workers."""

from __future__ import annotations

from celery import Celery
from celery.schedules import schedule

from app.core.config import settings


def _beat_schedule() -> dict:
    """Schedule email polling only when an email provider may be used."""
    provider = settings.email_provider_name
    if provider in {"none", ""}:
        return {}
    interval = max(30, int(settings.EMAIL_POLL_INTERVAL_SECONDS or 300))
    return {
        "poll-email-inbox": {
            "task": "app.workers.tasks.poll_email_inbox",
            "schedule": schedule(run_every=interval),
        },
    }


celery_app = Celery(
    "docflow",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule=_beat_schedule(),
)
