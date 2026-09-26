from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.document_relationship import (
    DocumentRelationshipCreate,
    DocumentRelationshipListResponse,
    DocumentRelationshipResponse,
    DocumentRelationshipSuggestionListResponse,
)
from app.schemas.document import MessageResponse
from app.services.document_relationship_service import DocumentRelationshipService
import uuid


router = APIRouter(prefix="/document-relationships")


@router.post("", response_model=DocumentRelationshipResponse, status_code=status.HTTP_201_CREATED)
def create_document_relationship(
    payload: DocumentRelationshipCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.RELATIONSHIPS_WRITE)),
) -> DocumentRelationshipResponse:
    return DocumentRelationshipService(db).create_relationship(payload)


@router.get("", response_model=DocumentRelationshipListResponse)
def list_document_relationships(
    document_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.RELATIONSHIPS_READ)),
) -> DocumentRelationshipListResponse:
    return DocumentRelationshipService(db).list_relationships(document_id=document_id)


@router.get("/suggestions/{document_id}", response_model=DocumentRelationshipSuggestionListResponse)
def suggest_document_relationships(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.RELATIONSHIPS_READ)),
) -> DocumentRelationshipSuggestionListResponse:
    return DocumentRelationshipService(db).suggest_for_document(document_id)


@router.get("/{document_id}", response_model=DocumentRelationshipListResponse)
def get_document_relationships(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.RELATIONSHIPS_READ)),
) -> DocumentRelationshipListResponse:
    return DocumentRelationshipService(db).get_for_document(document_id)


@router.delete("/{relationship_id}", response_model=MessageResponse)
def delete_document_relationship(
    relationship_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.RELATIONSHIPS_WRITE)),
) -> MessageResponse:
    DocumentRelationshipService(db).delete_relationship(relationship_id)
    return MessageResponse(detail="Document relationship deleted.")
