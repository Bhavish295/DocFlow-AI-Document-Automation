"""Analytics response schemas (read-only management reporting)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NamedCount(BaseModel):
    name: str
    count: int = 0


class CurrencyTotals(BaseModel):
    currency: str
    count: int = 0
    total: float = 0.0
    average: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    total_tax: float = 0.0
    average_tax: float = 0.0


class AnalyticsSummaryResponse(BaseModel):
    total_documents: int = 0
    processed_documents: int = 0
    failed_documents: int = 0
    documents_requiring_review: int = 0
    total_invoices: int = 0
    total_invoice_value_by_currency: list[CurrencyTotals] = Field(default_factory=list)
    total_purchase_orders: int = 0
    total_goods_receipts: int = 0
    validation_matched: int = 0
    validation_mismatch: int = 0
    validation_needs_review: int = 0
    three_way_matched: int = 0
    three_way_mismatch: int = 0
    three_way_needs_review: int = 0
    duplicate_pending: int = 0
    anomaly_count: int = 0
    active_processing_jobs: int = 0


class DocumentAnalyticsResponse(BaseModel):
    by_type: list[NamedCount] = Field(default_factory=list)
    by_status: list[NamedCount] = Field(default_factory=list)
    processing: dict[str, int] = Field(default_factory=dict)
    review_required: int = 0


class InvoiceAnalyticsResponse(BaseModel):
    invoice_count: int = 0
    by_currency: list[CurrencyTotals] = Field(default_factory=list)


class VendorAnalyticsRow(BaseModel):
    vendor: str
    vendor_id: str | None = None
    invoice_count: int = 0
    total_value: float = 0.0
    currency: str
    average_invoice: float = 0.0
    validation_issues: int = 0
    review_count: int = 0


class VendorAnalyticsResponse(BaseModel):
    vendor_count: int = 0
    items: list[VendorAnalyticsRow] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class ReviewAnalyticsResponse(BaseModel):
    pending: int = 0
    in_review: int = 0
    approved: int = 0
    rejected: int = 0
    total: int = 0
    by_reason: list[NamedCount] = Field(default_factory=list)
    average_age_hours: float | None = None
    median_age_hours: float | None = None


class ValidationAnalyticsResponse(BaseModel):
    invoice_po: dict[str, int] = Field(default_factory=dict)
    three_way: dict[str, int] = Field(default_factory=dict)
    mismatch_dimensions: list[NamedCount] = Field(default_factory=list)


class AnomalyAnalyticsResponse(BaseModel):
    normal: int = 0
    unusual: int = 0
    anomaly: int = 0
    requires_review: int = 0
    total_scored: int = 0


class DuplicateAnalyticsResponse(BaseModel):
    exact_duplicate: int = 0
    business_duplicate: int = 0
    similar_duplicate: int = 0
    pending: int = 0
    confirmed: int = 0
    dismissed: int = 0


class ProcessingAnalyticsResponse(BaseModel):
    queued: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    average_duration_seconds: float | None = None
    duration_sample_count: int = 0


class TrendSeriesPoint(BaseModel):
    period: str
    uploaded_documents: int = 0
    processed_documents: int = 0
    invoices: int = 0
    review_items: int = 0
    validation_mismatches: int = 0
    anomaly_findings: int = 0


class TrendsAnalyticsResponse(BaseModel):
    period: str
    granularity: str
    points: list[TrendSeriesPoint] = Field(default_factory=list)


class AnalyticsBundleResponse(BaseModel):
    """Optional combined payload for dashboard convenience."""

    summary: AnalyticsSummaryResponse
    documents: DocumentAnalyticsResponse
    invoices: InvoiceAnalyticsResponse
    reviews: ReviewAnalyticsResponse
    validations: ValidationAnalyticsResponse
    anomalies: AnomalyAnalyticsResponse
    duplicates: DuplicateAnalyticsResponse
    processing: ProcessingAnalyticsResponse
    trends: TrendsAnalyticsResponse
    filters: dict[str, Any] = Field(default_factory=dict)
