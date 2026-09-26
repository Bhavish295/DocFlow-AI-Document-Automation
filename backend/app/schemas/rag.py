import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DocumentIndexResponse(BaseModel):
    document_id: uuid.UUID
    chunks_created: int
    status: str
    detail: str | None = None


class DocumentIndexStatusResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    indexed: bool
    chunk_count: int
    last_indexed_at: datetime | None = None
    error: str | None = None


class RagSearchRequest(BaseModel):
    query: str
    top_k: int | None = Field(default=None, ge=1, le=50)
    document_type: str | None = None
    document_id: uuid.UUID | None = None


class RagSearchResult(BaseModel):
    document_id: uuid.UUID
    filename: str
    document_type: str | None = None
    chunk_id: uuid.UUID
    content: str
    similarity: float


class RagSearchResponse(BaseModel):
    query: str
    results: list[RagSearchResult]


class RagAskRequest(BaseModel):
    question: str
    top_k: int | None = Field(default=None, ge=1, le=50)
    document_type: str | None = None
    document_id: uuid.UUID | None = None


class RagSource(BaseModel):
    document_id: uuid.UUID
    filename: str
    document_type: str | None = None
    chunk_id: uuid.UUID
    content: str
    similarity: float


class RagAskResponse(BaseModel):
    question: str
    answer: str
    sources: list[RagSource]
