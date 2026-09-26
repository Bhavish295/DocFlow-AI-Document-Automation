"""Celery tasks — thin wrappers around existing processing / email services."""

from __future__ import annotations

import logging
import uuid

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_TRANSIENT_MARKERS = (
    "connection refused",
    "connection reset",
    "timed out",
    "timeout",
    "temporarily unavailable",
    "could not connect",
    "deadlock",
    "server closed the connection",
    "connection aborted",
)


def _is_transient_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_MARKERS)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.process_document_job",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def process_document_job(self, job_id: str) -> dict:
    """Execute an existing processing job via DocumentProcessingRunner."""
    from app.core.config import settings
    from app.services.document_processing_runner import execute_processing_job

    try:
        execute_processing_job(uuid.UUID(job_id))
        return {"job_id": job_id, "status": "executed"}
    except Exception as exc:  # noqa: BLE001
        max_retries = max(0, int(settings.CELERY_TASK_MAX_RETRIES))
        delay = max(5, int(settings.CELERY_TASK_RETRY_DELAY_SECONDS))
        if _is_transient_error(exc) and self.request.retries < max_retries:
            logger.warning(
                "Transient failure processing job %s (retry %s/%s): %s",
                job_id,
                self.request.retries + 1,
                max_retries,
                exc.__class__.__name__,
            )
            raise self.retry(exc=exc, countdown=delay * (self.request.retries + 1))
        logger.exception("Processing job %s failed permanently", job_id)
        raise


@celery_app.task(name="app.workers.tasks.poll_email_inbox")
def poll_email_inbox() -> dict:
    """Scheduled / manual email attachment poll (no credentials in result)."""
    from app.core.database import SessionLocal
    from app.services.email_polling_service import EmailPollingService

    db = SessionLocal()
    try:
        result = EmailPollingService(db).poll(actor_id=None, background_tasks=None)
        return result.model_dump(mode="json")
    finally:
        db.close()
