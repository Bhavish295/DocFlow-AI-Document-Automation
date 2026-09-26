from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IngestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: str
    source_reference: str | None = None
    original_filename: str
    document_id: uuid.UUID | None = None
    processing_job_id: uuid.UUID | None = None
    status: str
    error_message: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class IngestionListResponse(BaseModel):
    items: list[IngestionResponse]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class BatchIngestionItemResult(BaseModel):
    filename: str
    ingestion_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    processing_job_id: uuid.UUID | None = None
    status: str
    error: str | None = None


class BatchIngestionResponse(BaseModel):
    total: int
    accepted: int
    failed: int
    skipped: int
    items: list[BatchIngestionItemResult]


class EmailAttachmentIngestRequest(BaseModel):
    provider: str = Field(default="mock", min_length=1, max_length=100)
    message_id: str = Field(min_length=1, max_length=255)
    sender: str | None = Field(default=None, max_length=255)
    subject: str | None = Field(default=None, max_length=500)
    received_at: datetime | None = None
    filename: str = Field(min_length=1, max_length=255)
    content_base64: str = Field(min_length=1)
    content_type: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] | None = None


class EmailAttachmentIngestResponse(BaseModel):
    filename: str
    ingestion_id: uuid.UUID
    document_id: uuid.UUID | None = None
    processing_job_id: uuid.UUID | None = None
    status: str
    error: str | None = None
    already_ingested: bool = False
