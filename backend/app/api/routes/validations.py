import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.three_way_match import (
    ThreeWayMatchListResponse,
    ThreeWayMatchRequest,
    ThreeWayMatchResponse,
)
from app.schemas.validation import ValidationListResponse, ValidationResponse
from app.services.three_way_matching import ThreeWayMatchingService
from app.services.validation_service import ValidationService


router = APIRouter(prefix="/validations")


@router.get("", response_model=ValidationListResponse)
def list_validations(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.VALIDATIONS_READ)),
) -> ValidationListResponse:
    return ValidationService(db).list_validations(page=page, page_size=page_size)


@router.post("/three-way", response_model=ThreeWayMatchResponse)
def run_three_way_match(
    payload: ThreeWayMatchRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.VALIDATIONS_WRITE)),
) -> ThreeWayMatchResponse:
    return ThreeWayMatchingService(db).run_match(payload)


@router.get("/three-way", response_model=ThreeWayMatchListResponse)
def list_three_way_matches(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.VALIDATIONS_READ)),
) -> ThreeWayMatchListResponse:
    return ThreeWayMatchingService(db).list_matches(page=page, page_size=page_size)


@router.get("/three-way/{match_id}", response_model=ThreeWayMatchResponse)
def get_three_way_match(
    match_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.VALIDATIONS_READ)),
) -> ThreeWayMatchResponse:
    return ThreeWayMatchingService(db).get_match(match_id)


@router.get("/{validation_id}", response_model=ValidationResponse)
def get_validation(
    validation_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.VALIDATIONS_READ)),
) -> ValidationResponse:
    return ValidationService(db).get_validation(validation_id)


@router.post(
    "/invoice/{invoice_id}/purchase-order/{purchase_order_id}",
    response_model=ValidationResponse,
)
def validate_invoice_against_purchase_order(
    invoice_id: uuid.UUID,
    purchase_order_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.VALIDATIONS_WRITE)),
) -> ValidationResponse:
    return ValidationService(db).validate_invoice_against_po(invoice_id, purchase_order_id)
