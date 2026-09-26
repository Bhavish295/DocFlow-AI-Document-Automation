import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.document import MessageResponse
from app.schemas.vendor import (
    VendorCreate,
    VendorDetailResponse,
    VendorListResponse,
    VendorUpdate,
)
from app.services.vendor_service import VendorService


router = APIRouter(prefix="/vendors")


@router.get("", response_model=VendorListResponse)
def list_vendors(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.VENDORS_READ)),
) -> VendorListResponse:
    return VendorService(db).list_vendors(page=page, page_size=page_size)


@router.post("", response_model=VendorDetailResponse, status_code=status.HTTP_201_CREATED)
def create_vendor(
    payload: VendorCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.VENDORS_WRITE)),
) -> VendorDetailResponse:
    return VendorService(db).create_vendor(payload)


@router.get("/{vendor_id}", response_model=VendorDetailResponse)
def get_vendor(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.VENDORS_READ)),
) -> VendorDetailResponse:
    return VendorService(db).get_vendor(vendor_id)


@router.patch("/{vendor_id}", response_model=VendorDetailResponse)
def update_vendor(
    vendor_id: uuid.UUID,
    payload: VendorUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.VENDORS_WRITE)),
) -> VendorDetailResponse:
    return VendorService(db).update_vendor(vendor_id, payload)


@router.delete("/{vendor_id}", response_model=MessageResponse)
def delete_vendor(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.VENDORS_WRITE)),
) -> MessageResponse:
    VendorService(db).delete_vendor(vendor_id)
    return MessageResponse(detail="Vendor deleted successfully.")
