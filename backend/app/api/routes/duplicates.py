from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.duplicate import (
    DuplicateCheckResponse,
    DuplicateDocumentResponse,
    DuplicateListResponse,
    DuplicateResolveRequest,
    DuplicateResult,
    DuplicateSummary,
)
from app.services.duplicate_detection import DuplicateDetectionService


router = APIRouter()


@router.post("/duplicates/check/{document_id}", response_model=DuplicateCheckResponse)
def check_duplicates(
    document_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DUPLICATES_CHECK)),
) -> DuplicateCheckResponse:
    result = DuplicateDetectionService(db).check_document(document_id)
    return DuplicateCheckResponse(**result)


@router.get("/duplicates/summary", response_model=DuplicateSummary)
def duplicates_summary(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DUPLICATES_READ)),
) -> DuplicateSummary:
    return DuplicateSummary(**DuplicateDetectionService(db).summary())


@router.get("/duplicates", response_model=DuplicateListResponse)
def list_duplicates(
    status: str | None = None,
    detection_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = "detected_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DUPLICATES_READ)),
) -> DuplicateListResponse:
    payload = DuplicateDetectionService(db).list_duplicates(
        status=status,
        detection_type=detection_type,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return DuplicateListResponse(**payload)


@router.get("/duplicates/{document_id}", response_model=DuplicateDocumentResponse)
def get_document_duplicates(
    document_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DUPLICATES_READ)),
) -> DuplicateDocumentResponse:
    payload = DuplicateDetectionService(db).list_for_document(document_id)
    return DuplicateDocumentResponse(**payload)


@router.patch("/duplicates/{duplicate_id}", response_model=DuplicateResult)
def resolve_duplicate(
    duplicate_id: UUID,
    payload: DuplicateResolveRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.DUPLICATES_RESOLVE)),
) -> DuplicateResult:
    result = DuplicateDetectionService(db).resolve_duplicate(duplicate_id, payload.status)
    return DuplicateResult(**result)
