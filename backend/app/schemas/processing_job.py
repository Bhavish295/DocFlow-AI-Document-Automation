from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import DocumentResponse


class ProcessingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    job_type: str
    progress: int
    current_stage: str
    error_message: str | None = None
    cancel_requested: bool = False
    parent_job_id: uuid.UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProcessingJobListResponse(BaseModel):
    items: list[ProcessingJobResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class ProcessDocumentResponse(DocumentResponse):
    """Document payload plus processing-job metadata (backward compatible)."""

    job_id: uuid.UUID | None = None
    job_status: str | None = None
    current_stage: str | None = None
    progress: int | None = None
