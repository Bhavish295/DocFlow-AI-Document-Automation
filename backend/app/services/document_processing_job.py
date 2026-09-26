"""Document processing job lifecycle (create / progress / complete / fail / retry / cancel)."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.document import Document
from app.models.document_processing_job import (
    ACTIVE_JOB_STATUSES,
    STAGE_PROGRESS,
    DocumentProcessingJob,
    ProcessingJobStage,
    ProcessingJobStatus,
    ProcessingJobType,
)
from app.schemas.processing_job import ProcessingJobListResponse, ProcessingJobResponse


def _safe_error_message(exc: BaseException | str | None) -> str:
    if exc is None:
        return "Document processing failed."
    text = str(exc).strip() if not isinstance(exc, str) else exc.strip()
    if not text:
        return "Document processing failed."
    # Never expose huge traces through the API.
    first_line = text.splitlines()[0].strip()
    return first_line[:500]


class DocumentProcessingJobService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_active_job(self, document_id: uuid.UUID) -> DocumentProcessingJob | None:
        return self.db.scalar(
            select(DocumentProcessingJob)
            .where(
                DocumentProcessingJob.document_id == document_id,
                DocumentProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(DocumentProcessingJob.created_at.desc())
        )

    def create_job(
        self,
        document_id: uuid.UUID,
        *,
        parent_job_id: uuid.UUID | None = None,
        commit: bool = True,
    ) -> DocumentProcessingJob:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)

        active = self.get_active_job(document_id)
        if active is not None:
            raise AppError(
                "An active processing job already exists for this document.",
                status_code=409,
            )

        now = datetime.now(timezone.utc)
        job = DocumentProcessingJob(
            document_id=document_id,
            status=ProcessingJobStatus.QUEUED.value,
            job_type=ProcessingJobType.DOCUMENT_PROCESSING.value,
            progress=STAGE_PROGRESS[ProcessingJobStage.QUEUED.value],
            current_stage=ProcessingJobStage.QUEUED.value,
            parent_job_id=parent_job_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(job)
        if commit:
            self.db.commit()
            self.db.refresh(job)
        else:
            self.db.flush()
        return job

    def get_job(self, job_id: uuid.UUID) -> DocumentProcessingJob:
        job = self.db.get(DocumentProcessingJob, job_id)
        if job is None:
            raise AppError("Processing job not found.", status_code=404)
        return job

    def list_for_document(
        self,
        document_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> ProcessingJobListResponse:
        document = self.db.get(Document, document_id)
        if document is None:
            raise AppError("Document not found.", status_code=404)

        page = max(1, page)
        page_size = min(100, max(1, page_size))
        base = select(DocumentProcessingJob).where(
            DocumentProcessingJob.document_id == document_id
        )
        total = len(list(self.db.scalars(base).all()))
        rows = list(
            self.db.scalars(
                base.order_by(DocumentProcessingJob.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return ProcessingJobListResponse(
            items=[ProcessingJobResponse.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def mark_running(self, job: DocumentProcessingJob) -> DocumentProcessingJob:
        now = datetime.now(timezone.utc)
        job.status = ProcessingJobStatus.RUNNING.value
        job.started_at = job.started_at or now
        job.updated_at = now
        self.db.commit()
        self.db.refresh(job)
        return job

    def update_stage(
        self,
        job: DocumentProcessingJob,
        stage: str,
        *,
        progress: int | None = None,
    ) -> DocumentProcessingJob:
        self.db.refresh(job)
        if job.status in {
            ProcessingJobStatus.COMPLETED.value,
            ProcessingJobStatus.FAILED.value,
            ProcessingJobStatus.CANCELLED.value,
        }:
            return job
        if job.cancel_requested:
            return job

        job.current_stage = stage
        job.progress = progress if progress is not None else STAGE_PROGRESS.get(stage, job.progress)
        job.progress = max(0, min(100, int(job.progress)))
        job.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        return job

    def complete(self, job: DocumentProcessingJob) -> DocumentProcessingJob:
        now = datetime.now(timezone.utc)
        job.status = ProcessingJobStatus.COMPLETED.value
        job.current_stage = ProcessingJobStage.COMPLETED.value
        job.progress = 100
        job.error_message = None
        job.completed_at = now
        job.updated_at = now
        self.db.commit()
        self.db.refresh(job)
        return job

    def fail(self, job: DocumentProcessingJob, error: BaseException | str) -> DocumentProcessingJob:
        now = datetime.now(timezone.utc)
        job.status = ProcessingJobStatus.FAILED.value
        job.error_message = _safe_error_message(error)
        job.completed_at = now
        job.updated_at = now
        self.db.commit()
        self.db.refresh(job)
        return job

    def request_cancel(self, job_id: uuid.UUID) -> ProcessingJobResponse:
        job = self.get_job(job_id)
        if job.status == ProcessingJobStatus.QUEUED.value:
            now = datetime.now(timezone.utc)
            job.status = ProcessingJobStatus.CANCELLED.value
            job.cancel_requested = True
            job.completed_at = now
            job.updated_at = now
            job.error_message = "Cancelled before execution started."
            self.db.commit()
            self.db.refresh(job)
            return ProcessingJobResponse.model_validate(job)

        if job.status == ProcessingJobStatus.RUNNING.value:
            job.cancel_requested = True
            job.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(job)
            return ProcessingJobResponse.model_validate(job)

        raise AppError(
            "Only queued or running jobs can be cancelled.",
            status_code=400,
        )

    def is_cancel_requested(self, job_id: uuid.UUID) -> bool:
        job = self.db.get(DocumentProcessingJob, job_id)
        return bool(job and job.cancel_requested)

    def mark_cancelled(self, job: DocumentProcessingJob, message: str | None = None) -> DocumentProcessingJob:
        now = datetime.now(timezone.utc)
        job.status = ProcessingJobStatus.CANCELLED.value
        job.cancel_requested = True
        job.completed_at = now
        job.updated_at = now
        job.error_message = message or "Cancelled during processing."
        self.db.commit()
        self.db.refresh(job)
        return job

    def retry(self, job_id: uuid.UUID) -> DocumentProcessingJob:
        previous = self.get_job(job_id)
        if previous.status != ProcessingJobStatus.FAILED.value:
            raise AppError("Only failed jobs can be retried.", status_code=400)
        return self.create_job(previous.document_id, parent_job_id=previous.id, commit=True)

    def to_response(self, job: DocumentProcessingJob) -> ProcessingJobResponse:
        return ProcessingJobResponse.model_validate(job)
