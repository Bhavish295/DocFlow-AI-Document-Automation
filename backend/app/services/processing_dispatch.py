"""Enqueue helpers for document processing (local BackgroundTasks or Celery)."""

from __future__ import annotations

import logging
import uuid

from fastapi import BackgroundTasks

from app.core.config import settings
from app.services.document_processing_runner import execute_processing_job

logger = logging.getLogger(__name__)


def enqueue_processing_job(
    job_id: uuid.UUID,
    *,
    background_tasks: BackgroundTasks | None = None,
    force_sync: bool = False,
) -> str:
    """
    Dispatch a processing job.

    Returns the dispatch mode used: sync | local | celery.
    """
    if force_sync or settings.DOCUMENT_PROCESSING_SYNC:
        execute_processing_job(job_id)
        return "sync"

    if settings.uses_celery_workers:
        from app.workers.tasks import process_document_job

        process_document_job.delay(str(job_id))
        logger.info("Enqueued processing job %s via Celery", job_id)
        return "celery"

    if background_tasks is not None:
        background_tasks.add_task(execute_processing_job, job_id)
        return "local"

    # No BackgroundTasks and not celery — run inline to avoid orphaned queued jobs.
    execute_processing_job(job_id)
    return "sync"
