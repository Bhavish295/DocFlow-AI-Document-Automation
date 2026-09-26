"""API-facing helpers to enqueue document processing jobs."""

from __future__ import annotations

import uuid

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.document_processing_job import ProcessingJobStatus
from app.schemas.processing_job import ProcessDocumentResponse, ProcessingJobResponse
from app.services.document import DocumentService
from app.services.document_processing import DocumentProcessingService
from app.services.document_processing_job import DocumentProcessingJobService
from app.services.document_processing_runner import DocumentProcessingRunner
from app.services.processing_dispatch import enqueue_processing_job
from app.services.text_extraction import PROCESSABLE_FILE_TYPES


class DocumentProcessingOrchestrator:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.jobs = DocumentProcessingJobService(db)

    def enqueue_process(
        self,
        document_id: uuid.UUID,
        *,
        background_tasks: BackgroundTasks | None = None,
        force_sync: bool | None = None,
    ) -> ProcessDocumentResponse:
        document = DocumentService(self.db).get_document(document_id)
        if document.file_type.lower() not in PROCESSABLE_FILE_TYPES:
            raise AppError(
                "Text extraction is only supported for PDF, PNG, JPG, and JPEG files.",
                status_code=400,
            )

        active = self.jobs.get_active_job(document_id)
        if active is not None:
            return self._combine(document_id, active)

        job = self.jobs.create_job(document_id, commit=True)
        sync = settings.DOCUMENT_PROCESSING_SYNC if force_sync is None else force_sync

        if sync:
            DocumentProcessingRunner(self.db).run(job.id)
            job = self.jobs.get_job(job.id)
            return self._combine(document_id, job)

        enqueue_processing_job(
            job.id,
            background_tasks=background_tasks,
            force_sync=False,
        )
        return self._combine(document_id, job)

    def retry_job(
        self,
        job_id: uuid.UUID,
        *,
        background_tasks: BackgroundTasks | None = None,
        force_sync: bool | None = None,
    ) -> ProcessingJobResponse:
        new_job = self.jobs.retry(job_id)
        sync = settings.DOCUMENT_PROCESSING_SYNC if force_sync is None else force_sync
        if sync:
            DocumentProcessingRunner(self.db).run(new_job.id)
            new_job = self.jobs.get_job(new_job.id)
            return self.jobs.to_response(new_job)

        enqueue_processing_job(
            new_job.id,
            background_tasks=background_tasks,
            force_sync=False,
        )
        return self.jobs.to_response(new_job)

    def _combine(self, document_id: uuid.UUID, job) -> ProcessDocumentResponse:
        document_payload = DocumentProcessingService(self.db)._to_response(
            DocumentProcessingService(self.db)._get_or_404(document_id)
        )
        data = document_payload.model_dump()
        data.update(
            {
                "job_id": job.id,
                "job_status": job.status,
                "current_stage": job.current_stage,
                "progress": job.progress,
            }
        )
        if (
            job.status == ProcessingJobStatus.FAILED.value
            and not data.get("processing_error")
            and job.error_message
        ):
            data["processing_error"] = job.error_message
        return ProcessDocumentResponse.model_validate(data)
