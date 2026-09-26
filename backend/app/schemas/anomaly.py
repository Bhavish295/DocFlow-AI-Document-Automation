from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, Field


class AnomalyTrainRequest(BaseModel):
    contamination: float | None = Field(default=None, ge=0.01, le=0.5)
    min_samples: int | None = Field(default=None, ge=5, le=10000)


class AnomalyScoreRequest(BaseModel):
    document_id: uuid.UUID | None = None
    document_ids: list[uuid.UUID] | None = None
    force: bool = False
    limit: int = Field(default=100, ge=1, le=500)


class AnomalyModelRunResponse(BaseModel):
    id: uuid.UUID
    model_name: str
    model_version: str
    status: str
    trained_at: datetime | None = None
    sample_count: int
    feature_count: int
    metadata: dict[str, Any] | None = None
    created_at: datetime


class AnomalyResult(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    filename: str | None = None
    document_type: str | None = None
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_total: float | None = None
    model_run_id: uuid.UUID
    model_name: str | None = None
    model_version: str | None = None
    anomaly_score: float
    status: str
    reasons: list[str] = Field(default_factory=list)
    feature_values: dict[str, Any] | None = None
    detected_at: datetime


class AnomalyListResponse(BaseModel):
    items: list[AnomalyResult]
    total: int
    page: int
    page_size: int
    total_pages: int = 0


class AnomalyModelRunListResponse(BaseModel):
    items: list[AnomalyModelRunResponse]
    total: int
    page: int
    page_size: int


class AnomalyScoreBatchResponse(BaseModel):
    model_run_id: uuid.UUID
    scored: int
    errors: list[dict[str, str]] = Field(default_factory=list)
    items: list[AnomalyResult] = Field(default_factory=list)


class AnomalySummaryResponse(BaseModel):
    latest_model_run: AnomalyModelRunResponse | None = None
    analyzed_documents: int
    anomalies_requiring_attention: int
    feature_names: list[str]
    disclaimer: str
