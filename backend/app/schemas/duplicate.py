from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, Field


class DuplicateResult(BaseModel):
    id: uuid.UUID
    source_document_id: uuid.UUID
    duplicate_document_id: uuid.UUID
    matched_document_id: uuid.UUID | None = None
    matched_filename: str | None = None
    matched_document_type: str | None = None
    source_filename: str | None = None
    duplicate_filename: str | None = None
    detection_type: str
    similarity_score: float | None = None
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)
    status: str
    detected_at: datetime
    resolved_at: datetime | None = None


class DuplicateListResponse(BaseModel):
    items: list[DuplicateResult]
    total: int
    page: int
    page_size: int
    total_pages: int = 0


class DuplicateDocumentResponse(BaseModel):
    document_id: uuid.UUID
    items: list[DuplicateResult]
    total: int


class DuplicateCheckResponse(BaseModel):
    document_id: uuid.UUID
    created_count: int
    items: list[DuplicateResult]
    summary: dict[str, Any]


class DuplicateResolveRequest(BaseModel):
    status: str = Field(..., description="pending | confirmed | dismissed")


class DuplicateSummary(BaseModel):
    exact: int = 0
    business: int = 0
    similar: int = 0
    pending: int = 0
    confirmed: int = 0
    dismissed: int = 0
    total: int = 0
