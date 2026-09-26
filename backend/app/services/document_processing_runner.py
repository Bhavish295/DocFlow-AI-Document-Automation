"""Replaceable local runner that executes document processing jobs."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.exceptions import AppError
from app.models.document import DocumentStatus
from app.models.document_processing_job import (
    ProcessingJobStage,
    ProcessingJobStatus,
)
from app.services.document_processing import DocumentProcessingService
from app.services.document_processing_job import DocumentProcessingJobService


class JobCancelled(Exception):
    """Raised when cooperative cancellation is observed between stages."""


class DocumentProcessingRunner:
    """
    Orchestrates a processing job by calling the existing DocumentProcessingService.

    Execution mechanism is intentionally local and replaceable later
    (BackgroundTasks today; a distributed worker later).
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.jobs = DocumentProcessingJobService(db)

    def run(self, job_id: uuid.UUID) -> None:
        job = self.jobs.get_job(job_id)
        if job.status == ProcessingJobStatus.CANCELLED.value:
            return
        if job.status not in {
            ProcessingJobStatus.QUEUED.value,
            ProcessingJobStatus.RUNNING.value,
        }:
            return

        if job.cancel_requested and job.status == ProcessingJobStatus.QUEUED.value:
            self.jobs.mark_cancelled(job, "Cancelled before execution started.")
            return

        self.jobs.mark_running(job)

        def on_stage(stage: str, progress: int) -> None:
            self.db.refresh(job)
            if job.cancel_requested:
                raise JobCancelled("Cancellation requested.")
            self.jobs.update_stage(job, stage, progress=progress)

        try:
            DocumentProcessingService(self.db).process_document(
                job.document_id,
                on_stage=on_stage,
            )
            self.db.refresh(job)
            if job.cancel_requested:
                self.jobs.mark_cancelled(job)
                return

            from app.models.document import Document

            document = self.db.get(Document, job.document_id)
            if document is not None and document.status == DocumentStatus.FAILED.value:
                self.jobs.fail(
                    job,
                    document.processing_error or "Document processing failed.",
                )
                return

            self.jobs.complete(job)
        except JobCancelled:
            self.jobs.mark_cancelled(job)
        except AppError as exc:
            self.jobs.fail(job, exc.message)
        except Exception as exc:  # noqa: BLE001 - job must never stay stuck running
            self.jobs.fail(job, exc)


def execute_processing_job(job_id: uuid.UUID) -> None:
    """Background entrypoint: opens a fresh DB session for the job."""
    db = SessionLocal()
    try:
        DocumentProcessingRunner(db).run(job_id)
    finally:
        db.close()
