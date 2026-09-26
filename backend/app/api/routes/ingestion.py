import uuid
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.core.rate_limit import enforce_upload_rate_limit
from app.models.user import User
from app.schemas.ingestion import (
    BatchIngestionResponse,
    EmailAttachmentIngestRequest,
    EmailAttachmentIngestResponse,
    IngestionListResponse,
    IngestionResponse,
)
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.email_polling_service import EmailPollResult, EmailPollingService, EmailPollStatus


router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/batch", response_model=BatchIngestionResponse)
async def ingest_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.DOCUMENTS_WRITE)),
) -> BatchIngestionResponse:
    enforce_upload_rate_limit(request)
    return DocumentIngestionService(db).ingest_batch(
        files,
        actor_id=user.id,
        background_tasks=background_tasks,
        queue_processing=True,
    )


@router.post("/email-attachments", response_model=EmailAttachmentIngestResponse)
def ingest_email_attachment(
    payload: EmailAttachmentIngestRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.DOCUMENTS_WRITE)),
) -> EmailAttachmentIngestResponse:
    return DocumentIngestionService(db).ingest_email_request(
        payload,
        actor_id=user.id,
        background_tasks=background_tasks,
        queue_processing=True,
    )


@router.get("/email/status", response_model=EmailPollStatus)
def email_ingestion_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> EmailPollStatus:
    return EmailPollingService(db).get_status()


@router.post("/email/poll", response_model=EmailPollResult)
def email_ingestion_poll(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.DOCUMENTS_WRITE)),
) -> EmailPollResult:
    return EmailPollingService(db).poll(
        actor_id=user.id,
        background_tasks=background_tasks,
    )


@router.get("", response_model=IngestionListResponse)
def list_ingestions(
    source_type: str | None = Query(None),
    status: str | None = Query(None),
    created_from: date | None = Query(None),
    created_to: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> IngestionListResponse:
    return DocumentIngestionService(db).list_ingestions(
        source_type=source_type,
        status=status,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )


@router.get("/{ingestion_id}", response_model=IngestionResponse)
def get_ingestion(
    ingestion_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DOCUMENTS_READ)),
) -> IngestionResponse:
    return DocumentIngestionService(db).get_ingestion(ingestion_id)
