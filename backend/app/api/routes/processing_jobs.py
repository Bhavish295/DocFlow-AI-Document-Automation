import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.processing_job import ProcessingJobResponse
from app.services.document_processing_job import DocumentProcessingJobService
from app.services.document_processing_orchestrator import DocumentProcessingOrchestrator


router = APIRouter(prefix="/processing-jobs")


@router.get("/{job_id}", response_model=ProcessingJobResponse)
def get_processing_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PROCESSING_JOBS_READ)),
) -> ProcessingJobResponse:
    job = DocumentProcessingJobService(db).get_job(job_id)
    return DocumentProcessingJobService(db).to_response(job)


@router.post("/{job_id}/retry", response_model=ProcessingJobResponse)
def retry_processing_job(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PROCESSING_JOBS_WRITE)),
) -> ProcessingJobResponse:
    return DocumentProcessingOrchestrator(db).retry_job(
        job_id,
        background_tasks=background_tasks,
    )


@router.post("/{job_id}/cancel", response_model=ProcessingJobResponse)
def cancel_processing_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.PROCESSING_JOBS_WRITE)),
) -> ProcessingJobResponse:
    return DocumentProcessingJobService(db).request_cancel(job_id)
