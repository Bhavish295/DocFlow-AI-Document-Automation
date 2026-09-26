import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.document_review import (
    ReviewActionRequest,
    ReviewDetailResponse,
    ReviewListResponse,
    ReviewUpdate,
)
from app.services.audit_service import AuditService
from app.services.document_review import DocumentReviewService


router = APIRouter(prefix="/reviews")


@router.get("", response_model=ReviewListResponse)
def list_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    priority: str | None = Query(None),
    reason: str | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.REVIEWS_READ)),
) -> ReviewListResponse:
    return DocumentReviewService(db).list_reviews(
        status=status,
        priority=priority,
        reason=reason,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/{review_id}", response_model=ReviewDetailResponse)
def get_review(
    review_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.REVIEWS_READ)),
) -> ReviewDetailResponse:
    return DocumentReviewService(db).get_review(review_id)


@router.patch("/{review_id}", response_model=ReviewDetailResponse)
def update_review(
    review_id: uuid.UUID,
    payload: ReviewUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.REVIEWS_WRITE)),
) -> ReviewDetailResponse:
    return DocumentReviewService(db).update_review(review_id, payload)


@router.post("/{review_id}/start", response_model=ReviewDetailResponse)
def start_review(
    review_id: uuid.UUID,
    payload: ReviewActionRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.REVIEWS_WRITE)),
) -> ReviewDetailResponse:
    return DocumentReviewService(db).start_review(review_id, payload)


@router.post("/{review_id}/approve", response_model=ReviewDetailResponse)
def approve_review(
    review_id: uuid.UUID,
    payload: ReviewActionRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.REVIEWS_WRITE)),
) -> ReviewDetailResponse:
    result = DocumentReviewService(db).approve_review(review_id, payload)
    AuditService(db).log(
        action="review_approved",
        user_id=user.id,
        resource_type="review",
        resource_id=review_id,
    )
    return result


@router.post("/{review_id}/reject", response_model=ReviewDetailResponse)
def reject_review(
    review_id: uuid.UUID,
    payload: ReviewActionRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission(Permission.REVIEWS_WRITE)),
) -> ReviewDetailResponse:
    result = DocumentReviewService(db).reject_review(review_id, payload)
    AuditService(db).log(
        action="review_rejected",
        user_id=user.id,
        resource_type="review",
        resource_id=review_id,
    )
    return result
