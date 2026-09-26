from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentRelationshipCreate(BaseModel):
    source_document_id: uuid.UUID
    target_document_id: uuid.UUID
    relationship_type: str
    match_key: str | None = None


class DocumentRelationshipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_document_id: uuid.UUID
    target_document_id: uuid.UUID
    relationship_type: str
    status: str
    match_key: str | None = None
    created_at: datetime
    updated_at: datetime
    source_filename: str | None = None
    target_filename: str | None = None
    source_document_type: str | None = None
    target_document_type: str | None = None
    related_document_id: uuid.UUID | None = None
    related_filename: str | None = None
    related_document_type: str | None = None
    display_label: str | None = None


class DocumentRelationshipListResponse(BaseModel):
    items: list[DocumentRelationshipResponse]
    total: int


class DocumentRelationshipSuggestion(BaseModel):
    relationship_type: str
    source_document_id: uuid.UUID
    target_document_id: uuid.UUID
    match_key: str
    match_field: str
    source_filename: str | None = None
    target_filename: str | None = None
    source_document_type: str | None = None
    target_document_type: str | None = None
    status: str = "suggested"
    already_linked: bool = False


class DocumentRelationshipSuggestionListResponse(BaseModel):
    document_id: uuid.UUID
    items: list[DocumentRelationshipSuggestion] = Field(default_factory=list)
    total: int = 0
